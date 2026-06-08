# Transactions Schema

- Transaction `amount` is positive.
- Transaction direction comes from `type`: `INFLOW` or `OUTFLOW`.
- Spending, expenses, payments, and card charges usually mean `OUTFLOW`.
- Income, received money, and PIX received usually mean `INFLOW`.
- Use `value_date` for user-facing date filters.
- Use `status=PROCESSED` by default.
- Description, merchant, category, and subcategory support deterministic text/category filters.
