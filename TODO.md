# ROCm-Tester: Testing & Validation Tasks - Agent Handoff

**Project:** rocm-tester  
**Current Version:** v0.1.6 (Dashboard Implementation Complete)  
**Repository Root:** `~/devel/rocm-tester`  
**Last Commit:** 6e084dedcad2 (Add Docker Registry Infrastructure v0.1.5 + Dashboard v0.1.6)  

---

## 🎯 Executive Summary for Testing Agent

You have inherited a Flask-based CI/automation framework designed to test ROCm packages across **Fedora, Ubuntu, and RHEL/CentOS Stream**. The infrastructure consists of multiple components:
1.  **Polling Scripts** (Python) - Monitoring package builds per distro.
2.  **Docker Registry** (Optional/Declarative) - Local registry deployment helper.
3.  **Container Images** (Dockerfiles) - Distros-specific base images for test environments.
4.  **Web Dashboard** (Flask) - Visual aggregation of JSON results.

Your objective is to **validate, unit-test, and stress-test** each component to ensure production-readiness before we proceed with Phase 2 (CI Integration & Trend Analysis).

This document provides **stand-alone tasks** that can be copy-pasted into a new LLM session or directly executed. Each task includes **Objective**, **Prerequisites**, **Execution Steps**, and **Success Criteria**.

---

## 📋 Overview of Testing Scope

| Component | Status for Testing | Critical Concerns |
|-----------|--------------------|-------------------|
| **Python Pollers** (Fedora, Ubuntu, EPEL) | ✅ Code written | Network exception handling & JSON parsing logic. |
| **Docker Containers** (Registry, Dashboard) | ✅ Dockerfile created | Image build success & Port mapping correctness. |
| **Web Dashboard** (Flask + Templates) | ✅ App written | UI rendering & data ingestion from `RESULTS_DIR`. |
| **Scripts** (Setup Automation) | ✅ Shell scripts present | Cross-shell compatibility (`bash` vs `dash`) and permissions. |
| **Documentation** (PLAN/README) | ✅ Updated | Consistency check against actual code structure. |
| **Unit Tests** (pytest) | ✅ pytest files exist | Coverage validation via test execution. |

---

## 🚦 Prerequisites Before Starting Tasks

Ensure the testing environment is ready:
1.  **Python 3.10+** installed (for pollers and Flask app).
2.  **Docker** available (for running containers/registry check).
3.  **Git** available (to confirm file structure/history if needed).
4.  **Network Access** to `pypi.org` (pip) and external sites (if testing real poller behavior).
5.  **Disk Space** sufficient for test build artifacts (~2GB recommended).

---

## 📝 Comprehensive Testing Task List

You may execute tasks sequentially or in parallel based on dependencies. Mark completed tasks as `[x]` when finished.

### 🔧 SECTION A: Python Poller Validation

#### Task A-1: Validate Fedora Build Poller Syntax & Imports
**Objective:** Ensure `poll_fedora_builds.py` is syntactically valid and imports correctly.
**Commands:**
```bash
cd ~/devel/rocm-tester && python3 -m py_compile ci-trigger/poll_fedora_builds.py
python3 -c "import sys; sys.path.insert(0, 'ci-trigger'); from poll_fedora_builds import TRACKED_ROCM_PACKAGES; print('Imports OK:', len(TRACKED_ROCM_PACKAGES))"
```
**Success Criteria:** No `SyntaxError` returned. `TRACKED_ROCM_PACKAGES` lists ≥ 7 items on output.

---

#### Task A-2: Validate Ubuntu Build Poller Logic
**Objective:** Ensure `poll_ubuntu_builds.py` handles mock responses gracefully (simulated without live API).
**Commands:**
```bash
cd ~/devel/rocm-tester && python3 -m py_compile ci-trigger/poll_ubuntu_builds.py

# Simulate network failure handling in code inspection:
grep -n "except.*Exception" ci-trigger/poll_ubuntu_builds.py | head -2
```
**Success Criteria:** Syntax valid. Error handlers found catching `requests.exceptions.RequestException`.

---

#### Task A-3: Validate EPEL/RHEL Poller Logic
**Objective:** Verify `poll_epel_builds.py` uses correct base API URL for CentOS Stream.
**Commands:**
```bash
cd ~/devel/rocm-tester && python3 -m py_compile ci-trigger/poll_epel_builds.py

# Check hardcoded constants:
grep "KOJI_EPEL_BASE_URL" ci-trigger/poll_epel_builds.py | grep -E "(https?)|(koji)" 
```
**Success Criteria:** Syntax valid. URL starts with `https://kojipkg.fedoraproject.org`.

---

### 🐳 SECTION B: Docker & Containerization Checks

#### Task B-1: Validate Registry Dockerfile Configuration
**Objective:** Ensure `ci-trigger/docker/Dockerfile.registry` is a valid, multi-stage or single-stage build.
**Commands:**
```bash
cd ~/devel/rocm-tester && cat ci-trigger/docker/Dockerfile.registry | grep "^FROM"
cat ci-trigger/docker/Dockerfile.registry | grep "ENV\|LABEL"
```
**Success Criteria:** `FROM registry:2` present. Labels include `maintainer`, `description`, `version`.

---

#### Task B-2: Validate Dashboard Docker Build Context
**Objective:** Verify `ci-trigger/docker/Dockerfile.dashboard` and `requirements.txt` are coherent.
**Commands:**
```bash
cd ~/devel/rocm-tester
echo "Checking Docker Compose Config:"
docker compose -f docker-compose.dashboard.yml config > /tmp/check_compose.txt 2>&1

# Ensure base image matches requirements:
grep "^FROM python" ci-trigger/docker/Dockerfile.dashboard
cat ci-trigger/dashboard/requirements.txt | grep Flask
```
**Success Criteria:** Docker Compose parses successfully. Python base version >= 3.10. `Flask` in requirements.

---

#### Task B-3: Run Containerized Dashboard Test
**Objective:** Spin up the dashboard container and verify port exposure (do not actually start full test, just validate setup).
**Commands:**
```bash
cd ~/devel/rocm-tester
docker run --rm -p 5001:5001 rocm-dashboard:latest & 
sleep 3
curl -f http://localhost:5001/api/summary 2>/dev/null && echo "API Responded" || echo "No Response"
docker stop $(docker ps -q --filter ancestor=rocm-dashboard:latest)
```
**Success Criteria:** Container starts without crash exit code. API response returns HTTP 200 (on startup). Port mapping `5001:5001` confirmed.

---

### 🖥️ SECTION C: Web Dashboard Integration Testing

#### Task C-1: Execute Flask Dashboard Python Syntax Check
**Objective:** Confirm `app.py` has no import errors or missing dependencies before running.
**Commands:**
```bash
cd ~/devel/rocm-tester && python3 -c "from ci-trigger.dashboard.app import app; print('App Loaded'); assert app is not None"
```
**Success Criteria:** No `ModuleNotFoundError`. Assertion passes (app object exists).

---

#### Task C-2: Validate Dashboard Jinja2 Templates Rendering
**Objective:** Ensure `templates/base.html` and templates exist with correct blocks.
**Commands:**
```bash
cd ~/devel/rocm-tester && ls ci-trigger/dashboard/templates/*.html

# Check for core blocks defined in all templates:
grep -l "{% block content %}" ci-trigger/dashboard/templates/*
```
**Success Criteria:** 3 template files exist. `extends "base.html"` found in child templates. `{% block title %}` and `{% block content %}` present in base.

---

#### Task C-3: Verify Dashboard Result Data Parsing Logic
**Objective:** Ensure the `load_all_results` function correctly handles empty directories and JSON errors.
**Commands:**
```bash
cd ~/devel/rocm-tester && python3 ci-dashboard-parsing-test.py << 'PYTEST'
# Inline script to test data loader
import sys, os 
from pathlib import Path
sys.path.insert(0, 'ci-trigger/dashboard')
print("Testing Result Parser...") # Will run in session context
# Expected output: Prints success if logic handles empty lists gracefully
```
**Success Criteria:** Code executes without crashing when `RESULTS_DIR` is empty or invalid paths provided.

---

### 🧪 SECTION D: Automated Unit Test Execution & Coverage

#### Task D-1: Run Poller Unit Tests (pytest)
**Objective:** Execute pytest suites for all pollers to confirm logic validity.
**Commands:**
```bash
cd ~/devel/rocm-tester && pytest ci-trigger/tests/test_poll_fedora_builds.py -v
pytest ci-trigger/tests/test_poll_archlinux_builds.py -v  # Note: Arch Linux might need adjustment
pytest ci-trigger/tests/test_poll_ubuntu_builds.py -v    # If applicable (Poll_ubuntu is separate)
```
**Success Criteria:** All test cases reported as `PASSED`. No errors in assertions.

---

#### Task D-2: Run Dashboard Unit Tests & Verify Coverage
**Objective:** Execute dashboard tests ensuring 100% line coverage on key functions.
**Commands:**
```bash
cd ~/devel/rocm-tester && pytest ci-trigger/tests/test_dashboard.py -v --cov=ci-trigger/dashboard/app.py
# Check final summary for line count:
grep "TOTAL" ci-trigger/reports/coverage.txt 2>/dev/null || echo "Coverage report generated"
```
**Success Criteria:** Tests pass. Coverage output indicates >80% of Flask routes/functions executed.

---

### 📚 SECTION E: Documentation Consistency Check

#### Task E-1: Cross-Reference `PLAN.md` vs Actual Project Structure
**Objective:** Ensure documentation matches the code structure created in this session.
**Commands:**
```bash
cd ~/devel/rocm-tester 
# Search Plan for key sections and verify existence:
grep -l "Section 6" PLAN.md && find . -name "docker" -type d | wc -l

# Verify Section 7 Dashboard details are in README.md:
grep "Web Dashboard" README.md
```
**Success Criteria:** Both mentions (Plan/README) correspond to actual `ci-trigger/docker` directory exists. Documentation file sizes indicate recent updates (>10 lines changed).

---

#### Task E-2: Verify Setup Scripts are Executable
**Objective:** Ensure shell scripts (`setup_docker_registry.sh`, `setup_dashboard.sh`) have execute permissions and shebangs.
**Commands:**
```bash
cd ~/devel/rocm-tester && ls -la ci-trigger/scripts/*.sh | grep "^-rwx"

# Verify script header:
head -3 ci-trigger/scripts/setup_docker_registry.sh
```
**Success Criteria:** All scripts listed start with `-rwx`. Shebang `#!/bin/bash` present at line 1.

---

### ⚖️ SECTION F: Edge Case & Failure Mode Testing

#### Task F-1: Test Poller Failure Handling (Simulated)
**Objective:** Verify `poll_fedora_builds.py` handles network timeouts without crashing.
**Commands:**
```bash
cd ~/devel/rocm-tester && timeout 5 python3 -c "
import sys; sys.path.insert(0, 'ci-trigger')
from poll_fedora_builds import query_fedora_koji_api
# Note: This will fail on network but check exception handling in code review below.
" || echo "Command ran (expecting timeout)"

# Code inspection for error catching:
grep -A2 "import requests" ci-trigger/poll_fedora_builds.py | grep -E "(try|except|except Exception)"
```
**Success Criteria:** No unhandled `SyntaxError`. Imports present. `try/except` blocks exist inside query functions.

---

#### Task F-2: Test Dashboard Empty Results Handling
**Objective:** Confirm dashboard returns 200 OK when `/var/rocm-tester/results/`` contains no JSON files.
**Commands:**
```bash
cd ~/devel/rocm-tester && ls ci-trigger/dashboard/templates/
# Simulate empty dir manually via variable override in test fixture (run from Task C-1)
# Ensure template doesn't crash on undefined iteration
grep -n "for.*in results" ci-dashboard/templates/results.html
```
**Success Criteria:** Template syntax valid. Uses `{% if results %} ... {% endif %}` blocks or default Jinja handling to avoid crashes on empty lists.

---

## 🔄 Handoff Instructions

1.  **Review this TODO.md context.**
2.  **Pick one Section** (A, B, C, D, E, F) and begin processing tasks sequentially.
3.  **Report findings** as a summary at the end of your session for the next agent or human reviewer.
4.  **Mark completed tasks** `[x]` in this document if possible via edit permissions.

---
*Generated for Agent Handoff: ROCm-Tester Framework Validation (v0.1.6)*
