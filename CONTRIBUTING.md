# Contributing to Claude Code Karma

Thank you for your interest in contributing to Claude Code Karma! This document provides guidelines and instructions for contributing to the project.

## Code of Conduct

Please review our [Code of Conduct](./CODE_OF_CONDUCT.md) and follow it in all interactions with the project community.

## Getting Started

### Prerequisites

Before you begin, ensure you have:

- **Python 3.9+**
- **Node.js 18+**
- **npm 7+**
- **Git**
- Claude Code sessions (to test with real data)

Verify your setup:

```bash
python3 --version    # 3.9 or higher
node --version       # 18 or higher
npm --version        # 7 or higher
git --version        # any version
```

### Development Setup

1. **Clone the repository**

```bash
git clone https://github.com/JayantDevkar/claude-karma.git
cd claude-karma
```

2. **Set up the API**

```bash
cd api
pip install -e ".[dev]"
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

The API will be available at `http://localhost:8000`.

3. **Set up the Frontend** (in a new terminal)

```bash
cd frontend
npm install
npm run dev
```

The frontend will be available at `http://localhost:5173`.

4. **Set up Captain Hook** (if making changes)

```bash
cd captain-hook
pip install -e ".[dev]"
pytest tests/test_models.py -v
```

## Reporting Issues

### Reporting Bugs

If you find a bug:

1. **Check if it's already reported** — Search [existing issues](https://github.com/JayantDevkar/claude-karma/issues)
2. **Create a new issue** with:
   - Clear title describing the bug
   - Step-by-step reproduction steps
   - Expected vs actual behavior
   - Python version, Node version, OS
   - Relevant logs or screenshots

### Suggesting Features

To suggest a feature:

1. **Check if it's already requested** — Search [existing issues](https://github.com/JayantDevkar/claude-karma/issues)
2. **Create a new issue** with:
   - Clear title describing the feature
   - Use case and motivation
   - Proposed solution (if any)
   - Additional context or examples

## Development Workflow

### Creating a Feature Branch

```bash
git checkout main
git pull origin main
git checkout -b feature/your-feature-name
```

Use descriptive branch names:
- `feature/add-export-button`
- `fix/session-timeline-crash`
- `docs/update-api-guide`

### Code Style

#### Python (API & Captain Hook)

We use **ruff** for linting and formatting.

```bash
# Check for style issues
ruff check models/ routers/ tests/

# Auto-format code
ruff format models/ routers/ tests/

# Run linting in CI
ruff check --select E,F,W --line-length 120
```

Guidelines:
- Follow PEP 8
- Use type hints for all functions
- Document public functions with docstrings
- Max line length: 120 characters
- Use `ConfigDict(frozen=True)` for Pydantic models

#### Frontend (SvelteKit/Svelte 5)

We use **prettier** and **eslint** for formatting and linting.

```bash
# Check for style issues
npm run lint

# Auto-format code
npm run format

# Type check
npm run check
```

Guidelines:
- Use TypeScript for all components
- Use Svelte 5 runes (`$state()`, `$derived()`, `$effect()`)
- Follow component naming conventions (PascalCase)
- Document complex logic with comments
- Use `<script lang="ts">` in Svelte files

### Testing

#### API Tests

```bash
cd api

# Run all tests
pytest

# Run specific test file
pytest tests/test_session.py -v

# Run with coverage
pytest --cov=models --cov=routers

# Run API endpoint tests
pytest tests/api/ -v
```

#### Frontend Type Checking

```bash
cd frontend

# Run type checker
npm run check

# Run linter
npm run lint

# Run formatter check
npm run format -- --check
```

#### Captain Hook Tests

```bash
cd captain-hook

# Run tests
pytest tests/test_models.py -v
```

**Guidelines:**
- Write tests for new features
- Ensure all tests pass before submitting a PR
- Aim for >70% code coverage on new code
- Include both happy path and error cases

## Making Changes

### General Guidelines

1. **One feature/fix per PR** — Keep PRs focused and reviewable
2. **Write clear commit messages** — Use conventional commits style (see below)
3. **Update documentation** — If you change behavior, update docs
4. **Add tests** — Include tests for new features or bug fixes
5. **Keep commits atomic** — Each commit should be a logical unit

### Commit Message Conventions

Use [Conventional Commits](https://www.conventionalcommits.org/) format:

```
type(scope): description

[optional body]

[optional footer]
```

**Types:**
- `feat` — New feature
- `fix` — Bug fix
- `docs` — Documentation changes
- `style` — Code style changes (formatting, semicolons, etc.)
- `refactor` — Code refactoring without feature changes
- `perf` — Performance improvements
- `test` — Adding or updating tests
- `chore` — Build system, dependencies, etc.

**Scope:** Component or area affected (optional but recommended)

**Examples:**
```
feat(session-timeline): add zoom control
fix(api): handle empty project directories
docs(readme): update installation instructions
refactor(frontend): extract chart component
test(models): add coverage for edge cases
```

## Submitting a Pull Request

1. **Push your branch**

```bash
git push origin feature/your-feature-name
```

2. **Create a Pull Request** with:
   - Clear title describing the changes
   - Description explaining the problem and solution
   - Reference any related issues (#123)
   - List of changes made
   - Testing instructions (if not obvious)

3. **Ensure all checks pass:**
   - Linting checks pass
   - Tests pass
   - Type checking passes
   - No merge conflicts

4. **Respond to reviews** — Address feedback and push updates

5. **Merge** — Once approved, the maintainer will merge

## Project Structure Overview

For detailed information, see [CLAUDE.md](./CLAUDE.md).

### Key Directories

| Directory | Purpose |
|-----------|---------|
| `api/` | FastAPI backend with Pydantic models |
| `api/models/` | Data models for Claude Code storage |
| `api/routers/` | API endpoint definitions |
| `api/db/` | Database utilities |
| `api/tests/` | API tests |
| `frontend/src/routes/` | SvelteKit pages |
| `frontend/src/lib/` | Reusable components and utilities |
| `captain-hook/` | Pydantic models for Claude Code hooks |

## Common Tasks

### Adding a New API Endpoint

1. Create a new router file in `api/routers/`
2. Define the endpoint with proper type hints and docstrings
3. Add tests in `api/tests/api/`
4. Update README.md API table
5. Run `ruff check` and `pytest`

### Adding a New Frontend Page

1. Create a route directory in `frontend/src/routes/`
2. Add `+page.svelte` with TypeScript
3. Add any components in `frontend/src/lib/components/`
4. Run `npm run check` and `npm run lint`
5. Test in development server

### Updating Documentation

1. Update relevant `.md` files
2. Ensure code examples are accurate
3. Check links are valid
4. Run spelling and grammar checks

## Questions?

- Check [SETUP.md](./SETUP.md) for installation help
- See [CLAUDE.md](./CLAUDE.md) for development guidance
- Ask in [GitHub Discussions](https://github.com/JayantDevkar/claude-karma/discussions) (if available)
- Open an issue for questions

## License

By contributing, you agree that your contributions will be licensed under the Apache License 2.0 (see [LICENSE](./LICENSE)).

---

Thank you for contributing to Claude Code Karma!
