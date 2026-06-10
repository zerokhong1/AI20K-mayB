#!/usr/bin/env python3
"""
LLM agent — warehouse pick-and-deliver using WorldBackend + Gemini flash-lite.

Usage (after sourcing the colcon workspace):
  GEMINI_API_KEY=your-key python3 llm_agent.py
  GEMINI_API_KEY=your-key ros2 run warehouse_robot_agent llm_agent

Quota rule: use a GEMINI_API_KEY separate from the P0.1 official eval key.
If sharing one key with the BTC P0.1 eval, only run this after Bảng A
official numbers are finalized (avoid rate-limit interference).

Backend: any WorldBackend (Flat2DBackend, GazeboBackend, mocks).
Model:   gemini-2.0-flash-lite  (override with GEMINI_MODEL env var)
SDK:     google-genai >= 2.0  (pip install google-genai)
"""

import json
import os
import sys

try:
    from google import genai
    from google.genai import types as gtypes
    _GEMINI_OK = True
except ImportError:
    _GEMINI_OK = False

# rclpy and GazeboBackend are imported lazily inside main() so that
# dispatch(), run_agent(), and tool definitions can be imported by
# tests and eval scripts without a live ROS installation.


# ─────────────────────────── tool definitions ─────────────────────────────── #

# Tool schemas in JSON Schema format. _gemini_tools() converts to gtypes.Tool.
# Keeping them as plain dicts lets parity_check.py and eval scripts import
# TOOLS without importing any LLM SDK.
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
            "Pick up a named object. Robot must already be near it. "
            "Returns {success: bool}."
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
        "description": "Drop the held object at (x, y). Returns {success: bool}.",
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
            "Query ground-truth state to verify task completion. "
            "Returns robot_pose, carrying status, and pallet_jack GT pose."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "done",
        "description": "Signal task complete. Call as the final step.",
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


# ─────────────────────────── Gemini tool builder ──────────────────────────── #

def _gemini_tools() -> "list[gtypes.Tool]":
    """Convert TOOLS (JSON Schema) → google.genai Tool list."""
    if not _GEMINI_OK:
        raise ImportError("google-genai not installed: pip install google-genai")
    decls = [
        gtypes.FunctionDeclaration(
            name=t["name"],
            description=t["description"],
            parameters=t["input_schema"],
        )
        for t in TOOLS
    ]
    return [gtypes.Tool(function_declarations=decls)]


# ─────────────────────────── tool dispatcher ──────────────────────────────── #

def dispatch(backend, name: str, inp: dict) -> str:
    """Dispatch a tool call to any WorldBackend implementation."""
    if name == "perceive":
        view = backend.perceive()
        return json.dumps({
            "robot_pose": str(view.robot_pose),
            "objects":    {k: str(v) for k, v in view.objects.items()},
            "map_info":   view.map_info,
        })
    elif name == "locate_object":
        pose = backend.locate_object(inp["name"])
        return json.dumps(None if pose is None else {"x": pose.x, "y": pose.y, "yaw": pose.yaw})
    elif name == "check_path":
        return json.dumps({"reachable": backend.check_path(float(inp["x"]), float(inp["y"]))})
    elif name == "move_to":
        ok = backend.move_to(float(inp["x"]), float(inp["y"]), float(inp.get("yaw", 0.0)))
        return json.dumps({"success": ok})
    elif name == "pick":
        return json.dumps({"success": backend.pick(inp["object_name"])})
    elif name == "drop":
        return json.dumps({"success": backend.drop(float(inp["x"]), float(inp["y"]))})
    elif name == "oracle_check":
        return json.dumps(backend.oracle_check())
    elif name == "done":
        return json.dumps({"acknowledged": True, "summary": inp.get("summary", "")})
    else:
        return json.dumps({"error": f"unknown tool: {name}"})


# ─────────────────────────── agent loop ───────────────────────────────────── #

GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash-lite")

SYSTEM_PROMPT = """You are a warehouse logistics agent controlling a forklift robot
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
    if not _GEMINI_OK:
        raise ImportError("google-genai not installed: pip install google-genai")

    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY not set.\n"
            "  export GEMINI_API_KEY=your-key\n"
            "Use a key SEPARATE from the P0.1 official eval key."
        )

    client = genai.Client(api_key=api_key)

    config = gtypes.GenerateContentConfig(
        system_instruction=(system_prompt or SYSTEM_PROMPT),
        tools=_gemini_tools(),
        automatic_function_calling=gtypes.AutomaticFunctionCallingConfig(disable=True),
    )

    chat = client.chats.create(model=GEMINI_MODEL, config=config)
    user_msg = goal_text or INITIAL_USER_MSG

    done_called = False
    step = 0
    trace: list[dict] = []

    print(f"[agent] Starting LLM tool-calling loop ({GEMINI_MODEL}) …")
    response = chat.send_message(user_msg)

    while not done_called and step < 30:
        # Print any text the model emits
        for part in (response.candidates[0].content.parts if response.candidates else []):
            if getattr(part, "text", None):
                print(f"[agent] Assistant: {part.text}")

        # Collect function calls from this turn
        parts = response.candidates[0].content.parts if response.candidates else []
        fn_calls = [
            p.function_call
            for p in parts
            if getattr(p, "function_call", None) and p.function_call.name
        ]

        if not fn_calls:
            fr = response.candidates[0].finish_reason if response.candidates else "unknown"
            print(f"[agent] No tool calls — finish_reason={fr}")
            break

        print(f"\n[agent] ─── LLM turn ({len(fn_calls)} tool call(s)) ───")

        fn_result_parts = []
        for fc in fn_calls:
            step += 1
            name = fc.name
            inp = dict(fc.args)

            print(f"[agent] [{step:02d}] → {name}({json.dumps(inp, ensure_ascii=False)})")
            result_str = dispatch(backend, name, inp)
            print(f"[agent]       ← {result_str[:300]}")

            try:
                output = json.loads(result_str)
            except Exception:
                output = result_str

            trace.append({"step": step, "tool": name, "input": inp, "output": output})

            if name == "done":
                done_called = True

            fn_result_parts.append(
                gtypes.Part.from_function_response(name=name, response={"output": output})
            )

        if fn_result_parts and not done_called:
            response = chat.send_message(fn_result_parts)

    print("\n[agent] ══════════════════════════════")
    print(f"[agent] Task loop finished. steps={step} done={done_called}")
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
