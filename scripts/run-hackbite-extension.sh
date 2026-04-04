#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
EXT_DIR="$ROOT_DIR/hackbite-vscode"

cd "$EXT_DIR"
npm install
npm run compile
code --new-window --extensionDevelopmentPath="$EXT_DIR" "$ROOT_DIR"

