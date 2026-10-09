# SLIMANE

## FIRST DAY
- In a RAG system, “grounded” means anchoring the AI's response entirely to verified, retrievable source documents rather than letting it rely blindly on patterns learned during its training.
- How a Bot "Knows" It Doesn't Know:
   - Explicit Prompt Constraints (The "Guardrails") : When you type a question, the software invisibly wraps it in a strict system prompt before sending it to the LLM.
   - Vector Database Similarity Scores : Before the text ever reaches the LLM, the system converts your question into an embedding and compares it against your database of documents.

- Cosine similarity measures how similar two text embeddings are by calculating the cosine of the angle between them.
- A query–document language mismatch happens when a user types a search query in one language, but the indexed documents or search system retrieve results in a different language, causing embedding failure or poor semantic relevance.
- A similarity threshold in RAG is a numerical cutoff used to filter out low-relevance document chunks before sending them to the LLM.This saves quota and prevents hallucination.
- Why def and not async def for routes? (Blocking work such as embedding or parsing would freeze the event loop in an async def. FastAPI runs def in a thread pool.)
- Why secrets.compare_digest? (Constant-time comparison prevents timing attacks that guess a token character by character.)