# Code Quality & Linter Enforcement

## 🧠 Mental Model: "Ship it Clean"
Before generating, modifying, or committing code in this monorepo, ensure the output adheres to the strict linting and formatting rules defined by `Black`, `SQLFluff`, and `Hadolint`. 

## 1. Python & SQL Rules (The Primary Workflow)
**Primary Linters:** `Black` (Formatter), `Python-SQLFluff` (SQL Formatter)  
**Command:** `black . && sqlfluff fix --dialect postgres --rules all --ignore RF04`

### 🛠️ Mandatory Checks before "I'm done":
- **Formatting**: Always use Black formatting. Enforce 80-char line width.
- **Syntax**: Run `Flake8` to ensure no trailing whitespace (`W291`) or missing docstrings (`C0114`).
- **SQL**: Ensure `schema.sql` and `seed.sql` pass SQLFluff checks with the Postgres dialect.

### 🎨 Python/SQL Style Guide:
1.  **Docs**: Every module must have a docstring (triple-quote `"""..."""`) at the top of the file to avoid `C0114`.
2.  **SQL**: No non-null assertions; use explicit column lists in UPDATE statements.

## 2. Docker Rules (When applicable)
If I modify `Dockerfile` files, I must run them through **Hadolint**. 

### 🛠️ Mandatory Docker Checks:
1.  **Pin Versions**: Use `DL3013`. Never use bare `pip install <package>`.
2.  **No Cache**: Use `DL3042`. Always append `--no-cache-dir` to pip/rpm installs.