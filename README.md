# Belvo Financial Specialist Agent

Read-only Financial Specialist Agent for Belvo's Software Engineer, Applied AI take-home challenge.

The app lets a user ask natural-language questions about synthetic Open Finance data exposed by Belvo's local mock MCP server. It answers with grounded account and transaction information, refuses write operations, and keeps financial calculations deterministic and auditable.

No real Belvo production credentials are used. No real customer data is used. The dataset is synthetic and lives inside the local MCP server container.

## What the app does

The agent can answer questions about:

- account balances and net position;
- expenses and income;
- PIX sent and received;
- credit-card charges;
- subscriptions breakdowns;
- exact dates, month ranges and common natural date windows;
- spending grouped by account or category;
- bar and pie charts for account/category breakdowns.

The app is read-only by design. It refuses mutation requests such as:

```text
make a payment
transfer R$ 100 to Joao
delete this transaction
update my balance
```

## Requirements

- Python 3.11+
- Docker, for the mock Open Finance MCP server
- Optional: an Anthropic API key for the answer-polish layer

## Setup

### Windows PowerShell

```powershell
cd "C:\Users\marce\OneDrive\Documentos\New project\belvo-financial-agent"
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
copy .env.example .env
```

### macOS/Linux

```bash
cd belvo-financial-agent
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
cp .env.example .env
```

## Environment variables

The app reads configuration from `.env` through `pydantic-settings`. The repository includes a safe `.env.example`; do not commit real API keys.

```env
MCP_URL=http://localhost:8000/mcp
MCP_TOKEN=belvo-demo-token

MODEL_PROVIDER=anthropic
MODEL_NAME=claude-haiku-4-5
ANTHROPIC_API_KEY=your_anthropic_key_here
ENABLE_LLM_POLISH=true
LLM_POLISH_MAX_TOKENS=350

ENABLE_STREAMING=true
LOG_LEVEL=INFO
MCP_MAX_PAGES=20
MCP_PAGE_SIZE=100
```

Only Anthropic is currently wired for LLM calls. `OPENAI_API_KEY` is not used by the current codebase.

The financial workflows are provider-independent. Changing or disabling the model provider affects final response phrasing only; it does not affect transaction retrieval, filtering, aggregation, totals, percentages, or chart values.

Set either of these to run without any LLM call:

```env
MODEL_PROVIDER=none
ENABLE_LLM_POLISH=false
```

## Run the mock MCP server

```bash
docker pull gniparcs/intelligence-se-hiring-ofda-mcp:latest
docker run -d -p 8000:8000 --name ofda-mcp gniparcs/intelligence-se-hiring-ofda-mcp:latest
curl http://localhost:8000/health
```

Expected health response:

```json
{"status":"ok"}
```

MCP configuration:

```text
MCP endpoint: http://localhost:8000/mcp
Authorization header: Bearer belvo-demo-token
```

The synthetic dataset is inside the MCP server container. The app accesses it through MCP tools, not through local CSV or JSON files.

### MCP tools used

```text
get_owners
list_accounts
list_transactions
```

- `get_owners`: identifies the synthetic user/owner.
- `list_accounts`: retrieves account metadata, balances, account types and institutions.
- `list_transactions`: retrieves transactions with filters and pagination.

You can probe the MCP connection with:

```bash
python -m belvo_finance_agent.mcp_probe
```

## Run the app

```bash
python -m streamlit run src/belvo_finance_agent/app_streamlit.py
```

Streamlit usually opens:

```text
http://localhost:8501
```

The UI includes a `Show evidence and filters` toggle. When enabled, it exposes workflow metadata, filters, loaded skill context and result metadata for reviewer inspection.

## Run tests and evals

Run the unit/regression suite:

```bash
pytest
```

Run the built-in spot-check eval runner:

```bash
python -m belvo_finance_agent.eval_runner
```

The eval runner writes:

```text
evals/results.md
```

Additional manual validation artifacts are stored under `evals/`, including chart prompt checks and Anthropic polish checks. `evals/questions.yaml` is a prompt reference file; the current eval runner uses its own representative prompt list in `src/belvo_finance_agent/eval_runner.py`.

The tests cover:

- text normalization and date parsing;
- transaction intent parsing in English and Portuguese;
- deterministic filters for PIX, Netflix, subscriptions, Nubank bill payments, card charges and amount thresholds;
- grouped spending by account and category;
- chart intent parsing for bar and pie charts;
- BRL formatting, balance summaries, food/salary heuristics and recurring expense detection;
- optional Anthropic answer-polish fallbacks;
- read-only mutation refusal without MCP or LLM calls.

## Architecture

The app is a grounded, read-only financial analysis pipeline. It is not a free-form autonomous finance bot.

```text
User question
  -> FinancialSpecialistAgent
  -> deterministic intent parser / router
  -> MCP client
  -> get_owners / list_accounts / list_transactions
  -> local filtering, grouping, totals and evidence
  -> FinancialAnswer result object
  -> optional Anthropic Haiku polish
  -> Streamlit text, table, chart and evidence rendering
```

Text diagram:

```text
+-------------+
| User prompt |
+------+------+
       |
       v
+----------------------+
| Intent parser/router |
| metric + safety      |
+------+---------------+
       |
       v
+----------------------+
| MCP client           |
| read-only tools      |
+------+---------------+
       |
       v
+----------------------+
| Finance workflows    |
| filters + aggregates |
+------+---------------+
       |
       v
+----------------------+
| Result formatter     |
| text + chart + table |
+----------------------+
```

### Core layers

- `app_streamlit.py`: thin UI shell for chat input, answer rendering, charts and the evidence drawer.
- `agent.py`: top-level routing and read-only safety boundary. Mutation requests return immediately.
- `finance_workflows.py`: deterministic finance logic for parsing, filtering, grouping, totals, sorting and formatting.
- `mcp_client.py`: Streamable HTTP JSON-RPC client for the mock MCP server.
- `models.py`: Pydantic models for accounts, transactions, evidence, chart specs and final answers.
- `charts.py`: creates chart specs from deterministic grouped results.
- `response_polisher.py`: optional Anthropic Haiku pass that rewrites only final prose.
- `schema_context.py` and `docs/skills/`: compact schema/safety notes loaded on demand for evidence and prompt context.

## Architecture rationale

### Intent parsing before tool execution

The app first determines whether the user is asking for:

- a list;
- a total;
- a smallest/largest/latest transaction;
- grouped spending by account;
- grouped spending by category;
- chart output;
- a mutation request that must be refused.

This prevents different financial questions from being treated as generic transaction lists.

### Broad fetch plus client-side filtering

The MCP server supports filters, but the app also applies client-side filtering for correctness. This is especially important for:

- description filters such as Netflix and PIX;
- Portuguese and English category terms;
- exact-day date handling;
- amount thresholds;
- credit-card charge versus bill-payment distinction;
- subscription heuristics;
- grouping by actual account and institution metadata.

### Deterministic calculations

All monetary calculations are performed in Python code:

- sums;
- counts;
- percentages;
- account totals;
- category totals;
- subscription breakdowns;
- smallest/largest/latest sorting;
- chart values.

This matters because financial answers must be reproducible, auditable and grounded in actual transaction data.

### LLM used only where it adds value

The current code does not use an LLM planner. Intent parsing and financial calculations are deterministic. Anthropic Claude Haiku 4.5 is used only as an optional final wording polish layer after the deterministic `FinancialAnswer` already exists.

The LLM is not trusted to invent numbers, manually calculate totals, choose filters, call tools, or fabricate chart values.

### Read-only safety boundary

Only read-only MCP tools are wrapped. There are no create/update/delete/payment/transfer tools in the codebase. Mutation requests are refused before MCP or LLM calls.

### Why the architecture supports charts

The chart feature uses the same deterministic transaction-query pipeline as text answers. A chart request is parsed as a grouped metric, such as `group_by_account` or `group_by_category`, plus an optional `chart_type`. The backend computes totals, counts and shares before rendering. This keeps visualizations auditable and avoids relying on the model to infer or fabricate chart values.

## Model and framework choice

### Framework choice

This project does not use Pydantic AI. It uses:

- Pydantic models for typed, permissive account/transaction/result normalization;
- a small deterministic router in `agent.py`;
- regular Python workflow functions in `finance_workflows.py`;
- a thin `httpx` MCP client;
- optional Anthropic Messages API calls for final answer polish.

This was chosen because the assignment is not just an open-ended chatbot. Answers must be grounded in account and transaction data, and financial calculations need to be auditable. A deterministic workflow keeps the implementation small, testable and reviewer-friendly for the take-home scope.

Compared with heavier orchestration frameworks such as LangChain or LangGraph, this approach avoids extra graph abstraction and keeps the financial logic easy to inspect. Compared with a full LLM-agent planner, it reduces hallucination risk because routing, filtering, totals and chart values are all tested Python behavior.

Pydantic is still useful here: normalized account and transaction models make routing, filtering and evidence generation easier to test.

## Extra features implemented

### Skill-style context management

The agent keeps compact Open Finance reference notes in `docs/skills/` and loads relevant schema, filtering and safety context for each workflow or parsed transaction intent. This keeps context modular and auditable without injecting one giant schema prompt everywhere.

### Streaming

The Streamlit UI can stream the final answer text after MCP tool calls, filtering and deterministic calculations are complete. Set `ENABLE_STREAMING=false` to disable it.

### Charts and visual analytics

Supported chart-style prompts include:

```text
show me a graph per category of my expenses
show me a graph of my expenses by account
show me a pie chart of my expenses by category
mostre um grafico dos meus gastos por conta
gastos por categoria
```

Supported groupings:

- expenses by account;
- expenses by category;
- subscription spending by service;
- account/institution breakdown separating Nubank and Itau accounts;
- bar chart rendering for graph/chart/plot prompts;
- pie chart rendering for pie/pizza prompts.

Charts are rendered from the same transaction-query pipeline used for textual answers. The agent first fetches transactions, applies deterministic filters, groups the results, and only then renders a chart/table. This avoids asking the model to invent chart values.

### Advanced financial filters

Implemented filters and query types include:

- PIX sent/received;
- credit-card charges;
- Nubank card transactions;
- Nubank bill payments;
- amount thresholds such as below R$ 100 or above R$ 500;
- exact-day and month date filters;
- subscription detection;
- grouped spending by account/category.

### Multilingual support

The agent supports a pragmatic subset of English and Portuguese financial prompts, for example:

```text
quanto recebi por PIX?
quando paguei a fatura Nubank?
separe meus gastos por conta
mostre meus gastos por categoria
```

This is phrase/intent support for the challenge scope, not complete multilingual NLU coverage.

### Evidence and assumptions drawer

The UI can show workflow, tools used, filters, loaded skill context and metadata. This helps a reviewer inspect how an answer was produced.

### Anthropic Haiku inline polish

When configured, the app sends only a compact grounded payload to Claude Haiku 4.5 for readability. If the key is missing, invalid or rate-limited, the app falls back to the deterministic answer.

### Model and provider configuration

Anthropic is the only live LLM provider currently wired in the app.

```env
MODEL_PROVIDER=anthropic
MODEL_NAME=claude-haiku-4-5
ANTHROPIC_API_KEY=your_anthropic_key_here
ENABLE_LLM_POLISH=true
LLM_POLISH_MAX_TOKENS=350
```

Claude Haiku 4.5 was selected because this layer only needs low-cost language polish. The model does not perform financial reasoning.

### Anthropic message tuning

No model fine-tuning is performed in this project. The project uses message/prompt tuning: iterative improvements to deterministic routing rules, schema context, safety context and the Anthropic Messages API system prompt.

Message tuning improved:

- read-only refusal behavior;
- metric-specific answers such as smallest/largest/latest;
- Portuguese and English intent handling;
- subscription query formatting;
- chart/grouping requests;
- clearer responses explaining filters used.

Message/system prompt locations:

- `src/belvo_finance_agent/agent.py`: `SYSTEM_POLICY`, documenting the financial assistant policy.
- `src/belvo_finance_agent/response_polisher.py`: `POLISH_SYSTEM_PROMPT`, used by the Anthropic Messages API polish layer.
- `docs/skills/*.md`: compact Open Finance schema, filtering and safety context loaded by workflow.

## Chart example

Example prompt:

```text
show me a graph of my expenses by account
```

In the Streamlit app, this renders a bar chart plus a supporting grouped table. The chart is generated from grouped processed OUTFLOW transactions in the synthetic MCP dataset. The app first computes account totals deterministically, then renders the chart from the grouped result. The model does not generate chart values.

Expected flow:

```text
User prompt
-> parse metric = group_by_account, chart_type = bar
-> fetch processed transactions
-> group by account metadata
-> compute totals and shares
-> render chart + supporting table
```

Captured synthetic MCP account breakdown:

| Account | Institution | Transactions | Total | Share |
|---|---|---:|---:|---:|
| Conta Corrente Itau | itau_br_retail | 140 | R$ 46.126,71 | 74.4% |
| Nubank Mastercard | nubank_br_retail | 175 | R$ 15.892,37 | 25.6% |

`Poupanca Itau` is still modeled as a separate account in `list_accounts`; it does not appear in this spending chart because the captured processed OUTFLOW grouping had no savings-account expenses.

## Supported questions

### Balance

```text
What is my current balance across accounts?
Show my account balances.
```

### Spending

```text
How much did I spend in May?
What was my biggest expense last month?
What was my smallest expense?
Show me all expenses below R$ 100.
```

### PIX

```text
Show me only PIX transactions.
How much did I send by PIX?
Quanto recebi por PIX?
```

### Credit card

```text
Show me all credit card expenses.
What was my biggest card charge?
How much did I spend on the credit card in May?
```

### Nubank

```text
Show me all Nubank transactions.
When did I last pay Nubank?
Quando paguei a fatura Nubank?
```

### Subscriptions

```text
Show me all subscription transactions.
How much did I spend on subscriptions?
What was my biggest subscription payment?
```

### Grouping and charts

```text
Split my expenses per account.
Show me a graph of my expenses by account.
Show me a pie chart of my expenses by account.
Show me a graph per category of my expenses.
Show me a pie chart of my expenses by category.
Mostre um grafico dos meus gastos por conta.
Faca um grafico de pizza dos meus gastos por categoria.
```

### Read-only refusal

```text
Make a payment.
Transfer R$ 100 to Joao.
Delete this transaction.
```

## Evaluation and spot checks

| Question | Expected behavior | Correctness note |
|---|---|---|
| What is my current balance across accounts? | Lists balances by account and separates cash accounts from credit card balance. | Verified against `list_accounts`. |
| Show me transactions over R$ 500 last 90 days. | Lists processed transactions above the threshold in the date range. | Amount filtering applied client-side. |
| Show me all Netflix transactions. | Filters by description/merchant containing Netflix. | Client-side text filter. |
| Split my expenses per account. | Groups processed OUTFLOW transactions by account, separating Nubank and Itau. | Uses account metadata from `list_accounts`. |
| Show me a graph per category of my expenses. | Groups processed outflows by category and renders chart-ready totals. | Uses deterministic grouped transaction result. |
| Show me a pie chart of my expenses by account. | Groups processed outflows by account and renders a pie chart. | Chart values come from deterministic account grouping. |
| How much did I spend on subscriptions? | Totals subscription-like outflows and shows breakdown by service. | Heuristic classifier excludes rent, transfers, PIX, ATM and card bill payments. |
| What was my biggest subscription payment? | Returns one largest subscription-like transaction. | Metric-specific routing. |
| Quando paguei a fatura Nubank? | Returns the latest `PAGAMENTO FATURA NUBANK` outflow. | Portuguese bill-payment intent. |
| What was my smallest expense? | Returns one smallest processed outflow transaction. | Metric-specific routing, not a generic list. |
| Make a payment. | Refuses because the app is read-only. | Safety boundary. |

Current validation:

- `pytest`: covers deterministic parsing, filtering, grouping, charts, safety and LLM fallback behavior.
- `python -m belvo_finance_agent.eval_runner`: writes reviewer-friendly spot checks to `evals/results.md`.
- Manual prompt result files in `evals/`: preserve broader prompt sweeps used during development.

## Design decisions

### Read-only tool boundary

Only `get_owners`, `list_accounts` and `list_transactions` are wrapped. There are no mutation wrappers anywhere in the codebase.

### Credit-card handling

Checking and savings balances count as cash. Credit card `balance.current` is treated as spending/debt. Credit card available limit is not counted as cash.

### Date and status defaults

The app uses `value_date` for user-facing date ranges and `status=PROCESSED` by default. No date range means the full available dataset, not today, unless the user explicitly asks for today.

### Account metadata over text guesses

Account grouping and filters use account metadata from `list_accounts`, which keeps `Conta Corrente Itau`, `Poupanca Itau` and `Nubank Mastercard` separate.

### Heuristics

Food, salary, subscriptions and recurring expenses use categories first and description keywords when categories are missing or noisy.

## Trade-offs

- Deterministic workflows were favored over fully autonomous tool use for financial correctness.
- The Anthropic provider layer adds polish but requires careful environment-variable setup.
- Prompt/message tuning improves behavior but does not replace deterministic tests.
- Subscription classification is heuristic and may misclassify edge cases.
- Chart support is intentionally limited to account/category/service aggregations to avoid unsupported visual claims.
- Pydantic models provide typed structure without a heavy graph-orchestration layer.
- Client-side filtering compensates for possible MCP filter limitations.
- The UI was kept simple because the assignment focuses on agent behavior and correctness.
- The architecture favors correctness and explainability over broad autonomous-agent behavior.

## Conscious cuts

- No real model fine-tuning.
- No real payment initiation.
- No write operations by design.
- No real Belvo production API integration.
- No persistent user database.
- No multi-user support beyond the synthetic MCP dataset.
- No persistent conversation memory.
- No production authentication.
- No production deployment.
- No full observability stack.
- Limited chart types.
- Limited Portuguese/English phrase coverage.
- Heuristic subscription and merchant normalization.
- No exhaustive coverage of every possible finance question.
- No full Pydantic AI planner integration.

## Limitations and future improvements

- More robust multilingual parsing.
- Better merchant and category normalization.
- Stronger subscription and recurring-expense detection.
- A larger eval suite with golden expected outputs.
- Better UI/UX and richer chart interactivity.
- Full tool-call tracing in the UI.
- Confidence scoring for heuristic classifications.
- Richer streaming that starts earlier while still preserving grounded final answers.
- Integration with real Belvo sandbox or production APIs if credentials and scope were provided.
- Deployment, auth, CI/CD and production observability.

## Use of coding agents

Codex and ChatGPT were used to accelerate implementation planning, regression-test generation, manual prompt validation, documentation drafting and iterative bug fixing. The final design decisions, validation and correctness checks were reviewed by the author. Coding agents were especially useful for turning prompt failures into regression tests and keeping README claims aligned with actual code behavior.

## Project structure

```text
src/belvo_finance_agent/
  agent.py               top-level router and safety boundary
  app_streamlit.py       Streamlit UI
  charts.py              chart spec generation
  config.py              environment configuration
  eval_runner.py         spot-check eval runner
  finance_workflows.py   deterministic finance workflows
  mcp_client.py          MCP Streamable HTTP client
  models.py              Pydantic models
  response_polisher.py   optional Anthropic answer polish
  schema_context.py      skill-style context loader
docs/
  skills/                compact Open Finance and safety reference notes
  assets/                README chart images
evals/                   eval runner and manual prompt artifacts
tests/                   unit/regression tests
```
