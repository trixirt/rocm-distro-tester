#!/bin/bash

while true; do
    echo "[poller] $(date +'%Y-%m-%d %H:%M:%S') === Starting Fedora RAWHIDE poll cycle ===" >> "$LOG_FILE"
    
    # 1. Ensure local DNF metadata is fresh (matches dnf clean/makecache logic)
    dnf update -y
    
    while IFS= read -r pkg || [[ -n "$pkg" ]]; do
        # Ignore blank lines and comments
        [[ -z "$pkg" || "$pkg" =~ ^# ]] && continue

        echo "[poller] Checking: ${pkg}"

        # 2. Run metadata query safely (prevents set -e from killing on unavailable pkg)
	dnf repoquery -i ${pkg} 2> /dev/null 1> /tmp/rq
	if [ $? = 0 ]; then
	    v=`grep 'Version' /tmp/rq | awk '{ print $3 }'`
	    r=`grep 'Release' /tmp/rq | tr '.' ' ' | awk '{ print $3 }'`
	    echo ${v}.${r}
	fi

    done < packages.txt

    # TODO 3: sleep to 24 hours +- random 60 minutes
    # Math: Base 24h (86400s) + Random jitter between 0 and 3600s
    JITTER=$(( RANDOM % 3601 ))
    TOTAL_SLEEP=$(( 86400 + JITTER ))
    
    echo "[poller] Sleeping for a bit "
    sleep $TOTAL_SLEEP

done
