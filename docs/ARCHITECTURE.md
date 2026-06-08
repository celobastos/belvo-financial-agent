# Architecture

## Chosen Stack

- Python 3.11+
- Pydantic for permissive typed domain models
- Streamlit for a minimal interactive UI
- pytest for tests
- python-dotenv for local configuration
- httpx for the thin MCP HTTP client

This stack is small, readable and easy for a reviewer to run in under 10 minutes. Streamlit matches the challenge brief because frontend polish is explicitly not required.

## Agent Framework Choice

Belvo uses Pydantic AI by default, but this implementation keeps the default runtime deterministic and dependency-light. The project uses Pydantic models plus a small `FinancialSpecialistAgent` orchestration layer that routes intent to deterministic workflows. This avoids making a reviewer configure an LLM key before seeing the core product work.

The conscious trade-off: there is less free-form agent reasoning, but the financial answers are more reproducible and easier to evaluate. The architecture leaves a clear place to add Pydantic AI summarization later.

## MCP Client Approach

`MCPClient` sends JSON-RPC requests to the Streamable HTTP endpoint at `MCP_URL`, defaulting to `http://localhost:8000/mcp`. It includes:

- bearer token auth from `MCP_TOKEN`;
- `initialize`, `tools/list` and `tools/call` requests;
- wrappers for `get_owners`, `list_accounts`, `list_transactions`;
- pagination guards;
- response normalization for plain lists, Belvo-style `{results: [...]}` and MCP content wrappers.

No public Belvo REST endpoints are called.

## Tool Boundaries

The application exposes only read-only financial tools. There are no wrappers, UI actions, eval cases or README examples for creating, updating or deleting financial data.

## Domain Model Design

The model layer treats Belvo fields as nullable and preserves raw payloads where useful. Main models:

- `Owner`
- `Institution`
- `AccountBalance`
- `CreditCardData`
- `Account`
- `Transaction`
- `TransactionEvidence`
- `FinancialAnswer`

Money is calculated as `Decimal` internally where practical and formatted as BRL at the answer boundary.

## Financial Calculation Workflows

`finance_workflows.py` owns arithmetic and filtering:

- `get_balance_summary`
- `get_food_spending`
- `detect_salary`
- `get_large_transactions`
- `detect_recurring_expenses`
- `refuse_mutation_request`

The workflows return structured `FinancialAnswer` objects with evidence and metadata, not just strings.

## Prompting Strategy

The default agent is rule-routed. Its policy mirrors the intended system prompt:

- ground every answer in tool results;
- never mutate financial data;
- use processed transactions by default;
- use `value_date` for natural-language date ranges;
- use transaction `type` for direction;
- disclose category heuristics;
- treat credit-card current balance as debt/spending.

If an LLM layer is added later, it should summarize structured workflow output rather than doing raw arithmetic over transactions.

## Eval Strategy

The eval runner executes representative questions through the same agent path used by the UI. It writes `evals/results.md` with:

- question;
- answer;
- workflow used;
- filters and basis;
- evidence;
- correctness note.

This is a spot-check harness rather than a full benchmark, matching the challenge scope.

## Observability and Logging

The app logs request metadata, selected workflows, filter summaries and errors through standard Python logging. It avoids logging secrets. Eval output provides a durable run artifact.

## Trade-Offs

- Deterministic routing over a full LLM planner keeps the demo reliable and easy to test.
- The MCP client is intentionally thin instead of depending on fragile framework glue.
- Recurring-expense detection is heuristic and explainable, not a dedicated ML model.
- The UI is intentionally simple.
- The default path does not require an LLM API key; the README explains how to extend the agent layer.
