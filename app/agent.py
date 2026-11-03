"""A bounded, policy-checked tool loop (Stage 5.11 and masterclass M7).

The loop is written against the SDK's attribute path
(`client.models.generate_content`) so tests can pass a fake client that
returns real `google.genai.types` objects.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from google.genai import types

from app.guards import ToolPolicy, wrap_untrusted

MAX_RESULT_CHARS = 4_000


@dataclass
class AgentRun:
    answer: str
    steps: int
    calls: list[tuple[str, dict[str, Any], Any]] = field(default_factory=list)
    stopped: str = ""


def run_tool_loop(
    client: Any,
    *,
    model: str,
    goal: str,
    tools: Mapping[str, Callable[..., Any]],
    policy: ToolPolicy,
    role: str,
    confirmed_tools: frozenset[str] = frozenset(),
    max_steps: int = 6,
) -> AgentRun:
    config = types.GenerateContentConfig(
        tools=list(tools.values()),
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
    )
    history: list[types.Content] = [types.UserContent(parts=[types.Part(text=goal)])]
    run = AgentRun(answer="", steps=0)
    per_tool: dict[str, int] = {}
    last_call: tuple[str, str] | None = None

    for step in range(1, max_steps + 1):
        run.steps = step
        response = client.models.generate_content(model=model, contents=history, config=config)
        history.append(response.candidates[0].content)  # keeps thought signatures
        calls = response.function_calls or []
        if not calls:
            run.answer = response.text or ""
            return run

        parts = []
        for call in calls:
            args = dict(call.args or {})
            fingerprint = (call.name, json.dumps(args, sort_keys=True))
            if fingerprint == last_call:
                run.stopped = f"repeated call {call.name}"
                return run
            last_call = fingerprint

            decision = policy.check(
                call.name,
                role=role,
                calls_so_far=per_tool.get(call.name, 0),
                confirmed=call.name in confirmed_tools,
            )
            if decision.allowed:
                per_tool[call.name] = per_tool.get(call.name, 0) + 1
                try:
                    output: Any = tools[call.name](**args)
                except Exception as exc:  # the model sees the error and can adapt
                    output = {"error": f"{type(exc).__name__}: {exc}"}
            else:
                output = {"error": decision.reason}
            run.calls.append((call.name, args, output))
            text = json.dumps(output, default=str)[:MAX_RESULT_CHARS]
            parts.append(
                types.Part.from_function_response(
                    name=call.name,
                    response={"result": wrap_untrusted(text, source=f"tool:{call.name}")},
                )
            )
        history.append(types.UserContent(parts=parts))

    run.stopped = "step limit reached"
    return run
