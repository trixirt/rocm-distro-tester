# ROCm Distro Tester

Self-hosted, always-on testing of AMD **ROCm packages across Linux distributions** on a
local GPU lab: test images built once, GPU tests run in parallel by many machines on
demand, and every result recorded in one durable store.

---

## 🤖 AI Tools & Process

Everything is developed **on-premise — no external LLM services are used.**

| | |
|---|---|
| **Coding agent** | `pi-coding-agent` (terminal coding agent) writes the scripts, configs, and docs |
| **LLM backend** | Ollama running Qwen3 35B-class models (`Qwen3.6:35b`, `Qwen3.5:35b`) |
| **Hardware** | AMD stack — Strix Halo + Radeon Pro W7900 |

**The working process:** a human sets direction (plans, task briefs, acceptance
criteria); the agent drafts and iterates on code, scripts, and documentation; every
piece is **validated against the real environment** (live Docker, SELinux-Enforcing
hosts, GPU nodes) before and after each change; a human reviews the diff and owns
the commit. The repository itself is the product of that loop — the same discipline
the repo enforces on its own CI components.

AI is also part of the **future test pipeline**, not just the development process:
per-failure analysis reports (`analysis.log`) will be stored as first-class artifacts
in the results database (see [PLAN.md](./PLAN.md) §7).

---

## The Problem

ROCm packages (hipblas, hipsolver, …) ship into **many Linux distributions**, and
each combination must be validated on **real AMD GPU hardware** before it can ship.

Today that happens the manual way: hand-written Docker container tests —
[rocm-distro-containers](https://github.com/trixirt/rocm-distro-containers),
~1,200 Dockerfiles across 8 distributions — built and run **by hand, on the lab's
GPU machines**. It works, but:

- **No scheduling** — somebody has to decide what to test, start it, and chase it.
- **Serial and ad-hoc** — the limited GPU fleet cannot be used in parallel on demand.
- **Results are scavenged** — pass/fail lives in JSON files scattered across
  machines; no single place answers "does this package work on this distro today?"
- **Builds re-fetch everything** — base images come from upstream per build, so a
  multi-hour test wave can silently drift between two different base revisions.

## What This Project Adds

This repository is the automation layer built **on top of** the existing manual
container tests:

| # | Component | What it changes for the lab |
|---|---|---|
| **1** | **A registry testers can pull from — and run tests asynchronously** | GPU machines become a self-service test pool: pull `rocm-builder:5000/<distro>-<package>` and run it. Start a wave and walk away — machines claim and execute work on their own schedule. *(local registry, test tier, :5000)* |
| **2** | **A registry builders build into** | Build once on the builder, push, deploy to the whole fleet. The infrastructure registry also **pins the ever-changing distro bases** (`fedora:rawhide`, `ubuntu:latest`, `archlinux:latest`, `centos:stream10`) so an entire test wave builds against *one* base revision — consistent results, offline-capable, and receipts that name the exact image used. *(local registry, infra tier, :5001)* |
| **3** | **A database as the single source of truth** | PostgreSQL holds the work queues, every pass/fail/timeout, and the build/test artifacts (logs, Dockerfiles, analyses) content-addressed by SHA-256. Baselines become first-class objects — "regressed against last month's run" is a query, not an archaeology project. The dashboard and API are read-only views of that one store. |

In one sentence: **turn "someone manually tests ROCm on the lab GPUs" into a
scheduled, parallel, reproducible service with an auditable record.**

---

## Status

| Area | Status |
|------|--------|
| Design plan, runbook, verification scripts | ✅ Done |
| Registries (test `:5000` + infra `:5001`), SELinux & non-root safe | ✅ Deployable & verified |
| Base-image & postgres pinning (`pin_infra_images.sh`) | ✅ Working |
| Results dashboard (file-based, interim) | ✅ Active |
| hipblas smoke tests — Fedora/Ubuntu | 🟡 In progress |
| Results database (PostgreSQL, v0.3) | 🟡 Deploy script ready (`setup_db.sh`) |
| Full ROCm package matrix (~89 packages) | 🔴 Next |

## Go Deeper

- **[PLAN.md](./PLAN.md)** — full architecture and design decisions (registry tiering, DB schema, retention)
- **[INSTALL.md](./INSTALL.md)** — deployment runbook for builder / state / tester machines
- **[TODO.md](./TODO.md)** — current task queue
- **[rocm-distro-containers](https://github.com/trixirt/rocm-distro-containers)** — the manual test suites this project automates

---

*MIT License — see [LICENSE](./LICENSE).*
