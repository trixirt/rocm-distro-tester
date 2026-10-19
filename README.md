# ROCm Distro Tester

**Self-hosted continuous integration for AMD ROCm package testing across multiple Linux distributions**

---

*AI development:

coding agent: pi-coding-agent
backend: ollama
models: Qwen3.6:35b, Qwen3.5:35b
AMD hardware: Strix Halo, Radeon Pro W7900 *

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
git clone https://github.com/your-org/rocm-distro-tester.git
cd rocm-distro-tester
```

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

## Quick Guide to Repository Structure

**Main Project Files:**
- `PLAN.md` - Comprehensive technical specifications and roadmap
- `README.md` - This overview and quick start guide  
- `HISTORY.md` - Design decisions and version history
- `TODO.md` - Current development targets

**Key Directories:**
```
rocm-distro-tester/
├── ci-trigger/
│   ├── poll_{distro}_builds.py  # Package update detection (Fedora, Ubuntu, Arch, EPEL)
│   ├── orchestrator.sh           # Test matrix execution controller
│   ├── tests/                    # pytest test suites for all components
│   └── dashboard/                # Flask web interface for results
├── pkg-tests/
│   └── hipblas/                  # First production-ready test package
│       ├── Dockerfile.*          # Distro-specific container builds
│       └── smoke-tests/          # Comprehensive test scripts
├── docker/                       # Container images (registry, dashboard)
└── scripts/                      # Build automation utilities
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

## Docker Registry Setup (Local Development & CI)

### Quick Start

**1. Deploy Registry on Builder Machine:**
```bash
cd rocm-distro-tester
./ci-trigger/scripts/setup_docker_registry.sh -v
```

This will:
- Create a local registry container (`rocm-registry`) on port 5000
- Set up storage at `/var/lib/registry/docker-registry`
- Validate registry health automatically
- Show next steps for test machine configuration

**2. Configure Test Machines:**  
On each test node where images will run:  
Copy the repo's tester sample into place (it sets `insecure-registries` for this deployment):
```bash
cp <rocm-distro-tester>/samples/daemon.json.tester /etc/docker/daemon.json
# ...adjust the builder hostname/IP if yours differs, then:
sudo systemctl restart docker
```
> Do not confuse the two samples: `daemon.json.tester` = `insecure-registries` (pull-side),
> `daemon.json.builder` = `data-root` (build-side, for the builder node).

**2b. Builder Node Docker Data Root:**  
On the builder machine, before first build:
```bash
cp <rocm-distro-tester>/samples/daemon.json.builder /etc/docker/daemon.json
# ...adjust 'data-root' if your build disk path differs, then:
sudo systemctl restart docker
```

**3. Build and Push Images:**  
On the builder machine (this is where builds happen once, deploy many times):

```bash
# Build all available test images (one-time operation)
./scripts/build-all-images.sh --force-rebuild

# Or build specific image for testing:
./scripts/build-all-images.sh hipblas-fedora
```

**4. Pull and Run on Test Nodes:**  
Once registry is configured, any test node can pull and execute containers:

```bash
docker pull rocm-builder:5000/hipblas-fedora:latest
docker run --rm --device=/dev/kfd rocm-builder:5000/hipblas-fedora:latest
```

---

### Image Naming Convention

All test images use this tagging pattern:
- **Format**: `rocm-builder:5000/<distro>-<package>:latest`
- **Examples**:
  - `rocm-builder:5000/hipblas-fedora:latest`
  - `rocm-builder:5000/hipblas-ubuntu:latest`  
  - `rocm-builder:5000/hipblas-rhel:latest`

---

### Registry Architecture

```
BUILDER MACHINE ───┐       ┌───────────── TEST MACHINES
      │            │       │
  registry:2     local   pull & run
   (port:5000) ├──◄──────►│ docker daemon
                    network configured for 
                    <builder>:5000
```

**Benefits:**
- Build once → Deploy many times across all GPU nodes
- Zero-copy deployment (pulls cached on network)  
- Minimal operational overhead (one process, no complex orchestration)
- Fast subsequent pulls from local registry cache

---

### Troubleshooting Common Issues

1. **Registry won't start**
   ```bash
   docker logs rocm-registry     # View error output
   sudo systemctl status docker  # Check daemon health
   ```

2. **Test machines can't reach registry**  
   Ensure builder hostname resolves from all test nodes:
   ```bash
   ping <builder-hostname>       # Should resolve to local network IP
   cat /etc/docker/daemon.json   # Verify insecure-registries setting
   sudo systemctl restart docker  # Restart Docker on affected nodes
   ```

3. **Image build errors**  
   Check builder machine for:
   - Sufficient disk space (registry stores images persistently)
   - Docker daemon connectivity to network
   - Package dependencies for each distro in respective Dockerfiles

4. **Pull fails on test node**  
   ```bash
   docker info | grep "Registry Mirrors"  # Verify configuration applied
   curl http://<builder>:5000/v2/_catalog  # Manual health check from test node
   ```

---

### Future Enhancements

v0.2 scope (deferred, based on production experience):
- Registry backup and disaster recovery procedures
- Automated registry health monitoring  
- TLS encryption for registry communication
- Multi-organization support with access control

For now: Manual operational simplicity prioritizes single-developer maintenance model.

See [PLAN.md](./PLAN.md#section-6-docker-registry-infrastructure-new-v015) for complete technical details and options evaluation.

## 🖥️ Web Dashboard for Results Aggregation

**Quick Start**: Deploy the dashboard on builder machine to view unified test results across all distros.

```bash
# Deploy dashboard container (one-time)
./ci-trigger/scripts/setup_dashboard.sh -v

# Access from any browser:
http://localhost:5001   # On builder machine
http://<builder-hostname>:5001  # From other machines on network

# API access for programmatic use:
curl http://localhost:5001/api/summary | jq '.statistics'
```

### Dashboard Features:

| Feature | Description | Status |
|---------|-------------|--------|
| **Overview Page** | Statistics, charts, recent activity | ✅ Active |
| **Filtered Results View** | Search by distro/package/result/day window | ✅ Active |  
| **API Endpoints** | JSON data for external integration | ✅ Active |
| **Dockerized Deployment** | Single-container setup on builder machine | ✅ Deployed |
| **Real-time Updates** | Dashboard reflects latest JSON results automatically | ✅ Updated |

### Configuration:

See [PLAN.md](./PLAN.md) for detailed setup instructions including:
- Docker registry deployment
- Dashboard configuration and environment variables  
- Per-distro package dependency specifications

See [PLAN.md Section 7](./PLAN.md#section-7-web-dashboard-for-test-results-new-v016) for detailed technical documentation, API reference, and upgrade considerations.
