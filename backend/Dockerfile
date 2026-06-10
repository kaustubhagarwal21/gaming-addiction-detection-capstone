# Backend image for the Gaming Addiction Detection capstone.
# Two-stage build: builder installs deps, runtime is slim.

FROM python:3.11-slim AS builder

WORKDIR /build
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential gcc libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt


FROM python:3.11-slim AS runtime

# librosa/soundfile need libsndfile + ffmpeg at runtime; libgomp for sklearn/numba;
# tzdata so the TZ env var resolves (server runs in the family's local timezone).
RUN apt-get update && apt-get install -y --no-install-recommends \
    libsndfile1 ffmpeg libgomp1 curl tzdata \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --shell /bin/bash app

COPY --from=builder /root/.local /home/app/.local
# numba/matplotlib need writable cache dirs under the non-root user; PORT is
# supplied by the platform (Render sets it) and defaults to 5000 locally.
ENV PATH=/home/app/.local/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    NUMBA_CACHE_DIR=/tmp \
    MPLCONFIGDIR=/tmp \
    TZ=Asia/Kolkata \
    PORT=5000

WORKDIR /app
COPY --chown=app:app . /app
RUN mkdir -p /app/audio_uploads && chown -R app:app /app/audio_uploads

USER app

EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 CMD curl -fsS "http://localhost:${PORT}/api/health" || exit 1

# Production: gunicorn, threaded sync worker (Flask doesn't need async).
# ONE worker on purpose: the free tier has only 512 MB and the process loads the
# whole ML stack (RF + calibrator + chat + tfidf + voice + SHAP + numpy/sklearn).
# Two workers each grew their own copy under load (SHAP explainer + numpy buffers
# break --preload's copy-on-write sharing) and OOM-killed the instance -> 50x crash
# loop. Raise --workers only on a plan with more RAM (e.g. WEB_CONCURRENCY).
#
# --threads 8: requests are I/O-bound (waiting on Neon round trips), so more threads
#   give real concurrency at near-zero extra memory (they share the one model copy).
#   The DB connection pool (PG_POOL_MAX=10) is sized above the thread count.
# --max-requests 1000 (was 50): with three apps polling every 20-60 s, 50 recycled
#   the worker every few MINUTES — each recycle stalled in-flight polls and re-warmed
#   caches, which presented as "fails under load". 1000 still reclaims slow memory
#   creep, just roughly hourly instead of constantly.
# sh -c so ${PORT} (set by the platform) is expanded at runtime.
CMD ["sh", "-c", "gunicorn --bind 0.0.0.0:${PORT} --workers ${WEB_CONCURRENCY:-1} --threads 8 --timeout 120 --graceful-timeout 30 --keep-alive 5 --preload --max-requests 1000 --max-requests-jitter 100 --access-logfile - --error-logfile - app:app"]
