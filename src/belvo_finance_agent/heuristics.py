from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from statistics import mean

from .models import Transaction, TransactionEvidence


FOOD_SUBCATEGORIES = {
    "Delivery",
    "Groceries",
    "Restaurants",
    "Bakery & Coffee",
    "Bars & Nightclubs",
    "Convenience Store",
}

FOOD_KEYWORDS = {
    "IFOOD",
    "RESTAURANTE",
    "RESTAURANT",
    "BURGER",
    "PIZZA",
    "PADARIA",
    "BAKERY",
    "CAFE",
    "COFFEE",
    "MERCADO",
    "SUPERMERCADO",
    "GROCERY",
    "GROCERIES",
    "HORTIFRUTI",
    "DELIVERY",
}

SALARY_KEYWORDS = {"SALARIO", "PAYROLL", "FOLHA", "ORDENADO", "HOLERITE"}
MUTATION_PHRASES = {
    "CREATE",
    "ADD",
    "INSERT",
    "UPDATE",
    "EDIT",
    "DELETE",
    "REMOVE",
    "PAY",
    "MAKE A PAYMENT",
    "SEND MONEY",
    "TRANSFER",
    "SIMULATE",
    "CHARGE",
    "CANCEL",
    "REFUND",
    "CRIAR",
    "CRIE",
    "ADICIONAR",
    "ADICIONE",
    "INSERIR",
    "INSIRA",
    "ATUALIZAR",
    "ATUALIZE",
    "EDITAR",
    "EDITE",
    "DELETAR",
    "DELETE",
    "APAGAR",
    "APAGUE",
    "REMOVER",
    "REMOVA",
    "PAGAR",
    "PAGUE",
    "FACA UM PAGAMENTO",
    "FAZER PAGAMENTO",
    "ENVIAR DINHEIRO",
    "ENVIE DINHEIRO",
    "TRANSFERIR",
    "TRANSFIRA",
    "SIMULAR",
    "SIMULE",
    "COBRAR",
    "COBRE",
    "CANCELAR",
    "CANCELE",
    "ESTORNAR",
    "ESTORNE",
}
MUTATION_TARGET_WORDS = {
    "TRANSACTION",
    "TRANSACTIONS",
    "ACCOUNT",
    "ACCOUNTS",
    "BALANCE",
    "BALANCES",
    "OWNER",
    "OWNERS",
    "BILL",
    "CARD",
    "PAYMENT",
    "MONEY",
    "TRANSACAO",
    "TRANSACOES",
    "CONTA",
    "CONTAS",
    "SALDO",
    "PAGAMENTO",
    "DINHEIRO",
    "CARTAO",
    "FATURA",
}
READ_ONLY_QUERY_MARKERS = {
    "WHEN",
    "WHAT",
    "WHICH",
    "SHOW",
    "LIST",
    "LAST",
    "BIGGEST",
    "SMALLEST",
    "HOW MUCH",
    "DATE",
    "QUAL",
    "QUANDO",
    "LISTE",
    "MOSTRE",
    "ULTIMO",
    "ULTIMA",
    "MAIOR",
    "MENOR",
    "DATA",
    "QUANTO",
    "TODOS",
    "TODAS",
}

RECURRING_EXCLUDE = {
    "PAGAMENTO FATURA",
    "TRANSFERENCIA",
    "PIX ENVIADO",
    "TED",
    "DOC",
    "BOLETO",
}

MONTHS = {
    "JANUARY": 1,
    "JAN": 1,
    "JANEIRO": 1,
    "FEBRUARY": 2,
    "FEB": 2,
    "FEVEREIRO": 2,
    "FEV": 2,
    "MARCH": 3,
    "MAR": 3,
    "MARCO": 3,
    "APRIL": 4,
    "APR": 4,
    "ABRIL": 4,
    "ABR": 4,
    "MAY": 5,
    "MAIO": 5,
    "JUNE": 6,
    "JUN": 6,
    "JUNHO": 6,
    "JULY": 7,
    "JUL": 7,
    "JULHO": 7,
    "AUGUST": 8,
    "AUG": 8,
    "AGOSTO": 8,
    "AGO": 8,
    "SEPTEMBER": 9,
    "SEPT": 9,
    "SEP": 9,
    "SETEMBRO": 9,
    "SET": 9,
    "OCTOBER": 10,
    "OCT": 10,
    "OUTUBRO": 10,
    "OUT": 10,
    "NOVEMBER": 11,
    "NOV": 11,
    "NOVEMBRO": 11,
    "DECEMBER": 12,
    "DEC": 12,
    "DEZEMBRO": 12,
    "DEZ": 12,
}


def normalize_text(value: str | None) -> str:
    if not value:
        return ""
    normalized = unicodedata.normalize("NFKD", value)
    ascii_text = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    ascii_text = ascii_text.upper()
    ascii_text = re.sub(r"[^A-Z0-9\s*&.-]", " ", ascii_text)
    ascii_text = re.sub(r"\b\d{2,}\b", " ", ascii_text)
    ascii_text = re.sub(r"\s+", " ", ascii_text).strip()
    return ascii_text


def normalize_query_text(value: str | None) -> str:
    if not value:
        return ""
    normalized = unicodedata.normalize("NFKD", value)
    ascii_text = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    ascii_text = ascii_text.upper()
    ascii_text = re.sub(r"[^A-Z0-9\s*&./-]", " ", ascii_text)
    ascii_text = re.sub(r"\s+", " ", ascii_text).strip()
    return ascii_text


def money(value: Decimal | int | float | str | None) -> Decimal:
    if value is None:
        return Decimal("0")
    return Decimal(str(value))


def format_brl(value: Decimal | int | float | str | None) -> str:
    amount = money(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    sign = "-" if amount < 0 else ""
    amount = abs(amount)
    whole, cents = f"{amount:.2f}".split(".")
    parts = []
    while whole:
        parts.append(whole[-3:])
        whole = whole[:-3]
    formatted = ".".join(reversed(parts))
    return f"{sign}R$ {formatted},{cents}"


def parse_iso_date(value: str | None) -> date | None:
    if not value:
        return None
    return date.fromisoformat(value[:10])


def last_n_days(today: date, days: int) -> tuple[date, date]:
    return today - timedelta(days=days), today


def current_month(today: date) -> tuple[date, date]:
    return today.replace(day=1), today


def previous_month(today: date) -> tuple[date, date]:
    first_this_month = today.replace(day=1)
    end = first_this_month - timedelta(days=1)
    start = end.replace(day=1)
    return start, end


def month_range(year: int, month: int) -> tuple[date, date]:
    start = date(year, month, 1)
    if month == 12:
        end = date(year, 12, 31)
    else:
        end = date(year, month + 1, 1) - timedelta(days=1)
    return start, end


def this_week(today: date) -> tuple[date, date]:
    start = today - timedelta(days=today.weekday())
    return start, today


def last_week(today: date) -> tuple[date, date]:
    start_this_week = today - timedelta(days=today.weekday())
    start = start_this_week - timedelta(days=7)
    end = start_this_week - timedelta(days=1)
    return start, end


def resolve_natural_date_range(question: str, today: date | None = None) -> tuple[date, date, str]:
    today = today or date.today()
    text = normalize_query_text(question)

    iso_dates = [date.fromisoformat(match) for match in re.findall(r"\b\d{4}-\d{2}-\d{2}\b", question)]
    if len(iso_dates) >= 2:
        start, end = sorted(iso_dates[:2])
        return start, end, f"from {start} to {end}"
    if len(iso_dates) == 1:
        only = iso_dates[0]
        if any(term in text for term in ["SINCE", "DESDE"]):
            return only, today, f"from {only} to {today}"
        return only, only, f"on {only}"

    month_day_dates: list[date] = []
    for month_name, month in MONTHS.items():
        for match in re.finditer(rf"\b{month_name}\s+(\d{{1,2}})(?:\s+(20\d{{2}}))?\b", text):
            day = int(match.group(1))
            year = int(match.group(2)) if match.group(2) else today.year
            try:
                month_day_dates.append(date(year, month, day))
            except ValueError:
                continue
        for match in re.finditer(
            rf"\b(?:(?:ON|EM)\s+)?(\d{{1,2}})\s+(?:OF|DE)\s+{month_name}(?:\s+(20\d{{2}}))?\b",
            text,
        ):
            day = int(match.group(1))
            year = int(match.group(2)) if match.group(2) else today.year
            try:
                month_day_dates.append(date(year, month, day))
            except ValueError:
                continue
    if len(month_day_dates) >= 2:
        start, end = sorted(month_day_dates[:2])
        return start, end, f"from {start} to {end}"
    if len(month_day_dates) == 1:
        only = month_day_dates[0]
        if any(term in text for term in ["SINCE", "DESDE"]):
            return only, today, f"from {only} to {today}"
        return only, only, f"on {only}"

    if "YESTERDAY" in text or "ONTEM" in text:
        target = today - timedelta(days=1)
        return target, target, "yesterday"
    if "TODAY" in text or "HOJE" in text:
        return today, today, "today"
    if "LAST WEEK" in text or "SEMANA PASSADA" in text:
        start, end = last_week(today)
        return start, end, f"from {start} to {end}"
    if "THIS WEEK" in text or "ESTA SEMANA" in text or "ESSA SEMANA" in text:
        start, end = this_week(today)
        return start, end, f"from {start} to {end}"
    if "LAST MONTH" in text or "MES PASSADO" in text:
        start, end = previous_month(today)
        return start, end, f"from {start} to {end}"
    if "THIS MONTH" in text or "ESSE MES" in text or "ESTE MES" in text:
        start, end = current_month(today)
        return start, end, f"from {start} to {end}"

    relative_match = re.search(
        r"(?:LAST|PAST|ULTIMOS|ULTIMAS)\s+(\d+)\s+(DAY|DAYS|DIA|DIAS|WEEK|WEEKS|SEMANA|SEMANAS|MONTH|MONTHS|MES|MESES)",
        text,
    )
    if relative_match:
        count = int(relative_match.group(1))
        unit = relative_match.group(2)
        if unit.startswith(("WEEK", "SEMANA")):
            days = count * 7
        elif unit.startswith(("MONTH", "MES")):
            days = count * 30
        else:
            days = count
        start = today - timedelta(days=days)
        return start, today, f"from {start} to {today}"

    for month_name, month in MONTHS.items():
        if re.search(rf"\b{month_name}\b", text):
            year_match = re.search(r"\b(20\d{2})\b", text)
            year = int(year_match.group(1)) if year_match else today.year
            start, end = month_range(year, month)
            return start, end, f"from {start} to {end}"

    return today, today, "today"


def has_date_reference(question: str) -> bool:
    text = normalize_query_text(question)
    if re.search(r"\b\d{4}-\d{2}-\d{2}\b", question):
        return True
    if any(
        term in text
        for term in [
            "TODAY",
            "HOJE",
            "YESTERDAY",
            "ONTEM",
            "WEEK",
            "SEMANA",
            "MONTH",
            "MES",
            "DAYS",
            "DIAS",
            "SINCE",
            "DESDE",
        ]
    ):
        return True
    return any(re.search(rf"\b{month_name}\b", text) for month_name in MONTHS)


def is_food_transaction(transaction: Transaction) -> bool:
    category = transaction.category or ""
    subcategory = transaction.subcategory or ""
    description = normalize_text(transaction.description)
    if category == "Food & Groceries":
        return True
    if subcategory in FOOD_SUBCATEGORIES:
        return True
    return any(keyword in description for keyword in FOOD_KEYWORDS)


def is_salary_transaction(transaction: Transaction) -> bool:
    category = transaction.category or ""
    subcategory = transaction.subcategory or ""
    description = normalize_text(transaction.description)
    if subcategory == "Salary":
        return True
    if category == "Income & Payments" and any(keyword in description for keyword in SALARY_KEYWORDS):
        return True
    return any(keyword in description for keyword in SALARY_KEYWORDS)


def is_mutation_request(question: str) -> bool:
    normalized = normalize_text(question)
    words = set(normalized.split())

    if any(re.search(rf"\b{re.escape(marker)}\b", normalized) for marker in READ_ONLY_QUERY_MARKERS):
        return False

    for phrase in MUTATION_PHRASES:
        if re.search(rf"\b{re.escape(phrase)}\b", normalized):
            if phrase in {"PAY", "PAGAR", "PAGUE", "TRANSFER", "TRANSFERIR", "TRANSFIRA", "CHARGE", "COBRAR", "COBRE"}:
                return True
            return bool(words & MUTATION_TARGET_WORDS)
    return False


def evidence_from_transaction(transaction: Transaction) -> TransactionEvidence:
    return TransactionEvidence(
        date=transaction.value_date,
        amount=transaction.amount,
        type=transaction.type,
        account=transaction.account_name,
        description=transaction.description,
        category=transaction.category,
        subcategory=transaction.subcategory,
    )


def normalize_merchant(transaction: Transaction) -> str:
    merchant_name = None
    if transaction.merchant:
        merchant_name = transaction.merchant.get("merchant_name")
    description = normalize_text(merchant_name or transaction.description)
    description = re.sub(r"\b(PARCELA|PARC|COMPRA|CARTAO|DEBITO|CREDITO)\b", " ", description)
    description = re.sub(r"[*.-]+", " ", description)
    description = re.sub(r"\s+", " ", description).strip()
    return description


@dataclass
class RecurringCandidate:
    name: str
    transactions: list[Transaction]
    average_amount: Decimal
    cadence: str
    confidence: str


def detect_recurring_candidates(transactions: list[Transaction]) -> list[RecurringCandidate]:
    groups: dict[str, list[Transaction]] = defaultdict(list)
    for transaction in transactions:
        name = normalize_merchant(transaction)
        if not name or any(blocked in name for blocked in RECURRING_EXCLUDE):
            continue
        groups[name].append(transaction)

    candidates: list[RecurringCandidate] = []
    for name, txs in groups.items():
        dated = sorted([tx for tx in txs if parse_iso_date(tx.value_date)], key=lambda tx: tx.value_date or "")
        if len(dated) < 3:
            continue

        amounts = [money(tx.amount) for tx in dated]
        average_amount = sum(amounts, Decimal("0")) / Decimal(len(amounts))
        amount_variance = max(abs(amount - average_amount) for amount in amounts)
        stable_amount = amount_variance <= max(Decimal("15"), average_amount * Decimal("0.15"))

        dates = [parse_iso_date(tx.value_date) for tx in dated]
        gaps = [(dates[i] - dates[i - 1]).days for i in range(1, len(dates)) if dates[i] and dates[i - 1]]
        avg_gap = mean(gaps) if gaps else 0
        regular_gap = any(
            target - tolerance <= avg_gap <= target + tolerance
            for target, tolerance in [(7, 3), (14, 4), (30, 8)]
        )
        if not (stable_amount or regular_gap):
            continue

        if 4 <= avg_gap <= 10:
            cadence = "weekly"
        elif 10 < avg_gap <= 20:
            cadence = "biweekly"
        elif 20 < avg_gap <= 40:
            cadence = "monthly"
        else:
            cadence = "recurring"

        confidence = "high" if stable_amount and regular_gap else "medium"
        candidates.append(RecurringCandidate(name, dated, average_amount, cadence, confidence))

    return sorted(candidates, key=lambda item: item.average_amount, reverse=True)
