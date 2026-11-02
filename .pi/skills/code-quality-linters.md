# Code Quality & Linter Enforcement (Agent Infrastructure)

## 🧠 Mental Model: "Ship it Clean"
Before generating, modifying, or committing code, ensure the output is clean and strictly validated. I must run the appropriate linter for each file type before considering myself finished.

## 1. Python & SQL Rules (Primary Workflow)
**Primary Linters:** `Black` (Formatter), `SQLFluff` (SQL Formatter).

### 🛠️ Mandatory Checks:
- **Python:** Run `black . --check`. Use `flake8` for syntax (no trailing whitespace, mandatory module docstrings).
- **SQL:** Ensure `schema.sql` and `seed.sql` pass SQLFluff checks with the Postgres dialect (`--dialect postgres`).

## 2. Docker Linting (When applicable)
If I modify `Dockerfile` files, I must run them through **Hadolint**. 

### 🛠️ Mandatory Docker Checks:
- **Pin Versions (DL3013):** Never use bare pip installs; always pin versions.
- **No Cache (DL3042):** Always append `--no-cache-dir` to pip/rpm installs.

## 3. HTML & Template Linting (Dashboard)
For files in `ci-trigger/dashboard/templates/`, I must run `tidy-hl5`.

### 🛠️ Mandatory Checks:
- **Linting:** Run `tidy -e <file.html>` on all modified standard HTML files to check for missing DOCTYPEs or structural errors.
- **🔔 Jinja2 Caveat:** Be aware that template variables (`{% %}` or `{{ }}`) in templates like `results.html` will cause `tidy-hl5` to report "invalid attribute" errors. These are safe in Flask environments but can be ignored for the sake of structure.

## 4. XML Prompt Rules
All `.xml` files (especially agent prompts) must be strictly well-formed and validated.
**Mandatory:** Run `xmllint --noout <file.xml>` before committing! If a file fails, use `xmllint --recover`.

## 5. Text File Linting
For `.txt` and markdown files (especially documentation):
- **Spelling:** Run `codespell <files.txt>`.
- **Style:** Run `proselint <files.txt>` to catch style inconsistencies.
