FROM python:3.12-slim
# O LightGBM usa a libgomp do sistema.
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir uv
WORKDIR /app/robo
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY mneme ./mneme
ENV PYTHONUNBUFFERED=1 PYTHONPATH=/app/robo
USER 1000:1000
