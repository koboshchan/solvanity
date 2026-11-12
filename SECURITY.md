# Security

This implementation has not received an independent cryptographic/security audit. Do not assume the existence of tests makes a new key generator safe for high-value assets.

Every candidate receives an independent 32-byte OS CSPRNG seed. CUDA computes public keys and pattern matches only. All returned GPU hits, including surplus hits beyond the requested result count, are independently rederived with PyNaCl and solders before any are exported. Mismatches abort with no export for that hit. Patterns and Base58 encoding are rechecked on CPU; a local Ed25519 sign/verify check is performed.

The CUDA device buffers holding seeds and public keys are overwritten in a finally block after synchronization. This is best effort, not secure erasure. Python immutable bytes, CuPy transfers, driver memory, allocator caches, OS swap, crash dumps, runtime checkpoints, and notebook logs can retain copies. A GPU fault may prevent device clearing. No complete zeroization guarantee is made.

Private keys are deliberately returned through the API and emitted in CLI hit events. Never send them to an external service, put them in screenshots, commit them, or publish notebook outputs. The project has no telemetry, network requests, remote key generation, or embedded credentials. Package installation and first-time dependency downloads naturally use the network.

Keypair files are created exclusively with Unix permissions 0600 and fsynced. Parent directories are created 0700 when new; existing parent permissions are not changed. Protect the filesystem and runtime yourself. Windows permission semantics may differ.

Treat cloud notebooks and shared GPUs as untrusted for high-value wallets. Test an import/signing operation, back up secrets offline, and start with negligible funds. Exported JSON64 is seed followed by public key, not an expanded SHA-512 private scalar.
