---
name: sdd-apply
description: Apply mandatory SDD+TDD RED-GREEN-REFACTOR for ChronoLog domain/use-cases. Use for TSK-005..011.
---

## What I do
- SDD apply phase is mandatory. Follow spec/design from doc/proposal.md and ADR before coding. No vibe coding: never generate production code without a prior spec.
- RED: write the failing unit test first. GREEN: minimal code. REFACTOR clean.
- Enforce DIP, user_id mandatory, Python only in domain/.
- Every task must then pass `/verify` and `/archive`.

## When to use me
Every backend domain/use-cases change.
