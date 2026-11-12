"""CPU reference and custom CUDA backends. GPU imports stay lazy."""
from pathlib import Path
import hashlib
import time
import secrets
from .core import Pattern, pubkey, validate_owner, seed_for, verify_hit

class CPU:
    name = "cpu"
    def __init__(self, base, owner, namespace, pattern):
        self.base, self.owner = bytes(base), bytes(owner)
        self.namespace, self.pattern = namespace, pattern
    def batch(self, start, count):
        from solders.pubkey import Pubkey
        hits = []
        for counter in range(start, start + count):
            raw = hashlib.sha256(self.base + seed_for(self.namespace, counter).encode() + self.owner).digest()
            if self.pattern.matches(str(Pubkey(raw))):
                hits.append(counter)
        return hits

class CUDA:
    name = "cuda"
    def __init__(self, base, owner, namespace, pattern):
        import cupy as cp
        import numpy as np
        self.cp, self.np = cp, np
        source = Path(__file__).with_name("kernel.cu").read_text()
        self.kernel = cp.RawKernel(source, "grind", options=("--std=c++11",))
        self.vector_kernel = cp.RawKernel(source, "vectors", options=("--std=c++11",))
        def device(raw):
            return cp.asarray(np.frombuffer(raw or b"\0", dtype=np.uint8))
        self.base, self.owner = device(bytes(base)), device(bytes(owner))
        self.ns = device(namespace.encode())
        self.pre, self.suf = device(pattern.prefix.encode()), device(pattern.suffix.encode())
        self.nslen = np.int32(len(namespace.encode()))
        self.plen, self.slen = np.int32(len(pattern.prefix)), np.int32(len(pattern.suffix))
        self.ic = np.int32(pattern.ignore_case)
        # Compile before reporting timed attempts.
        self.kernel.compile()
        self.vector_kernel.compile()
        # Compare actual device SHA256 with hashlib on every backend startup.
        raw = self.hashes(0, 33)
        for counter, digest in enumerate(raw):
            expected = hashlib.sha256(bytes(base) + seed_for(namespace, counter).encode() + bytes(owner)).digest()
            if digest != expected:
                raise RuntimeError("CUDA startup SHA256 self-test failed")
        cp.cuda.get_current_stream().synchronize()

    def hashes(self, start, count):
        cp, np = self.cp, self.np
        out = cp.empty((count, 32), dtype=cp.uint8)
        self.vector_kernel(((count + 127)//128,), (128,),
            (self.base, self.owner, self.ns, self.nslen, np.uint64(start), np.uint32(count), out))
        return [row.tobytes() for row in cp.asnumpy(out)]

    def batch(self, start, count):
        cp, np = self.cp, self.np
        hit_count = cp.zeros(1, dtype=cp.uint32)
        hits = cp.empty(count, dtype=cp.uint64)
        self.kernel(((count + 127)//128,), (128,), (
            self.base, self.owner, self.ns, self.nslen, np.uint64(start), np.uint32(count),
            self.pre, self.plen, self.suf, self.slen, self.ic, hit_count, hits))
        n = int(hit_count.get()[0])  # synchronization included in throughput
        if n > count:
            raise RuntimeError("invalid GPU hit count")
        return sorted(int(v) for v in hits[:n].get())

def grind(*, base, owner="token", prefix="", suffix="", ignore_case=False,
          backend="cpu", batch_size=65536, max_attempts=None, count=1,
          namespace=None, start=0, on_event=None, should_stop=None):
    """Return summary; emit verified hit/progress dictionaries through on_event.

    No private key or RPC is needed. should_stop is checked between batches.
    max_attempts=None searches the remaining uint64 counter space.
    """
    base, owner = pubkey(base), pubkey(owner)
    validate_owner(owner)
    pattern = Pattern(prefix, suffix, ignore_case)
    namespace = secrets.token_hex(8) if namespace is None else namespace
    seed_for(namespace, start)
    if backend not in {"cpu", "cuda"}:
        raise ValueError("backend must be cpu or cuda")
    if not 1 <= batch_size <= 2**24:
        raise ValueError("batch_size must be between 1 and 16777216")
    if count < 1:
        raise ValueError("count must be positive")
    remaining = 2**64 - start
    if max_attempts is not None and not 1 <= max_attempts <= remaining:
        raise ValueError("max_attempts must be positive and cannot wrap uint64")
    budget = remaining if max_attempts is None else max_attempts
    engine = (CPU if backend == "cpu" else CUDA)(base, owner, namespace, pattern)
    emit = on_event or (lambda event: None)
    attempts, found = 0, []
    started = time.perf_counter()
    emit({"type": "start", "backend": backend, "base": str(base), "owner": str(owner),
          "namespace": namespace, "start": start, "batch_size": batch_size})
    status = "exhausted"
    try:
        while attempts < budget:
            if should_stop and should_stop():
                status = "cancelled"
                break
            n = min(batch_size, budget - attempts)
            counters = engine.batch(start + attempts, n)
            # Verify EVERY device hit, including extras after count is reached.
            for counter in counters:
                hit = verify_hit(base, owner, namespace, counter, pattern)
                if len(found) < count:
                    found.append(hit)
                    emit(hit)
            attempts += n
            elapsed = time.perf_counter() - started
            emit({"type": "progress", "attempts": attempts, "keys_per_second": attempts / max(elapsed, 1e-9),
                  "elapsed_seconds": elapsed, "hits": len(found), "next_counter": start + attempts})
            if len(found) >= count:
                status = "complete"
                break
    except KeyboardInterrupt:
        status = "cancelled"
    elapsed = time.perf_counter() - started
    summary = {"type": "summary", "status": status, "backend": backend, "attempts": attempts,
               "keys_per_second": attempts/max(elapsed, 1e-9), "elapsed_seconds": elapsed,
               "hits": found, "namespace": namespace, "next_counter": start + attempts,
               "base": str(base), "owner": str(owner)}
    emit(summary)
    return summary
