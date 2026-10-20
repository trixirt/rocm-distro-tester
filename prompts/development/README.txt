development-*.xml - Prompt corpus for developing rocm-distro-tester

These self-contained XML prompts instruct the `pi` coding agent to
work on THIS repository: onboarding analysis, design reviews, and
code-verification passes. Prompt style follows the
fedora-pi-prompts corpus (pi < prompt-file).

Usage (from the repository root)
------------------------------------------------------------------------

    pi < prompts/development/project-getting-started.xml

Prompts
------------------------------------------------------------------------

project-getting-started.xml
  Fresh-checkout analysis. Reads the docs in intent order, reviews
  the last 20 commits, verifies the code against its own claims
  (bash -n / py_compile / pytest), classifies every component as
  production-grade, in-progress, or draft, cross-checks the three
  pillars against their PLAN.md sections, and reports a status table
  with findings and suggested next steps.
  Output: /tmp/rocm-distro-tester-getting-started.txt

design-review.xml
  Reviews a proposed change (pasted, a file, or a PLAN.md section)
  against the project invariants: PLAN.md as contract, registry
  tiering, the sacred port map, state-DB discipline, node roles,
  SELinux/host reality, digest-named receipts, test-layout policy,
  and the verify-script rule. Verdict APPROVE /
  APPROVE WITH CHANGES / REJECT, with per-invariant PASS/CONFLICT,
  affected files, required verify scripts, unstated assumptions,
  and concrete alternatives. Review only — it does not implement.
  Output: /tmp/rocm-distro-tester-design-review.txt

verify-change.xml
  The post-change gate. Establishes the change set (user-named,
  uncommitted, or last commit), then runs the applicable checks —
  shell/python syntax, poller tests, compose parse, SELinux :z on
  writable mounts, registry-tier naming, pkg-tests layout,
  docs parity, and the matching verify_*.sh battery — reporting
  PASS / PASS WITH WARNINGS / FAIL with the failing line and most
  likely cause. Verifies; it does not fix or refactor. Closes with
  a residual-risk list (things needing a GPU node, SELinux-Enforcing
  host, or live infra).
  Output: /tmp/rocm-distro-tester-verify-change.txt

Workflow
------------------------------------------------------------------------
  These three form a loop around a change:

    design-review.xml      -> judge the proposal before coding
    <implement>            -> human + pi write the code
    verify-change.xml      -> prove it safe before calling it done

  getting-started.xml remains the entry point of every session in a
  fresh clone.

Outputs (for all prompts)
------------------------------------------------------------------------
  /tmp/rocm-distro-tester-<prompt-stem>.txt

  Every prompt ends with a built-in improvement clause: if any
  instruction is confusing the agent proposes three better; if data
  is missing it asks for it. The corpus is expected to iterate.
