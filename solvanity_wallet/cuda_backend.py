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
        self.stream = cp.cuda.Stream(non_blocking=True)
        self._buffers = None
        self._capacity = 0
        self._pattern = None
        self._pre = self._suf = None

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
        # Reuse bounded buffers across batches; wipe secrets before any reuse.
        with self.stream:
            if n > self._capacity:
                self._buffers = (cp.empty(n*32,dtype=cp.uint8),
                                 cp.empty(n,dtype=cp.uint32),
                                 cp.empty((n,32),dtype=cp.uint8),
                                 cp.zeros(1,dtype=cp.uint32))
                self._capacity = n
            src,indices,pubs,found = self._buffers
            pattern=(prefix,suffix)
            if pattern != self._pattern:
                self._pre = cp.asarray(np.frombuffer(prefix.encode("ascii"),dtype=np.uint8))
                self._suf = cp.asarray(np.frombuffer(suffix.encode("ascii"),dtype=np.uint8))
                self._pattern = pattern
            start,end = cp.cuda.Event(),cp.cuda.Event()
            try:
                src[:n*32].set(np.frombuffer(seeds,dtype=np.uint8),stream=self.stream)
                found.fill(0)
                start.record()
                self.kernel(((n+self.block_size-1)//self.block_size,),(self.block_size,),
                    (src,np.uint64(n),self._pre,np.int32(len(prefix)),
                     self._suf,np.int32(len(suffix)),np.int32(ignore_case),
                     found,np.uint32(n),indices,pubs))
                end.record()
                # The count copy is already a synchronization point. Avoid a
                # redundant end.synchronize and copy only actual hit payloads.
                k=int(found.get(stream=self.stream)[0])
                self.last_seconds=cp.cuda.get_elapsed_time(start,end)/1000
                if k > n:
                    raise RuntimeError("GPU hit buffer overflow")
                if k == 0:
                    return []
                ids=indices[:k].get(stream=self.stream)
                keys=pubs[:k].get(stream=self.stream)
                if any(int(i)>=n for i in ids):
                    raise RuntimeError("invalid GPU candidate index")
                return [(int(i),bytes(p)) for i,p in zip(ids,keys)]
            finally:
                src.fill(0); pubs.fill(0)
                self.stream.synchronize()

    def close(self):
        with self.stream:
            if self._buffers is not None:
                self._buffers[0].fill(0); self._buffers[2].fill(0)
            self.stream.synchronize()
        self._buffers=None
        self._capacity=0
        self.cp.cuda.get_current_stream().synchronize()
