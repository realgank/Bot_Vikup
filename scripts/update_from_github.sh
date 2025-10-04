#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")"/.. && pwd)"
cd "$REPO_ROOT"

REMOTE_URL="${1:-}" 
BRANCH="${BRANCH:-main}"

if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  if [ -n "$REMOTE_URL" ]; then
    if git remote get-url origin >/dev/null 2>&1; then
      git remote set-url origin "$REMOTE_URL"
    else
      git remote add origin "$REMOTE_URL"
    fi
  fi
  if ! git remote get-url origin >/dev/null 2>&1; then
    echo "Origin remote is not configured. Pass the GitHub repository URL as the first argument." >&2
    exit 1
  fi
  git fetch origin "$BRANCH"
  git pull --rebase origin "$BRANCH"
else
  if [ -z "$REMOTE_URL" ]; then
    echo "Usage: $0 <github-repo-url>" >&2
    exit 1
  fi
  git clone "$REMOTE_URL" "$REPO_ROOT"
fi
