CONTROL_PLANE_ROOT ?= ../perfeng-control-plane
REGISTRY_VALIDATOR_REVISION := 403e2f2dd0c07854593020b6f8da4979d808b21d

.PHONY: help fmt fmt-check check test definitions validate runtime-registry

help:
	@echo perfeng-k8s engineering command surface
	@echo "  make fmt               Format Python sources"
	@echo "  make fmt-check         Verify formatting without changing files"
	@echo "  make check             Run formatting, linting and type checks"
	@echo "  make test              Run the unit-test suite"
	@echo "  make definitions       Validate charts, workloads and current bundle"
	@echo "  make validate          Run all repository-local checks"
	@echo "  make runtime-registry  Validate all bundles using the pinned adjacent control plane"

fmt:
	uv run --locked ruff format scripts tests

fmt-check:
	uv run --locked ruff format --check .

check: fmt-check
	uv run --locked ruff check .
	uv run --locked ty check

test:
	uv run --locked python -m unittest discover -s tests -v

definitions:
	uv run --locked python -m scripts.validate

validate: check test definitions

runtime-registry:
	uv run --locked python -c "import subprocess, sys; root=r'$(CONTROL_PLANE_ROOT)'; expected='$(REGISTRY_VALIDATOR_REVISION)'; actual=subprocess.check_output(['git', '-C', root, 'rev-parse', 'HEAD'], text=True).strip(); dirty=subprocess.check_output(['git', '-C', root, 'status', '--porcelain'], text=True).strip(); sys.exit(0 if actual == expected and not dirty else f'Expected clean control plane {expected}, found {actual}' + (' with local changes' if dirty else ''))"
	go -C "$(CONTROL_PLANE_ROOT)" run ./cmd/validate-registry -root "$(CURDIR)/testdata/runtime-registry" -manifest registry.json
	go -C "$(CONTROL_PLANE_ROOT)" run ./cmd/validate-registry -root "$(CURDIR)/bundles/local-kind-windows/1.0.0" -manifest registry.json
	go -C "$(CONTROL_PLANE_ROOT)" run ./cmd/validate-registry -root "$(CURDIR)/bundles/local-kind-windows/1.1.0" -manifest registry.json
	go -C "$(CONTROL_PLANE_ROOT)" run ./cmd/validate-registry -root "$(CURDIR)/bundles/local-kind-windows/1.1.1" -manifest registry.json
	go -C "$(CONTROL_PLANE_ROOT)" run ./cmd/validate-registry -root "$(CURDIR)/bundles/local-kind-windows/1.1.2" -manifest registry.json
	go -C "$(CONTROL_PLANE_ROOT)" run ./cmd/validate-registry -root "$(CURDIR)/bundles/local-kind-windows/1.1.3" -manifest registry.json
