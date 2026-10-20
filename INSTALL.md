# INSTALL — Setting Up the ROCm Distro-Tester Infrastructure

Step-by-step deployment runbook for all three node roles. Design docs:
[PLAN.md](./PLAN.md) (§6 registry, §7 state stack), [README.md](./README.md).

## Machine roles (used throughout this document)

| Role | Machine name | What it runs | Notes |
|---|---|---|---|
| **rocm-tester-registry** | builder / registry host | `rocm-registry` `:5000`, `rocm-infra-registry` `:5001`, image builds, pollers | dedicated disk ≥500 GB at `/rocm-builder` |
| **rocm-infra** | infra image host | infra registry `:5001` + pinned images (postgres, state-svc, dashboard) | **standard setup: same machine as rocm-tester-registry** (co-hosting, PLAN §7.5.1); separate only if you split the tiers |
| **rocm-db** | state node | `rocm-state-db` (`:5432`), optional dashboard (`:5002`) | **standard setup: rocm-infra or the same machine**; separate only if you split it |
| **rocm-tester** | generic GPU machine | test image containers (`--device=/dev/kfd`) | any number of testers |

```
rocm-tester-registry              rocm-infra / rocm-db           rocm-tester (GPU)
 (builder)
 ┌────────────────────────┐   ┌───────────────────────┐   ┌─────────────────────
 │ rocm-registry   :5000 ───────►│ rocm-state-db :5432     │◄───────│ run test images      
 │ rocm-infra-reg :5001 ────►│   (postgres from :5001)   │  :5000 pull │ /dev/kfd             
 │ /rocm-builder/ (root,755)│   │ /rocm-db/ (pg/→uid 999) │              └─────────────────────
 └────────────────────────┘   └───────────────────────┘
```

**Which machine runs what (quick map — detail per script below):**

| Script | Runs on |
|---|---|
| `ci-trigger/scripts/setup_docker_registry.sh` | **rocm-tester-registry** (and **rocm-infra** separately only if tiers are split) |
| `ci-trigger/scripts/pin_infra_images.sh` | **rocm-infra** — i.e. the machine the infra registry is on (= rocm-tester-registry in the standard co-hosted setup) |
| `ci-trigger/scripts/setup_db.sh` | **rocm-db** |
| `ci-trigger/scripts/setup_dashboard.sh` | **rocm-db** (where the DB is) — or rocm-tester-registry |
| `scripts/build-all-images.sh` | **rocm-tester-registry** (the builder) |
| `scripts/verify_builder_setup.sh` | **rocm-tester-registry** |
| `scripts/verify_registry_test.sh` | any **rocm-tester** (verifies the reachability contract from a tester) |
| `scripts/verify_registry_infra.sh` | **rocm-infra** / **rocm-db** — machines that *consume* `:5001` |
| `scripts/verify_db_setup.sh` | **rocm-db** |
| `scripts/verify_tester_setup.sh`, `verify_network_registry.sh`, `verify_state_setup.sh` | any **rocm-tester** |

**Trust model**
- Testers trust **only** `rocm-builder:5000` (`samples/daemon.json.tester`).
- The state node trusts `rocm-builder:5001` **only if it is not the rocm-infra host** (`samples/daemon.json.db`).
- A registry host ↔ its own registries uses `127.0.0.1` — Docker's default loopback-HTTP exception covers any local port; no `daemon.json` entry needed.

> **Naming note:** `rocm-builder` (as in `rocm-builder:5000/postgres:16`) is the registry's
> **alias** — the hostname part of the image reference used in `insecure-registries` and all
> pull/push commands (keep it constant; it is baked into image names). It is *not* a machine
> name: the alias lives on whichever machine hosts that tier (standard: rocm-tester-registry).
> The *role* names above (rocm-tester-registry, rocm-infra, rocm-db, rocm-tester) describe
> machines. Adjust the IP/hostname inside `samples/daemon.json.*` to match your network.

**Permission model (no root needed in the scripts)**
- Everything the scripts touch is **root-owned, mode 755** (user-readable/traversable).
- Registry containers run as root and write their data through the root docker daemon — normal users never need write access under `/rocm-builder`.
- SELinux: the registry bind-mounts use Docker's `:z` option (applied inside `setup_docker_registry.sh`), so Enforcing policies do not block writes.

---

## 1. Builder / rocm-tester-registry (test + infra registries, image builds)

### 1.1 Admin prerequisites (one-time, needs root) — *on the rocm-tester-registry machine*

```bash
# Distro packages — Fedora/RHEL:
sudo dnf install docker-ce docker-ce-cli containerd.io && sudo systemctl enable --now docker

# Storage root for docker data + both registries (dedicated disk, ≥500 GB, XFS preferred):
sudo mkdir -p /rocm-builder/registry-test /rocm-builder/registry-infra
sudo chown -R root:root /rocm-builder
sudo chmod 755 /rocm-builder /rocm-builder/registry-test /rocm-builder/registry-infra

# Docker data-root (keeps layers off the root partition):
cp samples/daemon.json.builder /etc/docker/daemon.json   # adjust "data-root" if the build disk differs
sudo systemctl restart docker
sudo usermod -aG docker $USER   # then re-login for the group to take effect
```

### 1.2 Deploy both registries — *runs on: rocm-tester-registry (both tiers; or rocm-infra for `--tier infra` if split)*

```bash
./ci-trigger/scripts/setup_docker_registry.sh --dry-run    # preview
./ci-trigger/scripts/setup_docker_registry.sh -v           # real

# → rocm-registry         :5000   (test images)
# → rocm-infra-registry   :5001   (postgres / state-svc / dashboard)
```

Verify:

```bash
bash scripts/verify_registry_test.sh      # any rocm-tester: :5000 reachable + cat
bash scripts/verify_registry_infra.sh     # rocm-infra/rocm-db: :5001 reachable
curl -s http://127.0.0.1:5000/v2/_catalog # on the rocm-tester-registry host
curl -s http://127.0.0.1:5001/v2/_catalog # on the rocm-infra host
```

### 1.3 Pin infra & rolling-base images

*runs on: rocm-infra (the machine the infra registry is on — in the standard
co-hosted setup that is the rocm-tester-registry machine)*

```bash
./ci-trigger/scripts/pin_infra_images.sh --dry-run --bases    # preview
./ci-trigger/scripts/pin_infra_images.sh --bases              # initial deploy: everything
```

One pin per image = `pull (if needed) → tag → push → verify manifest`, and each gets a
digest twin (``<repo>:sha256-<12>``) so receipts can name the exact revision (PLAN §6.1 style).

| Pinned | Pinned name (FROM / pull) | Refresh policy |
|---|---|---|
| `postgres:16` (required) | `rocm-builder:5001/postgres:16` | local reused; `--rebuild` to re-pull |
| `rocm/state-svc`, `rocm/dashboard` (when built, PLAN §7.5) | `rocm-builder:5001/rocm-{state-svc,dashboard}:local` | local only, not re-pulled |
| `fedora:rawhide` | `rocm-builder:5001/fedora-rawhide:rawhide` | **always re-pulled from upstream** |
| `ubuntu:latest` | `rocm-builder:5001/ubuntu-latest:latest` | **always re-pulled from upstream** |
| `archlinux:latest` | `rocm-builder:5001/archlinux-latest:latest` | **always re-pulled from upstream** |
| `quay.io/centos/centos:stream10` | `rocm-builder:5001/centos-stream10:stream10` | **always re-pulled from upstream** |

**Before each CI wave (rocm-distro-containers builds):**

```bash
./ci-trigger/scripts/pin_infra_images.sh --bases-only
# re-pins ONLY the rolling bases to the current upstream head — the whole wave then
# builds against ONE consistent base revision (no rawhide drift between builds),
# and the postgres/state-stack pins (5001 infra tier) are left untouched.
```

Re-run here — and not on rocm-db/rocm-tester — because it **pushes** to `127.0.0.1:5001`
(loopback trust only exists on the registry's own host) and pulls the upstream images.
Dockerfiles then build with `FROM rocm-builder:5001/fedora-rawhide:rawhide` etc. (a
`ARG BASE=fedora:rawhide` / `FROM ${BASE}` form lets non-CI builds keep the plain upstream refs).

### 1.4 Build & push test images — *runs on: rocm-tester-registry (the builder)*

```bash
./scripts/build-all-images.sh --force-rebuild        # or: ./scripts/build-all-images.sh hipblas-fedora
bash scripts/verify_builder_setup.sh                 # full builder-node health (storage, docker, IP)
```

Test images land as `rocm-builder:5000/<distro>-<package>:latest` (PLAN §6).

---

## 2. State node / rocm-db (results DB) — *all of this runs on the rocm-db machine;
in the standard setup that may be the same machine as rocm-infra/rocm-tester-registry*

### 2.1 Admin prerequisites (one-time)

```bash
# Dedicated disk ≥ 500 GB, ext4; /rocm-db with the three data areas (PLAN §7):
sudo mkdir -p /rocm-db/pg /rocm-db/artifacts /rocm-db/backups
sudo chown -R root:root /rocm-db && sudo chmod 755 /rocm-db /rocm-db/*
# pg/ will be chowned to uid 999 (postgres image user) by setup_db.sh at deploy

# ONLY if rocm-db is a different machine than rocm-infra — trust the infra registry:
cp samples/daemon.json.db /etc/docker/daemon.json    # merge with existing daemon.json; adjust host/IP
sudo systemctl restart docker
```

### 2.2 Deploy the database — *runs on: rocm-db*

```bash
bash scripts/verify_db_setup.sh        # /rocm-db, trust model, docker — full check
./ci-trigger/scripts/setup_db.sh --dry-run
./ci-trigger/scripts/setup_db.sh       # pulls rocm-builder:5001/postgres:16 (fallback: upstream),
                                       # generates+persists a password (/rocm-db/rocm-state.env, 600),
                                       # starts rocm-state-db on :5432 with healthcheck
./ci-trigger/scripts/setup_db.sh --status    # status any time, on the rocm-db machine
```

---

## 3. Tester / rocm-tester (GPU machine) — *all of this runs on the rocm-tester machine*

```bash
# One-time (admin): trust ONLY the test registry tier:
cp samples/daemon.json.tester /etc/docker/daemon.json   # adjust builder hostname/IP
sudo systemctl restart docker

bash scripts/verify_tester_setup.sh                      # runtime + trust check
bash scripts/verify_network_registry.sh                   # :5000 reachable from here
bash scripts/verify_state_setup.sh                        # state-stack reachability (PLAN §7.x)

docker pull  rocm-builder:5000/hipblas-fedora:latest
docker run --rm --device=/dev/kfd rocm-builder:5000/hipblas-fedora:latest
```

---

## Optional: results dashboard — *runs on the machine hosting the DB (rocm-db),
or on rocm-tester-registry if you prefer*

```bash
./ci-trigger/scripts/setup_dashboard.sh -v
# → http://localhost:5002   (host port 5002; the app keeps 5001 in-container — PLAN §7.5.1)
# → API: curl http://localhost:5002/api/summary | jq '.statistics'
```

---

## Verification matrix (who runs what)

| Check (script) | Run on | Purpose |
|---|---|---|
| `scripts/verify_builder_setup.sh` | rocm-tester-registry | docker, data-root, IP, /rocm-builder 755 + subdirs |
| `scripts/verify_registry_test.sh` | any rocm-tester | `:5000` reachable + catalog readable (tester's contract) |
| `scripts/verify_registry_infra.sh` | rocm-infra / rocm-db | `:5001` reachable + catalog readable |
| `scripts/verify_db_setup.sh` | rocm-db | /rocm-db areas, `:5001` trust, docker |
| `ci-trigger/scripts/setup_db.sh --status` | rocm-db | DB container/health/pg_isready snapshot |
| `scripts/verify_tester_setup.sh` | any rocm-tester | runtime + `:5000` trust |
| `scripts/verify_network_registry.sh` | any rocm-tester | tester → `:5000` network path |
| `scripts/verify_state_setup.sh` | any rocm-tester | tester → state stack (DB/dashboard) reachability |

## Troubleshooting

### 1. `docker push` fails with `error from registry: unknown error` (SELinux / stale container)

**Symptom:** on rocm-infra, `pin_infra_images.sh` (or any push to `:5000`/`:5001`) fails
with `error from registry: unknown error`. The registry itself looks healthy —
`/v2/_catalog` answers 200. The registry's own log shows the real error:

```text
time="…" level=error msg="response completed with error" err.code="unknown" \
  err.detail="filesystem: mkdir /var/lib/registry/docker: permission denied" \
  err.message="unknown error" … http.request.method=POST … http.response.status=500
```
(Repeated `HEAD /v2/<name>/blobs/sha256:… → 404 "blob unknown"` lines immediately
before are **normal** — the client pre-checks each blob. The `POST …/blobs/uploads/ → 500`
is the failure. `docker push` renders that 500 as `unknown error`.)

**Root cause:** SELinux **Enforcing** host. A confined container (`container_t`) was denied
writing its bind-mounted store — i.e. the registry container was started **without the `:z`
SELinux relabel**. Classic stale-container case: it was started by an older script/compose
(or hand-rolled) and `--restart unless-stopped` keeps serving the broken mount. Read OK /
write denied is the fingerprint.

**Checklist (on rocm-infra):**

```bash
# 1) confirm the SELinux denial in the registry's log (the smoking gun):
docker logs rocm-infra-registry 2>&1 | grep -m3 'err.detail'
# expect: filesystem: mkdir /var/lib/registry/docker: permission denied

# 2) see how the current container was started (want `:z` in the mount mode):
docker inspect rocm-infra-registry --format '{{range .Mounts}}{{.Source}} -> {{.Destination}} mode={{.Mode}}{{end}}'

# 3) prove the store is writable from INSIDE the container (the exact failing op, forced early):
docker exec rocm-infra-registry sh -c 'mkdir /var/lib/registry/docker 2>&1 && echo ok'   # -> ok

# 4) confirm SELinux + the fix's evidence (mount should carry the seclabel option
#    when started with :z):
getenforce
docker exec rocm-infra-registry sh -c 'grep "var/lib/registry" /proc/mounts'
docker exec rocm-infra-registry cat /proc/self/attr/current    # container_t:s0:cNN,cNN
```

**Fix — recreate the container with the current script (which mounts `:z`), then re-push:**

```bash
docker rm -f rocm-infra-registry                       # kill the stale, unrelabeled mount
./ci-trigger/scripts/setup_docker_registry.sh --tier infra   # re-creates with -v …:/var/lib/registry:z 
                     # (test tier: --tier test / default both)
docker exec rocm-infra-registry sh -c 'mkdir /var/lib/registry/docker && echo ok'  # -> ok
./ci-trigger/scripts/pin_infra_images.sh                # now push -> catalog -> verify succeeds
```

A fresh `:z` mount re-labels the store dir on startup, so any partial/failed blob state from
the broken container is harmless. Both startup paths in this repo apply `:z`
(`setup_docker_registry.sh` and `docker-compose.registry.yml`); if you hand-roll a registry
container on an Enforcing host, add `:z` yourself or it will fail exactly like this.

> **Do not** "fix" it by lowering the host dir's DAC mode (e.g. `chmod 777`) or switching
> SELinux to Permissive — that hides the confinement and breaks the model. The relabel is
> the correct, least-privilege fix and lets the dir stay `root:755`.

### 2. `"dial tcp: lookup rocm-builder: no such host"` on push

You pushed under the alias from rocm-db (wrong machine). Pushes happen **on rocm-infra**
via `127.0.0.1:<port>`; only rocm-db pulls the result. `rocm-builder` is the registry
**alias** (image-reference hostname), not resolvable from a non-builder host unless you
map it — use loopback on the registry host.

### 3. `MANIFEST_UNKNOWN: OCI manifest found, but accept header does not support OCI manifests`

The image is actually **present** — this is the verification probe, not the store.
Add an `Accept` header listing `application/vnd.oci.image.manifest.v1+json` (already
handled in `pin_infra_images.sh`'s `manifest_ok()`).

### 4. `"insecure registry"` errors from a tester

`daemon.json` lacks the `rocm-builder:5000` entry, or docker wasn't restarted afterwards.
Use `samples/daemon.json.tester`, then `sudo systemctl restart docker`.

### 5. Port map (do not rearrange)

`5000` test registry · `5001` infra registry · `5432` state DB · `5002` dashboard (host).
Do not repurpose `5001` — it is baked into pinned image names (`rocm-builder:5001/postgres:16`).

