# Shared frontend protocol

Run `python -m solvanity_contract grind ... --json`. Standard output is one complete JSON object per line. Errors use a JSON error object. Exact matching is the default; pass `--ignore-case` for ASCII case-insensitive mode. CPU is the default backend, and GPU failures do not silently fall back.

A start event has type=start, backend, base, owner, namespace, start and batch_size. A hit event has type=hit, base, owner, seed, counter, address and verified=true. Progress has type=progress, attempts, keys_per_second, elapsed_seconds, hits (integer), and next_counter. The summary has type=summary, status (complete, exhausted or cancelled), backend, attempts, keys_per_second, elapsed_seconds, hits (array of verified hit objects), namespace, next_counter, base and owner. Error events contain type=error and message.

Throughput includes complete batch execution, GPU synchronization, CPU verification and event callback overhead. It excludes engine initialization/JIT and startup hash self-tests. Every candidate in a completed batch is counted, even if the first requested match occurs early within the batch.

Python integration uses `solvanity_contract.search.grind`. It returns the summary and invokes `on_event(dict)` synchronously. All emitted data is JSON serializable. `should_stop()` is checked between batches. CLI exit status is 0 for complete or successful verify, 1 for exhausted search, 2 for invalid arguments/backend errors, and 130 for cancellation. argparse usage failures are written to stderr. Unexpected failures propagate rather than reporting a false success.

The `--namespace` value is UTF-8, at most 16 bytes, followed by exactly 16 lowercase hex counter bytes. A missing namespace is generated randomly. Resume with the same namespace/base/owner and last completed next_counter. Never wrap a uint64 counter. JSON logs and seeds contain public data only, but the base wallet private key must never be passed to this tool.

Install `.[test]` for CPU verification; `.[cuda,test]` for CUDA 12 wheels. CLI flags are --base, --owner, --prefix, --suffix, --ignore-case/--ignorecase, --backend, --batch-size, --max-attempts, --count, --namespace, --start and --json. Owner aliases are token and token2022. Custom owner values are base58 program pubkeys. Only public base keys are accepted.
