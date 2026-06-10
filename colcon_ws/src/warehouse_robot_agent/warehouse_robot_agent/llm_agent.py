#!/usr/bin/env python3
"""
LLM agent — warehouse pick-and-deliver task using GazeboBackend + Claude Opus 4.8.

Usage (after sourcing the colcon workspace):
  python3 llm_agent.py
  # or via ROS 2:
  ros2 run warehouse_robot_agent llm_agent
"""

import json
import sys

import anthropic

# rclpy and GazeboBackend are imported lazily inside main() so that
# dispatch(), run_agent(), and the tool definitions can be imported by
# tests and eval scripts without a live ROS installation.


# ─────────────────────────── tool definitions ─────────────────────────────── #

TOOLS: list[dict] = [
    {
        "name": "perceive",
        "description": (
            "Read current robot pose and visible world state. "
            "Returns robot pose (x, y, yaw) and known object positions."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "locate_object",
        "description": (
            "Return the 2D pose of a named warehouse object. "
            "Known names: pallet_jack, clutter_c_027..030, clutter_d_005, dropoff_a, dropoff_b."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Object name, e.g. 'pallet_jack'"},
            },
            "required": ["name"],
        },
    },
    {
        "name": "check_path",
        "description": "Return true if Nav2 can compute a collision-free path to (x, y).",
        "input_schema": {
            "type": "object",
            "properties": {
                "x": {"type": "number", "description": "Target X in metres"},
                "y": {"type": "number", "description": "Target Y in metres"},
            },
            "required": ["x", "y"],
        },
    },
    {
        "name": "move_to",
        "description": (
            "Navigate to pose (x, y, yaw). Blocks until Nav2 reports success or failure. "
            "Returns {success: bool}."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "x":   {"type": "number", "description": "Target X in metres"},
                "y":   {"type": "number", "description": "Target Y in metres"},
                "yaw": {"type": "number", "description": "Target heading in radians (default 0)"},
            },
            "required": ["x", "y"],
        },
    },
    {
        "name": "pick",
        "description": (
            "Pick up a named object. Robot should already be near it. "
            "Returns {success: bool}. (Stub — no MoveIt yet.)"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "object_name": {"type": "string", "description": "Name of object to pick"},
            },
            "required": ["object_name"],
        },
    },
    {
        "name": "drop",
        "description": (
            "Drop the held object at (x, y). "
            "Returns {success: bool}. (Stub — no MoveIt yet.)"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "x": {"type": "number", "description": "Drop X in metres"},
                "y": {"type": "number", "description": "Drop Y in metres"},
            },
            "required": ["x", "y"],
        },
    },
    {
        "name": "oracle_check",
        "description": (
            "Query Gazebo ground-truth state to verify task completion. "
            "Returns robot_pose, carrying status, and pallet_jack GT pose."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "done",
        "description": "Signal that the task is fully complete. Call this as the final step.",
        "input_schema": {
            "type": "object",
            "properties": {
                "summary": {
                    "type": "string",
                    "description": "One-sentence summary of what was accomplished",
                },
            },
            "required": ["summary"],
        },
    },
]


# ─────────────────────────── tool dispatcher ──────────────────────────────── #

def dispatch(backend, name: str, inp: dict) -> str:
    """Dispatch a tool call to any WorldBackend implementation."""
    if name == "perceive":
        view = backend.perceive()
        return json.dumps({
            "robot_pose": str(view.robot_pose),
            "objects": {k: str(v) for k, v in view.objects.items()},
            "map_info": view.map_info,
        })

    elif name == "locate_object":
        pose = backend.locate_object(inp["name"])
        if pose is None:
            return json.dumps(None)
        return json.dumps({"x": pose.x, "y": pose.y, "yaw": pose.yaw})

    elif name == "check_path":
        ok = backend.check_path(float(inp["x"]), float(inp["y"]))
        return json.dumps({"reachable": ok})

    elif name == "move_to":
        yaw = float(inp.get("yaw", 0.0))
        ok = backend.move_to(float(inp["x"]), float(inp["y"]), yaw)
        return json.dumps({"success": ok})

    elif name == "pick":
        ok = backend.pick(inp["object_name"])
        return json.dumps({"success": ok})

    elif name == "drop":
        ok = backend.drop(float(inp["x"]), float(inp["y"]))
        return json.dumps({"success": ok})

    elif name == "oracle_check":
        return json.dumps(backend.oracle_check())

    elif name == "done":
        return json.dumps({"acknowledged": True, "summary": inp.get("summary", "")})

    else:
        return json.dumps({"error": f"unknown tool: {name}"})


# ─────────────────────────── agent loop ───────────────────────────────────── #

SYSTEM_PROMPT = """You are a warehouse logistics agent controlling a TurtleBot3 Waffle AMR
inside a Gazebo Harmonic simulation of an AWS small warehouse.

Available tools: perceive, locate_object, check_path, move_to, pick, drop, oracle_check, done.

Map reference:
  • Robot spawns at (3.45, 2.15).
  • Warehouse spans roughly x = [-6, 7], y = [-12, 8] in map frame.
  • pallet_jack: (-0.28, -9.48)
  • dropoff_a: (0.0, 0.0)
  • dropoff_b: (3.45, 2.15) — near spawn.

General approach:
  1. Call perceive() to read robot pose and world state.
  2. Use locate_object() to confirm object positions.
  3. Navigate with move_to(); if it fails, try a nearby (x, y).
  4. Use check_path() when uncertain whether a position is reachable.
  5. Call oracle_check() before done() to verify task success.
  6. Call done() with a concise summary when the task is complete.

Do not exceed 25 total tool calls.
"""

INITIAL_USER_MSG = (
    "Start the task: retrieve the pallet_jack from its current location "
    "and deliver it to dropoff_a."
)


def run_agent(
    backend,
    goal_text: str | None = None,
    system_prompt: str | None = None,
) -> dict:
    """Run the LLM tool-calling loop for one task.

    Accepts any WorldBackend (GazeboBackend, Flat2DBackend, mocks).
    Returns {"steps": int, "done_called": bool, "trace": list[dict]}.
    Each trace entry: {"step": int, "tool": str, "input": dict, "output": any}.
    """
    client = anthropic.Anthropic()

    user_msg  = goal_text    if goal_text    is not None else INITIAL_USER_MSG
    sys_prompt = system_prompt if system_prompt is not None else SYSTEM_PROMPT

    messages: list[dict] = [{"role": "user", "content": user_msg}]
    done_called = False
    step = 0
    trace: list[dict] = []

    print("[agent] Starting LLM tool-calling loop …")

    while not done_called and step < 30:
        step += 1
        print(f"\n[agent] ─── LLM call #{step} ───")

        with client.messages.stream(
            model="claude-opus-4-8",
            max_tokens=4096,
            thinking={"type": "adaptive"},
            system=sys_prompt,
            tools=TOOLS,
            messages=messages,
        ) as stream:
            response = stream.get_final_message()

        # Preserve full content blocks (needed for tool_use IDs)
        messages.append({"role": "assistant", "content": response.content})

        # Print any visible text from the assistant
        for block in response.content:
            if hasattr(block, "text") and block.type == "text":
                print(f"[agent] Assistant: {block.text}")

        if response.stop_reason == "end_turn":
            print("[agent] Assistant signalled end_turn — treating as complete.")
            break

        if response.stop_reason != "tool_use":
            print(f"[agent] Unexpected stop_reason: {response.stop_reason!r} — aborting.")
            break

        # Execute all tool calls in this turn
        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue

            print(f"[agent] → {block.name}({json.dumps(block.input, ensure_ascii=False)})")
            result_str = dispatch(backend, block.name, block.input)
            print(f"[agent]   ← {result_str[:300]}")

            # Record in trace
            try:
                output = json.loads(result_str)
            except Exception:
                output = result_str
            trace.append({"step": step, "tool": block.name,
                           "input": block.input, "output": output})

            if block.name == "done":
                done_called = True

            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": result_str,
            })

        messages.append({"role": "user", "content": tool_results})

    print("\n[agent] ══════════════════════════════")
    print("[agent] Task loop finished.")
    if done_called:
        print("[agent] Status: DONE ✓")
    else:
        print("[agent] Status: loop ended without done() call")

    return {"steps": step, "done_called": done_called, "trace": trace}


# ─────────────────────────── entry point ──────────────────────────────────── #

def main():
    import rclpy
    from warehouse_robot_agent.gazebo_backend import GazeboBackend, GazeboBackendNode

    rclpy.init()
    node = GazeboBackendNode()
    backend = GazeboBackend(node)

    print("[agent] Waiting for initial AMCL/odom pose …")
    if not node.spin_until_pose(timeout=30.0):
        print("[agent] WARNING: No pose received in 30 s. Is the sim running?")

    try:
        metrics = run_agent(backend)
        print(f"[agent] Metrics: steps={metrics['steps']} done={metrics['done_called']}")
    except KeyboardInterrupt:
        print("\n[agent] Interrupted by user.")
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
