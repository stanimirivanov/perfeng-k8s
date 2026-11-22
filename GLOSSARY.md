# Kubernetes packaging language

Terms for packaged execution and reviewed runtime inputs. Shared terms are defined in the [Perfeng glossary](https://github.com/stanimirivanov/perfeng-contracts/blob/main/GLOSSARY.md).

## Language

**Runtime Registry Bundle**
Immutable reviewed deployment input binding exact policies, workload selections, compatible producer identities, execution templates and principals.

**Runtime Input Package**
Content-addressed non-secret runtime settings and exact Registry Bundle files prepared for mounting.

**Execution Job Template**
Reviewed reusable Kubernetes Job definition for a contained benchmark or an analysis phase.

**Deployable Bundle**
A reviewed, immutable package eligible for downstream environment selection.

**Synthetic Fixture**
Evidence prepared to test validation or rendering. Its identities apply only to the fixture.

**Benchmark Qualification**
Evidence that a target and execution context satisfy the prerequisites for an eligible contained measurement.
