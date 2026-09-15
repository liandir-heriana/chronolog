---
name: security-audit
description: Audit IDOR, injection and user_id isolation in ChronoLog. Use for TSK-015.
---

## What I do
- Find queries without user_id, secrets in code.
- Run bandit, require findByIdAndUserId.

## When to use me
Every persistence or auth change.
