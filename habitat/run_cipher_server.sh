#!/bin/sh
set -eu
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repo_dir=$(dirname -- "$script_dir")
export FLASK_SKIP_DOTENV=1
exec "$repo_dir/.venv/bin/python" -B "$script_dir/cipher_server.py"
