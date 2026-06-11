# SDS Parser 🧪
### Automated Safety Data Sheet Analysis & GHS Data Extraction

---

## Overview

**SDS Parser** is a Python tool for automated extraction and classification of chemical hazard data from Safety Data Sheet (SDS) documents. Given a material identifier (Z-number), the tool retrieves the corresponding SDS PDF from an Oracle database, extracts GHS-compliant hazard information, and uploads the structured output directly to a **CISPro** chemical inventory system via REST API.

The tool supports two usage modes:
- **Interactive mode** — a Gradio web interface embedded in a Jupyter Notebook for single or batch analysis
- **Batch mode** — a CLI script for unattended processing of large lists of reagents

---

## Features

- 📄 **PDF text extraction** — uses PyMuPDF (`fitz`) for fast text parsing of digital SDS PDFs
- 🔍 **OCR fallback** — automatically switches to Tesseract OCR when no extractable text layer is found (scanned PDFs)
- ⚠️ **GHS hazard extraction** — identifies H-codes, GHS pictograms, and signal words using a curated reference dictionary (`ghscode_10.txt`) covering the full UN GHS standard
- 🤖 **LLM-assisted extraction** — calls an LLM via [OpenRouter](https://openrouter.ai/) to extract physicochemical properties (flash point, boiling point, physical state) and storage & handling instructions
- 📦 **Dual JSON output** — generates two structured payloads:
  - **Main JSON** — GHS hazard classification data (H-codes, pictograms, signal word)
  - **Additional JSON** — PPE recommendations, physicochemical data, storage & handling conditions
- 🔗 **CISPro integration** — uploads both JSONs to CISPro (Biovia) via authenticated REST API
- 📋 **Batch processing** — processes a list of material IDs from a text file, with per-reagent JSON backup and full run logging
- 🖥️ **Gradio UI** — user-friendly web interface for interactive analysis without writing any code

---

## Tech Stack

| Component | Technology |
|---|---|
| PDF text extraction | [PyMuPDF](https://pymupdf.readthedocs.io/) (`fitz`) |
| OCR fallback | [Tesseract OCR](https://github.com/tesseract-ocr/tesseract) + [pytesseract](https://github.com/madmaze/pytesseract) |
| Database | Oracle DB via [python-oracledb](https://python-oracledb.readthedocs.io/) |
| LLM calls | [OpenRouter API](https://openrouter.ai/) (configurable model) |
| Web interface | [Gradio](https://www.gradio.app/) |
| Chemical inventory | CISPro (Biovia) REST API |
| Data handling | pandas, chardet |
| Language | Python 3.9+ |

---

## Project Structure

```
SDS_Parser/
├── SDS_functions.py            # Core logic: DB access, PDF parsing, OCR, H-code extraction, LLM calls, API upload
├── gradio_callbacks.py         # UI callback functions wired to the Gradio interface
├── SDS_parser_gradio.ipynb     # Jupyter Notebook — launch this to use the interactive UI
├── batch_runner.py             # CLI script for unattended batch processing
├── config.py                   # Configuration: DB credentials, API endpoints, Tesseract path, OpenRouter key
├── ghscode_10.txt              # Reference TSV: H-codes → GHS categories, pictograms, signal words, P-codes
├── models.txt                  # List of OpenRouter-compatible LLM models (first line = default)
└── README.md
```

---

## How It Works

```
Material ID (Z-number)
        │
        ▼
 ┌─────────────────────────┐
 │  Oracle DB              │  Retrieve SDS PDF blob by Z-number → node ID
 └──────────┬──────────────┘
            │
            ▼
 ┌─────────────────────────┐
 │  PDF Parsing            │  PyMuPDF text extraction
 └──────────┬──────────────┘
            │
     Text found?
      ├─ NO ───────────────►  ┌──────────────────────────┐
      │                       │  OCR (Tesseract)          │
      │                       └──────────────┬───────────┘
      └─ YES ◄────────────────────────────────┘
            │
            ▼
 ┌─────────────────────────┐
 │  H-Code Extraction      │  Match against ghscode_10.txt
 │                         │  → H-codes, pictograms, signal word
 └──────────┬──────────────┘
            │
            ├──────────────────────────────────────────►
            │                               ┌───────────────────────────────┐
            │                               │  LLM call (OpenRouter)        │
            │                               │  → Flash point, boiling point,│
            │                               │  physical state, PPE,         │
            │                               │  storage & handling           │
            │                               └──────────────┬────────────────┘
            │                                              │
            ▼                                              ▼
 ┌─────────────────────┐              ┌────────────────────────────────┐
 │  Main JSON          │              │  Additional JSON                │
 │  (GHS hazard data)  │              │  (physicochemical + PPE data)   │
 └────────┬────────────┘              └────────────────┬───────────────┘
          │                                            │
          └───────────────────┬────────────────────────┘
                              │
                              ▼
                    ┌─────────────────────┐
                    │  CISPro REST API    │  POST both JSONs to the chemical
                    │  upload             │  inventory system
                    └─────────────────────┘
```

---

## Configuration

Edit `config.py` before running:

```python
# Oracle Database
DB_USERNAME = 'your_username'
DB_PASSWORD = 'your_password'
DB_HOST     = 'your_oracle_host'
DB_PORT     = '1521'
DB_SERVICE  = 'your_service_name'

# Tesseract OCR (Windows path example)
TESSERACT_PATH = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

# OpenRouter (LLM API)
OPENROUTER_API_KEY = "sk-or-v1-..."

# CISPro API endpoints
LOGIN_URL           = "https://your-cispro-host/foundation/hub/api/v1/security/login"
LOGOUT_URL          = "https://your-cispro-host/foundation/hub/api/v1/security/logout"
UPLOAD_URL          = "https://your-cispro-host/cispro/inventory/api/v1/ghs"
UPLOAD_ADDITIONAL_URL = "https://your-cispro-host/cispro/inventory/api/v1/chemicals"
```

To switch the LLM model, either edit `models.txt` (the first line is the default) or pass a model name directly on the CLI. Available free models are listed in `models.txt`.

---

## Getting Started

### Prerequisites

- Python 3.9+
- Oracle DB client libraries
- [Tesseract OCR](https://github.com/UB-Mannheim/tesseract/wiki) installed and its path set in `config.py`
- Access to CISPro and an OpenRouter API key

### Installation

```bash
git clone https://github.com/lombardi-seb/SDS_Parser.git
cd SDS_Parser

pip install gradio requests fitz pytesseract pillow chardet oracledb pandas
```

---

## Usage

### Interactive mode (Gradio UI)

1. Open `SDS_parser_gradio.ipynb` in Jupyter
2. Run all cells — a Gradio web interface will launch in your browser
3. From the UI, enter a material ID (Z-number) and click **Analyze**
4. Inspect the JSON output and submit to CISPro with a click

### Batch mode (CLI)

```bash
# Create a text file with one Z-number per line
echo -e "Z12345\nZ67890\nZ11111" > ids.txt

# Run without LLM (H-code extraction only)
python batch_runner.py ids.txt

# Run with a specific LLM model for additional data extraction
python batch_runner.py ids.txt moonshotai/kimi-k2-0905
```

**Output** — for each run, a timestamped `logs_<YYYYMMDDHHMM>/` folder is created containing:
- `<material_id>.json` — main GHS JSON (local backup)
- `<material_id>_additional.json` — additional data JSON (if LLM is enabled)
- `batch_processing.log` — full run log with timestamps and status for each reagent

---

## GHS Reference Dictionary

`ghscode_10.txt` is a tab-separated file covering the full GHS hazard statement catalogue. For each H-code it maps:

| Column | Description |
|---|---|
| H-Code | e.g. `H301` |
| Hazard Statement | e.g. *Toxic if swallowed* |
| GHS Hazard Class | e.g. *Acute toxicity, oral* |
| GHS Hazard Category | e.g. *Category 3* |
| GHS Pictogram | e.g. `GHS06` |
| GHS Signal Word | `Danger` / `Warning` |
| P-Code(s) | Associated precautionary statements |
| CISPro classification | Internal CISPro label |

---

## Key Functions (`SDS_functions.py`)

| Function | Description |
|---|---|
| `connect_to_CISPro_api(user, pwd)` | Authenticate to CISPro, return bearer token |
| `get_oracle_connection()` | Open Oracle DB connection |
| `get_pdf_blob_from_db(conn, nodeid)` | Fetch SDS PDF binary from Oracle |
| `perform_ocr_on_pdf(pdf_bytes)` | Run Tesseract OCR on a PDF as fallback |
| `search_h_codes_in_pdf(text, dict, nodeid)` | Match H-codes and build main JSON |
| `analyser_material_id(mid, dict)` | End-to-end analysis for one material |
| `build_additional_json(result, text, model, key)` | LLM-based additional data extraction |
| `envoyer_json(user, pwd, json)` | POST main JSON to CISPro GHS endpoint |
| `send_additional_json(user, pwd, json)` | POST additional JSON to CISPro chemicals endpoint |

---

## Notes & Limitations

- **Windows only** (as configured) — Tesseract path in `config.py` is a Windows path; adapt for Linux/macOS if needed
- **Oracle dependency** — requires access to the Oracle database where SDS PDFs are stored as BLOBs
- **OCR quality** — extraction accuracy on scanned PDFs depends on scan resolution and document quality
- **LLM availability** — free models on OpenRouter may have rate limits or variable availability; results may vary by model
- **No medical/safety advice** — this tool is for data processing only; always consult the original SDS for safety decisions

---

## License

Internal tool — please check with the project owner before reuse or redistribution.
