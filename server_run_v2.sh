#!/bin/bash
# BanglaMed backend watchdog: restarts uvicorn if it ever exits.
cd /workspace/banglamed2.0/backend || exit 1
while true; do
  python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000 >> /tmp/uvicorn.log 2>&1
  echo "[watchdog] uvicorn exited $?, restarting in 3s" >> /tmp/uvicorn.log
  sleep 3
done
