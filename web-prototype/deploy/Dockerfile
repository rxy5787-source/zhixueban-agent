FROM node:24-bookworm-slim AS web
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
ENV VITE_ONLINE_TRIAL=true
RUN npm run build

FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HOME=/home/trial
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates libgomp1 && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 trial && mkdir /data && chown trial:trial /data
COPY server/requirements.txt ./
RUN python -m pip install --no-cache-dir -r requirements.txt
COPY server/ ./
COPY --from=web /build/dist /app/public
USER trial
CMD ["python", "-m", "uvicorn", "backend.web_trial:from_environment", "--factory", "--host", "0.0.0.0", "--port", "8080", "--workers", "1", "--proxy-headers", "--forwarded-allow-ips", "*"]
