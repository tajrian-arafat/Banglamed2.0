#!/usr/bin/env bash
# Resilient Cloudflare quick-tunnel wrapper for the BanglaMed 2.0 sandbox app.
# - Forces HTTP/2 (this sandbox blocks outbound QUIC/UDP 7844)
# - Auto-restarts cloudflared if it exits
# - Records the live public URL to /tmp/tunnel_url.txt (+ append-only history)
set -u

PORT="${PORT:-8000}"
LOG="/tmp/cloudflared.log"
URLFILE="/tmp/tunnel_url.txt"
URLHIST="/tmp/tunnel_url_history.txt"
CF="/tmp/cloudflared"

if [ ! -x "$CF" ]; then
  echo "[wrapper] cloudflared missing, downloading..." >> "$LOG"
  curl -fsSL -o "$CF" https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 \
    && chmod +x "$CF"
fi

# URL recorder: watches the log for the assigned hostname and records it.
record_url() {
  while true; do
    url=$(grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' "$LOG" 2>/dev/null | tail -1)
    if [ -n "$url" ]; then
      if [ ! -f "$URLFILE" ] || [ "$(cat "$URLFILE")" != "$url" ]; then
        printf '%s' "$url" > "$URLFILE"
        printf '%s\n' "$url" >> "$URLHIST"
        echo "[recorder] new URL: $url" >> "$LOG"
      fi
    fi
    sleep 5
  done
}
record_url &
RECORDER=$!

attempt=0
while true; do
  attempt=$((attempt+1))
  echo "[wrapper] === attempt #$attempt starting cloudflared $(date -u +%FT%TZ) ===" >> "$LOG"
  "$CF" tunnel --url "http://127.0.0.1:${PORT}" --no-autoupdate --protocol http2 --retries 5 >> "$LOG" 2>&1
  code=$?
  echo "[wrapper] cloudflared exited (code=$code) at $(date -u +%FT%TZ); restarting in 3s" >> "$LOG"
  sleep 3
done
