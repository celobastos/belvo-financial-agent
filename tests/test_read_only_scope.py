import asyncio

from belvo_finance_agent.agent import FinancialSpecialistAgent
from belvo_finance_agent.finance_workflows import refuse_mutation_request


class ExplodingClient:
    async def list_accounts(self, filters=None):
        raise AssertionError("should not call tools for mutation requests")

    async def list_transactions(self, filters=None):
        raise AssertionError("should not call tools for mutation requests")


class SpendingClient:
    async def list_accounts(self, filters=None):
        return []

    async def list_transactions(self, filters=None):
        from decimal import Decimal
        from belvo_finance_agent.models import Transaction

        value_date = (filters or {}).get("value_date__gte", "2026-06-07")
        return [
            Transaction(description="Lunch", amount=Decimal("40"), value_date=value_date, type="OUTFLOW", status="PROCESSED")
        ]


class TransactionHistoryClient:
    async def list_accounts(self, filters=None):
        return []

    async def list_transactions(self, filters=None):
        from decimal import Decimal
        from belvo_finance_agent.models import Account, Transaction

        rows = [
            Transaction(description="ALUGUEL APARTAMENTO", amount=Decimal("2300"), value_date="2026-05-01", type="OUTFLOW", status="PROCESSED", account=Account(name="Conta Corrente")),
            Transaction(description="MERCADO", amount=Decimal("180"), value_date="2026-05-10", type="OUTFLOW", status="PROCESSED", account=Account(name="Nubank")),
            Transaction(description="CAFE", amount=Decimal("20"), value_date="2026-06-06", type="OUTFLOW", status="PROCESSED", account=Account(name="Nubank")),
            Transaction(description="SALARIO", amount=Decimal("8000"), value_date="2026-05-05", type="INFLOW", status="PROCESSED", account=Account(name="Conta Corrente")),
        ]
        if not filters:
            return rows
        result = rows
        if filters.get("status"):
            result = [tx for tx in result if tx.status == filters["status"]]
        if filters.get("type"):
            result = [tx for tx in result if tx.type == filters["type"]]
        if filters.get("value_date__gte"):
            result = [tx for tx in result if tx.value_date >= filters["value_date__gte"]]
        if filters.get("value_date__lte"):
            result = [tx for tx in result if tx.value_date <= filters["value_date__lte"]]
        if filters.get("amount__gt"):
            result = [tx for tx in result if tx.amount > Decimal(str(filters["amount__gt"]))]
        return result


def test_refusal_uses_no_tools() -> None:
    answer = refuse_mutation_request("Create a new transaction for R$ 100")
    assert answer.workflow == "read_only_refusal"
    assert answer.tools_used == []


def test_agent_refuses_mutation_without_tool_call() -> None:
    agent = FinancialSpecialistAgent(client=ExplodingClient())
    answer = asyncio.run(agent.answer("Create a new transaction for R$ 100"))
    assert answer.workflow == "read_only_refusal"
    assert answer.tools_used == []


def test_agent_routes_plain_spending_question() -> None:
    agent = FinancialSpecialistAgent(client=SpendingClient())
    answer = asyncio.run(agent.answer("how much I spent today"))
    assert answer.workflow == "spending_summary"
    assert answer.tools_used == ["list_transactions"]


def test_agent_routes_spending_question_with_other_period() -> None:
    agent = FinancialSpecialistAgent(client=SpendingClient())
    answer = asyncio.run(agent.answer("how much did I spend last week"))
    assert answer.workflow == "spending_summary"
    assert answer.filters["type"] == "OUTFLOW"
    assert answer.filters["status"] == "PROCESSED"


def test_agent_routes_recurring_expense_before_generic_expense() -> None:
    agent = FinancialSpecialistAgent(client=SpendingClient())
    answer = asyncio.run(agent.answer("what's my biggest recurring expense?"))
    assert answer.workflow == "recurring_expense_detection"


def test_agent_allows_last_payment_as_read_only_query() -> None:
    agent = FinancialSpecialistAgent(client=TransactionHistoryClient())
    answer = asyncio.run(agent.answer("when I last did a payment"))
    assert answer.workflow == "transaction_query_last"
    assert "Your last processed outflow was on 2026-06-06" in answer.answer


def test_agent_answers_biggest_expense_in_may_as_specific_transaction() -> None:
    agent = FinancialSpecialistAgent(client=TransactionHistoryClient())
    answer = asyncio.run(agent.answer("what was my biggest expense on May"))
    assert answer.workflow == "transaction_query_biggest"
    assert answer.metadata["date_range"] == ["2026-05-01", "2026-05-31"]
    assert "R$ 2.300,00" in answer.answer
    assert "ALUGUEL APARTAMENTO" in answer.answer


def test_agent_lists_all_expenses_in_may() -> None:
    agent = FinancialSpecialistAgent(client=TransactionHistoryClient())
    answer = asyncio.run(agent.answer("show me all my expenses in May"))
    assert answer.workflow == "transaction_query_list"
    assert answer.metadata["matches"] == 2
    assert "ALUGUEL APARTAMENTO" in answer.answer
    assert "MERCADO" in answer.answer


def test_agent_routes_show_transactions_over_as_list_not_last() -> None:
    agent = FinancialSpecialistAgent(client=TransactionHistoryClient())
    answer = asyncio.run(agent.answer("show me transactions over R$ 500 in the last 90 days"))
    assert answer.workflow == "transaction_query_list"
    assert answer.filters["amount__gt"] == 500.0
    assert "SALARIO" in answer.answer
