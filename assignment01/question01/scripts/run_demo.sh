#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
.venv/bin/python -m app.cli \
  --pages 3 \
  --interval 1.0 \
  --export-dir data/demo_books_3pages
