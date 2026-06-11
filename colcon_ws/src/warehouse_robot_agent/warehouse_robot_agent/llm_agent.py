#!/usr/bin/env python3
"""
LLM agent — warehouse pick-and-deliver using WorldBackend.

Providers (set LLM_PROVIDER env var):
  gemini  (default) — Gemini flash-lite via google-genai SDK.
                      Requires GEMINI_API_KEY.
                      Quota rule: use a key separate from the P0.1 official
                      eval key; share only after Bảng A numbers are finalized.

  ollama            — Local model via Ollama's OpenAI-compatible REST API.
                      No API key required.  Requires ollama running locally.
                      Set OLLAMA_MODEL (default: qwen2.5:7b).
                      Set OLLAMA_BASE_URL if non-default (default: http://localhost:11434).

Usage:
  # Gemini (remote key)
  GEMINI_API_KEY=your-key python3 llm_agent.py

  # Local — no key
  LLM_PROVIDER=ollama python3 llm_agent.py
  LLM_PROVIDER=ollama WORLD_BACKEND=gazebo ros2 run warehouse_robot_agent llm_agent

Backend: any WorldBackend (Flat2DBackend, GazeboBackend, mocks).
SDK:     google-genai >= 2.0  (pip install google-genai)  — Gemini only
         requests (stdlib)                                 — Ollama only
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


# ──────────────────────── Ollama provider (OpenAI-compat) ────────────────── #
# Uses requests (stdlib) against Ollama's /v1/chat/completions endpoint.
# No extra pip install; qwen2.5:7b supports tool_call format via this endpoint.

OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL    = os.environ.get("OLLAMA_MODEL",    "qwen2.5:7b")


def _ollama_tools() -> list[dict]:
    """Convert TOOLS (JSON Schema) → OpenAI function-calling format for Ollama."""
    return [
        {
            "type": "function",
            "function": {
                "name":        t["name"],
                "description": t["description"],
                "parameters":  t["input_schema"],
            },
        }
        for t in TOOLS
    ]


def _parse_text_tool_calls(text: str) -> list[dict]:
    """Fallback: extract tool calls from model text when tool_calls[] is empty.

    qwen2.5:7b sometimes emits calls as text even with tool_choice='required':
      <tool_call>{"name": "pick", "arguments": {"object_name": "pallet_jack"}}</tool_call>
    or bare JSON with "name"/"arguments" keys.
    """
    import re
    results = []
    # Try <tool_call> blocks first
    for block in re.findall(r'<tool_call>\s*(.*?)\s*(?:</tool_call>|$)', text, re.DOTALL):
        try:
            obj = json.loads(block.strip())
            if "name" in obj and "arguments" in obj:
                results.append({
                    "function": {
                        "name": obj["name"],
                        "arguments": json.dumps(obj["arguments"]),
                    },
                    "id": f"text_{len(results)}",
                })
        except Exception:
            pass
    if results:
        return results
    # Try bare top-level JSON objects with name+arguments
    for m in re.finditer(r'(\{(?:[^{}]|\{[^{}]*\})*\})', text):
        try:
            obj = json.loads(m.group(1))
            if isinstance(obj, dict) and "name" in obj and "arguments" in obj:
                results.append({
                    "function": {
                        "name": obj["name"],
                        "arguments": json.dumps(obj["arguments"]),
                    },
                    "id": f"text_{len(results)}",
                })
        except Exception:
            pass
    return results


def _run_agent_ollama(
    backend,
    goal_text: str,
    system_prompt: str,
    temperature: float,
) -> dict:
    """Run one task via Ollama's OpenAI-compatible tool-calling endpoint.

    Uses urllib.request (Python stdlib) — no pip install needed.
    tool_choice='required' forces the model to call a tool each turn;
    without it, small models (qwen2.5:7b) may reply in text and the
    loop breaks at step 0.
    """
    import urllib.request as _ur

    tools    = _ollama_tools()
    url      = f"{OLLAMA_BASE_URL}/v1/chat/completions"
    messages: list[dict] = [
        {"role": "system", "content": system_prompt},
        {"role": "user",   "content": goal_text},
    ]

    done_called = False
    step        = 0
    trace: list[dict] = []

    print(f"[agent] Starting Ollama tool-calling loop ({OLLAMA_MODEL}) …")

    while not done_called and step < 25:
        payload = json.dumps({
            "model":       OLLAMA_MODEL,
            "messages":    messages,
            "tools":       tools,
            "tool_choice": "required",   # force tool call; prevents text-only replies
            "temperature": temperature,
            "stream":      False,
        }).encode()
        req = _ur.Request(url, data=payload, headers={"Content-Type": "application/json"})
        with _ur.urlopen(req, timeout=120) as r:
            data = json.loads(r.read())
        choice = data["choices"][0]
        msg    = choice["message"]
        reason = choice.get("finish_reason", "")

        if msg.get("content"):
            print(f"[agent] Assistant: {msg['content']}")

        tool_calls = msg.get("tool_calls") or []
        if not tool_calls and msg.get("content"):
            tool_calls = _parse_text_tool_calls(msg["content"])
            if tool_calls:
                print(f"[agent] ⚠ text-fallback parsed {len(tool_calls)} tool call(s) from content")
        if not tool_calls:
            print(f"[agent] No tool calls — finish_reason={reason}")
            break

        print(f"\n[agent] ─── Ollama turn ({len(tool_calls)} tool call(s)) ───")

        # Append assistant message (carries tool_calls) before tool results
        messages.append(msg)

        for tc in tool_calls:
            step += 1
            name = tc["function"]["name"]
            try:
                inp = json.loads(tc["function"]["arguments"])
            except Exception:
                inp = {}

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

            messages.append({
                "role":         "tool",
                "tool_call_id": tc.get("id", f"call_{step}"),
                "content":      result_str,
            })

    print("\n[agent] ══════════════════════════════")
    print(f"[agent] Task loop finished. steps={step} done={done_called}")
    print(f"[agent] Status: {'DONE ✓' if done_called else 'loop ended without done() call'}")

    return {"steps": step, "done_called": done_called, "trace": trace}


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
        pose = backend.locate_object(inp.get("name") or inp.get("object_name", ""))
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

# Model string must match the BTC sprint plan ("gemini-flash-lite-latest").
# Override with GEMINI_MODEL if the string is wrong for your API region.
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-flash-lite-latest")

SYSTEM_PROMPT = """You are a warehouse logistics agent controlling a forklift robot
inside a Gazebo Harmonic simulation of an AWS small warehouse.

Available tools: perceive, locate_object, check_path, move_to, pick, drop, oracle_check, done.

Map reference (fixed infrastructure only — object positions must come from locate_object):
  • Robot spawns at (3.45, 2.15).
  • Warehouse spans roughly x = [-6, 7], y = [-12, 8] in map frame.
  • dropoff_a: (0.0, 0.0)   — fixed drop zone
  • dropoff_b: (3.45, 2.15) — fixed drop zone, near spawn

General approach:
  1. Call perceive() to read robot pose and visible world state.
  2. Call locate_object(name) to get the current pose of any warehouse object.
     Do NOT assume object positions — always call locate_object first.
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
    temperature: float = 0.0,
) -> dict:
    """Run the LLM tool-calling loop for one task.

    Accepts any WorldBackend (GazeboBackend, Flat2DBackend, mocks).
    Returns {"steps": int, "done_called": bool, "trace": list[dict]}.
    Each trace entry: {"step": int, "tool": str, "input": dict, "output": any}.

    Provider is selected by LLM_PROVIDER env var (default: "gemini").
      gemini — Gemini flash-lite via google-genai SDK; requires GEMINI_API_KEY
      ollama — local Ollama via /v1/chat/completions; requires ollama running
    """
    provider      = os.environ.get("LLM_PROVIDER", "gemini").lower()
    goal          = goal_text    or INITIAL_USER_MSG
    prompt        = system_prompt or SYSTEM_PROMPT

    if provider == "ollama":
        return _run_agent_ollama(backend, goal, prompt, temperature)

    # ── Gemini path ───────────────────────────────────────────────────────── #
    if not _GEMINI_OK:
        raise ImportError("google-genai not installed: pip install google-genai")

    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY not set.\n"
            "  export GEMINI_API_KEY=your-key\n"
            "Use a key SEPARATE from the P0.1 official eval key.\n"
            "Or: LLM_PROVIDER=ollama for local no-key run."
        )

    client = genai.Client(api_key=api_key)

    config = gtypes.GenerateContentConfig(
        system_instruction=prompt,
        tools=_gemini_tools(),
        automatic_function_calling=gtypes.AutomaticFunctionCallingConfig(disable=True),
        temperature=temperature,   # 0.0 = deterministic; parity runs use T=0
    )

    chat = client.chats.create(model=GEMINI_MODEL, config=config)

    done_called = False
    step = 0
    trace: list[dict] = []

    print(f"[agent] Starting LLM tool-calling loop ({GEMINI_MODEL}) …")
    response = chat.send_message(goal)

    while not done_called and step < 25:
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
