import re
import csv
import logging
import requests
import json
from io import BytesIO
import fitz
import pytesseract
from PIL import Image
import chardet
import oracledb
from config import (
    DB_USERNAME, DB_PASSWORD, DB_HOST, DB_PORT, DB_SERVICE,
    LOGIN_URL, LOGOUT_URL, DELETE_URL, UPLOAD_URL, UPLOAD_ADDITIONAL_URL, TSV_PATH, TESSERACT_PATH
)


pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH

# Global variable temporary
LAST_RESULT_JSON = None
CISPRO_TOKEN = None

"""
    List of functions

    connect_to_CISPro_api(username, password):
    disconnect_from_CISPro_API():

    get_oracle_connection():
    get_nodeid_from_material_id(connection, znumber):
    get_pdf_blob_from_db(connection, nodeid):

    perform_ocr_on_pdf(pdf_bytes):
    read_tsv_file(tsv_path):
    expand_hcodes(hcode_str):
    search_h_codes_in_pdf(text, h_codes_dict, nodeid):

    analyser_material_id(material_id, h_codes_dict):
    envoyer_json(username, password, json_data):

    build_additional_json(result_json, full_text=None, model_name=None, api_key=None):
    send_additional_json(username, password, additional_json):

    extract_physicochemical_properties_via_llm(text: str, model_name: str, api_key: str):
    extract_storage_and_handling_via_llm(text: str, model_name: str, api_key: str):
"""

def connect_to_CISPro_api(username, password):
    """
    Login to CISPro API and return bearer token
    
    Args:
        username (str): username CISPro
        password (str): password CISPro
    
    Returns:
        str: Bearer token if success
        None: if failed
    
    Raises:
        Exception: if connection error
    """
    global CISPRO_TOKEN
    
    login_data = {
        'client_id': 'foundation-hub',
        'username': username,
        'password': password
    }
    
    try:
        logging.info(f"🔐 Try to login to CISPro: {username}")
        login_response = requests.post(LOGIN_URL, json=login_data, verify=False)
        
        if login_response.status_code != 200:
            error_msg = f"API connection failed: {login_response.status_code} - {login_response.text}"
            logging.error(error_msg)
            raise Exception(error_msg)
        
        CISPRO_TOKEN = login_response.json().get('access_token')
        if not CISPRO_TOKEN:
            raise Exception(
            f"Bearer token not found in API response"
            f"Response: {login_response.text}"
        )
        
        logging.info("✅ Connection successful, token found")
        return CISPRO_TOKEN
        
    except Exception as e:
        logging.error(f"❌ Error during the connection : {e}")
        raise

def disconnect_from_CISPro_API():
    """
    logout the user from CISPro.

    Args:
        delete_url (str): endpoint URL of deleting session
    """
    global CISPRO_TOKEN

    if CISPRO_TOKEN:
        headers = {"Authorization": f"Bearer {CISPRO_TOKEN}"}
        try:
            response = requests.delete(DELETE_URL, headers=headers, verify=False)
            response.raise_for_status()
            logging.info("logout successful.")
        except requests.exceptions.RequestException as e:
            logging.error(f"Logout failed: {e}")
        finally:
            CISPRO_TOKEN = None
    else:
        logging.warning("No token found. Already disconnected ?")

# Oracle connection
def get_oracle_connection():
    return oracledb.connect(
        user=DB_USERNAME,
        password=DB_PASSWORD,
        dsn=f"{DB_HOST}:{DB_PORT}/{DB_SERVICE}"
    )

# Get nodeid
def get_nodeid_from_material_id(connection, znumber):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT NODEID FROM CISPRO.CHEMICAL WHERE MATERIALID = :Znumber",
            {'Znumber': znumber}
        )
        row = cursor.fetchone()
        if not row:
            raise ValueError("Material ID not found.")
        return int(row[0])
        
# Get PDF file from DB
def get_pdf_blob_from_db(connection, nodeid):
    """
    Get the BLOB PDF content from Id
    """
    nodeid = int(nodeid)
    
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT 
                filename, blobdata 
            FROM 
                CISPRO.BLOB_DATA bd 
                JOIN cispro.SDSDOCUMENT s ON s.FILE1_BLOBID = bd.BLOBDATAID 
            WHERE 
                s.OWNER_ID = :nodeid AND s.ARCHIVED = 'N' AND ROWNUM = 1
            ORDER BY 
                s.DATECREATED DESC""", {'nodeid': nodeid})
        row = cursor.fetchone()
        if row:
            filename, blob_bytes = row[0], row[1].read()
            return filename, blob_bytes
        else:
            raise ValueError("PDF not found for nodeid =", nodeid)

def perform_ocr_on_pdf(pdf_bytes):
    pdf_file = BytesIO(pdf_bytes)
    doc = fitz.open(stream=pdf_file, filetype="pdf")
    
    full_text = ""
    for page in doc:
        # Convertir la page en image (pixmap)
        pix = page.get_pixmap(dpi=300)
        img = Image.open(BytesIO(pix.tobytes("png")))

        # OCR via pytesseract
        text = pytesseract.image_to_string(img, lang="eng")
        full_text += text + "\n"
    
    doc.close()
    return full_text

# Function to read H-codes and their corresponding values from a TSV file
def read_tsv_file(tsv_path):
    h_codes_dict = {}
    with open(tsv_path, mode='rb') as file:
        result = chardet.detect(file.read())
            
    with open(tsv_path, mode='r', encoding=result['encoding']) as tsv_file:
        #tsv_reader = csv.reader(tsv_file, delimiter='\t')
        tsv_reader = csv.DictReader(tsv_file, delimiter='\t')
        for row in tsv_reader:
            if row and row['H-Code'].startswith('H') and len(row) > 1:  # Ensure the row is not empty
                h_codes_dict[row['H-Code']] = {
                    'pictogram': row['CISPro pictogram'], 
                    'classification': row['CISPro classification'],
                    'signalWord_id': row['CISPro signal word Id'],
                    'GHS07_not_skin_eye' : row['CISPRO_exclamation_not_skin_eye_irritation'],
                    'P-Code': row.get('P-Code', '')
                }
    return h_codes_dict

# Function to re-write correctly the H code. For example, H302+312+332 => H302+H312+H332
def expand_hcodes(hcode_str):
    parts = hcode_str.split('+')
    return '+'.join([p if p.startswith('H') else 'H' + p for p in parts])

# Function to search for H-codes in a PDF file
def search_h_codes_in_pdf(text, h_codes_dict, nodeid):
    found_h_codes = {
        "labelCodes": "", "pictograms": "", "classifications" : "", "signalWord_id" : "", "jurisdiction_id": "", "material_id": "", "nodetypename": ""
    }
    h_codes_set = set()
    pictograms_set = set()
    classifications_set = set()
    signalwords_set = set()
    has_exclamation_not_skin_eye_irritation = False
    p_codes_set = set()

    # Minimal normalization
    normalized_text = re.sub(r'\s*\+\s*', '+', text)
    # Exemple de texte
    #normalized_text = """Le produit est classé : H302+312+332, H360F, H361fd, H319, H999, H302+999"""
    
    # All H-codes in the text
    #hcode_matches = re.findall(r'\bH\d{3}(?:\+(?:H)?\d{3})*\b', normalized_text)
    hcode_matches = re.findall(r'\bH\d{3}[a-zA-Z]{0,2}(?:\+(?:H)?\d{3}[a-zA-Z]{0,2})*\b', normalized_text)
    
    hcode_matches_canonized = [expand_hcodes(c) for c in hcode_matches]
    
    # To avoid duplicates
    found_hcode_set = set()

    for match in hcode_matches_canonized:
        if match in h_codes_dict and match not in found_hcode_set:
            found_hcode_set.add(match)
            h_codes_set.add(match)
            pictograms_set.add(h_codes_dict[match]['pictogram'])
            classifications_set.add(h_codes_dict[match]['classification'])
            signalwords_set.add(h_codes_dict[match]['signalWord_id'])
            if h_codes_dict[match].get('GHS07_not_skin_eye') == 'TRUE':
                has_exclamation_not_skin_eye_irritation = True
            pcode_raw = h_codes_dict[match].get('P-Code', '')
            if pcode_raw:
                for p in pcode_raw.split(','):
                    cleaned = p.strip()
                    if cleaned:
                        p_codes_set.add(cleaned)


    # No valid H-code found : return an 'empty' JSON to create a Jurisdiction without any H-code
    if not h_codes_set:
        return {
            "signalWord_id": 332028,
            "jurisdiction_id": 31745,
            "material_id": int(nodeid),
            "nodetypename": "GHS"
         }
       

    # Rule for Signal Word
    # Define priority order for signalWord_id
    priority_order = ['41941', '41942', '327286', '332028']

    # Find the highest priority signalWord_id
    selected_signal_word_id = None
    for priority_id in priority_order:
        if priority_id in signalwords_set:
            selected_signal_word_id = priority_id
            break

    # Rules for pictograms
    # Rule 1 : if the skull and crossbones applies, the exclamation mark should not appear
    if 'Acute Toxicity (severe)' in pictograms_set and 'Irritant' in pictograms_set:
        pictograms_set.discard('Irritant')
        logging.info("Rule 1 applied: GHS07 removed due to GHS06 (skull and crossbones)")

    # Rule 2 : if the corrosive symbol applies, the exclamation mark should not appear where it is used for skin or eye irritation
    if 'Corrosive' in pictograms_set and 'Irritant' in pictograms_set and has_exclamation_not_skin_eye_irritation is not True:
        pictograms_set.discard('Irritant')
        logging.info("Rule 2 applied: GHS07 - only skin or eye irritation - removed due to GHS05")       

    # Rule 3 : if the health hazard symbol appears for respiratory sensitization, 
    # the exclamation mark should not appear where it is used for skin or for skin or eye irritation
    if 'Target Organ Toxicity' in pictograms_set and 'Irritant' in pictograms_set and has_exclamation_not_skin_eye_irritation is not True:
        pictograms_set.discard('Irritant')
        logging.info("Rule 3 applied: GHS07 - only skin or eye irritation - removed due to GHS08")       
        
    # Convert sets to comma-separated strings and construct JSON
    found_h_codes = {
        "labelCodes": ",".join(sorted(h_codes_set.union(p_codes_set))),
        "pictograms": ",".join(filter(None, pictograms_set)),  # Filter out empty strings
        "classifications": ",".join(classifications_set),
        "signalWord_id": int(selected_signal_word_id),
        "jurisdiction_id": 31745,
        "material_id": int(nodeid),
        "nodetypename": "GHS"
     }
   
    return found_h_codes


# Main function of analyze
def analyser_material_id(material_id, h_codes_dict):
    if not re.match(r'^Z\d{7}$', material_id):
        return "❌ Invalid format of Material ID (Z & 7 numbers)"

    try:
        conn = get_oracle_connection()
        nodeid = get_nodeid_from_material_id(conn, material_id)

        # PDF from DB
        filename, pdf_bytes = get_pdf_blob_from_db(conn, nodeid)
        doc = fitz.open(stream=BytesIO(pdf_bytes), filetype="pdf")
        has_text = any(page.get_text().strip() for page in doc)
        doc.close()

        if has_text:
            full_text = "\n".join(page.get_text() for page in fitz.open(stream=BytesIO(pdf_bytes), filetype="pdf"))
        else:
            full_text = perform_ocr_on_pdf(pdf_bytes)

        # Searching of H-Codes
        full_text_upper = full_text.upper()
        result = search_h_codes_in_pdf(full_text_upper, h_codes_dict, nodeid)

        # Temporary save (memory only)
        global LAST_RESULT_JSON
        LAST_RESULT_JSON = result

        return json.dumps(result, indent=4), full_text
    
    except Exception as e:
        return None, f"Error : {e}"

# Function Send to API
def envoyer_json(username, password, json_data):
    global LAST_RESULT_JSON
    if LAST_RESULT_JSON is None:
        return "Nothing to send. Please first analyze a file."

    global CISPRO_TOKEN
    
    # When using the Gradio UI, the login is not yet done at this step
    if not CISPRO_TOKEN:
        CISPRO_TOKEN = connect_to_CISPro_api(username, password)
    
    # If not yet logged in, there is an issue
    if not CISPRO_TOKEN:
        raise Exception("Login failed.")
        sys.exit(1)
        
    headers = {
        'Authorization': f'Bearer {CISPRO_TOKEN}',
        'Content-Type': 'application/json'
    }
    
    try:
        # Post
        upload_response = requests.post(UPLOAD_URL, json=LAST_RESULT_JSON, headers=headers, verify=False)
        if upload_response.status_code in [200, 201]:
            return "✅ Success. SDS data is saved in CISPro."
        else:
            return f"❌ Error : {upload_response.status_code} - {upload_response.text}"
    
    except Exception as e:
        return f"Exception during POST : {e}"

def build_additional_json(result_json, full_text=None, model_name=None, api_key=None):
    """
    Create the secondary JSON for Additional information
    """
    if result_json is None:
        logging.error("⚠️ result_json is None")
        return None
    
    pictograms = result_json.get("pictograms", "")
    nodeid = result_json.get("material_id")
    labelCodes = result_json.get("labelCodes", "")

    # Hazardous is True if labelCodes is not null
    hazardous = bool(labelCodes.strip())

    # PPE
    if "Corrosive" in pictograms.split(","):
        ppe = "Face Shield,Goggles,Gloves,Fume Hood,Lab Coat"
    else:
        ppe = "Goggles,Gloves,Fume Hood,Lab Coat"

    # Default values
    physical_state = boiling_point = flash_point = storage_and_handling = None

    if full_text and model_name and api_key:
        # LLM call to extract physicochemical properties data
        logging.info("✅ Starting physicochemical properties LLM call...")
        llm_output = extract_physicochemical_properties_via_llm(full_text, model_name, api_key)
        logging.info("📄 LLM physicochemical properties output received:")
        logging.info(llm_output[:500])  # Limite à 500 caractères pour ne pas inonder la console
        
        match = re.search(r"### FINAL ANSWER ###\s*(.+)", llm_output, re.DOTALL)
        if not match:
            logging.error("❌ FINAL ANSWER section not found in LLM output")
            return {
                "nodeid": nodeid,
                "hazardous": hazardous,
                "ppe": ppe
            }
        else:
            final_answer = match.group(1).strip()
            logging.info("✅ FINAL ANSWER section extracted:")
            logging.info(final_answer)
            
            try:
                for line in final_answer.splitlines():
                    logging.info(f"🔹 Processing line: {line}")
                    if line.lower().startswith("physical state"):
                        value = line.split(":", 1)[-1].strip().lower()
                        physical_state = None if value in ["null", "no data available"] else value
                    elif line.lower().startswith("boiling point"):
                        value = line.split(":", 1)[-1].strip().lower()
                        boiling_point = None if value in ["null", "no data available"] else value
                    elif line.lower().startswith("flash point"):
                        value = line.split(":", 1)[-1].strip().lower()
                        flash_point = None if value in ["null", "no data available"] else value
            except Exception as e:
                logging.info(f"⚠️ Error parsing LLM physicochemical properties output: {e}")
            
        # LLM call to extract Storage and Handling data
        logging.info("✅ Starting storage and handling LLM call...")
        llm_output = extract_storage_and_handling_via_llm(full_text, model_name, api_key)
        logging.info("📄 LLM storage and handling output received:")
        logging.info(llm_output[:500])  # Limite à 500 caractères pour ne pas inonder la console
        
        match = re.search(r"### FINAL ANSWER ###\s*(.+)", llm_output, re.DOTALL)
        if not match:
            logging.error("❌ FINAL ANSWER section not found in LLM output")
            return {
                "nodeid": nodeid,
                "hazardous": hazardous,
                "ppe": ppe
            }
        else:
            final_answer = match.group(1).strip()
            logging.info("✅ FINAL ANSWER section extracted:")
            logging.info(final_answer)
            
            try:
                storage_and_handling = None if final_answer in ["null", "no data available"] else final_answer
            except Exception as e:
                logging.info(f"⚠️ Error parsing LLM storage and handling output: {e}")
                
        logging.info("Return full json.")
        return {
            "nodeid": nodeid,
            "hazardous": hazardous,
            "ppe": ppe,
            "physicalState": physical_state,
            "boilingPoint": boiling_point,
            "flashPoint": flash_point,
            "storageAndHandling": storage_and_handling
        }
        
    logging.info("Return short json.")
    return {
        "nodeid": nodeid,
        "hazardous": hazardous,
        "ppe": ppe
   }


def send_additional_json(username, password, additional_json):
    if additional_json is None:
        return "Nothing to send. Please analyze a file first."
    
    try:
        # Parse la chaîne JSON en dictionnaire Python
        additional_json_dict = json.loads(additional_json)
    except json.JSONDecodeError:
        return "Invalid JSON format in additional data."

    global CISPRO_TOKEN
    
    # When using the Gradio UI, the login is not yet done at this step
    if not CISPRO_TOKEN:
        CISPRO_TOKEN = connect_to_CISPro_api(username, password)
    
    # If not yet logged in, there is an issue
    if not CISPRO_TOKEN:
        raise Exception("Login failed.")
        sys.exit(1)
            
    upload_url = f"{UPLOAD_ADDITIONAL_URL}/{additional_json_dict['nodeid']}"
    headers = {
        'Authorization': f'Bearer {CISPRO_TOKEN}',
        'Content-Type': 'application/json'
    }
    
    try:
        upload_response = requests.put(upload_url, json=additional_json_dict, headers=headers, verify=False)
        logging.info(f"LOG --- upload_response: {upload_response}")
        
        if upload_response.status_code in [200, 201, 202]:
            return f"✅ Additional data successfully sent for node {additional_json_dict['nodeid']}."
        else:
            return f"❌ Error sending PPE data: {upload_response.status_code} - {upload_response.text}"
        
    except Exception as e:
        return f"Exception during PUT: {e}"


# Chat with LLM on OpenRouter
def extract_physicochemical_properties_via_llm(text: str, model_name: str, api_key: str):
    prompt = f"""
Here is a safety data sheet SDS: {text}

Please analyze the document and locate section 9 (Physical and Chemical Properties).
Then extract only the following properties:
- Physical state
- Boiling point
- Flash point
Important rule for extraction : for Physical state, the value must be strictly one of the following : solid, liquid or gas.
If the document indicates something equivalent (e.g. "powder", "aqueous solution", "vapour"), you must map it to the closest category (powder → solid, aqueous solution → liquid, vapour → gas).
If you cannot determine the state unambiguously, return null.

You may take your time to reason through the text if needed.
At the end of your reasoning, return your final answer **in this exact format**, and nothing else after it:

### FINAL ANSWER ###
Physical state : <solid/liquid/gas or null>
Boiling point : <value or null>
Flash point : <value or null>
"""
    headers = {
        "Authorization": f"bearer {api_key}",
        "Content-Type": "application/json"
    }

    data = {
        "model": model_name,
        "messages": [
            {"role": "user", "content": prompt}
        ]
    }

    response = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, data=json.dumps(data))
    
    try:
        output = response.json()
        return output['choices'][0]['message']['content']
    except Exception as e:
        return f"❌ Error extracting physical properties: {e}\nRaw: {response.text}"

# Chat with LLM on OpenRouter
def extract_storage_and_handling_via_llm(text: str, model_name: str, api_key: str):
    prompt = f"""
Here is a safety data sheet SDS: {text}

Please analyze the document and locate section 7 (Handling and storage) and section 10 (Stability and reactivity).
Then extract the information. If you think it is necessary, then make a summary of the content of those 2 sections.

You may take your time to reason through the text if needed.
At the end of your reasoning, return your final answer **in this exact format**, and nothing else after it:

### FINAL ANSWER ###
<Your analyze>
"""
    headers = {
        "Authorization": f"bearer {api_key}",
        "Content-Type": "application/json"
    }

    data = {
        "model": model_name,
        "messages": [
            {"role": "user", "content": prompt}
        ]
    }

    response = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, data=json.dumps(data))
    
    try:
        output = response.json()
        return output['choices'][0]['message']['content']
    except Exception as e:
        return f"❌ Error extracting storage and handling: {e}\nRaw: {response.text}"
