import ctypes
import hashlib
from pathlib import Path
import random
import shutil
import subprocess
import pytest
from solders.pubkey import Pubkey
from solvanity_contract import Pattern, derive, seed_for
from solvanity_contract.search import CPU, CUDA, grind

ZERO = str(Pubkey.default())

def test_official_vector():
    assert derive(ZERO, "limber chicken: 4/45", ZERO) == "9h1HyLCW5dZnBVap8C5egQ9Z6pHyjsh5MNy83iPqqRuq"

@pytest.mark.parametrize("seed", ["", "☉", "😀"*8, "\0"*32, "a"*32])
def test_solders(seed):
    assert derive(ZERO, seed) == str(Pubkey.create_with_seed(Pubkey.default(), seed, Pubkey.from_string("TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA")))

def test_invalid_seed_owner():
    with pytest.raises(ValueError): derive(ZERO, "😀"*9)
    with pytest.raises(ValueError): derive(ZERO, "", Pubkey(bytes(11)+b"ProgramDerivedAddress"))
    with pytest.raises(ValueError): seed_for("😀"*5, 0)
    with pytest.raises(ValueError): seed_for("", 2**64)

@pytest.mark.parametrize("prefix,suffix,ic", [
    ("0","",False), ("O","",False), ("I","",False), ("l","",False),
    ("0","",True), ("z"*44,"",False), ("1"*33,"",False),
    ("1"*32,"2",False), ("a"*45,"",False), ("😀","",True)])
def test_impossible(prefix, suffix, ic):
    with pytest.raises(ValueError): Pattern(prefix,suffix,ic)

def test_case():
    assert Pattern("O", ignore_case=True).matches("o123")
    assert Pattern("I", ignore_case=True).matches("i123")
    assert Pattern("l", ignore_case=True).matches("L123")
    assert Pattern("Ab", "Z", True).matches("aBcZ")
    assert not Pattern("Ab", "Z").matches("aBcZ")

def test_possible_random_known():
    rng = random.Random(12)
    for i in range(100):
        address = str(Pubkey(rng.randbytes(32)))
        p, s = rng.randrange(len(address)+1), rng.randrange(len(address)+1)
        assert Pattern(address[:p],address[len(address)-s:] if s else "").matches(address)
    assert Pattern("1"*32).matches("1"*32)
    assert Pattern("z").possible()  # possible 43-char address even though 44-char z is impossible

def test_search():
    events=[]
    result=grind(base=ZERO,prefix="A",backend="cpu",batch_size=128,max_attempts=4096,namespace="test",on_event=events.append)
    assert result["status"]=="complete"
    assert result["hits"][0]["address"].startswith("A")
    assert any(e["type"]=="progress" and e["keys_per_second"]>0 for e in events)
    assert derive(ZERO,result["hits"][0]["seed"])==result["hits"][0]["address"]

def test_exhaustion_cancellation_wrap():
    assert grind(base=ZERO, prefix="abcdef", max_attempts=1)["status"]=="exhausted"
    assert grind(base=ZERO, should_stop=lambda:True)["status"]=="cancelled"
    with pytest.raises(ValueError): grind(base=ZERO,start=2**64-1,max_attempts=2)
    with pytest.raises(ValueError): grind(base=ZERO, backend="bad")

@pytest.fixture(scope="module")
def native(tmp_path_factory):
    if not shutil.which("g++"): pytest.skip("g++ needed for host differential tests")
    # /dev/shm can be noexec, so use pytest's regular tmp directory.
    out=tmp_path_factory.mktemp("kernel")/"kernel.so"
    source=Path(__file__).parents[1]/"solvanity_contract/kernel.cu"
    subprocess.run(["g++","-x","c++","-std=c++11","-O2","-shared","-fPIC","-DSOLVANITY_CPU_TEST",str(source),"-o",str(out)],check=True)
    lib=ctypes.CDLL(str(out))
    lib.cpu_hash.argtypes=[ctypes.c_char_p,ctypes.c_char_p,ctypes.c_char_p,ctypes.c_int,ctypes.c_uint64,ctypes.c_void_p]
    lib.cpu_base58.argtypes=[ctypes.c_char_p,ctypes.c_void_p]
    lib.cpu_match.argtypes=[ctypes.c_char_p,ctypes.c_int,ctypes.c_char_p,ctypes.c_int,ctypes.c_char_p,ctypes.c_int,ctypes.c_int]
    return lib

def test_native_hash_base58(native):
    rng=random.Random(123)
    for namespace in ["", "a", "😀"*4, "0123456789abcdef"]:
        for counter in [0,1,2**32-1,2**32,2**64-1]+[rng.randrange(2**64) for _ in range(100)]:
            base,owner=rng.randbytes(32),rng.randbytes(32)
            digest=ctypes.create_string_buffer(32)
            native.cpu_hash(base,owner,namespace.encode(),len(namespace.encode()),counter,digest)
            expected=hashlib.sha256(base+seed_for(namespace,counter).encode()+owner).digest()
            assert digest.raw==expected
            text=ctypes.create_string_buffer(45)
            native.cpu_base58(digest.raw,text)
            assert text.value.decode()==str(Pubkey(expected))
    for raw in [bytes(32),bytes(31)+b"\1",b"\xff"*32]+[bytes(z)+rng.randbytes(32-z) for z in range(32)]:
        text=ctypes.create_string_buffer(45)
        native.cpu_base58(raw,text)
        assert text.value.decode()==str(Pubkey(raw))

def test_native_matching(native):
    rng=random.Random(1234)
    for _ in range(200):
        a=str(Pubkey(rng.randbytes(32)))
        pre=a[:rng.randrange(5)]; suf=a[-rng.randrange(1,5):]
        for ic in [False,True]:
            if ic: pre=pre.swapcase();suf=suf.swapcase()
            p=Pattern(pre,suf,ic)
            assert bool(native.cpu_match(a.encode(),len(a),pre.encode(),len(pre),suf.encode(),len(suf),ic))==p.matches(a)

def gpu_available():
    try:
        import cupy
        return cupy.cuda.runtime.getDeviceCount()>0
    except Exception:
        return False

@pytest.mark.skipif(not gpu_available(),reason="CUDA GPU required")
def test_gpu_differential():
    base=Pubkey.default()
    from solvanity_contract.core import pubkey
    owner=pubkey("token")
    for ns in ["", "😀"*4, "0123456789abcdef"]:
        for pattern in [Pattern(),Pattern("A"),Pattern(suffix="z"),Pattern("a","Z",True)]:
            gpu=CUDA(base,owner,ns,pattern)
            cpu=CPU(base,owner,ns,pattern)
            for start in [0,2**32-17,2**64-257]:
                assert gpu.batch(start,257)==cpu.batch(start,257)
    result=grind(base=ZERO,prefix="a",ignore_case=True,backend="cuda",batch_size=4096,max_attempts=65536)
    assert result["status"]=="complete"
