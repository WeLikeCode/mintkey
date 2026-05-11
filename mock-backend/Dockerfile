# Mock Backend — Python 3.12 + FastAPI
# Build context is mock-backend/ directory.
FROM python:3.12-slim

WORKDIR /app

COPY src/ src/
COPY pyproject.toml .

RUN pip install --no-cache-dir -e .

ENV PYTHONPATH=/app/src

EXPOSE 8999

CMD ["uvicorn", "mock_backend.rest.main:app", "--host", "0.0.0.0", "--port", "8999"]
