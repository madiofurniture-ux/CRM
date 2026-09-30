# Production image for the MADIO CRM FastAPI backend.
# Works on Google Cloud Run, Render (Docker), Fly.io, Railway, or any container host.
FROM python:3.12-slim

WORKDIR /app

# Install deps first so layer caching survives code changes.
COPY requirements-prod.txt .
RUN pip install --no-cache-dir -r requirements-prod.txt

COPY . .

# Cloud Run / Render inject $PORT; default to 8080 for local `docker run`.
ENV PORT=8080
EXPOSE 8080

# Shell form so ${PORT} expands at runtime.
CMD uvicorn server:app --host 0.0.0.0 --port ${PORT}
