# Accounts Schema

- Account records include `id`, `name`, `institution`, `category`, `type`, `subtype`, and balance fields.
- Account category distinguishes checking, savings, and credit-card accounts.
- Treat `Conta Corrente Itau`, `Poupanca Itau`, and `Nubank Mastercard` as separate account groups.
- Credit-card current balance is spending/debt, not cash.
- Account and institution metadata should drive account filters, not broad description search.
