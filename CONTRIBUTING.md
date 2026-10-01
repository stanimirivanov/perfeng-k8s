# Contributing to perfeng-k8s

## TL;DR

- Deliver one coherent, verified deployment or promotion outcome per issue and pull request.
- Use MUST, SHOULD and MAY as defined below; lowercase wording is explanatory.
- Proceed on documented, reversible assumptions and stop for choices that materially affect
  immutable identity, authorization, compatibility, security or external state.
- Prepare requested changes without staging or committing, then print issue content for the
  repository owner.
- Run repository checks and the pinned runtime loader where applicable; report unavailable checks
  as not run—never as passed.
- Use exact published milestone titles in the form `MNN — Outcome`.

## Policy language and sources of truth

- **MUST** and **MUST NOT** identify requirements. A deviation needs an explicit reviewer-approved
  exception recorded in the issue or pull request.
- **SHOULD** and **SHOULD NOT** identify strong defaults. A deviation is allowed only when its
  reason and trade-off are recorded.
- **MAY** identifies an optional choice.

Lowercase guidance does not silently create another normative level.

| Concern | Canonical source |
|:--|:--|
| Contributor workflow, issue timing, escalation and completion | This document |
| Concise contributor and agent entry point | [AGENTS.md](AGENTS.md) |
| Task-oriented documentation routing | [docs/README.md](docs/README.md) |
| Coding harness and verification tiers | [docs/development/harness.md](docs/development/harness.md) |
| Kubernetes, bundle and promotion engineering | [docs/development/engineering-standards.md](docs/development/engineering-standards.md) |
| Dependency admission and supply chain | [docs/development/dependency-policy.md](docs/development/dependency-policy.md) |
| Architecture decisions | [docs/decisions](docs/decisions/README.md) |
| Cross-repository milestones | [perfeng-environment roadmap](https://github.com/stanimirivanov/perfeng-environment/blob/main/docs/roadmap/milestones.md) |
| Repository boundaries and current releases | [README.md](README.md) |
| Pod-startup execution | [docs/pod-startup.md](docs/pod-startup.md) |
| Raw-manifest assembly | [docs/raw-manifests.md](docs/raw-manifests.md) |

When sources conflict, the narrower source governs its concern. An accepted ADR governs its
decision until superseded. The control plane's pinned offline loader governs whether a runtime
bundle is consumable. Surface unresolved conflict rather than quietly choosing the convenient rule.

## Before starting

A contributor MUST inspect the branch and working tree and preserve unrelated changes; read
affected charts, schemas, bundles, policies, identities, workloads, validators, fixtures and
documentation; identify the smallest independently reviewable outcome; identify affected immutable
identities, principals, permissions, environments, compatibility and operations; and select the
workflow under [Issue timing](#issue-timing).

A contributor MUST NOT discard, overwrite, reformat or incorporate unrelated work to obtain a
clean diff. Destructive operations and external writes outside the task require explicit
authorization.

An ADR MUST be proposed when a change establishes or revises durable promotion policy, immutable
identity, chart ownership, security, repository ownership, foundational technology, deployment
topology or cross-component behavior.

## Ambiguity and escalation

Before escalating, inspect relevant manifests, chart rendering, values schemas, bundle hashes,
runtime-loader behavior, tests, documentation, ADRs and issue history and perform safe read-only
investigation.

A contributor MAY proceed with a documented assumption only when it is local, reversible and
inexpensive; stays in scope; does not alter a promoted identity, authorization, environment
selection, runtime compatibility, security or external state; does not weaken acceptance; and would
not materially change what reviewers believe they approve. Record the assumption and consequence.

A contributor MUST stop for a decision when missing information could materially change outcome,
milestone, environment or principal selection, image/content identity, permissions, secret
ownership, compatibility, security, an irreversible action, promotion/publication or a choice
between materially different deployment designs. State evidence, options, consequences and work
that can safely continue.

## Issue timing

- When an issue number is supplied, follow its scope and milestone. A material mismatch follows the
  escalation rules.
- Without an issue number, prepare the smallest coherent requested change and print a complete
  proposed issue in the completion report. The owner creates the issue and then creates or renames
  the branch with its number.
- Contributors acting for the owner MUST NOT stage, commit, push, create or modify issues, create
  pull requests, mutate a cluster, promote a bundle, publish artifacts, create releases, or change
  milestones unless explicitly requested.
- Read-only investigation, offline validation and rendering with synthetic values MAY occur before
  an issue exists.

Creating or modifying GitHub records, releases, packages, live clusters or promoted environment
state is an externally visible write and requires explicit authority.

## Milestones and required issue

Use exact published titles in the form `MNN — Short outcome`. Published milestones MUST NOT be
reused, renumbered or casually renamed. GitHub owns live assignment; the centralized
[roadmap](https://github.com/stanimirivanov/perfeng-environment/blob/main/docs/roadmap/milestones.md)
owns intended outcomes and sequencing.

Every implementation issue uses:

```markdown
**Repository:** perfeng-k8s
**Milestone:** MNN — Outcome

## Goal

Describe the problem and observable result.

## Scope

- Included behavior and boundaries.

## Design decisions

- Choices, assumptions, immutable identities, compatibility effects, and ADRs.

## Security and operations

- Principals, RBAC, credentials, external effects, rollout and recovery.

## Acceptance criteria

- [ ] Observable deployment or promotion behavior and verification evidence.
- [ ] Relevant rejection, rendering, runtime-loader and failure behavior.
- [ ] Documentation, compatibility and operational effects.

## Verification

- Required repository, Helm, runtime-loader and live checks.

## Out of scope

- Explicit exclusions and deferred work.
```

Acceptance criteria MUST describe observable behavior or verifiable invariants, not implementation
activities. Known limitations MUST be visible.

## Pull-request-sized work

A pull request MUST solve one coherent deployment or promotion problem, leave all current bundles
valid, include charts, schemas, identities, policy, validation, fixtures and documentation required
for the outcome, and prove important rejection and failure behavior.

Split independent promotions, chart behavior, validator upgrades, dependencies and broad cleanup.
A vertical promotion may introduce a new bundle version containing all exact identities and tests
needed for one deployable outcome. Do not mutate prior bundle versions or create placeholders for
roadmap appearance.

## Immutable bundles and fixtures

- Every published bundle version is an immutable review unit. Corrections create a new version and
  preserve older bytes and meaning.
- Use the final registry manifest digest from the component publisher and exact checksums of every
  referenced catalogue, workload, environment, dataset and policy document.
- Candidate images must exist and be approved for the target environment. Runner and producer
  identities must agree with reusable Job templates.
- Principals are authorization data, not descriptive labels.
- `testdata` contains deliberately synthetic validation input and is never deployable. Synthetic
  hashes, registry names and values remain confined there.
- Contract snapshots pin one reviewed `perfeng-contracts` revision and preserve imported bytes and
  license exactly.

## Development workflow

1. Select the workflow defined in [Issue timing](#issue-timing).
2. Prepare one focused change without staging, committing or pushing for the owner.
3. Add or update non-deployable fixtures and rejection tests.
4. Implement the smallest coherent chart or new immutable-bundle outcome and update documentation.
5. Format and run exact repository checks.
6. Validate affected bundles with the exact pinned control-plane runtime loader.
7. Review the diff for secrets, synthetic/promoted confusion, identity drift, permissions,
   assumptions, lock/package drift and unrelated edits.
8. Print the canonical [completion report](#completion-report).
9. The owner creates or confirms the issue and branch, may adjust the change, commits with `[#N]`,
   pushes and opens the pull request.

Do not store task-specific issue bodies, PR descriptions or handoff notes in the repository.

## External operations and destructive actions

Read-only inspection is allowed when relevant. Filesystem, Kubernetes, registry, GitHub and other
mutations MUST remain within requested scope and authority.

- Validation is offline and renders with non-deployable synthetic values.
- Charts do not create credentials, authentication documents, runtime Secrets or environment-owned
  ConfigMaps.
- Direct benchmark execution defaults to preview and requires an explicit kubeconfig, context and
  matching confirmation. It is limited to authorized disposable targets.
- Credentials, authentication documents and sensitive evidence MUST NOT appear in arguments, logs,
  fixtures, bundles or Git.
- Promotion, Argo CD reconciliation, cluster mutation and artifact publication require explicit
  authorization and an immutable reviewed revision.
- Deletion, history changes, namespace cleanup and artifact replacement require explicit authority
  and verified exact targets.

## Verification and constrained environments

Run `make verify` for all repository-local checks and `make validate` for complete acceptance.
Helm is required for strict chart linting and rendering. The exact commands and prerequisites are
inventoried in the [harness guide](docs/development/harness.md).

Changes affecting runtime bundles MUST additionally use the exact control-plane validator revision
declared in the Makefile and CI workflow. Check out that revision in a clean adjacent
`perfeng-control-plane` repository and run `make runtime-registry`. This check is deliberately
separate because it proves runtime consumption rather than repository-local structure.

When a check cannot run because of sandbox, platform, network, credentials, Helm, Go, sibling
checkout, cluster access or another environmental constraint, report the exact command as **not
run**, the blocker and attempts, checks that passed, residual risk, and where it should run. Never
weaken a check or claim an unexecuted check passed. Report a failure even when it appears unrelated.

## Documentation

Every long narrative document MUST contain `## TL;DR` immediately after its title and status
metadata. A document is long when it has at least 800 words, more than five second-level sections,
or is an architecture, security, compatibility, migration or operational guide readers consult
selectively. Issue and PR templates are excluded.

The TL;DR SHOULD state purpose, intended reader, important outcome and next action in three to seven
bullets. Bundle identity, chart ownership, security boundaries, compatibility, promotion,
validation and recovery guidance change with the configuration that makes them inaccurate. Accepted
ADRs and published bundle documentation are historical; supersede rather than rewrite them.

## Pull request description

A pull request MUST state the linked issue and milestone; outcome and exclusions; assumptions and
unresolved questions; identity, authorization, chart and compatibility effects; verification
including checks not run; security, promotion, rollout and rollback; and known limitations.

## Review checklist

- [ ] MUST: The issue uses the required structure and exact milestone title.
- [ ] MUST: The change is one coherent deployment or promotion outcome.
- [ ] MUST: Published bundle versions remain unchanged and new identities are exact and immutable.
- [ ] MUST: Charts preserve caller-owned environment selection and external secret/configuration
      ownership.
- [ ] MUST: Principals, RBAC and credential-bearing containers remain least privilege.
- [ ] MUST: Deployable input and synthetic fixtures cannot be confused.
- [ ] MUST: Success and relevant rejection/rendering/runtime-loader paths are tested.
- [ ] MUST: Contracts, hashes, provenance, charts, fixtures and documentation agree.
- [ ] MUST: Applicable local, runtime-loader and live checks passed or are reported.
- [ ] MUST: No secrets, local results, machine paths or unrelated churn are present.
- [ ] MUST: An ADR exists when the decision meets the ADR threshold.

## Completion report

After every work item, print the repository, exact milestone, proposed issue title, complete issue
body, assumptions and limitations, verification outcomes distinguished as passed/failed/not run,
and a suggested `[#N]` commit subject. When an issue exists, repeat or amend it so delivered scope
is auditable. Printing the report does not publish external records.
