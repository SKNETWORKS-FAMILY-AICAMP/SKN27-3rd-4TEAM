# =============================================
# 전세계약 위험 진단 에이전트
# 데이터 엔지니어링 Dockerfile
# =============================================

FROM python:3.11-slim

# 시스템 패키지 설치 (PostgreSQL 클라이언트 + PDF 처리용)
RUN apt-get update && apt-get install -y \
    postgresql-client \
    poppler-utils \
    cron \
    && rm -rf /var/lib/apt/lists/*

# 작업 디렉토리
WORKDIR /app

# 의존성 먼저 설치 (캐시 활용)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 소스 코드 복사
COPY . .

# 데이터 디렉토리 생성
RUN mkdir -p /app/data /app/logs

# 배치 쉘 실행 권한 부여
RUN chmod +x /app/batch.sh

# cron 등록 (매주 월요일 오전 6시 실행)
RUN echo "0 6 * * 1 root /app/batch.sh >> /app/logs/batch.log 2>&1" \
    > /etc/cron.d/jeonse-batch \
    && chmod 0644 /etc/cron.d/jeonse-batch

# 기본 실행: cron 데몬 + 로그 출력
CMD ["sh", "-c", "cron && tail -f /app/logs/batch.log"]
