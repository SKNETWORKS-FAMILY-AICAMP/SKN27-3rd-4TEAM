import requests
import json

def test_chat():
    url = "http://localhost:8000/api/v1/chat/query"
    payload = {
        "session_id": "test-session",
        "message": "전세가율이 90% 이상인 경우 어떤 법적 근거로 보증금을 보호받을 수 있어?",
        "history": []
    }
    try:
        print(f"Sending request to {url}...")
        response = requests.post(url, json=payload, timeout=60)
        print(f"Status Code: {response.status_code}")
        if response.ok:
            data = response.json()
            print("\n--- Answer ---")
            print(data.get("answer"))
            print("\n--- References ---")
            for ref in data.get("references", []):
                print(f"- [{ref.get('doc_type')}] {ref.get('title')} (score: {ref.get('relevance_score')})")
            
            # Check for graph references
            graph_refs = [r for r in data.get("references", []) if "graph" in str(r.get("doc_type")).lower() or "risk" in str(r.get("doc_type")).lower()]
            if graph_refs:
                print(f"\n✅ Graph references found: {len(graph_refs)}")
            else:
                print("\n❌ No graph references found.")
        else:
            print(f"Error: {response.text}")
    except Exception as e:
        print(f"Failed to connect: {e}")

if __name__ == "__main__":
    test_chat()
