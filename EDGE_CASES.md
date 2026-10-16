# EDGE CASES

| Edge case                                  | Proof it is real                                                                              | Decision                | Why                                                                                                      |
| ------------------------------------------ | --------------------------------------------------------------------------------------------- | ----------------------- | -------------------------------------------------------------------------------------------------------- |
| Message longer than 2,000 characters       | `test_chat_message_too_long` (2,001 chars returns 422 in the error format)                    | Fixed                   | Required by the contract. Enforced in the schema, so no code path can forget it.                         |
| Empty or whitespace-only message (`"   "`) | `test_chat_empty_message` (returns 422)                                                       | Fixed                   | Would otherwise reach retrieval and the LLM and waste one of the 50 daily requests.                      |
| Wrong bearer token                         | `test_chat_bad_token` (returns 401)                                                           | Fixed (design decision) | Treating it as public would silently hide a client bug. The client should learn it is not authenticated. |
| Unexpected exception inside a route        | `test_unexpected_exception_hides_internals` (500 JSON, internal message absent from response) | Fixed                   | A stack trace or HTML page in a response is a stated failure. Trace goes to server logs only.            |
| Unknown route or wrong HTTP method         | `test_unknown_route_is_json`, `test_wrong_method_is_json` (404 and 405 in the error format)   | Fixed                   | FastAPI's default shape differs from the contract's error format.                                        |

## Other tested API edge cases

| Edge case | Proof it is real | Behavior |
| --- | --- | --- |
| Missing or invalid admin key on document operations | `test_all_document_operations_require_admin` | Each documents route returns the shared 401 JSON error. |
| Unsupported upload extension | `test_upload_rejects_unsupported_file_type` | Upload returns 415. Supported suffixes are `.md`, `.markdown`, `.pdf`, and `.docx`. |
| Upload exceeds configured byte limit | `test_upload_rejects_file_over_configured_size` | Upload returns 413 before ingestion proceeds. |
| Visibility is outside `public` / `members` | `test_upload_rejects_invalid_visibility`, `test_invalid_visibility_is_rejected` | Request is rejected with a validation error; invalid visibility cannot be stored. |
| Delete references an unknown document | `test_delete_unknown_document_returns_404`, `test_delete_unknown_document_returns_false` | API returns 404; pipeline reports that nothing was deleted. |
| Feedback has an invalid rating or blank conversation ID | `test_feedback_rejects_invalid_rating`, `test_feedback_rejects_empty_conversation_id` | Request returns 422 and does not create the feedback database. |
| Feedback comment is at or over the 1,000-character limit | `test_feedback_accepts_comment_at_limit`, `test_feedback_rejects_comment_over_limit` | 1,000 characters is accepted; 1,001 is rejected. |
| Feedback comment is omitted | `test_feedback_allows_missing_comment` | Feedback is accepted and the stored comment is `NULL`. |
| Health dependency is unavailable | `test_health_is_degraded_when_database_is_unreachable`, `test_health_is_degraded_when_vector_store_is_unreachable` | Health remains a JSON response with `status: degraded`; an unavailable database reports zero documents. |

## Embedding and language edge cases covered by tests

| Edge case | Proof it is real | Behavior |
| --- | --- | --- |
| E5 document/query prefixes and vector normalization | `test_embed_documents_adds_e5_passage_prefix_and_normalizes`, `test_embed_query_adds_e5_query_prefix` | Documents use `passage: `, queries use `query: `, and the model is asked to normalize vectors. |
| Empty document batch or empty/whitespace document/query | `test_empty_document_list_returns_without_loading_or_calling_model`, `test_embed_documents_rejects_empty_text`, `test_embed_query_rejects_empty_text` | Empty batch returns without loading the model; blank texts are rejected before encoding. |
| Model should not load until needed and should be reused | `test_model_is_loaded_lazily_and_reused` | Model is loaded on first use and reused. |
| English, French, Arabic, mixed Arabic/Latin, ambiguous Latin, or blank input | `test_detect_language`, `test_arabic_is_detected_even_when_text_contains_latin_words`, `test_ambiguous_latin_text_defaults_to_english`, `test_detect_language_rejects_empty_text` | Supported languages are detected; ambiguous Latin defaults to English; blank input is rejected. |

## Ingestion, parsing, and chunking edge cases covered by tests

| Edge case | Proof it is real | Behavior |
| --- | --- | --- |
| Empty or whitespace-only Markdown, DOCX, or parsed document | `test_parse_md_rejects_empty_file`, `test_parse_docx_rejects_empty_document`, `test_empty_document_is_marked_failed` | Empty input is rejected; failed ingestion is recorded and creates no chunks. |
| Invalid UTF-8 Markdown | `test_parse_md_rejects_invalid_utf8` | Parser reports an unreadable Markdown file. |
| Unsupported file format | `test_parse_document_rejects_unsupported_format` | Parser rejects the format rather than guessing. |
| PDF mixes selectable text and scanned text | `test_parse_pdf_ocr_handles_selectable_and_image_text` | OCR output preserves existing selectable text and adds recognized image text. |
| Chunker receives empty text, invalid overlap, or a long section | `test_empty_text_returns_no_chunks`, `test_invalid_overlap_is_rejected`, `test_large_text_is_split` | Empty input yields no chunks; invalid overlap raises; long text is split within the configured character limit. |
| Text normalization and overlap boundaries | `test_normalize_text`, `test_chunks_have_overlap` | Whitespace is normalized and adjacent chunks retain the configured overlap. |
| An ingestion fails after vectors may have been written | `test_failed_ingestion_marks_document_failed_and_removes_chunks`, `test_vector_store_failure_keeps_registry_row` | Ingestion marks the registry row failed and attempts to remove partial vectors; a failed vector deletion preserves the registry row for retry. |
| Same file is uploaded again, or with a different visibility | `test_ingesting_same_file_twice_skips_without_adding_duplicates`, `test_same_hash_with_different_visibility_is_rejected` | Same hash and visibility is skipped; changing visibility is a 409 conflict instead of silently changing access. |
| Previously failed document is retried | `test_failed_document_can_be_retried` | Retry reuses its document ID and clears the prior error on success. |
| Deletion must not leave searchable chunks | `test_delete_document_removes_chunks_before_registry_row`, `test_delete_then_search_returns_no_document_chunks` | Vectors are removed before the registry row; subsequent search returns no deleted chunks. |

## Retrieval, access control, and answer edge cases covered by tests

| Edge case | Proof it is real | Behavior |
| --- | --- | --- |
| Public search's best match is members-only | `test_public_search_filters_member_perfect_match_before_top_k` | Visibility filtering happens before top-k selection; private content cannot displace public results or leak. |
| Member search has both public and members content | `test_member_search_can_return_public_and_members_chunks` | Members can retrieve either visibility. |
| Retrieval score is below, equal to, or above threshold | `test_retrieve_refuses_when_best_score_is_below_threshold`, `test_retrieve_accepts_score_equal_to_threshold`, `test_retrieve_returns_chunks_with_scores` | Below threshold refuses; equality is accepted. |
| Store is empty, query is blank, or top-k is non-positive | `test_retrieve_refuses_empty_store`, `test_retrieve_rejects_empty_query`, `test_retrieve_rejects_invalid_k` | Retrieval fails cleanly instead of embedding an invalid request or returning unsupported context. |
| No sufficiently relevant context exists | `test_chat_returns_refusal_when_retrieval_is_below_threshold`, `test_refusal_log_matches_zero_usage` | Chat returns a refusal with no sources and zero LLM usage; the LLM is not called. |
| LLM returns an empty refusal marker or malformed answer | `test_finalize_answer_treats_empty_model_output_as_refusal`, `test_finalize_answer_converts_english_marker_to_refusal`, `test_finalize_answer_converts_french_marker_to_refusal`, `test_finalize_answer_converts_arabic_marker_to_refusal` | Empty or exact refusal marker becomes a localized refusal; normal text remains grounded. |
| Retrieved text contains prompt-like instructions | `test_prompt_marks_passages_as_untrusted_data`, `test_prompt_does_not_treat_passage_text_as_system_instructions` | Retrieved passages are framed as untrusted data, not instructions. |
| Prompt context exceeds its size cap or configuration is invalid | `test_prompt_respects_context_size_cap`, `test_prompt_rejects_non_positive_context_cap` | Context is limited; a non-positive cap is rejected. |
| A member conversation is later used without member access | `test_public_access_does_not_reuse_members_turns`, `test_public_reusing_members_conversation_does_not_reuse_members_context` | Previous members-only questions and retrieved content are not reused by a public request. |
| Conversation has no history, exceeds turn/query/conversation limits, or is cleared | `test_first_question_is_used_as_retrieval_query`, `test_only_recent_turns_are_kept`, `test_query_is_size_capped`, `test_conversation_count_is_capped`, `test_clear_removes_conversation` | First query stands alone; old turns are dropped; query and conversation counts are bounded; clearing removes history. |
| Conversation memory receives a blank ID/question or invalid access level | `test_invalid_inputs_are_rejected` | Invalid memory inputs raise `ValueError`. |
| Chat gets a caller-supplied conversation ID or a French question | `test_chat_preserves_supplied_conversation_id`, `test_chat_passes_detected_language_to_prompt` | Supplied ID is returned unchanged; detected language reaches the prompt builder. |

## External LLM, quota, observability, and storage edge cases covered by tests

| Edge case | Proof it is real | Behavior |
| --- | --- | --- |
| LLM timeout or unavailable configuration | `test_timeout_returns_llm_unavailable_without_retry`, `test_missing_api_key_returns_clean_error_without_http_request` | Returns a clean 503; timeout is not retried and missing credentials cause no network request. |
| LLM returns 429 or 5xx | `test_429_retries_once_and_returns_success`, `test_repeated_429_returns_rate_limited_after_one_retry`, `test_500_retries_once_then_returns_llm_unavailable`, `test_5xx_retry_can_recover` | One retry is allowed; successful retry is reported, repeated 429 returns 429, and exhausted server errors return 503. Failed calls release their quota reservation. |
| LLM response is malformed or invalid JSON | `test_malformed_success_payload_returns_llm_unavailable`, `test_invalid_json_returns_llm_unavailable` | Invalid payloads are treated as unavailable and do not consume quota. |
| LLM request messages are empty or malformed | `test_invalid_messages_are_rejected_before_network` | Returns 422 before making a network request. |
| LLM returns an authentication error (401) | `test_other_client_error_maps_to_unavailable_without_retry` | Returns 503 without retrying; the provider's error body is not passed through. |
| Daily quota is exhausted, request arrives concurrently, or UTC day changes | `test_allows_exact_limit_then_rejects_without_increasing_count`, `test_concurrent_reservations_never_exceed_limit`, `test_new_utc_day_gets_a_separate_quota`, `test_uses_utc_date_instead_of_local_calendar_date` | Quota is atomic, uses UTC dates, and never exceeds the configured limit. |
| A failed request releases its reservation, or release is repeated | `test_releasing_failed_reservation_returns_quota_slot_idempotently` | The slot is returned once and can be reserved again. |
| Logs could expose tokens, query strings, or disagree with response usage | `test_successful_chat_log_matches_response_usage_and_hides_auth_token`, `test_llm_failure_logs_unknown_usage_without_credentials`, `test_non_chat_error_logs_defaults_and_one_json_line` | Logs omit credentials and query strings, include a request ID, and report usage/defaults consistently. |
| Qdrant collection has a different vector size or incomplete payload | `test_add_chunks_rejects_dimension_mismatch_with_existing_collection`, `test_search_rejects_incomplete_qdrant_payload` | Invalid collection data is rejected rather than misread. |
| Invalid vector lengths, empty vectors, or invalid access filters | `test_add_rejects_a_chunk_without_a_matching_embedding`, `test_add_rejects_embeddings_with_different_dimensions`, `test_search_rejects_empty_embedding`, `test_search_rejects_unknown_access_level` | Store rejects invalid inputs before search or upsert. |
| Local Qdrant is reopened after a process/client closes | `test_local_store_persists_data_between_clients` | Persisted local vectors remain searchable after reopening the client. |
| Vector upsert repeats a point, replaces a document, or deletes one document among others | `test_add_chunks_returns_count_and_readding_same_chunks_upserts`, `test_replace_document_chunks_removes_chunks_from_previous_version`, `test_replace_document_chunks_validates_before_deleting_existing_data`, `test_delete_by_doc_id_removes_only_that_documents_chunks` | Repeated point IDs upsert; replacement removes old chunks only after validation; document deletion leaves other documents intact. |
| SQLite receives a hostile title or invalid stored values | `test_hostile_title_is_stored_literally`, `test_database_rejects_bad_values_even_without_python_checks` | SQL values remain data, and database constraints reject invalid visibility/status values. |

## Other covered response and persistence boundaries

- An OpenRouter 200 response with missing choices/usage/content, negative token counts, boolean token counts, or invalid JSON maps to a clean 503 (`test_malformed_success_payload_returns_llm_unavailable`, `test_invalid_json_returns_llm_unavailable`).
- Refusal matching is exact: extra text around a refusal marker is not treated as the exact marker (`test_marker_with_extra_text_is_not_detected_as_refusal`).
- Prompt building rejects an empty question and unsupported language (`test_prompt_rejects_empty_question`, `test_prompt_rejects_unknown_language`).
- Feedback persists both supported ratings; a missing comment is stored as `NULL` (`test_feedback_persists_rating_and_optional_comment`, `test_feedback_allows_missing_comment`).
- Database health and vector-store health are checked independently; the health route reuses the app's vector-store instance (`test_health_is_degraded_when_database_is_unreachable`, `test_health_is_degraded_when_vector_store_is_unreachable`, `test_health_is_ok_and_reports_ready_document_count`).


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

## Issue #11: Conversation memory decisions

- Conversation memory is in-process and intentionally non-persistent.
- It is keyed by `conversation_id`.
- Each conversation keeps at most 4 recent questions.
- At most 1,000 conversations are retained.
- Retrieval queries are capped at 2,000 characters.
- Follow-up retrieval queries combine eligible previous questions with the current question.
- Previous assistant answers are not reused in retrieval or prompts yet.
- Members requests may reuse public and members questions from the same conversation.
- Public requests may reuse only public questions from the same conversation.
- A public request reusing a members conversation never receives members-only retrieval context.
- The vector store remains the final access-control boundary and always receives the current request access level.
- Conversations are evicted least-recently-used when the dictionary reaches its limit.
- Memory is cleared when the process restarts.
- Conversation history is not shared between processes or workers.
- Persistent conversation storage is intentionally deferred to a later issue.

## Coverage gaps (not claimed as verified)

- The CLI corpus loader behavior is documented above, but there is no named automated test for manifest filtering, continuing after one file fails, or its final exit code.
- Reclaiming a document left in `processing` after a process crash is implemented by `claim_document`, but there is no dedicated test for that recovery path.
- The unique content-hash constraint protects against cross-process duplicate claims, but the tests do not currently simulate two separate processes racing to claim the same hash.
- PDF OCR tests mock OCR and PDF extraction; they do not exercise a real corrupt PDF or missing system OCR executable/language data.
- The maximum upload test covers an oversized file; it does not test a file exactly at the configured limit or a missing/empty uploaded filename.
- Admin and member authentication tests do not explicitly cover behavior when their server-side secrets are unset, or every malformed bearer-header form.
- Feedback persistence errors, malformed multipart requests, and an inaccessible document registry on the list endpoint do not have dedicated tests.
