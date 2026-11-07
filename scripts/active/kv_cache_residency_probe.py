"""Measure five independent GPU KV reservations without loading a model.

The cache sizes are inputs in MiB, so this probe applies to dense and MoE
models after their real KV bytes per token have been measured separately.
"""

import argparse
import ctypes
import json
import time


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cudart", required=True)
    parser.add_argument("--cache-mib", type=int, required=True)
    parser.add_argument("--workspace-mib", type=int, required=True)
    parser.add_argument("--devices", default="1,2,3,4,5")
    args = parser.parse_args()
    cuda = ctypes.CDLL(args.cudart)
    cuda.cudaSetDevice.argtypes = [ctypes.c_int]
    cuda.cudaMalloc.argtypes = [ctypes.POINTER(ctypes.c_void_p), ctypes.c_size_t]
    cuda.cudaFree.argtypes = [ctypes.c_void_p]
    cuda.cudaMemGetInfo.argtypes = [ctypes.POINTER(ctypes.c_size_t), ctypes.POINTER(ctypes.c_size_t)]
    cuda.cudaGetErrorString.argtypes = [ctypes.c_int]
    cuda.cudaGetErrorString.restype = ctypes.c_char_p

    def check(code):
        if code:
            raise RuntimeError(cuda.cudaGetErrorString(code).decode())

    def memory():
        free = ctypes.c_size_t()
        total = ctypes.c_size_t()
        check(cuda.cudaMemGetInfo(ctypes.byref(free), ctypes.byref(total)))
        return {"free_mib": round(free.value / 1048576, 2), "total_mib": round(total.value / 1048576, 2)}

    devices = [int(item) for item in args.devices.split(",")]
    held = []
    rows = []
    try:
        for device in devices:
            check(cuda.cudaSetDevice(device))
            before = memory()
            cache = ctypes.c_void_p()
            workspace = ctypes.c_void_p()
            cache_error = cuda.cudaMalloc(ctypes.byref(cache), args.cache_mib * 1048576)
            workspace_error = 0
            if cache_error == 0:
                held.append((device, cache))
                workspace_error = cuda.cudaMalloc(ctypes.byref(workspace), args.workspace_mib * 1048576)
                if workspace_error == 0:
                    held.append((device, workspace))
            rows.append({"device": device, "before": before, "after": memory(),
                         "cache_ok": cache_error == 0, "workspace_ok": cache_error == 0 and workspace_error == 0,
                         "cache_error": None if cache_error == 0 else cuda.cudaGetErrorString(cache_error).decode(),
                         "workspace_error": None if workspace_error == 0 else cuda.cudaGetErrorString(workspace_error).decode()})
            if cache_error or workspace_error:
                break
        print(json.dumps({"schema": "kv-residency-probe/1", "time_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                          "cache_mib_per_device": args.cache_mib, "workspace_mib_per_device": args.workspace_mib,
                          "all_fit": len(rows) == len(devices) and all(row["workspace_ok"] for row in rows),
                          "devices": rows}, separators=(",", ":")))
    finally:
        for device, pointer in reversed(held):
            cuda.cudaSetDevice(device)
            cuda.cudaFree(pointer)


if __name__ == "__main__":
    main()
