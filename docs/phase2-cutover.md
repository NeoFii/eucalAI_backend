# Phase 2 Cutover

This document is retained as operational history. Active schema management is now
Alembic-only for admin and user.

Current commands:

```bash
uv run migrate --service admin-service upgrade head
uv run migrate --service user-service upgrade head
uv run bootstrap-databases
```

The phase2 helper and manifest may still be useful as historical references for
schema ownership review, but they are not part of runtime startup.
