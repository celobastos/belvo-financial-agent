from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Iterable

from .models import TransactionQueryIntent


SKILL_DOCS_DIR = Path(__file__).resolve().parents[2] / "docs" / "skills"


@dataclass(frozen=True)
class SkillContext:
    name: str
    content: str


class SkillContextLoader:
    def __init__(self, docs_dir: Path = SKILL_DOCS_DIR) -> None:
        self.docs_dir = docs_dir

    def load(self, names: Iterable[str]) -> list[SkillContext]:
        return [SkillContext(name=name, content=self._read(name)) for name in dict.fromkeys(names)]

    def load_for_workflow(self, workflow: str) -> list[SkillContext]:
        if workflow == "balance_summary":
            return self.load(["open_finance_overview", "accounts_schema", "balances_semantics", "safety_read_only"])
        if workflow == "read_only_refusal":
            return self.load(["open_finance_overview", "safety_read_only"])
        if workflow in {"food_spending", "spending_summary", "large_transactions", "cash_flow_last_month"}:
            return self.load(["open_finance_overview", "transactions_schema", "filtering_rules", "safety_read_only"])
        if workflow in {"salary_detection", "recurring_expense_detection"}:
            return self.load(["open_finance_overview", "transactions_schema", "filtering_rules", "safety_read_only"])
        return self.load(["open_finance_overview", "safety_read_only"])

    def load_for_transaction_intent(self, intent: TransactionQueryIntent) -> list[SkillContext]:
        names = ["open_finance_overview", "transactions_schema", "filtering_rules", "safety_read_only"]
        if intent.account_filter or intent.metric == "group_by_account" or intent.payment_method_filter == "credit_card":
            names.insert(2, "accounts_schema")
        if intent.category_intent == "nubank_bill_payment":
            names.insert(2, "accounts_schema")
        return self.load(names)

    def names_for_workflow(self, workflow: str) -> list[str]:
        return [context.name for context in self.load_for_workflow(workflow)]

    def names_for_transaction_intent(self, intent: TransactionQueryIntent) -> list[str]:
        return [context.name for context in self.load_for_transaction_intent(intent)]

    @lru_cache(maxsize=16)
    def _read(self, name: str) -> str:
        path = self.docs_dir / f"{name}.md"
        return path.read_text(encoding="utf-8").strip()


def compact_context_block(contexts: list[SkillContext]) -> str:
    return "\n\n".join(f"[{context.name}]\n{context.content}" for context in contexts)


def loaded_skill_names(contexts: list[SkillContext]) -> list[str]:
    return [context.name for context in contexts]
