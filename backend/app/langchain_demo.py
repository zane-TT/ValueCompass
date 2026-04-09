from __future__ import annotations

import json
import os

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI

from .langchain_tools import compare_peer_snapshot, lookup_company_industry, lookup_industry_peers
from .models import AgentDemoResponse, AgentToolCall


@tool
def get_company_industry(ticker: str) -> dict:
    """
    获取公司所属行业。

    适合在模型需要判断“该用哪种估值框架”之前调用。
    """
    return lookup_company_industry(ticker)


@tool
def get_industry_peers_by_ticker(ticker: str) -> dict:
    """
    获取某只股票的同行列表。

    适合在模型需要做“同行对比”或“找可比公司”时调用。
    """
    return lookup_industry_peers(ticker)


@tool
def get_company_snapshot(ticker: str) -> dict:
    """
    获取公司的一页式财务和估值快照。

    这个 tool 只返回结构化事实，不直接给投资结论，
    让模型自己在调用完 tool 后总结。
    """
    return compare_peer_snapshot(ticker)


TOOLS = [
    get_company_industry,
    get_industry_peers_by_ticker,
    get_company_snapshot,
]


def run_langchain_openai_demo(question: str, ticker: str | None = None) -> AgentDemoResponse:
    api_key = os.getenv("OPENAI_API_KEY")
    model_name = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")

    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set.")

    llm = ChatOpenAI(model=model_name, temperature=0)
    llm_with_tools = llm.bind_tools(TOOLS)

    system_prompt = (
        "You are the ValueCompass demo agent. "
        "Use tools whenever the answer depends on industry classification, peers, or company snapshot facts. "
        "Do not invent financial data. "
        "If a ticker is provided, prefer using it in tool calls before making conclusions. "
        "Keep the final answer practical and explain which tools were used."
    )

    user_prompt = question
    if ticker:
        user_prompt += f"\n\nTarget ticker: {ticker}"

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt),
    ]

    first_response = llm_with_tools.invoke(messages)
    messages.append(first_response)

    tool_calls: list[AgentToolCall] = []
    tool_map = {tool_item.name: tool_item for tool_item in TOOLS}

    for tool_call in first_response.tool_calls:
        tool_name = tool_call["name"]
        tool_args = tool_call.get("args", {})
        tool_result = tool_map[tool_name].invoke(tool_args)
        tool_calls.append(
            AgentToolCall(
                name=tool_name,
                args=tool_args,
                result=tool_result,
            )
        )
        messages.append(
            ToolMessage(
                content=json.dumps(tool_result, ensure_ascii=False),
                tool_call_id=tool_call["id"],
                name=tool_name,
            )
        )

    final_response = llm_with_tools.invoke(messages)
    final_text = final_response.content if isinstance(final_response.content, str) else str(final_response.content)

    return AgentDemoResponse(
        answer=final_text,
        model=model_name,
        tool_calls=tool_calls,
    )
