# Agentic Cinema Backend — Cloud Run
# FastAPI JSON API (post-split from the Jinja2 monolith)
# \u0000\u0000
FROM python:3.10-slim

WORKDIR /app

# Install system deps needed by some Python packages (pdfplumber, lxml, etc.)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential \
        pkg-config \
        libxml2-dev \
        libxslt1-dev \
        && rm -rf /var/lib/apt/lists/*

# Copy dependency files first for Docker layer caching
COPY pyproject.toml README.md ./
COPY requirements.txt ./

# Install dependencies
# NOTE: if requirements.txt doesn't exist at the repo root, the build will fail.
# The Dockerfile expects requirements.txt at the repo root (same dir as this file).
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY src/ ./src/
COPY docs/ ./docs/

# Create a writable temp dir for file uploads (Cloud Run ephemeral filesystem)
RUN mkdir -p /tmp/uploads && chmod 777 /tmp/uploads

# The backend no longer serves Jinja2 templates or static files — those live
# in the Vercel-hosted Next.js frontend.  The APP_STATIC_DIR and template
# paths are no longer needed.

EXPOSE 8080

ENV PYTHONUNBUFFERED=1
ENV PORT=8080

CMD ["uvicorn", "src.web.app:app", "--host", "0.0.0.0", "--port", "8080"]
