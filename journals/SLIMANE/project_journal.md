# Slimane's Project Journal

## Day 1

- A grounded answer uses information found in our documents. The bot should not make up an answer when it cannot find one.
- Before answering, the app can search the document database for useful passages. If the results are not relevant enough, the bot should say it does not know.
- Cosine similarity is one way to compare text embeddings and see how close their meanings are.
- Search can work poorly when the question and the documents use different languages. We should keep this in mind because the bot needs to support Arabic, French, and English.
- A similarity threshold sets a minimum score for search results. It can help keep unrelated passages out of the answer.
- Some FastAPI routes use `def` because parsing and embedding can take time. FastAPI runs those routes in a thread pool so they do not block the main event loop.
- `secrets.compare_digest` compares secret tokens in a way that makes it harder to guess them by timing the checks.
