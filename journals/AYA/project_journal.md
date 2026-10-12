# AYA's Project Journal

## Day 1

I started working on how the chatbot reads its documents. I added a parser in `app/ingestion/parsers.py` for Markdown, PDF, and DOCX files.

The parser gives each file a title from its filename and extracts its text. It reports a clear error if a file is empty, broken, unreadable, or in a format we do not support.

I added `pypdf` and `python-docx` to `requirements.txt` so the app can read PDF and DOCX files. I also added `tests/test_parsers.py` to check the parsers with normal files and a few problem cases.

I added `.vscode/` to `.gitignore` and moved the team journals into separate folders. Slimane's notes are now in `journals/SLIMANE/`, and mine are in `journals/AYA/`.

### Next

Next, I will add a parser for web pages. I will also handle PDFs made up of images, where the text cannot be copied or extracted directly.

I have not run the tests yet, so I still need to check that they pass. I should also check whether our documents include password-protected PDFs or tables in DOCX files.
