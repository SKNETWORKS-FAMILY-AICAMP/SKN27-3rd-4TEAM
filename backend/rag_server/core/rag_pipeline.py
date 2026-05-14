"""
전세계약 위험 진단 에이전트 - RAG 파이프라인 오케스트레이터
VectorStore + GraphStore + LLM 통합 → 최종 답변/진단 생성
"""

from __future__ import annotations
import json
from typing import Any

from langchain_core.messages import HumanMessage, AIMessage
from langsmith import traceable

from rag_server.config import Settings
from rag_server.core.vector_store import VectorStore
from rag_server.core.graph_store import GraphStore
from rag_server.core.llm import build_rag_chain, build_diagnosis_chain
from rag_server.models.schemas import RagReference, RiskFactor

MIN_FORCED_RERANK_SCORE = 0.12
FORCED_RERANK_SCORE_RATIO = 0.45


def _first_metadata_value(metadata: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = metadata.get(key)
        if value not in (None, "", [], {}):
            return value
    return None


def _source_id_from_file_chunk(metadata: dict[str, Any]) -> str | None:
    file_name = metadata.get("file_name") or metadata.get("title")
    chunk_index = metadata.get("chunk_index")
    if file_name not in (None, "") and chunk_index not in (None, ""):
        return f"{file_name}#chunk-{chunk_index}"
    return None


def _extract_query_terms(question: str) -> list[str]:
    terms = []
    for token in question.replace("?", " ").replace("!", " ").split():
        cleaned = token.strip(" ,.;:()[]{}\"'")
        if len(cleaned) >= 2:
            terms.append(cleaned)
    return terms[:8]


def _explicit_doc_type_order(question: str) -> list[str]:
    order: list[str] = []
    if any(token in question for token in ["법령", "법률", "조문", "주택임대차보호법", "민법"]):
        order.append("법령")
    if any(token in question for token in ["판례", "판결", "사건번호", "법원"]):
        order.append("판례")
    if any(token in question for token in ["사례", "사례집", "피해사례", "체크리스트", "가이드"]):
        order.append("사례집")

    for doc_type in ["사례집", "법령", "판례"]:
        if doc_type not in order:
            order.append(doc_type)
    return order if order != ["사례집", "법령", "판례"] else []


def _doc_type_boosts_for_question(question: str) -> dict[str, float]:
    boosts: dict[str, float] = {}
    if any(token in question for token in ["법령", "법률", "조문", "주택임대차보호법", "민법", "공인중개사법"]):
        boosts["법령"] = 0.22
    if any(token in question for token in ["대항력", "우선변제", "확정일자", "전입신고"]):
        boosts["법령"] = max(boosts.get("법령", 0.0), 0.16)
    if any(token in question for token in ["판례", "판결", "사건번호", "법원"]):
        boosts["판례"] = 0.18
    if any(token in question for token in ["사례", "사례집", "피해사례", "체크리스트", "가이드"]):
        boosts["사례집"] = 0.12
    return boosts


def _forced_pick_threshold(ranked: list[dict[str, Any]]) -> float:
    if not ranked:
        return MIN_FORCED_RERANK_SCORE
    best_score = max(float(item.get("rerank_score", 0.0)) for item in ranked)
    return round(max(MIN_FORCED_RERANK_SCORE, best_score * FORCED_RERANK_SCORE_RATIO), 4)


def _rerank_score(result: dict[str, Any], search_plan: dict[str, Any]) -> float:
    base_score = float(result.get("score", 0.0))
    metadata = result.get("metadata") or {}
    doc_type = str(metadata.get("doc_type") or "")
    title = str(metadata.get("title") or metadata.get("file_name") or "")
    content = str(result.get("content") or "")
    haystack = f"{title}\n{content}"

    score = base_score
    boost_terms = search_plan.get("boost_terms") or []
    must_terms = search_plan.get("must_terms") or []
    doc_type_boosts = search_plan.get("doc_type_boosts") or {}

    score += float(doc_type_boosts.get(doc_type, 0.0))

    matched_boosts = sum(1 for term in boost_terms if term and term in haystack)
    score += min(0.18, matched_boosts * 0.035)

    if must_terms:
        matched_musts = sum(1 for term in must_terms if term and term in haystack)
        if matched_musts == 0:
            score -= 0.18
        elif matched_musts < len(must_terms):
            score -= 0.06
        else:
            score += 0.08

    if any(token in title for token in ["본문바로출력", "제목없음", "미상"]):
        score -= 0.12
    if doc_type == "법령" and any(token in content[:500] for token in ["부칙", "다른 법률의 개정", "생략"]):
        score -= 0.08
    if len(content.strip()) < 120:
        score -= 0.08
    if content.count("\n") > 20 and len(content.strip()) < 500:
        score -= 0.04

    return round(max(0.0, min(1.0, score)), 4)


class RAGPipeline:
    def __init__(self, settings: Settings, vector_store: VectorStore, graph_store: GraphStore):
        self._settings     = settings
        self._vector_store = vector_store
        self._graph_store  = graph_store
        self._rag_chain    = build_rag_chain(settings)
        self._diag_chain   = build_diagnosis_chain(settings)

    # ── 일반 RAG 채팅 ─────────────────────────────────────

    @traceable(name="rag_chat")
    async def chat(self, session_id: str, question: str, history: list[dict]) -> dict[str, Any]:
        search_plan = self._build_search_plan(question)
        raw_results = self._search_with_plan(search_plan)
        graph_results = self._graph_context_for_question(question)
        context_text = self._format_context(raw_results)
        graph_context_text = self._format_graph_context(graph_results)
        if graph_context_text:
            context_text = f"{context_text}\n\n---\n\n{graph_context_text}"

        lc_history = [
            HumanMessage(content=m["content"]) if m["role"] == "user"
            else AIMessage(content=m["content"])
            for m in history
        ]

        response = await self._rag_chain.ainvoke({
            "context": context_text, "history": lc_history, "question": question,
        })
        return {
            "answer": response.content if hasattr(response, "content") else str(response),
            "references": self._build_references(raw_results) + self._build_graph_references(graph_results),
            # graph_context: ChatAgentService → answer_writer 에서 사용
            "graph_context": self._build_graph_context_items(graph_results),
        }

    # ── 계약서 진단 ───────────────────────────────────────

    @traceable(name="contract_diagnosis")
    async def diagnose(
        self, session_id: str, contract_text: str, contract_keywords: list[str],
    ) -> dict[str, Any]:
        search_query = f"전세계약 위험 {' '.join(contract_keywords[:5])}"
        raw_results  = self._vector_store.similarity_search(query=search_query, k=self._settings.RAG_TOP_K)

        graph_risks: list[dict] = []
        try:
            graph_risks = self._graph_store.get_risk_factors_by_keywords(contract_keywords)
        except Exception as e:
            print(f"[GraphStore] 조회 실패 (Neo4j 미연결?): {e}")
            graph_risks = self._get_fallback_risk_factors()

        response = await self._diag_chain.ainvoke({
            "context":       self._format_context(raw_results[:4], max_chars_per_doc=700),
            "risk_factors":  json.dumps(graph_risks[:6], ensure_ascii=False),
            "contract_text": contract_text[:2500],
        })

        raw_answer = response.content if hasattr(response, "content") else str(response)
        parsed = self._parse_diagnosis_response(raw_answer, graph_risks)
        parsed["references"] = self._build_references(raw_results)
        return parsed

    # ── 내부 헬퍼 ─────────────────────────────────────────

    def _format_context(self, results: list[dict], max_chars_per_doc: int = 1200) -> str:
        if not results:
            return "관련 문서를 찾지 못했습니다."
        parts = []
        for i, r in enumerate(results, 1):
            meta  = r.get("metadata", {})
            content = str(r.get("content", ""))[:max_chars_per_doc]
            r = {**r, "content": content}
            parts.append(
                f"[{i}] [{meta.get('doc_type','문서')}] {meta.get('title','제목없음')} "
                f"(유사도: {r.get('score', 0):.2f})\n{r['content']}"
            )
        return "\n\n---\n\n".join(parts)

    def _graph_context_for_question(self, question: str) -> list[dict[str, Any]]:
        if not self._graph_store:
            return []
        try:
            return self._graph_store.get_context_by_question(question, limit=3)
        except Exception:
            return []

    def _format_graph_context(self, graph_results: list[dict[str, Any]]) -> str:
        if not graph_results:
            return ""
        parts = ["[Neo4j 그래프 관계 근거]"]
        for index, item in enumerate(graph_results, 1):
            laws = ", ".join(str(value) for value in item.get("laws", []) if value) or "없음"
            cases = ", ".join(str(value) for value in item.get("cases", []) if value) or "없음"
            advice = str(item.get("advice") or "").strip()
            parts.append(
                f"[G{index}] {item.get('title') or item.get('source_id')}\n"
                f"- labels: {', '.join(item.get('labels', [])) or item.get('schema', 'graph')}\n"
                f"- summary: {item.get('summary') or ''}\n"
                f"- severity: {item.get('severity') or 'UNKNOWN'}\n"
                f"- laws: {laws}\n"
                f"- cases: {cases}\n"
                f"- advice: {advice}"
            )
        return "\n\n".join(parts)

    def _build_search_plan(self, question: str) -> dict[str, Any]:
        normalized = question.lower()
        explicit_doc_types = _explicit_doc_type_order(question)
        doc_type_boosts = _doc_type_boosts_for_question(question)
        if any(token in question for token in ["대항력", "우선변제", "확정일자", "전입신고", "주택임대차보호법"]):
            return {
                "question_type": "LEASE_PROTECTION_LAW",
                "query": f"주택임대차보호법 대항력 우선변제권 확정일자 전입신고 조문 {question}",
                "doc_types": explicit_doc_types or ["법령", "사례집", "판례"],
                "must_terms": ["주택임대차보호법"],
                "boost_terms": ["제3조", "대항력", "주택의 인도", "주민등록", "전입신고", "다음 날", "확정일자", "우선변제권"],
                "doc_type_boosts": {"법령": max(doc_type_boosts.get("법령", 0.0), 0.24), **{k: v for k, v in doc_type_boosts.items() if k != "법령"}},
            }
        if any(token in question for token in ["다음 임차인", "보증금 반환", "반환 지연", "돌려준", "돌려받"]):
            return {
                "question_type": "DEPOSIT_RETURN",
                "query": "전세계약 특약 보증금 반환 다음 임차인 입주 이후 반환 지연 임대차 종료 동시이행 보증금반환청구",
                "doc_types": explicit_doc_types or ["사례집", "법령", "판례"],
                "must_terms": ["보증금", "반환"],
                "boost_terms": ["주택임대차보호법", "법령", "법", "다음 임차인", "입주", "지연", "동시이행", "계약 종료", "반환청구"],
                "doc_type_boosts": doc_type_boosts,
            }
        if any(token in question for token in ["특약", "수리비", "원상복구", "권리변동"]):
            return {
                "question_type": "SPECIAL_CLAUSE",
                "query": f"전세계약 특약 위험 임차인 불리한 조항 표준계약서 체크리스트 {question}",
                "doc_types": explicit_doc_types or ["사례집", "법령", "판례"],
                "must_terms": ["특약"],
                "boost_terms": ["임차인", "불리", "수리비", "원상복구", "권리변동", "보증금"],
                "doc_type_boosts": doc_type_boosts,
            }
        if any(token in question for token in ["신탁", "근저당", "가압류", "압류", "등기부", "임차권등기"]):
            return {
                "question_type": "REGISTRY_RIGHTS",
                "query": f"전세계약 등기부 권리관계 신탁 근저당 가압류 임차권등기 전세사기 {question}",
                "doc_types": explicit_doc_types or ["사례집", "법령", "판례"],
                "must_terms": [],
                "boost_terms": ["등기부", "신탁", "근저당", "가압류", "압류", "임차권등기", "권리관계"],
                "doc_type_boosts": doc_type_boosts,
            }
        if any(token in question for token in ["전세가율", "깡통전세", "시세", "보증보험", "hug"]) or "hug" in normalized:
            return {
                "question_type": "MARKET_RECOVERY",
                "query": f"깡통전세 전세가율 보증보험 보증금 회수 위험 전세사기 {question}",
                "doc_types": explicit_doc_types or ["사례집", "법령"],
                "must_terms": [],
                "boost_terms": ["깡통전세", "전세가율", "보증보험", "보증금", "회수", "HUG"],
                "doc_type_boosts": doc_type_boosts,
            }
        if any(token in question for token in ["대리인", "위임장", "소유자", "임대인", "신분증", "동명이인"]):
            return {
                "question_type": "IDENTITY_AUTHORITY",
                "query": f"전세계약 임대인 소유자 일치 대리인 위임장 신분증 확인 전세사기 {question}",
                "doc_types": explicit_doc_types or ["사례집", "법령", "판례"],
                "must_terms": [],
                "boost_terms": ["임대인", "소유자", "대리인", "위임장", "신분증", "동명이인"],
                "doc_type_boosts": doc_type_boosts,
            }
        return {
            "question_type": "GENERAL",
            "query": question,
            "doc_types": explicit_doc_types or ["사례집", "법령", "판례"],
            "must_terms": [],
            "boost_terms": _extract_query_terms(question),
            "doc_type_boosts": doc_type_boosts,
        }

    def _search_with_plan(self, search_plan: dict[str, Any]) -> list[dict]:
        query = search_plan["query"]
        doc_types = search_plan.get("doc_types") or []
        top_k = self._settings.RAG_TOP_K
        per_type_k = max(4, min(8, top_k * 2))

        results: list[dict] = []
        for doc_type in doc_types:
            results.extend(
                self._vector_store.similarity_search(
                    query=query,
                    k=per_type_k,
                    filter_doc_type=doc_type,
                )
            )

        if not results:
            results = self._vector_store.similarity_search(query=query, k=top_k)

        return self._dedupe_and_rank_results(results, limit=top_k, search_plan=search_plan)

    def _dedupe_and_rank_results(self, results: list[dict], limit: int, search_plan: dict[str, Any]) -> list[dict]:
        preferred_doc_types = search_plan.get("doc_types") or []
        deduped: dict[str, dict] = {}
        for result in results:
            meta = result.get("metadata", {})
            key = "|".join([
                str(meta.get("doc_type", "")),
                str(meta.get("title", "")),
                str(meta.get("file_name", "")),
                str(meta.get("chunk_index", "")),
                result.get("content", "")[:80],
            ])
            current = deduped.get(key)
            if current is None or float(result.get("score", 0.0)) > float(current.get("score", 0.0)):
                deduped[key] = result

        for item in deduped.values():
            item["rerank_score"] = _rerank_score(item, search_plan)

        ranked = sorted(deduped.values(), key=lambda item: float(item.get("rerank_score", 0.0)), reverse=True)
        if not preferred_doc_types:
            return ranked[:limit]

        selected: list[dict] = []
        selected_keys: set[int] = set()
        forced_threshold = _forced_pick_threshold(ranked)
        for doc_type in preferred_doc_types:
            for index, item in enumerate(ranked):
                if index in selected_keys:
                    continue
                if (
                    item.get("metadata", {}).get("doc_type") == doc_type
                    and float(item.get("rerank_score", 0.0)) >= forced_threshold
                ):
                    selected.append(item)
                    selected_keys.add(index)
                    break

        for index, item in enumerate(ranked):
            if len(selected) >= limit:
                break
            if index not in selected_keys:
                selected.append(item)
                selected_keys.add(index)
        return sorted(selected[:limit], key=lambda item: float(item.get("rerank_score", 0.0)), reverse=True)

    def _build_references(self, results: list[dict]) -> list[RagReference]:
        references: list[RagReference] = []
        for index, result in enumerate(results, 1):
            metadata = dict(result.get("metadata") or {})
            metadata["vector_score"] = float(result.get("score", 0.0))
            metadata["rerank_score"] = float(result.get("rerank_score", result.get("score", 0.0)))
            source_id = _first_metadata_value(
                metadata,
                "source_id",
                "row_id",
                "chunk_id",
                "id",
                "document_id",
                "doc_id",
                "case_number",
                "case_no",
                "사건번호",
            ) or _source_id_from_file_chunk(metadata) or f"rag-ref-{index}"
            references.append(
                RagReference(
                    source_id=str(source_id),
                    doc_type=str(metadata.get("doc_type") or "문서"),
                    title=str(metadata.get("title") or metadata.get("file_name") or "제목없음"),
                    chunk_text=result["content"][:700] + ("..." if len(result["content"]) > 700 else ""),
                    relevance_score=float(result.get("rerank_score", result.get("score", 0.0))),
                    metadata=metadata,
                )
            )
        return references

    def _build_graph_context_items(self, graph_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """graph_results → GraphContextItem dict 리스트 (ChatResponse.graph_context 용)."""
        items: list[dict[str, Any]] = []
        for item in graph_results:
            node   = str(item.get("title") or item.get("source_id") or "UNKNOWN")
            target = str(item.get("summary") or "")
            laws   = item.get("laws") or []
            relation = f"법령:{laws[0]}" if laws else str(item.get("schema") or "관계")
            items.append({"node": node, "relation": relation, "target": target})
        return items

    def _build_graph_references(self, graph_results: list[dict[str, Any]]) -> list[RagReference]:
        references: list[RagReference] = []
        for index, item in enumerate(graph_results, 1):
            source_id = str(item.get("source_id") or f"graph-ref-{index}")
            laws = ", ".join(str(value) for value in item.get("laws", []) if value)
            cases = ", ".join(str(value) for value in item.get("cases", []) if value)
            chunk_parts = [
                str(item.get("summary") or "").strip(),
                f"관련 법령: {laws}" if laws else "",
                f"관련 판례/사례: {cases}" if cases else "",
                f"대응 조언: {item.get('advice')}" if item.get("advice") else "",
            ]
            chunk_text = "\n".join(part for part in chunk_parts if part)
            if not chunk_text:
                chunk_text = str(item.get("title") or source_id)
            references.append(
                RagReference(
                    source_id=f"graph-{source_id}",
                    doc_type="GRAPH_RISK",
                    title=str(item.get("title") or source_id),
                    chunk_text=chunk_text[:700] + ("..." if len(chunk_text) > 700 else ""),
                    relevance_score=0.0,
                    metadata={
                        "provider": "neo4j",
                        "schema": item.get("schema"),
                        "labels": item.get("labels", []),
                        "severity": item.get("severity"),
                        "laws": item.get("laws", []),
                        "cases": item.get("cases", []),
                    },
                )
            )
        return references

    def _parse_diagnosis_response(self, raw: str, graph_risks: list[dict]) -> dict[str, Any]:
        import re

        # JSON 추출 시도 (코드블록 → 중괄호 객체 순서로)
        json_str = None
        m = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", raw)
        if m:
            json_str = m.group(1).strip()
        else:
            m = re.search(r"\{[\s\S]+\}", raw)
            if m:
                json_str = m.group(0).strip()

        if json_str:
            try:
                data = json.loads(json_str)
                risk_factors = [
                    RiskFactor(
                        factor_id=rf.get("factor_id", f"RF{i:03d}"),
                        category=rf.get("category", "기타"),
                        description=rf.get("description", ""),
                        severity=rf.get("severity", "MEDIUM"),
                        legal_basis=rf.get("legal_basis"),
                        advice=rf.get("advice", "전문가 상담 권고"),
                    )
                    for i, rf in enumerate(data.get("risk_factors", []), 1)
                ]
                # risk_factors가 비어있으면 graph_risks로 보완
                if not risk_factors and graph_risks:
                    risk_factors = self._risks_from_graph(graph_risks)

                return {
                    "risk_score": float(data.get("risk_score", 50)),
                    "risk_level": data.get("risk_level", "주의"),
                    "risk_factors": risk_factors,
                    "summary": data.get("summary", "진단을 완료했습니다."),
                }
            except Exception:
                pass

        return self._fallback_diagnosis(raw, graph_risks)

    def _risks_from_graph(self, graph_risks: list[dict]) -> list[RiskFactor]:
        return [
            RiskFactor(
                factor_id=r.get("factor_id", "RF000"),
                category=r.get("category", "기타"),
                description=r.get("description", ""),
                severity=r.get("severity", "MEDIUM"),
                legal_basis=(r.get("laws") or [None])[0],
                advice=r.get("advice", "전문가 상담 권고"),
            )
            for r in graph_risks[:10]
        ]

    def _fallback_diagnosis(self, summary: str, graph_risks: list[dict]) -> dict[str, Any]:
        # graph_risks가 비어있으면 기본 위험요소로 대체
        risks = graph_risks or self._get_fallback_risk_factors()
        risk_factors = self._risks_from_graph(risks)
        high = sum(1 for r in risks if r.get("severity") == "HIGH")
        med  = sum(1 for r in risks if r.get("severity") == "MEDIUM")
        score = min(100, high * 25 + med * 10)
        level = "위험" if score >= 80 else ("주의" if score >= 60 else "안전")

        # summary가 JSON 덩어리면 깔끔한 메시지로 대체
        clean_summary = summary.strip()
        if clean_summary.startswith("{") or clean_summary.startswith("```"):
            clean_summary = "계약서 분석을 완료했습니다. 상세 위험 요소를 확인하세요."

        return {
            "risk_score": float(score),
            "risk_level": level,
            "risk_factors": risk_factors,
            "summary": clean_summary[:1000],
        }

    def _get_fallback_risk_factors(self) -> list[dict]:
        return [
            {"factor_id": "RF001", "category": "전세가율",
             "description": "전세가율 80% 초과", "severity": "HIGH",
             "keywords": "전세가율 보증금", "advice": "시세 대비 전세금 비율 확인",
             "laws": ["주택임대차보호법 제3조의3"]},
            {"factor_id": "RF002", "category": "권리관계",
             "description": "근저당·가압류 과다", "severity": "HIGH",
             "keywords": "근저당 가압류", "advice": "등기부등본 열람 후 선순위 권리 확인",
             "laws": ["민법 제356조"]},
        ]
