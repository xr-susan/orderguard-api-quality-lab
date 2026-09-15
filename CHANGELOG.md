# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Versioning and links

- The version in `pyproject.toml` (`[project].version`) is the single source of
  truth; this changelog is kept in step with it.
- Releases are tagged `vMAJOR.MINOR.PATCH` on the default branch (`main`).
- Entry links use the repository URL convention
  `https://github.com/xr-susan/orderguard-api-quality-lab`:
  - released versions link to their tag, e.g.
    `.../releases/tag/v0.1.0`;
  - the unreleased section links to a comparison against the latest tag, e.g.
    `.../compare/v0.1.0...HEAD`.
- Because `api_testkit` is a library plus a test suite rather than a published
  runtime service, the version follows Semantic Versioning for the framework
  surface: breaking changes to `api_testkit` public APIs, the pytest plugin
  contract, or the case-data schema bump MAJOR; backwards-compatible framework
  additions bump MINOR; backwards-compatible fixes bump PATCH.
- While the project is pre-1.0 (`0.x.y`), MINOR releases may still contain
  breaking changes; they are always called out in this file.

## [Unreleased]

### Added

- `src/api_testkit/py.typed` (PEP 561 marker) so type checkers treat the
  framework as typed when it is installed.
- `CHANGELOG.md` and `CONTRIBUTING.md`.

### Changed

- `.gitignore` now covers `work/`, `build/`, `dist/`, `venv/`, `.coverage.*`,
  `coverage.xml`, `.tox/`, `.nox/` and `.hypothesis/`.
- `pyproject.toml` ships the `py.typed` marker as setuptools package data.

### Removed

- Stopped tracking the local end-to-end run artifacts under `work/`
  (`orderguard-e2e.db`, `order-e2e.{out,err}.log`,
  `payment-e2e.{out,err}.log`). They are local, regenerable evidence and now
  stay on disk but out of version control.

## [0.1.0] - 2026-07-16

### Added

- Reusable test framework `src/api_testkit/` with independent boundaries for
  configuration, HTTP, data loading, assertions and observability:
  - `config/`: layered `base`/`local`/`ci` YAML sources resolved into Pydantic
    Settings models.
  - `http/`: an `httpx`-based `ApiClient` with authentication, request/response
    hooks and an idempotency-aware retry policy (only safe methods retry by
    default; `POST` requires an `Idempotency-Key`).
  - `data/`: YAML, JSON and Excel loaders normalised into one Pydantic case
    model, so malformed case data fails before execution.
  - `assertions/`: core assertions and JSON Schema response validation.
  - `observability/`: structured logging, log context binding, credential
    redaction and an Allure adapter.
  - `pytest_plugin` exported as the `orderguard` pytest11 entry point.
- Two demo services under `services/`:
  - `order_service`: FastAPI + SQLAlchemy/SQLite order workflow with stock
    reservation, create/payment idempotency, bounded payment retries with stock
    release on exhaustion, JWT authentication and HMAC callback verification.
  - `payment_mock`: programmable payment dependency with fault injection
    (429/503/timeouts, delayed or duplicate callbacks, wrong signatures) and a
    request history exposed for assertions.
- Black-box test layers under `tests/cases/` — `smoke`, `functional`,
  `contract`, `resilience` and `security` — driven by the YAML, JSON and Excel
  cases in `tests/data/`, with domain clients and helpers in `tests/support/`.
- Framework unit tests under `tests/framework_unit/` that use MockTransport and
  need no running service.
- Layered configuration in `config/`, `compose.yaml` for the two services,
  `.env.example`, Allure category definitions in `reporting/` and
  `scripts/generate_excel_cases.py` for regenerating the Excel case workbook.
- GitHub Actions workflows: `quality.yml` (Ruff, mypy and framework coverage on
  Python 3.12/3.13/3.14) and `api-tests.yml` (Docker Compose black-box run,
  evidence upload, Allure HTML generation and GitHub Pages publishing).
- Documentation: `docs/architecture.md`, `docs/test-strategy.md` and ADRs
  `001-httpx-over-requests`, `002-idempotency-aware-retry` and
  `003-yaml-as-primary-format`.
- MIT license.

### Changed

- `README.md` expanded with the architecture diagram, technology stack,
  directory layout, case-to-capability mapping, retry and exception-handling
  principles, CI/CD description and roadmap.

### Testing

- pytest markers `smoke`, `functional`, `contract`, `resilience`, `security`,
  `external` and `slow`, with `--strict-markers` and `--strict-config` enabled.
- Coverage configured over `src/api_testkit` with `branch = true` and a
  `fail_under = 80` gate.
- Framework unit tests covering assertions, configuration resolution, all three
  data loaders, the HTTP client and observability helpers.
- Local end-to-end run evidence was captured under `work/` (SQLite database and
  per-service stdout/stderr logs) to document a real Compose run.

### Fixed

- CI referenced an unsupported `setup-uv` action version; both workflows now
  pin `astral-sh/setup-uv@v7`, guarded by
  `tests/framework_unit/test_ci_workflows.py`.

[Unreleased]: https://github.com/xr-susan/orderguard-api-quality-lab/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/xr-susan/orderguard-api-quality-lab/releases/tag/v0.1.0
