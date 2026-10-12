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

### Next ? 

