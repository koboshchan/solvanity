"""Genuine Ed25519 keypairs with CPU-verified CSPRNG candidate streams."""
from __future__ import annotations
import json
import os
from pathlib import Path
import time
from nacl.signing import SigningKey
from solders.keypair import Keypair

ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"

def b58encode(data: bytes) -> str:
    zeros = len(data) - len(data.lstrip(b"\0"))
    n = int.from_bytes(data, "big")
    chars = []
    while n:
        n, r = divmod(n, 58)
        chars.append(ALPHABET[r])
    return "1" * zeros + "".join(reversed(chars))

def validate_pattern(prefix="", suffix="", ignore_case=False):
    for pattern in (prefix, suffix):
        if not isinstance(pattern, str) or len(pattern) > 44:
            raise ValueError("patterns must be strings of at most 44 characters")
        for c in pattern:
            options = (c.lower(), c.upper()) if ignore_case else (c,)
            if not any(option in ALPHABET for option in options):
                raise ValueError(f"{c!r} cannot occur in base58 under this case mode")
    # Overlapping prefix/suffix positions depend on the address length; compare
    # only overlaps unavoidable even at maximum (44-character) length.
    p, s = (prefix.lower(), suffix.lower()) if ignore_case else (prefix, suffix)
    overlap = len(p) + len(s) - 44
    if overlap > 0 and p[-overlap:] != s[:overlap]:
        raise ValueError("prefix and suffix have incompatible overlap")

def matches(address, prefix="", suffix="", ignore_case=False):
    if ignore_case:
        address, prefix, suffix = address.lower(), prefix.lower(), suffix.lower()
    return address.startswith(prefix) and address.endswith(suffix)

def public_key(seed):
    if len(seed) != 32:
        raise ValueError("seed must be exactly 32 bytes")
    return bytes(SigningKey(seed).verify_key)

def verify_hit(seed, gpu_pub, prefix="", suffix="", ignore_case=False):
    """Two independent CPU implementations must agree before exporting secrets."""
    nacl_pub = public_key(seed)
    keypair = Keypair.from_seed(seed)
    solders_pub = bytes(keypair.pubkey())
    if nacl_pub != bytes(gpu_pub) or solders_pub != nacl_pub:
        raise RuntimeError("CPU/GPU Ed25519 verification mismatch; refusing key export")
    address = b58encode(nacl_pub)
    if not matches(address, prefix, suffix, ignore_case):
        raise RuntimeError("CPU pattern verification failed; refusing key export")
    message = b"solvanity-wallet self-verification v1"
    signing = SigningKey(seed)
    signing.verify_key.verify(message, signing.sign(message).signature)
    secret = seed + nacl_pub
    if bytes(keypair) != secret:
        raise RuntimeError("Solana secret-key encoding verification failed")
    return dict(address=address, keypair_json=list(secret), phantom_secret=b58encode(secret))

def save_hit(hit, output_dir):
    path = Path(output_dir)
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    target = path / (hit["address"] + ".json")
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(hit["keypair_json"], f)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())
    return str(target)

class CPUBackend:
    def scan(self, seeds, prefix, suffix, ignore_case):
        hits = []
        for i in range(len(seeds)//32):
            pub = public_key(seeds[i*32:(i+1)*32])
            if matches(b58encode(pub), prefix, suffix, ignore_case):
                hits.append((i, pub))
        return hits
    def close(self):
        pass

def grind(*, prefix="", suffix="", ignore_case=False, backend="cuda",
          batch_size=None, count=1, max_attempts=None, on_event=None,
          output_dir=None):
    """Return verified hits. Callback receives progress/hit/done dictionaries.

    The hit callback intentionally includes private material. Never log it to a
    public/shared output. Progress events never include candidate seeds.
    """
    validate_pattern(prefix, suffix, ignore_case)
    if batch_size is not None and (not isinstance(batch_size, int) or isinstance(batch_size, bool) or not 1 <= batch_size <= 1048576):
        raise ValueError("batch_size must be between 1 and 1048576")
    if count < 1 or (max_attempts is not None and max_attempts < 1):
        raise ValueError("count and max_attempts must be positive")
    if backend not in ("cpu", "cuda"):
        raise ValueError("backend must be cpu or cuda")
    if backend == "cuda":
        from .cuda_backend import CUDABackend
        engine = CUDABackend()
    else:
        engine = CPUBackend()
    emit = on_event or (lambda event: None)
    results = []
    attempts = 0
    start = time.monotonic()
    pool = None
    pending = None
    seed_source = None
    try:
        if backend == "cuda":
            from concurrent.futures import ThreadPoolExecutor
            from .entropy import source
            seed_source = source()
            pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="wallet-entropy")
        tuner = None
        if batch_size is None and backend == "cuda":
            from .tuning import LaunchTuner
            device = engine.cp.cuda.Device()
            tuner = LaunchTuner(device.attributes, device.mem_info[0], 1048576, 128,
                                engine.kernel.attributes["max_threads_per_block"])
        batch_size = batch_size or 65536
        emit(dict(type="start", backend=backend, batch_size=tuner.config[0] if tuner else batch_size,
                  automatic=tuner is not None, tuning=tuner.report() if tuner else None))
        while len(results) < count and (max_attempts is None or attempts < max_attempts):
            if tuner:
                batch_size, engine.block_size = tuner.config
            batch_started = time.perf_counter()
            n = batch_size if max_attempts is None else min(batch_size, max_attempts-attempts)
            if seed_source:
                batch = pending.result() if pending is not None else seed_source.batch(n)
                pending = None
                try:
                    # Once calibration is stable, overlap next native/OS batch
                    # with current CUDA work. At most two seed batches exist.
                    if tuner is None or tuner.done:
                        remaining = None if max_attempts is None else max_attempts-attempts-n
                        if remaining is None or remaining > 0:
                            next_n = batch_size if remaining is None else min(batch_size,remaining)
                            pending = pool.submit(seed_source.batch,next_n)
                    candidates = engine.scan(batch.data,prefix,suffix,ignore_case)
                    verified = [verify_hit(batch.seed(index),pub,prefix,suffix,ignore_case)
                                for index,pub in candidates]
                finally:
                    batch.close()
            else:
                # CPU reference retains one independent OS seed per candidate.
                seeds = os.urandom(32*n)
                candidates = engine.scan(seeds,prefix,suffix,ignore_case)
                verified = [verify_hit(seeds[index*32:(index+1)*32],pub,
                                       prefix,suffix,ignore_case)
                            for index,pub in candidates]
            attempts += n
            # Verify the entire device result batch before exporting any hit.
            for hit in verified:
                if len(results) < count:
                    if output_dir is not None:
                        hit["path"] = save_hit(hit, output_dir)
                    results.append(hit)
                    emit(dict(type="hit", **hit))
            if tuner and tuner.observe(n, time.perf_counter() - batch_started):
                emit(dict(type="tuning", **tuner.report()))
            elapsed = time.monotonic()-start
            emit(dict(type="progress", backend=backend, attempts=attempts,
                      elapsed_seconds=elapsed, keys_per_second=attempts/max(elapsed,1e-9),
                      found=len(results)))
        emit(dict(type="done", attempts=attempts, found=len(results),
                  elapsed_seconds=time.monotonic()-start, complete=len(results)>=count))
        return results
    finally:
        try:
            if pool is not None:
                pool.shutdown(wait=True)
            if pending is not None:
                pending.result().close()
        finally:
            engine.close()
        # Best-effort wipe only; immutable copies can survive. See SECURITY.md.
