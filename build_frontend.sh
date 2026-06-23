#!/bin/bash
set -e
cd "$(dirname "$0")/frontend"
npm install
npm run build
echo "[build] Frontend built to frontend/dist/"
