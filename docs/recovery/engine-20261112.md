Engine recovery checkpoint, November 12 2026.

Recovered from this engine task's exact printed source, git diffs and finish-auto.py script after sandbox tmpfs loss. Base wallet source is published 3abf6ce, contract source is published c083f7c. Only nine engine and tuning-test files are supplied. No UI, package metadata, RNG replacement or GPU work is included.

Old local commits e96d351 (wallet) and 36abfdf (contract) are unavailable. Their original commit metadata and full-object identities cannot be reproduced; this is a new explicitly labelled recovery commit, not those commits. Compile passed before checkpoint. Full tests have not yet been rerun on recovered files. Earlier copies passed wallet34/contract39 CPU tests and tuning15 each, but that does not establish this recovery's test result.

Integrator should copy solvanity_wallet and solvanity_contract files over their corresponding published package bases, and import tests/wallet/test_tuning.py and tests/contract/test_tuning.py. recover.py records the exact recovery transformations against read-only published base histories. Do not replace the integrator's complete package tree with this intentionally partial artifact tree.

Raw A100 report JSONs and original transfer patches were lost. Recorded benchmark summaries are historical transcript evidence only, not recovered raw telemetry. Wallet profiling remains pending, no vetted device RNG selected.
