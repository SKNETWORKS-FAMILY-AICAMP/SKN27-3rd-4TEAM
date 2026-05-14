"""Evaluate the local jeonse RAG API with RAGAS.

This script calls the real FastAPI RAG endpoint, builds a RAGAS dataset from
the returned answers and references, then evaluates answer/context quality.
Run it while the RAG server is available at RAG_SERVER_URL.
"""
from __future__ import annotations

import os
from typing import Any

import requests
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


RAG_SERVER_URL = os.getenv("RAG_SERVER_URL", "http://localhost:8000").rstrip("/")
CHAT_ENDPOINT = f"{RAG_SERVER_URL}/api/v1/chat/query"

EVAL_CASES = [
    {
        "question": "주택임대차보호법상 대항력은 언제 발생하나요?",
        "ground_truth": (
            "주택의 인도와 주민등록 전입신고를 마치면 그 다음 날부터 제3자에 대한 대항력이 발생한다."
        ),
    },
    {
        "question": "보증금 반환을 다음 임차인 입주 이후에 한다는 특약은 왜 위험한가요?",
        "ground_truth": (
            "보증금 반환을 다음 임차인 입주에 조건부로 묶으면 임대차 종료 후 반환이 지연될 수 있고, "
            "임차인의 반환청구권 행사와 보증금 회수에 불리하게 작용할 수 있다."
        ),
    },
    {
        "question": "신탁등기가 있는 전세계약에서 신탁원부와 계약 권한을 확인해야 하는 이유는?",
        "ground_truth": (
            "신탁부동산은 수탁자가 소유권과 처분 권한을 갖는 구조일 수 있으므로, 신탁원부와 수탁자 동의 "
            "또는 계약 권한을 확인하지 않으면 무권한자와 계약하거나 보증금 회수 위험이 생길 수 있다."
        ),
    },
    {
        "question": "다가구주택 전세계약에서 선순위 보증금과 확정일자 현황을 확인해야 하는 이유는?",
        "ground_truth": (
            "다가구주택은 다른 임차인의 선순위 보증금이 보증금 회수 가능성에 영향을 주므로, 등기부만으로는 "
            "부족하고 선순위 임차보증금, 전입세대, 확정일자 부여 현황 등을 확인해야 한다."
        ),
    },
]


def query_rag(question: str, index: int) -> dict[str, Any]:
    body = {
        "session_id": f"ragas-eval-{index}",
        "message": question,
        "history": [],
    }
    response = requests.post(CHAT_ENDPOINT, json=body, timeout=90)
    response.raise_for_status()
    return response.json()


def build_dataset() -> Dataset:
    rows: dict[str, list[Any]] = {
        "question": [],
        "answer": [],
        "contexts": [],
        "ground_truth": [],
    }

    print(f"Calling RAG server: {CHAT_ENDPOINT}")
    for index, case in enumerate(EVAL_CASES, 1):
        question = case["question"]
        payload = query_rag(question, index)
        references = payload.get("references") or []
        contexts = [
            str(ref.get("chunk_text") or "").strip()
            for ref in references
            if str(ref.get("chunk_text") or "").strip()
        ]

        rows["question"].append(question)
        rows["answer"].append(str(payload.get("answer") or "").strip())
        rows["contexts"].append(contexts)
        rows["ground_truth"].append(case["ground_truth"])

        print(f"\n[{index}] {question}")
        print(f"answer_chars={len(rows['answer'][-1])}, contexts={len(contexts)}")
        for ref_index, ref in enumerate(references[:3], 1):
            print(
                f"  ref{ref_index}: "
                f"{ref.get('doc_type')} | {ref.get('title')} | score={ref.get('relevance_score')}"
            )

    return Dataset.from_dict(rows)


def test_ragas() -> None:
    if "OPENAI_API_KEY" not in os.environ:
        raise RuntimeError("OPENAI_API_KEY is required for RAGAS evaluation.")

    dataset = build_dataset()
    llm_model = os.getenv("RAGAS_LLM_MODEL", "gpt-4o-mini")
    embedding_model = os.getenv("RAGAS_EMBEDDING_MODEL", "text-embedding-3-small")
    llm, embeddings = build_judges(llm_model, embedding_model)
    metrics = build_metrics(llm, embeddings)

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
    return (
        ChatOpenAI(model=llm_model, temperature=0),
        OpenAIEmbeddings(model=embedding_model),
    )


def build_metrics(llm: Any, embeddings: Any) -> list[Any]:
    return [faithfulness, answer_relevancy, context_precision, context_recall]


if __name__ == "__main__":
    load_dotenv()
    print("Ragas version:", __import__("ragas").__version__)
    test_ragas()
