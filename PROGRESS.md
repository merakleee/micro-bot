# PROGRESS

## Day 1

### Shipped
- API skeleton with FastAPI, mounted under `/api/v1`.
- `GET /health` returns `{"status": "ok", "documents": 0}` (count is a placeholder until the document store exists).
- `POST /chat` is a stub that matches the contract shape (answer, conversation_id, grounded, sources, usage, latency_ms). No RAG yet.
- Unified error format `{"error": {"code", "message"}}` for our errors, HTTP errors (404/405), validation errors (422) and unexpected exceptions (500). No stack traces or HTML in responses.
- Auth: no header means `public`, valid `Authorization: Bearer` means `members`, wrong token returns `401`. Admin check via `X-Admin-Key` is written but not attached to any route yet.
- Message validation: 1 to 2,000 characters after trimming, otherwise `422`.
- Config through environment variables, `.env.example` committed, `.env` gitignored.
- 9 automated tests, all passing (`pytest -v`).


### Next (Day 2)
- Ingestion pipeline: parse Markdown/PDF/DOCX, clean, chunk, hash-based deduplication.
- Choose a multilingual embedding model (Arabic, French, English) and test it locally.
- Add a test for empty bearer token and record it in `EDGE_CASES.md`.