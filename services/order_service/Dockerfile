FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# /data backs the named volume declared in compose.yaml. It must exist in the
# image and be owned by appuser: Docker seeds a fresh named volume with the
# image's contents *and ownership*, so without this the volume stays root-owned
# and the app cannot create its SQLite file ("unable to open database file").
RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /data \
    && chown -R appuser:appuser /app /data
USER appuser

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

