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
    messages: Annotated[List[BaseMessage], operator.add]
    next: str


def create_supervisor(llm: ChatOpenAI, tools: list):
    tool_names = [t.name for t in tools]
    options = ["FINISH"] + tool_names

    system_prompt = (
        "당신은 사용자의 질문을 해결하기 위해 적절한 도구를 선택하는 관리자입니다.\n"
        "문서 근거가 필요하면 search_documents를 사용하고, 충분한 정보가 있으면 FINISH로 종료하세요.\n"
        f"선택 가능한 항목: {options}"
    )

    def supervisor_node(state: AgentState):
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
    cfg = load_config()
    if cfg.llm_provider != "openai":
        raise ValueError("agent 명령은 현재 OpenAI tool-calling 모델만 지원합니다. 무료 실행은 generate + ollama를 사용하세요.")

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
    graph = get_agent_graph()
    final_state = graph.invoke({"messages": [HumanMessage(content=query)]})
    return final_state["messages"][-1].content
