# ROCm-Distro-Tester CI Framework - Project Plan

**Status**: v0.2 (Updated for Storage Requirements)  
**Date**: Oct 16, 2024  
**Author**: Single Developer Team

---

## Executive Summary

This project creates a **self-hosted continuous integration framework** for testing AMD ROCm packages across multiple Linux distributions (Ubuntu, Fedora, OpenSUSE). The system automatically polls Fedora Koji and Ubuntu Launchpad for package updates, builds distro-specific test containers, runs GPU-enabled smoke tests on local hardware nodes, and aggregates results into a unified dashboard.

---

## Problem Statement

ROCm packages live in Fedora's build infrastructure (Koji/Bodhi) but testing requires:
- Physical GPU hardware diversity (MI200, MI300, Vega, etc.)
- Multiple Linux distributions for compatibility validation
- Automated execution when packages are updated
- Resource-efficient parallelization across limited test machines

Current state is **manual Docker builds** per package — error-prone, slow, and no version tracking.

---

## Goals & Success Criteria

### Primary Goals (v0.1)
- [ ] Poll Fedora Koji for ROCm package builds automatically
- [ ] Build and deploy distro-specific test containers on-demand
- [ ] Run hipblas/smoke test across Ubuntu/Fedora with 2 GPU types
- [ ] Aggregate test results to a unified JSON output

### Secondary Goals (v0.2+)
- [ ] Extend to all ROCm packages (hipblas, rocblas, hipsolver, etc.)
- [ ] Add scheduling/queue management for limited GPU resources
- [ ] Slack/Discord failure notifications
- [ ] Historical trend visualization of test results

### Success Criteria
| Metric | Target |
|--------|--------|
| Time from package build → test start | < 5 minutes |
| Test execution per package (3 distros × 2 GPUs) | < 2 hours total |
| Manual intervention required per CI run | 0 (fully automated) |

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                     CONTROLLER MACHINE (CI MASTER)                   │
│                                                                      │
│  ┌──────────────────┐     ┌──────────────────┐     ┌──────────────┐│
│  │ Poller Service   │────>│ Build Orchestrator│────>│ Test Matrix  ││
│  │ (Fedora Koji)    │     │ (Jenkins Pipeline)│    │ Scheduler    ││
│  └──────────────────┘     └──────────────────┘     └──────────────┘│
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────────┐│
│  │  Shared Registry: Docker Images built once, pulled everywhere   │
│  └─────────────────────────────────────────────────────────────────┘│
│                                                                   │
└───────────────────────────────────┬───────────────────────────────┘
                                    │
          ┌─────────────────────────┼─────────────────────────┐
          ▼                         ▼                         ▼
  ┌─────────────────┐      ┌─────────────────┐      ┌─────────────────┐
  │   Ubuntu GPU    │      │  Fedora GPU     │      │  OpenSUSE GPU   │
  │   Node (1)      │      │   Node (1)      │      │   Node (1)      │
  │ - AMD MI300     │      │ - AMD MI250     │      │ - NVIDIA RTX    │
  │ - Docker        │      │ - Docker        │      │ - Podman        │
  └─────────────────┘      └─────────────────┘      └─────────────────┘
```

---

## Component Breakdown

### 1. Poller Service (`ci-trigger/poller-*`)
**Purpose**: Detect package updates in build repositories

- `poll-fedora-builds.py` — Queries Koji API for ROCm RPM versions
- `poll-ubuntu-launchpad.py` — Monitors Ubuntu package builds via Launchbridge
- Tracks last-checked timestamp per package to avoid redundant polling

### 2. Build Orchestrator (`ansible/`)
**Purpose**: Consistent provisioning across distros

- `site.yml` — Main Ansible playbook for controller setup
- `roles/gpu-setup-{ubuntu,fedora,opensuse}/` — Distro-specific GPU driver installation
- `roles/test-environment/` — Docker/Podman runtime + NVIDIA/ROCm CUDA dependencies

### 3. Test Matrix Runner
**Purpose**: Execute tests on target hardware

```bash
ci-trigger/orchestrator.sh
├── Detects new package build via poller
...
```

---

## Implementation Roadmap

### Phase 1: Core Infrastructure (2 weeks)
**Week 1-3**: Set up base automation framework

### Phase 2: Distro Abstraction Layer (1 week)
- Complete `package-config.yaml` for all ROCm packages

### Phase 3: Queue Management & Scaling (2 weeks)
- GPU resource queue to prevent concurrent jobs on single node

---

## File Structure Template

The repository root can be placed anywhere on your system.

---

# Section 6: Docker Registry Infrastructure (v0.1.x)

This document outlines the deployment of a local Docker Registry (`registry:2`) on the **controller/builder machine** to facilitate building and distributing test images to remote GPU tester nodes.

#### 📍 Architecture & Flow

```
              ┌─────────── Builder / Controller Node ───────────┐
              │            (Expected IP: 192.168.1.25)          │
              │                                                  │
      git     │   <--- poll packages from Koji/Launchpad        │
clone         │   [ docker build ] → [ registry:2 ]             │
pull ─────────┘                         │                        ▼
                                          push                    [ Remote Tester Machines ]
                                                                    - Pull Images
                                                                    (rocm-builder:5000/...)
                                                                    - Execute Smoke Tests
```

**Key Operational Principles:**
1.  **Local Registry**: The controller node serves as a lightweight internal Docker Hub (`registry:2`) on port `5000`. No internet access is required for test nodes.
2.  **Build-Once-Deploy-Many**: Images are built *once* on the builder and pushed to the local registry. Remote tester nodes simply `docker pull` from this central source.
3.  **Tagging Convention**: All builds use the format **`rocm-builder:5000/<package-distro>:latest`**.

#### 🎨 Image Naming & Versioning Policy

| Distro | Standard Tag Format | Example (hipblas-fedora) |
|--------|---------------------|--------------------------|
| **Fedora** | `rocm-builder:5000/fedora-<pkg>` | `rocm-builder:5000/hipblas-fedora:latest` |
| **Ubuntu** | `rocm-builder:5000/<distro>-<pkg>` | `rocm-builder:5000/hipblas-ubuntu:latest` |
| **RHEL/CentOS** | `rocm-builder:5000/<package>-<release>` | `rocm-builder:5000/hipblas-rhel-central9:latest` |

#### 📊 Storage & Infrastructure Requirements (Updated)

To support a complete matrix build (targeting ~1000 distinct Dockerfiles across Arch, Fedora, Ubuntu, etc.) and maintain a registry copy for each node, significant resources are required.

| Configuration Metric | Requirement / Standard | Implementation Details |
|----------------------|------------------------|------------------------|
| **OS Architecture** | 64-bit x86_64 (or ARM64 if supported) | Ubuntu/Fedora/RHEL base compatibility |
| **Builder Compute Type** | CPU/RAM/Storage focused — NO GPUs required for this node type | Isolated build environment; GPUs reserved strictly for target test harnesses |
| **Docker Version** | v20.10+ with BuildKit enabled | Required for `DOCKER_BUILDKIT=1` builds |
| **Storage on Builder** | **≥500GB dedicated capacity** | Root partition used only for OS; `/rocm-builder` handles all image layers and registries |
| **Data Root Directory** | `/rocm-builder` (Mounted) | Configured via `daemon.json` to isolate build space from system root |

---

### 🧱 6.1 Hardware Readiness Verification (Builder Node)
Before attempting matrix builds, every builder node must pass the `verify_builder_setup.sh` checks:

| Requirement | Description |
|-------------|-------------|
| **Registry Alias Identity** | Must resolve dynamically via `getent hosts` or strict `/etc/hosts` parsing. No longer bound to hardcoded IPs |
| **Docker Root Dir Alignment** | Must be configured as `/rocm-builder` and active in daemon config |
| **Storage Capacity** | Minimum **500GB total volume** on the `/rocm-builder` mount point |
| **Directory Permissions** | Strict ownership: `root:root` mode `0700` (Required for Docker security) |
| **Docker Runtime** | Must be running and accessible by a non-root user in the `docker` group |

**Deployment Checksums**: Verify deployment integrity across all test nodes using standard image digests to ensure consistency.

---

# Section 7: Persistent State & Results Database (v0.3) — PostgreSQL

**Purpose**: Replace the current file-scavenging results path (per-run `*-result.json` files, `all-results.jsonl`, `*_build_state.json` — which disagree on schema, location, and writer) with **one durable, queryable source of truth** for:

- the **build queue** and build status/failures (builder nodes),
- the **test queue** and test status/failures across all tester nodes,
- **artifacts** (build logs, docker-run log, `test.log`, AI `analysis.log`, Dockerfiles, prompts) stored once, referenced everywhere,
- **baselines** as first-class, GC-protected objects (a run is judged against a pinned previous run),
- the **dashboard and API** as pure read-only SQL projections.

**Supersedes**: the legacy result-JSON flow (`ci-trigger/dashboard/app.py` globbing `*-result.json`, `orchestrator.sh → all-results.jsonl`). That path is frozen as-is until Phase 7.5 below completes, then removed.

#### 🎯 Design Invariants (non-negotiable)

| # | Invariant | Rationale |
|---|-----------|-----------|
| 1 | **The DB stores indexes, receipts, and summaries — never blobs** | A 10-year DB stays ≤ few GB; logs live in the artifact store |
| 2 | **Artifacts are content-addressed by SHA-256 and machine-independent** | Identical `Dockerfile`/logs across runs dedupe; no path ever becomes a reference |
| 3 | **Only `state-svc` writes to Postgres** (`rocmtest` role); dashboard holds `dashboard_reader` (SELECT-only) | A dashboard bug can never corrupt state |
| 4 | **The queue *is* the `jobs` table** (status `queued → running → passed/failed/timeout/stuck`) | No separate queue system; atomic claim = one guarded `UPDATE` |
| 5 | **Baseline pins protect artifacts from GC** | A 3-month-old pinned baseline run must not be aged out |
| 6 | **Runners are idempotent clients** (`PUT artifact` → `POST job`; both retryable) | Crashed/retired tester nodes never leave half-states |

#### 📍 7.1 Deployment Topology

Consistent with Section 6 (builder = no-GPU CPU/storage node; testers = GPU nodes): the state stack sits on the **builder-class node** (or a dedicated state node of the same class), reached by tester nodes in the same direction they already reach the registry.

```
  TESTER NODE (any, GPU)                     BUILDER / STATE NODE
  ┌──────────────────────┐                   ┌───────────────────────────────┐
  │ rocm-distro-containers│                  │  docker compose: state.yml    │
  │  <distro>/<rel>/<pkg> │ ── docker pull   │  ┌────────────┐  ┌───────────┐ │
  │  /check (recipe+run)  │ ◄──────────────── │  │ state-db   │  │ state-svc │ │
  │  run.sh (runner CLI)  │ ─┬────────────────┼─►│ postgres:16│  │ (Flask)   │ │
  └──────────────────────┘  │  1. PUT /artifacts?key=<sha256>  └────┬───────┘ │
                            │  2. POST /jobs/<job_id> (atomic row)  │          │
                            ▼                                       ▼          │
                     (network egress to state:8443 required)   ARTIFACT STORE │
                                                        /rocm-db/artifacts
                                                        ┌────────────────────┐  │
                                                        │ DASHBOARD (ro)     │  │
                                                        │ generic SQL pane   │  │
                                                        └────────────────────┘  │
└──────────────────────────────────────────────────────────────────────────────┘
```

**Network requirement (verify before build)**: every tester node must reach `state:<port>` (planned `8443`, HTTPS). This is the *push* direction — mirror of the existing registry pull path. If egress is filtered, reconsider before implementation (pull-from-nodes design is to be avoided).

#### 💽 7.2 Dedicated Disk & Filesystem

The store is **not** for the database alone — Postgres data is ~1–2 GB even long-term; the artifacts are the hundreds-of-GB part. One dedicated disk serves both, plus the on-host copy of backups:

```
mkfs.ext4 -L rocmstate /dev/sdX
/dev/disk/by-label/rocmstate  /rocm-db  ext4  defaults,noatime  0 2
/rocm-db/
  pg/           # postgres data dir (bind-mounted into state-db)
  artifacts/    # state-svc content store (bind-mounted into state-svc)
  backups/      # on-host pg_dump + artifact tar (the *copy* must live OFF-host)
```

| Decision | Choice | Notes |
|----------|--------|-------|
| Filesystem | **ext4** | Not ext3 (EOL): no 64-bit growth path, no modern tooling. xfs is equally acceptable on Fedora hosts. ZFS only if already in use (snapshots/compression are nice-to-have, not required) |
| Mount options | `defaults,noatime` | Eliminates atime churn on a disk hosting a DB |
| Quotas | ext4 dir-quota on `artifacts/` (optional, set to disk − pg headroom) | Keeps `pg/` uncapped |
| Container ownership | **UID 999** (official `postgres` image) | Fresh empty `pg/` + first-init lets the entrypoint `chown` itself; otherwise `chown 999:999 /rocm-db/pg` on host. `state-svc` runs the same UID |

#### 🔄 7.3 Runner → State Protocol (the only write path)

Tester/builder nodes talk to **two idempotent endpoints**; nothing else touches the DB:

```sh
# 1) Content-addressed artifact upload (deduped server-side, safe to retry)
curl -sfT "$file" -H "Authorization: Bearer $NODE_TOKEN" \
     https://state:8443/artifacts?key=$(sha256sum "$file" | cut -d' ' -f1)

# 2) Atomic job record — succeeds only if ALL referenced sha256s are present
curl -sf -XPOST -H "Authorization: Bearer $NODE_TOKEN" \
     -d @job.json https://state:8443/jobs/$JOB_ID
```

`job.json` (single canonical record — fixes the `result`/`status` field split forever):

```json
{
  "kind": "test",
  "status": "failed",
  "package": "rocrand", "distro": "fedora", "release": "rawhide",
  "node": "mi250-node-2", "gpu": "gfx1100",
  "baseline_job_id": "t-2026-08-01-…",
  "build_ids": {"koji": "…"},
  "image": "rocm-builder:5000/rocrand-fedora:sha256-<digest>",
  "test_cases": [{"suite": "rocrand_basic_tests", "case": "…", "status": "failed", "duration_ms": 12}],
  "artifacts": [
    {"type": "test_log",       "sha256": "…"},
    {"type": "docker_run_log", "sha256": "…"},
    {"type": "analysis_log",   "sha256": "…"},
    {"type": "dockerfile",     "sha256": "…"}
  ]
}
```

Guarantees: content-addressed upload decouples ordering → `POST /jobs` is one transaction that is all-or-nothing; any retry sequence (PUT, PUT, POST, POST) is safe (`artifacts` unique on `sha256`; `jobs` unique on `job_id`). **Machine-local directories (`/sfs/…`, `~/rocm/…`) are scratch only — safe to delete at any time.**

Onboarding a node = one `nodes` row (`node_id`, `token`, class `build|test`, capabilities). `verify_state_setup.sh` mirrors the existing verify-script pattern: reach `state:8443`, present node token, write+delete a canary queued job.

#### 🗄️ 7.4 Schema (v1, in `schema.sql` — the contract)

```sql
CREATE TABLE nodes (
  node_id text PRIMARY KEY, class text CHECK (class IN ('build','test')),
  token_hash text NOT NULL, gpu text, arch text,
  registered_at timestamptz DEFAULT now(), last_seen timestamptz
);

CREATE TABLE jobs (
  job_id           text PRIMARY KEY,          -- 'b-2026-10-18-…' | 't-2026-10-18-…'
  kind             text NOT NULL CHECK (kind IN ('build','test','analyze')),
  status           text NOT NULL DEFAULT 'queued'
                   CHECK (status IN ('queued','running','passed','failed','timeout','skipped','stuck')),
  package text NOT NULL, distro text NOT NULL, release text NOT NULL,
  gpu text, node text REFERENCES nodes(node_id),
  baseline_job_id text REFERENCES jobs(job_id),
  built_by_job_id text REFERENCES jobs(job_id),   -- test → the build job it tested
  image     text,                                 -- rocm-builder:5000/<pkg>-<distro>:sha256-…
  build_ids jsonb,                                 -- koji/launchpad/pacman ids from pollers
  test_total int, test_passed int,                 -- parsed from test.log (GTest)
  failure_class text,                               -- deps|build_error|no_gpu|lib_missing|test_crash|assertion|timeout
  failure_summary text,                             -- ≤1 KB classifier output at finish
  queued_at timestamptz DEFAULT now(),
  started_at timestamptz, finished_at timestamptz, last_heartbeat timestamptz,
  UNIQUE (kind, package, distro, release, gpu, node, queued_at)
);

CREATE TABLE artifacts (
  artifact_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  job_id text REFERENCES jobs(job_id),             -- NULL for pre-job uploads
  type text NOT NULL,                               -- test_log|run_log|build_log|analysis_log|dockerfile|prompt|rocminfo|result_json|core
  sha256 char(64) NOT NULL, size_bytes bigint NOT NULL, mime text,
  node_local_path text,                             -- EPHEMERAL debug field; never a reference
  stored_at timestamptz DEFAULT now(),
  UNIQUE (job_id, type, sha256)
);
CREATE TABLE artifacts_global (sha256 char(64) PRIMARY KEY, first_seen timestamptz, size_bytes bigint);  -- dedup ledger

CREATE TABLE test_cases (
  job_id text REFERENCES jobs(job_id), suite text, case_name text,
  status text, duration_ms int, log_excerpt text,
  PRIMARY KEY (job_id, suite, case_name)
);

CREATE TABLE baselines (
  package text, distro text, role text,            -- 'default' | 'perf' | 'copr-preview'
  pinned_job_id text REFERENCES jobs(job_id),
  active boolean DEFAULT true, pinned_at timestamptz DEFAULT now(),
  PRIMARY KEY (package, distro, role)
);

CREATE TABLE log_tail (job_id text PRIMARY KEY REFERENCES jobs(job_id), tail text NOT NULL);  -- last 64 KB, failed jobs only

CREATE TABLE dashboard_panes (                      -- "dashboard as data" (see 7.7)
  pane_id text PRIMARY KEY, title text NOT NULL,
  kind text NOT NULL CHECK (kind IN ('table','bar','line','kpi')),
  sql text NOT NULL, sort_order int, enabled boolean DEFAULT true
);
```

Key views (dashboard *and* API both SELECT these — they can never disagree):

```sql
CREATE VIEW v_build_queue AS SELECT job_id, package, distro, status, node,
       now()-queued_at AS queued_for FROM jobs
 WHERE kind='build' AND status IN ('queued','running') ORDER BY queued_at;

CREATE VIEW v_test_queue AS SELECT t.*, b.job_id AS built_by
 FROM jobs t LEFT JOIN jobs b ON b.job_id = t.built_by_job_id
 WHERE t.kind='test' AND t.status IN ('queued','running','stuck') ORDER BY t.queued_at;

CREATE VIEW v_regressions AS                          -- the killer query
 SELECT c.job_id, c.package, c.distro, c.release, tc.suite, tc.case_name
 FROM test_cases tc
 JOIN jobs c ON c.job_id = tc.job_id AND c.status='failed'
 JOIN jobs b ON b.job_id = c.baseline_job_id AND b.status='passed'
 JOIN test_cases bt USING (suite, case_name)
 WHERE tc.status='failed' AND bt.status='passed';

CREATE VIEW v_gc_candidates AS                         -- baseline-aware retention (7.6)
 SELECT j.job_id, a.sha256 FROM jobs j JOIN artifacts a USING (job_id)
 WHERE (j.status='passed' AND j.finished_at < now()-interval '30 days')
    OR (j.status IN ('failed','timeout') AND j.finished_at < now()-interval '180 days')
   AND a.type NOT IN ('result_json','dockerfile','prompt')
   AND NOT EXISTS (SELECT 1 FROM baselines bs WHERE bs.active AND bs.pinned_job_id = j.job_id);
```

Roles:

```sql
CREATE ROLE rocmtest LOGIN PASSWORD '…';             -- writer: state-svc only
CREATE ROLE state_svc LOGIN PASSWORD '…';
CREATE ROLE dashboard_reader LOGIN;                   -- no password: unix-socket/proxy only; SELECT only
GRANT SELECT ON ALL TABLES IN SCHEMA public TO dashboard_reader;
```

#### 🐳 7.5 Deployment (compose, on the state node)

```yaml
services:
  state-db:
    image: postgres:16
    volumes:
      - /rocm-db/pg:/var/lib/postgresql/data
      - ./schema.sql:/docker-entrypoint-initdb.d/01-schema.sql:ro
    env: { POSTGRES_DB: rocmtest, POSTGRES_USER: rocmtest, POSTGRES_PASSWORD: ${POST…_PW} }
    healthcheck: { test: ["pg_isready", "-U", "rocmtest"], interval: 5s }

  state-svc:
    image: rocm/state-svc:local        # PUT /artifacts, POST /jobs, GET /api/*, static artifact serving
    user: "999:999"
    volumes: [ /rocm-db/artifacts:/srv/artifacts ]
    ports: [ "8443:8443" ]
    depends_on: { state-db: { condition: service_healthy } }

  dashboard:
    image: rocm/dashboard:local        # SELECT-only pane renderer (replaces ci-trigger/dashboard/app.py)
    environment: { DATABASE_URL: postgresql://dashboard_reader@state-db/rocmtest }
    ports: [ "5002:5001" ]              # host 5002 (see 7.5.1); app still listens on 5001 in-container
    depends_on: [ state-svc ]
```

- Artifacts served at `https://state:8443/artifacts/<sha256>` — uniform download links from any browser, on any machine.
- **Backups**: nightly `pg_dump -Fc` copied **off-host** (builder → another machine) + on-host copy in `/rocm-db/backups/`; artifact integrity is self-verifying via SHA-256 (a cold tar can be re-built from the `artifacts_global` ledger + any surviving copy).

#### 🔀 7.5.1 Registry Tiering (co-hosting with the builder) & Dashboard Port Decision

**Premise**: the state node MAY be the same machine as the builder (shared `/rocm-builder` Docker data-root). Two registries on that machine keep the two image tiers separated by boundary instead of by convention:

| | `rocm-builder:5000` (existing) | `rocm-builder:5001` (new, infra) |
|---|---|---|
| Contents | matrix test images (`<distro>-<pkg>`) | infrastructure: `postgres:16`, `rocm-state-svc`, `rocm-dashboard` |
| Who pulls | all testers (+ dashboard) | **builder only** (same host) |
| Trust exposure in tester `daemon.json` | yes (`daemon.json.tester`) | **no — testers never trust this port** |
| Data character | build *artifacts* (receipts) | commodity, infinitely repullable |
| Storage | large (500 GB world) | hundreds of MB |

**Consequences:**
- Tester `samples/daemon.json.tester` is **unchanged** — it cannot pull infrastructure images because that port is absent from its `insecure-registries` list. The "don't push system images into the test catalog" rule stops being a discipline.
- **State node ≠ builder:** that node's `daemon.json` needs the `:5001` trust entry — see `samples/daemon.json.db` (checked by `verify_db_setup.sh`, step 6; merge `daemon.json.builder` into the same file if the node is also the builder).
- **State node == builder (co-hosted):** same-host push/pull via `127.0.0.1:5001` is Docker's default loopback-HTTP exception (any port). `daemon.json.builder` unchanged.
- Storage layout on a shared node:

```text
/rocm-builder/
├── docker/            # data-root: test images + build cache (as today)
├── registry-test/     # storage volume for :5000 (large)
└── registry-infra/    # storage volume for :5001 (small; GB quota is plenty)
```

**Naming (append to §6 naming policy):**
- test image: `rocm-builder:5000/<distro>-<pkg>:latest` (unchanged)
- state-svc:  `rocm-builder:5001/rocm-state-svc:local`
- dashboard:  `rocm-builder:5001/rocm-dashboard:local`
- postgres:   pin `rocm-builder:5001/postgres:16` so the state stack boots offline

**Port decision (dashboard): `5001 → 5002`.** The dashboard currently occupies host port 5001; the infrastructure registry takes 5001. The *in-container* app keeps listening on 5001 — only the host mapping changes (`5002:5001` in compose, `localhost:5002` for humans). Rationale: the registry port is baked into image references forever; the dashboard port is a one-line human-facing change.

**Catalog hygiene:** `verify_registry_test.sh` continues to inventory `:5000` only — the `:5001` catalog is deliberately outside that view (infrastructure, not artifacts).

#### ♻️ 7.6 Retention & GC (policy = SQL, executor = `jobctl gc`)

| Class | Lifetime | Notes |
|-------|----------|-------|
| `jobs` / `test_cases` / receipts (`result_json`) / `dockerfile` / `prompt` | **forever** | rows are ~KB; reproducibility inputs |
| passed-run logs (`test_log`, run/build logs) | 30 days hot → cold | pass *record* persists in DB |
| failed/timeout-run logs | **180 days** → cold | triage history pays the higher price |
| core dumps | never auto-deleted | quarantine, explicit review |
| baseline-pinned runs | **exempt while pinned** | enforced in `v_gc_candidates` |
| images in registry | follow build retention; always pin `sha256-…` digests | DB row is the receipt; see Section 6.1 checksums |

`jobctl gc --dry-run` selects `v_gc_candidates`, deletes files, then rows (marks `expired`, reaps on next pass). Cold tier: rotated `tar.zst` under `backups/` or a second slow volume.

#### 🖥️ 7.7 Dashboard as SQL Projection

- Panes are rows in `dashboard_panes` (`title`, `kind`, `sql`); the app is a ~80-line generic renderer — **a new view on the dashboard = one `INSERT`, no deploy**.
- Seed panes: `v_build_queue`, `v_test_queue`, `v_pass_rate_by_distro` (30 d), `v_recent_failures` (with inline `log_tail` + download links), `v_regressions` (baseline diff — "which exact case broke vs baseline").
- Optional live update via `LISTEN/NOTIFY` in place of 5 s polling.
- Retires: `ci-trigger/dashboard/app.py` (its `request`-import bug, mangled `/api/latest-results/(d+):i` route, and `status` vs `result` mismatch all die with it). `orchestrator.sh`'s `all-results.jsonl` and the smoke-script `*-result.json` writers are replaced by the `job.json` report of 7.3.

#### ✅ 7.8 Phased Delivery & Definition of Done

| Phase | Deliverable | Done when |
|-------|-------------|-----------|
| 7.1 | `state/` dir: `schema.sql`, `compose state.yml`, `verify_state_setup.sh` | `docker compose up` on state node; canary job via curl succeeds; dashboard panes render from views |
| 7.2 | `state-svc` (~200 LOC): PUT artifact / POST job / static / read API / node-token auth | idempotent re-PUT + duplicate POST verified; artifact missing ⇒ 409 |
| 7.3 | Runner report-stub in `run.sh` (replaces `docker cp` cluster); GTest `test.log` → `test_cases` parser; `failure_class` classifier (grep-based v1) | one `check/` run on a tester node appears fully on dashboard with tail, cases, downloads |
| 7.4 | `jobctl` node-side CLI (register/claim/report/gc client); builder wires image-digest pinning | second node onboarded with ≤3 commands |
| 7.5 | GC cron + off-host backup drill; **delete legacy result-JSON path** (dashboard/app.py, orchestrator jsonl, smoke-script writers) | dashboard still green after deletion; 30-day retention verified by dry-run |
