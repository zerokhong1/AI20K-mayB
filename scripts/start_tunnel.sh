#!/usr/bin/env bash
# start_tunnel.sh — Expose foxglove_bridge:8765 via cloudflared or ngrok.
#
# Usage:
#   ./scripts/start_tunnel.sh              # auto-detect tunnel tool
#   ./scripts/start_tunnel.sh cloudflared  # force cloudflared
#   ./scripts/start_tunnel.sh ngrok        # force ngrok
#
# Prerequisites (pick one):
#   cloudflared:
#     wget -q https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 \
#          -O /usr/local/bin/cloudflared && chmod +x /usr/local/bin/cloudflared
#   ngrok:
#     curl -s https://ngrok-agent.s3.amazonaws.com/ngrok.asc | sudo tee /etc/apt/trusted.gpg.d/ngrok.asc >/dev/null
#     echo "deb https://ngrok-agent.s3.amazonaws.com buster main" | sudo tee /etc/apt/sources.list.d/ngrok.list
#     sudo apt update && sudo apt install ngrok
#     ngrok config add-authtoken <YOUR_TOKEN>
#
# Connect from external network once tunnel is running:
#   Foxglove Studio → Open connection → Foxglove WebSocket → paste the wss:// URL

set -euo pipefail

FOXGLOVE_PORT=8765
LOG_DIR="$(dirname "$0")/../eval/results"
TOOL_PREF="${1:-auto}"

_log() { echo "[tunnel] $*"; }
_err() { echo "[tunnel] ERROR: $*" >&2; }

# ── 1. Ensure foxglove_bridge is up ────────────────────────────────────────── #
if ! nc -z localhost "$FOXGLOVE_PORT" 2>/dev/null; then
    _err "foxglove_bridge is not running on port $FOXGLOVE_PORT."
    _err "Start the demo stack first:"
    _err "  bash scripts/start_demo.sh"
    exit 1
fi
_log "foxglove_bridge confirmed on port $FOXGLOVE_PORT"

# ── 2. Detect available tunnel tool ────────────────────────────────────────── #
pick_tool() {
    case "$TOOL_PREF" in
        cloudflared) echo "cloudflared" ;;
        ngrok)       echo "ngrok" ;;
        auto)
            if command -v cloudflared &>/dev/null; then echo "cloudflared"
            elif command -v ngrok &>/dev/null;      then echo "ngrok"
            else
                _err "Neither cloudflared nor ngrok found."
                _err ""
                _err "Install cloudflared (no account required):"
                _err "  wget -q https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 \\"
                _err "       -O /usr/local/bin/cloudflared && chmod +x /usr/local/bin/cloudflared"
                _err ""
                _err "Install ngrok (free account required):"
                _err "  See: https://dashboard.ngrok.com/get-started/setup/linux"
                exit 1
            fi
            ;;
        *) _err "Unknown tool '$TOOL_PREF'. Use: cloudflared | ngrok | auto"; exit 1 ;;
    esac
}

TOOL=$(pick_tool)
_log "Using tunnel tool: $TOOL"

# ── 3. Start tunnel and capture URL ────────────────────────────────────────── #
mkdir -p "$LOG_DIR"
TUNNEL_LOG="$LOG_DIR/tunnel_last.log"

start_cloudflared() {
    _log "Starting cloudflared quick-tunnel → ws://localhost:$FOXGLOVE_PORT"
    _log "URL will appear below in ~5 s (press Ctrl-C to stop):"
    echo ""

    # cloudflared prints the URL to stderr; tee to log
    cloudflared tunnel --url "http://localhost:$FOXGLOVE_PORT" 2>&1 | \
        tee "$TUNNEL_LOG" | \
        while IFS= read -r line; do
            echo "  $line"
            # Foxglove needs wss:// — cloudflared gives https://
            if echo "$line" | grep -qo 'https://[a-z0-9-]*\.trycloudflare\.com'; then
                URL=$(echo "$line" | grep -o 'https://[a-z0-9-]*\.trycloudflare\.com')
                WSS="${URL/https:/wss:}"
                echo ""
                echo "┌──────────────────────────────────────────────────────────────┐"
                echo "│  HTTPS URL : $URL"
                echo "│  WSS URL   : $WSS"
                echo "│"
                echo "│  Foxglove Studio → Open connection → Foxglove WebSocket"
                echo "│  Paste:  $WSS"
                echo "└──────────────────────────────────────────────────────────────┘"
                echo "$WSS" > "$LOG_DIR/tunnel_url.txt"
            fi
        done
}

start_ngrok() {
    _log "Starting ngrok HTTP tunnel → http://localhost:$FOXGLOVE_PORT"

    # ngrok API runs on 4040 by default
    ngrok http "$FOXGLOVE_PORT" --log stdout --log-format json > "$TUNNEL_LOG" 2>&1 &
    NGROK_PID=$!
    _log "ngrok PID: $NGROK_PID"

    # Poll ngrok local API for the public URL
    _log "Waiting for ngrok URL …"
    for i in $(seq 1 20); do
        sleep 1
        URL=$(curl -s http://localhost:4040/api/tunnels 2>/dev/null \
              | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    for t in d.get('tunnels', []):
        u = t.get('public_url','')
        if u.startswith('https'):
            print(u); break
except: pass
" 2>/dev/null || true)
        if [[ -n "$URL" ]]; then
            WSS="${URL/https:/wss:}"
            echo ""
            echo "┌──────────────────────────────────────────────────────────────┐"
            echo "│  HTTPS URL : $URL"
            echo "│  WSS URL   : $WSS"
            echo "│"
            echo "│  Foxglove Studio → Open connection → Foxglove WebSocket"
            echo "│  Paste:  $WSS"
            echo "└──────────────────────────────────────────────────────────────┘"
            echo "$WSS" > "$LOG_DIR/tunnel_url.txt"
            _log "Press Ctrl-C to stop the tunnel."
            wait "$NGROK_PID"
            return
        fi
    done
    _err "ngrok did not expose a URL within 20 s. Check $TUNNEL_LOG"
    kill "$NGROK_PID" 2>/dev/null || true
    exit 1
}

# ── 4. Load Foxglove layout reminder ────────────────────────────────────────── #
LAYOUT_PATH="$(cd "$(dirname "$0")/.." && pwd)/foxglove/warehouse_demo.json"
_log "Foxglove layout: $LAYOUT_PATH"
_log "  → Foxglove Studio → Layouts → Import from file → warehouse_demo.json"
echo ""

case "$TOOL" in
    cloudflared) start_cloudflared ;;
    ngrok)       start_ngrok       ;;
esac
