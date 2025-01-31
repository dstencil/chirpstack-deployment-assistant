# Stage 1: Build dependencies in a separate stage
FROM python:3.12-alpine3.18 AS builder
WORKDIR /app
COPY requirements.txt .

# Install dependencies and remove build tools in the same layer
RUN apk add --no-cache --virtual .build-deps gcc musl-dev libffi-dev && \
    pip install --no-cache-dir --prefix=/install -r requirements.txt && \
    rm -rf /root/.cache/pip && \
    apk del .build-deps

# Stage 2: Final lightweight image
FROM python:3.12-alpine3.18
WORKDIR /app
COPY --from=builder /install /usr/local
COPY /app .

# Remove __pycache__
RUN find /usr/local -type d -name '__pycache__' -exec rm -rf {} +

# Expose Flask default port
EXPOSE 5000

# Set environment variables
ENV FLASK_APP=app.py
ENV FLASK_RUN_HOST=0.0.0.0
ENV FLASK_ENV=production

# Run Flask server
CMD exec python -m flask run
