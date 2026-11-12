import argparse
import json
import sys
from .core import grind

def main(argv=None):
    parser = argparse.ArgumentParser(description="OS-CSPRNG-fed Ed25519 vanity keypair search")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("grind")
    p.add_argument("--prefix", default="")
    p.add_argument("--suffix", default="")
    p.add_argument("--ignore-case", action="store_true")
    p.add_argument("--backend", choices=["cpu","cuda"], default="cuda")
    p.add_argument("--batch-size", type=int, default=65536)
    p.add_argument("--count", type=int, default=1)
    p.add_argument("--max-attempts", type=int)
    p.add_argument("--output-dir")
    p.add_argument("--json", action="store_true", help="JSON Lines events (includes private keys for hits)")
    args = vars(parser.parse_args(argv))
    args.pop("command")
    json_mode = args.pop("json")
    def event(e):
        if json_mode:
            print(json.dumps(e), flush=True)
        elif e["type"] == "hit":
            print("Address " + e["address"], flush=True)
            print("Solana JSON64 " + json.dumps(e["keypair_json"]), flush=True)
            print("Phantom secret " + e["phantom_secret"], flush=True)
            if "path" in e:
                print("Keypair file " + e["path"], flush=True)
        else:
            print(json.dumps(e), file=sys.stderr, flush=True)
    try:
        hits = grind(**args, on_event=event)
    except KeyboardInterrupt:
        return 130
    except (ValueError, RuntimeError) as e:
        print(str(e), file=sys.stderr)
        return 2
    return 0 if len(hits) >= args["count"] else 1

if __name__ == "__main__":
    sys.exit(main())
