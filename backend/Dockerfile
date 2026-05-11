FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app/backend

# 루트 requirements.txt 설치
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# backend 소스 복사
COPY backend/ .

EXPOSE 8000

CMD ["uvicorn", "rag_server.main:app", "--host", "0.0.0.0", "--port", "8000"]
