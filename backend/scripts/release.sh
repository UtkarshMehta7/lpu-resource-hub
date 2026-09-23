#!/usr/bin/env bash
# Release step: bring a deployed database up to the current schema.
#
# Run from your own machine, pointed at the production database. The API
# deliberately does not migrate on start -- two instances booting at once
# would race -- and Render's pre-deploy hook is not on the free tier, so
# this is the step that replaces it.
#
#   backend/scripts/release.sh
#
# Reads DATABASE_URL from backend/.env.production (git-ignored) if it is not
# already in the environment, so the connection string never has to be typed
# into a shell where it would land in history.
set -euo pipefail

cd "$(dirname "$0")/.."

if [[ -z "${DATABASE_URL:-}" ]]; then
  if [[ -f .env.production ]]; then
    # shellcheck disable=SC1091
    set -a && source .env.production && set +a
  else
    echo "DATABASE_URL is not set, and backend/.env.production does not exist." >&2
    echo >&2
    echo "Create it with the Neon connection string, note the scheme:" >&2
    echo '  DATABASE_URL=postgresql+psycopg://user:password@host/dbname' >&2
    echo >&2
    echo "The file is git-ignored (.env.* in .gitignore)." >&2
    exit 1
  fi
fi

if [[ "${DATABASE_URL}" != postgresql+psycopg://* ]]; then
  echo "DATABASE_URL must start with postgresql+psycopg://" >&2
  echo "Neon gives you postgres://…  -- change the scheme, keep the rest." >&2
  exit 1
fi

# Never print the URL itself: it carries the password.
python - <<'PY'
import os
from urllib.parse import urlsplit

parts = urlsplit(os.environ["DATABASE_URL"])
print(f"Target: {parts.hostname}{parts.path}")
PY

echo "Applying migrations…"
alembic upgrade head
alembic current

echo
echo "Schema is current. Next, create the first administrator:"
echo "  cd backend && set -a && source .env.production && set +a && python -m scripts.create_admin"
echo "It prompts for the password, so it has to be run interactively."
