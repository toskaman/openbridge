# Free-credit-only operation

The participant permits promotional Meta credits only, with an absolute $150 ceiling and no paid fallback. The Meta dashboard was observed with $150 in active free credits before the development design request. That request's estimated token cost is $0.01219975.

Meta's spending alerts do not impose a provider hard cap. Billing data can also be delayed. This prototype therefore defaults to no cloud inference. There is no public UI control that enables billing, adds a payment method or changes a credit permit.

An operator may issue a supervised permit only after directly checking the actual Meta promotional balance. Runtime startup reads that observation through environment values: OPENBRIDGE_CREDIT_VERIFIED_AT (UTC ISO timestamp), OPENBRIDGE_CREDIT_OBSERVATION_ID (unique observation), OPENBRIDGE_FREE_CREDITS_USD, and MODEL_API_KEY. These values must never be committed. The server accepts the observation for at most five minutes, reserves $0.10 before each explicit request, allows at most $0.20 per observation and $1 total in its persistent local prototype ledger, and keeps $1 of observed credits untouched. Ambiguous failures retain reservations; there are no retries.

The ledger belongs outside the repository, under the local user's OpenBridge application data directory. Do not delete it to bypass exhausted allowances. The design call is recorded separately; the runtime's $1 persistent local lifetime reservation allowance is distinct from the participant's overall $150 maximum and cannot enforce account-wide billing.

This local ledger cannot monitor usage by other applications or API keys. A fresh observation is an operator attestation, not an account-wide live balance API. Do not use this mode unattended or when external usage could consume the observed credits. An expired or unavailable observation must block requests.

Only the synthetic demo facts can be sent. Physical device reports remain local. The pinned model is muse-spark-1.3 at the official Meta endpoint. Model output is advisory only and cannot execute hardware operations.

Official references: https://dev.meta.ai/help/billing/spend-limit-alert and https://dev.meta.ai/docs/pricing-rate-limits.
