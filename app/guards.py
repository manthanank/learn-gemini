"""Agent safety controls for Stage 5.10 and masterclass M7.

None of these stop prompt injection on their own. They shrink what an
injected instruction can achieve: untrusted text is fenced and labelled, tools
are checked against the caller's role in code, side effects need a
confirmation the model cannot give, and links in the output are restricted to
hosts you trust.
"""

from __future__ import annotations

import re
import secrets
from collections.abc import Iterable
from dataclasses import dataclass
from urllib.parse import urlparse

URL_RE = re.compile(r"https?://[^\s)\"'<>\]]+", re.IGNORECASE)


def wrap_untrusted(text: str, source: str, *, boundary: str | None = None) -> str:
    """Fence third-party text (web pages, emails, tool output) as data.

    The boundary is random per call, so text inside cannot close the fence
    by guessing the tag. Any occurrence of the boundary is removed anyway.
    """
    tag = boundary or f"untrusted-{secrets.token_hex(6)}"
    cleaned = text.replace(tag, "")
    safe_source = re.sub(r"[^\w.:/-]", "_", source)
    return f'<{tag} source="{safe_source}">\n{cleaned}\n</{tag}>'


def disallowed_urls(text: str, allowed_hosts: Iterable[str]) -> list[str]:
    """URLs in model output whose host is not allowed (or a subdomain of one).

    Markdown images and links to attacker hosts are the usual way an injected
    prompt exfiltrates data: the secret goes into the query string and the
    client fetches it. Strip or refuse anything this returns.
    """
    allowed = {h.lower().strip(".") for h in allowed_hosts}
    bad = []
    for url in URL_RE.findall(text):
        host = (urlparse(url).hostname or "").lower()
        if not any(host == h or host.endswith("." + h) for h in allowed):
            bad.append(url)
    return bad


@dataclass(frozen=True)
class ToolRule:
    name: str
    roles: frozenset[str]
    side_effect: bool = False
    max_calls_per_task: int = 5


@dataclass(frozen=True)
class Decision:
    allowed: bool
    reason: str = ""


class ToolPolicy:
    """Decides, in code, whether a model-requested tool call may run."""

    def __init__(self, rules: Iterable[ToolRule]) -> None:
        self._rules = {rule.name: rule for rule in rules}

    def check(
        self, tool: str, *, role: str, calls_so_far: int = 0, confirmed: bool = False
    ) -> Decision:
        rule = self._rules.get(tool)
        if rule is None:
            return Decision(False, f"unknown tool {tool!r}")
        if role not in rule.roles:
            return Decision(False, f"role {role!r} may not call {tool!r}")
        if calls_so_far >= rule.max_calls_per_task:
            return Decision(False, f"{tool!r} call limit reached")
        if rule.side_effect and not confirmed:
            return Decision(False, f"{tool!r} needs user confirmation")
        return Decision(True)
