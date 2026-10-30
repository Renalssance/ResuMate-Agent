#!/bin/sh
set -eu

task_root=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
cd "$task_root"
mkdir -p build/cloudbase

# An explicit source list keeps credentials, local databases and logs out.
COPYFILE_DISABLE=1 tar \
  --exclude=node_modules \
  --exclude=dist \
  --exclude=__pycache__ \
  --exclude='*.pyc' \
  --exclude=.DS_Store \
  --exclude=.env \
  --exclude='.env.*' \
  --exclude='*.env' \
  -czf build/cloudbase/resumate-cloudbase-source.tar.gz \
  Dockerfile .dockerignore pyproject.toml uv.lock README.md \
  backend frontend extension deploy/cloudbase

printf '%s\n' "$task_root/build/cloudbase/resumate-cloudbase-source.tar.gz"
