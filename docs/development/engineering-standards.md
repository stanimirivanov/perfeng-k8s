# Kubernetes deployment engineering standards

## TL;DR

- Promote exact component and configuration identities through new immutable bundle versions.
- Keep reusable charts environment-agnostic and require externally managed configuration and
  credentials.
- Treat principals, RBAC, ServiceAccounts and credential-bearing containers as authorization
  boundaries.
- Separate credential-free compute from narrowly privileged transfer and publication.
- Validate charts structurally and by rendered behavior, then validate bundles with the exact
  control-plane runtime loader.
- Keep synthetic fixtures visibly non-deployable and live-cluster mutation explicitly authorized.

## Policy strength

Normative terms use the meanings in
[CONTRIBUTING.md](../../CONTRIBUTING.md#policy-language-and-sources-of-truth). MUST and MUST NOT are
requirements; SHOULD and SHOULD NOT are strong defaults requiring a recorded reason to deviate; MAY
is optional.

## Architecture and ownership

Organize around reusable charts, immutable runtime-registry bundles, platform workload definitions,
contract snapshots, offline validators and explicit operational commands.

- Charts describe reusable Kubernetes workloads and minimum permissions. They do not select an
  environment, image release, credential value or promoted registry bundle.
- Versioned bundles compose exact component/configuration identities for one environment and are
  append-only after publication.
- Workload definitions bind exact inputs and budgets; execution adapters preserve their identities.
- Repository validators prove local structure, hashes, chart rendering and security invariants.
- The pinned control-plane loader proves the runtime can consume the bundle.
- `perfeng-environment` owns local kind/Argo CD composition and external configuration materialization.
- Component repositories own executable code and image publication; `perfeng-contracts` owns shared
  schemas.

Use SOLID and patterns as reasoning tools, not quotas. Prefer declarative ownership, small validators
and explicit immutable references over generic templating layers, hidden environment discovery or
configuration mutation.

## Immutable promotion and provenance

- A deployable bundle version is an immutable review unit. Never change previously promoted bytes;
  create a new version that states the correction and retained identities.
- Use the final registry manifest digest emitted by a successful component publisher. A base-image
  digest, local image ID, mutable tag or digest-shaped placeholder is not a component identity.
- Bind exact checksums of referenced catalogue, workload, environment, dataset, policy and template
  bytes. Hash the actual selected bytes, not a reconstructed equivalent.
- Record component source revision, artifact platform and version where the identity document
  requires them.
- Candidate, runner, raw producer, normalizer and reporter identities must be internally consistent
  with Job commands and declared artifact formats.
- Environment fingerprints identify exact reviewed environment/configuration bytes; a live preflight
  still proves the target matches them.
- Principals are explicit authorization selectors. Wildcards and descriptive placeholders are not
  valid production authorization.
- Promotion through GitOps changes the pinned reviewed revision. Direct edits to reconciled live
  resources are diagnosis or emergency action, not durable configuration.

## Chart and Kubernetes design

- Charts MUST require immutable component images and named externally managed runtime inputs.
- Reusable charts MUST NOT create Secrets, authentication documents, image-pull credentials or
  environment-owned ConfigMaps.
- Define ownership for every resource name, namespace, label, annotation, volume and external
  reference. Avoid adopting pre-existing resources implicitly.
- Set namespace explicitly and keep cross-namespace access narrow and reviewable.
- Use dedicated ServiceAccounts. Disable or enable token automount deliberately according to the
  workload's reviewed Kubernetes API needs.
- Containers run as numeric non-root identities, disallow privilege escalation, use runtime-default
  seccomp, drop all capabilities and use read-only root filesystems unless a documented requirement
  proves otherwise.
- Declare CPU, memory and ephemeral-storage requests/limits. Bound active deadlines, retries,
  backoff, history, temporary volumes and output sizes where the workload permits.
- Probes reflect distinct startup, liveness and readiness semantics and use the service boundary
  actually exposed by the component.
- Prefer immutable fields and deterministic names/labels that allow the control plane and GitOps
  tooling to detect ownership and drift.

## Job privilege separation and artifacts

- Keep runner, normalizer and reporter containers free of object-storage credentials.
- Use narrowly privileged init/publisher containers to retrieve or publish exact objects and expose
  verified bytes through bounded shared volumes.
- Verify downloaded bytes against expected size and SHA-256 before untrusted processing.
- Publish stable artifact keys conditionally so retries cannot overwrite evidence. Read back and
  verify bytes, media type and required discovery metadata before declaring completion.
- The final manifest or analysis object is a completion marker only after every prerequisite object
  is verified.
- Do not put secret values in environment-owned non-secret configuration, command arguments,
  manifests, logs, labels or annotations.
- Job templates remain Run-independent. The control plane assigns Run identity, deterministic
  names, ownership labels and specification fingerprints at resolution time.

## Workloads and native execution

- Workloads declare exact tool, model, phase budgets, dataset identity, configuration hashes and
  candidate constraints.
- Preserve raw measurement files. Assembly and normalization must not rewrite producer evidence.
- Missing or incomplete output is never successful evidence and must not be replaced with synthetic
  artifacts.
- Native benchmark commands default to non-mutating preview, require explicit kubeconfig/context,
  and require a matching confirmation before execution.
- Native execution is limited to explicitly authorized disposable environments unless a separate
  reviewed operating procedure covers shared infrastructure.
- Tool downloads use pinned upstream release URLs plus archive and executable hashes.
- Namespace/resource cleanup is verified after execution; failure leaves evidence for diagnosis and
  requires an explicit cleanup decision.
- Small integration workloads do not establish stable performance thresholds or production
  capacity claims.

## Contracts, fixtures and input safety

- Resolve vendored schemas locally and verify the snapshot lock before use. Runtime validation MUST
  NOT fetch schemas.
- Contract updates pin one reviewed source revision, preserve upstream bytes/license and update all
  affected fixtures and consumers coherently.
- Treat YAML, JSON, paths, receipts, URLs and rendered objects as untrusted input. Reject duplicate
  fields, non-finite values, path escape including symlinks, unstable artifact locations and
  checksum/size mismatches.
- Bound collection sizes, resource quantities, input files, diagnostics and subprocess timeouts.
- Files under `testdata` are synthetic and non-deployable. Names, hashes and values there must make
  that boundary obvious and validators must reject their use as promotion input.
- Paths may contain links or traversal while identifying the same file. Resolve and
  compare paths safely without assuming temporary-path textual equality.

## Python and validator design

- Use Python from `.python-version`, exact dependencies from `uv.lock`, Ruff formatting and the
  configured type checker.
- Keep parsing, validation, Helm invocation and CLI reporting separated enough to test without a
  live cluster.
- Use precise exceptions with stable non-sensitive messages; preserve causes for operational
  failures.
- Subprocesses use argument arrays, explicit working directories, captured diagnostics where safe,
  bounded timeouts and checked expected outcomes.
- Validators fail closed on unknown fields, missing resources, extra permissions, mutable images,
  identity drift and unsupported versions.
- Do not add lint-suppression comments merely to silence findings.
- Comments and docstrings explain ownership, security and compatibility contracts rather than
  restating syntax.

## Testing and validation

- Run formatting, linting, type checking and unit tests on repository-owned Python.
- Run full repository validation on Linux because archive, path and temporary-directory
  behavior is part of the supported surface.
- Helm checks include strict linting, values-schema rejection and assertions over rendered resource
  kinds, namespaces, identities, security contexts, probes, mounts, resources and RBAC.
- Bundle tests cover exact identities and important rejection paths; they do not merely snapshot
  rendered YAML.
- Every deployable bundle is validated with the exact pinned control-plane loader in CI. Local
  reproduction uses the same clean adjacent revision.
- Live-cluster checks are separate, explicitly authorized acceptance evidence and never implied by
  offline validation.
- Defect fixes SHOULD begin with a failing regression test.

## Documentation and dependencies

- Document environment scope, immutable identities, ownership, authorization, rollout, recovery,
  limitations and required validation.
- Long documents follow the TL;DR policy in CONTRIBUTING. Published bundle documentation remains
  historical with its immutable version.
- Dependencies and external tools require a current need, compatible license, maintained release,
  exact lock/digest/checksum, security review and a proportionate replacement boundary.
- Pin GitHub Actions and cross-repository validators according to repository policy; never float a
  promotion check against a branch.

## Required verification

Run `make validate` with Helm available. For bundle changes, also place the exact clean pinned
control-plane revision at `CONTROL_PLANE_ROOT` and run `make runtime-registry`. Live execution or
GitOps reconciliation is required only when the issue explicitly includes an authorized environment
acceptance check.
