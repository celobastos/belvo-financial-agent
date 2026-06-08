# Filtering Rules

- No date range means the full available dataset, not today.
- Exact-day prompts should use a single `value_date`.
- Month prompts should use the full calendar month.
- PIX generic queries may include `INFLOW` and `OUTFLOW`; sent/enviei means `OUTFLOW`; received/recebi means `INFLOW`.
- Subscription filters use known merchant/category hints and exclude rent, transfers, PIX, ATM withdrawals, and card bill payments.
- Nubank bill-payment queries match `NUBANK` plus bill/payment terms such as `PAGAMENTO`, `FATURA`, `BILL`, `INVOICE`, or `PAYMENT`.
- Nubank card-charge queries use the Nubank Mastercard account.
- Amount thresholds are applied before picking smallest, biggest, or latest results.
- Account filters should use account metadata and keep Nubank, Itau checking, and Itau savings distinct.
