import asyncio
from decimal import Decimal

from belvo_finance_agent.agent import FinancialSpecialistAgent
from belvo_finance_agent.finance_workflows import parse_date_range, parse_transaction_intent
from belvo_finance_agent.models import Account, Institution, Transaction


class FilterClient:
    def __init__(self):
        self.accounts = [
            Account(id="chk", name="Conta Corrente Itau", category="CHECKING_ACCOUNT", institution=Institution(name="Itau")),
            Account(id="sav", name="Poupanca Itau", category="SAVINGS_ACCOUNT", institution=Institution(name="Itau")),
            Account(id="nub", name="Nubank Mastercard", category="CREDIT_CARD", institution=Institution(name="Nubank")),
        ]
        self.transactions = [
            Transaction(description="PIX ENVIADO - MARIA", amount=Decimal("100"), value_date="2026-05-02", type="OUTFLOW", status="PROCESSED", account=self.accounts[0]),
            Transaction(description="PIX RECEBIDO - JOAO", amount=Decimal("250"), value_date="2026-05-03", type="INFLOW", status="PROCESSED", account=self.accounts[0]),
            Transaction(description="PAGAMENTO FATURA NUBANK", amount=Decimal("500"), value_date="2026-05-04", type="OUTFLOW", status="PROCESSED", account=self.accounts[0]),
            Transaction(description="MAGALU LOJA ONLINE", amount=Decimal("300"), value_date="2026-05-05", type="OUTFLOW", status="PROCESSED", account=self.accounts[2]),
            Transaction(description="IFOOD*BURGER", amount=Decimal("80"), value_date="2026-05-06", type="OUTFLOW", status="PROCESSED", account=self.accounts[2]),
            Transaction(description="TRANSFERENCIA RECEBIDA POUPANCA", amount=Decimal("200"), value_date="2026-05-07", type="INFLOW", status="PROCESSED", account=self.accounts[1]),
            Transaction(description="TARIFA CONTA", amount=Decimal("55"), value_date="2026-05-08", type="OUTFLOW", status="PROCESSED", account=self.accounts[0]),
            Transaction(description="NETFLIX.COM", amount=Decimal("39.90"), value_date="2026-05-09", type="OUTFLOW", status="PROCESSED", account=self.accounts[2], category="Online Platforms & Leisure", subcategory="Streaming"),
            Transaction(description="SPOTIFY PREMIUM", amount=Decimal("21.90"), value_date="2026-05-10", type="OUTFLOW", status="PROCESSED", account=self.accounts[2], category="Apps, Software and Cloud Services", subcategory="Movie & Audio"),
            Transaction(description="DISNEY PLUS BR", amount=Decimal("33.90"), value_date="2026-05-11", type="OUTFLOW", status="PROCESSED", account=self.accounts[2], category="Online Platforms & Leisure", subcategory="Streaming"),
            Transaction(description="AMAZON PRIME BR", amount=Decimal("14.90"), value_date="2026-05-12", type="OUTFLOW", status="PROCESSED", account=self.accounts[2], category="Online Platforms & Leisure", subcategory="Streaming"),
            Transaction(description="ICLOUD.COM/BILL", amount=Decimal("9.90"), value_date="2026-05-13", type="OUTFLOW", status="PROCESSED", account=self.accounts[2], category="Online Platforms & Leisure", subcategory="Cloud Storage"),
            Transaction(description="VIVO FIBRA INTERNET", amount=Decimal("129.90"), value_date="2026-05-14", type="OUTFLOW", status="PROCESSED", account=self.accounts[0], category="Bills & Utilities", subcategory="Internet"),
            Transaction(description="CLARO TELECOM MOVEL", amount=Decimal("89.90"), value_date="2026-05-15", type="OUTFLOW", status="PROCESSED", account=self.accounts[0], category="Bills & Utilities", subcategory="Mobile"),
            Transaction(description="ALUGUEL APARTAMENTO", amount=Decimal("2300"), value_date="2026-05-11", type="OUTFLOW", status="PROCESSED", account=self.accounts[0], category="Housing", subcategory="Rent"),
            Transaction(description="PADARIA DO BAIRRO", amount=Decimal("25"), value_date="2026-05-22", type="OUTFLOW", status="PROCESSED", account=self.accounts[0], category="Food & Groceries", subcategory="Bakery & Coffee"),
            Transaction(description="UBER TRIP", amount=Decimal("45"), value_date="2026-05-22", type="OUTFLOW", status="PROCESSED", account=self.accounts[2], category="Transport", subcategory="Ride sharing"),
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
        if filters.get("value_date__gte"):
            result = [tx for tx in result if tx.value_date >= filters["value_date__gte"]]
        if filters.get("value_date__lte"):
            result = [tx for tx in result if tx.value_date <= filters["value_date__lte"]]
        if filters.get("amount__gt"):
            result = [tx for tx in result if tx.amount > Decimal(str(filters["amount__gt"]))]
        return result


def answer(question: str):
    return asyncio.run(FinancialSpecialistAgent(client=FilterClient()).answer(question))


def test_pix_list_includes_inflows_and_outflows() -> None:
    result = answer("show me only PIX transactions")
    assert result.workflow == "transaction_query_list"
    assert result.metadata["parsed_intent"]["payment_method_filter"] == "pix"
    assert result.metadata["parsed_intent"]["direction"] == "BOTH"
    assert result.metadata["transactions_after_filtering"] == 2
    assert "PIX ENVIADO" in result.answer
    assert "PIX RECEBIDO" in result.answer


def test_pix_sent_and_received_totals_infer_direction() -> None:
    sent = answer("how much did I send by PIX?")
    received = answer("quanto recebi por PIX?")
    assert sent.workflow == "transaction_query_total"
    assert sent.metadata["parsed_intent"]["direction"] == "OUTFLOW"
    assert "R$ 100,00" in sent.answer
    assert received.metadata["parsed_intent"]["direction"] == "INFLOW"
    assert "R$ 250,00" in received.answer


def test_credit_card_transactions_use_card_account_and_exclude_bill_payment() -> None:
    result = answer("show me all credit card transactions")
    assert result.workflow == "transaction_query_list"
    assert result.metadata["parsed_intent"]["account_filter"]["account_ids"] == ["nub"]
    assert "MAGALU LOJA ONLINE" in result.answer
    assert "IFOOD*BURGER" in result.answer
    assert "PAGAMENTO FATURA NUBANK" not in result.answer


def test_biggest_card_charge_returns_single_card_transaction() -> None:
    result = answer("what was my biggest card charge?")
    assert result.workflow == "transaction_query_biggest"
    assert "R$ 300,00" in result.answer
    assert "MAGALU LOJA ONLINE" in result.answer
    assert "PAGAMENTO FATURA NUBANK" not in result.answer


def test_nubank_card_vs_bill_payment_interpretation() -> None:
    card = answer("show me all Nubank transactions")
    bill = answer("what was my last Nubank payment?")
    assert card.metadata["parsed_intent"]["account_filter"]["account_ids"] == ["nub"]
    assert "PAGAMENTO FATURA NUBANK" not in card.answer
    assert "PAGAMENTO FATURA NUBANK" in bill.answer
    assert bill.metadata["parsed_intent"]["description_contains"] == ["NUBANK"]


def test_itau_account_type_filters_use_account_metadata() -> None:
    checking = answer("show me Itau checking expenses")
    savings = answer("show me Itau savings transactions")
    assert checking.metadata["parsed_intent"]["account_filter"]["account_ids"] == ["chk"]
    assert "TARIFA CONTA" in checking.answer
    assert "MAGALU LOJA ONLINE" not in checking.answer
    assert savings.metadata["parsed_intent"]["account_filter"]["account_ids"] == ["sav"]
    assert "TRANSFERENCIA RECEBIDA POUPANCA" in savings.answer


def test_latest_expense_does_not_default_to_today() -> None:
    intent = parse_transaction_intent("what was my latest expense?")
    assert intent.metric == "latest"
    assert intent.direction == "OUTFLOW"
    assert intent.date_range is None

    result = answer("what was my latest expense?")
    assert "today" not in result.answer.lower()
    assert "no processed outflow transactions today" not in result.answer.lower()
    assert "2026-05-22" in result.answer


def test_smallest_expense_returns_single_transaction_not_full_list() -> None:
    intent = parse_transaction_intent("what was my smallest expense?")
    assert intent.metric == "smallest"
    assert intent.direction == "OUTFLOW"

    result = answer("what was my smallest expense?")
    assert result.workflow == "transaction_query_smallest"
    assert result.metadata["final_answer_metric"] == "smallest"
    assert len(result.evidence) == 1
    assert result.evidence[0].description == "ICLOUD.COM/BILL"
    assert "Your smallest processed expense" in result.answer
    assert "| Date | Amount |" not in result.answer


def test_show_me_smallest_expense_still_returns_single_transaction() -> None:
    result = answer("show me my smallest expense?")
    assert result.workflow == "transaction_query_smallest"
    assert len(result.evidence) == 1
    assert result.evidence[0].description == "ICLOUD.COM/BILL"


def test_exact_day_transaction_dates_parse_as_single_day() -> None:
    for prompt in [
        "show me my payments on 22 of May",
        "liste meus gastos em 22 de maio",
        "me mostre meus pagamentos em 22 de maio",
    ]:
        intent = parse_transaction_intent(prompt)
        assert intent.metric == "list"
        assert intent.direction == "OUTFLOW"
        assert intent.date_range
        assert intent.date_range.start == "2026-05-22"
        assert intent.date_range.end == "2026-05-22"

        result = answer(prompt)
        assert result.evidence
        assert all(item.date == "2026-05-22" for item in result.evidence)


def test_month_only_still_parses_as_full_month() -> None:
    assert parse_date_range("show me expenses in May").start == "2026-05-01"
    assert parse_date_range("show me expenses in May").end == "2026-05-31"
    assert parse_date_range("qual foi meu maior gasto em maio").start == "2026-05-01"
    assert parse_date_range("qual foi meu maior gasto em maio").end == "2026-05-31"
    assert parse_date_range("what was my latest expense?") is None
    assert parse_date_range("how much did I spend on Netflix?") is None


def test_netflix_prompts_apply_text_filter_before_metric() -> None:
    for prompt in [
        "show me all Netflix transactions",
        "show me Netflix payments",
        "how much did I spend on Netflix?",
    ]:
        intent = parse_transaction_intent(prompt)
        assert "NETFLIX" in [keyword.upper() for keyword in intent.description_contains]
        assert intent.date_range is None

    listed = answer("show me all Netflix transactions")
    assert listed.evidence
    assert all("NETFLIX" in (item.description or "").upper() for item in listed.evidence)
    assert "ALUGUEL" not in listed.answer
    assert "PAGAMENTO FATURA" not in listed.answer

    total = answer("how much did I spend on Netflix?")
    assert total.workflow == "transaction_query_total"
    assert "R$ 39,90" in total.answer
    assert all("NETFLIX" in (item.description or "").upper() for item in total.evidence)


def test_pix_received_intent_is_inflow_with_text_filter() -> None:
    intent = parse_transaction_intent("quanto recebi por PIX?")
    assert intent.metric == "total"
    assert intent.direction == "INFLOW"
    assert "PIX" in [keyword.upper() for keyword in intent.description_contains]


def test_subscription_total_excludes_rent_and_uses_transaction_query() -> None:
    intent = parse_transaction_intent("how much did I spend on subscriptions?")
    assert intent.metric == "total"
    assert intent.direction == "OUTFLOW"
    assert intent.category_intent == "subscriptions"

    result = answer("how much did I spend on subscriptions?")
    assert result.workflow == "transaction_query_total"
    assert "likely subscription spending" in result.answer
    assert all("ALUGUEL" not in (item.description or "").upper() for item in result.evidence)
    assert all("RENT" not in f"{item.category or ''} {item.subcategory or ''}".upper() for item in result.evidence)


def test_below_amount_filter_is_client_side_less_than() -> None:
    intent = parse_transaction_intent("show me all expenses below R$ 100")
    assert intent.metric == "list"
    assert intent.direction == "OUTFLOW"
    assert intent.amount_lt == Decimal("100")

    result = answer("show me all expenses below R$ 100")
    assert result.evidence
    assert all(item.amount < Decimal("100") for item in result.evidence)
    assert all(item.type == "OUTFLOW" for item in result.evidence)
    assert "ALUGUEL APARTAMENTO" not in result.answer


def test_group_by_account_prompts_parse_correctly() -> None:
    prompts = [
        "split my expenses per account",
        "break down my spending by account",
        "show my expenses grouped by account",
        "quanto gastei por conta?",
        "separe meus gastos por conta",
    ]

    for prompt in prompts:
        intent = parse_transaction_intent(prompt)
        assert intent.metric == "group_by_account"
        assert intent.direction == "OUTFLOW"
        assert intent.date_range is None


def test_graph_by_account_prompts_parse_correctly() -> None:
    prompts = [
        "show me a graph of my expenses by account",
        "show me a chart of my spending per account",
        "show me my expenses per account",
        "show me spending by account",
        "plot my expenses by account",
        "graph my expenses grouped by account",
        "mostre um gráfico dos meus gastos por conta",
        "mostre meus gastos por conta",
        "faça um gráfico por conta dos meus gastos",
        "gastos por conta",
    ]

    for prompt in prompts:
        intent = parse_transaction_intent(prompt)
        assert intent.metric == "group_by_account"
        assert intent.direction == "OUTFLOW"
        assert intent.date_range is None


def test_pie_chart_by_account_prompts_parse_correctly() -> None:
    prompts = [
        "show me a pie chart of my expenses by account",
        "show me a pizza chart of my expenses by account",
        "faça um gráfico de pizza dos meus gastos por conta",
        "mostre um gráfico de pizza dos meus gastos por conta",
    ]

    for prompt in prompts:
        intent = parse_transaction_intent(prompt)
        assert intent.metric == "group_by_account"
        assert intent.chart_type == "pie"


def test_bar_chart_default_for_graph_by_account() -> None:
    intent = parse_transaction_intent("show me a graph of my expenses by account")
    assert intent.metric == "group_by_account"
    assert intent.chart_type == "bar"


def test_plain_group_by_account_has_no_chart_type() -> None:
    intent = parse_transaction_intent("gastos por conta")
    assert intent.metric == "group_by_account"
    assert intent.chart_type is None


def test_group_by_account_formatter_separates_nubank_and_itau() -> None:
    for prompt in [
        "split my expenses per account",
        "break down my spending by account",
        "quanto gastei por conta?",
    ]:
        result = answer(prompt)
        assert result.workflow == "transaction_query_group_by_account"
        assert result.metadata["final_answer_metric"] == "group_by_account"
        assert "today" not in result.answer.lower()
        assert "| Account | Institution | Transactions | Total | Share |" in result.answer
        assert "Conta Corrente Itau" in result.answer
        assert "Nubank Mastercard" in result.answer


def test_group_by_account_chart_prompts_return_chart_spec() -> None:
    bar = answer("show me a graph of my expenses by account")
    pie = answer("show me a pie chart of my expenses by account")

    assert bar.workflow == "transaction_query_group_by_account"
    assert bar.chart is not None
    assert bar.chart.chart_type == "bar"
    assert "| Date | Amount | Type | Account | Description | Category |" not in bar.answer

    assert pie.workflow == "transaction_query_group_by_account"
    assert pie.chart is not None
    assert pie.chart.chart_type == "pie"
    assert "Conta Corrente Itau" in pie.answer
    assert "Nubank Mastercard" in pie.answer


def test_category_chart_prompts_parse_correctly() -> None:
    cases = [
        ("show me a graph per category of my expenses", "bar"),
        ("show me a chart by category of my expenses", "bar"),
        ("show me my spending by category", None),
        ("mostre um gráfico dos meus gastos por categoria", "bar"),
        ("gastos por categoria", None),
        ("show me a pie chart of my expenses by category", "pie"),
        ("mostre um gráfico de pizza dos meus gastos por categoria", "pie"),
    ]

    for prompt, chart_type in cases:
        intent = parse_transaction_intent(prompt)
        assert intent.metric == "group_by_category"
        assert intent.direction == "OUTFLOW"
        assert intent.date_range is None
        assert intent.chart_type == chart_type


def test_group_by_category_returns_aggregated_rows_and_chart() -> None:
    result = answer("show me a graph per category of my expenses")

    assert result.workflow == "transaction_query_group_by_category"
    assert result.metadata["final_answer_metric"] == "group_by_category"
    assert result.chart is not None
    assert result.chart.chart_type == "bar"
    assert "| Category | Transactions | Total | Share |" in result.answer
    assert "| Date | Amount | Type | Account | Description | Category |" not in result.answer
    assert "today" not in result.answer.lower()


def test_group_by_category_pie_chart_prompt_returns_pie_chart() -> None:
    result = answer("mostre um gráfico de pizza dos meus gastos por categoria")

    assert result.workflow == "transaction_query_group_by_category"
    assert result.chart is not None
    assert result.chart.chart_type == "pie"
    assert "| Category | Transactions | Total | Share |" in result.answer


def test_subscription_list_prompts_parse_as_list() -> None:
    prompts = [
        "show me my subscriptions",
        "show me all subscription transactions",
        "list all my subscription payments",
        "liste minhas assinaturas",
        "me mostre todas as assinaturas",
    ]

    for prompt in prompts:
        intent = parse_transaction_intent(prompt)
        assert intent.metric == "list"
        assert intent.direction == "OUTFLOW"
        assert intent.category_intent == "subscriptions"


def test_subscription_total_prompts_parse_as_total() -> None:
    prompts = [
        "how much did I spend on subscriptions?",
        "quanto eu gastei com assinaturas?",
        "what is my total subscription spending?",
    ]

    for prompt in prompts:
        intent = parse_transaction_intent(prompt)
        assert intent.metric == "total"
        assert intent.direction == "OUTFLOW"
        assert intent.category_intent == "subscriptions"


def test_subscription_specific_prompts_parse_correctly() -> None:
    cases = [
        ("what was my biggest subscription payment?", "largest"),
        ("what was my smallest subscription payment?", "smallest"),
        ("what was my latest subscription payment?", "latest"),
        ("qual foi minha maior assinatura?", "largest"),
        ("qual foi minha menor assinatura?", "smallest"),
        ("qual foi minha assinatura mais recente?", "latest"),
    ]

    for prompt, metric in cases:
        intent = parse_transaction_intent(prompt)
        assert intent.metric == metric
        assert intent.direction == "OUTFLOW"
        assert intent.category_intent == "subscriptions"


def test_subscription_list_returns_rows_not_total() -> None:
    result = answer("show me all subscription transactions")
    assert result.workflow == "transaction_query_list"
    assert result.metadata["final_answer_metric"] == "list"
    assert "| Date | Amount | Account | Description | Category |" in result.answer
    for description in ["NETFLIX", "SPOTIFY", "DISNEY", "AMAZON PRIME", "ICLOUD", "VIVO FIBRA", "CLARO TELECOM"]:
        assert description in result.answer.upper()
    assert "ALUGUEL" not in result.answer
    assert "PAGAMENTO FATURA" not in result.answer
    assert "PIX ENVIADO" not in result.answer


def test_subscription_total_has_breakdown() -> None:
    result = answer("how much did I spend on subscriptions?")
    assert result.workflow == "transaction_query_total"
    assert "Breakdown by subscription" in result.answer
    assert "Largest examples" not in result.answer
    for description in ["NETFLIX", "SPOTIFY", "DISNEY", "AMAZON PRIME", "ICLOUD"]:
        assert description in result.answer.upper()


def test_subscription_specific_returns_single_transaction() -> None:
    result = answer("what was my biggest subscription payment?")
    assert result.workflow == "transaction_query_biggest"
    assert len(result.evidence) == 1
    assert "| Date |" not in result.answer
    assert "subscription payment" in result.answer


def test_portuguese_nubank_bill_prompts_parse_correctly() -> None:
    prompts = [
        "quando paguei a fatura Nubank?",
        "quando eu paguei a fatura Nubank?",
        "qual foi meu ultimo pagamento da fatura Nubank?",
    ]

    for prompt in prompts:
        intent = parse_transaction_intent(prompt)
        assert intent.metric == "latest"
        assert intent.direction == "OUTFLOW"
        assert intent.category_intent == "nubank_bill_payment"
        assert "NUBANK" in [keyword.upper() for keyword in intent.description_contains]


def test_portuguese_nubank_bill_latest_not_unsupported() -> None:
    result = answer("quando paguei a fatura Nubank?")
    assert result.workflow == "transaction_query_last"
    assert "unsupported" not in result.answer.lower()
    assert "NUBANK" in result.answer.upper()
    assert "FATURA" in result.answer.upper() or "PAGAMENTO" in result.answer.upper()
