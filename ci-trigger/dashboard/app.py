#!/usr/bin/env python3
# =============================================================================
# ROCm-Tester: Result Dashboard Application (v0.1)
# Flask web application for displaying test/build results from local JSON outputs
# Aggregates results across all distros (Fedora, Ubuntu, RHEL/CentOS Stream)
# and displays in unified, filtered interface with Chart.js visualizations
# =============================================================================

import json
import logging
from pathlib import Path
from flask import Flask, render_template, jsonify
from datetime import datetime, timedelta
import os

app = Flask(__name__)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("dashboard")
RESULTS_DIR = Path(os.environ.get('RESULTS_DIR', '/var/rocm-distro-tester/results'))


def load_all_results(distros=None):
    """Load all JSON result files from results directory, optionally filtered by distro."""
    all_results = []
    
    if not RESULTS_DIR.exists():
        logger.warning(f"Results directory not found: {RESULTS_DIR}")
        return all_results
    
    for json_file in RESULTS_DIR.glob('*-result.json'):
        try:
            with open(json_file, 'r') as f:
                data = json.load(f)
                
                distro = data.get('distro', 'unknown')
                
                if distros is None or distro in distros:
                    all_results.append(data)
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"Error reading {json_file}: {e}")
    
    return sorted(all_results, key=lambda x: x.get('timestamp', ''), reverse=True)


@app.route('/')
def index():
    """Index page shows overview statistics for all test results with visual charts."""
    results = load_all_results()
    
    total_tests = len(results)
    passed = sum(1 for r in results if r.get('status') == 'PASSED')
    failed = total_tests - passed
    pass_rate = (passed / total_tests * 100) if total_tests > 0 else 0
    
    distro_stats = {}
    for result in results:
        distro = result.get('distro', 'unknown')
        if distro not in distro_stats:
            distro_stats[distro] = {'total': 0, 'passed': 0}
        distro_stats[distro]['total'] += 1
        if result.get('status') == 'PASSED':
            distro_stats[distro]['passed'] += 1
    
    stats = {
        'total_tests': total_tests,
        'passed': passed,
        'failed': failed,
        'pass_rate': round(pass_rate, 2),
        'distro_breakdown': distro_stats,
        'latest_timestamp': results[0].get('timestamp', 'N/A') if results else None
    }
    
    packages = sorted(set(r.get('package_name', '') or '' for r in results if r))
    
    return render_template('index.html', stats=stats, packages=packages, now=datetime.now())


@app.route('/results')
def results_view():
    """Results page shows detailed list of all test results with filtering."""
    distro_filter = request.args.get('distro') or None
    package_filter = request.args.get('package', '').strip() or None
    result_filter_raw = request.args.get('result', '')
    result_filter = (result_filter_raw.upper() in ['PASSED', 'FAILED']) and result_filter_raw.upper() or None
    days_back = int(request.args.get('days', 7)) or 7
    
    results = load_all_results([distro_filter] if distro_filter else None)
    
    cutoff_date = datetime.now() - timedelta(days=days_back)
    results = [r for r in results 
               if datetime.fromisoformat(r.get('timestamp', str(datetime.min))) >= cutoff_date]
    
    if package_filter:
        results = [r for r in results 
                   if package_filter.lower() in (r.get('package_name') or '').lower()]
    
    if result_filter:
        results = [r for r in results if r.get('status', '').upper() == result_filter]
    
    return render_template(
        'results.html', 
        results=results, 
        distro_filter=distro_filter,
        package_filter=package_filter,
        result_filter=result_filter,
        current_days=days_back,
        packages=sorted(set(r.get('package_name') or '' for r in results if r))
    )


@app.route('/api/latest-results/(d+):i')
def api_latest_results(limit=10):
    """API endpoint to get latest N results as JSON."""
    results = load_all_results()[:int(limit)]
    return jsonify({
        'count': len(results),
        'results': results
    })


@app.route('/api/summary')
def api_summary():
    """API endpoint returning summarized statistics for all results."""
    results = load_all_results()
    
    total_tests = len(results)
    passed = sum(1 for r in results if r.get('status') == 'PASSED')
    failed = total_tests - passed
    
    distro_stats = {}
    for result in results:
        distro = result.get('distro', 'unknown')
        if distro not in distro_stats:
            distro_stats[distro] = {'total': 0, 'passed': 0}
        distro_stats[distro]['total'] += 1
        if result.get('status') == 'PASSED':
            distro_stats[distro]['passed'] += 1
    
    return jsonify({
        'statistics': {
            'total_results': total_tests,
            'passed': passed,
            'failed': failed,
            'pass_rate': round(passed / total_tests * 100) if total_tests else 0,
        },
        'by_distro': distro_stats,
        'latest_timestamp': results[0].get('timestamp') if results else None
    })


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='ROCm-Tester Result Dashboard Server')
    parser.add_argument('--port', '-p', type=int, default=5001)
    parser.add_argument('--host', '-H', default='0.0.0.0')
    
    args = parser.parse_args()
    
    logger.info(f"Starting ROCm-Tester Dashboard on {args.host}:{args.port}")
    app.run(host=args.host, port=args.port, debug=False)
