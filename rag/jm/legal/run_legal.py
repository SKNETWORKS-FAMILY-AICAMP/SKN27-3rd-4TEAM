# rag/jm/legal/run_legal.py
# 법률 상담 에이전트를 모듈 단위로 실행하기 위한 간단한 CLI입니다.

from __future__ import annotations

import argparse
import json
import sys

from dotenv import load_dotenv

from .agent import run_legal_agent


def main() -> int:
    """터미널에서 질문을 받아 legal_agent 실행 결과를 JSON으로 출력합니다."""

    load_dotenv()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(prog="python -m rag.jm.legal.run_legal")
    parser.add_argument("--question", required=True, help="법률 상담 질문")
    parser.add_argument("--k", type=int, default=5, help="검색할 법률 문서 chunk 개수")
    args = parser.parse_args()

    result = run_legal_agent(question=args.question, k=args.k)
    payload = {
        "answer": result.answer,
        "review_passed": result.review_passed,
        "review_message": result.review_message,
        "hits": [
            {"score": hit.score, "metadata": hit.metadata, "content": hit.content}
            for hit in result.hits
        ],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
