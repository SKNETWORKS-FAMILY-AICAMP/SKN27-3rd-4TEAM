"""
전세계약 위험 진단 에이전트 - FastAPI 엔드포인트 테스트

테스트 대상 엔드포인트:
  1. GET  /api/v1/health             헬스체크
  2. POST /api/v1/rag/retrieve       RAG 벡터 검색
  3. POST /api/v1/chat/query         RAG 채팅 질문
  4. POST /api/v1/diagnosis/text     텍스트 계약서 진단
  5. POST /api/v1/diagnosis/upload   PDF 계약서 업로드 진단
  6. GET  /api/v1/diagnosis/logs     진단 이력 조회

실행:
  docker compose up -d          # API 서버 먼저 기동
  python test_fastapi.py         # 전체 테스트
  python test_fastapi.py health  # 특정 테스트만
  python test_fastapi.py --verbose
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import uuid
from pathlib import Path

import requests

# ── 설정 ──────────────────────────────────────────────────────
BASE_URL   = os.getenv("API_BASE_URL", "http://localhost:8000")
API_PREFIX = "/api/v1"
TIMEOUT    = 60          # 초 (LLM 호출 포함이라 여유 있게)
SESSION_ID = f"test-{uuid.uuid4().hex[:8]}"

# 가상 계약서 텍스트 (진단 테스트용)
SAMPLE_CONTRACT = """
표준임대차계약서

계약일: 2025년 01월 20일

1. 계약 당사자
   임대인: 홍길동 (주민번호: 800101-1234567)
   임차인: 김철수 (주민번호: 900202-1234567)

2. 임대차 목적물
   소재지: 서울특별시 종로구 청운동 123-45
   건물명: 청운빌라 101호
   전용면적: 84.84㎡ (25.66평)
   건축연도: 2005년

3. 계약 내용
   보증금: 금 사억원 (400,000,000원)
   월세: 없음 (순전세)
   계약기간: 2025년 3월 1일 ~ 2027년 2월 28일 (2년)

4. 등기부 현황
   근저당 설정금액: 6,000만원 (채권최고액)
   채권자: 국민은행

5. 특약사항
   제1조: 임대인은 본 계약 보증금을 사업자금으로 사용할 수 있으며,
          임차인은 이에 동의한다.
   제2조: 계약 만료 후 임대인의 사정에 따라 보증금 반환이 최대 3개월
          지연될 수 있다.
   제3조: 임차인은 전입신고 및 확정일자를 받지 않기로 한다.
   제4조: 임대인이 파산하는 경우 보증금 반환 의무는 소멸한다.
   제5조: 계약 기간 내 임대인은 해당 부동산을 제3자에게 담보로
          제공할 수 있다.
   제6조: 본 계약서는 공증받지 않으며 구두 합의를 우선으로 한다.
"""

PDF_PATH = Path("docs/가상계약서.docx")   # 실제 테스트 시 PDF 파일 경로로 변경


# ── 공통 유틸 ──────────────────────────────────────────────────

class Color:
    GREEN  = "\033[92m"
    RED    = "\033[91m"
    YELLOW = "\033[93m"
    CYAN   = "\033[96m"
    BOLD   = "\033[1m"
    RESET  = "\033[0m"

def ok(msg):   print(f"{Color.GREEN}  ✅ {msg}{Color.RESET}")
def fail(msg): print(f"{Color.RED}  ❌ {msg}{Color.RESET}")
def info(msg): print(f"{Color.CYAN}  ℹ  {msg}{Color.RESET}")
def warn(msg): print(f"{Color.YELLOW}  ⚠  {msg}{Color.RESET}")
def header(msg): print(f"\n{Color.BOLD}{Color.CYAN}{'='*55}\n  {msg}\n{'='*55}{Color.RESET}")

def url(path: str) -> str:
    return f"{BASE_URL}{API_PREFIX}{path}"

def show_json(data: dict, verbose: bool, max_chars: int = 300) -> None:
    if not verbose:
        return
    text = json.dumps(data, ensure_ascii=False, indent=2)
    if len(text) > max_chars:
        text = text[:max_chars] + "\n  ...(생략)..."
    print(f"  {Color.YELLOW}응답:{Color.RESET}")
    for line in text.splitlines():
        print(f"    {line}")


# ── 1. 헬스체크 ────────────────────────────────────────────────

def test_health(verbose: bool = False) -> bool:
    header("1. 헬스체크  GET /api/v1/health")
    try:
        t0  = time.time()
        res = requests.get(url("/health"), timeout=TIMEOUT)
        ms  = int((time.time() - t0) * 1000)

        if res.status_code == 200:
            data = res.json()
            ok(f"status={data.get('status')}  version={data.get('version')}  ({ms}ms)")

            services = data.get("services", {})
            for svc, detail in services.items():
                status = detail.get("status", "unknown")
                extra  = f"  doc_count={detail.get('doc_count', '-')}" if "doc_count" in detail else ""
                if status == "ok":
                    ok(f"  [{svc}] {status}{extra}")
                else:
                    warn(f"  [{svc}] {status}{extra}")

            show_json(data, verbose)
            return True
        else:
            fail(f"HTTP {res.status_code}: {res.text[:200]}")
            return False
    except requests.ConnectionError:
        fail(f"연결 실패 — Docker가 실행 중인지 확인하세요: {BASE_URL}")
        return False
    except Exception as e:
        fail(str(e))
        return False


# ── 2. RAG 벡터 검색 ───────────────────────────────────────────

def test_retrieve(verbose: bool = False) -> bool:
    header("2. RAG 검색  POST /api/v1/rag/retrieve")

    test_cases = [
        {
            "name": "특약 위험 분석",
            "payload": {
                "task_type": "special_clause_analysis",
                "query": "보증금을 사업자금으로 사용한다는 특약은 유효한가요?",
                "top_k": 3,
                "session_id": SESSION_ID,
            },
        },
        {
            "name": "법령 검색",
            "payload": {
                "task_type": "legal_law_guide_search",
                "query": "주택임대차보호법 대항력 요건",
                "top_k": 3,
                "session_id": SESSION_ID,
            },
        },
        {
            "name": "판례 검색",
            "payload": {
                "task_type": "legal_case_search",
                "query": "전세사기 보증금 반환 판례",
                "top_k": 3,
                "session_id": SESSION_ID,
            },
        },
    ]

    passed = 0
    for tc in test_cases:
        try:
            t0  = time.time()
            res = requests.post(url("/rag/retrieve"), json=tc["payload"], timeout=TIMEOUT)
            ms  = int((time.time() - t0) * 1000)

            if res.status_code == 200:
                data  = res.json()
                total = data.get("total_retrieved", 0)
                refs  = data.get("references", [])
                ok(f"[{tc['name']}] {total}건 검색 ({ms}ms)")
                if refs:
                    top = refs[0]
                    info(f"  top1: [{top.get('doc_type')}] {top.get('title','')[:40]}  score={top.get('relevance_score',0):.3f}")
                else:
                    warn("  검색 결과 0건 — 임베딩이 적재됐는지 확인하세요")
                show_json(data, verbose)
                passed += 1
            else:
                fail(f"[{tc['name']}] HTTP {res.status_code}: {res.text[:200]}")
        except Exception as e:
            fail(f"[{tc['name']}] {e}")

    print(f"\n  결과: {passed}/{len(test_cases)} 통과")
    return passed == len(test_cases)


# ── 3. 채팅 질문 ───────────────────────────────────────────────

def test_chat(verbose: bool = False) -> bool:
    header("3. 채팅 질문  POST /api/v1/chat/query")

    questions = [
        "전세 계약 시 확정일자를 받아야 하는 이유가 뭔가요?",
        "근저당이 설정된 집에 전세 들어가도 되나요?",
    ]

    history = []
    passed  = 0

    for i, q in enumerate(questions, 1):
        payload = {
            "session_id": SESSION_ID,
            "message": q,
            "history": history,
        }
        try:
            t0  = time.time()
            res = requests.post(url("/chat/query"), json=payload, timeout=TIMEOUT)
            ms  = int((time.time() - t0) * 1000)

            if res.status_code == 200:
                data   = res.json()
                answer = data.get("answer", "")
                refs   = data.get("references", [])
                ok(f"Q{i}: {q[:40]}...  ({ms}ms)")
                info(f"  답변({len(answer)}자): {answer[:120]}...")
                info(f"  참조문서: {len(refs)}건")
                show_json(data, verbose)

                # 다음 질문에 이전 대화 이력 추가 (멀티턴 테스트)
                history.append({"role": "user",      "content": q})
                history.append({"role": "assistant", "content": answer})
                passed += 1
            else:
                fail(f"Q{i} HTTP {res.status_code}: {res.text[:200]}")
        except Exception as e:
            fail(f"Q{i} {e}")

    print(f"\n  결과: {passed}/{len(questions)} 통과")
    return passed == len(questions)


# ── 4. 텍스트 계약서 진단 ──────────────────────────────────────

def test_diagnosis_text(verbose: bool = False) -> bool:
    header("4. 텍스트 진단  POST /api/v1/diagnosis/text")

    payload = {
        "session_id": SESSION_ID,
        "contract_text": SAMPLE_CONTRACT,
    }

    try:
        t0  = time.time()
        res = requests.post(url("/diagnosis/text"), json=payload, timeout=TIMEOUT)
        ms  = int((time.time() - t0) * 1000)

        if res.status_code == 200:
            data    = res.json()
            score   = data.get("risk_score", 0)
            level   = data.get("risk_level", "")
            factors = data.get("risk_factors", [])
            summary = data.get("summary", "")
            refs    = data.get("references", [])

            ok(f"진단 완료  score={score}  level={level}  ({ms}ms)")
            info(f"  위험요소: {len(factors)}개  |  참조문서: {len(refs)}건")
            info(f"  요약: {summary[:120]}...")

            if factors:
                print()
                for f in factors[:3]:
                    sev   = f.get("severity", "")
                    desc  = f.get("description", "")[:60]
                    color = Color.RED if sev == "HIGH" else Color.YELLOW if sev == "MEDIUM" else Color.GREEN
                    print(f"  {color}[{sev}]{Color.RESET} {desc}")
                if len(factors) > 3:
                    info(f"  ... 외 {len(factors)-3}개 더")

            # 기대값 검증
            assert score >= 0 and score <= 100, f"risk_score 범위 오류: {score}"
            assert level in ("안전", "주의", "위험", "CRITICAL"), f"risk_level 값 오류: {level}"
            ok("검증 통과 (score 범위, level 값)")

            show_json(data, verbose)
            return True
        else:
            fail(f"HTTP {res.status_code}: {res.text[:300]}")
            return False
    except AssertionError as e:
        fail(f"검증 실패: {e}")
        return False
    except Exception as e:
        fail(str(e))
        return False


# ── 5. PDF 업로드 진단 ─────────────────────────────────────────

def test_diagnosis_upload(verbose: bool = False) -> bool:
    header("5. PDF 업로드 진단  POST /api/v1/diagnosis/upload")

    # PDF 파일이 없으면 스킵
    if not PDF_PATH.exists():
        warn(f"PDF 파일 없음 ({PDF_PATH}) — 스킵")
        warn("docs/ 폴더에 PDF 계약서를 넣으면 테스트됩니다.")
        return True

    try:
        t0 = time.time()
        with open(PDF_PATH, "rb") as f:
            res = requests.post(
                url("/diagnosis/upload"),
                files={"file": (PDF_PATH.name, f, "application/pdf")},
                data={"session_id": SESSION_ID},
                timeout=TIMEOUT,
            )
        ms = int((time.time() - t0) * 1000)

        if res.status_code == 200:
            data  = res.json()
            score = data.get("risk_score", 0)
            level = data.get("risk_level", "")
            ok(f"PDF 진단 완료  score={score}  level={level}  ({ms}ms)")
            show_json(data, verbose)
            return True
        else:
            fail(f"HTTP {res.status_code}: {res.text[:300]}")
            return False
    except Exception as e:
        fail(str(e))
        return False


# ── 6. 진단 이력 조회 ──────────────────────────────────────────

def test_logs(verbose: bool = False) -> bool:
    header("6. 진단 이력  GET /api/v1/diagnosis/logs")

    # 전체 이력
    try:
        t0  = time.time()
        res = requests.get(url("/diagnosis/logs?limit=5"), timeout=TIMEOUT)
        ms  = int((time.time() - t0) * 1000)

        if res.status_code == 200:
            data  = res.json()
            total = data.get("total", 0)
            ok(f"전체 이력 조회: {total}건  ({ms}ms)")
            show_json(data, verbose)
        else:
            fail(f"HTTP {res.status_code}: {res.text[:200]}")
            return False
    except Exception as e:
        fail(str(e))
        return False

    # 세션별 이력
    try:
        t0  = time.time()
        res = requests.get(url(f"/diagnosis/logs?session_id={SESSION_ID}&limit=5"), timeout=TIMEOUT)
        ms  = int((time.time() - t0) * 1000)

        if res.status_code == 200:
            data  = res.json()
            total = data.get("total", 0)
            ok(f"세션별 이력 조회 (session_id={SESSION_ID[:12]}...): {total}건  ({ms}ms)")
            return True
        else:
            fail(f"HTTP {res.status_code}: {res.text[:200]}")
            return False
    except Exception as e:
        fail(str(e))
        return False


# ── 전체 실행 ──────────────────────────────────────────────────

TESTS = {
    "health":    test_health,
    "retrieve":  test_retrieve,
    "chat":      test_chat,
    "diagnosis": test_diagnosis_text,
    "upload":    test_diagnosis_upload,
    "logs":      test_logs,
}


def main():
    global BASE_URL

    parser = argparse.ArgumentParser(description="FastAPI 엔드포인트 테스트")
    parser.add_argument(
        "tests", nargs="*",
        help=f"실행할 테스트 (미지정 시 전체): {list(TESTS.keys())}",
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="응답 JSON 상세 출력")
    parser.add_argument("--url", default=BASE_URL, help=f"API 베이스 URL (기본: {BASE_URL})")
    args = parser.parse_args()

    BASE_URL = args.url

    targets = args.tests if args.tests else list(TESTS.keys())
    invalid = [t for t in targets if t not in TESTS]
    if invalid:
        print(f"알 수 없는 테스트: {invalid}")
        print(f"사용 가능: {list(TESTS.keys())}")
        sys.exit(1)

    print(f"\n{Color.BOLD}🔍 FastAPI 테스트 시작{Color.RESET}")
    print(f"   대상 서버  : {BASE_URL}")
    print(f"   세션 ID    : {SESSION_ID}")
    print(f"   실행 테스트: {targets}")

    results = {}
    for name in targets:
        results[name] = TESTS[name](verbose=args.verbose)

    # 최종 요약
    print(f"\n{Color.BOLD}{'='*55}")
    print("  최종 결과")
    print(f"{'='*55}{Color.RESET}")
    passed = sum(1 for v in results.values() if v)
    for name, ok_flag in results.items():
        mark  = f"{Color.GREEN}PASS{Color.RESET}" if ok_flag else f"{Color.RED}FAIL{Color.RESET}"
        print(f"  {name:<12} {mark}")
    print(f"\n  {passed}/{len(results)} 통과")

    if passed < len(results):
        print(f"\n{Color.YELLOW}  Swagger UI에서 직접 확인:{Color.RESET}")
        print(f"  {BASE_URL}/docs")
        sys.exit(1)
    else:
        print(f"\n{Color.GREEN}  ✅ 전체 통과!{Color.RESET}")


if __name__ == "__main__":
    main()
