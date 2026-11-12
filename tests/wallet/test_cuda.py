"""GPU QA: SOLVANITY_TEST_CUDA=1 pytest tests/test_cuda.py -v"""
import os
import pytest
from solvanity_wallet.core import public_key, b58encode, verify_hit

pytestmark = pytest.mark.skipif(os.environ.get("SOLVANITY_TEST_CUDA") != "1",
                              reason="explicit GPU QA opt-in required")

def test_cuda_derivation_rfc_and_random():
    from solvanity_wallet.cuda_backend import CUDABackend
    engine = CUDABackend()
    seeds = [bytes(32),bytes([255])*32,
             bytes.fromhex("9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60")]
    seeds += [os.urandom(32) for _ in range(257)]
    try:
        pubs = engine.derive(b"".join(seeds))
        assert pubs == b"".join(public_key(s) for s in seeds)
    finally:
        engine.close()

@pytest.mark.parametrize("ignore_case", [False,True])
def test_cuda_matching_and_every_hit_verified(ignore_case):
    from solvanity_wallet.cuda_backend import CUDABackend
    engine = CUDABackend()
    seeds = [os.urandom(32) for _ in range(300)]
    pubs = [public_key(seed) for seed in seeds]
    addresses = [b58encode(pub) for pub in pubs]
    try:
        for prefix,suffix in [("",""),(addresses[0][:2],""),("",addresses[1][-2:]),
                              (addresses[2][:1],addresses[2][-1:]),
                              (addresses[3][:2].swapcase(),"")]:
            hits = engine.scan(b"".join(seeds),prefix,suffix,ignore_case)
            from solvanity_wallet.core import matches
            expected = {i for i,a in enumerate(addresses) if matches(a,prefix,suffix,ignore_case)}
            assert {i for i,_ in hits} == expected
            for i,pub in hits:
                verify_hit(seeds[i],pub,prefix,suffix,ignore_case)
    finally:
        engine.close()


def test_cuda_reused_buffer_sizes_and_wipe():
    from solvanity_wallet.cuda_backend import CUDABackend
    from solvanity_wallet.entropy import source
    engine=CUDABackend()
    entropy=source()
    try:
        for n in (257,1024,1,999,2049,3):
            batch=entropy.batch(n)
            try:
                hits=engine.scan(batch.data,"","",False)
                assert len(hits)==n
                for i,pub in hits: verify_hit(batch.seed(i),pub)
                assert not engine._buffers[0].get().any()
                assert not engine._buffers[2].get().any()
            finally: batch.close()
    finally: engine.close()
