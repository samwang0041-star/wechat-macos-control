#!/usr/bin/env bash
set -euo pipefail

repo_name="${1:-wechat-macos-control}"
visibility="${2:-public}"

if [[ "${visibility}" != "public" && "${visibility}" != "private" ]]; then
  echo "Usage: $0 [repo-name|owner/repo-name] [public|private]" >&2
  exit 1
fi

if ! command -v gh >/dev/null 2>&1; then
  echo "gh CLI is not installed." >&2
  exit 1
fi

if ! gh auth status >/dev/null 2>&1; then
  echo "GitHub CLI is not authenticated. Run: gh auth login" >&2
  exit 1
fi

if git remote get-url origin >/dev/null 2>&1; then
  echo "origin already exists. Pushing current branch..." >&2
  git push -u origin main
  exit 0
fi

gh repo create "${repo_name}" \
  "--${visibility}" \
  --source . \
  --remote origin \
  --push
