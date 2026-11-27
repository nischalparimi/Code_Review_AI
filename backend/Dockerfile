FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8000

WORKDIR /app

COPY backend/requirements.txt ./requirements.txt
RUN python -m pip install --no-cache-dir -r requirements.txt

COPY analyzer/__init__.py analyzer/base.py analyzer/engine.py analyzer/rules.py analyzer/advanced_rules.py ./analyzer/
COPY backend/__init__.py ./backend/__init__.py
COPY backend/app/ ./backend/app/

RUN groupadd --system app && useradd --system --gid app --home-dir /app --no-create-home app
USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/health' % os.getenv('PORT', '8000'), timeout=2).read()" || exit 1

CMD ["sh", "-c", "exec uvicorn backend.app.main:app --host 0.0.0.0 --port \"${PORT:-8000}\" --no-server-header"]
