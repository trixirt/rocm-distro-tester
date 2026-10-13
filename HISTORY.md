# ROCm-Tester Project History

## Creation Date: Oct 8, 2024

### Initial Requirements Discussed:
1. **Test ROCm packages** from Fedora project (Koji/Bodhi)
2. **Multi-distro support**: Ubuntu, Fedora, OpenSUSE
3. **Self-hosted infrastructure only** - no GitHub Actions or cloud CI dependency
4. **Multiple GPU test machines** locally accessible (MI200, MI300, Vega, etc.)
5. **Single developer** maintaining and developing the CI system
6. **Resource-constrained environment**: need to batch and queue test jobs efficiently

### Key Design Decisions:
- Use Ansible for multi-distro node provisioning and configuration
- Use Jenkins Pipeline + Poller for orchestrating distributed GPU tests  
- Distro-specific Dockerfiles with unified test scripts
- Package version tracking via Koji API / Launchpad polling

## Plan Evolution
See `PLAN.md` for current state of planning. This file tracks changes and major revisions.

### Version Log:
- v0.1 (Oct 8, 2024) - Initial creation during requirements gathering session
  - Discussed GitHub Actions vs Jenkins vs Custom controller approach
  - Decided on self-hosted Ansible+Jenkins for maximum control and no external dependencies
  - Identified need for distro-agnostic test abstraction layer
  - Defined hipblas/smoke as first package to migrate
