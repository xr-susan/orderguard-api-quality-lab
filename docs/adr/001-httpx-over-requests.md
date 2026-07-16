# ADR 001: Use HTTPX for the test client

## Status

Accepted.

## Decision

Use a composed synchronous `httpx.Client` as the default test transport.

## Rationale

HTTPX provides connection pooling, granular timeouts, event hooks, and an
injectable transport for unit tests. Synchronous tests remain easier to read and
debug. Async usage will be introduced only for a scenario that requires it.

## Consequences

The wrapper must stay thin and must not reproduce the complete HTTPX API.

