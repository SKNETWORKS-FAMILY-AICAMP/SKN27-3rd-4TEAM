# rag/jm/evaluation.py
# 현재 rag/jm RAG 파이프라인의 검색/답변 품질을 점수화합니다.

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import mean
from typing import Any, Iterable, Optional

from langchain_openai import ChatOpenAI, OpenAIEmbeddings

from .core.config import load_config
from .retrieval.generate import generate_answer


@dataclass(frozen=True)
class EvaluationCase:
    """RAG 평가에 사용할 질문과 기대 답변입니다."""

    question: str
    ground_truth: str


@dataclass(frozen=True)
class EvaluationRow:
    """개별 평가 케이스 실행 결과와 점수를 담습니다."""

    question: str
    ground_truth: str
    answer: str
    contexts: list[str]
    hit_count: int
    avg_retrieval_score: float
    answer_relevance: float
    context_recall: float
    groundedness: float
    overall_score: float


@dataclass(frozen=True)
class EvaluationReport:
    """전체 평가 결과의 요약과 상세 행을 담습니다."""

    case_count: int
    averages: dict[str, float]
    rows: list[EvaluationRow]
    ragas: Optional[dict[str, Any]] = None


DEFAULT_EVAL_CASES = [
    EvaluationCase(
        question="전세보증금 반환 보증 가입 전에 무엇을 확인해야 해?",
        ground_truth=(
            "보증기관별 가입 조건, 신청 기한, 계약 후 실제 가입 여부, "
            "임대인의 보증금지 대상 여부와 대위변제 이력, 재계약 시 재가입 필요 여부를 확인해야 한다."
        ),
    ),
    EvaluationCase(
        question="전세계약 전에 등기부등본에서 어떤 위험을 봐야 해?",
        ground_truth=(
            "소유자 일치 여부, 근저당권과 압류 등 선순위 권리, 신탁 등 소유권 제한, "
            "보증금 회수 가능성에 영향을 주는 권리관계를 확인해야 한다."
        ),
    ),
    EvaluationCase(
        question="보증금을 올려 재계약할 때 확정일자는 다시 받아야 해?",
        ground_truth=(
            "보증금이 증액되면 기존 확정일자가 증액분을 보호하지 않으므로 "
            "증액된 금액에 대해 확정일자를 다시 받아야 한다."
        ),
    ),
]


def load_eval_cases(path: Optional[str]) -> list[EvaluationCase]:
    """JSON 파일 또는 기본 케이스에서 평가 케이스를 로드합니다."""

    if not path:
        return list(DEFAULT_EVAL_CASES)

    raw_cases = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw_cases, list):
        raise ValueError("평가 케이스 파일은 JSON 배열이어야 합니다.")

    cases: list[EvaluationCase] = []
    for item in raw_cases:
        if not isinstance(item, dict):
            raise ValueError("각 평가 케이스는 객체여야 합니다.")
        cases.append(
            EvaluationCase(
                question=str(item["question"]).strip(),
                ground_truth=str(item["ground_truth"]).strip(),
            )
        )
    return cases


def evaluate_rag(
    cases: Iterable[EvaluationCase],
    k: int = 3,
    use_ragas: bool = False,
) -> EvaluationReport:
    """RAG 답변을 생성하고 lightweight 점수와 선택적 RAGAS 점수를 계산합니다."""

    rows: list[EvaluationRow] = []
    for case in cases:
        result = generate_answer(query=case.question, k=k)
        contexts = [hit.content for hit in result.hits]
        avg_retrieval_score = _safe_mean([hit.score for hit in result.hits])
        answer_relevance = _overlap_score(result.answer, case.question)
        context_recall = _overlap_score("\n".join(contexts), case.ground_truth)
        groundedness = _overlap_score(result.answer, "\n".join(contexts))
        overall_score = _safe_mean(
            [avg_retrieval_score, answer_relevance, context_recall, groundedness]
        )

        rows.append(
            EvaluationRow(
                question=case.question,
                ground_truth=case.ground_truth,
                answer=result.answer,
                contexts=contexts,
                hit_count=len(result.hits),
                avg_retrieval_score=round(avg_retrieval_score, 4),
                answer_relevance=round(answer_relevance, 4),
                context_recall=round(context_recall, 4),
                groundedness=round(groundedness, 4),
                overall_score=round(overall_score, 4),
            )
        )

    return EvaluationReport(
        case_count=len(rows),
        averages=_average_scores(rows),
        rows=rows,
        ragas=_run_ragas(rows) if use_ragas else None,
    )


def report_to_dict(report: EvaluationReport) -> dict[str, Any]:
    """평가 리포트를 JSON 직렬화 가능한 dict로 변환합니다."""

    return asdict(report)


def _run_ragas(rows: list[EvaluationRow]) -> dict[str, Any]:
    """설치된 RAGAS로 faithfulness/relevancy/context 점수를 계산합니다."""

    try:
        from datasets import Dataset
        from ragas import evaluate
        from ragas.metrics import (
            answer_relevancy,
            context_precision,
            context_recall,
            faithfulness,
        )
    except ImportError as exc:
        raise RuntimeError("RAGAS 평가에는 `ragas`와 `datasets` 설치가 필요합니다.") from exc

    cfg = load_config()
    dataset = Dataset.from_dict(
        {
            "question": [row.question for row in rows],
            "answer": [row.answer for row in rows],
            "contexts": [row.contexts for row in rows],
            "ground_truth": [row.ground_truth for row in rows],
        }
    )
    result = evaluate(
        dataset=dataset,
        metrics=[faithfulness, answer_relevancy, context_precision, context_recall],
        llm=ChatOpenAI(model=cfg.llm_model, temperature=0),
        embeddings=OpenAIEmbeddings(model=cfg.embedding_model),
    )
    return dict(result)


def _average_scores(rows: list[EvaluationRow]) -> dict[str, float]:
    """평가 행들의 평균 점수를 계산합니다."""

    return {
        "avg_retrieval_score": round(_safe_mean([row.avg_retrieval_score for row in rows]), 4),
        "answer_relevance": round(_safe_mean([row.answer_relevance for row in rows]), 4),
        "context_recall": round(_safe_mean([row.context_recall for row in rows]), 4),
        "groundedness": round(_safe_mean([row.groundedness for row in rows]), 4),
        "overall_score": round(_safe_mean([row.overall_score for row in rows]), 4),
    }


def _overlap_score(source: str, target: str) -> float:
    """두 텍스트의 글자 2-gram 겹침 비율을 0~1 점수로 계산합니다."""

    target_terms = _char_bigrams(target)
    if not target_terms:
        return 0.0
    source_terms = _char_bigrams(source)
    return len(source_terms & target_terms) / len(target_terms)


def _char_bigrams(text: str) -> set[str]:
    """한글 문장에도 동작하도록 정규화된 글자 2-gram 집합을 만듭니다."""

    normalized = re.sub(r"\s+", "", text.lower())
    normalized = re.sub(r"[^0-9a-z가-힣]", "", normalized)
    if len(normalized) < 2:
        return {normalized} if normalized else set()
    return {normalized[index : index + 2] for index in range(len(normalized) - 1)}


def _safe_mean(values: Iterable[float]) -> float:
    """빈 값 목록은 0점으로 처리해 평균을 계산합니다."""

    filtered = [float(value) for value in values]
    return mean(filtered) if filtered else 0.0
