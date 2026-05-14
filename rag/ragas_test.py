"""로컬 RAG 파이프라인을 RAGAS 공식 지표로 평가합니다."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

from datasets import Dataset
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from ragas import evaluate
from ragas.metrics import (
    answer_relevancy,
    context_precision,
    context_recall,
    faithfulness,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    # 스크립트를 직접 실행해도 프로젝트 루트 패키지를 import할 수 있게 합니다.
    sys.path.insert(0, str(PROJECT_ROOT))

from rag.jm.retrieval.generate import generate_answer


EVAL_CASES = [
    {
        "question": "주택임대차보호법의 대항력은 언제 발생하나?",
        "ground_truth": "주택의 인도와 주민등록 전입신고를 마치면 그 다음 날 0시에 제3자에 대한 대항력이 발생한다.",
    },
    {
        "question": "보증금 반환을 다음 임차인 입주 이후로 미루는 특약은 왜 위험한가?",
        "ground_truth": (
            "보증금 반환을 다음 임차인 입주 조건으로 묶으면 임대차 종료 후 반환이 지연될 수 있고, "
            "임차인의 반환청구권 행사와 보증금 회수에 불리하게 작용할 수 있다."
        ),
    },
    {
        "question": "신탁등기가 있는 전세계약에서 신탁자에게 계약 권한을 확인해야 하는 이유는?",
        "ground_truth": (
            "신탁부동산은 수탁자가 소유권과 처분 권한을 갖는 구조일 수 있어 신탁자에게 임대차 동의 "
            "또는 계약 권한이 없으면 무권한자와 계약하게 되어 보증금 회수 위험이 생길 수 있다."
        ),
    },
    {
        "question": "다가구주택 전세계약에서 선순위 보증금과 확정일자 현황을 확인해야 하는 이유는?",
        "ground_truth": (
            "다가구주택은 다른 임차인의 선순위 보증금이 보증금 회수 가능성에 영향을 주므로 등기부만으로는 "
            "부족하고 선순위 임차보증금, 전입일, 확정일자 부여 현황 등을 확인해야 한다."
        ),
    },
]


def query_local_rag(question: str, k: int = 3) -> dict[str, Any]:
    # FastAPI 서버를 띄우지 않고 로컬 RAG 검색/생성 함수를 직접 호출합니다.
    result = generate_answer(query=question, k=k)
    return {
        "answer": result.answer,
        "contexts": [hit.content for hit in result.hits],
        "references": [
            {
                "doc_type": hit.metadata.get("doc_type"),
                "title": hit.metadata.get("title"),
                "relevance_score": hit.score,
            }
            for hit in result.hits
        ],
    }


def build_dataset(k: int = 3) -> Dataset:
    # RAGAS가 요구하는 question/answer/contexts/ground_truth 컬럼을 구성합니다.
    rows: dict[str, list[Any]] = {
        "question": [],
        "answer": [],
        "contexts": [],
        "ground_truth": [],
    }

    print("Calling local RAG pipeline")
    for index, case in enumerate(EVAL_CASES, 1):
        question = case["question"]
        payload = query_local_rag(question, k=k)
        contexts = [context for context in payload["contexts"] if context.strip()]

        rows["question"].append(question)
        rows["answer"].append(str(payload.get("answer") or "").strip())
        rows["contexts"].append(contexts)
        rows["ground_truth"].append(case["ground_truth"])

        print(f"\n[{index}] {question}")
        print(f"answer_chars={len(rows['answer'][-1])}, contexts={len(contexts)}")
        for ref_index, ref in enumerate(payload["references"][:3], 1):
            print(
                f"  ref{ref_index}: "
                f"{ref.get('doc_type')} | {ref.get('title')} | score={ref.get('relevance_score')}"
            )

    return Dataset.from_dict(rows)


def test_ragas() -> None:
    # RAG 답변 생성과 RAGAS 평가 모두 OpenAI API 키가 필요합니다.
    if "OPENAI_API_KEY" not in os.environ:
        raise RuntimeError("OPENAI_API_KEY is required for RAGAS evaluation.")

    dataset = build_dataset(k=int(os.getenv("RAGAS_RETRIEVAL_K", "3")))
    llm_model = os.getenv("RAGAS_LLM_MODEL", "gpt-4o-mini")
    embedding_model = os.getenv("RAGAS_EMBEDDING_MODEL", "text-embedding-3-small")
    llm, embeddings = build_judges(llm_model, embedding_model)
    metrics = build_metrics()

    print("\nEvaluating with RAGAS...")
    result = evaluate(
        dataset=dataset,
        metrics=metrics,
        llm=llm,
        embeddings=embeddings,
    )
    print("\nEvaluation Results:")
    print(result)


def build_judges(llm_model: str, embedding_model: str) -> tuple[Any, Any]:
    # RAGAS 판정용 LLM과 임베딩 모델을 구성합니다.
    return (
        ChatOpenAI(model=llm_model, temperature=0),
        OpenAIEmbeddings(model=embedding_model),
    )


def build_metrics() -> list[Any]:
    # 공식 RAGAS 핵심 지표를 사용합니다.
    return [faithfulness, answer_relevancy, context_precision, context_recall]


if __name__ == "__main__":
    load_dotenv()
    print("Ragas version:", __import__("ragas").__version__)
    test_ragas()
