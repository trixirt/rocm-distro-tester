#!/bin/bash
# =============================================================================
# ROCm-Tester: Build and Push All Docker Images to Registry
# =============================================================================

set -x

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$SCRIPT_DIR/.."
TAG_PREFIX="rocm-builder:5000/"

cd $PROJECT_ROOT
docker build -t hipblas-fedora-smoke pkg-tests/fedora/rawhide/hipblas/smoke/
if [ $? = 0 ]; then
    docker tag hipblas-fedora-smoke ${TAG_PREFIX}hipblas-fedora-smoke:latest
    if [ $? = 0 ]; then
	docker push ${TAG_PREFIX}hipblas-fedora-smoke:latest
	if [ $? = 0 ]; then
	    echo "should be working"
	fi
    fi
fi

