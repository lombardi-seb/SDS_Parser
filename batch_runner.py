# batch_runner.py
import os
import sys
import json
import logging
from datetime import datetime
from SDS_functions import analyser_material_id, build_additional_json, envoyer_json, send_additional_json, read_tsv_file, connect_to_CISPro_api, disconnect_from_CISPro_API
from config import TSV_PATH, OPENROUTER_API_KEY
import getpass

# === Creation of the folder logs with timestamp ===
timestamp = datetime.now().strftime("%Y%m%d%H%M")
output_dir = f"logs_{timestamp}"
os.makedirs(output_dir, exist_ok=True)

# === Configuration of logging ===
log_file = os.path.join(output_dir, "batch_processing.log")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(log_file, encoding="utf-8"),
        logging.StreamHandler(sys.stdout)
    ]
)

def process_material_id(mid, h_codes_dict, username, password, model_name=None, use_llm=False):
    logging.info(f"--- Start process {mid} ---")

    try:
        result_json, full_text = analyser_material_id(mid, h_codes_dict)
        if result_json is None:
            logging.error(f"{mid} ❌ Error analyze SDS : {full_text}")
            return

        # Back-up JSON local
        output_path = os.path.join(output_dir, f"{mid}.json")
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(result_json)
        logging.info(f"{mid} ✅ Main JSON saved : {output_path}")

        # Post Main JSON
        resp = envoyer_json(username, password, result_json)
        logging.info(f"{mid} → Post SDS : {resp}")

        # Build additional JSON
        if use_llm and model_name:
            try:
                parsed = json.loads(result_json)
                additional_json = build_additional_json(parsed, full_text, model_name, OPENROUTER_API_KEY)
                if additional_json:
                    add_path = os.path.join(output_dir, f"{mid}_additional.json")
                    with open(add_path, "w", encoding="utf-8") as f:
                        json.dump(additional_json, f, indent=4, ensure_ascii=False)
                    logging.info(f"{mid} ✅ Additional JSON saved : {add_path}")

                    resp2 = send_additional_json(username, password, json.dumps(additional_json))
                    logging.info(f"{mid} → Post additional JSON : {resp2}")
            except Exception as e:
                logging.error(f"{mid} ❌ Error build additional JSON : {e}")

    except Exception as e:
        logging.exception(f"{mid} ❌ Exception : {e}")

    logging.info(f"--- End process {mid} ---\n")


def main():
    if len(sys.argv) < 2:
        print("Usage: python batch_runner.py ids.txt [model_name]")
        sys.exit(1)

    ids_file = sys.argv[1]
    model_name = sys.argv[2] if len(sys.argv) > 2 else None
    use_llm = model_name is not None

    # Connection user API
    username = input("Username CISPro: ")
    password = getpass.getpass("Password CISPro: ")
    
    CISPRO_TOKEN = connect_to_CISPro_api(username, password)
    if not CISPRO_TOKEN:
        raise Exception("Login failed. Stop of the batch runner.")
        sys.exit(1)

    # Load dictionary H-codes
    h_codes_dict = read_tsv_file(TSV_PATH)

    # Load list of IDs
    with open(ids_file, "r", encoding="utf-8") as f:
        ids = [line.strip() for line in f if line.strip()]

    logging.info(f"Process of {len(ids)} IDs (use_llm={use_llm}, model={model_name})")
    logging.info(f"Results and logs saved in : {output_dir}")

    for mid in ids:
        process_material_id(mid, h_codes_dict, username, password, model_name, use_llm)
    
    disconnect_from_CISPro_API()

if __name__ == "__main__":
    main()
