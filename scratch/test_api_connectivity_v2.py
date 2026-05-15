import requests
import json
import sys

# Set encoding for output to utf-8
if sys.stdout.encoding != 'utf-8':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

def test_chat():
    url = "http://localhost:8000/api/v1/chat/query"
    payload = {
        "session_id": "test-session",
        "message": "전세가율이 90% 이상인 경우 어떤 법적 근거로 보증금을 보호받을 수 있어?",
        "history": []
    }
    try:
        response = requests.post(url, json=payload, timeout=60)
        result = {
            "status_code": response.status_code,
            "data": response.json() if response.ok else response.text
        }
        with open("scratch/api_test_result.json", "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print("Result saved to scratch/api_test_result.json")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_chat()
