#!/usr/bin/env bash
# Build the GitHub Pages site into ./site  (landing page + the real overlay as a live demo)
set -euo pipefail
cd "$(dirname "$0")/.."
rm -rf site && mkdir -p site/demo
cp docs/index.html site/index.html
cp web/index.html web/demo.json site/demo/
touch site/.nojekyll
echo "Site built in ./site  (preview: python3 -m http.server -d site 8000)"
