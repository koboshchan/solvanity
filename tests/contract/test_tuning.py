import pytest
from solvanity_contract.tuning import launch_candidates, LaunchTuner

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

def test_cpu_auto_default_no_cuda():
    from solvanity_contract.search import grind
    events=[]
    result=grind(base="11111111111111111111111111111111",backend="cpu",
                 prefix="abcdef",max_attempts=7,on_event=events.append)
    assert events[0]["automatic"] is False
    assert result["attempts"]==7

@pytest.mark.parametrize("bad", [True, False, 0, -1, 1.5, "auto"])
def test_invalid_explicit_batch(bad):
    from solvanity_contract.search import grind
    with pytest.raises(ValueError):
        grind(base="11111111111111111111111111111111", backend="cpu", batch_size=bad)


def test_mock_cuda_auto_and_override(monkeypatch):
    from types import SimpleNamespace
    from solvanity_contract.search import grind
    import solvanity_contract.search as search
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
    monkeypatch.setattr(search, "CUDA", Engine)
    events=[]
    grind(base="11111111111111111111111111111111", namespace="test", backend="cuda", prefix="abcdef", max_attempts=7, on_event=events.append)
    assert len(device_calls) == 1
    assert events[0]["automatic"]
    assert calls[0][:2] == (7, 64)
    assert events[-1]["attempts"] == 7
    assert not any("keypair_json" in e or "phantom_secret" in e for e in events)
    calls.clear(); events.clear()
    grind(base="11111111111111111111111111111111", namespace="test", backend="cuda", prefix="abcdef", batch_size=3, max_attempts=7, on_event=events.append)
    assert len(device_calls) == 1
    assert not events[0]["automatic"]
    assert [c[0] for c in calls] == [3,3,1]
    assert all(c[1]==128 for c in calls)
