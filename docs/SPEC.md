# Specification

## Product Goal

Build a read-only financial specialist agent for one synthetic Open Finance user. The user asks natural-language questions about accounts, balances, income and transactions. The application answers with grounded calculations from the local Belvo MCP server.

## Target User

The target user is an end user of a fintech or bank that uses Open Finance data. They want practical answers such as balances, spending totals, salary confirmation, large transaction review and recurring expense detection without reading raw statements.

## In-Scope Questions

- Current cash balance, credit card spending and net position.
- Spending by category or merchant over a date range.
- Salary or income detection for the current month.
- Large transactions over a threshold.
- Biggest likely recurring expense.
- Read-only explanations of the data basis, filters and caveats.

## Explicitly Out of Scope

- Creating, updating or deleting owners, accounts, balances or transactions.
- Simulating payments, transfers, card charges or balance changes.
- Direct calls to public Belvo REST APIs.
- Production deployment, auth, CI, full frontend polish or full benchmark coverage.
- Treating credit card available limit as cash.

## Read-Only Scope

The only financial-data tools exposed to the app are:

- `get_owners`
- `list_accounts`
- `list_transactions`

Local writes are limited to application artifacts such as logs, eval results and generated reports. If the user requests a mutation, the agent refuses and offers read-only analysis instead.

## MCP Tools

### `get_owners`

Retrieves owner/person data for the synthetic user. Use it for identity questions, optional personalization and data-scope checks.

### `list_accounts`

Retrieves available accounts and balances. Use it for balance summaries, account discovery and credit-card metadata.

### `list_transactions`

Retrieves transactions with Belvo-style filters such as date ranges, amount thresholds, account, category, type, status, description substring and pagination. Use it for spending, income, large transactions and recurrence workflows.

## Required User-Facing Behavior

- Answer concisely with a financial summary first.
- Include the basis of calculation: date range, accounts considered, transaction status, filters and heuristic use.
- Use BRL formatting.
- Use `value_date` for user-facing date ranges unless the user asks for accounting/posting dates.
- Use `status=PROCESSED` by default.
- Use `OUTFLOW` for spending and `INFLOW` for income.
- Separate checking/savings cash from credit card spending/debt.
- Refuse financial-data mutation requests.

## Data-Grounding Rules

- Never invent owners, accounts, balances, transactions, dates, descriptions or categories.
- Deterministic code performs raw arithmetic and filtering.
- The agent layer selects the workflow and formats the explanation.
- Category fields are preferred when present.
- Description heuristics are allowed for messy data and must be disclosed.
- Null fields remain unknown; the app should not fill them with guesses.

## Error Handling

- MCP unavailable: show the Docker command and health-check instructions.
- Tool failure: return a clear error with the tool name and a concise recovery step.
- Empty result set: explain that no matching data was found and show the filters.
- Pagination/schema mismatch: handle arrays, `{results: [...]}` and common MCP content wrappers defensively.
- Ambiguous question: choose a sensible default and state it.

## Acceptance Criteria

- Planning docs exist and define read-only scope.
- `.env.example`, `pyproject.toml`, package code, tests, eval files and README exist.
- App connects to `http://localhost:8000/mcp` with bearer auth.
- Only read-only MCP wrappers are implemented.
- The five representative workflows return structured results.
- Mutation requests are refused without MCP mutation calls.
- Eval runner writes `evals/results.md`.
- Tests cover heuristics, read-only routing, balance logic and recurrence grouping.
- README includes setup, Docker MCP instructions, run commands, trade-offs, cuts and AI-agent usage note.
