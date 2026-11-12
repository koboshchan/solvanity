"""Lazy CUDA loading so CPU tests do not initialize or allocate a GPU."""
from pathlib import Path
import numpy as np

class CUDABackend:
    def __init__(self):
        try:
            import cupy as cp
        except ImportError as e:
            raise RuntimeError("install solvanity-wallet[cuda12] (or cuda13) first") from e
        self.cp = cp
        root = Path(__file__).parent / "cuda"
        # NVRTC compiles device-only primitives; stripping __host__ avoids unused
        # host variants referencing device precomputation tables.
        source = (root / "grind.cu").read_text()
        self.module = cp.RawModule(code=source,
            options=("--std=c++17", "-I"+str(root), "-D__host__="),
            name_expressions=("wallet_grind", "wallet_derive"))
        self.kernel = self.module.get_function("wallet_grind")
        self.derive_kernel = self.module.get_function("wallet_derive")
        self.last_seconds = None
        self.block_size = 128

    def derive(self, seeds):
        cp = self.cp
        n = len(seeds)//32
        if len(seeds) % 32 or not n:
            raise ValueError("nonempty whole 32-byte seeds required")
        src = cp.asarray(np.frombuffer(seeds, dtype=np.uint8))
        out = cp.empty((n,32), dtype=cp.uint8)
        try:
            self.derive_kernel(((n+127)//128,), (128,), (src,out,np.uint64(n)))
            return out.get().tobytes()
        finally:
            src.fill(0); out.fill(0); cp.cuda.get_current_stream().synchronize()

    def scan(self, seeds, prefix, suffix, ignore_case):
        cp = self.cp
        n = len(seeds)//32
        if len(seeds) % 32 or not n:
            raise ValueError("nonempty whole 32-byte seeds required")
        src = cp.asarray(np.frombuffer(seeds, dtype=np.uint8))
        pre = cp.asarray(np.frombuffer(prefix.encode("ascii"), dtype=np.uint8))
        suf = cp.asarray(np.frombuffer(suffix.encode("ascii"), dtype=np.uint8))
        found = cp.zeros(1, dtype=cp.uint32)
        # Capacity equals candidate count, so no hit can overflow or be lost.
        indices = cp.empty(n, dtype=cp.uint32)
        pubs = cp.empty((n,32), dtype=cp.uint8)
        start, end = cp.cuda.Event(), cp.cuda.Event()
        try:
            start.record()
            self.kernel(((n+self.block_size-1)//self.block_size,), (self.block_size,),
                (src,np.uint64(n),pre,np.int32(len(prefix)),suf,np.int32(len(suffix)),
                 np.int32(ignore_case),found,np.uint32(n),indices,pubs))
            end.record(); end.synchronize()
            self.last_seconds = cp.cuda.get_elapsed_time(start,end)/1000
            k = int(found.get()[0])
            if k > n:
                raise RuntimeError("GPU hit buffer overflow")
            ids, keys = indices[:k].get(), pubs[:k].get()
            return [(int(i), bytes(p)) for i,p in zip(ids,keys)]
        finally:
            src.fill(0); pubs.fill(0); cp.cuda.get_current_stream().synchronize()

    def close(self):
        self.cp.cuda.get_current_stream().synchronize()
