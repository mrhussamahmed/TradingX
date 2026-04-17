FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN pip install --no-cache-dir uv

WORKDIR /app

COPY . /app

RUN uv sync --dev

CMD ["uv", "run", "python", "-m", "tradingx"]
