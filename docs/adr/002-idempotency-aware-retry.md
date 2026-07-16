# ADR 002: Retry only at safe boundaries

## Status

Accepted.

## Decision

Retry transient transport failures and 429/502/503/504 responses within a
bounded time budget. POST is eligible only when an idempotency key is present.

## Rationale

Blind retries can duplicate orders or payments and can hide defects. Retry
attempts are observable events and must appear in logs and reports.

## Consequences

Assertion failures, schema failures, and ordinary 4xx responses are never
retried. Whole-test reruns are not part of the merge gate.

