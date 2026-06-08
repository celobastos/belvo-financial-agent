from __future__ import annotations

from dataclasses import asdict
from datetime import date
from decimal import Decimal
import re
from typing import Protocol

from .charts import account_spending_chart, category_spending_chart, subscription_breakdown_chart
from .heuristics import (
    current_month,
    detect_recurring_candidates,
    evidence_from_transaction,
    format_brl,
    has_date_reference,
    is_food_transaction,
    is_salary_transaction,
    last_n_days,
    money,
    normalize_query_text,
    normalize_text,
    parse_iso_date,
    previous_month,
    resolve_natural_date_range,
)
from .models import Account, AccountFilter, DateRange, FinancialAnswer, Transaction, TransactionQueryIntent
from .schema_context import SkillContextLoader, compact_context_block, loaded_skill_names


SKILL_LOADER = SkillContextLoader()


class FinanceDataClient(Protocol):
    async def list_accounts(self, filters: dict | None = None) -> list[Account]: ...

    async def list_transactions(self, filters: dict | None = None) -> list[Transaction]: ...


def _with_skill_context(answer: FinancialAnswer, workflow: str | None = None, intent: TransactionQueryIntent | None = None) -> FinancialAnswer:
    contexts = SKILL_LOADER.load_for_transaction_intent(intent) if intent else SKILL_LOADER.load_for_workflow(workflow or answer.workflow)
    answer.metadata = {
        **(answer.metadata or {}),
        "loaded_skills": loaded_skill_names(contexts),
        "skill_context": compact_context_block(contexts),
    }
    return answer


def _date_filter(start: date, end: date, **extra: object) -> dict[str, object]:
    return {"value_date__gte": start.isoformat(), "value_date__lte": end.isoformat(), **extra}


def _in_date_range(transaction: Transaction, start: date, end: date) -> bool:
    value_date = parse_iso_date(transaction.value_date)
    return bool(value_date and start <= value_date <= end)


def _processed(transaction: Transaction) -> bool:
    return (transaction.status or "").upper() == "PROCESSED"


def _table_for_transactions(transactions: list[Transaction]) -> str:
    rows = [
        "| Date | Amount | Type | Account | Description | Category |",
        "|---|---:|---|---|---|---|",
    ]
    rows.extend(
        "| {date} | {amount} | {type} | {account} | {desc} | {category} |".format(
            date=tx.value_date or "",
            amount=format_brl(tx.amount),
            type=tx.type or "",
            account=tx.account_name,
            desc=(tx.description or "").replace("|", "/"),
            category="/".join(part for part in [tx.category, tx.subcategory] if part),
        )
        for tx in transactions
    )
    return "\n".join(rows)


def _table_for_subscription_transactions(transactions: list[Transaction]) -> str:
    rows = [
        "| Date | Amount | Account | Description | Category |",
        "|---|---:|---|---|---|",
    ]
    rows.extend(
        "| {date} | {amount} | {account} | {desc} | {category} |".format(
            date=tx.value_date or "",
            amount=format_brl(tx.amount),
            account=tx.account_name,
            desc=(tx.description or "").replace("|", "/"),
            category="/".join(part for part in [tx.category, tx.subcategory] if part),
        )
        for tx in transactions
    )
    return "\n".join(rows)


def _percentage(part: Decimal, total: Decimal) -> str:
    if total == 0:
        return "0.0%"
    return f"{(part / total * Decimal('100')).quantize(Decimal('0.1'))}%"


def _display_institution(account: Account | None, fallback_name: str = "") -> str:
    if account:
        institution = account.institution
        if hasattr(institution, "name") and institution.name:
            return institution.name
        if isinstance(institution, dict) and institution.get("name"):
            return str(institution["name"])
        fallback_name = fallback_name or account.display_name
    text = normalize_query_text(fallback_name)
    if "NUBANK" in text:
        return "Nubank"
    if "ITAU" in text:
        return "Itau"
    return "Unknown"


def _subscription_service_name(transaction: Transaction) -> str:
    text = normalize_query_text(transaction.description)
    service_patterns = [
        "NETFLIX.COM",
        "SPOTIFY BRASIL",
        "DISNEY PLUS BR",
        "AMAZON PRIME BR",
        "ICLOUD.COM/BILL",
        "VIVO FIBRA INTERNET",
        "CLARO TELECOM MOVEL",
    ]
    for service in service_patterns:
        if normalize_query_text(service) in text:
            return service
    description = (transaction.description or "UNKNOWN SUBSCRIPTION").strip()
    return re.sub(r"\s+", " ", description).upper()


def _subscription_breakdown_groups(transactions: list[Transaction]) -> list[dict[str, object]]:
    groups: dict[str, dict[str, object]] = {}
    for tx in transactions:
        service = _subscription_service_name(tx)
        group = groups.setdefault(service, {"count": 0, "total": Decimal("0")})
        group["count"] = int(group["count"]) + 1
        group["total"] = money(group["total"]) + money(tx.amount)

    grand_total = sum((money(group["total"]) for group in groups.values()), Decimal("0"))
    sorted_groups = sorted(groups.items(), key=lambda item: money(item[1]["total"]), reverse=True)
    return [
        {
            "service": name,
            "count": int(group["count"]),
            "total": str(money(group["total"])),
            "share": _percentage(money(group["total"]), grand_total),
        }
        for name, group in sorted_groups
    ]


def _subscription_breakdown_table(transactions: list[Transaction]) -> str:
    sorted_groups = _subscription_breakdown_groups(transactions)
    rows = ["| Service | Transactions | Total | Share |", "|---|---:|---:|---:|"]
    rows.extend(
        f"| {group['service']} | {group['count']} | {format_brl(group['total'])} | {group['share']} |"
        for group in sorted_groups
    )
    return "\n".join(rows)


def _group_by_account_answer(
    transactions: list[Transaction],
    accounts: list[Account],
    question: str,
    intent: TransactionQueryIntent | None = None,
) -> FinancialAnswer:
    account_by_id = {account.id: account for account in accounts if account.id}
    groups: dict[str, dict[str, object]] = {}

    for tx in transactions:
        account = tx.account if isinstance(tx.account, Account) else account_by_id.get(_account_id(tx.account))
        account_name = account.display_name if isinstance(account, Account) else tx.account_name
        institution_name = _display_institution(account if isinstance(account, Account) else None, account_name)
        group = groups.setdefault(
            account_name,
            {"institution": institution_name, "transactions": [], "total": Decimal("0")},
        )
        group["transactions"].append(tx)
        group["total"] = money(group["total"]) + money(tx.amount)

    grand_total = sum((money(group["total"]) for group in groups.values()), Decimal("0"))
    sorted_groups = sorted(groups.items(), key=lambda item: money(item[1]["total"]), reverse=True)

    rows = [
        "| Account | Institution | Transactions | Total | Share |",
        "|---|---|---:|---:|---:|",
    ]
    top_lines = []
    metadata_groups = []
    for account_name, group in sorted_groups:
        txs = list(group["transactions"])
        total = money(group["total"])
        top = max(txs, key=lambda tx: money(tx.amount)) if txs else None
        rows.append(
            f"| {account_name} | {group['institution']} | {len(txs)} | {format_brl(total)} | {_percentage(total, grand_total)} |"
        )
        if top:
            top_lines.append(f"- {account_name}: {format_brl(top.amount)} - {top.description or 'No description'}")
        metadata_groups.append(
            {
                "account": account_name,
                "institution": group["institution"],
                "count": len(txs),
                "total": str(total),
                "share": _percentage(total, grand_total),
            }
        )

    answer = (
        "I grouped processed outflow transactions across the available dataset.\n\n"
        + "\n".join(rows)
    )
    if top_lines:
        answer += "\n\nTop transaction per account:\n" + "\n".join(top_lines)

    return _with_skill_context(FinancialAnswer(
        question=question,
        answer=answer,
        workflow="transaction_query_group_by_account",
        tools_used=["list_accounts", "list_transactions"],
        filters={"status": "PROCESSED"},
        evidence=[evidence_from_transaction(tx) for group in groups.values() for tx in list(group["transactions"])[:1]],
        metadata={
            "final_answer_metric": "group_by_account",
            "groups": metadata_groups,
            "grand_total": str(grand_total),
            "transactions_after_filtering": len(transactions),
        },
        caveats=["Grouped by account metadata from the processed transaction dataset."],
        chart=account_spending_chart(metadata_groups, intent.chart_type if intent else None),
    ), workflow="transaction_query_group_by_account", intent=intent)


def _category_name(transaction: Transaction) -> str:
    return (transaction.category or "Uncategorized").strip() or "Uncategorized"


def _group_by_category_answer(
    transactions: list[Transaction],
    question: str,
    intent: TransactionQueryIntent | None = None,
) -> FinancialAnswer:
    groups: dict[str, dict[str, object]] = {}

    for tx in transactions:
        category = _category_name(tx)
        group = groups.setdefault(category, {"transactions": [], "total": Decimal("0")})
        group["transactions"].append(tx)
        group["total"] = money(group["total"]) + money(tx.amount)

    grand_total = sum((money(group["total"]) for group in groups.values()), Decimal("0"))
    sorted_groups = sorted(groups.items(), key=lambda item: money(item[1]["total"]), reverse=True)

    rows = [
        "| Category | Transactions | Total | Share |",
        "|---|---:|---:|---:|",
    ]
    metadata_groups = []
    for category, group in sorted_groups:
        txs = list(group["transactions"])
        total = money(group["total"])
        share = _percentage(total, grand_total)
        rows.append(f"| {category} | {len(txs)} | {format_brl(total)} | {share} |")
        metadata_groups.append(
            {
                "category": category,
                "count": len(txs),
                "total": str(total),
                "share": share,
            }
        )

    language_pt = _is_portuguese(question)
    if language_pt:
        intro = "Agrupei suas transacoes de saida processadas por categoria no conjunto de dados disponivel."
    else:
        intro = "I grouped your processed outflow transactions by category across the available dataset."

    return _with_skill_context(FinancialAnswer(
        question=question,
        answer=f"{intro}\n\n" + "\n".join(rows),
        workflow="transaction_query_group_by_category",
        tools_used=["list_transactions"],
        filters={"status": "PROCESSED"},
        evidence=[evidence_from_transaction(list(group["transactions"])[0]) for group in groups.values() if group["transactions"]],
        metadata={
            "final_answer_metric": "group_by_category",
            "groups": metadata_groups,
            "grand_total": str(grand_total),
            "transactions_after_filtering": len(transactions),
        },
        caveats=["Grouped by transaction category from the processed transaction dataset."],
        chart=category_spending_chart(metadata_groups, intent.chart_type if intent else None),
    ), workflow="transaction_query_group_by_category", intent=intent)


def _is_portuguese(question: str) -> bool:
    normalized = question.upper()
    return any(
        term in normalized
        for term in [
            "QUAL",
            "QUANTO",
            "MEU",
            "MINHA",
            "GASTO",
            "PAGAMENTO",
            "DESPESA",
            "LISTE",
            "MOSTRE",
            "RECEBI",
            "ONTEM",
            "MAIO",
        ]
    )


def _account_id(account: Account | str | dict | None) -> str | None:
    if isinstance(account, Account):
        return account.id
    if isinstance(account, str):
        return account
    if isinstance(account, dict):
        value = account.get("id")
        return str(value) if value else None
    return None


def _account_institution(account: Account) -> str:
    institution = account.institution
    if hasattr(institution, "name"):
        return normalize_query_text(institution.name)
    if isinstance(institution, dict):
        return normalize_query_text(institution.get("name"))
    return ""


def _account_search_text(account: Account) -> str:
    parts = [
        account.id,
        account.name,
        account.category,
        account.type,
        account.subtype,
        _account_institution(account),
    ]
    return normalize_query_text(" ".join(part for part in parts if part))


def _transaction_search_text(transaction: Transaction) -> str:
    merchant_name = ""
    if transaction.merchant:
        merchant_name = str(transaction.merchant.get("merchant_name") or "")
    return normalize_query_text(
        " ".join(
            part
            for part in [
                transaction.description,
                merchant_name,
                transaction.category,
                transaction.subcategory,
            ]
            if part
        )
    )


def _is_pix_transaction(transaction: Transaction) -> bool:
    text = _transaction_search_text(transaction)
    return "PIX" in text or ("TRANSFER" in text and "PIX" in text)


SUBSCRIPTION_INCLUDE_KEYWORDS = [
    "NETFLIX",
    "SPOTIFY",
    "DISNEY PLUS",
    "AMAZON PRIME",
    "ICLOUD",
    "APPLE",
    "GOOGLE",
    "YOUTUBE",
    "PRIME VIDEO",
    "DISNEY",
    "HBO",
    "MAX",
    "GITHUB",
    "MICROSOFT",
    "ADOBE",
    "ICLOUD",
    "DROPBOX",
    "NOTION",
    "OPENAI",
    "CHATGPT",
    "VIVO FIBRA",
    "VIVO FIBRA INTERNET",
    "CLARO TELECOM",
    "CLARO TELECOM MOVEL",
    "TELECOM",
    "FIBRA",
    "MOVEL",
]

SUBSCRIPTION_CATEGORY_HINTS = [
    "ONLINE PLATFORMS & LEISURE",
    "STREAMING",
    "CLOUD STORAGE",
    "INTERNET",
    "MOBILE",
    "APPS SOFTWARE AND CLOUD SERVICES",
    "APPS, SOFTWARE AND CLOUD SERVICES",
    "MOVIE & AUDIO",
    "GAMING",
]

SUBSCRIPTION_EXCLUDE_KEYWORDS = [
    "ALUGUEL",
    "RENT",
    "CONDOMINIO",
    "ENERGIA",
    "ENEL",
    "WATER",
    "AGUA",
    "LUZ",
    "SABESP",
    "PAGAMENTO FATURA",
    "FATURA NUBANK",
    "TRANSFERENCIA",
    "PIX",
    "POUPANCA",
    "SAQUE",
    "ATM",
    "TED ENVIADA",
]


def matches_text_filter(transaction: Transaction, keywords: list[str]) -> bool:
    normalized_keywords = [normalize_query_text(keyword) for keyword in keywords]
    return all(keyword in _transaction_search_text(transaction) for keyword in normalized_keywords)


def _is_subscription_transaction(transaction: Transaction) -> bool:
    text = _transaction_search_text(transaction)
    if any(keyword in text for keyword in SUBSCRIPTION_EXCLUDE_KEYWORDS):
        return False
    return any(keyword in text for keyword in SUBSCRIPTION_INCLUDE_KEYWORDS + SUBSCRIPTION_CATEGORY_HINTS)


def filter_transactions_by_account(transactions: list[Transaction], account_ids: list[str]) -> list[Transaction]:
    wanted = set(account_ids)
    return [tx for tx in transactions if _account_id(tx.account) in wanted]


def filter_transactions_by_description(transactions: list[Transaction], keywords: list[str]) -> list[Transaction]:
    return [tx for tx in transactions if matches_text_filter(tx, keywords)]


def parse_payment_method_filter(question: str) -> str | None:
    text = normalize_query_text(question)
    if "PIX" in text:
        return "pix"
    if any(term in text for term in ["CREDIT CARD", "CARD", "CARTAO"]):
        return "credit_card"
    return None


def is_nubank_bill_payment_query(question: str) -> bool:
    text = normalize_query_text(question)
    return "NUBANK" in text and any(
        term in text
        for term in ["PAYMENT", "PAY", "BILL", "INVOICE", "PAGAMENTO", "FATURA", "PAGAR", "PAGUE", "PAGUEI"]
    )


def is_credit_card_charge_query(question: str) -> bool:
    text = normalize_query_text(question)
    return any(term in text for term in ["CREDIT CARD", "CARD", "CARTAO"]) and not any(
        term in text for term in ["BILL", "INVOICE", "FATURA", "PAGAMENTO DA FATURA"]
    )


def _contains_query_term(text: str, terms: list[str]) -> bool:
    return any(re.search(rf"\b{re.escape(term)}\b", text) for term in terms)


def _has_latest_metric(text: str) -> bool:
    if _contains_query_term(text, ["LATEST", "MOST RECENT", "MAIS RECENTE", "ULTIMO", "ULTIMA", "WHEN", "QUANDO", "DATA"]):
        return True
    if re.search(r"\bQUANDO(?:\s+EU)?\s+PAGUEI\b", text):
        return True
    return bool(re.search(r"\bLAST\b", text)) and not bool(
        re.search(r"\bLAST\s+(?:\d+\s+)?(?:DAY|DAYS|WEEK|WEEKS|MONTH|MONTHS)\b", text)
    )


def _is_group_by_account_query(text: str) -> bool:
    return any(
        re.search(pattern, text)
        for pattern in [
            r"\bSPLIT\b.*\bPER\s+ACCOUNT\b",
            r"\bBREAK\s+DOWN\b.*\bBY\s+ACCOUNT\b",
            r"\bGROUP(?:ED)?\s+BY\s+ACCOUNT\b",
            r"\bPER\s+ACCOUNT\b",
            r"\bBY\s+ACCOUNT\b",
            r"\bPOR\s+CONTA\b",
            r"\bPOR\s+BANCO\b",
            r"\bPOR\s+INSTITUICAO\b",
            r"\bSEPARE\b.*\bGASTOS\b.*\bPOR\s+CONTA\b",
            r"\bGASTOS\b.*\bPOR\s+CONTA\b",
        ]
    )


def _is_group_by_category_query(text: str) -> bool:
    return any(
        re.search(pattern, text)
        for pattern in [
            r"\bPER\s+CATEGORY\b",
            r"\bBY\s+CATEGORY\b",
            r"\bGROUP(?:ED)?\s+BY\s+CATEGORY\b",
            r"\bSPENDING\s+BY\s+CATEGORY\b",
            r"\bEXPENSES?\s+BY\s+CATEGORY\b",
            r"\bGASTOS\b.*\bPOR\s+CATEGORIA\b",
            r"\bDESPESAS\b.*\bPOR\s+CATEGORIA\b",
            r"\bPOR\s+CATEGORIA\b",
        ]
    )


def _infer_chart_type(question: str) -> str | None:
    text = normalize_query_text(question)
    if any(term in text for term in ["PIE CHART", "PIZZA CHART", "GRAFICO DE PIZZA", "PIZZA"]):
        return "pie"
    if any(term in text for term in ["GRAPH", "CHART", "PLOT", "VISUALIZE", "GRAFICO"]):
        return "bar"
    return None


def _infer_metric(question: str) -> str:
    text = normalize_query_text(question)
    if _contains_query_term(text, ["SMALLEST", "LOWEST", "LEAST EXPENSIVE", "MENOR"]):
        return "smallest"
    if _contains_query_term(text, ["BIGGEST", "LARGEST", "HIGHEST", "MAIOR"]):
        return "largest"
    if _has_latest_metric(text):
        return "latest"
    if _is_group_by_account_query(text):
        return "group_by_account"
    if _is_group_by_category_query(text):
        return "group_by_category"
    if _contains_query_term(text, ["HOW MUCH", "QUANTO", "TOTAL", "SUM", "SOMA"]):
        return "total"
    if _contains_query_term(text, ["SHOW", "LIST", "ALL", "ONLY", "SPECIFIC", "WHOLE", "MOSTRE", "LISTE", "TODOS", "TODAS", "SO", "APENAS"]):
        return "list"
    return "list"


def _infer_direction(question: str) -> str:
    text = normalize_query_text(question)
    if any(term in text for term in ["RECEIVED", "RECEIVE", "RECEBI", "RECEBIDO", "ENTRADA", "INFLOW"]):
        return "INFLOW"
    if any(term in text for term in ["SENT", "SEND", "ENVIEI", "ENVIADO", "PAYMENT", "PAYMENTS", "PAGAMENTO", "PAGAMENTOS"]):
        return "OUTFLOW"
    if any(term in text for term in ["EXPENSE", "EXPENSES", "SPEND", "SPENT", "GASTO", "GASTOS", "DESPESA", "DESPESAS", "CHARGE", "CHARGES", "COMPRA"]):
        return "OUTFLOW"
    return "BOTH"


def _infer_description_filters(question: str) -> list[str]:
    text = normalize_query_text(question)
    filters: list[str] = []
    if is_nubank_bill_payment_query(question):
        filters.append("NUBANK")
    if "NETFLIX" in text:
        filters.append("NETFLIX")
    if "PIX" in text:
        filters.append("PIX")
    return filters


def _extract_amount_filters(question: str) -> dict[str, Decimal | None]:
    filters: dict[str, Decimal | None] = {"amount_gt": None, "amount_gte": None, "amount_lt": None, "amount_lte": None}
    text = normalize_query_text(question)
    normalized = question.replace(",", ".")
    has_lt = bool(re.search(r"\b(BELOW|UNDER|LESS THAN|ABAIXO|MENOR QUE)\b", text))
    has_gt = bool(re.search(r"\b(OVER|ABOVE|GREATER THAN|ACIMA|MAIS DE|MAIOR QUE)\b", text))
    if not (has_lt or has_gt):
        return filters
    match = re.search(r"(?:R\$|BRL)?\s*(\d+(?:\.\d+)?)", normalized, flags=re.IGNORECASE)
    if not match:
        return filters
    amount = Decimal(match.group(1))
    if has_lt:
        filters["amount_lt"] = amount
    elif has_gt:
        filters["amount_gt"] = amount
    return filters


def _extract_amount_threshold(question: str) -> Decimal | None:
    amount_filters = _extract_amount_filters(question)
    return amount_filters["amount_gt"] or amount_filters["amount_lt"]


def _workflow_metric_name(metric: str) -> str:
    if metric == "latest":
        return "last"
    if metric == "largest":
        return "biggest"
    return metric


def parse_account_filter(question: str, accounts: list[Account]) -> AccountFilter | None:
    text = normalize_query_text(question)
    categories: list[str] = []
    institution_names: list[str] = []
    account_name_contains: list[str] = []

    if any(term in text for term in ["CHECKING", "CURRENT ACCOUNT", "CONTA CORRENTE"]):
        categories.append("CHECKING_ACCOUNT")
    if any(term in text for term in ["SAVINGS", "POUPANCA"]):
        categories.append("SAVINGS_ACCOUNT")
    if any(term in text for term in ["CREDIT CARD", "CARD", "CARTAO"]):
        categories.append("CREDIT_CARD")
    if "ITAU" in text:
        institution_names.append("ITAU")
        account_name_contains.append("ITAU")
    if "NUBANK" in text and not is_nubank_bill_payment_query(question):
        institution_names.append("NUBANK")
        account_name_contains.append("NUBANK")

    if not categories and not institution_names and not account_name_contains:
        return None

    matched: list[str] = []
    for account in accounts:
        search_text = _account_search_text(account)
        category_ok = not categories or (account.category in categories)
        institution_ok = not institution_names or any(name in search_text for name in institution_names)
        name_ok = not account_name_contains or any(name in search_text for name in account_name_contains)
        if category_ok and institution_ok and name_ok and account.id:
            matched.append(account.id)

    return AccountFilter(
        account_ids=matched,
        institution_names=institution_names or None,
        account_categories=categories or None,
        account_name_contains=account_name_contains or None,
    )


def _parse_date_range_for_transaction_query(question: str) -> DateRange | None:
    if not has_date_reference(question):
        return None
    start, end, label = resolve_natural_date_range(question)
    return DateRange(start=start.isoformat(), end=end.isoformat(), label=label)


def parse_date_range(question: str) -> DateRange | None:
    return _parse_date_range_for_transaction_query(question)


def _build_transaction_query_intent(question: str, accounts: list[Account]) -> TransactionQueryIntent:
    payment_method = parse_payment_method_filter(question)
    direction = _infer_direction(question)
    text = normalize_query_text(question)
    if payment_method == "pix" and direction == "BOTH":
        direction = "BOTH"
    elif payment_method == "credit_card" and direction == "BOTH" and "TRANSACTION" not in normalize_query_text(question):
        direction = "OUTFLOW"

    account_filter = parse_account_filter(question, accounts)
    description_contains = _infer_description_filters(question)
    include_bill_payments = is_nubank_bill_payment_query(question) or any(
        term in normalize_query_text(question) for term in ["BILL PAYMENT", "INVOICE", "FATURA"]
    )
    institution_filter = None
    if account_filter and account_filter.institution_names:
        institution_filter = ", ".join(account_filter.institution_names)
    if is_nubank_bill_payment_query(question):
        category_intent = "nubank_bill_payment"
    elif any(term in text for term in ["SUBSCRIPTION", "SUBSCRIPTIONS", "ASSINATURA", "ASSINATURAS"]):
        category_intent = "subscriptions"
    else:
        category_intent = None
    metric = _infer_metric(question)
    if metric in {"group_by_account", "group_by_category"} or category_intent in {"subscriptions", "nubank_bill_payment"}:
        direction = "OUTFLOW"
    amount_filters = _extract_amount_filters(question)

    return TransactionQueryIntent(
        metric=metric,
        direction=direction,
        date_range=_parse_date_range_for_transaction_query(question),
        account_filter=account_filter,
        payment_method_filter=payment_method,
        institution_filter=institution_filter,
        description_contains=description_contains,
        category_intent=category_intent,
        include_bill_payments=include_bill_payments,
        amount_gt=amount_filters["amount_gt"],
        amount_gte=amount_filters["amount_gte"],
        amount_lt=amount_filters["amount_lt"],
        amount_lte=amount_filters["amount_lte"],
        chart_type=_infer_chart_type(question),
        status="PROCESSED",
    )


def parse_transaction_intent(question: str, accounts: list[Account] | None = None) -> TransactionQueryIntent:
    return _build_transaction_query_intent(question, accounts or [])


def _matches_bill_payment(transaction: Transaction) -> bool:
    text = _transaction_search_text(transaction)
    return "NUBANK" in text and any(term in text for term in ["PAGAMENTO", "FATURA", "BILL", "INVOICE", "PAYMENT"])


async def get_balance_summary(client: FinanceDataClient, question: str) -> FinancialAnswer:
    accounts = await client.list_accounts({})
    cash_accounts: list[tuple[Account, Decimal]] = []
    credit_accounts: list[tuple[Account, Decimal]] = []

    for account in accounts:
        balance = account.balance
        current = money(balance.current if balance else None)
        available = money(balance.available if balance else None)
        value = current if current != 0 else available
        category = account.category or ""
        if category in {"CHECKING_ACCOUNT", "SAVINGS_ACCOUNT"}:
            cash_accounts.append((account, value))
        elif category == "CREDIT_CARD" or account.balance_type == "LIABILITY":
            credit_accounts.append((account, current))

    cash_total = sum((value for _, value in cash_accounts), Decimal("0"))
    card_debt = sum((value for _, value in credit_accounts), Decimal("0"))
    net_position = cash_total - card_debt

    breakdown = []
    for account, value in cash_accounts:
        breakdown.append(f"- {account.display_name}: {format_brl(value)} cash")
    for account, value in credit_accounts:
        breakdown.append(f"- {account.display_name}: {format_brl(value)} current credit card spending/debt")

    answer = (
        f"Cash balance is {format_brl(cash_total)}. Credit card current spending/debt is "
        f"{format_brl(card_debt)}. Net position, treating card spending as a liability, is "
        f"{format_brl(net_position)}.\n\n" + "\n".join(breakdown)
    )

    return _with_skill_context(FinancialAnswer(
        question=question,
        answer=answer,
        workflow="balance_summary",
        tools_used=["list_accounts"],
        filters={},
        metadata={
            "cash_total": str(cash_total),
            "credit_card_debt": str(card_debt),
            "net_position": str(net_position),
            "accounts_considered": [account.display_name for account in accounts],
        },
        caveats=["Credit card available limit was not counted as cash."],
    ))


async def get_food_spending(client: FinanceDataClient, question: str, today: date | None = None) -> FinancialAnswer:
    today = today or date.today()
    start, end = last_n_days(today, 30)
    filters = _date_filter(start, end, type="OUTFLOW", status="PROCESSED")
    transactions = await client.list_transactions(filters)
    matching = [
        tx
        for tx in transactions
        if tx.type == "OUTFLOW" and _processed(tx) and _in_date_range(tx, start, end) and is_food_transaction(tx)
    ]
    total = sum((money(tx.amount) for tx in matching), Decimal("0"))
    examples = sorted(matching, key=lambda tx: money(tx.amount), reverse=True)[:5]
    example_text = "\n".join(
        f"- {tx.value_date}: {format_brl(tx.amount)} - {tx.description or 'No description'}"
        for tx in examples
    )
    answer = (
        f"You spent {format_brl(total)} on food from {start} to {end} across "
        f"{len(matching)} processed outflow transactions."
    )
    if examples:
        answer += f"\n\nLargest examples:\n{example_text}"

    return _with_skill_context(FinancialAnswer(
        question=question,
        answer=answer,
        workflow="food_spending",
        tools_used=["list_transactions"],
        filters=filters,
        evidence=[evidence_from_transaction(tx) for tx in examples],
        metadata={"total": str(total), "transaction_count": len(matching), "date_range": [start.isoformat(), end.isoformat()]},
        caveats=["Food classification used category/subcategory when available and description heuristics otherwise."],
    ))


async def get_spending_summary(
    client: FinanceDataClient,
    question: str,
    start: date,
    end: date,
    period_label: str,
) -> FinancialAnswer:
    filters = _date_filter(start, end, type="OUTFLOW", status="PROCESSED")
    transactions = await client.list_transactions(filters)
    matching = [
        tx
        for tx in transactions
        if tx.type == "OUTFLOW" and _processed(tx) and _in_date_range(tx, start, end)
    ]
    total = sum((money(tx.amount) for tx in matching), Decimal("0"))
    examples = sorted(matching, key=lambda tx: money(tx.amount), reverse=True)[:5]

    if matching:
        example_text = "\n".join(
            f"- {tx.value_date}: {format_brl(tx.amount)} - {tx.description or 'No description'}"
            for tx in examples
        )
        answer = (
            f"You spent {format_brl(total)} {period_label} across "
            f"{len(matching)} processed outflow transactions.\n\nLargest examples:\n{example_text}"
        )
    else:
        answer = f"I found no processed outflow transactions {period_label}."

    return _with_skill_context(FinancialAnswer(
        question=question,
        answer=answer,
        workflow="spending_summary",
        tools_used=["list_transactions"],
        filters=filters,
        evidence=[evidence_from_transaction(tx) for tx in examples],
        metadata={
            "total": str(total),
            "transaction_count": len(matching),
            "date_range": [start.isoformat(), end.isoformat()],
            "period_label": period_label,
        },
        caveats=["Spending means processed OUTFLOW transactions, using value_date."],
    ))


async def get_transaction_query(
    client: FinanceDataClient,
    question: str,
) -> FinancialAnswer:
    accounts = await client.list_accounts({})
    intent = _build_transaction_query_intent(question, accounts)

    filters: dict[str, object] = {"status": intent.status}
    if intent.amount_gt is not None:
        filters["amount__gt"] = float(intent.amount_gt)
    transactions = await client.list_transactions(filters)
    counts: dict[str, int] = {"fetched": len(transactions)}

    matching = [tx for tx in transactions if (tx.status or "").upper() == intent.status.upper()]
    counts["after_status"] = len(matching)

    if intent.direction in {"OUTFLOW", "INFLOW"}:
        matching = [tx for tx in matching if tx.type == intent.direction]
    counts["after_direction"] = len(matching)

    if intent.date_range:
        start_date = date.fromisoformat(intent.date_range.start)
        end_date = date.fromisoformat(intent.date_range.end)
        matching = [tx for tx in matching if _in_date_range(tx, start_date, end_date)]
    counts["after_date"] = len(matching)

    if intent.amount_gt is not None:
        matching = [tx for tx in matching if money(tx.amount) > intent.amount_gt]
    if intent.amount_gte is not None:
        matching = [tx for tx in matching if money(tx.amount) >= intent.amount_gte]
    if intent.amount_lt is not None:
        matching = [tx for tx in matching if money(tx.amount) < intent.amount_lt]
    if intent.amount_lte is not None:
        matching = [tx for tx in matching if money(tx.amount) <= intent.amount_lte]
    counts["after_amount"] = len(matching)

    if intent.payment_method_filter == "pix":
        matching = [tx for tx in matching if _is_pix_transaction(tx)]
    if intent.description_contains:
        matching = filter_transactions_by_description(matching, intent.description_contains)
    if is_nubank_bill_payment_query(question):
        matching = [tx for tx in matching if _matches_bill_payment(tx)]
    elif not intent.include_bill_payments and intent.payment_method_filter == "credit_card":
        matching = [tx for tx in matching if not _matches_bill_payment(tx)]
    counts["after_text"] = len(matching)

    if intent.category_intent == "subscriptions":
        matching = [tx for tx in matching if _is_subscription_transaction(tx)]
    if intent.category_intent == "nubank_bill_payment":
        matching = [tx for tx in matching if _matches_bill_payment(tx)]
    counts["after_category"] = len(matching)

    fallback_to_description = False
    if intent.account_filter:
        if intent.account_filter.account_ids:
            matching = filter_transactions_by_account(matching, intent.account_filter.account_ids)
        elif intent.institution_filter == "NUBANK":
            matching = filter_transactions_by_description(matching, ["NUBANK"])
            fallback_to_description = True
        else:
            matching = []
    if intent.payment_method_filter == "credit_card" and intent.account_filter and not intent.account_filter.account_ids:
        matching = []
    counts["final"] = len(matching)

    if intent.metric == "group_by_account":
        return _group_by_account_answer(matching, accounts, question, intent)
    if intent.metric == "group_by_category":
        return _group_by_category_answer(matching, question, intent)

    if intent.metric == "latest":
        matching.sort(key=lambda tx: (tx.value_date or "", str(tx.amount)), reverse=True)
    elif intent.metric == "smallest":
        matching.sort(key=lambda tx: money(tx.amount))
    else:
        matching.sort(key=lambda tx: money(tx.amount), reverse=True)

    language_pt = _is_portuguese(question)
    direction_label = "OUTFLOW" if intent.direction == "OUTFLOW" else "INFLOW" if intent.direction == "INFLOW" else "historical"
    if intent.date_range:
        range_text = f" from {intent.date_range.start} to {intent.date_range.end}"
        range_text_pt = f" de {intent.date_range.start} a {intent.date_range.end}"
    else:
        range_text = " in the available dataset"
        range_text_pt = " no conjunto disponivel"

    if not matching:
        if language_pt:
            answer = f"Nao encontrei transacoes correspondentes aos filtros exatos usados{range_text_pt}."
        else:
            answer = f"I found no matching processed transactions for the exact filters used{range_text}."
        return _with_skill_context(FinancialAnswer(
            question=question,
            answer=answer,
            workflow=f"transaction_query_{_workflow_metric_name(intent.metric)}",
            tools_used=["list_transactions"],
            filters=filters,
            metadata={
                "parsed_intent": asdict(intent),
                "counts": counts,
                "transactions_before_filtering": counts["fetched"],
                "transactions_after_filtering": 0,
                "final_answer_metric": intent.metric,
            },
            caveats=["This is a read-only historical transaction query."],
        ), intent=intent)

    interpretation_note = None
    if fallback_to_description:
        interpretation_note = 'I found no Nubank account transactions, so I searched descriptions containing "Nubank".'
    elif "NUBANK" in normalize_query_text(question) and intent.account_filter and intent.account_filter.account_ids and not intent.include_bill_payments:
        interpretation_note = "I interpreted Nubank transactions as transactions from the Nubank account/card."
    if is_nubank_bill_payment_query(question):
        interpretation_note = "I interpreted Nubank payment as bill/payment transactions with Nubank in the description."

    if intent.metric == "latest":
        tx = matching[0]
        if intent.category_intent == "subscriptions":
            if language_pt:
                answer = (
                    f"Sua assinatura provavel mais recente foi {format_brl(tx.amount)} em {tx.value_date}: "
                    f"{tx.description or 'Sem descricao'}, na conta {tx.account_name}."
                )
            else:
                answer = (
                    f"Your latest likely subscription payment was {format_brl(tx.amount)} on {tx.value_date}: "
                    f"{tx.description or 'No description'}, from {tx.account_name}."
                )
        elif intent.category_intent == "nubank_bill_payment" and language_pt:
            answer = (
                f"Voce pagou a fatura Nubank pela ultima vez em {tx.value_date}: "
                f"{format_brl(tx.amount)} - {tx.description or 'Sem descricao'}, na conta {tx.account_name}."
            )
        elif language_pt:
            answer = (
                f"Seu ultimo gasto processado foi em {tx.value_date}: {format_brl(tx.amount)} - "
                f"{tx.description or 'Sem descricao'}, na conta {tx.account_name}."
            )
        else:
            answer = (
                f"Your last processed outflow was on {tx.value_date}: {format_brl(tx.amount)} - "
                f"{tx.description or 'No description'}, from {tx.account_name}."
            )
        evidence = [evidence_from_transaction(tx)]
    elif intent.metric in {"largest", "smallest"}:
        tx = matching[0]
        adjective = "biggest" if intent.metric == "largest" else "smallest"
        if intent.category_intent == "subscriptions":
            if language_pt:
                adjective_pt = "maior" if intent.metric == "largest" else "menor"
                answer = (
                    f"Sua {adjective_pt} assinatura provavel foi {format_brl(tx.amount)} em "
                    f"{tx.value_date}: {tx.description or 'Sem descricao'}, na conta {tx.account_name}."
                )
            else:
                answer = (
                    f"Your {adjective} likely subscription payment was {format_brl(tx.amount)} on "
                    f"{tx.value_date}: {tx.description or 'No description'}, from {tx.account_name}."
                )
        elif language_pt:
            adjective_pt = "maior" if intent.metric == "largest" else "menor"
            answer = (
                f"Seu {adjective_pt} gasto processado{range_text_pt} foi {format_brl(tx.amount)} em "
                f"{tx.value_date}: {tx.description or 'Sem descricao'}.\n"
                f"Considerei transacoes {direction_label} processadas{range_text_pt}."
            )
        else:
            answer = (
                f"Your {adjective} processed expense{range_text} was {format_brl(tx.amount)} on "
                f"{tx.value_date}: {tx.description or 'No description'}.\n"
                f"I considered processed {direction_label} transactions{range_text}."
            )
        evidence = [evidence_from_transaction(tx)]
    elif intent.metric == "list":
        if intent.category_intent == "subscriptions":
            table = _table_for_subscription_transactions(matching)
            if language_pt:
                answer = f"Encontrei {len(matching)} transacoes provaveis de assinatura{range_text_pt}.\n\n{table}"
            else:
                answer = f"I found {len(matching)} likely subscription transactions{range_text}.\n\n{table}"
        elif language_pt:
            answer = (
                f"Encontrei {len(matching)} transacoes processadas{range_text_pt}.\n\n"
                f"{_table_for_transactions(matching)}"
            )
        else:
            answer = (
                f"I found {len(matching)} processed transactions{range_text}.\n\n"
                f"{_table_for_transactions(matching)}"
            )
        evidence = [evidence_from_transaction(tx) for tx in matching]
    else:
        total = sum((money(tx.amount) for tx in matching), Decimal("0"))
        examples = matching[:5]
        example_text = "\n".join(
            f"- {tx.value_date}: {format_brl(tx.amount)} - {tx.description or 'No description'}"
            for tx in examples
        )
        if intent.category_intent == "subscriptions":
            if language_pt:
                answer = (
                    f"Encontrei {format_brl(total)} em gastos provaveis com assinaturas em "
                    f"{len(matching)} transacoes OUTFLOW processadas.\n\n"
                    f"Breakdown by subscription:\n{_subscription_breakdown_table(matching)}"
                )
            else:
                answer = (
                    f"I found {format_brl(total)} in likely subscription spending across "
                    f"{len(matching)} processed outflow transactions.\n\n"
                    f"Breakdown by subscription:\n{_subscription_breakdown_table(matching)}"
                )
        elif language_pt:
            if intent.direction == "INFLOW":
                verb = "recebeu"
            elif "PIX" in normalize_query_text(question) and any(term in normalize_query_text(question) for term in ["ENVIEI", "SEND", "SENT"]):
                verb = "enviou"
            else:
                verb = "gastou"
            answer = f"Voce {verb} {format_brl(total)}{range_text_pt} em {len(matching)} transacoes processadas."
        else:
            if intent.direction == "INFLOW":
                verb = "received"
            elif "PIX" in normalize_query_text(question) and any(term in normalize_query_text(question) for term in ["SEND", "SENT"]):
                verb = "sent"
            else:
                verb = "spent"
            direction_word = "inflow" if intent.direction == "INFLOW" else "outflow" if intent.direction == "OUTFLOW" else "historical"
            answer = f"You {verb} {format_brl(total)}{range_text} across {len(matching)} processed {direction_word} transactions."
        if examples and intent.category_intent != "subscriptions":
            answer += f"\n\nLargest examples:\n{example_text}"
        evidence = [evidence_from_transaction(tx) for tx in examples]

    if interpretation_note:
        answer = f"{interpretation_note}\n\n{answer}"

    subscription_groups = _subscription_breakdown_groups(matching) if intent.category_intent == "subscriptions" else []
    chart = (
        subscription_breakdown_chart(subscription_groups)
        if intent.category_intent == "subscriptions" and intent.metric == "total"
        else None
    )

    return _with_skill_context(FinancialAnswer(
        question=question,
        answer=answer,
        workflow=f"transaction_query_{_workflow_metric_name(intent.metric)}",
        tools_used=["list_transactions"],
        filters=filters,
        evidence=evidence,
        metadata={
            "parsed_intent": asdict(intent),
            "counts": counts,
            "transactions_before_filtering": counts["fetched"],
            "transactions_after_filtering": len(matching),
            "final_answer_metric": intent.metric,
            "matches": len(matching),
            "date_range": [intent.date_range.start, intent.date_range.end] if intent.date_range else None,
            "amount_gt": str(intent.amount_gt) if intent.amount_gt is not None else None,
            "amount_gte": str(intent.amount_gte) if intent.amount_gte is not None else None,
            "amount_lt": str(intent.amount_lt) if intent.amount_lt is not None else None,
            "amount_lte": str(intent.amount_lte) if intent.amount_lte is not None else None,
            "transaction_type": intent.direction,
            "subscription_breakdown": subscription_groups,
        },
        caveats=["This is a read-only historical transaction query."],
        chart=chart,
    ), intent=intent)


async def detect_salary(client: FinanceDataClient, question: str, today: date | None = None) -> FinancialAnswer:
    today = today or date.today()
    start, end = current_month(today)
    filters = _date_filter(start, end, type="INFLOW", status="PROCESSED")
    transactions = await client.list_transactions(filters)
    salary_transactions = [
        tx
        for tx in transactions
        if tx.type == "INFLOW" and _processed(tx) and _in_date_range(tx, start, end) and is_salary_transaction(tx)
    ]
    salary_transactions.sort(key=lambda tx: tx.value_date or "", reverse=True)

    if salary_transactions:
        tx = salary_transactions[0]
        answer = (
            f"Yes. I found likely salary income on {tx.value_date}: {format_brl(tx.amount)} "
            f"in {tx.account_name}, described as \"{tx.description or 'No description'}\"."
        )
        evidence = [evidence_from_transaction(tx)]
    else:
        answer = f"I did not find a likely salary inflow from {start} to {end} among processed transactions."
        evidence = []

    return _with_skill_context(FinancialAnswer(
        question=question,
        answer=answer,
        workflow="salary_detection",
        tools_used=["list_transactions"],
        filters=filters,
        evidence=evidence,
        metadata={"date_range": [start.isoformat(), end.isoformat()], "matches": len(salary_transactions)},
        caveats=["Salary detection uses salary category/subcategory and description keywords."],
    ))


async def get_large_transactions(
    client: FinanceDataClient,
    question: str,
    threshold: Decimal = Decimal("500"),
    today: date | None = None,
) -> FinancialAnswer:
    today = today or date.today()
    start, end = last_n_days(today, 90)
    filters = _date_filter(start, end, amount__gt=float(threshold), status="PROCESSED")
    transactions = await client.list_transactions(filters)
    matching = [
        tx
        for tx in transactions
        if _processed(tx) and _in_date_range(tx, start, end) and money(tx.amount) > threshold
    ]
    matching.sort(key=lambda tx: money(tx.amount), reverse=True)
    rows = matching[:15]

    if rows:
        table = "\n".join(
            "| {date} | {amount} | {type} | {account} | {desc} | {category} |".format(
                date=tx.value_date or "",
                amount=format_brl(tx.amount),
                type=tx.type or "",
                account=tx.account_name,
                desc=(tx.description or "").replace("|", "/"),
                category="/".join(part for part in [tx.category, tx.subcategory] if part),
            )
            for tx in rows
        )
        answer = (
            f"I found {len(matching)} processed transactions over {format_brl(threshold)} from {start} to {end}, "
            f"sorted by amount descending.\n\n| Date | Amount | Type | Account | Description | Category |\n"
            f"|---|---:|---|---|---|---|\n{table}"
        )
    else:
        answer = f"I found no processed transactions over {format_brl(threshold)} from {start} to {end}."

    return _with_skill_context(FinancialAnswer(
        question=question,
        answer=answer,
        workflow="large_transactions",
        tools_used=["list_transactions"],
        filters=filters,
        evidence=[evidence_from_transaction(tx) for tx in rows],
        metadata={"date_range": [start.isoformat(), end.isoformat()], "threshold": str(threshold), "matches": len(matching)},
        caveats=["Results are sorted by amount descending."],
    ))


async def detect_recurring_expenses(client: FinanceDataClient, question: str) -> FinancialAnswer:
    filters = {"type": "OUTFLOW", "status": "PROCESSED"}
    transactions = await client.list_transactions(filters)
    outflows = [tx for tx in transactions if tx.type == "OUTFLOW" and _processed(tx)]
    candidates = detect_recurring_candidates(outflows)

    if not candidates:
        answer = "I did not find a strong recurring-expense candidate with at least three repeated processed outflows."
        evidence = []
        metadata = {"candidate_count": 0}
    else:
        candidate = candidates[0]
        recent = sorted(candidate.transactions, key=lambda tx: tx.value_date or "", reverse=True)[:5]
        evidence_lines = "\n".join(
            f"- {tx.value_date}: {format_brl(tx.amount)} - {tx.description or candidate.name}"
            for tx in recent
        )
        answer = (
            f"The biggest likely recurring expense is {candidate.name}, averaging "
            f"{format_brl(candidate.average_amount)} with an estimated {candidate.cadence} cadence. "
            f"Confidence: {candidate.confidence}. Last occurrence: {recent[0].value_date if recent else 'unknown'}.\n\n"
            f"Evidence:\n{evidence_lines}"
        )
        evidence = [evidence_from_transaction(tx) for tx in recent]
        metadata = {
            "candidate_count": len(candidates),
            "merchant": candidate.name,
            "average_amount": str(candidate.average_amount),
            "cadence": candidate.cadence,
            "confidence": candidate.confidence,
        }

    return _with_skill_context(FinancialAnswer(
        question=question,
        answer=answer,
        workflow="recurring_expense_detection",
        tools_used=["list_transactions"],
        filters=filters,
        evidence=evidence,
        metadata=metadata,
        caveats=["Recurring expense detection is heuristic and excludes obvious card bill payments or transfers."],
    ))


async def get_cash_flow_last_month(client: FinanceDataClient, question: str, today: date | None = None) -> FinancialAnswer:
    today = today or date.today()
    start, end = previous_month(today)
    filters = _date_filter(start, end, status="PROCESSED")
    transactions = await client.list_transactions(filters)
    processed = [tx for tx in transactions if _processed(tx) and _in_date_range(tx, start, end)]
    inflows = [tx for tx in processed if tx.type == "INFLOW"]
    outflows = [tx for tx in processed if tx.type == "OUTFLOW"]
    inflow_total = sum((money(tx.amount) for tx in inflows), Decimal("0"))
    outflow_total = sum((money(tx.amount) for tx in outflows), Decimal("0"))
    net = inflow_total - outflow_total

    answer = (
        f"Last month ({start} to {end}), money in was {format_brl(inflow_total)} and money out was "
        f"{format_brl(outflow_total)}. Net cash flow was {format_brl(net)} across "
        f"{len(inflows)} inflows and {len(outflows)} outflows."
    )

    examples = sorted(processed, key=lambda tx: money(tx.amount), reverse=True)[:5]
    return _with_skill_context(FinancialAnswer(
        question=question,
        answer=answer,
        workflow="cash_flow_last_month",
        tools_used=["list_transactions"],
        filters=filters,
        evidence=[evidence_from_transaction(tx) for tx in examples],
        metadata={
            "date_range": [start.isoformat(), end.isoformat()],
            "inflow_total": str(inflow_total),
            "outflow_total": str(outflow_total),
            "net": str(net),
            "inflow_count": len(inflows),
            "outflow_count": len(outflows),
        },
        caveats=["Transaction amounts are positive; direction is determined from transaction type."],
    ))


def refuse_mutation_request(question: str) -> FinancialAnswer:
    return _with_skill_context(FinancialAnswer(
        question=question,
        answer=(
            "I cannot modify accounts, balances or transactions in this demo. The available tools are read-only: "
            "get_owners, list_accounts and list_transactions. I can analyze existing data, summarize spending, "
            "find transactions or explain balances."
        ),
        workflow="read_only_refusal",
        tools_used=[],
        filters={},
        caveats=["No MCP mutation tool was called."],
    ))
