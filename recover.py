"""Recover only engine changes whose exact text survives in the task transcript."""
from pathlib import Path
import subprocess
root=Path(__file__).parent
def base(repo, sha, path):
    return subprocess.check_output(['git','-C',repo,'show',sha+':'+path]).decode()
sources={'wallet':('/home/kit/solvanity-recovery/unified','3abf6ce'),
         'contract':('/home/kit/solvanity-recovery/unified-contract-history','c083f7c')}
module='''"""Small hardware-aware launch policy; calibration uses real verified work."""
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
'''
tests='''import pytest
from solvanity_MODE.tuning import launch_candidates, LaunchTuner

@pytest.mark.parametrize("sms", [40, 60, 108, 56])
def test_sm_scaled_candidates(sms):
    configs = launch_candidates(dict(MultiProcessorCount=sms, MaxThreadsPerBlock=1024),
                                8*1024**3, 2**24, 128)
    assert configs[0] == (sms*64*4, 64)
    assert all(n > 0 and b in (64,128,256) and n <= 2**24 for n,b in configs)

def test_live_memory_cap_and_kernel_limit():
    configs = launch_candidates(dict(MultiProcessorCount=108, MaxThreadsPerBlock=128),
                                4096, 2**24, 128)
    assert configs == [(4,64),(4,128)]
    with pytest.raises(MemoryError):
        launch_candidates(dict(MultiProcessorCount=1, MaxThreadsPerBlock=64),0,100,128)
    with pytest.raises(ValueError):
        launch_candidates(dict(MultiProcessorCount=1, MaxThreadsPerBlock=32),4096,100,128)

def test_empirical_winner_and_bounded_calibration():
    now=[0.]
    t=LaunchTuner(dict(MultiProcessorCount=108,MaxThreadsPerBlock=1024),
                  8*1024**3,2**20,128,128,clock=lambda:now[0])
    expected=t.configs[-1]
    for i in range(len(t.configs)):
        n,b=t.config
        t.observe(n, .04/(i+1))
        if not t.done:
            # Ensure each config has >=30ms real work.
            while t.config == (n,b) and not t.done:
                t.observe(n,.04/(i+1))
    assert t.done
    assert t.config==expected
    assert t.report()["calibration_complete"]
    old=t.config
    assert not t.observe(99999,.0001)
    assert t.config==old

def test_cooperative_deadline():
    now=[0.]
    t=LaunchTuner(dict(MultiProcessorCount=1,MaxThreadsPerBlock=256),
                  1024**3,1000,128,clock=lambda:now[0])
    now[0]=3
    assert t.observe(10,.001)
    assert t.done and len(t.trials)==1
'''
extra='''
@pytest.mark.parametrize("bad", [True, False, 0, -1, 1.5, "auto"])
def test_invalid_explicit_batch(bad):
    IMPORT_GRIND
    with pytest.raises(ValueError):
        CALL


def test_mock_cuda_auto_and_override(monkeypatch):
    from types import SimpleNamespace
    IMPORTS
    device_calls = []
    calls = []
    def device():
        device_calls.append(True)
        return SimpleNamespace(attributes={"MultiProcessorCount": 4, "MaxThreadsPerBlock": 1024},
                               mem_info=(1024**3, 1024**3))
    class Engine:
        cp = SimpleNamespace(cuda=SimpleNamespace(Device=device))
        kernel = SimpleNamespace(attributes={"max_threads_per_block": 128})
        def __init__(self, *args): pass
        def scan(self, seeds, *args):
            calls.append((len(seeds)//32, self.block_size))
            return []
        def batch(self, start, n):
            calls.append((n, self.block_size, start))
            return []
        def close(self): pass
        block_size = 128
    PATCH
    events=[]
    AUTO
    assert len(device_calls) == 1
    assert events[0]["automatic"]
    assert calls[0][:2] == (7, 64)
    assert events[-1]["attempts"] == 7
    assert not any("keypair_json" in e or "phantom_secret" in e for e in events)
    calls.clear(); events.clear()
    EXPLICIT
    assert len(device_calls) == 1
    assert not events[0]["automatic"]
    assert [c[0] for c in calls] == [3,3,1]
    assert all(c[1]==128 for c in calls)
'''
for mode,(repo,sha) in sources.items():
    package='solvanity_'+mode
    out=root/package
    out.mkdir(exist_ok=True)
    (out/'tuning.py').write_text(module)
    main=base(repo,sha,package+'/__main__.py')
    assert 'type=int, default=65536' in main
    (out/'__main__.py').write_text(main.replace('type=int, default=65536','type=int, default=None, help="omit for SM-aware CUDA calibration; integer fixes batch size"'))
    if mode=='wallet':
        s=base(repo,sha,package+'/cuda_backend.py')
        s=s.replace('self.last_seconds = None','self.last_seconds = None\n        self.block_size = 128')
        s=s.replace('self.kernel(((n+127)//128,), (128,),','self.kernel(((n+self.block_size-1)//self.block_size,), (self.block_size,),')
        (out/'cuda_backend.py').write_text(s)
        s=base(repo,sha,package+'/core.py')
        s=s.replace('batch_size=65536, count=1','batch_size=None, count=1')
        s=s.replace('if not isinstance(batch_size, int) or not 1 <= batch_size <= 1048576:', 'if batch_size is not None and (not isinstance(batch_size, int) or isinstance(batch_size, bool) or not 1 <= batch_size <= 1048576):')
        s=s.replace('    try:\n        while len(results)', '''    try:
        tuner = None
        if batch_size is None and backend == "cuda":
            from .tuning import LaunchTuner
            device = engine.cp.cuda.Device()
            tuner = LaunchTuner(device.attributes, device.mem_info[0], 1048576, 128,
                                engine.kernel.attributes["max_threads_per_block"])
        batch_size = batch_size or 65536
        emit(dict(type="start", backend=backend, batch_size=tuner.config[0] if tuner else batch_size,
                  automatic=tuner is not None, tuning=tuner.report() if tuner else None))
        while len(results)''')
        s=s.replace('            n = batch_size if max_attempts', '''            if tuner:
                batch_size, engine.block_size = tuner.config
            batch_started = time.perf_counter()
            n = batch_size if max_attempts''')
        s=s.replace('            elapsed = time.monotonic()-start','''            if tuner and tuner.observe(n, time.perf_counter() - batch_started):
                emit(dict(type="tuning", **tuner.report()))
            elapsed = time.monotonic()-start''')
        (out/'core.py').write_text(s)
        t=tests.replace('MODE',mode)+'''
def test_cpu_auto_default_no_cuda():
    from solvanity_wallet.core import grind
    events=[]
    assert grind(backend="cpu",prefix="abcdef",max_attempts=7,on_event=events.append)==[]
    assert events[0]["automatic"] is False
    assert events[-1]["attempts"]==7
'''
        e=extra.replace('IMPORT_GRIND','from solvanity_wallet.core import grind').replace('CALL','grind(backend="cpu", batch_size=bad)').replace('IMPORTS','from solvanity_wallet.core import grind\n    import solvanity_wallet.cuda_backend as cuda').replace('PATCH','monkeypatch.setattr(cuda, "CUDABackend", Engine)').replace('AUTO','grind(backend="cuda", prefix="abcdef", max_attempts=7, on_event=events.append)').replace('EXPLICIT','grind(backend="cuda", prefix="abcdef", batch_size=3, max_attempts=7, on_event=events.append)')
    else:
        s=base(repo,sha,package+'/search.py')
        s=s.replace('self.cp, self.np = cp, np','self.cp, self.np = cp, np\n        self.block_size = 128')
        s=s.replace('self.kernel(((count + 127)//128,), (128,),','self.kernel(((count + self.block_size-1)//self.block_size,), (self.block_size,),')
        s=s.replace('backend="cpu", batch_size=65536','backend="cpu", batch_size=None')
        s=s.replace('if not 1 <= batch_size <= 2**24:', 'if batch_size is not None and (not isinstance(batch_size, int) or isinstance(batch_size, bool) or not 1 <= batch_size <= 2**24):')
        s=s.replace('    attempts, found = 0, []','''    tuner = None
    if batch_size is None and backend == "cuda":
        from .tuning import LaunchTuner
        device = engine.cp.cuda.Device()
        tuner = LaunchTuner(device.attributes, device.mem_info[0], 2**24, 32,
                            engine.kernel.attributes["max_threads_per_block"])
    batch_size = batch_size or 65536
    attempts, found = 0, []''')
        s=s.replace('"namespace": namespace, "start": start, "batch_size": batch_size})','''"namespace": namespace, "start": start, "batch_size": tuner.config[0] if tuner else batch_size,
          "automatic": tuner is not None, "tuning": tuner.report() if tuner else None})''')
        s=s.replace('            n = min(batch_size, budget - attempts)','''            if tuner:
                batch_size, engine.block_size = tuner.config
            batch_started = time.perf_counter()
            n = min(batch_size, budget - attempts)''')
        s=s.replace('            attempts += n','''            if tuner and tuner.observe(n, time.perf_counter() - batch_started):
                emit({"type": "tuning", **tuner.report()})
            attempts += n''')
        (out/'search.py').write_text(s)
        t=tests.replace('MODE',mode)+'''
def test_cpu_auto_default_no_cuda():
    from solvanity_contract.search import grind
    events=[]
    result=grind(base="11111111111111111111111111111111",backend="cpu",
                 prefix="abcdef",max_attempts=7,on_event=events.append)
    assert events[0]["automatic"] is False
    assert result["attempts"]==7
'''
        e=extra.replace('IMPORT_GRIND','from solvanity_contract.search import grind').replace('CALL','grind(base="11111111111111111111111111111111", backend="cpu", batch_size=bad)').replace('IMPORTS','from solvanity_contract.search import grind\n    import solvanity_contract.search as search').replace('PATCH','monkeypatch.setattr(search, "CUDA", Engine)').replace('AUTO','grind(base="11111111111111111111111111111111", namespace="test", backend="cuda", prefix="abcdef", max_attempts=7, on_event=events.append)').replace('EXPLICIT','grind(base="11111111111111111111111111111111", namespace="test", backend="cuda", prefix="abcdef", batch_size=3, max_attempts=7, on_event=events.append)')
    dest=root/'tests'/mode
    dest.mkdir(parents=True,exist_ok=True)
    (dest/'test_tuning.py').write_text(t+e)
print('Recovered nine engine/test files from public bases plus recorded exact edits.')
