# Risk-based test strategy

The suite prioritizes independent business risks over inflated parameter counts.

| Risk | Example scenario | Evidence |
|---|---|---|
| Duplicate order | Repeat `POST /orders` with one idempotency key | One order and one stock reservation |
| Ambiguous payment | Provider times out before returning | Bounded attempts and no duplicate payment |
| Rate limiting | Provider returns 429 with `Retry-After` | Delay is respected and attempts are reported |
| Provider outage | Provider returns 503 | Order fails safely and reserved stock is released |
| Duplicate callback | Same signed callback is delivered twice | State transition occurs only once |
| Forged callback | HMAC signature is invalid | Request is rejected without state mutation |
| Contract drift | Response shape changes | Independent JSON Schema validation fails |
| Secret leakage | A request fails with credentials present | Logs and Allure attachments are redacted |

## Suite policy

- `smoke` runs on every pull request.
- `functional`, `contract`, `resilience`, and `security` run on `main` and on demand.
- `external` is scheduled and non-blocking because public APIs are outside this repository's control.
- Whole-test reruns are not a merge-gate default. Retrying is allowed only at a documented I/O boundary.

## Quality targets

Targets become claims only after CI measures them:

- 20–30 independent API scenarios;
- at least six deterministic dependency behaviors;
- an 80% core-framework coverage gate, with 85% as the next target;
- 20 consecutive core-suite runs without a random failure;
- pull-request feedback in approximately five minutes or less.
