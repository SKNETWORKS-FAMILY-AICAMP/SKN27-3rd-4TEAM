import os
import sys
import json

# Add project root to sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from pcj_common.agents.pdf_review_agent import run_pdf_review_agent

def test_file(file_name):
    file_path = os.path.join(PROJECT_ROOT, "docs", file_name)
    print(f"\n--- Testing file: {file_name} ---")
    if not os.path.exists(file_path):
        print(f"Error: File not found at {file_path}")
        return

    try:
        result = run_pdf_review_agent(file_path)
        print(f"Result for {file_name}:")
        print(result)
        
        # Try to parse as JSON to check if it's valid
        try:
            parsed = json.loads(result)
            print("Status:", parsed.get("status"))
            if parsed.get("status") == "missing_data":
                print("Missing fields:", parsed.get("missing_fields"))
        except:
            print("Response is not valid JSON")
            
    except Exception as e:
        print(f"Error processing {file_name}: {e}")

if __name__ == "__main__":
    test_file("가상계약서.docx")
    test_file("평창동2.docx")
