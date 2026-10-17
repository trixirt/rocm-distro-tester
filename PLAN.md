# ROCm-Distro-Tester CI Framework - Project Plan

**Status**: v0.2 (Updated for Storage Requirements)  
**Date**: Oct 16, 2024  
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
│  │  Shared Registry: Docker Images built once, pulled everywhere   │
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
...
```

---

## Implementation Roadmap

### Phase 1: Core Infrastructure (2 weeks)
**Week 1-3**: Set up base automation framework

### Phase 2: Distro Abstraction Layer (1 week)
- Complete `package-config.yaml` for all ROCm packages

### Phase 3: Queue Management & Scaling (2 weeks)
- GPU resource queue to prevent concurrent jobs on single node

---

## File Structure Template

The repository root can be placed anywhere on your system.

---

# Section 6: Docker Registry Infrastructure (v0.1.x)

This document outlines the deployment of a local Docker Registry (`registry:2`) on the **controller/builder machine** to facilitate building and distributing test images to remote GPU tester nodes.

#### 📍 Architecture & Flow

```
              ┌─────────── Builder / Controller Node ───────────┐
              │            (Expected IP: 192.168.1.25)          │
              │                                                  │
      git     │   <--- poll packages from Koji/Launchpad        │
clone         │   [ docker build ] → [ registry:2 ]             │
pull ─────────┘                         │                        ▼
                                          push                    [ Remote Tester Machines ]
                                                                    - Pull Images
                                                                    (rocm-builder:5000/...)
                                                                    - Execute Smoke Tests
```

**Key Operational Principles:**
1.  **Local Registry**: The controller node serves as a lightweight internal Docker Hub (`registry:2`) on port `5000`. No internet access is required for test nodes.
2.  **Build-Once-Deploy-Many**: Images are built *once* on the builder and pushed to the local registry. Remote tester nodes simply `docker pull` from this central source.
3.  **Tagging Convention**: All builds use the format **`rocm-builder:5000/<package-distro>:latest`**.

#### 🎨 Image Naming & Versioning Policy

| Distro | Standard Tag Format | Example (hipblas-fedora) |
|--------|---------------------|--------------------------|
| **Fedora** | `rocm-builder:5000/fedora-<pkg>` | `rocm-builder:5000/hipblas-fedora:latest` |
| **Ubuntu** | `rocm-builder:5000/<distro>-<pkg>` | `rocm-builder:5000/hipblas-ubuntu:latest` |
| **RHEL/CentOS** | `rocm-builder:5000/<package>-<release>` | `rocm-builder:5000/hipblas-rhel-central9:latest` |

#### 📊 Storage & Infrastructure Requirements (Updated)

To support a complete matrix build (targeting ~1000 distinct Dockerfiles across Arch, Fedora, Ubuntu, etc.) and maintain a registry copy for each node, significant resources are required.

| Configuration Metric | Requirement / Standard | Implementation Details |
|----------------------|------------------------|------------------------|
| **OS Architecture** | 64-bit x86_64 (or ARM64 if supported) | Ubuntu/Fedora/RHEL base compatibility |
| **Docker Version** | v20.10+ with BuildKit enabled | Required for `DOCKER_BUILDKIT=1` builds |
| **Storage on Builder** | **≥500GB dedicated capacity** | Root partition used only for OS; `/rocm-builder` handles all image layers and registries |
| **Data Root Directory** | `/rocm-builder` (Mounted) | Configured via `daemon.json` to isolate build space from system root |

---

### 🧱 6.1 Hardware Readiness Verification (Builder Node)
Before attempting matrix builds, every builder node must pass the `verify_builder_setup.sh` checks:

| Requirement | Description |
|-------------|-------------|
| **Registry Alias Identity** | Must resolve to `EXPECTED_IP` (e.g., 192.168.1.25) in `/etc/hosts` |
| **Docker Root Dir Alignment** | Must be configured as `/rocm-builder` and active in daemon config |
| **Storage Capacity** | Minimum **500GB total volume** on the `/rocm-builder` mount point |
| **Directory Permissions** | Strict ownership: `root:root` mode `0700` (Required for Docker security) |
| **Docker Runtime** | Must be running and accessible by a non-root user in the `docker` group |

**Deployment Checksums**: Verify deployment integrity across all test nodes using standard image digests to ensure consistency.