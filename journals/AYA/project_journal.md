# AYA's Project Journal

## Day 1

I started working on how the chatbot reads its documents. I added a parser in `app/ingestion/parsers.py` for Markdown, PDF, and DOCX files.

The parser gives each file a title from its filename and extracts its text. It reports a clear error if a file is empty, broken, unreadable, or in a format we do not support.

I added `pypdf` and `python-docx` to `requirements.txt` so the app can read PDF and DOCX files. I also added `tests/test_parsers.py` to check the parsers with normal files and a few problem cases.

I added `.vscode/` to `.gitignore` and moved the team journals into separate folders. Slimane's notes are now in `journals/SLIMANE/`, and mine are in `journals/AYA/`.

### Next ?

Next, I will add a parser for web pages. I will also handle PDFs made up of images, where the text cannot be copied or extracted directly.

I have not run the tests yet, so I still need to check that they pass. I should also check whether our documents include password-protected PDFs or tables in DOCX files.

## Day 2

I added OCR support for PDFs using OCRmyPDF and Tesseract. The parser now runs OCRmyPDF in `redo_ocr` mode before reading the PDF text. OCRmyPDF analyzes the page content, keeps visible selectable text, and OCRs text found in images. The old `skip_text` mode skipped the whole page as soon as it found any selectable text, so it could miss words in an image on that same page. Redo mode is meant to handle this mixed-content case.

For the OCR setup, the project needs the `ocrmypdf` Python package, Tesseract with the `eng`, `fra`, and `ara` language data, and a PDF rasterizer such as Ghostscript. Tesseract is installed on my computer; I checked that English, French, and Arabic are available. Ghostscript 10.08.0 (64-bit) is installed at `C:\Program Files\gs\gs10.08.0\bin`; I verified it with `gswin64c.exe --version`. The Python packages must be installed with `python -m pip install -r requirements.txt` in the project's virtual environment. Tesseract reads words from page images, while OCRmyPDF coordinates OCR and adds a text layer that `pypdf` can read.

I updated the parser test to cover a page with both selectable text and text inside an image. I ran the parser tests: all 12 passed. I also made a temporary image-only PDF and sent it through the real parser; OCRmyPDF  and Tesseract recognized "MicroClub OCR verification 123" correctly.

The installed 64-bit Ghostscript is available for OCRmyPDF's PDF processing. The real OCR check succeeded using the PDFium rasterizer installed with OCRmyPDF, so Ghostscript was not needed for that simple PDF.

Because `redo_ocr` checks every PDF, it adds processing time during ingestion. This is the trade-off for catching pages where only some of the text is selectable. We can look for a faster strategy later if ingestion time becomes a problem.

I added a general web page parser in `app/ingestion/parsers.py`. It fetches HTTP and HTTPS pages, extracts the title and readable text, and removes scripts, styles, navigation, footers, and noscript content. It reports clear errors for invalid URLs, failed requests, and pages with no readable text. I added `beautifulsoup4` to `requirements.txt` for HTML parsing.

I tested the generic parser on `https://www.microclub.info/` and found that its initial HTML contains an empty React root. The site renders its content with JavaScript, so a normal HTTP request cannot read the page body. I added a rendered-page parser path that uses headless Chromium through Playwright, scrolls to reveal viewport-triggered sections, and removes scripts, styles, navigation, the footer, and the code-editor panel before extracting page text.

I added Playwright to `requirements.txt` and installed Chromium with `playwright install chromium`. I tested the parser against the live site: it returned the title `Micro Club` and extracted the rendered event and project text. A static HTML fixture and Arabic text fixture are still needed for repeatable parser tests.

### Why Playwright with Chromium?

Micro Club builds its page with JavaScript, so a simple HTTP request with `httpx` and HTML parsing with BeautifulSoup cannot access the rendered content. Playwright lets the parser wait for the page to load and read the text from a real browser. Chromium is a practical browser to run headlessly and install through Playwright. This is a better fit for this JavaScript-rendered page than a static HTML parser; for regular pages, the lighter `httpx` and BeautifulSoup path is still enough.

## Day 3

### Issue #9 — LLM client and daily counter

Before implementing the OpenRouter client, I clarified how the daily limit should work. The project brief sets a limit of 50 requests per day. Per the latest decision, only a valid successful completion remains counted. The UTC-date counter has a configurable limit that defaults to 50. A slot is reserved atomically before each provider attempt so concurrent requests cannot exceed the limit; failed HTTP responses, transport errors, and invalid responses release their reservations. A retry reserves separately. If the limit is reached, the app returns a JSON `rate_limited` error without contacting the model.

The project already has OpenRouter settings, the `httpx` dependency, shared JSON error handling, and SQLite persistence for documents. The next implementation steps are to add configurable quota and timeout settings, store the daily request count in SQLite, build and test the client with mocked responses, then connect it to the chat flow when the RAG integration is ready.

I implemented the SQLite reservation and release functions in `app/llm/daily_counter.py`. It creates its table automatically in the configured database, keys usage by UTC date, and uses SQLite immediate transactions plus a conditional upsert to make reservations atomic. A failed attempt can release its reserved slot; a valid successful completion leaves it counted. The caller reserves immediately before each provider HTTP attempt, including retries.

I added `tests/test_daily_counter.py` with coverage for automatic database/table creation, the exact quota boundary, releasing a failed reservation, the JSON 429 error response, persistence across connections, UTC date rollover and offset conversion, naive datetime rejection, and concurrent reservations. The 9 counter tests pass.

The counter tests check database creation and persistence, quota enforcement and JSON errors, releasing failed reservations, UTC day reset and timezone conversion, invalid dates, and concurrent requests.

I implemented `app/llm/client.py` as a synchronous OpenRouter chat-completions client. It reads the provider URL, model, key, and timeout from settings; reserves quota before each attempt; releases reservations for failed attempts; retries once only for HTTP 429 and 5xx responses; validates response text and token usage; and maps provider/transport failures to the shared `llm_unavailable` or `rate_limited` JSON errors. Its injectable `httpx` transport lets tests use `MockTransport` without network access. `tests/test_llm_client.py` covers successful payload and usage parsing, timeout, 429 and 5xx retries, invalid JSON/response data, non-retryable 4xx, missing key, invalid input, quota exhaustion, and confirms failed calls do not stay in the quota.

The LLM client and daily counter are currently independent of `/chat`; the chat route remains a stub until the RAG integration is ready.

### Issue #17 — Evaluation set

I created `evals/evaluation_set.json` with 40 questions, expected answers, and expected source documents. The cases cover public and members-only content, out-of-scope questions, member-only questions asked without authentication, follow-ups, and English, French, and Arabic. JSON keeps each case's fields structured and consistent, so a future evaluation script can load and process the set directly. The file is a reference dataset; it is not yet connected to an automated evaluator or `/chat`.


## Day 4

### Issue #6 — Vector store selection

I chose Qdrant as the performance candidate for filtered vector search. Each point can hold a chunk's embedding, text, and payload metadata such as `doc_id`, `title`, and `visibility`. Public searches can require `visibility = public`, while member searches can allow both `public` and `members`; the application must choose the filter from the authenticated access level.

I chose Qdrant because this RAG needs vector similarity search combined with strict `visibility` and `doc_id` filters. Qdrant supports payload indexes and filter-aware HNSW search in server mode, giving us explicit controls for those filters as the collection grows; it can also run locally while we develop. [Qdrant's filtering documentation](https://qdrant.tech/documentation/search-patterns/vector-search-filtering/) describes how payload indexes support filtered search. The current local mode does not use payload indexes, so the server-mode performance benefit is a reason to benchmark later, not a measured result.

Chroma is a valid alternative: it also supports metadata filtering and self-hosted deployment. I did not reject it for missing features; I chose Qdrant because its payload-index and filtered-search controls fit this project's access-filtering priority and anticipated server deployment. [Chroma's documentation](https://docs.trychroma.com/docs/overview/introduction) confirms its metadata-filtering support. FAISS concentrates on nearest-neighbor search, so we would need to build and maintain filtering and deletion logic ourselves. SQLite would need a vector extension or custom similarity-search implementation. A managed-only service would not meet this issue's self-hosted-store requirement. This is a fit-based choice, not proof that Qdrant is faster than Chroma for our data; no direct Qdrant-versus-Chroma benchmark has been run.

I implemented `QdrantVectorStore` in `app/vector_store.py`. It adds chunks with stable point IDs, deletes all chunks for a `doc_id`, and searches with a visibility filter chosen from the caller's access level. The default configuration persists data under `data/qdrant`; `QDRANT_URL` and `QDRANT_API_KEY` can connect to a Qdrant server. Payload indexes are created in server mode for `visibility` and `doc_id`; local mode does not use those indexes. The vector store is not yet connected to ingestion or `/chat`.

The store also exposes `replace_document_chunks` to replace one document's indexed chunks, so chunks left over from an older, longer version are removed. It validates chunk ownership, embedding count, visibility, embedding dimensions, and compatibility with the existing collection before deleting the old data. Search also checks that returned Qdrant payloads contain all required fields and raises a clear `ValueError` if one is incomplete. The main operations are: `add_chunks` stores each chunk with its embedding and metadata; `delete_by_doc_id` removes every stored chunk belonging to one document; `search` finds the closest vectors while filtering results according to the caller's public or member access level.

Tests use Qdrant's in-memory mode for behavior and an isolated temporary directory for persistence. They cover access filtering, member search, deletion, upsert and document replacement, preserving old data when replacement validation fails, collection dimension mismatch, incomplete payloads, persistence, NumPy vectors, and input validation. Verification: all 20 vector-store tests and all 91 project tests pass; the full suite reports one Starlette/httpx deprecation warning. Replacement validation occurs before deletion, but deletion and the subsequent upsert are separate Qdrant operations, so an unexpected storage failure between them could leave the document without its old or new chunks. This implementation does not yet make replacement atomic.

I added `TextEmbedder` in `app/embeddings.py` to turn document passages and search questions into normalized vectors using the configured Sentence Transformers model. It applies E5's `passage:` prefix to document text and `query:` to questions, loads the model only on first use, and allows a fake model to be injected for tests. `tests/test_embeddings.py` checks prefixes, empty inputs, returned vectors, and lazy model loading without downloading or calling the real model. `scripts/real_embedding_check.py` provides a repeatable smoke check that loads the configured real model and verifies document/query dimensions, finite values, and normalization; it passed with 384-dimensional E5 vectors. The embedder is not yet wired into ingestion, Qdrant search, or `/chat`. Verification after this addition: 9 embedding tests and 100 project tests pass; the full suite has one Starlette/httpx deprecation warning.

### Issue #14 — Real `/health`

Updated `/api/v1/health` to report the number of ready SQLite documents and return `degraded` if the database count or Qdrant connectivity check fails. The endpoint does not call the LLM. Added a registry count function and a Qdrant connection check; health-created Qdrant clients are closed after the probe. Tests cover the ready-document count, healthy response, and degraded responses for database and vector-store failures. Verification: 28 focused health/registry/foundation tests and all 104 project tests pass; one Starlette/httpx deprecation warning remains.

## Day 5

### Documents management API

Added admin-protected `POST` and `GET /api/v1/documents` routes and `DELETE /api/v1/documents/{doc_id}`. Uploads accept Markdown, PDF, and DOCX, validate visibility, and enforce the configurable `MAX_UPLOAD_BYTES` limit (10 MiB by default). Uploads use the existing ingestion pipeline; listing omits internal content hashes, and deletion removes Qdrant chunks before the registry entry. Unknown document IDs return JSON 404 errors. Tests cover admin authentication, invalid visibility, unsupported and oversized uploads, listing, unknown IDs, and deleting an uploaded document then confirming vector search returns no matching chunks. Verification: all 9 focused document tests pass. The other tests pass when `tests/test_foundations.py` is excluded (129 passed, 1 skipped); two tests in that existing file try to load the real embedding model and fail here because the Hugging Face cache is inaccessible.

### Feedback endpoint

I implemented the public `POST /api/v1/feedback` endpoint. It accepts a non-empty `conversation_id`, a `rating` of `up` or `down`, and an optional comment limited to 1,000 characters. Valid feedback is saved in SQLite and the endpoint returns `201` with a `feedback_id`. Invalid input returns the standard `422` validation error; a database write failure returns a clean `503` error.

I added contract tests for both ratings, comments present or absent, the 1,000-character boundary, invalid ratings, and empty conversation IDs. I ran the feedback, registry, document-route, and foundation tests: all 46 passed. The run reported one Starlette/httpx deprecation warning, with no test failures.
