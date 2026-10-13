# ROCm-Tester CI Framework - Project Plan

**Status**: v0.1 (Initial Draft)  
**Date**: Oct 8, 2024  
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
│  │  Shared Registry: Docker Images built once, pulled everywhere   ││
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
├── Iterates test matrix (distro × GPU)
├── Builds distro-specific Docker containers
├── Runs smoke tests with GPU passthrough
└── Aggregates results to JSON output
```

### 4. Distro-Agnostic Test Scripts
**Purpose**: Unified test execution regardless of target OS

- `pkg-tests/hipblas/smoke-test.sh` — Auto-detects distro package manager
- `pkg-tests/{package}/package-config.yaml` — Per-package dependency mapping per distro

```yaml
# Example: pkg-tests/hipblas/package-config.yaml
distro_configs:
  ubuntu:
    base_image: "ubuntu:jammy"
    package_manager: "apt"
    rocm_packages: { runtime, development }
  
  fedora:
    base_image: "fedora:rawhide"
    package_manager: "dnf"
    rocm_packages: { runtime, development }
```

### 5. Results Aggregation
**Purpose**: Consolidate test outcomes for monitoring

- `ci-trigger/results/report-generator.py` — Parses logs and builds trend data
- Output format: JSON array with test_name, distro, result, timestamp

---

## Implementation Roadmap

### Phase 1: Core Infrastructure (2 weeks)
**Week 1-3**: Set up base automation framework
```bash
# Day 1-2: Create project structure and initialize Git
mkdir -p rocm-tester/{pkg-tests,ansible,ci-trigger}

# Day 3-5: Ansible playbooks for node provisioning
playbook: roles/gpu-setup-* for Ubuntu/Fedora/opensuse

# Day 6-7: Jenkins configuration + Docker daemon setup on controller
```

**Week 2**: First end-to-end test (hipblas/smoke)
```bash
# Poller service implementation
python: ci-trigger/poll-fedora-builds.py tests hipblas package version tracking

# Unified smoke-test.sh with distro detection
bash: pkg-tests/hipblas/smoke-dist-agnostic-smoke-test.sh

# Integration test run on single GPU node
script: ci-trigger/orchestrator.sh --test-pack=hipblas --gpu=mi250
```

**Deliverables**: Functional CI execution of one test across two distros.

### Phase 2: Distro Abstraction Layer (1 week)
- Complete `package-config.yaml` for all ROCm packages
- Automated container image generation from templates
- Unified Dockerfile template engine
- Test results JSON schema standardization

### Phase 3: Queue Management & Scaling (2 weeks)
- GPU resource queue to prevent concurrent jobs on single node
- Jenkins pipeline matrix syntax for parallel execution
- Job prioritization based on package change history

### Phase 4: Reporting & Notifications (1 week)
- Slack webhook integration for test failures
- Historical result persistence (SQLite or JSONL storage)
- Trend visualization dashboard (optional: Grafana or custom HTML)

---

## File Structure Template

```
~/devel/rocm-tester/
├── PLAN.md                          <- This document
├── HISTORY.md                       <- Revision history
├── LICENSE
├── README.md                        <- Getting started guide
│
├── ansible/                         <- Infrastructure provisioning
│   ├── site.yml                   <- Main entry point  
│   └── roles/
│       ├── gpu-setup-ubuntu/      <- Ubuntu GPU node setup
│       │   ├── tasks/main.yml
│       │   └── templates/
│       ├── gpu-setup-fedora/      <- Distro-specific variants
│       └── test-environment/      <- Docker/Podman runtime
│
├── ci-trigger/                      <- CI orchestration
│   ├── poller-service.py          <- Polls package build APIs
│   ├── orchestrator.sh            <- Matrix test runner  
│   └── results/                   <- Test result storage
│       ├── report-generator.py
│       └── trends/                <- Historical JSONL data
│
├── pkg-tests/                       <- Per-package tests
│   ├── hipblas/
│   │   ├── Dockerfile.ubuntu      <- Dist-agnostic variants
│   │   ├── Dockerfile.fedora
│   │   ├── package-config.yaml    <- Dependency mapping
│   │   └── smoke-test.sh          <- Unified test logic
│   ├── rocblas/                   <- More packages to come
│   └── {all-rocm-packages}/       <- 89 packages total
│
├── scripts/                         <- Utility automation
│   ├── build-image-template.py    <- Auto-generate Dockerfiles
│   ├── generate-package-matrix.py <- YAML -> Jenkins matrix config
│   └── report-viewer.html         <- Results dashboard
│
└── docs/                            <- Additional documentation
    └── architecture-diagrams.md
```

---

## Technical Stack Decisions

| Component | Choice | Rationale |
|-----------|--------|------------|
| **Orchestration** | Jenkins + Pipeline | Mature, matrix testing support, self-hostable |
| **Provisioning** | Ansible | Declarative config management, agentless |
| **Polling API** | Python `requests` library | Simple, native to most environments |
| **Container Runtime** | Docker | Universal across all target distros |
| **GPU Passthrough** | `--gpus=all`, `/dev/kfd` | Standard approach for both NVIDIA and AMD |
| **Results Storage** | JSON/JSONL | No database dependencies, easy to query with jq/grep |
| **Notification** | Webhooks (Slack) | Simple integration with existing tools |

---

## Known Constraints & Open Questions

### Constraints
- Single developer capacity (estimated 10-20 hrs/week available)
- Limited GPU nodes (3 total: MI300, MI250, Vega)
- No budget for cloud CI services (must be fully self-hosted)
- Local network only (no external VPN access to controller machine)

### Open Questions
1. **Koji API polling frequency**: Every 15 minutes? Hourly?
2. **Test failure tolerance**: How many GPU failures before alerting the developer?
3. **Container image caching**: Should we maintain persistent Docker Hub registry or rebuild per test run?
4. **Package build vs update testing**: Do we want to detect all package builds or only those updating existing versions?

---

## Next Steps (Immediate Actions)

### Priority 1: Project Init
- [x] Create repository structure in `~/devel/rocm-tester`
- [x] Document initial PLAN.md and HISTORY.md
- [ ] Initialize Git repository: `git init`

### Priority 2: First Working Prototype
- [ ] Implement `poller-service.py` for hipblas version tracking
- [ ] Create `smoke-test.sh` auto-detecting Ubuntu/Fedora package managers
- [ ] Build test Dockerfiles (Ubuntu/Fedora variants) for hipblas/smoke

### Priority 3: Controller Setup
- [ ] Write initial Ansible role: `roles/gpu-setup-federd/`
- [ ] Configure Jenkins controller as job orchestrator
- [ ] Test end-to-end execution on single GPU node

---

## Appendix A: API Endpoints Referenced

| Service | Endpoint | Purpose |
|---------|----------|---------|
| Fedora Koji | `https://kojipkg.fedoraproject.org/tasks/package/{package_name}/latest-build` | Get most recent build ID for a package |
| Fedora Bodhi | `https://bodhi.fedoraproject.org/updates/?packages=hipblas&state=testing` | Check testing branch updates |
| Ubuntu Launchpad | `https://launchpad.net/~rocm/+archive/ubuntu/main/+builds` | Monitor Ubuntu ROCm PPA builds |

---

## Appendix B: Sample Results JSON Schema

```json
[
  {
    "test_name": "hipblas-smoke",
    "distro": "fedora",
    "version": "40",
    "result": "PASSED",
    "gpu_model": "MI250",
    "gpu_device_card": "/dev/kfd",
    "duration_seconds": 847,
    "build_id": "123456789",
    "timestamp": "2024-10-08T14:30:00Z",
    "logs_url": null  // URL to Jenkins artifact for this specific run
  }
]
```

---

## Appendix C: Future Enhancements (Backlog)

- [ ] Kubernetes-based test runner with GPU affinity scheduling
- [ ] Automatic test case generation from ROCm documentation
- [ ] CI/CD integration with Fedora COPR previews (pre-release testing)
- [ ] Performance benchmark tracking across ROCm version upgrades
- [ ] Automated regression reporting when test results deviate significantly

---

*This plan will be refined iteratively as the project progresses. Major changes should be documented in this file or via pull requests.*
