# ROCm-Tester CI Framework

**Self-hosted continuous integration for AMD ROCm package testing across multiple Linux distributions**

---

## Quick Start

### Prerequisites
```bash
- Controller machine with:
  - Docker daemon installed
  - Jenkins (with Pipeline plugin) OR simple bash scheduler
  - Network access to target GPU test machines
- Target machines: At least one GPU-enabled machine (AMD MI200/MI300/NVIDIA RTX)
- Python 3.8+ for poller scripts
- Ansible 2.9+ (for node provisioning, optional)
```

### Initial Setup
```bash
cd ~/devel/rocm-tester
git init
git submodule add <jenkins-slave-node-repo> jenkins-nodes  # Optional

# Configure your test matrix via:
ansible-playbook ansible/site.yml -e "target=distro_name -e gpu_nodes=[mi250,mi300]"  
```

### First Test Run (hipblas/smoke)
```bash
# Trigger poller and build/test sequence
ci-trigger/poll-fedora-builds.py hipblas
ci-trigger/orchestrator.sh --test-pack=hipblas --distro=all --gpu=mi250

# View results
cat ci-trigger/results/all-results.json | jq '.[]'
```

---

## Architecture Overview

See [PLAN.md](./PLAN.md) for complete system architecture and design decisions.

### Components
- **Poller Service** (`ci-trigger/poller-*`): Monitors Fedora Koji/Ubuntu Launchpad for package updates
- **Orchestrator** (`ci-trigger/orchestrator.sh`): Manages distributed test execution across GPU nodes
- **Test Packets** (`pkg-tests/*`): Distro-specific test containers with unified scripts
- **Report Generator** (`ci-trigger/results/report-generator.py`): Aggregates test outcomes

---

## Project Status

| Component | Status |
|-----------|--------|
| Plan & Documentation | ✅ Complete v0.1 |
| Hipblas smoke tests (Ubuntu/Fedora) | 🟡 In Progress |
| ROCm package matrix (89 packages) | 🔴 Not Started |
| GPU resource queue management | 🔴 Not Started |
| Results dashboard | 🔴 Not Started |

---

## Project Structure

```
rocm-tester/
├── PLAN.md                       # Design specification
├── HISTORY.md                    # Major decisions log
├── ansible/                      # Infrastructure setup
│   ├── roles/gpu-setup-*/       # Distro-specific GPU drivers
│   └── site.yml                 # Main entry point
├── ci-trigger/                   # CI orchestration
│   ├── poller-service.py        # Koji/Launchpad polling
│   ├── orchestrator.sh          # Test matrix runner
│   └── results/                 # Output storage
├── pkg-tests/                    # Per-package tests
│   ├─ hipblas/*/                 # First test implementation
│   └─ {all-rocm-packages}        # All 89 packages to add
└── docs/                         # Additional documentation
```

---

## Contributing

To extend this framework:
1. Create a new `pkg-tests/{package}/` directory with its test artifacts
2. Add entries to `pkg-tests/{package}/package-config.yaml`
3. Update orchestrator dependencies if needed
4. Open a pull request for review

---

## License

MIT License (see LICENSE file)
