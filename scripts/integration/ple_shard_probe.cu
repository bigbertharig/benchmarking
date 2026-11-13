#include <cuda_runtime.h>

#include <algorithm>
#include <chrono>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fcntl.h>
#include <numeric>
#include <stdexcept>
#include <string>
#include <unistd.h>
#include <vector>

// Exact packed-row store; model-specific geometry comes from the GGUF header.
// This is a placement/correctness probe, not a model integration or dequantizer.
static uint64_t row_bytes = 0;
static uint64_t total_rows = 0;
static uint64_t tensor_offset = 0;
static constexpr uint64_t mib = 1024ull * 1024ull;

static void ck(cudaError_t e, const char * what) {
    if (e != cudaSuccess) throw std::runtime_error(std::string(what) + ": " + cudaGetErrorString(e));
}
static void read_all(int fd, void * dst, size_t bytes, uint64_t offset) {
    size_t done = 0;
    while (done < bytes) {
        ssize_t got = pread(fd, static_cast<char *>(dst) + done, bytes - done, offset + done);
        if (got <= 0) throw std::runtime_error("short GGUF pread");
        done += size_t(got);
    }
}
struct shard {
    int dev = -1;
    std::string name;
    int bus = -1;
    uint64_t first = 0, rows = 0;
    uint8_t * ptr = nullptr;
};
static std::vector<shard> shards;
static int fd = -1;

static void get_row(uint64_t row, void * dst) {
    if (row >= total_rows) throw std::runtime_error("row out of range");
    for (const auto & s : shards) {
        if (row < s.first || row >= s.first + s.rows) continue;
        ck(cudaSetDevice(s.dev), "cudaSetDevice fetch");
        ck(cudaMemcpy(dst, s.ptr + (row - s.first) * row_bytes, row_bytes,
                      cudaMemcpyDeviceToHost), "cudaMemcpy row D2H");
        return;
    }
    read_all(fd, dst, row_bytes, tensor_offset + row * row_bytes);
}
static double percentile(std::vector<double> v, double q) {
    std::sort(v.begin(), v.end());
    return v[size_t(q * (v.size() - 1))];
}
int main(int argc, char ** argv) {
    if (argc != 7) {
        std::fprintf(stderr, "usage: ple_shard_probe GGUF rows row_bytes absolute_offset per_1060_MiB per_1070_MiB\n");
        return 2;
    }
    const std::string path = argv[1];
    total_rows = std::stoull(argv[2]);
    row_bytes = std::stoull(argv[3]);
    tensor_offset = std::stoull(argv[4]);
    const uint64_t cap6 = std::stoull(argv[5]) * mib;
    const uint64_t cap8 = std::stoull(argv[6]) * mib;
    if (!total_rows || !row_bytes || row_bytes > 4096 || total_rows > UINT64_MAX / row_bytes ||
        tensor_offset > UINT64_MAX - total_rows * row_bytes) {
        std::fprintf(stderr, "invalid table dimensions or offset\n");
        return 2;
    }
    fd = open(path.c_str(), O_RDONLY);
    if (fd < 0) { perror("open GGUF"); return 3; }
    try {
        int count = 0;
        ck(cudaGetDeviceCount(&count), "cudaGetDeviceCount");
        if (count < 1) throw std::runtime_error("no CUDA cards");
        for (int dev = 0; dev < count; ++dev) {
            ck(cudaSetDevice(dev), "cudaSetDevice inventory");
            cudaDeviceProp prop{};
            ck(cudaGetDeviceProperties(&prop, dev), "cudaGetDeviceProperties");
            if (prop.totalGlobalMem < 5ull * 1024 * mib || prop.totalGlobalMem > 9ull * 1024 * mib)
                throw std::runtime_error("non-Pascal worker in visible CUDA set");
            int bus = -1;
            ck(cudaDeviceGetAttribute(&bus, cudaDevAttrPciBusId, dev), "cudaDevAttrPciBusId");
            shards.push_back({dev, prop.name, bus, 0, 0, nullptr});
        }
        std::sort(shards.begin(), shards.end(), [](const shard & a, const shard & b) {
            return a.name.find("1070") != std::string::npos && b.name.find("1070") == std::string::npos;
        });
        uint64_t next = 0;
        void * staging = nullptr;
        const size_t chunk = 32 * mib;
        ck(cudaMallocHost(&staging, chunk), "cudaMallocHost staging");
        auto load_start = std::chrono::steady_clock::now();
        for (auto & s : shards) {
            ck(cudaSetDevice(s.dev), "cudaSetDevice allocation");
            size_t free_bytes = 0, total_bytes = 0;
            ck(cudaMemGetInfo(&free_bytes, &total_bytes), "cudaMemGetInfo");
            const uint64_t desired = s.name.find("1070") != std::string::npos ? cap8 : cap6;
            const uint64_t safe = free_bytes > 512 * mib ? free_bytes - 512 * mib : 0;
            const uint64_t alloc_rows = std::min({desired, safe, (total_rows - next) * row_bytes}) / row_bytes;
            s.first = next;
            s.rows = alloc_rows;
            if (!alloc_rows) continue;
            ck(cudaMalloc(&s.ptr, alloc_rows * row_bytes), "cudaMalloc shard");
            const uint64_t bytes = alloc_rows * row_bytes;
            for (uint64_t offset = 0; offset < bytes; offset += chunk) {
                const size_t n = size_t(std::min<uint64_t>(chunk, bytes - offset));
                read_all(fd, staging, n, tensor_offset + next * row_bytes + offset);
                ck(cudaMemcpy(s.ptr + offset, staging, n, cudaMemcpyHostToDevice), "cudaMemcpy shard H2D");
            }
            next += alloc_rows;
            std::fprintf(stderr, "LOADED cuda=%d bus=%02x rows=%llu bytes=%llu next=%llu\n",
                         s.dev, s.bus, (unsigned long long)s.rows,
                         (unsigned long long)bytes, (unsigned long long)next);
            std::fflush(stderr);
        }
        ck(cudaFreeHost(staging), "cudaFreeHost staging");
        auto load_end = std::chrono::steady_clock::now();
        uint64_t seed = 0x1234abcdefull;
        auto rand_row = [&]() -> uint64_t {
            seed ^= seed << 13; seed ^= seed >> 7; seed ^= seed << 17;
            return seed % total_rows;
        };
        std::vector<uint64_t> checks{0, total_rows - 1};
        if (next < total_rows) checks.push_back(next);
        if (next) checks.push_back(next - 1);
        for (const auto & s : shards) {
            if (s.rows) {
                checks.push_back(s.first);
                checks.push_back(s.first + s.rows - 1);
            }
        }
        for (int i = 0; i < 500; ++i) checks.push_back(rand_row());
        std::vector<uint8_t> got(row_bytes), expected(row_bytes);
        uint64_t errors = 0, nvme_rows = 0;
        std::vector<double> us;
        for (uint64_t row : checks) {
            auto t0 = std::chrono::steady_clock::now();
            get_row(row, got.data());
            auto t1 = std::chrono::steady_clock::now();
            read_all(fd, expected.data(), row_bytes, tensor_offset + row * row_bytes);
            errors += std::memcmp(got.data(), expected.data(), row_bytes) != 0;
            nvme_rows += row >= next;
            us.push_back(std::chrono::duration<double, std::micro>(t1-t0).count());
        }
        double token_us = 0;
        for (int rep = 0; rep < 128; ++rep) {
            auto t0 = std::chrono::steady_clock::now();
            for (int i = 0; i < 16; ++i) get_row(rand_row(), got.data());
            auto t1 = std::chrono::steady_clock::now();
            token_us += std::chrono::duration<double, std::micro>(t1-t0).count();
        }
        token_us /= 128;
        std::printf("{\"schema\":\"ple-shard-probe/1\",\"table_rows\":%llu,\"row_bytes\":%llu,\"gpu_rows\":%llu,\"nvme_rows\":%llu,\"checked\":%zu,\"check_errors\":%llu,\"checked_nvme_rows\":%llu,\"load_s\":%.3f,\"row_p50_us\":%.3f,\"row_p95_us\":%.3f,\"sixteen_rows_mean_us\":%.3f}\n",
                    (unsigned long long)total_rows, (unsigned long long)row_bytes,
                    (unsigned long long)next, (unsigned long long)(total_rows-next), checks.size(),
                    (unsigned long long)errors, (unsigned long long)nvme_rows,
                    std::chrono::duration<double>(load_end-load_start).count(), percentile(us,.5), percentile(us,.95), token_us);
        for (auto & s : shards) if (s.ptr) { ck(cudaSetDevice(s.dev), "cudaSetDevice free"); ck(cudaFree(s.ptr), "cudaFree shard"); }
        close(fd);
        return errors ? 10 : 0;
    } catch (const std::exception & e) {
        std::fprintf(stderr, "PLE_SHARD_ERROR %s\n", e.what());
        close(fd);
        return 1;
    }
}
