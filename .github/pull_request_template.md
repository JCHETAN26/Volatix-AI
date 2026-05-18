<!--
ChainGuard-Core PR Template
One PR per build-plan task. Keep PRs small, sequenced, and CI-green.
-->

## Summary
<!-- One or two sentences. What changed and why. -->

## Build-Plan Reference
- **Phase / Task:** <!-- e.g. Phase 2 / Task 2.3 -->
- Link to the relevant section of `build-plan.md`.

## Acceptance Checklist
<!-- Copy the bullets from the task's "Acceptance" section and tick each. -->
- [ ]
- [ ]
- [ ]

## Verification
<!-- How was this verified locally? Commands run, metrics observed. -->
- Commands:
  ```
  ```
- Output / metrics:

## CI Status
- [ ] `frontend-ci` green
- [ ] `cpp-ci` green
- [ ] No new warnings under `-Wall -Wextra -Werror`
- [ ] `clang-format` and `prettier` clean

## Risk & Rollback
<!-- Blast radius, reversibility, anything destructive. -->

## Out-of-Scope
<!-- Anything intentionally not in this PR (link to follow-up issue if any). -->
