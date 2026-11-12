"""Small hardware-aware launch policy; calibration uses real verified work."""
import time


def launch_candidates(attributes, free_bytes, max_batch, bytes_per_candidate):
    """Conservative live-memory cap, not an occupancy or utilization guarantee."""
    sm = max(1, int(attributes["MultiProcessorCount"]))
    max_threads = int(attributes["MaxThreadsPerBlock"])
    cap = min(max_batch, int(free_bytes) // (8 * bytes_per_candidate))
    if cap < 1:
        raise MemoryError("insufficient free device memory for automatic search")
    configs = []
    for waves in (4, 16, 64, 256):
        for block in (64, 128, 256):
            if block > max_threads:
                continue
            n = min(cap, sm * block * waves)
            pair = (n, block)
            if pair not in configs:
                configs.append(pair)
    if not configs:
        raise ValueError("kernel must support at least 64 threads per block")
    return configs

class LaunchTuner:
    """Cooperative two-second budget, checked between non-preemptible batches.

    Each candidate gets >=30ms of real search work when possible. Timing includes
    host entropy, transfers and verification. Never creates or discards candidates.
    """
    def __init__(self, attributes, free_bytes, max_batch, bytes_per_candidate,
                 kernel_max_threads=1024, clock=time.perf_counter):
        attrs = dict(attributes)
        attrs["MaxThreadsPerBlock"] = min(attrs["MaxThreadsPerBlock"], kernel_max_threads)
        self.sm_count = attrs["MultiProcessorCount"]
        self.configs = launch_candidates(attrs, free_bytes, max_batch, bytes_per_candidate)
        self.clock = clock
        self.deadline = clock() + 2.0
        self.index = 0
        self.samples = []
        self.trials = []
        self.done = False
        self.selected = self.configs[0]

    @property
    def config(self):
        return self.selected if self.done else self.configs[self.index]

    def observe(self, attempts, seconds):
        if self.done:
            return False
        self.samples.append((attempts, seconds))
        spent = sum(s for _, s in self.samples)
        expired = self.clock() >= self.deadline
        if spent < .03 and not expired:
            return False
        n, block = self.config
        rate = sum(n for n, _ in self.samples) / max(spent, 1e-9)
        self.trials.append(dict(batch_size=n, block_size=block, keys_per_second=rate,
                                seconds=spent))
        self.samples = []
        self.index += 1
        if expired or self.index == len(self.configs):
            best = max(self.trials, key=lambda r: r["keys_per_second"])
            self.selected = (best["batch_size"], best["block_size"])
            self.done = True
            return True
        return False

    def report(self):
        n, block = self.config
        return dict(sm_count=self.sm_count, batch_size=n, block_size=block,
                    grid_blocks=(n + block - 1) // block,
                    calibration_complete=self.done, trials=self.trials)
