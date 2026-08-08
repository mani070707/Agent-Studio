# Frozen FastAPI contract

`fastapi-openapi.json` is the public compatibility baseline. Regenerate it only when an
intentional API contract change has been approved:

```bash
cd api
.venv/bin/python scripts/export_openapi.py
```

FastAPI modules must retain these paths, status codes and snake_case JSON fields. Contract changes
require corresponding frontend and fixture updates.
