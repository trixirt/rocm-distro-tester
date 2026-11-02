# Code Quality & Linter Enforcement (Agent Infrastructure)

## 🧠 Mental Model: "Ship it Clean"
Before generating, modifying, or committing code, ensure the output adheres to these linter rules. 

## 1. Python & SQL Rules (The Primary Workflow)
**Primary Linters:** `Black` (Formatter), `Python-SQLFluff` (SQL Formatter). 
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

## 3. XML Prompt Rules (When applicable)
All `.xml` files (especially your agent prompts) must be strictly well-formed and validated.

### 🛠️ Mandatory Checks:
- **Linting:** Run `xmllint --noout <file>.xml`. Any parser error here is a blocker for downstream AI ingestion!
- **Structure:** Ensure all tags (like `<purpose>` and `<instruction>`) are properly nested. If broken, run `xmllint --recover` to fix immediately.
## XML Rules \nAlways validate prompts with `xmllint --noout <file.xml>` before committing!

## 4. HTML \u0026 Template Linting (When applicable)
HTML templates used in the dashboard (`ci-trigger/dashboard/templates/`) should be valid HTML5 with a `<!DOCTYPE html>`.

### 🛠️ Mandatory Checks:
- **Linting:** Run `tidy -e <file.html>` on all modified standard HTML files.
- **Templating (Jinja2):** Be aware that `<template>` variables like `{% %}` or `{{ }}` in templates (like `results.html`) will cause `tidy-html5` to report "invalid attribute" errors. These are safe within Flask environments and can be ignored, provided the *structure* (missing tags/DOCTYPE) is clean.
