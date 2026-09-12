# Contributing

## Change boundaries

Keep deployment changes reviewable and reversible. A pull request should promote
one coherent set of immutable component and configuration identities. Do not mix
runtime promotion with unrelated repository tooling or local-development changes.

Reusable charts must not invent an environment selection. Require callers to
supply immutable component digests and named external configuration. Do not
create credentials, authentication documents or runtime Secrets in this
repository. Grant the control plane only the namespaced Kubernetes operations
used by its reviewed client interfaces.

A deployable bundle must contain real, independently verifiable identities:

- use the final registry manifest digest printed by each publisher workflow;
- hash the exact catalogue, workload, environment, dataset, and policy bytes;
- use a candidate image that exists in its registry and is approved for the
  target environment;
- keep Job images consistent with the producer bound in `registry.json`;
- review principals as authorization data, not descriptive metadata.

Files under `testdata` are validation fixtures only. Synthetic hashes and example
registry names are permitted there because they cannot be selected as deployment
configuration. Never copy a fixture into `bundles` and call it deployable.

## Local validation

Use Python 3.12 and the locked uv environment for repository-owned benchmark
definitions. Install Helm for chart linting and rendering:

```sh
uv sync --locked
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked ty check
uv run --locked python -m unittest discover -s tests -v
uv run --locked python -m scripts.validate
```

Validation is intentionally offline. It checks the owned kube-burner subset,
bounded workload size, immutable images, local output, referenced templates,
pod security, the pinned upstream release metadata, and the checksums of the
minimal contracts 0.13 snapshot. It does not prove that
a target cluster is healthy or representative.

Raw-manifest tests use synthetic storage receipts and do not upload or retrieve
objects. Contract snapshot updates must pin one reviewed perfeng-contracts
commit and preserve imported schema bytes exactly.

The validator revision used by CI is pinned in
`.github/workflows/validate.yml`. Check out that revision in the adjacent
`perfeng-control-plane` repository before reproducing CI locally.

Because component repositories are private, the `perfeng-k8s` repository must
define the Actions secret `PERFENG_REPOSITORIES_READ_TOKEN`. Use a fine-grained,
expiring token restricted to read-only Contents access for the selected
`perfeng-control-plane` repository. The workflow uses it only for the pinned
validator checkout and does not persist its credentials.

From this repository in PowerShell:

```powershell
$fixtureRoot = (Resolve-Path testdata/runtime-registry).Path
$bundleRoot = (Resolve-Path bundles/local-kind-windows/1.1.1).Path
git -C ../perfeng-control-plane checkout 403e2f2dd0c07854593020b6f8da4979d808b21d
go -C ../perfeng-control-plane run ./cmd/validate-registry -root $fixtureRoot -manifest registry.json
go -C ../perfeng-control-plane run ./cmd/validate-registry -root $bundleRoot -manifest registry.json
```

Return the adjacent repository to its previous branch after validation. The
command must print `Registry bundle is valid.` and exit successfully.

When the bundle format intentionally changes, update the pinned validator and
the fixtures in the same pull request. Review the control-plane change first;
never float validation against a branch or tag.
