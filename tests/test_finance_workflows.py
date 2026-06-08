from decimal import Decimal
import asyncio

from belvo_finance_agent.finance_workflows import (
    detect_recurring_expenses,
    get_balance_summary,
    get_food_spending,
    get_spending_summary,
)
from belvo_finance_agent.models import Account, AccountBalance, Transaction


class FakeClient:
    def __init__(self, accounts=None, transactions=None):
        self.accounts = accounts or []
        self.transactions = transactions or []
        self.calls = []

    async def list_accounts(self, filters=None):
        self.calls.append(("list_accounts", filters or {}))
        return self.accounts

    async def list_transactions(self, filters=None):
        self.calls.append(("list_transactions", filters or {}))
        return self.transactions


def test_balance_summary_separates_cash_and_credit_card() -> None:
    client = FakeClient(
        accounts=[
            Account(name="Itau checking", category="CHECKING_ACCOUNT", balance=AccountBalance(current=Decimal("1000"))),
            Account(name="Itau savings", category="SAVINGS_ACCOUNT", balance=AccountBalance(current=Decimal("500"))),
            Account(name="Nubank", category="CREDIT_CARD", balance=AccountBalance(current=Decimal("300"), available=Decimal("2000"))),
        ]
    )
    answer = asyncio.run(get_balance_summary(client, "balance?"))
    assert answer.metadata["cash_total"] == "1500"
    assert answer.metadata["credit_card_debt"] == "300"
    assert answer.metadata["net_position"] == "1200"
    assert "available limit was not counted" in answer.caveats[0]


def test_food_spending_filters_processed_outflows() -> None:
    client = FakeClient(
        transactions=[
            Transaction(description="IFOOD*BURGER KING", amount=Decimal("50"), value_date="2026-06-01", type="OUTFLOW", status="PROCESSED"),
            Transaction(description="IFOOD refund", amount=Decimal("20"), value_date="2026-06-01", type="INFLOW", status="PROCESSED"),
            Transaction(description="PIZZA", amount=Decimal("30"), value_date="2026-06-02", type="OUTFLOW", status="PENDING"),
        ]
    )
    answer = asyncio.run(get_food_spending(client, "food?", today=__import__("datetime").date(2026, 6, 7)))
    assert answer.metadata["total"] == "50"
    assert answer.metadata["transaction_count"] == 1


def test_spending_summary_for_today_filters_outflows() -> None:
    today = __import__("datetime").date(2026, 6, 7)
    client = FakeClient(
        transactions=[
            Transaction(description="Coffee", amount=Decimal("12.50"), value_date="2026-06-07", type="OUTFLOW", status="PROCESSED"),
            Transaction(description="Ride", amount=Decimal("30"), value_date="2026-06-07", type="OUTFLOW", status="PROCESSED"),
            Transaction(description="Refund", amount=Decimal("10"), value_date="2026-06-07", type="INFLOW", status="PROCESSED"),
            Transaction(description="Pending snack", amount=Decimal("8"), value_date="2026-06-07", type="OUTFLOW", status="PENDING"),
            Transaction(description="Yesterday", amount=Decimal("99"), value_date="2026-06-06", type="OUTFLOW", status="PROCESSED"),
        ]
    )
    answer = asyncio.run(get_spending_summary(client, "how much I spent today", today, today, "today"))
    assert answer.workflow == "spending_summary"
    assert answer.metadata["total"] == "42.50"
    assert answer.metadata["transaction_count"] == 2


def test_recurring_expense_workflow_returns_biggest_candidate() -> None:
    transactions = [
        Transaction(description="NETFLIX.COM", amount=Decimal("39.90"), value_date="2026-01-10", type="OUTFLOW", status="PROCESSED"),
        Transaction(description="NETFLIX.COM", amount=Decimal("39.90"), value_date="2026-02-10", type="OUTFLOW", status="PROCESSED"),
        Transaction(description="NETFLIX.COM", amount=Decimal("39.90"), value_date="2026-03-10", type="OUTFLOW", status="PROCESSED"),
    ]
    answer = asyncio.run(detect_recurring_expenses(FakeClient(transactions=transactions), "recurring?"))
    assert answer.workflow == "recurring_expense_detection"
    assert answer.metadata["merchant"] == "NETFLIX COM"
