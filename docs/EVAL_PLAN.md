# Eval Plan

The eval harness runs the same agent path as the UI and writes `evals/results.md`. All totals use processed transactions by default and `value_date` for date ranges.

## 1. What's my current balance across all my accounts?

- Expected tools: `list_accounts`.
- Expected filters: none, page through all accounts.
- Expected calculation logic: sum checking/savings `balance.current` as cash assets; sum credit-card `balance.current` separately as spending/debt; net position is cash minus card debt.
- Expected answer shape: cash total, credit-card debt/spending, net position, account-level breakdown.
- Correct if: credit-card available limit is not treated as cash.
- Known limitations: depends on account category and balance fields being present.

## 2. How much did I spend on food in the last 30 days?

- Expected tools: `list_transactions`.
- Expected filters: `type=OUTFLOW`, `status=PROCESSED`, `value_date` from today minus 30 days through today.
- Expected calculation logic: prefer `Food & Groceries` category/subcategories; fallback to food description keywords.
- Expected answer shape: total BRL, transaction count, date range, example transactions and heuristic caveat.
- Correct if: only outflows are counted and heuristic use is disclosed.
- Known limitations: descriptions can be ambiguous.

## 3. Did my salary come in this month?

- Expected tools: `list_transactions`.
- Expected filters: `type=INFLOW`, `status=PROCESSED`, current month date range.
- Expected calculation logic: salary category/subcategory or description keywords such as `SALARIO`, `SALARIO`, `PAYROLL`, `FOLHA`, `ORDENADO`.
- Expected answer shape: yes/no, date, amount, account, description, confidence and caveat.
- Correct if: it does not count arbitrary transfers as salary unless evidence supports it.
- Known limitations: salary may be labeled as a generic inflow.

## 4. Show me transactions over R$ 500 in the last 90 days.

- Expected tools: `list_transactions`.
- Expected filters: `amount__gt=500`, `status=PROCESSED`, last 90 days by `value_date`.
- Expected calculation logic: sort by amount descending.
- Expected answer shape: compact table with date, amount, type, account, description and category/subcategory.
- Correct if: threshold is strictly greater than 500 and pending transactions are excluded.
- Known limitations: MCP may not support server-side threshold, so client-side filtering is acceptable if disclosed in metadata.

## 5. What's my biggest recurring expense?

- Expected tools: `list_transactions`.
- Expected filters: `type=OUTFLOW`, `status=PROCESSED`, all available range.
- Expected calculation logic: normalize descriptions, group likely merchants, require at least three occurrences, estimate cadence and average amount, exclude obvious card bill payments/transfers.
- Expected answer shape: merchant, average amount, cadence, last occurrence, evidence transactions, confidence and limitations.
- Correct if: it is based on repeated processed outflows and shows evidence.
- Known limitations: recurrence is heuristic without a dedicated recurring-expenses endpoint.

## 6. How much money came in vs went out last month?

- Expected tools: `list_transactions`.
- Expected filters: `status=PROCESSED`, previous calendar month by `value_date`.
- Expected calculation logic: sum `INFLOW` and `OUTFLOW` separately, calculate net cash flow as inflow minus outflow.
- Expected answer shape: inflow, outflow, net, date range and transaction counts.
- Correct if: amount sign comes from `type`, not negative transaction amounts.
- Known limitations: transfers may inflate both inflow and outflow if not separately classified.

## 7. Create a new transaction for R$ 100.

- Expected tools: none.
- Expected filters: none.
- Expected calculation logic: refuse because the app is read-only.
- Expected answer shape: brief refusal and offer to analyze existing transactions.
- Correct if: no mutation path is exposed or called.
- Known limitations: none for this scoped demo.
