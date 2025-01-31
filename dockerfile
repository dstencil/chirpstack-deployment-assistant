# Stage 1: Build dependencies in a separate stage
FROM python:3.12-alpine3.18 AS builder
WORKDIR /app

# Copy dependency list first to leverage Docker layer caching
COPY requirements.txt .

# Update Alpine package index, install build dependencies, and remove them after installation
RUN apk update && apk add --no-cache --virtual .build-deps \
        gcc musl-dev libffi-dev \
    && python -m pip install --upgrade pip \
    && pip install --no-cache-dir --prefix=/install -r requirements.txt \
    && find /install -name '*.pyc' -delete \
    && find /install -name '__pycache__' -type d -exec rm -rf {} + \
    && rm -rf /root/.cache/pip \
    && apk del .build-deps \
    && rm -rf /var/cache/apk/*


# Stage 2: Final lightweight image
FROM python:3.12-alpine3.18

# Security: Create a non-root user to run the Flask app
RUN addgroup -S appgroup && adduser -S appuser -G appgroup
USER appuser

WORKDIR /app

# Copy dependencies from builder stage
COPY --from=builder /install /usr/local

# Copy the actual application
COPY --chown=appuser:appgroup /app .

# Expose Flask default port
EXPOSE 5000

# Environment variables
ENV FLASK_APP=app.py
ENV FLASK_RUN_HOST=0.0.0.0
ENV FLASK_ENV=production

# Secure entrypoint
ENTRYPOINT ["python", "-m", "flask"]
CMD ["run"]
