"""Optional maintained libsodium RFC8439 expansion, never custom cryptography.

CUDA batches use a fresh OS 256-bit key and 96-bit nonce per batch. Candidate i
is bytes [32*i, 32*i+32) of that batch's stream, starting at block counter 0.
No key/nonce is reused between batches. CPU-only mode retains direct OS seeds.
"""
from __future__ import annotations
import ctypes as C
import ctypes.util
import os

LIMIT_BYTES = (1 << 32) * 64
MAX_BATCH = 1048576

def _range(size, counter=0):
    if (not isinstance(size, int) or isinstance(size, bool) or size < 0 or
        not isinstance(counter, int) or isinstance(counter, bool) or
        not 0 <= counter < 1 << 32 or size > LIMIT_BYTES-counter*64):
        raise ValueError("RFC8439 counter exhaustion or invalid range")
    return size

class Sodium:
    def __init__(self):
        path = C.util.find_library("sodium")
        if not path:
            raise OSError("system libsodium unavailable")
        self.lib = C.CDLL(path)
        self.lib.sodium_init.argtypes = []
        self.lib.sodium_init.restype = C.c_int
        if self.lib.sodium_init() < 0:
            raise RuntimeError("libsodium initialization failed")
        self.stream = self.lib.crypto_stream_chacha20_ietf
        self.stream.argtypes = [C.c_void_p,C.c_ulonglong,C.c_void_p,C.c_void_p]
        self.stream.restype = C.c_int
        self.xor = self.lib.crypto_stream_chacha20_ietf_xor_ic
        self.xor.argtypes = [C.c_void_p,C.c_void_p,C.c_ulonglong,C.c_void_p,C.c_uint32,C.c_void_p]
        self.xor.restype = C.c_int
        self.wipe = self.lib.sodium_memzero
        self.wipe.argtypes = [C.c_void_p,C.c_size_t]
        self.wipe.restype = None
        # RFC8439 section 2.3.2, counter1, nonce000000090000004a00000000.
        key=C.create_string_buffer(bytes(range(32)),32)
        nonce=C.create_string_buffer(bytes.fromhex("000000090000004a00000000"),12)
        expected=bytes.fromhex("10f1e7e4d13b5915500fdd1fa32071c4c7d1f4c733c068030422aa9ac3d46c4e"
                               "d2826446079faa0914c2d705d98b02a2b5129cd1de164eb9cbd083e8a2503c4e")
        if self.read(key,nonce,1,64) != expected:
            raise RuntimeError("libsodium RFC8439 self-test failed")

    def read(self,key,nonce,counter,size):
        _range(size,counter)
        out=C.create_string_buffer(size)
        try:
            if self.xor(out,out,size,nonce,counter,key) != 0:
                raise RuntimeError("libsodium ChaCha20 failure")
            return out.raw
        finally:
            self.wipe(out,size)

    def batch(self,n):
        return NativeBatch(self,n)

class NativeBatch:
    def __init__(self,sodium,n):
        if not isinstance(n,int) or isinstance(n,bool) or not 1 <= n <= MAX_BATCH:
            raise ValueError("invalid seed batch size")
        self.sodium=sodium; self.n=n; self.closed=False
        self.key=C.create_string_buffer(32); self.nonce=C.create_string_buffer(12)
        self.output=C.create_string_buffer(_range(n*32))
        try:
            # Fresh domain per batch, never reset a stream under a reused key.
            C.memmove(self.key,os.urandom(32),32)
            C.memmove(self.nonce,os.urandom(12),12)
            if sodium.stream(self.output,n*32,self.nonce,self.key) != 0:
                raise RuntimeError("libsodium ChaCha20 generation failed")
        except BaseException:
            self.close()
            raise

    @property
    def data(self):
        if self.closed: raise RuntimeError("seed batch is closed")
        return memoryview(self.output).cast("B")

    def seed(self,index):
        if self.closed: raise RuntimeError("seed batch is closed")
        if not isinstance(index,int) or isinstance(index,bool) or not 0 <= index < self.n:
            raise RuntimeError("invalid GPU candidate index")
        # Recompute only this hit's block on CPU, not trust a GPU-provided seed.
        block=self.sodium.read(self.key,self.nonce,index//2,64)
        seed=block[(index%2)*32:(index%2+1)*32]
        if seed != bytes(self.data[index*32:(index+1)*32]):
            raise RuntimeError("CPU ChaCha20 recomputation mismatch")
        return seed

    def close(self):
        if not self.closed:
            self.sodium.wipe(self.output,self.n*32)
            self.sodium.wipe(self.key,32); self.sodium.wipe(self.nonce,12)
            self.closed=True

class OSBatch:
    def __init__(self,n):
        if not isinstance(n,int) or not 1 <= n <= MAX_BATCH:
            raise ValueError("invalid seed batch size")
        self.n=n; self.data=os.urandom(n*32)
    def seed(self,index):
        if not isinstance(index,int) or isinstance(index,bool) or not 0 <= index < self.n:
            raise RuntimeError("invalid GPU candidate index")
        return self.data[index*32:(index+1)*32]
    def close(self):
        self.data=b""

class OS:
    batch=staticmethod(OSBatch)

def source():
    # Absence of an optional native library retains the secure OS path.
    # Initialization/self-test failures are NOT swallowed.
    try:
        return Sodium()
    except (OSError,AttributeError):
        return OS()
