# solvanity-contract

An original CUDA SHA-256 vanity grinder for Solana **seed-derived account addresses**, with a CPU reference backend. Inspired by [cavemanloverboy/vanity](https://github.com/cavemanloverboy/vanity); this implementation does not copy its code.

This is **not a wallet generator**, a PDA finder, or a way to choose arbitrary executable program IDs. It searches:

```text
SHA256(base_public_key[32] || seed_utf8[0..32] || owner_program_id[32])
```

The base public key belongs to a signer you control. No private key, wallet file, RPC endpoint, or transaction signing is required to search. The owner defaults to the original SPL Token program; Token-2022 and custom program IDs are supported. The intended owner program must actually support the type of account and initialization you want.

## Install

Python 3.10 or later. CPU tests do not need CUDA.

```bash
git clone https://github.com/koboshchan/solvanity-contract
cd solvanity-contract
python -m pip install -e '.[test]'
python -m pytest -q
```

For Colab A100 or another CUDA 12-compatible setup:

```bash
python -m pip install -e '.[cuda,test]'
python -m pytest -q
```

Only install one CuPy distribution in a given environment. Match the CuPy wheel to your CUDA environment; see [CuPy installation](https://docs.cupy.dev/en/stable/install.html). The GPU backend compiles the bundled original CUDA kernel at runtime through CuPy RawKernel. It never silently falls back to CPU.

## Search

Replace the demonstration base with **your own public base signer address** before using a result.

```bash
python -m solvanity_contract grind \
  --base 11111111111111111111111111111111 \
  --owner token --prefix Cat --ignore-case \
  --backend cuda --batch-size 65536 --json
```

`--owner token2022` selects Token-2022. Pass a public program ID directly for a custom owner. Prefix and suffix are combined with AND. Exact matching is the default; `--ignore-case` (alias `--ignorecase`) folds ASCII letters only.

```bash
solvanity-contract grind --base YOUR_BASE_PUBLIC_KEY \
  --owner token2022 --suffix pump --ignore-case --backend cuda --count 1 --json

solvanity-contract grind --base YOUR_BASE_PUBLIC_KEY \
  --owner CUSTOM_OWNER_PUBLIC_KEY --prefix A --suffix z \
  --backend cpu --max-attempts 100000 --json
```

Invalid base58 characters and impossible combined patterns are rejected before GPU imports or allocation. Under ignore-case mode, O can match o, I can match i, and l can match L; zero cannot match anything. Validation respects canonical 32-byte base58 encoding, leading zero bytes, lengths, overlapping prefix/suffix constraints, and the 256-bit numerical bound. A 44-character address cannot start with z, but a 43-character address can, so a simple z prefix is valid.

Seeds are `namespace + counter_as_16_lowercase_hex_digits`. The namespace defaults to 16 random hex characters, is limited to 16 UTF-8 bytes, and is printed in the start and summary events. This leaves exactly 16 seed bytes for the uint64 counter. The generated seed is always at most 32 UTF-8 bytes. Search is deterministic for a supplied namespace and start counter.

```bash
solvanity-contract grind --base YOUR_BASE_PUBLIC_KEY --prefix A \
  --namespace my-run --start 0 --max-attempts 4096 --batch-size 128 --json
```

Resume with the same base, owner and namespace, using `next_counter` from the last completed progress/summary event. Counters never wrap. A uint64-exhausted run cannot be resumed. A cancellation is checked between batches; use a smaller batch for more responsive notebook cancellation. KeyboardInterrupt returns a cancelled summary. If interrupted during a batch, resuming from the last completed batch may repeat work but will not skip it.

## Verify a result

Every CPU or GPU hit is checked against both Python hashlib and the official solders `Pubkey.create_with_seed` before being reported. On GPU startup, device hashes are additionally checked against hashlib. The device returns all matching counters in a batch without a fixed-size hit cap; even extra matches beyond the requested count are CPU-verified. Only the requested number of hits are emitted.

```bash
solvanity-contract verify --base YOUR_BASE_PUBLIC_KEY \
  --owner token --seed YOUR_SEED --address RESULT_PUBLIC_KEY --json
```

The independent verifier accepts any valid UTF-8 seed up to 32 bytes, not just this grinder's counter format. Owners ending in the reserved `ProgramDerivedAddress` marker are rejected exactly as in Solana's implementation.

## Python and notebook integration

```python
from solvanity_contract.search import grind
from solvanity_contract import derive, Pattern

result = grind(
    base="11111111111111111111111111111111",  # demonstration only
    owner="token", prefix="A", suffix="", ignore_case=False,
    backend="cpu", batch_size=128, max_attempts=4096, count=1,
    namespace="demo", start=0,
    on_event=lambda event: print(event),
    should_stop=lambda: False,
)
for hit in result["hits"]:
    assert derive(hit["base"], hit["seed"], hit["owner"]) == hit["address"]
```

There is no notebook in this repository; a shared ipywidgets frontend can call this API or launch the JSON CLI. See [JSON protocol](docs/protocol.md).

## Account creation example and safety

[examples/create-account-with-seed.mjs](examples/create-account-with-seed.mjs) builds the official web3.js `SystemProgram.createAccountWithSeed` instruction, re-derives the address first, and prints a transaction summary. It does not request or handle keys and does not send a transaction.

Creating a token-owned account is **not** sufficient to initialize a token mint or token account. Choose the correct space, rent exemption and owner-specific initialization instructions. In particular, Token-2022 extensions can change the required account size. Review and combine creation and initialization appropriately before signing. Never treat this account address as a keypair with a recoverable private key. Changing the base, owner or seed changes the address. Keep your base wallet's private key secure; the seed itself is not a signing secret. Do not send funds to an uncreated/uninitialized result assuming it behaves like a normal wallet.

## Tests and performance

`pytest` checks the official Solana vector, UTF-8 byte limits, reserved owners, pattern feasibility, cancellation, counter boundaries, CPU search, and host-compiled versions of the **same CUDA device SHA-256/base58/matching code** against hashlib and solders. It includes edge cases for leading zeroes and uint64 boundaries.

GPU tests run automatically when a working CuPy GPU exists; otherwise they are explicitly skipped. They compare complete CPU/GPU match sets for empty, prefix, suffix and ignore-case AND patterns, Unicode namespaces, and uint64 boundaries. An actual GPU run is needed to certify CUDA compilation and device behavior; host tests alone do not establish GPU performance.

Progress reports actual attempted addresses per second (`keys_per_second` for shared frontend compatibility), including synchronization and hit verification, excluding backend startup/JIT. These are seeded addresses, not keypairs. High hit rates can be verification-bound. The kernel uses generic two-block SHA-256 plus full base58 conversion for correctness and clarity, not record-setting performance. No A100 benchmark is claimed until measured.

## Sources and attribution

[Solana Pubkey implementation and official test vector](https://github.com/solana-labs/solana/blob/master/sdk/program/src/pubkey.rs), [solders Pubkey reference](https://kevinheavey.github.io/solders/api_reference/pubkey.html), [web3.js createAccountWithSeed parameters](https://solana-foundation.github.io/solana-web3.js/v1.x/types/CreateAccountWithSeedParams.html), [Token-2022 documentation](https://www.solana-program.com/docs/token-2022), [CuPy RawKernel](https://docs.cupy.dev/en/stable/reference/generated/cupy.RawKernel.html), and [cavemanloverboy/vanity](https://github.com/cavemanloverboy/vanity) as prior art.

MIT licensed.
