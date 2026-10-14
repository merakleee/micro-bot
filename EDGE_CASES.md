# EDGE CASES

| Edge case                                  | Proof it is real                                                                              | Decision                | Why                                                                                                      |
| ------------------------------------------ | --------------------------------------------------------------------------------------------- | ----------------------- | -------------------------------------------------------------------------------------------------------- |
| Message longer than 2,000 characters       | `test_chat_message_too_long` (2,001 chars returns 422 in the error format)                    | Fixed                   | Required by the contract. Enforced in the schema, so no code path can forget it.                         |
| Empty or whitespace-only message (`"   "`) | `test_chat_empty_message` (returns 422)                                                       | Fixed                   | Would otherwise reach retrieval and the LLM and waste one of the 50 daily requests.                      |
| Wrong bearer token                         | `test_chat_bad_token` (returns 401)                                                           | Fixed (design decision) | Treating it as public would silently hide a client bug. The client should learn it is not authenticated. |
| Unexpected exception inside a route        | `test_unexpected_exception_hides_internals` (500 JSON, internal message absent from response) | Fixed                   | A stack trace or HTML page in a response is a stated failure. Trace goes to server logs only.            |
| Unknown route or wrong HTTP method         | `test_unknown_route_is_json`, `test_wrong_method_is_json` (404 and 405 in the error format)   | Fixed                   | FastAPI's default shape differs from the contract's error format.                                        |


## Ingestion pipeline decisions

- A file is identified by the SHA-256 hash of its bytes.
- A ready document with the same hash and visibility is skipped and returns the existing `doc_id`.
- A ready document with the same hash but different visibility is rejected instead of being silently skipped. This prevents content from remaining publicly visible when a later upload requests members-only visibility.
- Failed documents are retried using their existing registry row.
- Processing documents are retried using their existing registry row, which handles a previous process crashing during ingestion.
- A lock protects the hash lookup and document-creation sequence for concurrent uploads in the same process. The SQLite unique index protects the hash across processes.
- A document that produces no usable chunks is marked as failed.
- If parsing, chunking, embedding, or indexing fails, any chunks already added are deleted and the document is marked as failed with the error message.
- Document deletion removes vector-store chunks before deleting the registry row. If chunk deletion fails, the registry row remains so deletion can be retried.
- Chunk IDs are deterministic and based on the registry `doc_id` and chunk index.
- E5 receives text prefixed with `passage: `, while the original unprefixed text is stored in the vector store.
- The embedding model is loaded lazily and reused across files.
- The command-line loader reads only `corpus/manifest.csv`, uses the manifest title and visibility, continues after individual failures, and exits with an error if any file fails.