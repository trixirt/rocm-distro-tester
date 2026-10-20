#!/bin/bash
# =============================================================================
# pin_infra_images.sh - Pin infrastructure + rolling base images to the
#                       :5001 infra registry
# =============================================================================
# Purpose:
#  (A) PLAN.md §7.5.1 — the state stack must boot OFFLINE from the infra
#      registry: postgres (and later state-svc/dashboard) are pinned here.
#  (B) rolling/dev release BASE images (fedora:rawhide, ubuntu:latest,
#      archlinux:latest, centos:stream10) are pinned too, so the
#      rocm-distro-containers build matrix:
#        - shares ONE cached copy per base (432+ Dockerfiles dedupe to 4 pulls),
#        - builds against the SAME base revision within one CI wave
#          (rolling targets otherwise drift between build #3 and build #140),
#        - survives upstream rate limits/outages and works offline.
#
# Pushes go to 127.0.0.1:<port> (Docker's loopback-HTTP default trust — no
# insecure-registries entry needed ON THE REGISTRY HOST). Consuming nodes
# (rocm-db, rocm-testers-with-build) pull the same repos under the builder
# alias: rocm-builder:5001/<name>:<tag>.
#
# DIGEST TWINS: every pinned tag pushes a second tag
#   <repo>:sha256-<first 12 hex of the image ID>
# so CI receipts can name the exact base/image revision used (mirrors the
# sha256 digest naming convention for test artifacts, PLAN §6.1). Old twins
# stay in the registry = rolling pin history.
#
# REFRESH SEMANTICS:
#   infra images (postgres…)     : local copy reused; --rebuild forces re-pull
#   rolling bases                : ALWAYS re-pulled from upstream on every run
#                                  (freshness IS the point) — re-run before each
#                                  CI wave; do NOT re-pin mid-wave.
#
# Usage:
#   ./pin_infra_images.sh [options]
#
# Options:
#   --dry-run      Preview actions (no pull/tag/push)
#   --rebuild      Re-pull upstream even if present locally (infra images;
#                  rolling bases always refresh anyway)
#   --bases        Pin infra images AND the rolling base set (initial deploy)
#   --bases-only   Pin ONLY the rolling base set (wave-start refresh;
#                  postgres/state-svc/dashboard are left untouched)
#   --verbose,-v   Verbose output
#   --help,-h      This help
#
# Env overrides: INFRA_HOST (127.0.0.1), INFRA_PORT (5001), PG_VERSION (16),
#                BUILDER_ALIAS (rocm-builder)
#
# Precondition: setup_docker_registry.sh --tier infra started rocm-infra-registry.
# Follow-up:    rocm-db pulls rocm-builder:5001/postgres:16 → setup_db.sh
#               builders FROM rocm-builder:5001/fedora-rawhide:rawhide, etc.
# =============================================================================

set -euo pipefail

INFRA_HOST="${INFRA_HOST:-127.0.0.1}"
INFRA_PORT="${INFRA_PORT:-5001}"
PG_VERSION="${PG_VERSION:-16}"
BUILDER_ALIAS="${BUILDER_ALIAS:-rocm-builder}"

# Rolling/dev base set (fixed for now — the deliberately moving targets):
#   "upstream-image:tag|local-repo"
ROLLING_BASES=(
    "fedora:rawhide|fedora-rawhide"
    "ubuntu:latest|ubuntu-latest"
    "archlinux:latest|archlinux-latest"
    "quay.io/centos/centos:stream10|centos-stream10"
)

DRY_RUN=false
REBUILD=false
VERBOSE=false
BASES_MODE="off"    # off | bases | bases-only

usage() {
    sed -n '/^# Usage:/,/^# =============================================================================$/p' "$0" | sed 's/^# \{0,1\}//'
    exit 0
}

while [[ $# -gt 0 ]]; do
    case $1 in
        --dry-run) DRY_RUN=true; shift ;;
        --rebuild) REBUILD=true; shift ;;
        --bases) BASES_MODE="bases"; shift ;;
        --bases-only) BASES_MODE="bases-only"; shift ;;
        --verbose|-v) VERBOSE=true; shift ;;
        --help|-h) usage ;;
        *) echo "Unknown option: $1 (see --help)" >&2; exit 1 ;;
    esac
done
[ "${VERBOSE}" = "true" ] && set -x

log()  { echo -e "[PIN] $(date '+%Y-%m-%d %T') - $*"; }
fail() { echo -e "[PIN] ERROR: $*" >&2; exit 1; }

registry_up() {
    local url="http://${INFRA_HOST}:${INFRA_PORT}/v2/"
    curl -fsS --max-time 5 "$url" >/dev/null 2>&1
}

manifest_ok() {
    local name="$1" tag="$2"
    curl -fsS --max-time 5 \
        -H "Docker-Registry-Api-Version: registry/2.0" \
        -H "Accept: application/vnd.oci.image.manifest.v1+json, application/vnd.oci.image.index.v1+json, application/vnd.docker.distribution.manifest.v2+json, application/vnd.docker.distribution.manifest.list.v2+json" \
        "http://${INFRA_HOST}:${INFRA_PORT}/v2/${name}/manifests/${tag}" >/dev/null 2>&1
}

# pin_one UPSTREAM_IMAGE LOCAL_REPO TAG REQUIRED FORCE_PULL
pin_one() {
    local upstream="$1" target_name="$2" target_tag="$3" required="$4" force_pull="${5:-no}"
    local push_name="${BUILDER_ALIAS}:${INFRA_PORT}/${target_name}:${target_tag}"
    local local_ref="${INFRA_HOST}:${INFRA_PORT}/${target_name}:${target_tag}"

    log "=== ${required}: ${upstream} -> ${push_name} ==="

    if [ "${DRY_RUN}" = "true" ]; then
        if [ "${force_pull}" = "yes" ]; then
            log "  [dry-run] would: docker pull ${upstream}   (rolling base — always refreshed from upstream)"
        elif docker image inspect "${upstream}" >/dev/null 2>&1; then
            log "  [dry-run] would: use local ${upstream} (--rebuild to re-pull)"
        else
            log "  [dry-run] would: docker pull ${upstream}"
        fi
        log "  [dry-run] would: docker tag  ${upstream} ${local_ref}"
        log "  [dry-run] would: docker tag  ${upstream} ${INFRA_HOST}:${INFRA_PORT}/${target_name}:sha256-<imageID[:12]>"
        log "  [dry-run] would: docker push ${local_ref}  (plus digest twin)"
        log "  [dry-run] would: verify manifest GET http://${INFRA_HOST}:${INFRA_PORT}/v2/${target_name}/manifests/${target_tag}"
        log "  ✓ ${push_name} pinned (simulated)"
        return 0
    fi

    # 1. Ensure availability locally (rolling bases: ALWAYS refresh — the pin
    #    must represent the current head of the rolling branch)
    local do_pull=false why="n/a"
    if [ "${force_pull}" = "yes" ]; then
        do_pull=true why="rolling base — always refreshed from upstream"
    elif [ "${REBUILD}" = "true" ]; then
        do_pull=true why="--rebuild requested"
    elif ! docker image inspect "${upstream}" >/dev/null 2>&1; then
        do_pull=true why="not present locally"
    fi
    if [ "${do_pull}" != "true" ]; then
        log "  local image present — using it (use --rebuild to refresh; rolling bases refresh automatically)"
    else
        log "  pulling ${upstream} (${why})…"
        docker pull "${upstream}" >/dev/null 2>&1 || if [ "${required}" = "required" -o "${force_pull}" = "yes" ]; then
            fail "upstream pull failed: ${upstream}"
        else
            log "  [skip] optional image unavailable (upstream pull failed)"; return 0
        fi
    fi

    # 2. Tag canonical + digest twin
    local imgid12=""
    imgid12=$(docker image inspect --format '{{.Id}}' "${upstream}" 2>/dev/null | cut -c8-19) || true
    imgid12="${imgid12//[!0-9a-f]/}"   # defensive: keep only hex chars
    docker tag "${upstream}" "${local_ref}"
    log "  tagged ${local_ref}"
    local twin_ref=""
    if [ -n "${imgid12}" ]; then
        twin_ref="${INFRA_HOST}:${INFRA_PORT}/${target_name}:sha256-${imgid12}"
        docker tag "${upstream}" "${twin_ref}"
        log "  tagged digest twin ${twin_ref}"
    fi

    # 3. Push (blob layers shared with the twin — cheap)
    log "  pushing to infra registry…"
    docker push "${local_ref}" >/dev/null || {
        [ "${required}" = "required" -o "${force_pull}" = "yes" ] && \
        fail "push failed: ${local_ref} — is rocm-infra-registry running (setup_docker_registry.sh --tier infra)?" || \
        { log "  [skip] optional image push failed"; return 0; }
    }
    if [ -n "${twin_ref}" ]; then
        docker push "${twin_ref}" >/dev/null 2>&1 || \
            log "  WARN: digest-twin push failed (non-fatal; canonical tag already pinned)"
    fi

    # 4. Verify the registry serves the pinned tag back
    if ! manifest_ok "${target_name}" "${target_tag}"; then
        [ "${required}" = "required" -o "${force_pull}" = "yes" ] && \
        fail "push reported success but the manifest for ${push_name} is not served — registry storage problem?" || \
        { log "  [skip] optional image manifest not found after push"; return 0; }
    fi

    log "  ✓ ${push_name} pinned (digest twin: sha256-${imgid12:-n/a})"
}

# =============================================================================
# MAIN
# =============================================================================
log "pin_infra_images.sh (infra=${INFRA_HOST}:${INFRA_PORT}, pg=${PG_VERSION}, mode=${BASES_MODE})"
[ "${DRY_RUN}" = "true" ] && log "  (DRY-RUN: no pull/tag/push)"

command -v docker  &>/dev/null || fail "docker CLI is absent"
docker info >/dev/null 2>&1   || fail "docker daemon unreachable — check permissions / daemon"
curl -fsS --max-time 2 "http://127.0.0.1:1/" >/dev/null 2>&1 || true   # no-op; curl presence guard below
command -v curl &>/dev/null  || fail "curl is required for registry verification"

if [ "${DRY_RUN}" != "true" ]; then
    if registry_up; then
        log "infra registry reachable at http://${INFRA_HOST}:${INFRA_PORT}"
    else
        fail "infra registry NOT reachable at http://${INFRA_HOST}:${INFRA_PORT} — run ./ci-trigger/scripts/setup_docker_registry.sh --tier infra first."
    fi
fi

# --- (A) infra images (state stack, offline boot) ----------------------------
if [ "${BASES_MODE}" != "bases-only" ]; then
    log "--- infra tier (state stack) ---"
    pin_one "postgres:${PG_VERSION}"      "postgres"       "${PG_VERSION}" "required" no

    pin_optional() {
        local upstream="$1" name="$2" tag="$3"
        if docker image inspect "${upstream}" >/dev/null 2>&1; then
            pin_one "${upstream}" "${name}" "${tag}" "optional" no
        else
            log "=== optional: ${upstream} -> ${BUILDER_ALIAS}:${INFRA_PORT}/${name}:${tag} ==="
            log "  [skip] not built locally yet (PLAN §7.5 state-svc/dashboard — pin when available)"
        fi
    }
    pin_optional "rocm/state-svc:local"  "rocm-state-svc" "local"
    pin_optional "rocm/dashboard:local"  "rocm-dashboard" "local"
else
    log "--- infra tier skipped (--bases-only) ---"
fi

# --- (B) rolling base images --------------------------------------------------
if [ "${BASES_MODE}" != "off" ]; then
    log "--- rolling base images (refreshed from upstream on every run) ---"
    for entry in "${ROLLING_BASES[@]}"; do
        upstream="${entry%%|*}"
        repo="${entry##*|}"
        tag="${upstream##*:}"
        pin_one "${upstream}" "${repo}" "${tag}" "required" "yes"
    done

    log "base-image FROM-references for Dockerfiles (pinned in this run):"
    for entry in "${ROLLING_BASES[@]}"; do
        upstream="${entry%%|*}"
        repo="${entry##*|}"
        tag="${upstream##*:}"
        log "  ${BUILDER_ALIAS}:${INFRA_PORT}/${repo}:${tag}"
    done
fi

# --- final catalog -------------------------------------------------------------
log "infra registry catalog now:"
if [ "${DRY_RUN}" != "true" ]; then
    curl -fsS "http://${INFRA_HOST}:${INFRA_PORT}/v2/_catalog" 2>/dev/null | sed 's/^/    /' || true
fi
log "done. Next: rocm-db → setup_db.sh · builders → FROM ${BUILDER_ALIAS}:${INFRA_PORT}/fedora-rawhide:rawhide"
