"""Dispatch wallet and contract modes to the existing engines."""
import argparse
import sys

def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(
        description="Solana vanity search for wallet keypairs and seeded accounts",
        epilog="Use solvanity MODE --help for engine commands and options.")
    parser.add_argument("mode", choices=["wallet", "contract"])
    if not argv or argv[0] in ("-h", "--help"):
        parser.parse_args(argv)
        return 0
    mode = parser.parse_args(argv[:1]).mode
    if mode == "wallet":
        from solvanity_wallet.__main__ import main as engine
    else:
        from solvanity_contract.__main__ import main as engine
    return engine(argv[1:])

if __name__ == "__main__":
    sys.exit(main())
