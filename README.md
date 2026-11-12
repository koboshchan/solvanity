<a id="readme-top"></a>
<!-- Adapted from othneildrew/Best-README-Template at fc444eb7b04b2e4863f6080b1507a219e95103fa. -->

<!-- PROJECT SHIELDS -->
[![Open In Colab][colab-shield]][colab-url]
[![MIT License][license-shield]][license-url]
[![CUDA][cuda-shield]][cuda-url]


<!-- PROJECT LOGO -->
<div align="center">
<h1>Solvanity Wallet</h1>
<p>CUDA Ed25519 vanity keypairs with independent CPU verification.</p>
<p><a href="https://colab.research.google.com/github/koboshchan/solvanity-wallet/blob/main/notebooks/Solvanity.ipynb">Open notebook</a> &middot; <a href="#getting-started">Local quickstart</a> &middot; <a href="#security">Security</a> &middot; <a href="https://github.com/koboshchan/solvanity-wallet/issues">Report an issue</a></p>
</div>


<!-- TABLE OF CONTENTS -->
<details>
  <summary>Table of Contents</summary>
  <ol>
    <li><a href="#about-the-project">About The Project</a></li>
    <li><a href="#getting-started">Getting Started</a></li>
    <li><a href="#usage">Usage</a></li>
    <li><a href="#tests">Tests</a></li>
    <li><a href="#benchmarks">Benchmarks</a></li>
    <li><a href="#security">Security</a></li>
    <li><a href="#contributing">Contributing</a></li>
    <li><a href="#license">License</a></li>
    <li><a href="#acknowledgments">Acknowledgments</a></li>
  </ol>
</details>


<!-- ABOUT THE PROJECT -->
## About The Project

Generate real Solana Ed25519 vanity keypairs on an NVIDIA GPU. This is **not** a create-with-seed address generator. Exported wallets can sign and can be imported into Phantom.

Own MIT search kernel with attributed Ed25519/SHA-512 device primitives. Every candidate gets a fresh independent 32-byte seed from host `os.urandom`. No cuRAND, timestamp seeds, counter expansion, or deterministic candidate stream. SHA-512, Ed25519 fixed-base multiplication, Base58 encoding, prefix/suffix checks run on the GPU. Every returned hit must pass independent PyNaCl and solders CPU checks before private-key export.

### Built With

Python, CuPy/NVRTC, PyNaCl, solders, and attributed CUDA Ed25519/SHA-512 primitives.

<p align="right">(<a href="#readme-top">back to top</a>)</p>


<!-- GETTING STARTED -->
## Getting Started

### Google Colab

Open the shared notebook using the badge above. In Colab, select a GPU under **Runtime > Change runtime type** and run the setup cell, then the interface cell. Runtime availability and billing are controlled by your Colab account; the notebook does not allocate or purchase a runtime.

Choose **Wallet keypair** or **Seeded account**, enter a prefix and/or suffix, and select **Exact caps** or **Any caps**. Choose **NVIDIA CUDA** or **CPU reference**, set a batch size and attempt limit, then start the search. Seeded mode also needs your base signer's **public** key and the intended owner program. Never paste an existing private key.

Wallet mode requires acknowledging the cloud-key warning. Results are hidden until an explicit reveal or export. Download JSON64 to retain a wallet, or derivation JSON to retain a seeded-account result. **Stop** takes effect between batches. When finished, use **Forget results**, clear all notebook outputs, and delete the runtime. Forgetting is not guaranteed secure erasure. The probability display is an estimate, not search completion or a promised deadline.

**Use cloud-generated wallets for testing only.** The runtime provider, browser extensions, saved outputs, and anyone with runtime access may be able to read private keys. Use a trusted local environment for wallets intended to hold real funds.

### Local installation

Python 3.10+ is required. For GPU search, use a compatible NVIDIA GPU and CUDA driver. With CUDA 12:

```sh
git clone https://github.com/koboshchan/solvanity-wallet
cd solvanity-wallet
pip install -e '.[cuda12,test]'
```

CUDA 13 environments may use `.[cuda13,test]` instead. CPU-only installation is `pip install -e '.[test]'`. Never install multiple CuPy distributions in one environment.

For a CPU-only quickstart, install the test extras and run the reference checks before generating keys.

```sh
python -m pip install -e '.[test]'
python -m pytest -q
python -m solvanity_wallet grind --prefix A --backend cpu \
  --batch-size 128 --max-attempts 4096 --count 1 --output-dir ./private-wallets
```

This command prints a private key if it finds a match. Run it only in a private terminal.

<p align="right">(<a href="#readme-top">back to top</a>)</p>


<!-- USAGE EXAMPLES -->
## Usage

### CLI

```sh
python -m solvanity_wallet grind --prefix ko --suffix sh --ignore-case \
  --backend cuda --batch-size 65536 --count 1 --output-dir ./private-wallets --json
```

Use `--backend cpu` for reference/testing. Use `--max-attempts 100000` to bound a run. Exact case is the default; `--ignore-case` uses ASCII case equivalence. Impossible Base58 characters are rejected (0 is always invalid; O/I/l are invalid in exact mode but can match o/i/L in ignore-case mode). Prefix and suffix must match the same address.

JSON Lines events have `type` set to `progress`, `hit`, or `done`. Progress includes attempts, elapsed_seconds, keys_per_second, and found. A hit includes address, keypair_json (64-byte seed || public key), phantom_secret (Base58 of those 64 bytes), and optional path. **Hit events contain PRIVATE KEYS. Do not share or publish terminal/notebook output.** Keypair files use exclusive creation and mode 0600. Existing files are never overwritten. Exit codes are 0 for success, 1 for attempt limit, 2 for validation/runtime errors, 130 for interruption.

### Python API

```python
from solvanity_wallet import grind

hits = grind(prefix="ko", suffix="sh", ignore_case=True,
             backend="cuda", batch_size=65536, count=1,
             max_attempts=1000000, output_dir="./private-wallets",
             on_event=lambda event: print(event["type"]))
print(hits[0]["address"] if hits else "No hit within limit")
```

The callback receives the same event dictionaries as the CLI. Avoid printing private hit fields in shared notebooks. CUDA loads lazily; importing the package and running CPU tests never initialize a GPU.

<p align="right">(<a href="#readme-top">back to top</a>)</p>

## Tests

```sh
pytest -q
SOLVANITY_TEST_CUDA=1 pytest tests/test_cuda.py -v
```

CPU tests include an RFC 8032 vector, Base58 leading zeros and solders cross-checks, fresh entropy per batch, mismatch rejection, pattern validation, bounded execution, secret formatting, and output permissions. Explicit GPU QA checks all derived public keys against PyNaCl, including RFC/random/edge seeds, plus exact and case-insensitive prefix, suffix, and combined matching, with CPU verification of every hit.

Host CSPRNG generation and transfers are included in the reported end-to-end rate. The A100 measurements and device validation below were performed on the actual target runtime.

## Benchmarks

Measured on a Colab NVIDIA A100-SXM4-80GB runtime with CuPy 14.2.0 and CUDA runtime 13.2. Each row is the median of five batches after one warmup batch. Startup and JIT compilation are excluded.

| Backend | Runtime | Batch size | Median throughput |
| --- | --- | --- | --- |
| CPU reference | CPU on the same Colab A100 runtime | 4,096 | 27,256 keypairs/s |
| CUDA | NVIDIA A100-SXM4-80GB | 65,536 | 7,062,114 keypairs/s |

The workload uses exact prefix `abcdef`, no suffix. The timed scan includes host OS-CSPRNG seed generation, SHA-512/Ed25519, base58/matching, transfers, synchronization, and device-buffer wiping. It is a batch-search measurement, not CLI startup or wallet-export latency. It does not measure the cost of a high-hit workload with per-hit verification/export.

The A100 device correctness suite passed all 21 tests, including all three CUDA tests. Actual notebook start/search/clear callbacks also returned verified GPU hits. Browser rendering, clipboard behavior, and download interaction still need interactive browser QA.

Wallet keypairs and seeded-account addresses perform different work. Compare these figures only with the same workload and timing scope.

## Security

Read [SECURITY.md](SECURITY.md) before using generated wallets. This is new unaudited software, not a hardware wallet. Prefer local trusted hardware for valuable keys. Colab operators, notebook owners, extensions, or anyone with runtime access can read private memory and outputs.

The CLI prints private keys in both text and JSON modes. JSON64 is a 64-byte integer array containing the seed followed by the public key, not base64. Treat Phantom secret strings and exported JSON files as full signing authority. Do not commit them, paste them into issues, or share notebook outputs.

<p align="right">(<a href="#readme-top">back to top</a>)</p>





<!-- CONTRIBUTING -->
## Contributing

Open an issue with a reproducible example or send a focused pull request. Run the CPU tests before submitting code changes. For CUDA changes, include the actual GPU model, CUDA/CuPy versions, and device test results; CPU-only checks do not validate the GPU backend. Never include generated private keys, access tokens, or notebook result state in a report.

<p align="right">(<a href="#readme-top">back to top</a>)</p>


<!-- LICENSE -->
## License

Project code is distributed under the MIT License. See [LICENSE](LICENSE). Vendored primitives retain Apache-2.0 and Orson Peters' zlib-style notices; see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

<p align="right">(<a href="#readme-top">back to top</a>)</p>





<!-- ACKNOWLEDGMENTS -->
## Acknowledgments

[ChorusOne/solanity](https://github.com/ChorusOne/solanity) inspired the CUDA Ed25519 approach, but its vanity search/RNG is not used. Primitive attribution and licenses are recorded in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

README adapted from the fetched [Best-README-Template](https://github.com/othneildrew/Best-README-Template/blob/fc444eb7b04b2e4863f6080b1507a219e95103fa/BLANK_README.md) (Unlicense), retaining its centered project header, badge references, collapsible contents, section structure, and back-to-top links.

<p align="right">(<a href="#readme-top">back to top</a>)</p>


<!-- MARKDOWN LINKS & IMAGES -->
[colab-shield]: https://colab.research.google.com/assets/colab-badge.svg
[colab-url]: https://colab.research.google.com/github/koboshchan/solvanity-wallet/blob/main/notebooks/Solvanity.ipynb
[license-shield]: https://img.shields.io/badge/License-MIT-blue.svg?style=for-the-badge
[license-url]: https://github.com/koboshchan/solvanity-wallet/blob/main/LICENSE
[cuda-shield]: https://img.shields.io/badge/CUDA-NVIDIA-76B900?style=for-the-badge&logo=nvidia&logoColor=white
[cuda-url]: https://developer.nvidia.com/cuda-zone
