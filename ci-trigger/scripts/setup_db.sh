#!/bin/bash
# =============================================================================
# setup_db.sh - Initialize & start the state-stack PostgreSQL (state-db)
# =============================================================================
# ASSUMES (preconditions; do NOT verify deeply, but fail fast if obviously off):
#   • scripts/verify_db_setup.sh has PASSED on this node:
#       - /rocm-db mounted (dedicated disk), ext4, pg/ artifacts/ backups/ present
#       - docker present + daemon.json trusts rocm-builder:5001 (unless co-hosted)
#   • ci-trigger/scripts/setup_docker_registry.sh has been run → rocm-infra-registry
#       is up on host :5001 and has `postgres:16` already pushed to it.
#
# This script (what it does, deliberately small):
#   1. Locate postgres:16 on the infra registry → use as the container image.
#   2. Pre-create /rocm-db/pg owned by UID 999 (the postgres image user).
#   3. Generate a default password if none supplied, persist it in
#      /rocm-db/rocmstate.env (chmod 600) and point it at POSTGRES_PASSWORD.
#   4. Deploy rocm-state-db as a long-lived container on host :5432 with a
#      healthcheck, a json-file log, and a --status sub-command.
#
# DEBUGGABILITY (since this is a start and will need iteration):
#   • Every stage is logged to a file (see LOG_FILE below) and to stderr.
#   • `--status` prints a full diagnostic snapshot (container, health,
#     last logs, pg_isready, /rocm-db capacity & ownership).
#   • On any failure we print WHICH step failed + the log file + a hint.
#
# Usage:
#   ./setup_db.sh [--status] [--dry-run] [--drop] [--reinit] [--verbose]
#   ./setup_db.sh --help
#
# Env overrides:
#   STORAGE_ROOT (default /rocm-db), STATE_IP / STATE_HOST, INFRA_PORT (5001),
#   DB_PORT (5432), DB_CONTAINER (rocm-state-db), POSTGRES_PASSWORD (optional)
# =============================================================================

set -euo pipefail

STORAGE_ROOT="${STORAGE_ROOT:-/rocm-db}"
STATE_IP="${STATE_IP:-192.168.1.25}"        # co-hosted builder's own IP, used for pulls
STATE_HOST="${STATE_HOST:-rocm-builder}"     # alias testers/state-nodes use
INFRA_PORT="${INFRA_PORT:-5001}"
DB_PORT="${DB_PORT:-5432}"
DB_CONTAINER="${DB_CONTAINER:-rocm-state-db}"
PG_UID=999
PGDATA_HOST="${STORAGE_ROOT}/pg"
ENV_FILE="${STORAGE_ROOT}/rocm-state.env"
LOG_FILE="${STORAGE_ROOT}/setup_db.log"
PG_VERSION=16

DRY_RUN=false; VERBOSE=false; STATUS=false; DROP=false; REINIT=false

# -----------------------------------------------------------------------------
# Arg parsing
# -----------------------------------------------------------------------------
while [[ $# -gt 0 ]]; do
    case $1 in
        --status) STATUS=true; shift ;;
        --dry-run) DRY_RUN=true; shift ;;
        --drop) DROP=true; shift ;;
        --reinit) REINIT=true; shift ;;
        --verbose|-v) VERBOSE=true; shift ;;
        --help|-h) sed -n '/^# Usage:/,/^# Env overrides:/p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) echo "Unknown option: $1 (see --help)" >&2; exit 1 ;;
    esac
done
if [ "${VERBOSE}" = "true" ]; then set -x; fi

# -----------------------------------------------------------------------------
# Logging helpers (to BOTH stderr and LOG_FILE once the dir is writable)
# -----------------------------------------------------------------------------
_ts() { date '+%Y-%m-%d %H:%M:%S'; }
_tee() { # log to stderr, and append to LOG_FILE if it exists/writable
    local m; m="$*"
    if [ -f "${LOG_FILE}" ] && [ -w "${LOG_FILE}" ]; then
        echo "[$(_ts)] ${m}" >> "${LOG_FILE}"
    fi
    echo -e "[DB @ $(hostname)] $m" >&2
}
info() { _tee "$*"; }
warn() { _tee "WARN: $*"; }
fail() { _tee "ERROR: $*"; fail_hint; exit 1; }
fail_hint() {
    cat >&2 << EOF
  log file : ${LOG_FILE}
  status   : ./setup_db.sh --status
  hints    : docker logs ${DB_CONTAINER}   ·   journalctl -u docker
EOF
}

# -----------------------------------------------------------------------------
# Precondition guards (light — verify_db_setup.sh is the source of truth)
# -----------------------------------------------------------------------------
precheck() {
    command -v docker &>/dev/null || fail "docker CLI is absent — run scripts/verify_db_setup.sh (step 6) and install docker first."
    docker info &>/dev/null || fail "docker daemon is unreachable — start it / fix permissions before running setup_db.sh."
    if [ ! -d "${STORAGE_ROOT}" ]; then
        # Allow dry-run to preview the plan even if the disk isn't here yet.
        [ "${DRY_RUN}" = "true" ] && warn "${STORAGE_ROOT} absent (dry-run: continuing to preview)" || \
        fail "${STORAGE_ROOT} is absent — run scripts/verify_db_setup.sh and mount the dedicated disk first."
    fi
}

# -----------------------------------------------------------------------------
# --status: full diagnostic snapshot (safe to run any time; used for debug)
# -----------------------------------------------------------------------------
do_status() {
    echo "======================================================================"
    echo " state-db status  ($(hostname))  $(date '+%F %T')"
    echo "======================================================================"
    echo "STORAGE_ROOT   = ${STORAGE_ROOT}"
    if [ -d "${STORAGE_ROOT}" ]; then
        echo "  disk usage     : $(df -h "${STORAGE_ROOT}" 2>/dev/null | awk 'NR==2{print $2" total, "$3" used, "$4" free ("$5")"}')"
        echo "  pg/ owner:mode  : $(stat -c '%U:%a' "${PGDATA_HOST}" 2>/dev/null || echo 'absent')"
        echo "  env file       : $( [ -f "${ENV_FILE}" ] && stat -c '%U:%a' "${ENV_FILE}" || echo 'absent' )"
    else
        echo "  (STORAGE_ROOT not present)"
    fi
    echo "--------------------------------------------------------------------"
    if command -v docker &>/dev/null && docker info &>/dev/null; then
        local running image
        running=$(docker ps -q -f name=^"${DB_CONTAINER}\$" 2>/dev/null | head -n1)
        image=$(docker inspect -f '{{.Config.Image}}' "${DB_CONTAINER}" 2>/dev/null || echo '?')
        echo "container ${DB_CONTAINER}:"
        if [ -n "${running}" ]; then
            echo "  state          : RUNNING  (image=${image})"
            echo "  port mapping   : $(docker port "${DB_CONTAINER}" 2>/dev/null | head -n1)"
            echo "  health         : $(docker inspect -f '{{.State.Health.Status}}' "${DB_CONTAINER}" 2>/dev/null || echo 'n/a')"
            echo "  pg_isready     : $(docker exec "${DB_CONTAINER}" pg_isready -U rocmtest 2>&1 || echo 'FAILED')"
            echo "  last 5 logs    :"
            docker logs --tail 5 "${DB_CONTAINER}" 2>&1 | sed 's/^/    | /'
            echo "  ready to use   : docker exec -it ${DB_CONTAINER} psql -U rocmtest -d rocmtest"
        else
            echo "  state          : NOT RUNNING"
            local dlogs
            dlogs=$(docker logs --tail 10 "${DB_CONTAINER}" 2>&1) || true
            if [ -n "${dlogs}" ]; then
                echo "  last logs    :"
                printf '%s\n' "${dlogs}" | sed 's/^/    | /'
            else
                echo "  last logs    : (none)"
            fi
        fi
    else
        echo "docker         : unavailable on this node"
    fi
    echo "======================================================================"
    echo " infra registry   : curl -s http://${STATE_HOST}:${INFRA_PORT}/v2/_catalog"
    echo "======================================================================"
    exit 0
}
[ "${STATUS}" = "true" ] && do_status

precheck

# -----------------------------------------------------------------------------
# 1. Ensure pg data dir ownership (postgres image runs as UID 999)
# -----------------------------------------------------------------------------
ensure_pgdata() {
    if [ "${DRY_RUN}" = "true" ]; then
        info "  [dry-run] would: mkdir -p ${PGDATA_HOST} && chown ${PG_UID}:${PG_UID} ${PGDATA_HOST}"
        return 0
    fi
    mkdir -p "${PGDATA_HOST}"
    local owner
    owner=$(stat -c '%u' "${PGDATA_HOST}")
    if [ "${owner}" != "${PG_UID}" ]; then
        info "  chowning ${PGDATA_HOST} → uid ${PG_UID} (postgres image user)"
        if ! chown "${PG_UID}:${PG_UID}" "${PGDATA_HOST}"; then
            warn "  chown failed (uid ${owner}) — the container will likely fail to start. Use sudo / root, or fix ownership."
        fi
    fi
}

# -----------------------------------------------------------------------------
# 2. Locate postgres:16 on the INFRA registry → use that image
#    (assumes setup_docker_registry.sh pushed it to rocm-builder:5001)
# -----------------------------------------------------------------------------
locate_image() {
    # Result is the global IMAGE
    IMAGE=""
    if [ "${DRY_RUN}" = "true" ]; then
        IMAGE="${STATE_HOST}:${INFRA_PORT}/postgres:${PG_VERSION}"
        info "  [dry-run] would: locate postgres:${PG_VERSION} from http://${STATE_HOST}:${INFRA_PORT}"
        return 0
    fi
    local candidate="${STATE_HOST}:${INFRA_PORT}/postgres:${PG_VERSION}"
    info "  locating image on infra registry: ${candidate}"
    if docker image inspect "${candidate}" >/dev/null 2>&1; then
        info "    already present locally → using ${candidate}"
        IMAGE="${candidate}"
        return 0
    fi
    if docker pull "${candidate}" >/dev/null 2>&1; then
        info "    pulled from infra registry → using ${candidate}"
        IMAGE="${candidate}"
        return 0
    fi
    warn "    not found on infra registry (${candidate}). Fallback: try upstream postgres:${PG_VERSION}."
    if docker pull "postgres:${PG_VERSION}" >/dev/null 2>&1; then
        warn "    WARNING: using UPSTREAM postgres (not the pinned infra image). Pin it to the registry later."
        IMAGE="postgres:${PG_VERSION}"
        return 0
    fi
    fail "could not obtain postgres:${PG_VERSION} from the infra registry (${STATE_HOST}:${INFRA_PORT}) or upstream.\n          verify setup_docker_registry.sh ran and pushed it; run scripts/verify_registry_infra.sh."
}

# -----------------------------------------------------------------------------
# 3. Generate / persist a default password (unless the env already set one)
# -----------------------------------------------------------------------------
ensure_password() {
    local pass="${POSTGRES_PASSWORD:-}"
    if [ -z "${pass}" ]; then
        pass=$(head -c 256 /dev/urandom | tr -dc 'A-Za-z0-9')
        [ -n "${pass}" ] || pass=$(head -c 256 /dev/urandom | tr -dc 'A-Za-z0-9')
        pass="${pass:0:24}"
        info "  generated a default POSTGRES_PASSWORD (none supplied) — persisting to ${ENV_FILE} (chmod 600)"
    fi
    if [ "${DRY_RUN}" = "true" ]; then
        info "  [dry-run] would write ${ENV_FILE} (POSTGRES_PASSWORD=<value>)"
        REPLY_PASS="<provided-or-generated>"
        return 0
    fi
    # Write the env file with restricted perms (best-effort; not root-safe here)
    {
        echo "# Generated by setup_db.sh on $(date '+%F %T') — source this for state stack env"
        echo "export POSTGRES_DB=rocmtest"
        echo "export POSTGRES_USER=rocmtest"
        echo "export POSTGRES_PASSWORD=${pass}"
        echo "export PGDATA=${PGDATA_HOST}"
    } > "${ENV_FILE}" 2>/dev/null || { warn "  could not write ${ENV_FILE} (non-root?) — relying on runtime env only"; }
    chmod 600 "${ENV_FILE}" 2>/dev/null || true
    REPLY_PASS="${pass}"
}

# -----------------------------------------------------------------------------
# 4. Deploy the container
# -----------------------------------------------------------------------------
deploy() {
    local image="${1}"
    if [ "${REINIT}" = "true" ]; then
        warn "  --reinit requested: removing ${DB_CONTAINER} (its VOLUME at ${PGDATA_HOST} is preserved)"
        docker rm -f "${DB_CONTAINER}" >/dev/null 2>&1 || true
    fi

    if [ "${DROP}" = "true" ]; then
        warn "  --drop requested: removing ${DB_CONTAINER} + its bind dir contents are NOT deleted (host-owned)"
        docker rm -f "${DB_CONTAINER}" >/dev/null 2>&1 || true
        info "  dropped ${DB_CONTAINER} (data dir ${PGDATA_HOST} left intact on host)"
        exit 0
    fi

    if [ "${DRY_RUN}" = "true" ]; then
        info "  [dry-run] would docker run:"
        cat >&2 << EOF
    docker run -d \\
      --name rocm-state-db \\
      --restart unless-stopped \\
      -p ${DB_PORT}:5432 \\
      -v ${PGDATA_HOST}:/var/lib/postgresql/data \\
      -e POSTGRES_DB=rocmtest -e POSTGRES_USER=rocmtest -e POSTGRES_PASSWORD=**** \\
      --label rocm-tier=state --label rocm-component=state-db \\
      ${image}
EOF
        return 0
    fi

    # stop + remove any previous instance
    docker rm -f "${DB_CONTAINER}" >/dev/null 2>&1 || true

    info "  deploying ${DB_CONTAINER} from image: ${image}"
    docker run -d \
        --name "${DB_CONTAINER}" \
        --restart unless-stopped \
        -p "${DB_PORT}:5432" \
        -v "${PGDATA_HOST}:/var/lib/postgresql/data" \
        -e POSTGRES_DB=rocmtest \
        -e POSTGRES_USER=rocmtest \
        -e "POSTGRES_PASSWORD=${2}" \
        --label "rocm-tier=state" \
        --label "rocm-component=state-db" \
        --health-cmd "pg_isready -U rocmtest || exit 1" \
        --health-interval 10s --health-timeout 5s --health-start-period 20s --health-retries 12 \
        --log-driver json-file --log-opt max-size=50m --log-opt max-file=5 \
        "${image}" >/dev/null

    # healthwait: poll container health + pg_isready for a bounded window
    info "  waiting for ${DB_CONTAINER} to become healthy…"
    local i ok=false
    for i in $(seq 1 30); do
        sleep 2
        local h
        h=$(docker inspect -f '{{.State.Health.Status}}' "${DB_CONTAINER}" 2>/dev/null || echo 'missing')
        if [ "${h}" = "healthy" ]; then ok=true; info "  ✓ healthy after ~$((i*2))s"; break; fi
        if [ "${h}" = "missing" ]; then warn "  container vanished — see: docker logs ${DB_CONTAINER}"; break; fi
    done
    if [ "${ok}" != "true" ]; then
        docker logs --tail 25 "${DB_CONTAINER}" 2>&1 | sed 's/^/    | /' >&2 || true
        fail "state-db did not become healthy (last logs above). Common causes: ${PGDATA_HOST} not owned by uid ${PG_UID}, port ${DB_PORT} taken, or a bad image."
    fi
    info "  ready: docker exec -it ${DB_CONTAINER} psql -U rocmtest -d rocmtest"
}

# =============================================================================
# MAIN
# =============================================================================
info "=== setup_db.sh starting (host=${STATE_HOST} db_port=${DB_PORT} storage=${STORAGE_ROOT}) ==="
[ "${DRY_RUN}" = "true" ] && info "  (DRY-RUN: no docker run, no filesystem writes)"

info "-- stage 1/3: pgdata ownership --"
ensure_pgdata

info "-- stage 2/3: locate postgres image on infra registry --"
locate_image

info "-- stage 3/3: password + deploy --"
ensure_password
deploy "${IMAGE}" "${REPLY_PASS:-${POSTGRES_PASSWORD:-}}"

info "=== setup_db.sh complete ==="
info "status anytime: ./setup_db.sh --status"
info "next:        deploy state-svc + dashboard (see PLAN.md §7.5) then run scripts/verify_state_setup.sh from a tester."
