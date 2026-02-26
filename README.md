# Colaberry AI

Agent-First, Deterministic-Execution platform with Test-First Validation.

## Project Structure

| Folder | Layer | Purpose |
|---|---|---|
| `agents/` | Directives | Agent personas and role definitions (no logic) |
| `directives/` | Directives | SOPs, runbooks, and contracts |
| `execution/` | Execution | Deterministic scripts (one script = one responsibility) |
| `services/worker/` | Execution | Long-running and scheduled background jobs |
| `tests/` | Verification | Unit, integration, and end-to-end tests |
| `config/` | Configuration | Environment wiring (no secrets) |
| `app/` | Boundary | FastAPI HTTP interface |
| `tmp/` | Scratch | Temporary files (never committed) |

## Rules

See [CLAUDE.md](Claude.md) for the full operating contract.
