import argparse
import json
import sys
from .core import derive
from .search import grind

def main(argv=None):
    parser = argparse.ArgumentParser(description="Grind seeded Solana accounts, not wallets or PDAs")
    sub = parser.add_subparsers(dest="command", required=True)
    search = sub.add_parser("grind")
    verify = sub.add_parser("verify")
    for p in (search, verify):
        p.add_argument("--base", required=True, help="public base signer address ONLY")
        p.add_argument("--owner", default="token", help="token, token2022, or a program pubkey")
        p.add_argument("--json", action="store_true", help="JSON Lines output")
    verify.add_argument("--seed", required=True)
    verify.add_argument("--address", help="optional expected address")
    search.add_argument("--prefix", default="")
    search.add_argument("--suffix", default="")
    search.add_argument("--ignore-case", "--ignorecase", action="store_true")
    search.add_argument("--backend", choices=["cpu", "cuda"], default="cpu")
    search.add_argument("--batch-size", type=int, default=None, help="omit for SM-aware CUDA calibration; integer fixes batch size")
    search.add_argument("--max-attempts", type=int)
    search.add_argument("--count", type=int, default=1)
    search.add_argument("--namespace", help="UTF-8 prefix, max 16 bytes; random by default")
    search.add_argument("--start", type=int, default=0)
    args = vars(parser.parse_args(argv))
    as_json = args.pop("json")
    command = args.pop("command")
    def event(data):
        if as_json:
            print(json.dumps(data, ensure_ascii=True), flush=True)
        elif data["type"] == "hit":
            print(f'{data["address"]}  seed={data["seed"]!r}  verified', flush=True)
        elif data["type"] == "progress":
            print(f'{data["attempts"]:,} attempts  {data["keys_per_second"]:,.0f} keys/sec', file=sys.stderr, flush=True)
        elif data["type"] == "summary":
            print(f'{data["status"]}: {len(data["hits"])} hit(s), {data["attempts"]:,} attempts', file=sys.stderr)
    try:
        if command == "verify":
            expected = args.pop("address")
            address = derive(**args)
            if expected and address != expected:
                raise ValueError("address does not match base, seed and owner")
            print(json.dumps({"type": "verify", "address": address, "verified": True}) if as_json else address)
            return 0
        summary = grind(**args, on_event=event)
        return 0 if summary["status"] == "complete" else 130 if summary["status"] == "cancelled" else 1
    except (ValueError, RuntimeError, ImportError) as exc:
        if as_json:
            print(json.dumps({"type": "error", "message": str(exc)}), flush=True)
        else:
            print(str(exc), file=sys.stderr)
        return 2

if __name__ == "__main__":
    sys.exit(main())
