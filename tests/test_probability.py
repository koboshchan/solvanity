from collections import Counter
import pytest
from solvanity.probability import matching_count, probability, estimate, _encode, ALPHABET

def test_kobosh_derived_interval_count():
    assert matching_count("kobosh", "", True) == 16 * 58 ** 37
    assert matching_count("kobosh") == 58 ** 37
    assert matching_count("K", "", True) == 2 * 58 ** 42
    assert (2**256 - 1) // 58**43 == ALPHABET.index("J")

def test_normalization_and_full_domain_partition():
    assert matching_count() == 2**256
    assert sum(matching_count(c) for c in ALPHABET) == 2**256
    assert matching_count("O", "", True) == matching_count("o")
    assert matching_count("l", "", True) == matching_count("L")
    assert matching_count("I", "", True) == matching_count("i")
    assert matching_count("0", "", True) == 0
    assert matching_count("O") == 0
    assert matching_count("1"*32) == 1
    assert matching_count("1"*33) == 0
    assert matching_count("2"*44, "3"*44) == 0
    assert matching_count("1"*32, "1"*32) == 1

@pytest.mark.parametrize("width",[1,2])
def test_exhaustive_uniform_byte_counts(width):
    addresses=[_encode(i.to_bytes(width,"big")) for i in range(1 << (8*width))]
    for prefix,suffix,fold in [("","",False),("1","",False),("","1",False),
                              ("K","",True),("o","",True),("l","",True),
                              ("a","a",True),("12","2",False),("1","11",False),
                              ("21","1",False),("","o",True),("J","",False)]:
        p,s=(prefix.lower(),suffix.lower()) if fold else (prefix,suffix)
        actual=sum((a.lower() if fold else a).startswith(p) and
                   (a.lower() if fold else a).endswith(s) for a in addresses)
        assert matching_count(prefix,suffix,fold,byte_length=width)==actual

def test_long_overlap_matches_single_encoding():
    for i in [0,1,255,256,2**248,2**256-1]:
        a=_encode(i.to_bytes(32,"big"))
        assert matching_count(a,a)==1

def test_estimate_not_deadline():
    e=estimate("kobosh","",True,1e6)
    assert 0 < e["median_seconds"] < e["mean_seconds"]
    assert e["exact_uniform_bytes"] and e["wallet_distribution_approximate"]
    assert estimate("0")["mean_seconds"] is None
