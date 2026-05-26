# Repository Guidelines

## Project Structure & Module Organization

This is a Python 3.13 FastAPI service for managing Amnezia-related server and peer operations. Application code lives under `src/`: `src/main.py` creates the FastAPI app, `src/api/v1/` contains routers, schemas, CRUD helpers, and middleware, `src/services/` contains business logic and protocol integrations, and `src/management/` contains settings, logging, security, and `protocols.yaml`. Static README assets are in `public/`. Container entrypoints are defined by `docker-compose.yml` and `src/Dockerfile`.

## Build, Test, and Development Commands

- `uv sync`: install project dependencies from `pyproject.toml` and `uv.lock`.
- `cp .env.example .env`: create local configuration before running the app.
- `uv run uvicorn src.main:app --reload --host 0.0.0.0 --port 8000`: run the API locally with reload.
- `docker compose up --build`: build and run the service with Docker, including the Docker socket and `/opt/amnezia` mounts required by the current compose file.
- `docker compose logs -f api`: follow API logs during containerized development.

## Coding Style & Naming Conventions

Follow the existing Python style: 4-space indentation, type-annotated FastAPI endpoints where practical, snake_case for modules/functions/variables, PascalCase for classes, and uppercase for constants and environment keys. Keep routers thin and place operational behavior in `src/services/`. Add new API areas under `src/api/v1/<domain>/` with `router.py`, `schemas.py`, and optional `crud/` modules when the domain needs persistence-style operations.

## Testing Guidelines

No test suite is currently committed. When adding tests, use `pytest` conventions: place tests under `tests/`, mirror the source domain where useful, and name files `test_<module>.py`. Prefer focused unit tests for services and FastAPI `TestClient` tests for router behavior. Document any new test command in this file and keep Docker-dependent tests clearly marked or isolated.

## Commit & Pull Request Guidelines

Use the Conventional Commits 1.0.0 specification: `type[optional scope]: description`, followed by an optional body and optional footer(s). Use `feat` for new features and `fix` for bug fixes; other useful types include `docs`, `test`, `refactor`, `perf`, `build`, `ci`, `style`, and `chore`. Keep descriptions concise, lowercase where practical, and scoped to one change, for example `fix(api): validate peer id format` or `docs: update local setup steps`. Mark breaking changes with `!` before the colon, such as `feat(config)!: rename protocol setting`, or with a `BREAKING CHANGE: ...` footer. Pull requests should include a short summary, configuration or migration notes, test results, linked issues when applicable, and screenshots only for README or documentation image changes.

## Security & Configuration Tips

Do not commit real `.env` files, API keys, server credentials, or generated peer secrets. Treat Docker socket access and `/opt/amnezia` mounts as privileged: keep related changes small and review them carefully. Preserve development-only docs behavior in `src/main.py`, where OpenAPI routes are exposed only when `DEVELOPMENT=true`.
