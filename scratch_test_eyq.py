import os
import httpx

api_key = "hbXBVgFaLGvWctzEwzhgdsavzsKOlfiD"
endpoint = "https://eyq-incubator.europe.fabric.ey.com/eyq/eu/api"
api_version = "2024-02-15-preview"

headers = {
    "api-key": api_key,
    "Content-Type": "application/json",
    "Authorization": f"Bearer {api_key}" # sometimes standard OpenAI uses Bearer
}

def test_api():
    try:
        with httpx.Client() as client:
            print("Trying to fetch models list...")
            resp = client.get(f"{endpoint}/models?api-version={api_version}", headers=headers, timeout=10)
            print(f"Status: {resp.status_code}")
            print(f"Body: {resp.text[:500]}\n")
            
            print("Trying a basic chat completion...")
            payload = {
                "messages": [{"role": "user", "content": "Hello!"}],
                "max_tokens": 10
            }
            # Many Azure endpoints require the deployment name in the URL, e.g. /openai/deployments/gpt-4/chat/completions
            # Let's try standard format first
            resp2 = client.post(f"{endpoint}/chat/completions?api-version={api_version}", headers=headers, json=payload, timeout=10)
            print(f"Status: {resp2.status_code}")
            print(f"Body: {resp2.text[:500]}")
    except Exception as e:
        print(f"Error connecting: {e}")

if __name__ == "__main__":
    test_api()
