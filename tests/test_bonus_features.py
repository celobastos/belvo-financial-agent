import asyncio
from decimal import Decimal

from belvo_finance_agent.agent import FinancialSpecialistAgent
from belvo_finance_agent.finance_workflows import parse_transaction_intent, refuse_mutation_request
from belvo_finance_agent.models import Account, Institution, Transaction
from belvo_finance_agent.schema_context import SkillContextLoader, loaded_skill_names
from belvo_finance_agent.streaming import enable_streaming, stream_text


def answer(question: str):
    return asyncio.run(FinancialSpecialistAgent(client=BonusClient()).answer(question))


class BonusClient:
    def __init__(self):
        self.accounts = [
            Account(id="chk", name="Conta Corrente Itau", category="CHECKING_ACCOUNT", institution=Institution(name="Itau")),
            Account(id="nub", name="Nubank Mastercard", category="CREDIT_CARD", institution=Institution(name="Nubank")),
        ]
        self.transactions = [
            Transaction(description="ALUGUEL APARTAMENTO", amount=Decimal("2300"), value_date="2026-05-01", type="OUTFLOW", status="PROCESSED", account=self.accounts[0]),
            Transaction(description="NETFLIX.COM", amount=Decimal("55.90"), value_date="2026-05-09", type="OUTFLOW", status="PROCESSED", account=self.accounts[1], category="Online Platforms & Leisure", subcategory="Streaming"),
            Transaction(description="SPOTIFY BRASIL", amount=Decimal("21.90"), value_date="2026-05-10", type="OUTFLOW", status="PROCESSED", account=self.accounts[1], category="Online Platforms & Leisure", subcategory="Streaming"),
            Transaction(description="ICLOUD.COM/BILL", amount=Decimal("9.90"), value_date="2026-05-11", type="OUTFLOW", status="PROCESSED", account=self.accounts[1], category="Online Platforms & Leisure", subcategory="Cloud Storage"),
        ]

    async def list_accounts(self, filters=None):
        return self.accounts

    async def list_transactions(self, filters=None):
        result = self.transactions
        filters = filters or {}
        if filters.get("status"):
            result = [tx for tx in result if tx.status == filters["status"]]
        if filters.get("type"):
            result = [tx for tx in result if tx.type == filters["type"]]
        return result


def test_transaction_query_loads_transaction_skills() -> None:
    intent = parse_transaction_intent("show me all PIX transactions")
    skills = SkillContextLoader().load_for_transaction_intent(intent)
    names = loaded_skill_names(skills)
    assert "transactions_schema" in names
    assert "filtering_rules" in names


def test_balance_query_loads_balance_skills() -> None:
    names = SkillContextLoader().names_for_workflow("balance_summary")
    assert "accounts_schema" in names
    assert "balances_semantics" in names


def test_mutation_request_loads_safety_skill() -> None:
    result = refuse_mutation_request("make a payment")
    assert "safety_read_only" in result.metadata["loaded_skills"]


def test_streaming_chunks_reconstruct_answer() -> None:
    text = "I found R$ 100.00 across 2 transactions."
    chunks = list(stream_text(text, delay=0, chunk_size=7))
    assert "".join(chunks) == text


def test_eval_mode_disables_streaming() -> None:
    assert enable_streaming(eval_mode=True, configured=True) is False
    assert enable_streaming(eval_mode=False, configured=True) is True


def test_group_by_account_returns_chart_spec() -> None:
    result = answer("show me a graph of my expenses by account")
    assert result.chart is not None
    assert result.chart.chart_type == "bar"
    assert "account" in result.chart.title.lower()


def test_subscription_total_returns_chart_spec() -> None:
    result = answer("how much did I spend on subscriptions?")
    assert result.chart is not None
    assert result.chart.chart_type == "bar"
    assert "subscription" in result.chart.title.lower()


def test_single_transaction_does_not_return_chart() -> None:
    result = answer("what was my smallest expense?")
    assert result.chart is None
