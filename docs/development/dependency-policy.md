# Dependency policy

## TL;DR

- Resolve Python 3.12 dependencies exactly from `uv.lock`.
- Admit dependencies only for current validation or execution needs after maintenance, license, security, and replacement review.
- Treat Helm, Go, kubectl, and kube-burner as explicit boundary tools with pinned identities where they affect reproducibility.
- GitHub Actions may use reviewed release tags or commit pins; bundle hashes, image digests, tool checksums, and consumer revisions remain exact.
- Dependabot may propose grouped GitHub Actions updates; Python updates remain a manual, lockfile-aware workflow until the hosted updater supports the pinned uv toolchain reliably.

## Python and development tools

Runtime validator libraries belong in project dependencies and development-only tools in dependency groups. Updates preserve the lock and run `make verify`. Dependency changes stay separate from bundle promotions unless inseparable for compatibility.

## Boundary tools and immutable identities

The contained publisher uses the maintained Apache-2.0 boto3/botocore S3 SDK,
locked in `uv.lock`, for conditional writes and bounded read-back verification.
Its transitive additions are Apache-2.0 s3transfer and MIT jmespath/urllib3;
existing python-dateutil/six dependencies are reused. Review the graph with
`make supply-chain`. Keep SDK client construction separate from publication
logic; do not implement request signing in repository code. The runner never
receives storage credentials. The reviewed upstream kube-burner executable and
its Apache-2.0 license are packaged without modifying its implementation.

Helm is required for offline chart validation. Go is required only for the pinned control-plane runtime loader. kube-burner acquisition follows the checked-in toolchain document and its checksums. Live Kubernetes clients are never hidden prerequisites of the repository-local inner loop.

Workflow `uses:` entries may use reviewed release tags or commit SHAs; repository policy does not enforce one reference style. Exact image digests, content hashes, release archives, contract revisions, and the runtime-validator commit remain unchanged unless the issue explicitly reviews that selection.

## Supply-chain response

`make supply-chain` checks the lock and known vulnerabilities. Findings are reviewed for reachability and remediation. A temporary exception must identify scope, owner, expiry, and compensating evidence. An unavailable advisory service is reported as not run, never passed.

Dependabot updates GitHub Actions only. Python dependency updates remain manual and MUST update `uv.lock` with the repository-pinned toolchain. Automation availability is not treated as a repository check or as evidence that the locked graph is current.
