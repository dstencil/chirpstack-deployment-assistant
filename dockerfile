ARG PYTHON_IMAGE=python:3.12.14-alpine3.24

FROM ${PYTHON_IMAGE} AS builder
WORKDIR /app

COPY requirements.txt .
RUN apk upgrade --no-cache \
    && python -m pip install --no-cache-dir --upgrade \
        pip setuptools==84.0.0 wheel==0.48.0 \
    && python -m pip install --no-cache-dir --prefix=/install \
        -r requirements.txt

FROM ${PYTHON_IMAGE}
WORKDIR /app

RUN apk upgrade --no-cache \
    && addgroup -S appgroup \
    && adduser -S -G appgroup appuser

COPY --from=builder /install /usr/local
COPY --chown=appuser:appgroup app ./

USER appuser

EXPOSE 5000

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    FLASK_DEBUG=false

CMD ["gunicorn", "--bind=0.0.0.0:5000", "--workers=1", "--threads=4", "--timeout=30", "app:application"]
