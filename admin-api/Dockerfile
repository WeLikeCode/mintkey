# Admin API — Python 3.12 + FastAPI (ADR-0005, ADR-0012)
# Build context must be repo root so mintkey-models/ is accessible.
FROM python:3.12-slim

WORKDIR /app

# Install admin-api deps
COPY admin-api/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY admin-api/src/ src/
# Copy shared mintkey_models package directly into PYTHONPATH so no editable install needed.
COPY mintkey-models/mintkey_models/ src/mintkey_models/

ENV PYTHONPATH=/app/src
ENV PORT=8080

EXPOSE 8080

CMD ["uvicorn", "admin_api.main:app", "--host", "0.0.0.0", "--port", "8080"]
