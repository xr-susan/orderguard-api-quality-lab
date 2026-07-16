# Order service

Controllable FastAPI system under test for OrderGuard. It reserves product stock,
enforces create/payment idempotency, calls the payment dependency with bounded
retries, verifies signed callbacks, and records every payment attempt.

## Local credentials

- `demo` / `demo123`
- `test` / `test123`

## Important environment variables

| Variable | Default |
|---|---|
| `APP_ENV` | `development` |
| `ORDER_DATABASE_URL` | `sqlite:///./orderguard.db` |
| `PAYMENT_BASE_URL` | `http://payment-mock:8001` |
| `ORDER_PUBLIC_BASE_URL` | `http://order-service:8000` |
| `PAYMENT_CALLBACK_SECRET` | shared local development secret |
| `AUTH_SECRET` | local development secret |
| `PAYMENT_MAX_ATTEMPTS` | `3` (hard maximum: 3) |

`POST /__test__/reset` is available only when `APP_ENV` is not `production`.
