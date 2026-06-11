#!/usr/bin/env bash
# start_demo.sh — Cold-start the full Máy B demo stack.
#
# Two workspaces:
#   ~/colcon_ws         — warehouse_nav (forklift SDF, bridge, Nav2 AMCL) — REAL stack
#   ~/AI20K/colcon_ws   — warehouse_robot_agent (agent, backends, perception)
#
# Usage:
#   ./scripts/start_demo.sh              # headless (default — no GUI window)
#   ./scripts/start_demo.sh --gui        # open Gazebo GUI window
#
# Creates a tmux session named "demo". One window runs the full sim+nav stack;
# the agent is launched separately by the operator.
#
# To attach:  tmux attach -t demo
# To kill:    tmux kill-session -t demo
# Cleanup:    bash ~/colcon_ws/kill_ros.sh

set -eo pipefail   # -u removed: colcon setup.bash references COLCON_TRACE without default

HEADLESS="true"
[[ "${1:-}" == "--gui" ]] && HEADLESS="false"

NAV_WS="$HOME/colcon_ws"
AGENT_WS="$HOME/AI20K/colcon_ws"
SESSION="demo"
TIMEOUT=300

_log() { echo "[start_demo] $*"; }
_ok()  { echo "[start_demo] ✓ $*"; }
_err() { echo "[start_demo] ✗ $*" >&2; exit 1; }

# ── preflight checks ──────────────────────────────────────────────────────── #
[[ -f "$NAV_WS/install/setup.bash"   ]] || _err "Nav workspace not built: $NAV_WS/install/setup.bash missing. Run: cd $NAV_WS && colcon build"
[[ -f "$AGENT_WS/install/setup.bash" ]] || _err "Agent workspace not built: $AGENT_WS/install/setup.bash missing. Run: cd $AGENT_WS && colcon build"
which tmux &>/dev/null                  || _err "tmux not found: sudo apt install -y tmux"

# ── source both workspaces (agent overlays nav) ───────────────────────────── #
source "$NAV_WS/install/setup.bash"
source "$AGENT_WS/install/setup.bash"

# ── clean up leftover processes ───────────────────────────────────────────── #
_log "Cleaning up leftover processes …"
bash "$NAV_WS/kill_ros.sh" 2>/dev/null || true
sleep 1

# ── tmux session ──────────────────────────────────────────────────────────── #
tmux kill-session -t "$SESSION" 2>/dev/null || true
tmux new-session -d -s "$SESSION" -x 220 -y 50

# Helper: open a new tmux window, source both workspaces, run command
_tmux_window() {
    local name="$1"; shift
    tmux new-window -t "$SESSION" -n "$name"
    tmux send-keys -t "$SESSION:$name" \
        "source $NAV_WS/install/setup.bash && source $AGENT_WS/install/setup.bash && $*" \
        Enter
}

# ── Layer 1: sim + robot + Nav2 + foxglove (one launch) ──────────────────── #
_log "Starting Gazebo + forklift + Nav2 + foxglove …"
_tmux_window "sim" \
    "ros2 launch warehouse_nav warehouse_sim.launch.py \
     robot_type:=forklift \
     headless:=$HEADLESS \
     use_foxglove:=true"

# ── wait: robot odom (proves forklift spawned + bridge running) ───────────── #
_log "Waiting for /odom (forklift spawned + bridge ready) …"
T0=$SECONDS
until ros2 topic list 2>/dev/null | grep -q "^/odom$"; do
    if (( SECONDS - T0 > 90 )); then
        _err "Forklift /odom not seen in 90 s — check tmux window 'sim'"
    fi
    sleep 2
done
_ok "/odom present ($(( SECONDS - T0 )) s)"

# ── wait: Nav2 action server ──────────────────────────────────────────────── #
_log "Waiting for Nav2 navigate_to_pose …"
T0=$SECONDS
until ros2 action list 2>/dev/null | grep -q "navigate_to_pose"; do
    if (( SECONDS - T0 > 90 )); then
        _err "Nav2 navigate_to_pose not seen in 90 s — check tmux window 'sim'"
    fi
    sleep 2
done
_ok "Nav2 ready ($(( SECONDS - T0 )) s)"

# ── wait: foxglove port 8765 ──────────────────────────────────────────────── #
_log "Waiting for foxglove_bridge port 8765 …"
T0=$SECONDS
until nc -z localhost 8765 2>/dev/null; do
    if (( SECONDS - T0 > 30 )); then
        _err "foxglove_bridge port 8765 not open in 30 s"
    fi
    sleep 1
done
_ok "foxglove_bridge ready ($(( SECONDS - T0 )) s)"

# ── summary ───────────────────────────────────────────────────────────────── #
TOTAL=$(( SECONDS ))
_ok "Full stack ready in ${TOTAL} s"
echo ""
echo "  tmux              : tmux attach -t $SESSION  (window: sim)"
echo "  Foxglove          : app.foxglove.dev → ws://localhost:8765"
echo "  Layout            : Foxglove → Layouts → Import → foxglove/warehouse_demo.json"
echo "  Tunnel (external) : bash scripts/start_tunnel.sh"
echo ""
echo "  Run 1 task (local): LLM_PROVIDER=ollama WORLD_BACKEND=gazebo \\"
echo "                        ros2 run warehouse_robot_agent llm_agent"
echo "  Run eval Bảng C   : LLM_PROVIDER=ollama python3 eval/run_eval_gazebo.py"
echo "  Run parity B3(b)  : LLM_PROVIDER=ollama python3 eval/parity_check.py --live-gazebo"
