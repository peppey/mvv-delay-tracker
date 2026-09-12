FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
COPY src ./src
COPY scripts ./scripts
COPY data ./data
COPY docs ./docs

RUN apt-get update \
	&& apt-get install --no-install-recommends --yes git \
	&& rm -rf /var/lib/apt/lists/* \
	&& uv sync --locked --no-dev

ENV PATH="/app/.venv/bin:$PATH"

ENTRYPOINT ["python", "scripts/cloud_job.py"]