# Security

This implementation has not received an independent cryptographic/security audit. Do not assume the existence of tests makes a new key generator safe for high-value assets.

CPU mode gives every candidate a fresh 32-byte OS CSPRNG seed. CUDA mode optionally uses the system's maintained libsodium RFC8439 IETF ChaCha20 implementation, never a custom GPU cipher. Each batch receives a fresh 256-bit key and 96-bit nonce from `os.urandom`. The 32-bit block counter starts at zero only under that fresh key/nonce domain; candidate index i maps to bytes [32i, 32i+32). Batches are capped at 1,048,576 candidates (32 MiB), far below the 256 GiB per-stream limit. Range checks reject counter exhaustion. Keys/nonces are not derived from a timestamp, device ID, Philox, or cuRAND. Random key/nonce domains make accidental reuse negligibly likely, not mathematically impossible.

A missing optional system libsodium library falls back to direct OS seeds. Native initialization or self-test failure aborts rather than silently selecting a different cipher. The binding has an RFC8439 known-answer self-test; tests independently compare random and boundary streams with PyCryptodome, including the final legal counter block. These tests are not a security audit.

One bounded lookahead batch can be generated on a single host worker while CUDA processes the current batch. Native key, nonce, and candidate buffers are wiped on normal completion and failure, including unused lookahead work. Each native hit is rederived on CPU from the batch key, nonce, and exact candidate index, checked against the generated seed, then passed through the existing independent Ed25519 verification. Immutable Python copies and the OS fallback cannot be reliably wiped. CUDA computes public keys and pattern matches only. All returned GPU hits, including surplus hits beyond the requested result count, are independently rederived with PyNaCl and solders before any are exported. Mismatches abort with no export for that hit. Patterns and Base58 encoding are rechecked on CPU; a local Ed25519 sign/verify check is performed.

The CUDA device buffers holding seeds and public keys are overwritten in a finally block after synchronization. This is best effort, not secure erasure. Python immutable bytes, CuPy transfers, driver memory, allocator caches, OS swap, crash dumps, runtime checkpoints, and notebook logs can retain copies. A GPU fault may prevent device clearing. No complete zeroization guarantee is made.

Private keys are deliberately returned through the API and emitted in CLI hit events. Never send them to an external service, put them in screenshots, commit them, or publish notebook outputs. The project has no telemetry, network requests, remote key generation, or embedded credentials. Package installation and first-time dependency downloads naturally use the network.

Keypair files are created exclusively with Unix permissions 0600 and fsynced. Parent directories are created 0700 when new; existing parent permissions are not changed. Protect the filesystem and runtime yourself. Windows permission semantics may differ.

Treat cloud notebooks and shared GPUs as untrusted for high-value wallets. Test an import/signing operation, back up secrets offline, and start with negligible funds. Exported JSON64 is seed followed by public key, not an expanded SHA-512 private scalar.
