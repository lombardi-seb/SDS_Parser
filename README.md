# SDS Parser
This project provides an interface to analyze SDS (Safety Data Sheets) PDFs, extract GHS-related hazard codes and pictograms, and submit the resulting data to the CISPro inventory system.

The tool includes: 
 - PDF parsing (with OCR fallback if needed)
 - Extraction of H-codes, pictograms, and signal words
 - Generation of a secondary JSON with PPE (Personal Protective Equipment) recommendations, Physical state, flash point, boiling point and Storage & Handling
 - A Gradio web interface for interaction - Batch processing mode

## Features
 - Extracts hazard classification data from SDS PDFs stored in Oracle (CISPro DB)
 - LLM call via OpenRouter to extract some data
 - Builds two JSON files: main SDS data + additional data (PPE, hazardous, ...)
 - Uploads both to CISPro via REST API
 - Supports batch mode (process multiple material IDs)
 - User-friendly interface using Gradio

## Project structure
 - SDS_functions.py              # Core logic: parsing, database, API, LLM call
 - gradio_callbacks.py      # Functions directly called by the Gradio UI
 - SDS parser gradio.ipynb  # Jupyter Notebook with the Gradio interface
 - config.py                # Configuration (DB/API credentials)
 - ghscode_10.txt      # Mapping of H-codes to pictograms and other metadata
 - models.txt               # List of models from OpenRouter. The 1st one is the default model
 - batch_runner.py          # Python script to use the tool in batch mode
 - README.md                # This file 

## Requirements
 - Python 3.9+
 - Oracle DB access
 - Packages : gradio, requests, json, fitz, pytesseract, PIL, chardet, oracledb, pandas
 - Tesseract OCR installed and configured in config.py (tesseract-ocr-w32-setup-5.3.0.20221222.exe)

## How to use - single mode through Gradio
1. Launch the Jupyter Notebook
2. Open SDS_parser_gradio.ipynb
3. Run all cells to launch the interface
4. From the UI:
   - Analyze a single material ID or a batch
   - Inspect the JSON output
   - Submit the results to CISPro

## How to use - batch mode
1. Create a text file ids.txt containing the list of reagents ids (Z-number)
2. Open a command window in the folder with python files
3. Run the command : >python batch_runner.py ids.txt [modelname]
4. The modelname is optional. If empty, the script will not use any LLM.
   Example with model kimi-k2: >python batch_runner.py ids.txt moonshotai/kimi-k2-0905
5. The script will ask the CISPro login & password, and then it will process all reagents ids from the text file.

## License
