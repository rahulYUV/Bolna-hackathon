# Dashboard metrics

All dashboard boundaries are calculated in `Asia/Kolkata`; timestamps remain UTC in Postgres.

- **Total outstanding:** sum of `customers.amount_due` where the balance is greater than zero.
- **Recovered this week:** sum of `payments.amount` since Monday 00:00 IST.
- **After a Hisaab call:** payments in that period within seven days after a completed call. This is attribution, not proof of causation.
- **Recovery rate:** recovered this week divided by outstanding plus recovered this week. The API returns `null` when the denominator is zero.
- **Promised today:** unpaid customers whose `promise_date` is today.
- **Overdue promises:** unpaid, callable customers whose promise date is before today, including count, outstanding amount, and maximum days overdue.
- **Disputes:** unpaid callable customers with `status = disputed`.
- **No answer:** unpaid callable customers with `status = no_answer`.
- **Calls completed:** calls with `status = completed` since Monday 00:00 IST.
- **Connected rate:** connected calls divided by attempted calls for the same period; `null` when there are no attempts.
- **Safety events:** opt-outs, disputes, complaints, early hang-ups, and calls blocked by do-not-call recorded this week.

The follow-up list is ordered by dispute, overdue promise, promise due today, no-answer retry, then first reminder. Customers with `do_not_call` are excluded.
