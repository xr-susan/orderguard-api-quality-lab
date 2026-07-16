# ADR 003: YAML is the primary case format

## Status

Accepted.

## Decision

YAML is the canonical human-authored format. JSON and Excel are input adapters
that produce the same strongly typed `CaseSpec`.

## Rationale

YAML handles nested request data well and remains diffable. Excel is retained
for compatibility with tabular boundary data, not as a workflow language.

## Consequences

Complex workflows remain Python code. The loaders do not evaluate Python,
arbitrary templates, formulas, or cross-sheet control flow.

