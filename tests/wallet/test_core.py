import json
import os
import stat
from unittest.mock import patch
import pytest
from solvanity_wallet.core import *

def test_rfc8032_vector():
    seed = bytes.fromhex("9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60")
    pub = bytes.fromhex("d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a")
    hit = verify_hit(seed, pub)
    assert bytes(hit["keypair_json"]) == seed+pub
    assert hit["address"] == str(Keypair.from_seed(seed).pubkey())

def test_b58_leading_zeros():
    assert b58encode(bytes(32)) == "1"*32
    assert b58encode(b"\0\0\1") == "112"
    for _ in range(100):
        seed = os.urandom(32)
        assert b58encode(public_key(seed)) == str(Keypair.from_seed(seed).pubkey())

@pytest.mark.parametrize("prefix,suffix,case",[("0","",False),("O","",False),("I","",False),("l","",False),("0","",True),("a"*45,"",False),("a"*44,"b",False)])
def test_bad_patterns(prefix,suffix,case):
    with pytest.raises(ValueError):
        validate_pattern(prefix,suffix,case)

def test_ignore_case_valid_equivalence():
    validate_pattern("oIl","",True)
    assert matches("Lio","lIO","",True)
    assert not matches("Lio","lIO","",False)

def test_mismatch_fail_closed():
    seed = bytes(32)
    with pytest.raises(RuntimeError):
        verify_hit(seed, bytes(32))
    with pytest.raises(RuntimeError):
        verify_hit(seed, public_key(seed), "ZZZZZZ")

def test_fresh_entropy_each_batch_and_max_attempts():
    events = []
    with patch("solvanity_wallet.core.os.urandom", wraps=os.urandom) as entropy:
        hits = grind(prefix="ZZZZZZZZ", backend="cpu", batch_size=4,
                     max_attempts=10,on_event=events.append)
    assert hits == []
    assert [c.args[0] for c in entropy.call_args_list] == [128,128,64]
    assert events[-1]["attempts"] == 10
    assert events[-1]["complete"] is False

def test_exports_and_no_overwrite(tmp_path):
    hit = grind(backend="cpu",batch_size=8,count=2,output_dir=tmp_path)[0]
    path = tmp_path/(hit["address"]+".json")
    assert json.loads(path.read_text()) == hit["keypair_json"]
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    with pytest.raises(FileExistsError):
        save_hit(hit,tmp_path)

@pytest.mark.parametrize("kwargs",[dict(batch_size=0),dict(batch_size=1048577),dict(count=0),dict(max_attempts=0),dict(backend="fake")])
def test_invalid_options(kwargs):
    with pytest.raises(ValueError):
        grind(**kwargs)
