FROM ghcr.io/astral-sh/uv:0.12.5@sha256:db2d5999728c5837e1bf9ba278ee6b05cef1e95e82a20e27b0c915cb4478b9d7 AS uv
FROM python:3.12-slim-bookworm@sha256:34386ef0cb081344d7ec1c103ba398e6e9f64e9ab3a1509accc92a4e24a07258 AS builder
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_PROJECT_ENVIRONMENT=/opt/venv UV_LINK_MODE=copy
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-cache
COPY scripts/ scripts/
COPY contracts/ contracts/
COPY toolchain/ toolchain/
RUN /opt/venv/bin/python -c "from scripts.benchmark import acquire_tool, host_asset; acquire_tool(host_asset())"

FROM python:3.12-slim-bookworm@sha256:34386ef0cb081344d7ec1c103ba398e6e9f64e9ab3a1509accc92a4e24a07258
ARG VCS_REF
LABEL org.opencontainers.image.source="https://github.com/stanimirivanov/perfeng-k8s" \
      org.opencontainers.image.revision="$VCS_REF" \
      org.opencontainers.image.title="perfeng-kube-burner" \
      org.opencontainers.image.version="1.0.0"
ENV PATH="/opt/venv/bin:$PATH" PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /app/.local/tools/kube-burner/2.8.5/kube-burner /usr/local/bin/kube-burner
COPY scripts/ scripts/
COPY contracts/ contracts/
COPY execution/ execution/
COPY toolchain/ toolchain/
COPY LICENSE /licenses/perfeng-k8s-LICENSE
COPY execution/kube-burner-LICENSE /licenses/kube-burner-LICENSE
USER 65532:65532
ENTRYPOINT ["python", "-m", "scripts.contained"]
CMD ["--help"]
