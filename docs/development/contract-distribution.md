# Updating Kubernetes contract snapshots

## TL;DR

- Stage both snapshots from their independently pinned signed historical profiles.
- Review the resulting files before applying them to a checkout.
- Retain the previous checkout and the signed assets for offline recovery.

Stage the inputs described in the [shadow guide](harness.md#signed-contract-shadow).
Use a new destination under a private operator-controlled directory.

```sh
make contracts-update-check CONTRACTS_SHADOW_ASSETS="$assets" \
  CONTRACTS_BOOTSTRAP="$bootstrap" CONTRACTS_VERIFIER="$verifier" \
  CONTRACTS_STAGING_TARGET="$scratch/current"
```

The command authenticates the complete primary 0.13.0 and contained 0.22.0
profiles separately. It stages only their reviewed schemas and ledgers. Review
and apply those files to their existing paths under `contracts/` in a build
checkout. Keep unrelated files in that tree. Changes to either source revision
require a reviewed selection and compatibility verification. Missing, mixed,
or invalid inputs fail before the staging directory is created.

Keep a clean export of the pre-cutover checkout and its reviewed commit ID.
Use a new staging destination for recovery:

```sh
make contracts-restore-check CONTRACTS_SHADOW_ASSETS="$assets" \
  CONTRACTS_BOOTSTRAP="$bootstrap" CONTRACTS_VERIFIER="$verifier" \
  CONTRACTS_STAGING_TARGET="$scratch/recovered" CONTRACTS_ROLLBACK_CHECKOUT="$retained"
```

This recreates the current snapshots from retained signed assets and verifies
the retained rollback copies against the independent selections and ledger
digests. The rehearsal covers distribution rollback at the same revisions.
Run `make verify` and `make runtime-registry` before handoff. Deployment bundles
and runtime validation continue to use the existing local files.
