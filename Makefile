CONTROL_PLANE_ROOT ?= ../perfeng-control-plane
REGISTRY_VALIDATOR_REVISION := 703d9d11fda3f94e52b4cf4fad749d73cf52247f
UV_RUN := uv run --locked --offline

.PHONY: help bootstrap doctor fmt fmt-check docs-check check test definitions verify supply-chain validate runtime-registry

help:
	@echo perfeng-k8s engineering command surface
	@echo "  make bootstrap          Resolve the locked Python environment"
	@echo "  make doctor             Report the effective engineering toolchain"
	@echo "  make fmt               Format Python sources"
	@echo "  make fmt-check         Verify formatting without changing files"
	@echo "  make docs-check        Verify repository-local documentation and policy"
	@echo "  make check             Run formatting, linting and type checks"
	@echo "  make test              Run the unit-test suite"
	@echo "  make definitions       Validate charts, workloads and current bundle"
	@echo "  make verify            Run all repository-local checks"
	@echo "  make supply-chain      Verify the lock and audit dependencies"
	@echo "  make validate          Run complete repository acceptance"
	@echo "  make runtime-registry  Validate all bundles using the pinned adjacent control plane"

bootstrap:
	uv sync --locked

doctor:
	@git --version
	@uv --version
	@$(UV_RUN) python --version
	@helm version --short
	@kubectl version --client
	@$(MAKE) --version

fmt:
	$(UV_RUN) ruff format scripts tests

fmt-check:
	$(UV_RUN) ruff format --check .

docs-check:
	$(UV_RUN) python scripts/repository_policy.py

check: fmt-check docs-check
	$(UV_RUN) ruff check .
	$(UV_RUN) ty check

test:
	$(UV_RUN) python -m unittest discover -s tests -v

definitions:
	$(UV_RUN) python -m scripts.validate

verify: check test definitions

supply-chain:
	uv lock --check
	uv audit --locked

validate: verify supply-chain

runtime-registry:
	$(UV_RUN) python -c "import subprocess, sys; root=r'$(CONTROL_PLANE_ROOT)'; expected='$(REGISTRY_VALIDATOR_REVISION)'; actual=subprocess.check_output(['git', '-C', root, 'rev-parse', 'HEAD'], text=True).strip(); dirty=subprocess.check_output(['git', '-C', root, 'status', '--porcelain'], text=True).strip(); sys.exit(0 if actual == expected and not dirty else f'Expected clean control plane {expected}, found {actual}' + (' with local changes' if dirty else ''))"
	go -C "$(CONTROL_PLANE_ROOT)" run ./cmd/validate-registry -root "$(CURDIR)/testdata/runtime-registry" -manifest registry.json
	go -C "$(CONTROL_PLANE_ROOT)" run ./cmd/validate-registry -root "$(CURDIR)/bundles/local-kind-windows/1.0.0" -manifest registry.json
	go -C "$(CONTROL_PLANE_ROOT)" run ./cmd/validate-registry -root "$(CURDIR)/bundles/local-kind-windows/1.1.0" -manifest registry.json
	go -C "$(CONTROL_PLANE_ROOT)" run ./cmd/validate-registry -root "$(CURDIR)/bundles/local-kind-windows/1.1.1" -manifest registry.json
	go -C "$(CONTROL_PLANE_ROOT)" run ./cmd/validate-registry -root "$(CURDIR)/bundles/local-kind-windows/1.1.2" -manifest registry.json
	go -C "$(CONTROL_PLANE_ROOT)" run ./cmd/validate-registry -root "$(CURDIR)/bundles/local-kind-windows/1.1.3" -manifest registry.json
	go -C "$(CONTROL_PLANE_ROOT)" run ./cmd/validate-registry -root "$(CURDIR)/bundles/local-kind-integration/1.0.0" -manifest registry.json
	go -C "$(CONTROL_PLANE_ROOT)" run ./cmd/validate-registry -root "$(CURDIR)/bundles/local-kind-integration/1.0.1" -manifest registry.json
