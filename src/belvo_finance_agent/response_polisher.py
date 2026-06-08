from __future__ import annotations

import json
from typing import Any

from .config import Settings, get_settings
from .models import FinancialAnswer


SKIP_POLISH_WORKFLOWS = {"read_only_refusal", "unsupported_question"}
POLISH_SYSTEM_PROMPT = """You polish grounded financial answers.

Rules:
- Do not change amounts, dates, descriptions, accounts, counts, transaction rows, filters, caveats or conclusions.
- Do not add new facts or recommendations.
- Keep the same language as the user's question.
- Keep markdown table placeholders exactly unchanged.
- Improve readability, confidence and flow only.
"""


async def polish_financial_answer(answer: FinancialAnswer, settings: Settings | None = None) -> FinancialAnswer:
    settings = settings or get_settings()
    provider = (settings.model_provider or "none").lower()
    model = settings.model_name or "claude-haiku-4-5"

    if answer.workflow in SKIP_POLISH_WORKFLOWS:
        return answer
    if not getattr(settings, "enable_llm_polish", False):
        _record_polish(answer, provider=provider, model=model, status="skipped", reason="disabled")
        return answer
    if provider == "none":
        _record_polish(answer, provider=provider, model=model, status="skipped", reason="provider_none")
        return answer
    if provider != "anthropic":
        _record_polish(answer, provider=provider, model=model, status="skipped", reason="unsupported_provider")
        return answer

    api_key = getattr(settings, "anthropic_api_key", "")
    if not api_key:
        _record_polish(answer, provider=provider, model=model, status="fallback", reason="missing_anthropic_api_key")
        return answer

    protected_answer, table_blocks = _protect_markdown_tables(answer.answer)
    payload = _build_payload(answer, protected_answer)

    try:
        polished = await _call_anthropic(
            api_key=api_key,
            model=model,
            max_tokens=getattr(settings, "llm_polish_max_tokens", 350),
            payload=payload,
        )
    except Exception as exc:  # pragma: no cover - exact SDK exceptions vary.
        _record_polish(answer, provider=provider, model=model, status="fallback", reason=exc.__class__.__name__)
        return answer

    polished = _restore_markdown_tables(polished.strip(), table_blocks)
    if not polished:
        _record_polish(answer, provider=provider, model=model, status="fallback", reason="empty_response")
        return answer

    answer.answer = polished
    _record_polish(answer, provider=provider, model=model, status="polished")
    return answer


def _record_polish(
    answer: FinancialAnswer,
    *,
    provider: str,
    model: str,
    status: str,
    reason: str | None = None,
) -> None:
    value: dict[str, Any] = {"provider": provider, "model": model, "status": status}
    if reason:
        value["reason"] = reason
    answer.metadata = {**(answer.metadata or {}), "llm_polish": value}


def _build_payload(answer: FinancialAnswer, protected_answer: str) -> str:
    evidence = [
        item.model_dump(mode="json") if hasattr(item, "model_dump") else item
        for item in (answer.evidence or [])[:8]
    ]
    payload = {
        "question": answer.question,
        "original_answer": protected_answer,
        "workflow": answer.workflow,
        "filters": answer.filters,
        "caveats": answer.caveats,
        "evidence": evidence,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


async def _call_anthropic(*, api_key: str, model: str, max_tokens: int, payload: str) -> str:
    try:
        from anthropic import AsyncAnthropic
    except ModuleNotFoundError as exc:
        raise RuntimeError("anthropic_sdk_missing") from exc

    client = AsyncAnthropic(api_key=api_key)
    message = await client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=POLISH_SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": (
                    "Rewrite only the original_answer field for presentation quality. "
                    "Return only the polished answer text, with no wrapper.\n\n"
                    f"{payload}"
                ),
            }
        ],
    )
    return _extract_message_text(message)


def _extract_message_text(message: Any) -> str:
    content = getattr(message, "content", None)
    if isinstance(content, str):
        return content
    if not content:
        return ""
    parts: list[str] = []
    for block in content:
        if isinstance(block, dict):
            text = block.get("text", "")
        else:
            text = getattr(block, "text", "")
        if text:
            parts.append(text)
    return "\n".join(parts)


def _protect_markdown_tables(text: str) -> tuple[str, dict[str, str]]:
    lines = text.splitlines(keepends=True)
    result: list[str] = []
    tables: dict[str, str] = {}
    index = 0
    table_number = 1

    while index < len(lines):
        if _is_table_line(lines[index]):
            start = index
            while index < len(lines) and _is_table_line(lines[index]):
                index += 1
            block_lines = lines[start:index]
            if _looks_like_markdown_table(block_lines):
                placeholder = f"[[TABLE_BLOCK_{table_number}]]"
                tables[placeholder] = "".join(block_lines)
                result.append(f"{placeholder}\n")
                table_number += 1
            else:
                result.extend(block_lines)
            continue
        result.append(lines[index])
        index += 1

    return "".join(result), tables


def _restore_markdown_tables(text: str, tables: dict[str, str]) -> str:
    for placeholder, table in tables.items():
        if placeholder not in text:
            return ""
        text = text.replace(placeholder, table.rstrip("\n"))
    return text


def _is_table_line(line: str) -> bool:
    stripped = line.strip()
    return stripped.startswith("|") and stripped.endswith("|")


def _looks_like_markdown_table(lines: list[str]) -> bool:
    if len(lines) < 2:
        return False
    separator = lines[1].strip().replace("|", "").replace(":", "").replace("-", "")
    return separator == ""
