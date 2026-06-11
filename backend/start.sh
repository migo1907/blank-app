#!/usr/bin/env bash
# Railway start wrapper. Railpack's runtime image has no system libgomp.so.1,
# which LightGBM needs. scikit-learn vendors a copy (with a patched soname),
# so expose it under the canonical filename via LD_LIBRARY_PATH before uvicorn
# starts — the dynamic linker resolves DT_NEEDED by filename on disk.
LIBDIR=/tmp/libs
mkdir -p "$LIBDIR"
GOMP=$(ls /app/.venv/lib/python*/site-packages/scikit_learn.libs/libgomp*.so* 2>/dev/null | head -1)
if [ -n "$GOMP" ]; then
  cp "$GOMP" "$LIBDIR/libgomp.so.1"
  echo "[start] libgomp.so.1 staged from $GOMP"
else
  echo "[start] WARNING: no vendored libgomp found — LightGBM may be unavailable"
fi
export LD_LIBRARY_PATH="$LIBDIR:${LD_LIBRARY_PATH:-}"
exec uvicorn main:app --host 0.0.0.0 --port "$PORT"
