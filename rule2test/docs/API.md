# Current API

Transport: factory/server.py (Python stdlib). factory/api is the future API layer scaffold; FastAPI is not installed or implemented yet.

| Method | Path | Input |
| --- | --- | --- |
| GET | /api/health | none |
| GET | /api/demo | none |
| POST | /api/extract | text |
| POST | /api/analyze | old, new, existing |
| POST | /api/run | plan_id, approved_ids, reviewer, fault |
| GET | /api/evidence/{id} | evidence ID |

Use data/demo.json for the current input schema. Error responses contain an error field. New schema modules are reserved for the next implementation phase.
