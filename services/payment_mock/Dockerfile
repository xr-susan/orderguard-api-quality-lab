FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
COPY services ./services

RUN pip install --no-cache-dir .

USER 65532:65532

EXPOSE 8001

CMD ["uvicorn", "services.payment_mock.app.main:app", "--host", "0.0.0.0", "--port", "8001"]
