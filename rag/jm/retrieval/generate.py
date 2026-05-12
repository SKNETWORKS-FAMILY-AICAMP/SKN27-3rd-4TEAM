from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from ..core.config import load_config
from .search import SearchHit, search


@dataclass
class GenerateResult:
    answer: str
    hits: List[SearchHit]

# RAG 답변 생성
def generate_answer(
    query: str,
    k: int = 5,
    where: Optional[Dict[str, Any]] = None,
) -> GenerateResult:
    """사용자 질문에 대해 벡터 검색을 수행하고, 그 결과를 바탕으로 LLM을 사용해 답변을 생성합니다."""
    
    # 문서 검색
    hits = search(query=query, k=k, where=where)
    
    # 컨텍스트 텍스트 구성
    context_text = "\n\n".join(
        [f"[참고 문서 {i+1}]\n{h.content}" for i, h in enumerate(hits)]
    )
    
    # LLM 설정 및 호출
    cfg = load_config()
    llm = ChatOpenAI(model=cfg.llm_model, temperature=0.0)
    
    system_prompt = (
        "당신은 전세사기 예방 및 관련 법률, 정책 등에 대해 답변하는 전문가 어시스턴트입니다.\n"
        "제공된 참고 문서(Context)를 바탕으로 사용자의 질문에 정확하고 상세하게 답변하세요.\n"
        "제공된 참고 문서에서 답변을 찾을 수 없다면, 임의로 지어내지 말고 모른다고 명확하게 답변하세요.\n"
        "답변 시 어느 참고 문서를 기반으로 했는지 적절히 언급해주면 좋습니다."
    )
    
    user_prompt = "[참고 문서]\n{context}\n\n[질문]\n{query}"
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        ("human", user_prompt),
    ])
    
    chain = prompt | llm | StrOutputParser()
    answer = chain.invoke({"context": context_text, "query": query})
    
    return GenerateResult(answer=answer, hits=hits)
