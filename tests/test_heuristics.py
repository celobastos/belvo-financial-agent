from decimal import Decimal
from datetime import date

from belvo_finance_agent.heuristics import (
    detect_recurring_candidates,
    format_brl,
    is_food_transaction,
    is_mutation_request,
    is_salary_transaction,
    normalize_text,
    resolve_natural_date_range,
)
from belvo_finance_agent.models import Transaction


def tx(description: str, amount: str = "10", value_date: str = "2026-05-01") -> Transaction:
    return Transaction(
        description=description,
        amount=Decimal(amount),
        value_date=value_date,
        type="OUTFLOW",
        status="PROCESSED",
    )


def test_normalize_text_removes_accents_and_noise() -> None:
    assert normalize_text("SALÁRIO mês 05/2026") == "SALARIO MES"


def test_food_keyword_classification() -> None:
    assert is_food_transaction(tx("IFOOD*BURGER KING"))


def test_salary_keyword_classification() -> None:
    transaction = Transaction(description="SALARIO ACME LTDA", amount=Decimal("5000"), type="INFLOW", status="PROCESSED")
    assert is_salary_transaction(transaction)


def test_brl_formatting() -> None:
    assert format_brl(Decimal("1234.5")) == "R$ 1.234,50"


def test_recurring_candidate_detection() -> None:
    transactions = [
        tx("NETFLIX.COM", "39.90", "2026-01-10"),
        tx("NETFLIX.COM", "39.90", "2026-02-10"),
        tx("NETFLIX.COM", "39.90", "2026-03-10"),
        tx("ONE OFF STORE", "900", "2026-03-12"),
    ]
    candidates = detect_recurring_candidates(transactions)
    assert candidates
    assert candidates[0].name == "NETFLIX COM"


def test_resolve_natural_date_range_common_phrases() -> None:
    today = date(2026, 6, 7)
    assert resolve_natural_date_range("how much did I spend today", today) == (today, today, "today")
    assert resolve_natural_date_range("how much did I spend yesterday", today)[0] == date(2026, 6, 6)
    assert resolve_natural_date_range("how much did I spend last week", today)[:2] == (date(2026, 5, 25), date(2026, 5, 31))
    assert resolve_natural_date_range("how much did I spend in May 2026", today)[:2] == (date(2026, 5, 1), date(2026, 5, 31))
    assert resolve_natural_date_range("how much did I spend from June 1 to June 5", today)[:2] == (date(2026, 6, 1), date(2026, 6, 5))
    assert resolve_natural_date_range("how much did I spend since 2026-06-01", today)[:2] == (date(2026, 6, 1), today)
    assert resolve_natural_date_range("quanto gastei nos ultimos 90 dias", today)[:2] == (date(2026, 3, 9), today)


def test_read_only_financial_nouns_are_not_mutation_requests() -> None:
    allowed = [
        "when I last did a payment",
        "what was my biggest payment",
        "qual foi meu ultimo pagamento",
        "qual foi meu maior gasto",
        "liste meus pagamentos",
    ]
    assert all(not is_mutation_request(question) for question in allowed)


def test_true_mutations_are_refused() -> None:
    refused = [
        "make a payment",
        "pay this bill",
        "create a transaction",
        "delete this transaction",
        "update my balance",
        "transfer money",
        "faca um pagamento",
        "pague essa conta",
        "crie uma transacao",
        "apague essa transacao",
        "transfira dinheiro",
    ]
    assert all(is_mutation_request(question) for question in refused)
