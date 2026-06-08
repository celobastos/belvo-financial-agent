# Tasks

## Phase 1 - Project setup
- [x] Create isolated `belvo-financial-agent` project folder. Verification: `dir belvo-financial-agent`.
- [x] Add planning docs. Verification: `dir belvo-financial-agent\docs`.
- [x] Add Python project config and environment template. Verification: `python -m pip install -e .`.

## Phase 2 - MCP connectivity
- [x] Implement configurable MCP URL/token. Verification: `python -m belvo_finance_agent.mcp_probe`.
- [x] Implement read-only wrappers for `get_owners`, `list_accounts`, `list_transactions`. Verification: unit tests and probe script.
- [x] Add response normalization and pagination guard. Verification: mocked tests.

## Phase 3 - Domain models and validation
- [x] Add Pydantic models for owners, accounts, transactions and answers. Verification: `pytest`.
- [x] Treat nullable fields permissively. Verification: mocked payload tests.

## Phase 4 - Deterministic financial workflows
- [x] Implement balance summary. Verification: `pytest tests/test_finance_workflows.py`.
- [x] Implement food spending. Verification: `pytest tests/test_finance_workflows.py`.
- [x] Implement salary detection. Verification: eval runner with MCP.
- [x] Implement large transactions. Verification: eval runner with MCP.
- [x] Implement recurring expense detection. Verification: `pytest tests/test_finance_workflows.py`.
- [x] Implement mutation refusal. Verification: `pytest tests/test_read_only_scope.py`.

## Phase 5 - Agent orchestration
- [x] Implement intent routing and grounded answer formatting. Verification: `pytest tests/test_read_only_scope.py`.
- [x] Keep tool registry read-only. Verification: code review and tests.

## Phase 6 - UI
- [x] Implement minimal Streamlit chat UI. Verification: `streamlit run src/belvo_finance_agent/app_streamlit.py`.
- [x] Add debug/evidence display. Verification: run the app and ask a sample question.

## Phase 7 - Eval harness
- [x] Add representative eval questions. Verification: `type evals\questions.yaml`.
- [x] Add runner that writes `evals/results.md`. Verification: `python -m belvo_finance_agent.eval_runner`.

## Phase 8 - README and final polish
- [x] Add reviewer-friendly README. Verification: read setup flow end to end.
- [x] Run tests. Verification: `pytest`.
- [ ] Run live MCP evals. Verification: Docker MCP running and `python -m belvo_finance_agent.eval_runner`.
