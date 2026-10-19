#!/bin/bash
# =============================================================================
# verify_db_setup.sh - ROCm CI State/DB Node Storage Checker
# =============================================================================
# Purpose: Validates that a target machine is ready to host the persistent
# state stack (PostgreSQL + state-svc + artifact store) planned in
# PLAN.md Section 7 on the dedicated database disk.
# SCOPE: host preparation ONLY — run this BEFORE any container is started.
# It never inspects docker, running databases, or network services.
#
# CHECKS (strictly READ-ONLY — this script never modifies the system):
#   [1] /rocm-db exists and is a DEDICATED mount point (own block device)
#   [2] Capacity: total >= 500GB, free >= 100GB
#   [3] Filesystem type: ext4 required (xfs acceptable, ext3/broken rejected)
#   [4] DB-specific filesystem properties:
#       - mounted read-write
#       - atime policy (noatime preferred; atime/relatime = churn on a DB disk)
#       - block size (4k/16k/32k; Postgres runs fine on any of these)
#       - inode headroom (Postgres = many small files; inode exhaustion is
#         the classic silent killer next to byte exhaustion)
#       - device class (SSD vs rotational — informational at this workload)
#   [5] Layout & ownership: pg/ artifacts/ backups/ (warning w/ fix hints if
#       absent), no world-writable, owner root or uid-999 (postgres image UID)
#
# Usage:
#   scp verify_db_setup.sh <state_host>:/tmp && ssh <state_host> /tmp/verify_db_setup.sh
#
# Override defaults via environment:
#   DB_ROOT=/rocm-db MIN_TOTAL_GB=500 MIN_FREE_GB=100 MIN_FREE_INODES=100000
# =============================================================================

set -u -o pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
NC='\033[0m' # No Color

DB_ROOT="${DB_ROOT:-/rocm-db}"
MIN_TOTAL_GB="${MIN_TOTAL_GB:-500}"
MIN_FREE_GB="${MIN_FREE_GB:-100}"
MIN_FREE_INODES="${MIN_FREE_INODES:-100000}"

PASS_COUNT=0
FAIL_COUNT=0
WARN_COUNT=0

# NOTE: unlike verify_builder_setup.sh, log_fail() ACCUMULATES instead of
# exiting, so the operator sees every problem at once; exit code = FAIL_COUNT.
log_pass()  { echo -e "${GREEN}[PASS]${NC} $1"; PASS_COUNT=$((PASS_COUNT+1)); }
log_fail()  { echo -e "${RED}[FAIL]${NC} $1"; FAIL_COUNT=$((FAIL_COUNT+1)); }
log_warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; WARN_COUNT=$((WARN_COUNT+1)); }
log_info()  { echo -e "[INFO] $1"; }
log_hint()  { echo -e "       ${RED}FIX:${NC} $1"; }

if [ ! "$(id -u)" = "0" ]; then
    # Non-root is fine for most checks; ownership block checks just lose precision.
    log_info "Running unprivileged: ownership/device checks may be limited."
fi

echo -e "\n=========================================="
echo "--- ROCm State/DB Node Storage Verification ---"
echo "Target Mount Root: ${DB_ROOT}"
echo "Standard: ext4 | ${MIN_TOTAL_GB}GB+ total, ${MIN_FREE_GB}GB+ free"
echo "Inode Floor: ${MIN_FREE_INODES} free inodes"
echo -e "==========================================\n"

# =============================================================================
# CHECK 1: /rocm-db exists and is a REAL, DEDICATED MOUNT POINT
# =============================================================================
echo -e "[1/5] Verifying mount point '${DB_ROOT}'..."

# 1a. Must exist and be a directory
if [ ! -d "$DB_ROOT" ]; then
    log_fail "CRITICAL: '${DB_ROOT}' does not exist (or is not a directory)."
    log_hint "mkfs.ext4 -L rocmstate </dev/sdX && mkdir -p ${DB_ROOT} && mount LABEL=rocmstate ${DB_ROOT}"
    # Without a mount point nothing else is verifiable — report and stop.
    echo -e "\n=========================================="
    echo -e "${RED}--- VERIFICATION FAILED: ${FAIL_COUNT} failing checks ---${NC}"
    echo -e "${RED}==========================================${NC}"
    exit "$FAIL_COUNT"
else
    log_pass "Directory '${DB_ROOT}' exists."
fi

# 1b. Must be a mount point (block or network device), not a dir on root FS
# Initialize to safe defaults: several late checks degrade gracefully
# (instead of crashing under set -u) when the mount point does not exist.
FS_SOURCE="" FS_TYPE="" FS_OPTIONS=""
MNT_INFO="$(findmnt -T "$DB_ROOT" -no SOURCE,FSTYPE,OPTIONS 2>/dev/null)" || MNT_INFO=""
if [ -z "$MNT_INFO" ]; then
    log_fail "'${DB_ROOT}' is NOT a mount point — it is a plain directory on the root filesystem. The dedicated-DISK requirement of PLAN §7.2 is not met: DB + artifacts would consume the OS partition."
    log_hint "Format the dedicated disk and add to /etc/fstab, e.g.:"
    log_hint "  /dev/disk/by-label/rocmstate  ${DB_ROOT}  ext4  defaults,noatime  0 2"
else
    FS_SOURCE="$(echo "$MNT_INFO"   | awk '{print $1}')"
    FS_TYPE="$(echo "$MNT_INFO"    | awk '{print $2}')"
    FS_OPTIONS="$(echo "$MNT_INFO" | awk '{print $3}')"
    log_pass "Mounted from '${FS_SOURCE}' (type: ${FS_TYPE}, options: ${FS_OPTIONS})."
fi

# =============================================================================
# CHECK 2: CAPACITY (>= MIN_TOTAL_GB total, >= MIN_FREE_GB free)
# =============================================================================
echo -e "\n[2/5] Verifying capacity..."

SPACE_LINE="$(df -BG "$DB_ROOT" 2>/dev/null | tail -1)"
if [ -n "$SPACE_LINE" ]; then
    TOTAL_GB="$(echo "$SPACE_LINE"  | awk '{gsub("G","",$2); print $2}')"
    FREE_GB="$(echo "$SPACE_LINE"   | awk '{gsub("G","",$4); print $4}')"

    if [ "${TOTAL_GB:-0}" -lt "$MIN_TOTAL_GB" ]; then
        log_fail "INSUFFICIENT CAPACITY: ${DB_ROOT} totals ${TOTAL_GB}GB; minimum is ${MIN_TOTAL_GB}GB."
    else
        log_pass "Total capacity OK: ${TOTAL_GB}GB (minimum ${MIN_TOTAL_GB}GB)."
    fi

    if [ "${FREE_GB:-0}" -lt "$MIN_FREE_GB" ]; then
        log_fail "CRITICAL: only ${FREE_GB}GB free on ${DB_ROOT}; need ${MIN_FREE_GB}GB+ for the artifact queue."
    else
        log_pass "Free capacity OK: ${FREE_GB}GB (minimum ${MIN_FREE_GB}GB)."
    fi
else
    log_fail "Could not read capacity for '${DB_ROOT}' (path missing?)"
fi

# =============================================================================
# CHECK 3: FILESYSTEM TYPE — ext4 required (PLAN §7.2)
# =============================================================================
echo -e "\n[3/5] Verifying filesystem type..."

case "${FS_TYPE:-<none>}" in
    ext4)
        log_pass "Filesystem is ext4 — the required standard for the state store."
        ;;
    xfs)
        log_warn "Filesystem is XFS (ext4 is required by PLAN §7.2). XFS is operational-acceptable but verify dir quotas work as expected for artifacts/."
        ;;
    ext3)
        log_fail "Filesystem is ext3 — EOL (no 64-bit growth path, obsolete tooling). REFORMAT: mkfs.ext4 -L rocmstate ${FS_SOURCE}"
        ;;
    zfs|btrfs)
        log_warn "Filesystem is ${FS_TYPE} — allowed by PLAN §7.2 only 'if already in use'; confirm snapshots/quota policy before enabling GC."
        ;;
    overlay|tmpfs|ramfs)
        log_fail "Filesystem '${FS_TYPE}' is volatile/layered — NEVER acceptable for the source-of-truth state store."
        ;;
    *)
        log_warn "Unrecognized filesystem '${FS_TYPE}'. Verify Postgres compatibility before proceeding."
        ;;
esac

# =============================================================================
# CHECK 4: DB-SPECIFIC FILESYSTEM PROPERTIES
# =============================================================================
echo -e "\n[4/5] Verifying DB-specific filesystem properties..."

# 4a. Mounted READ-WRITE
if [ -z "$FS_OPTIONS" ]; then
    log_warn "Could not read mount options (skip rw/noatime checks)."
elif echo "$FS_OPTIONS" | tr ',' '\n' | grep -qx 'ro'; then
    log_fail "'${DB_ROOT}' is mounted READ-ONLY. Postgres will fail to start. Remount rw (remove 'ro' from /etc/fstab)."
elif echo "$FS_OPTIONS" | tr ',' '\n' | grep -qx 'nosuid'; then
    log_warn "Mounted 'nosuid' — harmless here, noted for completeness."
else
    log_pass "Mounted read-write (rw)."
fi

# 4b. ATIME POLICY — atime updates are pure churn on a disk hosting a database
if [ -n "$FS_OPTIONS" ] && echo "$FS_OPTIONS" | tr ',' '\n' | grep -qxE 'noatime|relatime'; then
    log_pass "atime policy is low-churn (noatime/relatime)."
elif [ -n "$FS_OPTIONS" ] && echo "$FS_OPTIONS" | tr ',' '\n' | grep -qxE 'atime|strictatime'; then
    log_fail "Mounted with explicit atime — every artifact log read rewrites inode metadata. Add 'noatime' to the fstab options."
else
    log_warn "No noatime on '${DB_ROOT}' (default relatime is usually acceptable, explicit 'noatime' preferred per PLAN §7.2)."
fi

# 4c. BLOCK SIZE — Postgres is byte-oriented; 4k/16k/32k are all fine,
#     512B (ancient) is not. (df --output=bps reports in BYTES)
BLOCK_BYTES="$(df -B0 --output=bps "$DB_ROOT" 2>/dev/null | tail -1 | tr -dc '0-9')"
if [ -n "$BLOCK_BYTES" ]; then
    case "$BLOCK_BYTES" in
        4096|16384|32768)
            log_pass "Block size $((BLOCK_BYTES/1024))KiB — compatible with PostgreSQL heap/WAL on ext4."
            ;;
        *)
            log_warn "Unusual block size '${BLOCK_BYTES}' bytes. Verify ext4 mkfs options before hosting the DB."
            ;;
    esac
else
    log_warn "Could not determine block size for '${DB_ROOT}'."
fi

# 4d. INODE HEADROOM — the check verify_builder_setup.sh never has:
#     Postgres creates thousands of small files (heap, indexes, WAL segs);
#     the artifact store creates one file per upload. Byte-space can be
#     huge while inodes run out first.
INODE_LINE="$(df -i "$DB_ROOT" 2>/dev/null | tail -1)"
if [ -n "$INODE_LINE" ]; then
    FREE_INODES="$(echo "$INODE_LINE"  | awk '{print $4}')"
    INODE_USE="$(echo "$INODE_LINE"    | awk '{gsub("%","",$5); print $5}')"

    if [ "${FREE_INODES:-0}" -lt "$MIN_FREE_INODES" ]; then
        log_fail "LOW INODES: only ${FREE_INODES} free; need ${MIN_FREE_INODES}+ (artifact store + PG heap files allocate inodes, not just bytes)."
    else
        log_pass "Inode headroom OK: ${FREE_INODES} free (floor ${MIN_FREE_INODES}, usage ${INODE_USE}%)."
    fi
else
    log_warn "Could not read inode statistics for '${DB_ROOT}'."
fi

# 4e. DEVICE CLASS (SSD vs rotational) — informational at this write profile
DEV_BASE="$(basename "$FS_SOURCE" 2>/dev/null)"
if [ -n "$DEV_BASE" ] && [ -r "/sys/block/${DEV_BASE}/queue/rotational" ]; then
    ROT="$(cat "/sys/block/${DEV_BASE}/queue/rotational" 2>/dev/null || echo '?')"
    case "$ROT" in
        0) log_pass "Backing device /dev/${DEV_BASE} is NON-ROTATIONAL (SSD/NVMe) — ideal for WAL + artifact I/O." ;;
        1) log_warn "Backing device /dev/${DEV_BASE} is ROTATIONAL. Acceptable at this write profile (mostly small, spaced), expect checkpoint latency under bursts." ;;
        *) log_info "Device rotation class unknown (/dev/${DEV_BASE})." ;;
    esac
else
    log_info "Backing device class not inspectable (network source or unprivileged) — skipping."
fi

# =============================================================================
# CHECK 5: LAYOUT & OWNERSHIP (PLAN §7.2)
# =============================================================================
echo -e "\n[5/5] Verifying layout and ownership..."

LAYOUT_MISSING=""
for sub in pg artifacts backups; do
    [ -d "${DB_ROOT}/${sub}" ] || LAYOUT_MISSING="${LAYOUT_MISSING} ${sub}"
done
if [ -z "$LAYOUT_MISSING" ]; then
    log_pass "Layout OK: pg/ artifacts/ backups/ all present under ${DB_ROOT}."
else
    log_warn "Missing sub-dir(s):${LAYOUT_MISSING}. Expected PLAN §7.2 layout:"
    log_hint "mkdir -p ${DB_ROOT}/pg ${DB_ROOT}/artifacts ${DB_ROOT}/backups"
fi

if [ -d "$DB_ROOT" ]; then
    OWNER="$(stat -c %U "$DB_ROOT" 2>/dev/null)"
    OWNER_UID="$(stat -c %u "$DB_ROOT" 2>/dev/null)"
    PERMS="$(stat -c %a "$DB_ROOT" 2>/dev/null)"

    # Must NOT be world-writable (artifact store is served over the network).
    # Stat's %a is OCTAL: others-write is set when the digit is 3, 6, or 7.
    OTHER_PERMS="${PERMS: -1}"
    case "$OTHER_PERMS" in
        3|6|7)
            log_fail "${DB_ROOT} permissions '${PERMS}' grant OTHERS write. It is served over the network — strip 'o+w' (chmod o-w)."
            ;;
        *)
            log_pass "Not world-writable (perms ${PERMS})."
            ;;
    esac

    case "${OWNER_UID:-}" in
        0|999)
            log_pass "Owner '${OWNER}' (uid ${OWNER_UID}) — root (pre-init) or the postgres image UID (999)."
            ;;
        "")
            log_warn "Could not determine owner of '${DB_ROOT}'."
            ;;
        *)
            log_warn "Owner '${OWNER}' (uid ${OWNER_UID}) — neither root nor 999. The postgres entrypoint will chown an EMPTY pg/ at first boot; an already-populated dir owned by this uid would need: chown -R 999:999 ${DB_ROOT}/pg"
            ;;
    esac
fi

# =============================================================================
# FINAL SUMMARY
# =============================================================================
echo -e "\n=========================================="
if [ "$FAIL_COUNT" -eq 0 ]; then
    echo -e "${GREEN}--- STATE/DB DISK READY: ${DB_ROOT} (passes ${PASS_COUNT}, warns ${WARN_COUNT}) ---${NC}"
    echo -e "${GREEN}==========================================${NC}"
else
    echo -e "${RED}--- VERIFICATION FAILED: ${FAIL_COUNT} failing checks, ${WARN_COUNT} warnings ---${NC}"
    echo -e "${RED}==========================================${NC}"
fi

exit "$FAIL_COUNT"
