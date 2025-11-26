"""
LangGraph Brain - StateGraph with OpenRouter Gemini 3 Pro
"""

import os
from typing import Annotated, TypedDict, Sequence
from langchain_openai import ChatOpenAI
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, ToolMessage
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from langgraph.graph.message import add_messages

from .tools import get_all_tools


os.environ.setdefault("LANGCHAIN_TRACING_V2", "true")
os.environ.setdefault("LANGCHAIN_PROJECT", "payouts-automation")


class AgentState(TypedDict):
    """State for the agent graph"""
    messages: Annotated[Sequence[BaseMessage], add_messages]
    user_id: str


def create_llm():
    """Create the LLM using OpenRouter with Gemini 2.0 Flash (stable for tool calling)"""
    api_key = os.getenv("OPENROUTERA")
    if not api_key:
        raise ValueError("OPENROUTERA environment variable not set")
    
    return ChatOpenAI(
        model="google/gemini-2.0-flash-001",
        api_key=api_key,
        base_url="https://openrouter.ai/api/v1",
        temperature=0.1
    )


def create_agent_graph():
    """
    Create the LangGraph agent with tools for controlling services
    
    Returns:
        CompiledStateGraph ready to process messages
    """
    tools = get_all_tools()
    llm = create_llm()
    llm_with_tools = llm.bind_tools(tools)
    
    def should_continue(state: AgentState) -> str:
        """Determine if we should continue to tools or end"""
        messages = state["messages"]
        last_message = messages[-1]
        
        if hasattr(last_message, 'tool_calls') and last_message.tool_calls:
            return "tools"
        return END
    
    def call_model(state: AgentState) -> dict:
        """Call the LLM with the current messages"""
        messages = state["messages"]
        
        system_prompt = """You are an AI assistant that helps manage invoices, vendors, and subscriptions for a financial automation system.

You have access to these powerful tools:

1. **Gmail Tools**:
   - search_gmail_invoices: Search Gmail for invoice/receipt emails

2. **NetSuite Tools**:
   - search_netsuite_vendor: Find vendors by name, email, or tax ID
   - create_netsuite_vendor: Create a new vendor in NetSuite
   - create_netsuite_bill: Create a vendor bill/invoice in NetSuite
   - get_bill_status: Check the status of a bill

3. **Vendor Matching**:
   - match_vendor_to_database: Use AI to match invoice vendor names to our database

4. **Analytics**:
   - run_bigquery: Execute SQL queries on the data warehouse
   - get_subscription_summary: Get SaaS subscription analytics

When helping users:
- Be proactive in using tools to get information
- Explain what you're doing and why
- If a task requires multiple steps, break it down clearly
- Always confirm destructive actions before proceeding

Available BigQuery tables:
- vendors_ai.global_vendors: Master vendor database (vendor_id, name, aliases, tax_ids, etc.)
- vendors_ai.subscription_vendors: SaaS subscription vendors
- vendors_ai.subscription_events: Subscription payment events (vendor_name, amount, currency, payment_date)
- vendors_ai.netsuite_events: NetSuite sync events"""

        from langchain_core.messages import SystemMessage
        full_messages = [SystemMessage(content=system_prompt)] + list(messages)
        
        response = llm_with_tools.invoke(full_messages)
        return {"messages": [response]}
    
    tool_node = ToolNode(tools)
    
    workflow = StateGraph(AgentState)
    
    workflow.add_node("agent", call_model)
    workflow.add_node("tools", tool_node)
    
    workflow.set_entry_point("agent")
    
    workflow.add_conditional_edges(
        "agent",
        should_continue,
        {
            "tools": "tools",
            END: END
        }
    )
    
    workflow.add_edge("tools", "agent")
    
    return workflow.compile()


def run_agent(message: str, user_id: str = "default") -> dict:
    """
    Run the agent with a user message and return the response with tools used
    
    Args:
        message: The user's message/question
        user_id: User ID for tracking
        
    Returns:
        Dict with 'response' (text) and 'tools_used' (list of tool names)
    """
    graph = create_agent_graph()
    
    initial_state = {
        "messages": [HumanMessage(content=message)],
        "user_id": user_id
    }
    
    tools_used = []
    
    try:
        result = graph.invoke(initial_state)
        
        messages = result.get("messages", [])
        
        for msg in messages:
            if isinstance(msg, AIMessage) and getattr(msg, 'tool_calls', None):
                for tool_call in msg.tool_calls:
                    tool_name = tool_call.get("name")
                    if tool_name and tool_name not in tools_used:
                        tools_used.append(tool_name)
        
        response_text = "I processed your request but have no additional response."
        for msg in reversed(messages):
            if isinstance(msg, AIMessage) and msg.content:
                if not getattr(msg, 'tool_calls', None):
                    response_text = msg.content
                    break
        
        return {
            "response": response_text,
            "tools_used": tools_used
        }
        
    except Exception as e:
        return {
            "response": f"Error running agent: {str(e)}",
            "tools_used": tools_used
        }


def stream_agent(message: str, user_id: str = "default"):
    """
    Stream the agent's response for real-time output
    
    Args:
        message: The user's message/question
        user_id: User ID for tracking
        
    Yields:
        Streaming chunks of the agent's response
    """
    graph = create_agent_graph()
    
    initial_state = {
        "messages": [HumanMessage(content=message)],
        "user_id": user_id
    }
    
    try:
        for event in graph.stream(initial_state):
            for node_name, node_output in event.items():
                if node_name == "agent":
                    messages = node_output.get("messages", [])
                    for msg in messages:
                        if isinstance(msg, AIMessage):
                            if msg.content:
                                yield {
                                    "type": "content",
                                    "content": msg.content
                                }
                            if getattr(msg, 'tool_calls', None):
                                for tool_call in msg.tool_calls:
                                    yield {
                                        "type": "tool_call",
                                        "tool": tool_call.get("name"),
                                        "args": tool_call.get("args", {})
                                    }
                elif node_name == "tools":
                    messages = node_output.get("messages", [])
                    for msg in messages:
                        if isinstance(msg, ToolMessage):
                            yield {
                                "type": "tool_result",
                                "tool": msg.name,
                                "content": msg.content[:500] if len(msg.content) > 500 else msg.content
                            }
                            
    except Exception as e:
        yield {"type": "error", "content": str(e)}
