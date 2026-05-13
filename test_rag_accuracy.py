"""
RAG 정확도 · 신뢰도 검증 스크립트
=====================================
실행 방법:
    cd SKN27-3rd-4TEAM
    python test_rag_accuracy.py [--verbose] [--save-report]

측정 항목:
  1. 검색 품질   — 유사도 점수 분포 / TOP-K 커버리지
  2. 답변 정확도 — 알려진 Q&A 쌍에 대한 키워드 포함률
  3. DL 통합     — DL ContextPack 주입 전후 점수 비교
  4. 전체 파이프라인 — diagnose() 엔드투엔드 결과 검증
"""
from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

# ── 프로젝트 루트를 sys.path에 추가 ──────────────────────────────────────────
_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "backend"))


# ═══════════════════════════════════════════════════════════════════════════════
# 1. 알려진 Q&A 쌍 (ground-truth)
# ═══════════════════════════════════════════════════════════════════════════════
KNOWN_QA: list[dict[str, Any]] = [
    {
        "id": "QA001",
        "category": "보증금 반환",
        "question": "다음 임차인이 들어오기 전에 보증금을 돌려줄 필요가 없다는 특약은 유효한가요?",
        "expected_keywords": ["동시이행", "보증금 반환", "임차권등기", "다음 임차인"],
        "expected_doc_types": ["사례집", "법령", "판례"],
        "min_score": 0.30,
    },
    {
        "id": "QA002",
        "category": "전세가율",
        "question": "전세가율이 90%를 초과하면 깡통전세 위험이 있나요?",
        "expected_keywords": ["깡통전세", "전세가율", "보증금", "위험"],
        "expected_doc_types": ["사례집", "법령"],
        "min_score": 0.28,
    },
    {
        "id": "QA003",
        "category": "등기부 권리관계",
        "question": "계약 전 등기부등본에서 근저당권과 가압류를 확인해야 하는 이유는?",
        "expected_keywords": ["근저당", "가압류", "등기부등본", "선순위"],
        "expected_doc_types": ["사례집", "법령", "판례"],
        "min_score": 0.28,
    },
    {
        "id": "QA004",
        "category": "임대인 신원",
        "question": "계약 시 임대인이 소유자와 동일인인지 어떻게 확인하나요?",
        "expected_keywords": ["소유자", "임대인", "신분증", "위임장"],
        "expected_doc_types": ["사례집", "법령"],
        "min_score": 0.25,
    },
    {
        "id": "QA005",
        "category": "특약",
        "question": "수리비 전액 임차인 부담 특약은 법적으로 문제가 없나요?",
        "expected_keywords": ["수리비", "임차인", "특약", "원상복구"],
        "expected_doc_types": ["사례집", "판례"],
        "min_score": 0.25,
    },
    {
        "id": "QA006",
        "category": "신탁",
        "question": "신탁 등기가 되어 있는 주택을 임차할 때 주의사항은?",
        "expected_keywords": ["신탁", "수익자", "임차권", "전세사기"],
        "expected_doc_types": ["사례집", "법령"],
        "min_score": 0.25,
    },
    {
        "id": "QA007",
        "category": "임차권등기",
        "question": "계약 종료 후 임차권등기명령을 신청하면 어떤 효력이 있나요?",
        "expected_keywords": ["임차권등기", "대항력", "우선변제", "신청"],
        "expected_doc_types": ["법령", "판례"],
        "min_score": 0.25,
    },
    {
        "id": "QA008",
        "category": "보증보험",
        "question": "HUG 전세보증보험 가입 조건과 보증 한도는 어떻게 되나요?",
        "expected_keywords": ["보증보험", "HUG", "한도", "가입"],
        "expected_doc_types": ["사례집", "법령"],
        "min_score": 0.22,
    },
]

# 계약서 진단용 샘플 계약 필드
SAMPLE_CONTRACT_FIELDS = {
    "address": "서울특별시 종로구 청운동 123-1",
    "housing_type": "연립다세대",
    "deposit_amount": 250000000,
    "exclusive_area_m2": 59.5,
    "floor": 3,
    "property_name": "청운빌라",
    "dong_name": "청운동",
}

SAMPLE_CONTRACT_KEYWORDS = ["전세", "보증금", "근저당", "특약", "수리비"]


# ═══════════════════════════════════════════════════════════════════════════════
# 2. 결과 데이터 클래스
# ═══════════════════════════════════════════════════════════════════════════════
@dataclass
class QAResult:
    qa_id: str
    category: str
    question: str
    retrieved_count: int
    scores: list[float]
    doc_types_found: list[str]
    keyword_hits: int
    keyword_total: int
    min_score_pass: bool
    latency_ms: float
    error: str | None = None

    @property
    def keyword_coverage(self) -> float:
        return self.keyword_hits / max(self.keyword_total, 1)

    @property
    def avg_score(self) -> float:
        return statistics.mean(self.scores) if self.scores else 0.0

    @property
    def top1_score(self) -> float:
        return self.scores[0] if self.scores else 0.0

    @property
    def passed(self) -> bool:
        return (
            self.error is None
            and self.keyword_coverage >= 0.5
            and self.min_score_pass
            and self.retrieved_count >= 3
        )


@dataclass
class AccuracyReport:
    total_qa: int = 0
    passed: int = 0
    failed: int = 0
    avg_keyword_coverage: float = 0.0
    avg_top1_score: float = 0.0
    avg_latency_ms: float = 0.0
    score_distribution: dict[str, int] = field(default_factory=dict)
    doc_type_coverage: dict[str, int] = field(default_factory=dict)
    dl_integrated: bool = False
    dl_pack_score: float = 0.0
    diagnose_risk_score: float | None = None
    diagnose_risk_level: str | None = None
    diagnose_dl_findings: int = 0
    details: list[dict[str, Any]] = field(default_factory=list)


# ═══════════════════════════════════════════════════════════════════════════════
# 3. 검증 함수들
# ═══════════════════════════════════════════════════════════════════════════════

def _load_vector_store() -> Any:
    """VectorStore 로드 (연결 실패 시 None)"""
    try:
        from rag_server.config import get_settings
        from rag_server.core.vector_store import VectorStore
        settings = get_settings()
        vs = VectorStore(settings)
        print("[VectorStore] ✓ 연결 성공")
        return vs
    except Exception as e:
        print(f"[VectorStore] ✗ 연결 실패: {e}")
        return None


def _load_rag_pipeline() -> Any:
    """RAGPipeline 로드 (연결 실패 시 None)"""
    try:
        from rag_server.config import get_settings
        from rag_server.core.vector_store import VectorStore
        from rag_server.core.graph_store import GraphStore
        from rag_server.core.rag_pipeline import RAGPipeline
        settings = get_settings()
        vs = VectorStore(settings)
        gs = GraphStore(settings)
        pipeline = RAGPipeline(settings, vs, gs)
        print("[RAGPipeline] ✓ 로드 성공")
        return pipeline
    except Exception as e:
        print(f"[RAGPipeline] ✗ 로드 실패: {e}")
        return None


def evaluate_single_qa(
    vector_store: Any,
    qa: dict[str, Any],
    verbose: bool = False,
) -> QAResult:
    """단일 Q&A 검색 품질 평가"""
    start = time.perf_counter()
    try:
        results = vector_store.similarity_search(
            query=qa["question"],
            k=10,
        )
        elapsed = (time.perf_counter() - start) * 1000

        scores = [float(r.get("score", 0.0)) for r in results]
        doc_types = [r.get("metadata", {}).get("doc_type", "unknown") for r in results]

        # 키워드 포함률: 상위 5개 문서 전체 텍스트에서 확인
        all_text = " ".join(r.get("content", "") for r in results[:5]).lower()
        keyword_hits = sum(
            1 for kw in qa["expected_keywords"]
            if kw.lower() in all_text
        )

        min_score_pass = (scores[0] if scores else 0.0) >= qa["min_score"]

        if verbose:
            print(f"\n  [{qa['id']}] {qa['category']} — retrieved={len(results)}, "
                  f"top1={(scores[0] if scores else 0):.3f}, "
                  f"kw={keyword_hits}/{len(qa['expected_keywords'])}")
            for i, r in enumerate(results[:3], 1):
                meta = r.get("metadata", {})
                print(f"    {i}. [{meta.get('doc_type','?')}] {meta.get('title','제목없음')[:40]} "
                      f"score={r.get('score', 0):.3f}")

        return QAResult(
            qa_id=qa["id"],
            category=qa["category"],
            question=qa["question"],
            retrieved_count=len(results),
            scores=scores,
            doc_types_found=doc_types,
            keyword_hits=keyword_hits,
            keyword_total=len(qa["expected_keywords"]),
            min_score_pass=min_score_pass,
            latency_ms=elapsed,
        )
    except Exception as e:
        elapsed = (time.perf_counter() - start) * 1000
        return QAResult(
            qa_id=qa["id"],
            category=qa["category"],
            question=qa["question"],
            retrieved_count=0,
            scores=[],
            doc_types_found=[],
            keyword_hits=0,
            keyword_total=len(qa["expected_keywords"]),
            min_score_pass=False,
            latency_ms=elapsed,
            error=str(e),
        )


def evaluate_dl_bridge() -> tuple[bool, float, int]:
    """DL 브리지 동작 확인 — (성공여부, pack_score, findings_count)"""
    try:
        from common.tools.dl_market_bridge import run_dl_analysis
        pack, findings = run_dl_analysis(SAMPLE_CONTRACT_FIELDS)
        score = pack.quality.score
        print(f"[DL Bridge] ✓ ContextPack score={score:.2f}, findings={len(findings)}")
        return True, score, len(findings)
    except Exception as e:
        print(f"[DL Bridge] ✗ 오류: {e}")
        return False, 0.0, 0


async def evaluate_diagnose_pipeline(pipeline: Any) -> dict[str, Any]:
    """RAGPipeline.diagnose() 엔드투엔드 검증"""
    try:
        result = await pipeline.diagnose(
            session_id="test_accuracy",
            contract_text="서울특별시 종로구 청운동 123-1 연립다세대 전세계약. "
                          "보증금 2억 5천만원. 근저당권 설정 1억원. "
                          "특약: 수리비는 임차인이 전액 부담. 보증금은 다음 임차인 입주 후 반환.",
            contract_keywords=SAMPLE_CONTRACT_KEYWORDS,
        )
        print(f"[Diagnose] ✓ risk_score={result.get('risk_score')}, "
              f"level={result.get('risk_level')}, "
              f"factors={len(result.get('risk_factors', []))}")
        return result
    except Exception as e:
        print(f"[Diagnose] ✗ 오류: {e}")
        return {}


def compute_score_distribution(all_scores: list[float]) -> dict[str, int]:
    dist = {"0.0~0.2": 0, "0.2~0.4": 0, "0.4~0.6": 0, "0.6~0.8": 0, "0.8~1.0": 0}
    for s in all_scores:
        if s < 0.2:
            dist["0.0~0.2"] += 1
        elif s < 0.4:
            dist["0.2~0.4"] += 1
        elif s < 0.6:
            dist["0.4~0.6"] += 1
        elif s < 0.8:
            dist["0.6~0.8"] += 1
        else:
            dist["0.8~1.0"] += 1
    return dist


# ═══════════════════════════════════════════════════════════════════════════════
# 4. 메인 검증 흐름
# ═══════════════════════════════════════════════════════════════════════════════

async def run_accuracy_test(verbose: bool = False) -> AccuracyReport:
    report = AccuracyReport()
    print("\n" + "=" * 60)
    print("  RAG 정확도 · 신뢰도 검증 시작")
    print("=" * 60)

    # ── Step 1: VectorStore 연결 ──────────────────────────────
    print("\n[Step 1] VectorStore 연결 확인")
    vector_store = _load_vector_store()

    if vector_store is None:
        print("  ⚠ VectorStore 없음 — 검색 품질 테스트 스킵")
    else:
        # ── Step 2: Q&A 검색 품질 평가 ───────────────────────
        print(f"\n[Step 2] Q&A 검색 품질 평가 ({len(KNOWN_QA)}개 문항)")
        qa_results: list[QAResult] = []
        for qa in KNOWN_QA:
            result = evaluate_single_qa(vector_store, qa, verbose=verbose)
            qa_results.append(result)

        passed_count = sum(1 for r in qa_results if r.passed)
        all_scores_flat = [s for r in qa_results for s in r.scores]
        all_kw_coverage = [r.keyword_coverage for r in qa_results]
        all_latencies = [r.latency_ms for r in qa_results]
        all_doc_types_flat = [dt for r in qa_results for dt in r.doc_types_found]

        doc_type_counts: dict[str, int] = {}
        for dt in all_doc_types_flat:
            doc_type_counts[dt] = doc_type_counts.get(dt, 0) + 1

        report.total_qa = len(qa_results)
        report.passed = passed_count
        report.failed = len(qa_results) - passed_count
        report.avg_keyword_coverage = statistics.mean(all_kw_coverage) if all_kw_coverage else 0.0
        report.avg_top1_score = statistics.mean([r.top1_score for r in qa_results]) if qa_results else 0.0
        report.avg_latency_ms = statistics.mean(all_latencies) if all_latencies else 0.0
        report.score_distribution = compute_score_distribution(all_scores_flat)
        report.doc_type_coverage = doc_type_counts
        report.details = [
            {
                "id": r.qa_id,
                "category": r.category,
                "passed": r.passed,
                "keyword_coverage": round(r.keyword_coverage, 2),
                "top1_score": round(r.top1_score, 3),
                "avg_score": round(r.avg_score, 3),
                "retrieved": r.retrieved_count,
                "latency_ms": round(r.latency_ms, 1),
                "error": r.error,
            }
            for r in qa_results
        ]

        print(f"\n  ✅ 통과: {passed_count}/{len(qa_results)}")
        print(f"  📊 평균 키워드 커버리지: {report.avg_keyword_coverage:.1%}")
        print(f"  📊 평균 TOP-1 유사도:   {report.avg_top1_score:.3f}")
        print(f"  ⏱  평균 검색 레이턴시:  {report.avg_latency_ms:.1f}ms")
        print(f"  📁 점수 분포: {report.score_distribution}")
        print(f"  📂 doc_type 분포: {report.doc_type_coverage}")

        # 실패 항목 상세 출력
        failed_items = [r for r in qa_results if not r.passed]
        if failed_items:
            print(f"\n  ❌ 실패 항목 ({len(failed_items)}개):")
            for r in failed_items:
                reason = []
                if r.error:
                    reason.append(f"오류: {r.error}")
                else:
                    if r.keyword_coverage < 0.5:
                        reason.append(f"키워드 커버리지 낮음 ({r.keyword_coverage:.0%})")
                    if not r.min_score_pass:
                        reason.append(f"TOP-1 점수 낮음 ({r.top1_score:.3f})")
                    if r.retrieved_count < 3:
                        reason.append(f"검색 결과 부족 ({r.retrieved_count}건)")
                print(f"    [{r.qa_id}] {r.category}: {', '.join(reason)}")

    # ── Step 3: DL 브리지 검증 ────────────────────────────────
    print("\n[Step 3] 딥러닝 브리지 (dl_market_bridge) 검증")
    dl_ok, dl_score, dl_findings = evaluate_dl_bridge()
    report.dl_integrated = dl_ok
    report.dl_pack_score = dl_score
    report.diagnose_dl_findings = dl_findings

    # ── Step 4: RAGPipeline.diagnose() 엔드투엔드 ─────────────
    print("\n[Step 4] RAGPipeline.diagnose() 엔드투엔드 검증")
    pipeline = _load_rag_pipeline()
    if pipeline:
        diag = await evaluate_diagnose_pipeline(pipeline)
        report.diagnose_risk_score = diag.get("risk_score")
        report.diagnose_risk_level = diag.get("risk_level")

        factors = diag.get("risk_factors", [])
        refs = diag.get("references", [])
        print(f"  위험요소 {len(factors)}개, RAG 참조 {len(refs)}개")
    else:
        print("  ⚠ RAGPipeline 미연결 — 진단 파이프라인 테스트 스킵")

    return report


# ═══════════════════════════════════════════════════════════════════════════════
# 5. 리포트 출력
# ═══════════════════════════════════════════════════════════════════════════════

def print_summary(report: AccuracyReport) -> None:
    print("\n" + "=" * 60)
    print("  검증 결과 요약")
    print("=" * 60)

    if report.total_qa > 0:
        pass_rate = report.passed / report.total_qa
        grade = "🟢 우수" if pass_rate >= 0.8 else ("🟡 보통" if pass_rate >= 0.5 else "🔴 미흡")
        print(f"\n  Q&A 통과율:         {report.passed}/{report.total_qa} ({pass_rate:.0%}) {grade}")
        print(f"  평균 키워드 커버리지: {report.avg_keyword_coverage:.1%}")
        print(f"  평균 TOP-1 유사도:   {report.avg_top1_score:.3f}")
        print(f"  평균 검색 레이턴시:  {report.avg_latency_ms:.1f}ms")
    else:
        print("  Q&A 검색 테스트: 스킵됨 (VectorStore 미연결)")

    dl_status = "✓ 연동됨" if report.dl_integrated else "✗ 연동 실패"
    print(f"\n  DL 브리지 상태:     {dl_status}")
    if report.dl_integrated:
        print(f"  DL ContextPack 신뢰도: {report.dl_pack_score:.2f}")
        print(f"  DL RiskFinding 수:     {report.diagnose_dl_findings}개")

    if report.diagnose_risk_score is not None:
        print(f"\n  진단 파이프라인:    위험점수={report.diagnose_risk_score}, 등급={report.diagnose_risk_level}")

    print("\n" + "-" * 60)

    # 개선 권고
    suggestions = []
    if report.total_qa > 0:
        if report.avg_top1_score < 0.35:
            suggestions.append("유사도가 낮음 — 임베딩 모델 업그레이드(text-embedding-3-large) 또는 청크 크기 조정 검토")
        if report.avg_keyword_coverage < 0.6:
            suggestions.append("키워드 커버리지 낮음 — RAG_TOP_K 증가 또는 쿼리 확장(HyDE) 적용 검토")
        low_doc_types = [dt for dt in ["사례집", "법령", "판례"] if report.doc_type_coverage.get(dt, 0) == 0]
        if low_doc_types:
            suggestions.append(f"미검색 doc_type 존재: {low_doc_types} — 해당 문서 임베딩 확인 필요")
    if not report.dl_integrated:
        suggestions.append("DL 브리지 비연동 — deep_learning/risk_inference.py 경로 및 DB 연결 확인")

    if suggestions:
        print("  📋 개선 권고사항:")
        for i, s in enumerate(suggestions, 1):
            print(f"  {i}. {s}")
    else:
        print("  ✅ 모든 항목 기준 충족 — 추가 개선 불필요")

    print("=" * 60)


def save_report(report: AccuracyReport, path: Path) -> None:
    data = asdict(report)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n  📄 상세 리포트 저장: {path}")


# ═══════════════════════════════════════════════════════════════════════════════
# 6. CLI 진입점
# ═══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    parser = argparse.ArgumentParser(description="RAG 정확도 · 신뢰도 검증")
    parser.add_argument("--verbose", "-v", action="store_true", help="상세 검색 결과 출력")
    parser.add_argument("--save-report", "-s", action="store_true", help="JSON 리포트 저장")
    parser.add_argument("--report-path", default="rag_accuracy_report.json", help="리포트 저장 경로")
    args = parser.parse_args()

    report = asyncio.run(run_accuracy_test(verbose=args.verbose))
    print_summary(report)

    if args.save_report:
        save_report(report, Path(args.report_path))


if __name__ == "__main__":
    main()
