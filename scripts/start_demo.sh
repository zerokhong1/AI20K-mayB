#!/usr/bin/env bash
# start_demo.sh — Cold-start the full Máy B demo stack.
#
# Starts all layers in the correct order and waits for each to become ready
# before starting the next. Target: demo-ready in < 5 minutes from a cold boot.
#
# Usage:
#   ./scripts/start_demo.sh           # normal start
#   ./scripts/start_demo.sh --headless  # no Gazebo GUI (GPU-less mode)
#
# Creates a tmux session named "demo" with one window per layer.
# To attach: tmux attach -t demo
# To kill:   tmux kill-session -t demo

set -euo pipefail

HEADLESS=${1:-""}
WS="$HOME/AI20K/colcon_ws"
SESSION="demo"
TIMEOUT=300   # max seconds to wait for full stack

_log() { echo "[start_demo] $*"; }
_ok()  { echo "[start_demo] ✓ $*"; }
_err() { echo "[start_demo] ✗ $*" >&2; }

# ── source workspace ─────────────────────────────────────────────────────── #
if [[ ! -f "$WS/install/setup.bash" ]]; then
    _err "Workspace not built: $WS/install/setup.bash not found"
    _err "Run: cd $WS && colcon build"
    exit 1
fi
source "$WS/install/setup.bash"

# ── kill any leftover processes ───────────────────────────────────────────── #
_log "Killing leftover ROS/Gazebo processes …"
pkill -f "gz sim"        2>/dev/null || true
pkill -f "ros2 launch"   2>/dev/null || true
pkill -f "ros2 run"      2>/dev/null || true
pkill -f "foxglove"      2>/dev/null || true
sleep 2

# ── tmux session ─────────────────────────────────────────────────────────── #
tmux kill-session -t "$SESSION" 2>/dev/null || true
tmux new-session  -d -s "$SESSION" -x 220 -y 50

# Helper: run a command in a named tmux window
_tmux_window() {
    local name="$1"; shift
    tmux new-window -t "$SESSION" -n "$name"
    tmux send-keys -t "$SESSION:$name" "source $WS/install/setup.bash && $*" Enter
}

# ── Layer 3: Gazebo + AWS world ───────────────────────────────────────────── #
_log "Starting Gazebo + AWS warehouse world …"
GZ_ARGS=""
[[ "$HEADLESS" == "--headless" ]] && GZ_ARGS="headless:=true"
_tmux_window "gazebo" \
    "ros2 launch aws_robomaker_small_warehouse_world small_warehouse.launch.py $GZ_ARGS"

_log "Waiting for Gazebo model list …"
T0=$SECONDS
until gz model --list 2>/dev/null | grep -q "PalletJack\|warehouse"; do
    if (( SECONDS - T0 > 90 )); then
        _err "Gazebo did not become ready in 90 s"
        exit 1
    fi
    sleep 2
done
_ok "Gazebo ready ($(( SECONDS - T0 )) s)"

# ── Layer 3b: Nav2 ────────────────────────────────────────────────────────── #
_log "Starting Nav2 …"
_tmux_window "nav2" \
    "ros2 launch nav2_bringup navigation_launch.py use_sim_time:=true \
     map:=$WS/src/aws-robomaker-small-warehouse-world/maps/005/map.yaml"

_log "Waiting for Nav2 action server …"
T0=$SECONDS
until ros2 action list 2>/dev/null | grep -q "navigate_to_pose"; do
    if (( SECONDS - T0 > 60 )); then
        _err "Nav2 did not become ready in 60 s"
        exit 1
    fi
    sleep 2
done
_ok "Nav2 ready ($(( SECONDS - T0 )) s)"

# ── Layer 3c: Perception node ─────────────────────────────────────────────── #
_log "Starting perception node …"
_tmux_window "perception" \
    "ros2 run warehouse_robot_agent perception_node"
sleep 3

# ── Layer 1: foxglove_bridge ──────────────────────────────────────────────── #
_log "Starting foxglove_bridge …"
_tmux_window "foxglove" \
    "ros2 launch foxglove_bridge foxglove_bridge_launch.xml"

_log "Waiting for foxglove_bridge port 8765 …"
T0=$SECONDS
until nc -z localhost 8765 2>/dev/null; do
    if (( SECONDS - T0 > 20 )); then
        _err "foxglove_bridge did not open port 8765 in 20 s"
        exit 1
    fi
    sleep 1
done
_ok "foxglove_bridge ready ($(( SECONDS - T0 )) s)"

# ── Summary ───────────────────────────────────────────────────────────────── #
TOTAL=$(( SECONDS ))
_ok "Full stack ready in ${TOTAL} s"
echo ""
echo "  tmux session : tmux attach -t $SESSION"
echo "  Foxglove     : open app.foxglove.dev → ws://localhost:8765"
echo "  Layout       : Foxglove → Layouts → Import → foxglove/warehouse_demo.json"
echo "  Tunnel (ext) : bash scripts/start_tunnel.sh    # expose 8765 via cloudflared/ngrok"
echo "  Run agent    : ros2 run warehouse_robot_agent llm_agent"
echo "  Run eval     : python3 eval/run_eval_gazebo.py"
