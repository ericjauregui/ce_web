#!/bin/sh
set -eu

# Fail deployment before accepting traffic if durable storage is unavailable.
# This also supports services without Render's paid pre-deploy command.
.venv/bin/python -m scripts.database migrate
exec .venv/bin/gunicorn --workers 1 --threads 2 --timeout 60 --bind "0.0.0.0:${PORT:-5001}" app:app
