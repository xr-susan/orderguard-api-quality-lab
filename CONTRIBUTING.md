# Contributing

Thanks for your interest in OrderGuard API Quality Lab. This document covers the
practical steps for getting a change from a local checkout into a pull request.

By participating you agree that your contributions are licensed under the MIT
license in `LICENSE`.

## Prerequisites

| Requirement | Version | Source of truth |
| --- | --- | --- |
| Python | 3.12, 3.13 or 3.14 (`>=3.12,<3.15`; 3.13 is the pinned default) | `pyproject.toml` (`requires-python`), `.python-version` |
| [uv](https://docs.astral.sh/uv/) | recommended, CI pins `0.11.28` | `.github/workflows/*.yml` |
| Docker + Docker Compose | only for the black-box suite and the demo services | `compose.yaml` |

The `dev` extra (`pyproject.toml`) installs the whole toolchain:

- **pytest** (`>=9,<10`) and **coverage** (`>=7,<8`) for tests and coverage
- **ruff** (`>=0.15,<0.16`) for linting and import sorting
- **mypy** (`>=1.19,<2`) plus `types-PyYAML` for static typing (strict mode over
  `src/api_testkit`)

Runtime dependencies for the framework and the demo services are declared in the
main `dependencies` list, so a single install covers everything.

## Setting up a virtual environment

With uv (what CI uses):

```bash
uv sync --all-extras
```

With plain `venv`:

```bash
python -m venv .venv
# Linux / macOS
source .venv/bin/activate
# Windows (Git Bash)
source .venv/Scripts/activate
# Windows (PowerShell)
# .venv\Scripts\Activate.ps1

python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

`uv.lock` is intentionally not committed yet. After the first `uv lock` run on a
networked machine, commit the generated lockfile so new clones resolve the same
versions (see the README).

## Running the tests

`pyproject.toml` sets `testpaths = ["tests", "services/order_service/tests",
"services/payment_mock/tests"]` and `pythonpath = ["src", "."]`, so `pytest` with
no arguments collects everything and `import api_testkit` works without an
install.

### 1. Framework unit tests (no services, no Docker)

These use `httpx.MockTransport` and cover `api_testkit` only:

```bash
uv run coverage run -m pytest tests/framework_unit
uv run coverage report --show-missing
```

Coverage is configured with `branch = true` over `src/api_testkit` and a
`fail_under = 80` gate, matching the `quality` workflow.

Use `coverage run -m pytest`, not `pytest --cov`. pytest-cov only starts tracing
after pytest has loaded its plugins, so every module imported by the `pytest11`
entry point (`api_testkit.config`, `api_testkit.http`, and everything they pull
in) loses its import-time lines. That under-counts the total by roughly 15
points — enough to fail a gate the code actually passes.

### 2. Demo service unit tests

These test the FastAPI apps in isolation:

```bash
uv run pytest services/order_service/tests
uv run pytest services/payment_mock/tests
```

### 3. Category (black-box) tests

`tests/cases/` drives the running services over real HTTP. Start both services
first:

```bash
docker compose up --build --wait
uv run pytest tests/cases -m "not external" --alluredir=allure-results
docker compose down --volumes
```

If the services are not reachable the `services_ready` fixture **skips** those
tests. Set `REQUIRE_DEMO_SERVICES=1` to turn that into a failure instead — CI
does this so a broken Compose stack cannot silently pass:

```bash
REQUIRE_DEMO_SERVICES=1 uv run pytest tests/cases -m smoke
```

Markers are declared in `pyproject.toml` and `--strict-markers` is enabled, so a
typo in `-m` is an error. Register any new marker there:

`smoke`, `functional`, `contract`, `resilience`, `security`, `external`, `slow`.

The `external` marker is for optional tests against public APIs; CI excludes
them with `-m "not external"`.

### 4. Running the demo services without Docker

Useful for debugging. From the repository root, with the `dev` environment
active and a `.env` copied from `.env.example`:

```bash
# terminal 1 — payment mock on :8001
uv run uvicorn services.payment_mock.app.main:app --host 0.0.0.0 --port 8001

# terminal 2 — order service on :8000
cd services/order_service && uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Outside Compose the order service must point at the local payment mock
(`PAYMENT_BASE_URL=http://127.0.0.1:8001`) and at itself
(`ORDER_PUBLIC_BASE_URL=http://127.0.0.1:8000`) so callbacks resolve. The service
reads `.env` through pydantic-settings. `POST /__test__/reset` is only available
when `APP_ENV` is not `production`.

Local credentials are `demo` / `demo123` and `test` / `test123`.

## Reproducing CI locally

`quality.yml` — Python 3.12/3.13/3.14 matrix:

```bash
uv sync --all-extras
uv run ruff check .
uv run mypy src/api_testkit
uv run coverage run -m pytest tests/framework_unit
uv run coverage report --show-missing
uv run coverage xml
```

`api-tests.yml` — black-box run plus evidence:

```bash
uv sync --all-extras
docker compose up --detach --build --wait
REQUIRE_DEMO_SERVICES=1 TEST_MARKER=smoke uv run pytest tests/cases -m "$TEST_MARKER" \
  --alluredir=allure-results --junitxml=junit-results/api-tests.xml
docker compose logs --no-color > service-logs.txt
docker compose down --volumes
```

CI uses `TEST_MARKER=smoke` on pull requests and `TEST_MARKER="not external"` on
`main` and on the weekly schedule. To render the Allure report locally:

```bash
npx --yes allure-commandline@2.35.1 generate allure-results --clean --output allure-report
```

The workflows are ordinary shell steps, so they can be replayed by hand as
above; no `act` configuration is checked in. Note that
`tests/framework_unit/test_ci_workflows.py` asserts every `astral-sh/setup-uv@`
step is pinned to `@v7` — update that test together with the action if you bump
it.

## What not to commit

`.gitignore` covers these; the list is worth knowing explicitly:

- `work/` — local end-to-end run artifacts (SQLite database and captured service
  logs). Regenerable, never commit them.
- `allure-results/`, `allure-report/`, `junit-results/`, `htmlcov/`,
  `coverage.xml` — generated reports.
- `*.db`, `*.sqlite3`, `.env` — local state and secrets.
- `build/`, `dist/`, `*.egg-info/`, caches and virtualenvs.

If you have already committed one of these by accident, untrack it without
deleting your local copy:

```bash
git rm -r --cached <path>
```

## Commit and branch conventions

The history follows [Conventional Commits](https://www.conventionalcommits.org/)
(`feat:`, `fix(ci):`, `docs:`). Please keep it up:

```text
<type>(<optional scope>): <short imperative summary>
```

Common types: `feat`, `fix`, `docs`, `test`, `refactor`, `perf`, `build`, `ci`,
`chore`. Useful scopes here are `api_testkit`, `http`, `data`, `config`,
`order-service`, `payment-mock`, `ci`, `docs`.

- Keep the subject under ~72 characters and the body focused on *why*.
- One logical change per commit; avoid mixing refactors with behaviour changes.
- Branch from `main` and use a short-lived, prefixed branch name, e.g.
  `feat/idempotency-key-replay`, `fix/retry-budget`, `docs/adr-004`.
- `main` is the default branch; both workflows run on every pull request and on
  pushes to `main`, so open a PR rather than pushing to `main` directly.
- New behaviour needs tests in the matching layer (`tests/framework_unit` for the
  framework, `tests/cases` for black-box behaviour, `services/*/tests` for the
  demo services).
- Add an entry under `## [Unreleased]` in `CHANGELOG.md` following
  [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
- Record significant design decisions as a new ADR in `docs/adr/`.

## Reporting issues

Include the Python version, whether you ran via uv or `venv`, the exact command,
and the full output (or the relevant Allure/JUnit evidence) so the failure can be
reproduced.
