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

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD curl -fsS "http://localhost:${PORT}/api/health" || exit 1

# Production: gunicorn, threaded sync worker (Flask doesn't need async).
# ONE worker on purpose: the free tier has only 512 MB and the process loads the
# whole ML stack (RF + calibrator + chat + tfidf + voice + SHAP + numpy/sklearn).
# Two workers each grew their own copy under load (SHAP explainer + numpy buffers
# break --preload's copy-on-write sharing) and OOM-killed the instance -> 50x crash
# loop. One worker + 4 threads handles the demo's concurrency comfortably; raise
# --workers only if you move to a plan with more RAM (e.g. WEB_CONCURRENCY).
# --max-requests recycles the worker periodically to reclaim any memory creep.
# sh -c so ${PORT} (set by the platform) is expanded at runtime.
CMD ["sh", "-c", "gunicorn --bind 0.0.0.0:${PORT} --workers ${WEB_CONCURRENCY:-1} --threads 2 --timeout 120 --preload --max-requests 50 --max-requests-jitter 10 --access-logfile - --error-logfile - app:app"]
