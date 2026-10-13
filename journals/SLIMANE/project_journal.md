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

## THIRD DAY 
-The sqlite3 module comes built-in with Python, meaning you do not need to run a pip install command to use it. It provides a lightweight, serverless SQL database engine that reads and writes directly to a file on your disk.

## FOURTH DAY

- RAG pipeline:
1- Document ingestion:
    - Step 1: Upload a document :The endpoint accepts an uploaded file and a processor type
    - Step 2: Validate and read the File : Conceptually, the system should extract text from each page.
    - Step 3: Create metadata: Metadata is information about the document, rather than the document content itself.
    -Step 4: Split documents into chunks : Large documents should not normally be sent to the language model as one huge block.They are split into smaller pieces called chunks.
    -Step 5: Convert each chunk into an embedding :The embedding model converts the text into a numerical vector.
    -Step 6: Store the chunk in ChromaDB
    Step 7: Question answering: how a query moves through the system

2- Question answering: how a query moves through the system:
    - Step 1: Sub-query expansion :The first step is to expand the user’s question into multiple related questions.
    -Step 2: Retrieve documents from ChromaDB: The system then searches ChromaDB once for every sub-query.
        For each query, ChromaDB:



            1. Converts the query into an embedding.

            2. Compares it against stored document embeddings.

            3. Finds the closest chunks.

            4. Returns the top matching chunks.

    -Step 3: Cross-encoder reranking: after retrieval, the system may have many candidate chunks.The candidates are then sorted from highest score to lowest score,Only the top five are retained
    -Step 4: Build the context for the language model, the selected documents become the context for the final answer.
    - Step 5: Generate the final answer the answer-generation workflow is intended to be handled by a LangGraph agent

During ingestion: 
    PDF uploaded
    ↓
    PDF text extracted
    ↓
    Text split into chunks
    ↓
    Chunk converted to embedding
    ↓
    Chunk + embedding + metadata saved in ChromaDB


the repo apraoch (khiro)
    Question
    ↓
    Multiple related queries
    ↓
    Multiple searches
    ↓
    Candidate pooling
    ↓
    Cross-encoder reranking
    ↓
    LLM generation

    Ingest:
    Document -> extract -> chunk -> embed -> store

    Query:
    Question -> expand -> retrieve -> rerank -> generate


- A suitable target architecture would be:
    Admin upload
        ↓
    Hash file
        ↓
    Reject or reuse duplicate
        ↓
    Parse Markdown/PDF/DOCX
        ↓
    Normalize and chunk
        ↓
    Attach doc_id + visibility + title + chunk_index
        ↓
    Create multilingual embeddings
        ↓
    Store in vector database
        ↓
    Mark document ready


    User request
        ↓
    Authenticate as public/member
        ↓
    Resolve conversation context
        ↓
    Create one search query
        ↓
    Filter by visibility during retrieval
        ↓
    Vector search
        ↓
    Optional local cross-encoder reranking
        ↓
    Apply relevance threshold
        ↓
    If no useful results: return grounded=false
        ↓
    One OpenRouter LLM call
        ↓
    Return answer + sources + usage + latency