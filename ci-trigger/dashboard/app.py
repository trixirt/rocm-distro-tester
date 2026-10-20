#!/usr/bin/env python3
# =============================================================================
# ROCm-Distro-Tester: Result Dashboard Application (v0.2 STUB)
# Status: Placeholder mode for Phase 7 DB migration preparation.
# ----------------------------------------------------------------------
# This version strips out the legacy JSON-file scanning logic 
# to prepare for the PostgreSQL backend defined in PLAN.md §7.
# The API & health endpoints remain active but return initialization stubs.
# =============================================================================

import logging
from flask import Flask, render_template, jsonify
from datetime import datetime

app = Flask(__name__)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("dashboard")


@app.route('/')
def index():
    """Placeholder page shown while awaiting Section 7 Postgres backend."""
    return render_template('waiting.html', now=datetime.now())


@app.route('/results')
def results_view():
    """Proxy to placeholder template per §7 transition policy."""
    return render_template('waiting.html', now=datetime.now())


@app.route('/api/summary')
def api_summary():
    """Stubbed API: returns valid JSON structure required for Docker health checks.
    Will be replaced by SQL read-only projections in Phase 7.5."""
    return jsonify({
        'status': 'initialized_placeholder',
        'message': 'Dashboard is waiting for Postgres Backend (Section 7 of PLAN.md)',
        'statistics': {
            'total_results': 0,
            'passed': 0,
            'failed': 0,
            'pass_rate': 0,
        },
        'by_distro': {},
        'latest_timestamp': None
    })


@app.route('/api/latest-results/<int:limit>')
def api_latest_results(limit=10):
    """Stubbed API matching the v0.1 route signature for backwards compatibility."""
    return jsonify({
        'count': 0,
        'results': []
    })


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)
