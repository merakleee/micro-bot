# MC Club RAG Chatbot Challenge — Project Brief

> Build a deployed RAG chatbot that answers questions about MC Club accurately, cites its sources, and says "I don't know" instead of inventing.
> The best system becomes MC's official assistant.

---

## 1. Context

You are not students on this project. You are the engineering team shipping it. Reviews are interview-level: every line of code, every design choice and every number you show can be questioned by the jury.

### Who uses the bot

| Audience | What they ask | What the bot must respect |
| --- | --- | --- |
| Non-members (visitors, new students) | What is MC, how to join, events, departments | Public information only, never leak internal content |
| Members | Internal procedures, contacts, projects, event details | Member-only content is answered only to authenticated members |
| Admins (bureau) | Add, update or remove the documents the bot knows | Changes are live without redeploying |

---

## 2. What you must build

### Required

1. **Ingestion pipeline**: load the official MC corpus (PDF, DOCX, Markdown, web pages), clean, chunk, embed and index it. Re-ingesting the same file must not create duplicates.
2. **Grounded answers**: every answer is built from retrieved passages and returns its sources. If the corpus does not contain the answer, the bot says so.
3. **Access levels**: each document is tagged `public` or `members`. Member-only content is never retrieved for an unauthenticated request. Filtering happens at retrieval, not in the prompt.
4. **Follow-up questions**: short conversation memory, so "and when is it?" after a question about an event works.
5. **Language**: answer in the language of the question. Arabic, French and English at minimum.
6. **Admin document management**: add, list and delete documents through the API.
7. **Deployment**: public HTTPS URL, one-command local start (e.g. `docker compose up`), configuration through environment variables, no secrets in the repo.
8. **Evaluation**: your own test set of at least 30 questions with expected answers, plus a script that reports your scores.
9. **Observability**: structured logs per request with latency, number of LLM calls and tokens used.

### Bonus

There is no bonus list. You decide what the bonuses are: think of them and build them.

---

## 3. Mandatory API contract

All teams expose the same endpoints so the hidden tests run identically on every system. You may add endpoints, but these must exist exactly as written.

**Auth**
- Member requests: header `Authorization: Bearer <MEMBER_TOKEN>`
- Admin requests: header `X-Admin-Key: <ADMIN_API_KEY>`
- Both values come from environment variables. Organizers will set them for the tests.

### `POST /api/v1/chat`

Request:
```json
{
  "message": "How do I join MC?",
  "conversation_id": null
}
```

Response `200`:
```json
{
  "answer": "…",
  "conversation_id": "c_123",
  "grounded": true,
  "sources": [
    { "doc_id": "d_42", "title": "Membership guide", "snippet": "…" }
  ],
  "usage": { "llm_calls": 1, "prompt_tokens": 1830, "completion_tokens": 210 },
  "latency_ms": 2400
}
```

- `grounded: false` when the answer is a refusal or "I don't know".
- `message` is limited to 2,000 characters; longer input returns `422`.

### Other endpoints

| Method | Path | Who | Purpose |
| --- | --- | --- | --- |
| `GET` | `/api/v1/health` | Anyone | `{"status": "ok" \| "degraded", "documents": <count>}` |
| `POST` | `/api/v1/documents` | Admin | Upload a file + `visibility` (`public` or `members`). Returns `doc_id` |
| `GET` | `/api/v1/documents` | Admin | List documents with status and visibility |
| `DELETE` | `/api/v1/documents/{doc_id}` | Admin | Remove a document and its chunks from the index |
| `POST` | `/api/v1/feedback` | Anyone | `{conversation_id, rating: "up" \| "down", comment?}` |

### Error format

Every error returns JSON with the right HTTP status code:
```json
{ "error": { "code": "rate_limited", "message": "…" } }
```
A stack trace or an HTML error page in a response is a failure.

---

## 4. Rules and constraints

### LLM provider (same for every team)

- **Model:** `google/gemma-4-31b-it:free` on OpenRouter only. No other generation model, no paid variant.
- **API:** OpenRouter is OpenAI-compatible, so any OpenAI SDK works by changing the base URL.
- **Model facts:** 262K-token context window, 32K max output, text and image input.
- **Free-tier limits:** 20 requests per minute, **50 requests per day** per account. The daily counter resets at 00:00 UTC (01:00 Algiers time).
- **Do not buy credits.** Buying 10+ credits raises the daily limit from 50 to 1,000 requests. Any purchase on a team's account means disqualification.
- One OpenRouter account per team, registered with the organizers.

**What this means for you:** 50 requests per day is the real constraint of this challenge. Every extra LLM call per question (query rewriting, re-ranking with the LLM, self-checking) costs you directly. Design for it.

### Embeddings, vector store and hosting

- Embedding model: your choice, but it must be free (at least a free trial).
- No other paid API of any kind.
- Re-ranking models may run locally (open-source, on CPU) inside your deployment.
- Vector store and hosting must be free tier or self-hosted.

### Architecture

- Over-engineering counts against you. Every component must justify itself with a measured gain.
- Rule of thumb: if you can't explain why a component exists, with a number, remove it.

### Code and repository

- Git from day one. No secrets in the repo (`.env.example` only).
- Commits from every team member. One giant commit on the last day counts against you.
- AI coding assistants are allowed, but every member must be able to explain any line in the repo.

---

## 5. Engineering mindset: edge cases

This brief does not list every edge case on purpose. Finding them is part of the job.

For each edge case you find, record it in `EDGE_CASES.md`:

| Edge case | Proof it is real | Decision | Why |
| --- | --- | --- | --- |
| Short description | Log, failing test or reproduction steps | Fixed / Accepted / Deferred | Cost vs impact |

Rules:
- An edge case without proof does not count.
- Fixing something that is not real, or that costs more than it saves, is over-engineering.
- "Accepted, here is why" is a valid engineering answer.

---

## 6. Daily process

Every day at **[TIME TBD]**, each team presents:

1. **What shipped** since yesterday, shown working (not slides).
2. **What is blocked** and what you tried.
3. **What is next** for tomorrow.

Maximum 5 minutes per team. The jury also checks the repository: commits per member, reviewed pull requests, and a short `PROGRESS.md` updated daily.

---

## 7. Project journal (`project_journal.md`)

Every team member creates their own `project_journal.md` in the repo (for example `journals/<your-name>/project_journal.md`).

This file documents the whole process: what you tried, the errors, the approaches, what you learned — everything you thought about while doing the project.

- It is required.
- It doesn't have to be organised: just date, name and notes.
- It can give extra points.

---

## 8. Judging criteria

| Criterion | Weight | What is measured |
| --- | --- | --- |
| Output quality | 25% | Correct, grounded answers with right sources; honest refusals; right language |
| Robustness | 20% | No crash, no 500, graceful behavior when the LLM is slow, rate-limited or down |
| Optimization | 15% | Quality per LLM call and per token; latency |
| Code quality and good practices | 15% | Readability, structure, tests, config, error handling, repo hygiene |
| Architecture | 10% | Fits the problem; simple; every part justified |
| Daily progress and collaboration | 10% | Steady progress; every member contributes |
| Final presentation and Q&A | 5% | Clarity, honesty, ability to defend choices |

Since the model is free, **"cost" means LLM requests and tokens per answered question**, measured from the `usage` field in your responses and from the hidden test logs.

---

## 9. Hidden tests

Your system will be evaluated with hidden tests.

---

## 10. Deliverables

- [ ] Repository link (organizers invited)
- [ ] `README.md`: setup in 5 commands or fewer, architecture, key decisions
- [ ] `.env.example`
- [ ] Docker setup or equivalent one-command start
- [ ] Evaluation set + script + results
- [ ] `EDGE_CASES.md`
- [ ] `PROGRESS.md`
- [ ] `project_journal.md` for every member
- [ ] Public deployed URL
- [ ] Presentation slides

---

## Sources

- [Gemma 4 31B (free) on OpenRouter](https://openrouter.ai/google/gemma-4-31b-it:free)
- [OpenRouter rate limits](https://openrouter.ai/docs/api-reference/limits)