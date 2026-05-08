#!/bin/bash
# =============================================
# 전세계약 위험 진단 에이전트
# 데이터 정기 업데이트 배치 쉘
# 실행 주기: 매주 월요일 오전 6시 (cron)
# 수동 실행: bash batch.sh
# =============================================

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG_DIR="$SCRIPT_DIR/logs"
LOG_FILE="$LOG_DIR/batch_$(date +%Y%m%d_%H%M%S).log"

mkdir -p "$LOG_DIR"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

log "========================================="
log "배치 시작"
log "========================================="

# ---- Step 1. DB 연결 확인 ----
log "[1/3] DB 연결 확인..."
python3 -c "
import psycopg2, os
from dotenv import load_dotenv
load_dotenv()
try:
    conn = psycopg2.connect(
        host=os.getenv('DB_HOST', 'db'),
        port=os.getenv('DB_PORT', 5432),
        database=os.getenv('DB_NAME', 'jeonse_risk'),
        user=os.getenv('DB_USER', 'postgres'),
        password=os.getenv('DB_PASSWORD')
    )
    conn.close()
    print('DB 연결 성공')
except Exception as e:
    print(f'DB 연결 실패: {e}')
    exit(1)
" >> "$LOG_FILE" 2>&1

if [ $? -ne 0 ]; then
    log "❌ DB 연결 실패 - 배치 중단"
    exit 1
fi
log "✅ DB 연결 성공"

# ---- Step 2. API로 최신 데이터 수집 + DB 적재 ----
log "[2/3] API 데이터 수집 및 DB 적재 시작..."

python3 "$SCRIPT_DIR/scripts/fetch_data.py" >> "$LOG_FILE" 2>&1

if [ $? -eq 0 ]; then
    log "✅ API 수집 + 적재 완료"
else
    log "❌ API 수집 + 적재 실패 - 로그 확인: $LOG_FILE"
    exit 1
fi

# ---- Step 3. 오래된 로그 정리 (30일 초과) ----
log "[3/3] 오래된 로그 정리..."
find "$LOG_DIR" -name "batch_*.log" -mtime +30 -delete
log "✅ 30일 초과 로그 삭제 완료"

log "========================================="
log "배치 완료"
log "========================================="