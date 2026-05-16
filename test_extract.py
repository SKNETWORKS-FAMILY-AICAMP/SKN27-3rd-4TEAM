import sys, os, json, glob
sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8")

import fitz
from backend.config import get_llm
from backend.graph.extract_entities import EXTRACT_PROMPT

pdfs = sorted(glob.glob("docs/pdf/판례/*.pdf"))
filepath = pdfs[0]
print(f"파일: {os.path.basename(filepath)}")

doc = fitz.open(filepath)
text = ""
for page in doc:
    text += page.get_text()
doc.close()
print(f"텍스트: {len(text)}자")

# 더 짧게 잘라서 시도
truncated = text[:2000]

llm = get_llm(temperature=0.0)
chain = EXTRACT_PROMPT | llm

try:
    response = chain.invoke({"text": truncated})
    print(f"\n응답 타입: {type(response.content)}")
    print(f"응답 길이: {len(response.content)}")
    print(f"응답 내용:\n{response.content}")
except Exception as e:
    print(f"에러: {type(e).__name__}: {e}")
