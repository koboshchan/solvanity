"""CPU mocked-device cleanup tests, including late pipeline failures."""
from types import SimpleNamespace
import threading
import pytest
from solvanity_wallet.core import grind,public_key

def setup(monkeypatch,scan):
    batches=[]
    class Batch:
        def __init__(self,n):
            self.n=n; self.data=bytes(n*32); self.closed=False
            batches.append(self)
        def seed(self,i): return bytes(32)
        def close(self): self.closed=True
    closed=[]
    class Engine:
        def scan(self,data,*pattern): return scan(data)
        def close(self): closed.append(True)
    import solvanity_wallet.cuda_backend as cb
    monkeypatch.setattr(cb,"CUDABackend",Engine)
    monkeypatch.setattr("solvanity_wallet.entropy.source",lambda:SimpleNamespace(batch=Batch))
    return batches,closed

def test_stop_on_hit_closes_unused_lookahead(monkeypatch):
    batches,closed=setup(monkeypatch,lambda data:[(0,public_key(bytes(32)))])
    assert len(grind(backend="cuda",batch_size=2,count=1))==1
    assert len(batches)==2 and all(b.closed for b in batches)
    assert closed

def test_scan_failure_wipes_both_batches(monkeypatch):
    def fail(data): raise RuntimeError("device fault")
    batches,closed=setup(monkeypatch,fail)
    with pytest.raises(RuntimeError,match="device fault"):
        grind(backend="cuda",batch_size=2)
    assert len(batches)==2 and all(b.closed for b in batches)
    assert closed

def test_cpu_mismatch_no_export(monkeypatch):
    batches,closed=setup(monkeypatch,lambda data:[(0,bytes(32))])
    events=[]
    with pytest.raises(RuntimeError):
        grind(backend="cuda",batch_size=2,on_event=events.append)
    assert all(b.closed for b in batches) and closed
    assert not any(e["type"]=="hit" for e in events)

def test_callback_failure_cleans_pipeline(monkeypatch):
    batches,closed=setup(monkeypatch,lambda data:[])
    def callback(event):
        if event["type"]=="progress": raise RuntimeError("callback")
    with pytest.raises(RuntimeError,match="callback"):
        grind(backend="cuda",batch_size=2,max_attempts=4,on_event=callback)
    assert all(b.closed for b in batches) and closed

def test_worker_failure_closes_engine(monkeypatch):
    batches,closed=setup(monkeypatch,lambda data:[])
    calls=[]
    def fail(n):
        calls.append(n)
        if len(calls)>1: raise RuntimeError("entropy failure")
        class Batch:
            data=bytes(n*32)
            def close(self): batches.append("closed")
        return Batch()
    monkeypatch.setattr("solvanity_wallet.entropy.source",lambda:SimpleNamespace(batch=fail))
    with pytest.raises(RuntimeError,match="entropy failure"):
        grind(backend="cuda",batch_size=2,max_attempts=4)
    assert batches==["closed"] and closed
