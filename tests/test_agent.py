"""The tool loop runs against a scripted fake client: no network."""

from __future__ import annotations

from typing import Any

from google.genai import types

from app.agent import AgentRun, run_tool_loop
from app.guards import ToolPolicy, ToolRule


def call_response(name: str, **args: Any) -> types.GenerateContentResponse:
    part = types.Part(function_call=types.FunctionCall(name=name, args=args))
    return types.GenerateContentResponse(
        candidates=[types.Candidate(content=types.Content(role="model", parts=[part]))]
    )


def text_response(text: str) -> types.GenerateContentResponse:
    part = types.Part(text=text)
    return types.GenerateContentResponse(
        candidates=[types.Candidate(content=types.Content(role="model", parts=[part]))]
    )


class ScriptedModels:
    def __init__(self, replies: list[types.GenerateContentResponse]) -> None:
        self.replies = list(replies)
        self.requests: list[list[types.Content]] = []

    def generate_content(self, *, model: str, contents: Any, config: Any) -> Any:
        self.requests.append(list(contents))
        return self.replies.pop(0)


class ScriptedClient:
    def __init__(self, replies: list[types.GenerateContentResponse]) -> None:
        self.models = ScriptedModels(replies)


def lookup_order(order_id: str) -> dict:
    """Order status by id."""
    return {"order_id": order_id, "status": "delivered", "total": 40.0}


def issue_refund(order_id: str, amount: float) -> dict:
    """Refund an order."""
    return {"refunded": amount}


TOOLS = {"lookup_order": lookup_order, "issue_refund": issue_refund}
POLICY = ToolPolicy(
    [
        ToolRule("lookup_order", roles=frozenset({"customer"})),
        ToolRule("issue_refund", roles=frozenset({"customer"}), side_effect=True),
    ]
)


def run(
    replies: list[types.GenerateContentResponse], **kwargs: Any
) -> tuple[ScriptedClient, AgentRun]:
    client = ScriptedClient(replies)
    result = run_tool_loop(
        client,
        model="test-model",
        goal="refund A-1",
        tools=TOOLS,
        policy=POLICY,
        role="customer",
        **kwargs,
    )
    return client, result


def test_loop_runs_allowed_tool_and_returns_answer() -> None:
    client, result = run(
        [call_response("lookup_order", order_id="A-1"), text_response("Delivered.")]
    )
    assert result.answer == "Delivered."
    assert result.calls[0][2]["status"] == "delivered"
    sent = client.models.requests[1][-1].parts[0].function_response.response["result"]
    assert sent.startswith("<untrusted-")
    assert "delivered" in sent


def test_side_effect_without_confirmation_is_refused() -> None:
    _, result = run(
        [
            call_response("issue_refund", order_id="A-1", amount=40.0),
            text_response("Please confirm the refund."),
        ]
    )
    assert result.calls[0][2] == {"error": "'issue_refund' needs user confirmation"}
    assert result.answer == "Please confirm the refund."


def test_confirmed_side_effect_runs() -> None:
    _, result = run(
        [call_response("issue_refund", order_id="A-1", amount=40.0), text_response("Done.")],
        confirmed_tools=frozenset({"issue_refund"}),
    )
    assert result.calls[0][2] == {"refunded": 40.0}


def test_repeated_identical_call_stops_the_loop() -> None:
    same = call_response("lookup_order", order_id="A-1")
    _, result = run([same, same, text_response("never reached")])
    assert result.stopped == "repeated call lookup_order"
    assert result.steps == 2


def test_step_limit() -> None:
    replies = [call_response("lookup_order", order_id=f"A-{i}") for i in range(3)]
    _, result = run(replies, max_steps=3)
    assert result.stopped == "step limit reached"
