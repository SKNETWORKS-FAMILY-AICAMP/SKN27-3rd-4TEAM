# rag/jm/agent/supervisor.py
# 질문을 보고 필요한 도구를 선택하는 간단한 LangGraph Supervisor입니다.

from __future__ import annotations

import operator
from typing import Annotated, List, TypedDict

from langchain_core.messages import BaseMessage, HumanMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph
from langgraph.prebuilt import ToolNode

from ..core.config import load_config
from .tools import search_documents


class AgentState(TypedDict):
    """Supervisor 그래프에서 사용하는 상태 타입입니다."""

    messages: Annotated[List[BaseMessage], operator.add]
    next: str


def create_supervisor(llm: ChatOpenAI, tools: list):
    """주어진 LLM/도구 목록으로 supervisor 노드를 생성합니다."""

    tool_names = [t.name for t in tools]
    options = ["FINISH"] + tool_names

    system_prompt = (
        "너는 사용자의 질문을 해결하기 위해 적절한 도구를 선택하는 관리자야.\n"
        "문서 근거가 필요하면 search_documents를 호출하고, 충분한 정보가 있으면 FINISH로 종료해.\n"
        f"선택 가능한 옵션: {options}"
    )

    def supervisor_node(state: AgentState):
        """현재 메시지를 보고 다음에 실행할 도구를 결정합니다."""

        messages = [{"role": "system", "content": system_prompt}] + state["messages"]
        response = llm.bind_tools(tools).invoke(messages)

        if response.tool_calls:
            return {
                "next": response.tool_calls[0]["name"],
                "messages": [response],
            }

        return {
            "next": "FINISH",
            "messages": [response],
        }

    return supervisor_node


def get_agent_graph():
    """Supervisor + ToolNode로 구성된 LangGraph를 생성합니다."""

    cfg = load_config()
    llm = ChatOpenAI(model=cfg.llm_model, temperature=0)
    tools = [search_documents]

    workflow = StateGraph(AgentState)
    workflow.add_node("supervisor", create_supervisor(llm, tools))
    workflow.add_node("tools", ToolNode(tools))
    workflow.add_edge("tools", "supervisor")
    workflow.add_conditional_edges(
        "supervisor",
        lambda x: x["next"],
        {
            "search_documents": "tools",
            "FINISH": END,
        },
    )
    workflow.set_entry_point("supervisor")
    return workflow.compile()


def run_agent(query: str):
    """Supervisor 그래프를 실행해 최종 답변만 반환합니다."""

    graph = get_agent_graph()
    final_state = graph.invoke({"messages": [HumanMessage(content=query)]})
    return final_state["messages"][-1].content
