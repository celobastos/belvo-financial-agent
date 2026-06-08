from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Literal

try:
    from pydantic import BaseModel, ConfigDict, Field, field_validator
except ModuleNotFoundError:
    ConfigDict = dict

    class _Field:
        def __init__(self, default: Any = None, default_factory: Any = None, **_: Any) -> None:
            self.default = default
            self.default_factory = default_factory

        def get_default(self) -> Any:
            if self.default_factory:
                return self.default_factory()
            return self.default

    def Field(default: Any = None, default_factory: Any = None, **kwargs: Any) -> Any:
        return _Field(default=default, default_factory=default_factory, **kwargs)

    def field_validator(*_: Any, **__: Any) -> Any:
        def decorator(fn: Any) -> Any:
            return fn

        return decorator

    class BaseModel:
        def __init__(self, **data: Any) -> None:
            annotations: dict[str, Any] = {}
            for cls in reversed(self.__class__.mro()):
                annotations.update(getattr(cls, "__annotations__", {}))
            for name in annotations:
                default = getattr(self.__class__, name, None)
                if name in data:
                    value = data.pop(name)
                elif isinstance(default, _Field):
                    value = default.get_default()
                else:
                    value = default
                setattr(self, name, value)
            for name, value in data.items():
                setattr(self, name, value)

        def model_dump(self, mode: str = "python") -> dict[str, Any]:
            def dump(value: Any) -> Any:
                if isinstance(value, BaseModel):
                    return value.model_dump(mode=mode)
                if isinstance(value, list):
                    return [dump(item) for item in value]
                if isinstance(value, Decimal):
                    return str(value) if mode == "json" else value
                return value

            return {key: dump(value) for key, value in self.__dict__.items()}


class FlexibleModel(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)


class Institution(FlexibleModel):
    name: str | None = None
    type: str | None = None


class AccountBalance(FlexibleModel):
    current: Decimal | None = None
    available: Decimal | None = None
    blocked: Decimal | None = None
    automatically_invested: Decimal | None = None


class CreditCardData(FlexibleModel):
    credit_limit: Decimal | None = None
    cutting_date: str | None = None
    payment_due_date: str | None = None


class Owner(FlexibleModel):
    id: str | None = None
    display_name: str | None = None
    social_name: str | None = None
    document_id: dict[str, Any] | None = None
    raw: dict[str, Any] = Field(default_factory=dict)


class Account(FlexibleModel):
    id: str | None = None
    link: str | None = None
    institution: Institution | dict[str, Any] | None = None
    category: str | None = None
    balance_type: str | None = None
    type: str | None = None
    subtype: str | None = None
    name: str | None = None
    number: str | None = None
    balance: AccountBalance | dict[str, Any] | None = None
    currency: str | None = "BRL"
    internal_identification: str | None = None
    credit_data: CreditCardData | dict[str, Any] | None = None
    raw: dict[str, Any] = Field(default_factory=dict)

    def __init__(self, **data: Any) -> None:
        super().__init__(**data)
        if isinstance(self.institution, dict):
            self.institution = Institution(**self.institution)
        if isinstance(self.balance, dict):
            self.balance = AccountBalance(**self.balance)
        if isinstance(self.credit_data, dict):
            self.credit_data = CreditCardData(**self.credit_data)

    @field_validator("institution", mode="before")
    @classmethod
    def parse_institution(cls, value: Any) -> Any:
        if isinstance(value, dict):
            return Institution(**value)
        return value

    @field_validator("balance", mode="before")
    @classmethod
    def parse_balance(cls, value: Any) -> Any:
        if isinstance(value, dict):
            return AccountBalance(**value)
        return value

    @field_validator("credit_data", mode="before")
    @classmethod
    def parse_credit_data(cls, value: Any) -> Any:
        if isinstance(value, dict):
            return CreditCardData(**value)
        return value

    @property
    def display_name(self) -> str:
        if self.name:
            return self.name
        if isinstance(self.institution, Institution) and self.institution.name:
            suffix = self.category or self.type or "account"
            return f"{self.institution.name} {suffix}"
        return self.id or "Unknown account"


class Transaction(FlexibleModel):
    id: str | None = None
    internal_identification: str | None = None
    account: Account | dict[str, Any] | str | None = None
    value_date: str | None = None
    accounting_date: str | None = None
    amount: Decimal = Decimal("0")
    currency: str | None = "BRL"
    description: str | None = None
    merchant: dict[str, Any] | None = None
    category: str | None = None
    subcategory: str | None = None
    type: Literal["INFLOW", "OUTFLOW"] | str | None = None
    status: str | None = None
    credit_card_data: dict[str, Any] | None = None
    raw: dict[str, Any] = Field(default_factory=dict)

    def __init__(self, **data: Any) -> None:
        super().__init__(**data)
        if isinstance(self.account, dict):
            self.account = Account(**self.account)
        self.amount = Decimal(str(self.amount or "0"))

    @field_validator("account", mode="before")
    @classmethod
    def parse_account(cls, value: Any) -> Any:
        if isinstance(value, dict):
            return Account(**value)
        return value

    @property
    def account_name(self) -> str:
        if isinstance(self.account, Account):
            return self.account.display_name
        if isinstance(self.account, str):
            return self.account
        return "Unknown account"


class TransactionEvidence(FlexibleModel):
    date: str | None = None
    amount: Decimal | None = None
    type: str | None = None
    account: str | None = None
    description: str | None = None
    category: str | None = None
    subcategory: str | None = None


class ChartSpec(FlexibleModel):
    chart_type: Literal["bar", "line", "pie"]
    title: str
    x_label: str
    y_label: str
    data: list[dict[str, Any]] = Field(default_factory=list)


class FinancialAnswer(FlexibleModel):
    question: str
    answer: str
    workflow: str
    tools_used: list[str] = Field(default_factory=list)
    filters: dict[str, Any] = Field(default_factory=dict)
    evidence: list[TransactionEvidence] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    caveats: list[str] = Field(default_factory=list)
    chart: ChartSpec | None = None


@dataclass
class DateRange:
    start: str
    end: str
    label: str


@dataclass
class AccountFilter:
    account_ids: list[str] | None = None
    institution_names: list[str] | None = None
    account_categories: list[str] | None = None
    account_name_contains: list[str] | None = None


@dataclass
class TransactionQueryIntent:
    metric: Literal[
        "list",
        "total",
        "largest",
        "smallest",
        "latest",
        "group_by_account",
        "group_by_category",
        "group_by_merchant",
    ]
    direction: Literal["OUTFLOW", "INFLOW", "BOTH"]
    date_range: DateRange | None
    account_filter: AccountFilter | None
    payment_method_filter: Literal["pix", "credit_card", None]
    institution_filter: str | None
    description_contains: list[str]
    category_intent: str | None
    include_bill_payments: bool
    amount_gt: Decimal | None = None
    amount_gte: Decimal | None = None
    amount_lt: Decimal | None = None
    amount_lte: Decimal | None = None
    chart_type: Literal["bar", "pie", None] = None
    status: str = "PROCESSED"
