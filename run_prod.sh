#!/usr/bin/env bash
# Helper to run app locally with gunicorn
set -euo pipefail

# ensure venv is activated or use system python
if [ -f .venv/bin/activate ]; then
  source .venv/bin/activate
fi

export FLASK_ENV=production
export FLASK_APP=app2.py

# default bind
bind=${BIND:-0.0.0.0:8000}
workers=${WORKERS:-4}

exec gunicorn -w "$workers" -b "$bind" app2:app
