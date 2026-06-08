from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
import re

from .finance_workflows import (
    detect_recurring_expenses,
    detect_salary,
    get_balance_summary,
    get_cash_flow_last_month,
    get_food_spending,
    get_large_transactions,
    get_spending_summary,
    get_transaction_query,
    refuse_mutation_request,
)
from .heuristics import (
    has_date_reference,
    is_mutation_request,
    normalize_query_text,
    normalize_text,
    resolve_natural_date_range,
)
from .mcp_client import MCPClient
from .models import FinancialAnswer
from .response_polisher import polish_financial_answer


SYSTEM_POLICY = """You are a financial specialist agent for one user's Open Finance data.

You only have read-only access to:
- get_owners
- list_accounts
- list_transactions

Never create, update, delete, mutate, simulate, or alter financial data.
Ground every answer in tool results.
Use PROCESSED transactions by default.
Use value_date for user-facing date ranges.
For spending totals, use OUTFLOW.
For income questions, use INFLOW.
Treat credit-card current balance as spending/debt, not cash.
If categories are missing, use description heuristics and disclose that.
This demo is read-only, but read-only questions about historical payments, expenses, transactions or spending are allowed.
Do not refuse just because the user says "payment", "pagamento", "gasto", "expense" or "transaction".
Refuse only when the user asks to create, update, delete, pay, transfer, simulate, charge, refund or otherwise mutate financial data.
For specific questions, answer specifically. For list questions, return the full matching list. For total questions, return totals.
Do not replace a specific answer with a generic menu of supported capabilities.
"""


@dataclass
class FinancialSpecialistAgent:
    client: MCPClient

    async def answer(self, question: str) -> FinancialAnswer:
        if is_mutation_request(question):
            return refuse_mutation_request(question)

        answer = await self._deterministic_answer(question)
        return await polish_financial_answer(answer)

    async def _deterministic_answer(self, question: str) -> FinancialAnswer:
        intent = self._classify(question)
        if intent == "balance":
            return await get_balance_summary(self.client, question)
        if intent == "food":
            return await get_food_spending(self.client, question)
        if intent == "spending":
            start, end, label = self._resolve_spending_period(question)
            return await get_spending_summary(self.client, question, start=start, end=end, period_label=label)
        if intent == "salary":
            return await detect_salary(self.client, question)
        if intent == "large_transactions":
            threshold = self._extract_threshold(question) or Decimal("500")
            return await get_large_transactions(self.client, question, threshold=threshold)
        if intent == "transaction_query":
            return await get_transaction_query(self.client, question)
        if intent == "recurring":
            return await detect_recurring_expenses(self.client, question)
        if intent == "cash_flow":
            return await get_cash_flow_last_month(self.client, question)

        return FinancialAnswer(
            question=question,
            answer=(
                "I can help with balances, food spending, salary detection, large transactions, "
                "recurring expenses and last-month money in vs money out. Try one of those questions."
            ),
            workflow="unsupported_question",
            tools_used=[],
            filters={},
            caveats=["The scoped demo intentionally handles a small set of representative financial workflows."],
        )

    def _classify(self, question: str) -> str:
        text = normalize_text(question)
        query_text = normalize_query_text(question)
        if any(term in text for term in ["BALANCE", "SALDO", "NET POSITION", "CURRENT BALANCE"]):
            return "balance"
        if any(term in text for term in ["FOOD", "GROCER", "RESTAUR", "IFOOD", "COMIDA", "ALIMENT"]):
            return "food"
        if any(term in text for term in ["RECURRING", "RECORREN"]) and not any(
            term in text for term in ["SUBSCRIPTION", "ASSINATURA"]
        ):
            return "recurring"
        if self._is_transaction_history_query(query_text):
            return "transaction_query"
        if any(term in text for term in ["SPENT", "SPEND", "SPENDING", "EXPENSE", "EXPENSES", "GASTEI", "GASTO", "GASTOS"]):
            return "spending"
        if any(term in text for term in ["SALARY", "SALARIO", "PAYROLL", "FOLHA", "ORDENADO"]):
            return "salary"
        if any(term in text for term in ["OVER R", "OVER BRL", "LARG", "ACIMA", "MAIOR", "MAIS DE"]):
            return "large_transactions"
        if ("CAME IN" in text and "WENT OUT" in text) or ("MONEY IN" in text and "MONEY OUT" in text):
            return "cash_flow"
        if any(term in text for term in ["INFLOW VS OUTFLOW", "ENTROU", "SAIU"]):
            return "cash_flow"
        return "unsupported"

    def _is_transaction_history_query(self, text: str) -> bool:
        if any(
            term in text
            for term in [
                "GROUP BY ACCOUNT",
                "GROUPED BY ACCOUNT",
                "GROUP BY CATEGORY",
                "GROUPED BY CATEGORY",
                "PER ACCOUNT",
                "PER CATEGORY",
                "BY ACCOUNT",
                "BY CATEGORY",
                "POR CONTA",
                "POR BANCO",
                "POR INSTITUICAO",
                "POR CATEGORIA",
            ]
        ):
            return True

        financial_noun = any(
            term in text
            for term in [
                "PIX",
                "NETFLIX",
                "SPOTIFY",
                "SUBSCRIPTION",
                "SUBSCRIPTIONS",
                "ASSINATURA",
                "ASSINATURAS",
                "CARD",
                "CREDIT CARD",
                "CARTAO",
                "NUBANK",
                "ITAU",
                "CHECKING",
                "CURRENT ACCOUNT",
                "CONTA CORRENTE",
                "SAVINGS",
                "POUPANCA",
                "PAYMENT",
                "PAYMENTS",
                "PAGAMENTO",
                "PAGAMENTOS",
                "PAID",
                "PAGO",
                "EXPENSE",
                "EXPENSES",
                "GRAPH",
                "CHART",
                "PLOT",
                "GRAFICO",
                "CATEGORIA",
                "CATEGORY",
                "GASTO",
                "GASTOS",
                "DESPESA",
                "DESPESAS",
                "TRANSACTION",
                "TRANSACTIONS",
                "TRANSACAO",
                "TRANSACOES",
            ]
        )
        query_shape = any(
            term in text
            for term in [
                "WHEN",
                "LAST",
                "LATEST",
                "ULTIMO",
                "ULTIMA",
                "MAIS RECENTE",
                "BIGGEST",
                "MAIOR",
                "SMALLEST",
                "MENOR",
                "LOWEST",
                "LEAST EXPENSIVE",
                "SHOW",
                "LIST",
                "ALL",
                "WHOLE",
                "TOTAL",
                "SUM",
                "HOW MUCH",
                "QUANTO",
                "WHEN",
                "QUANDO",
                "SEND",
                "SENT",
                "RECEIVE",
                "RECEIVED",
                "ENVIEI",
                "RECEBI",
                "LISTE",
                "MOSTRE",
                "TODOS",
                "TODAS",
                "SPLIT",
                "BREAK DOWN",
                "GROUP BY ACCOUNT",
                "GROUPED BY ACCOUNT",
                "PER ACCOUNT",
                "PER CATEGORY",
                "BY ACCOUNT",
                "BY CATEGORY",
                "POR CONTA",
                "POR BANCO",
                "POR INSTITUICAO",
                "POR CATEGORIA",
                "OVER R",
                "ABOVE",
                "ACIMA",
                "MAIS DE",
                "BELOW",
                "UNDER",
                "LESS THAN",
                "ABAIXO",
                "MENOR QUE",
            ]
        )
        return financial_noun and (query_shape or has_date_reference(text))

    def _extract_threshold(self, question: str) -> Decimal | None:
        normalized = question.replace(",", ".")
        match = re.search(r"(?:R\$|BRL)?\s*(\d+(?:\.\d+)?)", normalized, flags=re.IGNORECASE)
        if not match:
            return None
        return Decimal(match.group(1))

    def _resolve_spending_period(self, question: str) -> tuple[date, date, str]:
        return resolve_natural_date_range(question)

    def _resolve_transaction_period(self, question: str) -> tuple[date | None, date | None, str | None]:
        if not has_date_reference(question):
            return None, None, None
        return resolve_natural_date_range(question)

    def _transaction_query_mode(self, question: str) -> str:
        text = normalize_query_text(question)
        if any(term in text for term in ["SHOW", "LIST", "ALL", "WHOLE", "LISTE", "MOSTRE", "TODOS", "TODAS", "OVER R", "ABOVE", "ACIMA"]):
            return "list"
        if any(term in text for term in ["LAST", "ULTIMO", "ULTIMA", "WHEN", "DATA"]):
            return "last"
        if any(term in text for term in ["BIGGEST", "MAIOR"]):
            return "biggest"
        if any(term in text for term in ["SMALLEST", "MENOR"]):
            return "smallest"
        return "total"

    def _transaction_type_for_query(self, question: str) -> str | None:
        text = normalize_query_text(question)
        if any(term in text for term in ["TRANSACTION", "TRANSACTIONS", "TRANSACAO", "TRANSACOES"]):
            if not any(term in text for term in ["EXPENSE", "EXPENSES", "GASTO", "GASTOS", "DESPESA", "DESPESAS", "PAYMENT", "PAGAMENTO"]):
                return None
        return "OUTFLOW"


def build_agent() -> FinancialSpecialistAgent:
    return FinancialSpecialistAgent(client=MCPClient())
