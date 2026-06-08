import asyncio
from decimal import Decimal
from types import SimpleNamespace

from belvo_finance_agent.agent import FinancialSpecialistAgent
from belvo_finance_agent.models import ChartSpec, FinancialAnswer, TransactionEvidence
from belvo_finance_agent.response_polisher import polish_financial_answer


def settings(**overrides):
    data = {
        "model_provider": "anthropic",
        "model_name": "claude-haiku-4-5",
        "anthropic_api_key": "test-key",
        "enable_llm_polish": True,
        "llm_polish_max_tokens": 350,
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def sample_answer(answer_text: str = "You spent R$ 55.90 on Netflix.") -> FinancialAnswer:
    return FinancialAnswer(
        question="how much did I spend on Netflix?",
        answer=answer_text,
        workflow="transaction_query_total",
        tools_used=["list_transactions"],
        filters={"status": "PROCESSED", "type": "OUTFLOW"},
        evidence=[
            TransactionEvidence(
                date="2026-05-09",
                amount=Decimal("55.90"),
                type="OUTFLOW",
                account="Nubank Mastercard",
                description="NETFLIX.COM",
            )
        ],
        metadata={"total": "55.90"},
        caveats=["Amounts are based on processed transactions."],
        chart=ChartSpec(chart_type="bar", title="Subscription spending", x_label="Service", y_label="Total"),
    )


def run(coro):
    return asyncio.run(coro)


def test_polisher_replaces_only_answer_text(monkeypatch) -> None:
    original = sample_answer()

    async def fake_call(**kwargs):
        return "You spent R$ 55.90 on Netflix, based on one processed transaction."

    monkeypatch.setattr("belvo_finance_agent.response_polisher._call_anthropic", fake_call)

    result = run(polish_financial_answer(original, settings()))

    assert result.answer == "You spent R$ 55.90 on Netflix, based on one processed transaction."
    assert result.workflow == "transaction_query_total"
    assert result.tools_used == ["list_transactions"]
    assert result.filters == {"status": "PROCESSED", "type": "OUTFLOW"}
    assert result.evidence[0].description == "NETFLIX.COM"
    assert result.chart is not None
    assert result.metadata["total"] == "55.90"
    assert result.metadata["llm_polish"] == {
        "provider": "anthropic",
        "model": "claude-haiku-4-5",
        "status": "polished",
    }


def test_polisher_preserves_markdown_tables_byte_for_byte(monkeypatch) -> None:
    table = "| Date | Description | Amount |\n|---|---|---|\n| 2026-05-09 | NETFLIX.COM | R$ 55.90 |"
    original = sample_answer(f"Here are the matching transactions:\n\n{table}\n\nTotal: R$ 55.90.")

    async def fake_call(**kwargs):
        assert "[[TABLE_BLOCK_1]]" in kwargs["payload"]
        return "I found these matching transactions:\n\n[[TABLE_BLOCK_1]]\n\nTotal: R$ 55.90."

    monkeypatch.setattr("belvo_finance_agent.response_polisher._call_anthropic", fake_call)

    result = run(polish_financial_answer(original, settings()))

    assert table in result.answer
    assert "| 2026-05-09 | NETFLIX.COM | R$ 55.90 |" in result.answer
    assert result.metadata["llm_polish"]["status"] == "polished"


def test_polisher_falls_back_when_api_key_is_missing(monkeypatch) -> None:
    original = sample_answer()

    async def fake_call(**kwargs):
        raise AssertionError("Anthropic should not be called without a key")

    monkeypatch.setattr("belvo_finance_agent.response_polisher._call_anthropic", fake_call)

    result = run(polish_financial_answer(original, settings(anthropic_api_key="")))

    assert result.answer == "You spent R$ 55.90 on Netflix."
    assert result.metadata["llm_polish"] == {
        "provider": "anthropic",
        "model": "claude-haiku-4-5",
        "status": "fallback",
        "reason": "missing_anthropic_api_key",
    }


def test_polisher_falls_back_when_api_fails(monkeypatch) -> None:
    original = sample_answer()

    async def fake_call(**kwargs):
        raise RuntimeError("rate limited")

    monkeypatch.setattr("belvo_finance_agent.response_polisher._call_anthropic", fake_call)

    result = run(polish_financial_answer(original, settings()))

    assert result.answer == "You spent R$ 55.90 on Netflix."
    assert result.metadata["llm_polish"] == {
        "provider": "anthropic",
        "model": "claude-haiku-4-5",
        "status": "fallback",
        "reason": "RuntimeError",
    }


def test_polisher_can_be_disabled(monkeypatch) -> None:
    original = sample_answer()

    async def fake_call(**kwargs):
        raise AssertionError("Anthropic should not be called when polish is disabled")

    monkeypatch.setattr("belvo_finance_agent.response_polisher._call_anthropic", fake_call)

    result = run(polish_financial_answer(original, settings(enable_llm_polish=False)))

    assert result.answer == "You spent R$ 55.90 on Netflix."
    assert result.metadata["llm_polish"]["status"] == "skipped"
    assert result.metadata["llm_polish"]["reason"] == "disabled"


def test_mutation_refusal_does_not_call_polisher(monkeypatch) -> None:
    class ExplodingClient:
        async def list_accounts(self, filters=None):
            raise AssertionError("Mutation requests should not call MCP tools")

        async def list_transactions(self, filters=None):
            raise AssertionError("Mutation requests should not call MCP tools")

    async def exploding_polisher(answer):
        raise AssertionError("Mutation requests should not call the LLM polisher")

    monkeypatch.setattr("belvo_finance_agent.agent.polish_financial_answer", exploding_polisher)

    result = run(FinancialSpecialistAgent(client=ExplodingClient()).answer("make a payment"))

    assert result.workflow == "read_only_refusal"
    assert result.tools_used == []
