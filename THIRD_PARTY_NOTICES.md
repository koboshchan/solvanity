# Third-party notices

The project-authored Python and CUDA search kernel are MIT licensed.

Files under solvanity_wallet/cuda/vendor are taken from ChorusOne/solanity,
https://github.com/ChorusOne/solanity, pinned commit
5bf33fe018d68b4eb244c18bb6914af5becd3ead, src/cuda-ecc-ed25519.

The repository-level license is Apache License 2.0, copyright 2018 Solana Labs, Inc.
Its full notice is preserved in vendor/LICENSE-APACHE.

The Ed25519 source additionally carries the permissive zlib-style license,
copyright 2015 Orson Peters <orsonpeters@gmail.com>, reproduced unmodified in
vendor/license.txt. Original project https://github.com/orlp/ed25519.
The SHA-512 file preserves the LibTomCrypt / Tom St Denis attribution in its header.

Vendored fixedint.h and sha512.h are plainly marked adaptations that provide
NVRTC-compatible integer and size types without host standard-library headers.
Other vendored source is unchanged. At compile time __host__ qualifiers are removed
by a macro for NVRTC device-only compilation. The project does not include or
use the upstream vanity scanner, CUDA RNG, seed generation, signing or verification
entrypoints. Keypair derivation/search integration in cuda/grind.cu is original.

PyNaCl, solders, NumPy and optional CuPy remain separately installed dependencies
under their respective upstream licenses.
