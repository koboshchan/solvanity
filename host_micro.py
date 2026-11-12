"""Host-only RNG/copy microprofile, not a wallet throughput result or RNG change."""
import concurrent.futures, ctypes as C, ctypes.util, json, os, statistics, time
from pathlib import Path
def measure(fn,n,reps=32):
    samples=[]
    for _ in range(reps):
        t=time.perf_counter(); fn(n); samples.append(time.perf_counter()-t)
    return {"bytes":n,"repetitions":reps,"median_s":statistics.median(samples),
            "bytes_per_second":n*reps/sum(samples)}
def main():
    rows={}
    for n in (65536*32,110592*32,1048576*32):
        rows[str(n)]={"os_urandom":measure(os.urandom,n)}
        for workers in (2,4):
            with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
                def parallel(size):
                    parts=list(pool.map(os.urandom,[size//workers]*workers))
                    joined=b"".join(parts)
                    assert len(joined)==size
                rows[str(n)]["os_urandom_threads_"+str(workers)]=measure(parallel,n)
    libpath=ctypes.util.find_library("sodium")
    if libpath:
        lib=C.CDLL(libpath)
        lib.sodium_init.restype=C.c_int
        assert lib.sodium_init()>=0
        fn=lib.crypto_stream_chacha20_ietf
        fn.argtypes=[C.c_void_p,C.c_ulonglong,C.c_void_p,C.c_void_p]
        fn.restype=C.c_int
        wipe=lib.sodium_memzero; wipe.argtypes=[C.c_void_p,C.c_size_t]; wipe.restype=None
        for n in (65536*32,110592*32,1048576*32):
            output=C.create_string_buffer(n)
            def sodium(size):
                key=C.create_string_buffer(os.urandom(32),32)
                nonce=C.create_string_buffer(os.urandom(12),12)
                try:
                    assert fn(output,size,nonce,key)==0
                finally:
                    wipe(output,size); wipe(key,32); wipe(nonce,12)
            rows[str(n)]["libsodium_ietf_freshkey_freshnonce_wipe"]=measure(sodium,n)
    return {"scope":"Host-only microbench. Not wallet keys/s. Fresh OS key+nonce each sodium batch; includes output wipe, excludes H2D.", "libsodium":libpath,"rows":rows}
if __name__=="__main__":
    data=main()
    path=Path(os.environ.get("PROFILE_HOST_OUT","host-micro.json"))
    path.write_text(json.dumps(data,indent=2))
    print(json.dumps(data,indent=2))
