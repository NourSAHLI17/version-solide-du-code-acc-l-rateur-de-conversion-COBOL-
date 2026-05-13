import requests
import json

payload = {
    "source_code": "IDENTIFICATION DIVISION.\nPROGRAM-ID. TEST.\nPROCEDURE DIVISION.\n STOP RUN.",
    "parser_output": {
        "program_name": "TEST",
        "paragraphs": [],
        "symbol_table": []
    }
}

response = requests.post(
    "http://localhost:8000/api/analyze",
    json=payload
)

print("STATUS:", response.status_code)
print("RESPONSE:", response.text)
