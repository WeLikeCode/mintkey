# Admin API — Python 3.12 + FastAPI + uv (ADR-0005, ADR-0012)
FROM python:3.12-slim

WORKDIR /app

# Install deps first for layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ src/

ENV PYTHONPATH=/app/src
ENV PORT=8080

EXPOSE 8080

CMD ["uvicorn", "admin_api.main:app", "--host", "0.0.0.0", "--port", "8080"]
