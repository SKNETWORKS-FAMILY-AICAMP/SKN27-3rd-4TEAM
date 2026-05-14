# rag/jm/cli.py
# RAG 문서 적재, 검색, 답변 생성, 에이전트 실행, 평가를 위한 CLI입니다.

from __future__ import annotations

import argparse
import json
import sys
from typing import List, Optional

from dotenv import load_dotenv

from .agent.multi_agent import run_multi_agent
from .agent.supervisor import run_agent
from .evaluation import evaluate_rag, load_eval_cases, report_to_dict
from .retrieval.generate import generate_answer
from .retrieval.ingest import ingest_paths
from .retrieval.search import search


def _cmd_ingest(args: argparse.Namespace) -> int:
    """CLI에서 문서 적재 명령을 실행합니다."""

    result = ingest_paths(
        paths=args.path,
        glob_pattern=args.glob,
        doc_type=args.doc_type,
        clear=args.clear,
    )
    print(json.dumps({"files": result.files, "chunks": result.chunks}, ensure_ascii=False))
    return 0


def _cmd_search(args: argparse.Namespace) -> int:
    """CLI에서 RAG 검색 명령을 실행합니다."""

    where = json.loads(args.where) if args.where else None
    hits = search(query=args.query, k=args.k, where=where)
    payload = [{"score": h.score, "metadata": h.metadata, "content": h.content} for h in hits]
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def _cmd_generate(args: argparse.Namespace) -> int:
    """CLI에서 검색 기반 답변 생성 명령을 실행합니다."""

    where = json.loads(args.where) if args.where else None
    result = generate_answer(query=args.query, k=args.k, where=where)
    payload = {
        "answer": result.answer,
        "hits": [{"score": h.score, "metadata": h.metadata, "content": h.content} for h in result.hits],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def _cmd_agent(args: argparse.Namespace) -> int:
    """CLI에서 Supervisor 에이전트를 실행합니다."""

    answer = run_agent(query=args.query)
    print(json.dumps({"answer": answer}, ensure_ascii=False, indent=2))
    return 0


def _cmd_multi_agent(args: argparse.Namespace) -> int:
    """CLI에서 DB/RAG/설명 멀티 에이전트를 실행합니다."""

    result = run_multi_agent(query=args.query, k=args.k)
    payload = {
        "answer": result.answer,
        "db_analysis": {
            "summary": result.db_analysis.summary,
            "metrics": result.db_analysis.metrics,
        },
        "rag_analysis": {
            "summary": result.rag_analysis.summary,
            "hits": [
                {"score": h.score, "metadata": h.metadata, "content": h.content}
                for h in result.rag_analysis.hits
            ],
        },
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def _cmd_eval(args: argparse.Namespace) -> int:
    """CLI에서 RAG 검색/답변 품질 평가를 실행합니다."""

    cases = load_eval_cases(args.cases)
    if args.limit:
        cases = cases[: args.limit]

    report = evaluate_rag(cases=cases, k=args.k, use_ragas=args.ragas)
    payload = report_to_dict(report)
    output = json.dumps(payload, ensure_ascii=False, indent=2)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as file:
            file.write(output)
    print(output)
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    """CLI argument를 파싱하고 선택한 하위 명령을 실행합니다."""

    load_dotenv()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(prog="rag.jm")
    subparsers = parser.add_subparsers(dest="cmd", required=True)

    ingest_parser = subparsers.add_parser("ingest", help="문서를 PGVector에 적재")
    ingest_parser.add_argument("--path", action="append", required=True, help="파일 또는 디렉터리 경로")
    ingest_parser.add_argument("--glob", default=None, help='디렉터리 검색 패턴 예: "*.pdf"')
    ingest_parser.add_argument("--doc-type", default="doc", help="문서 유형 메타데이터")
    ingest_parser.add_argument("--clear", action="store_true", help="기존 컬렉션을 삭제 후 적재")
    ingest_parser.set_defaults(func=_cmd_ingest)

    search_parser = subparsers.add_parser("search", help="유사 문서 chunk 검색")
    search_parser.add_argument("--query", required=True)
    search_parser.add_argument("--k", type=int, default=5)
    search_parser.add_argument("--where", default=None, help='메타데이터 JSON 필터 예: {"doc_type":"law"}')
    search_parser.set_defaults(func=_cmd_search)

    generate_parser = subparsers.add_parser("generate", help="검색 결과 기반 답변 생성")
    generate_parser.add_argument("--query", required=True)
    generate_parser.add_argument("--k", type=int, default=5)
    generate_parser.add_argument("--where", default=None, help='메타데이터 JSON 필터 예: {"doc_type":"law"}')
    generate_parser.set_defaults(func=_cmd_generate)

    agent_parser = subparsers.add_parser("agent", help="Supervisor 에이전트 실행")
    agent_parser.add_argument("--query", required=True)
    agent_parser.set_defaults(func=_cmd_agent)

    multi_agent_parser = subparsers.add_parser("multi-agent", help="DB/RAG/설명 에이전트 순차 실행")
    multi_agent_parser.add_argument("--query", required=True)
    multi_agent_parser.add_argument("--k", type=int, default=5)
    multi_agent_parser.set_defaults(func=_cmd_multi_agent)

    eval_parser = subparsers.add_parser("eval", help="RAG 평가 점수 측정")
    eval_parser.add_argument("--cases", default=None, help="평가 케이스 JSON 파일 경로")
    eval_parser.add_argument("--k", type=int, default=3, help="검색할 문서 chunk 개수")
    eval_parser.add_argument("--limit", type=int, default=None, help="앞에서부터 실행할 케이스 수")
    eval_parser.add_argument("--ragas", action="store_true", help="RAGAS 점수까지 계산")
    eval_parser.add_argument("--output", default=None, help="평가 결과 JSON 저장 경로")
    eval_parser.set_defaults(func=_cmd_eval)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
