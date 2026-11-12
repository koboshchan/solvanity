import ctypes as C
import os
import pytest
from solvanity_wallet.entropy import Sodium,NativeBatch,OS,source,_range,LIMIT_BYTES

@pytest.fixture
def sodium():
    try: return Sodium()
    except (OSError,AttributeError): pytest.skip("optional system libsodium unavailable")

def test_rfc8439_and_ranges(sodium):
    # Constructor tests full RFC8439 2.3.2 vector, not merely a round primitive.
    assert _range(64,(1<<32)-1)==64
    assert _range(0,(1<<32)-1)==0
    for size,counter in [(65,(1<<32)-1),(1,1<<32),(-1,0),(1,-1),(LIMIT_BYTES+1,0)]:
        with pytest.raises(ValueError): _range(size,counter)

def test_random_and_boundary_independent_library(sodium):
    chacha=pytest.importorskip("Crypto.Cipher.ChaCha20")
    cases=[(0,1),(0,63),(0,64),(1,65),(65535,129),((1<<32)-2,63)]
    cases += [(int.from_bytes(os.urandom(4),"little")%100000,97) for _ in range(32)]
    for counter,size in cases:
        key=os.urandom(32); nonce=os.urandom(12)
        k=C.create_string_buffer(key,32); n=C.create_string_buffer(nonce,12)
        independent=chacha.new(key=key,nonce=nonce); independent.seek(counter*64)
        assert sodium.read(k,n,counter,size)==independent.encrypt(bytes(size))

def test_candidate_mapping_rederive_domains_and_wipe(sodium):
    a=sodium.batch(129); b=sodium.batch(129)
    try:
        assert bytes(a.data)!=bytes(b.data)
        assert a.key.raw!=b.key.raw and a.nonce.raw!=b.nonce.raw
        seeds=[a.seed(i) for i in (0,1,2,63,64,127,128)]
        assert len(set(seeds))==len(seeds)
        for i in (0,1,2,63,64,127,128):
            assert a.seed(i)==bytes(a.data[i*32:(i+1)*32])
        for i in (-1,129,True):
            with pytest.raises(RuntimeError): a.seed(i)
        a.output[0]=bytes([a.output.raw[0]^1])
        with pytest.raises(RuntimeError,match="recomputation"): a.seed(0)
    finally: a.close(); b.close()
    assert a.output.raw==bytes(129*32)
    assert a.key.raw==bytes(32) and a.nonce.raw==bytes(12)
    with pytest.raises(RuntimeError): a.seed(0)
    with pytest.raises(RuntimeError): _=a.data

def test_fresh_os_key_and_nonce_per_batch(sodium,monkeypatch):
    calls=[]
    def entropy(n):
        calls.append(n); return bytes([len(calls)])*n
    monkeypatch.setattr("solvanity_wallet.entropy.os.urandom",entropy)
    a=sodium.batch(1); b=sodium.batch(1)
    try:
        assert calls==[32,12,32,12]
        assert a.seed(0)!=b.seed(0)
    finally: a.close(); b.close()

def test_optional_absence_falls_back(monkeypatch):
    monkeypatch.setattr("solvanity_wallet.entropy.C.util.find_library",lambda _:None)
    assert isinstance(source(),OS)

def test_selftest_failure_does_not_fallback(monkeypatch):
    def bad(): raise RuntimeError("selftest failure")
    monkeypatch.setattr("solvanity_wallet.entropy.Sodium",bad)
    with pytest.raises(RuntimeError): source()

def test_bad_sizes(sodium):
    for n in (0,-1,True,1048577):
        with pytest.raises(ValueError): sodium.batch(n)
