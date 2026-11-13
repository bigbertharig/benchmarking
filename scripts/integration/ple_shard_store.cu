#include <cuda_runtime.h>

#include <algorithm>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fcntl.h>
#include <string>
#include <unistd.h>
#include <vector>

struct shard {
    int dev;
    uint64_t first, rows;
    uint8_t * ptr;
    bool is1070;
    int bus;
};
static std::vector<shard> shards;
static int table_fd = -1;
static uint64_t table_rows = 0, row_bytes = 0, table_offset = 0, gpu_rows = 0;
static std::string last_error;
static constexpr uint64_t mib = 1024ull * 1024ull;

static bool cuda_ok(cudaError_t e, const char * where) {
    if (e == cudaSuccess) return true;
    last_error = std::string(where) + ": " + cudaGetErrorString(e);
    return false;
}
static bool read_all(void * dst, size_t n, uint64_t offset) {
    size_t done = 0;
    while (done < n) {
        ssize_t got = pread(table_fd, static_cast<char *>(dst) + done, n - done, offset + done);
        if (got <= 0) { last_error = "short GGUF pread"; return false; }
        done += size_t(got);
    }
    return true;
}
extern "C" const char * ple_shard_error() { return last_error.c_str(); }
extern "C" uint64_t ple_shard_gpu_rows() { return gpu_rows; }
extern "C" int ple_shard_init(const char * path, uint64_t rows, uint64_t bytes_per_row, uint64_t offset,
                               uint64_t cap6_mib, uint64_t cap8_mib) {
    if (table_fd >= 0) { last_error = "PLE shard store initialized twice"; return -1; }
    if (!path || !rows || !bytes_per_row || bytes_per_row > 4096 || rows > UINT64_MAX / bytes_per_row ||
        offset > UINT64_MAX - rows * bytes_per_row) { last_error = "invalid PLE geometry"; return -1; }
    table_fd = open(path, O_RDONLY);
    if (table_fd < 0) { last_error = std::string("cannot open PLE GGUF: ") + path; return -1; }
    table_rows = rows; row_bytes = bytes_per_row; table_offset = offset;
    int count = 0;
    if (!cuda_ok(cudaGetDeviceCount(&count), "cudaGetDeviceCount")) return -1;
    for (int dev = 0; dev < count; ++dev) {
        cudaDeviceProp p{};
        if (!cuda_ok(cudaGetDeviceProperties(&p, dev), "cudaGetDeviceProperties")) return -1;
        const bool is1070 = std::strstr(p.name, "1070") != nullptr;
        if (!is1070 && !std::strstr(p.name, "1060")) continue;
        int bus = -1;
        if (!cuda_ok(cudaDeviceGetAttribute(&bus, cudaDevAttrPciBusId, dev), "cudaDevAttrPciBusId")) return -1;
        shards.push_back({dev, 0, 0, nullptr, is1070, bus});
    }
    std::stable_sort(shards.begin(), shards.end(), [](const shard & a, const shard & b) { return a.is1070 && !b.is1070; });
    void * staging = nullptr;
    const size_t chunk = 32 * mib;
    if (!cuda_ok(cudaMallocHost(&staging, chunk), "cudaMallocHost")) return -1;
    uint64_t next = 0;
    for (auto & s : shards) {
        if (!cuda_ok(cudaSetDevice(s.dev), "cudaSetDevice")) return -1;
        size_t free_bytes = 0, total_bytes = 0;
        if (!cuda_ok(cudaMemGetInfo(&free_bytes, &total_bytes), "cudaMemGetInfo")) return -1;
        const uint64_t cap = (s.is1070 ? cap8_mib : cap6_mib) * mib;
        const uint64_t safe = free_bytes > 512 * mib ? free_bytes - 512 * mib : 0;
        const uint64_t nrows = std::min({cap, safe, (table_rows - next) * row_bytes}) / row_bytes;
        s.first = next; s.rows = nrows;
        if (!nrows) continue;
        const uint64_t nbytes = nrows * row_bytes;
        if (!cuda_ok(cudaMalloc(&s.ptr, nbytes), "cudaMalloc PLE shard")) return -1;
        for (uint64_t pos = 0; pos < nbytes; pos += chunk) {
            const size_t n = size_t(std::min<uint64_t>(chunk, nbytes - pos));
            if (!read_all(staging, n, table_offset + next * row_bytes + pos)) return -1;
            if (!cuda_ok(cudaMemcpy(s.ptr + pos, staging, n, cudaMemcpyHostToDevice), "cudaMemcpy PLE shard H2D")) return -1;
        }
        next += nrows;
        std::fprintf(stderr, "PLE_SHARD_LOADED cuda=%d bus=%02x first=%llu rows=%llu bytes=%llu\n",
                     s.dev, s.bus, (unsigned long long)s.first, (unsigned long long)nrows,
                     (unsigned long long)nbytes);
        std::fflush(stderr);
    }
    cudaFreeHost(staging);
    gpu_rows = next;
    std::fprintf(stderr, "PLE_SHARD_READY gpu_rows=%llu file_rows=%llu\n",
                 (unsigned long long)gpu_rows, (unsigned long long)(table_rows-gpu_rows));
    std::fflush(stderr);
    return 0;
}
extern "C" int ple_shard_fetch(const int32_t * indexes, size_t count, uint8_t * packed) {
    if (table_fd < 0 || !indexes || !packed) { last_error = "PLE store not ready"; return -1; }
    for (size_t i = 0; i < count; ++i) {
        const int64_t row = indexes[i];
        if (row < 0 || uint64_t(row) >= table_rows) { last_error = "PLE index out of range"; return -1; }
        bool found = false;
        for (const auto & s : shards) {
            if (uint64_t(row) < s.first || uint64_t(row) >= s.first + s.rows) continue;
            if (!cuda_ok(cudaSetDevice(s.dev), "cudaSetDevice fetch")) return -1;
            if (!cuda_ok(cudaMemcpy(packed + i * row_bytes, s.ptr + (uint64_t(row)-s.first)*row_bytes,
                                    row_bytes, cudaMemcpyDeviceToHost), "cudaMemcpy PLE row D2H")) return -1;
            found = true; break;
        }
        if (!found && !read_all(packed + i * row_bytes, row_bytes, table_offset + uint64_t(row)*row_bytes)) return -1;
    }
    return 0;
}
