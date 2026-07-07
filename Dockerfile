FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install dependencies first so the layer is cached across code changes.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Run as a non-root user.
RUN useradd --create-home appuser && chown -R appuser /app
USER appuser

# The bot touches /tmp/gamejam_bot_heartbeat every 30s while polling is alive
# (see app/main.py); a stale file means the event loop is wedged → unhealthy.
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD ["python", "-c", "import os,sys,time,tempfile; p=os.path.join(tempfile.gettempdir(),'gamejam_bot_heartbeat'); sys.exit(0 if os.path.exists(p) and time.time()-os.path.getmtime(p)<90 else 1)"]

# run_migrations() runs on startup, so no separate migration step is needed.
CMD ["python", "-m", "app.main"]
