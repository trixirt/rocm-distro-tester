#!/bin/bash
# verify_all_tests.sh
# Purpose: Master entry point for the Hardware Readiness Testsuite (Fedora 44 + K3s)

EXIT_CODE=0

echo ">>> Running Machine Readiness Checks..."
echo "----------------------------------------"

# Run Controller Check
bash scripts/verify_controller_setup.sh || EXIT_CODE=1
if [ $EXIT_CODE -ne 0 ]; then
    echo "[ERROR] controller setup failed." >&2
fi

echo ""

# Run GPU Check 
bash scripts/verify_gpu_setup.sh || EXIT_CODE=1
if [ $EXIT_CODE -ne 0 ]; then
    echo "[ERROR] gpu setup failed." >&2
fi

echo ""

# Run Network Registry Check
bash scripts/verify_network_registry.sh || EXIT_CODE=1
if [ $EXIT_CODE -ne 0 ]; then
    echo "[ERROR] network registry check failed." >&2
fi

echo ""
echo "----------------------------------------"
if [ $EXIT_CODE -eq 0 ]; then
    echo "- SYSTEM VERIFICATION PASSED - OK"
    echo "Ready for workloads."
else
    echo "- SYSTEM VERIFICATION FAILED - FIX ABOVE ERRORS"
    >&2 echo "See log entries above for detailed failures."
fi

exit $EXIT_CODE
