# learn-gemini starter: FastAPI + Google Gen AI SDK, served by uvicorn.

# ---- build: install dependencies into an isolated virtualenv ----------------
FROM python:3.13-slim AS build
ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
WORKDIR /app
COPY requirements.txt ./
RUN pip install -r requirements.txt

# ---- runtime ----------------------------------------------------------------
FROM python:3.13-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    PORT=8000
RUN useradd --create-home --uid 10001 appuser
WORKDIR /app
COPY --from=build /opt/venv /opt/venv
COPY --chown=appuser:appuser app ./app
USER appuser
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health').status == 200 else 1)"]
# GEMINI_API_KEY (or GOOGLE_GENAI_USE_ENTERPRISE + GOOGLE_CLOUD_PROJECT) is
# injected at run time. /health answers without it; /v1/* returns 503.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
