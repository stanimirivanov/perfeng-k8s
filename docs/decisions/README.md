# Architecture decision records

## TL;DR

- Use an ADR for durable decisions affecting promotion, resource ownership, authorization,
  compatibility, security or cross-component behavior.
- Number ADRs sequentially and never reuse a number.
- Allocate from fresh repository state and renumber concurrent collisions.
- Accepted ADRs are historical records; supersede rather than rewrite them.
- Record alternatives, consequences, rollout/recovery and validation.

## When an ADR is required

Create an ADR when a decision materially affects immutable promotion policy, chart/resource
ownership, runtime bundle semantics, authorization, secret/configuration ownership, public
compatibility, security, repository ownership, foundational technology, deployment topology or
cross-component behavior. Cheap local implementation choices do not need one.

## Naming and lifecycle

Use a four-digit sequence and short kebab-case name:

```text
0001-select-immutable-runtime-bundles.md
```

Statuses are Proposed, Accepted, Rejected, Deprecated or Superseded. Add every ADR to the index and
do not rewrite accepted decisions or consequences.

Immediately before creating an ADR, refresh the branch as the workflow allows and inspect this
index and directory. Allocate the lowest unused number. If concurrent work collides, rename the
later ADR to the next available number and update its title, index and references. Published numbers
remain immutable.

## Template

```markdown
# ADR-NNNN: Decision title

- Status: Proposed
- Date: YYYY-MM-DD
- Milestone: MNN — Outcome
- Deciders:
- Supersedes:
- Superseded by:

## Context

What forces a decision now? Include ownership, authorization and compatibility constraints.

## Decision

State the decision and scope precisely.

## Alternatives considered

### Alternative

- Benefits:
- Costs and risks:
- Reason not selected:

## Consequences

### Positive

### Negative

### Neutral or follow-up

## Compatibility and migration

## Security and operations

## Rollout, recovery and rollback

## Validation

How will assumptions and consequences be verified?
```

## Index

| ADR | Status | Decision |
|:--|:--|:--|
| [0001](0001-image-backed-native-search-chart.md) | Proposed | Package the published controlled fixture without absorbing environment selection, HTTPS access or Windows qualification. |
| [0002](0002-contained-kube-burner-packaging.md) | Proposed | Package upstream kube-burner with contained Pod writes and verified publication, separately from runtime promotion. |
| [0003](0003-package-non-secret-runtime-inputs.md) | Proposed | Package reviewed non-secret runtime inputs as a versioned Kustomize artifact while the workload chart keeps external references. |
