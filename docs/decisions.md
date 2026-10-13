# Decisions

This file records technical choices, the evidence behind them, and known
limitations. Rules are documented with their timing so post-hoc decisions are
not presented as pre-registered rules.

---

## 1. Embedding model (issue #5)

### Why this decision matters

The embedding model converts document chunks and questions into vectors for
semantic search. It must support English, French, and Arabic, including
cross-language retrieval, run locally, and be free so it does not consume the
OpenRouter request budget.

Changing the model later requires re-embedding the corpus, so the choice is
recorded with measured quality, storage, speed, and truncation results.

### Candidates

| Model | Measured weights size | Dimension | Input limit | Prefix | License |
| --- | ---: | ---: | ---: | --- | --- |
| `intfloat/multilingual-e5-small` | 471 MB | 384 | 512 tokens | `query:` / `passage:` | MIT |
| `paraphrase-multilingual-MiniLM-L12-v2` | 471 MB | 384 | 128 tokens | None | Apache 2.0 |
| `BAAI/bge-m3` | 2.27 GB | 1024 | 8192 tokens | None | MIT |

### Evaluation set

The evaluation set contains 23 verified questions:

- 20 scored in-scope questions: 7 English, 7 French, and 6 Arabic.
- 3 out-of-scope questions: one in each language.

Out-of-scope questions are excluded from hit@3 and MRR. Their top-1
similarities are recorded as evidence for the refusal-threshold work in issue
#8.

### Evaluation rules

1. Every model receives the same chunks and questions.
2. E5 uses its documented `query:` and `passage:` prefixes. The other models
   use no prefix.
3. Vectors are normalized and ranked with cosine similarity.
4. Retrieval is evaluated at document level: the first chunk from the expected
   document determines the rank.
5. A hit@3 means the expected document appears within the first three ranked
   results.
6. Out-of-scope similarity values are not compared as if they were quality
   scores because each model has a different score scale.
7. Measurements use CPU execution and record corpus embedding time and warm
   per-question time.

The truncation disqualification rule was added after the initial candidate
comparison and before this final reproducibility run. It is disclosed here
instead of being treated as part of the original blind selection:

8. Disqualify a model if more than 25% of chunks exceed its input limit.

### Selection rule

Keep models whose overall hit@3 is within five percentage points of the best
model. Among the models that remain and pass the truncation filter, choose the
smallest model. Arabic quality remains a required check, not an optional
bonus.

### Final measured results

| Model | Hit@3 | Truncated chunks | Weights size | Per-question embedding | Corpus embedding |
| --- | ---: | ---: | ---: | ---: | ---: |
| `intfloat/multilingual-e5-small` | 19/20 | 0/30 | 471 MB | 22.7 ms | 2.1 s |
| `paraphrase-multilingual-MiniLM-L12-v2` | 20/20 | 17/30 | 471 MB | 24.6 ms | 1.3 s |
| `BAAI/bge-m3` | 20/20 | 0/30 | 2.27 GB | 183.9 ms | 40.1 s |

Model load times are intentionally excluded from the decision. E5 ran first
and measured 46.8 seconds because it paid the process-level PyTorch import
cost; MiniLM and bge-m3 measured 5.4 and 6.9 seconds after that import. Those
numbers are not comparable.

The measurements were reproduced across multiple runs: E5 produced the same
numbers three times, and MiniLM and bge-m3 produced the same numbers twice.

### Similarity and refusal-threshold evidence

The final run produced the following boundary measurements:

| Model | Lowest in-scope top-1 | Highest out-of-scope top-1 | Margin |
| --- | ---: | ---: | ---: |
| `intfloat/multilingual-e5-small` | 0.791 | 0.785 | +0.006 |
| `paraphrase-multilingual-MiniLM-L12-v2` | Not separated | Not separated | -0.034 |
| `BAAI/bge-m3` | Not listed in the run summary | Not listed in the run summary | +0.041 |

The exact per-question similarity values should remain in the evaluator output
or be copied into this table when that output is available. The values above
are the exact boundary values reported for this decision and are sufficient to
identify the known risk: E5 leaves almost no reliable cutoff margin.

### Failure analysis

- **q005:** English question, French expected document. The top three scores
  were within 0.005 of one another. The expected `about.md` document is a
  code of conduct and does not state who can join, so this is likely a
  weakness in semantic discrimination and/or corpus coverage rather than a
  simple language mismatch. This question should be reviewed before treating
  the result as a model failure.

### Decision

- **Chosen model:** `intfloat/multilingual-e5-small`
- **Prefixes:** `query: ` for questions and `passage: ` for document chunks
- **Reason:** E5 has no truncated chunks, is tied for the smallest measured
  weights size, embeds the corpus far faster than bge-m3, and its hit@3 score
  is exactly five percentage points below the best score. Under the stated
  selection rule, E5 is retained and chosen as the smaller model.
- **Rejected model:** MiniLM is disqualified because 17/30 chunks (57%) exceed
  its 128-token limit, above the 25% maximum.
- **Not chosen:** bge-m3 passes the quality and truncation filters and has a
  stronger refusal margin, but requires 2.27 GB of weights and took 40.1
  seconds to embed 30 chunks. At that rate, embedding a 10-chunk upload would
  take about 13 seconds before any other ingestion work.

### Known risk and follow-up

E5's refusal margin is only **+0.006**: its lowest in-scope top-1 score is
0.791 and its highest out-of-scope score is 0.785. This estimate is based on
only one in-scope boundary case and three out-of-scope questions, so it is a
warning, not proof that a threshold will fail.

Issue #8 should test at least 10 out-of-scope questions. If E5 continues to
show a near-zero margin, the honest options are:

1. switch to bge-m3 and accept the larger memory use and slower re-embedding;
2. keep E5 but avoid relying on a similarity cutoff, using retrieval quality
   and the prompt's explicit “I don't know” behavior for borderline cases.

Any reopening of this decision must be recorded here with the new evidence.

### Limitations

- Only 20 questions were scored, so small differences may be noise.
- Only three out-of-scope questions were used for the refusal-margin warning.
- The question set contains few paraphrases and no deliberately confusable
  document pairs.
- Only three embedding models were compared.
- Chunk size was not varied in this experiment.
- Speed was measured on one CPU machine, not the deployment host.
- The E5 decision is exactly on the five-percentage-point quality boundary.
