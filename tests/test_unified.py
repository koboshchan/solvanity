import json
import subprocess
import sys
from solvanity import grind_wallet, grind_contract, derive_contract

def test_both_public_apis():
    hits = grind_wallet(prefix="", backend="cpu", count=1, batch_size=8, max_attempts=8)
    assert len(hits) == 1 and len(hits[0]["keypair_json"]) == 64
    result = grind_contract(base="11111111111111111111111111111111", prefix="", backend="cpu",
                           count=1, batch_size=8, max_attempts=8, namespace="unified-test")
    hit = result["hits"][0]
    assert derive_contract(hit["base"], hit["seed"], hit["owner"]) == hit["address"]

def test_cli_modes():
    for mode in ("wallet", "contract"):
        args = [sys.executable, "-m", "solvanity", mode, "grind", "--backend", "cpu",
                "--batch-size", "8", "--max-attempts", "8", "--count", "1", "--json"]
        if mode == "contract":
            args += ["--base", "11111111111111111111111111111111"]
        result = subprocess.run(args, capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
        events = [json.loads(line) for line in result.stdout.splitlines()]
        assert any(event["type"] == "hit" for event in events)
