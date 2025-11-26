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
        
        system_prompt = """You are Payouts AI - a SEMANTIC AI FIRST intelligent assistant for managing invoices, vendors, and subscriptions.

## CRITICAL: SEMANTIC AI FIRST PROTOCOL
You MUST follow this priority order for EVERY request:

1. **ALWAYS CHECK DATABASE FIRST** - Before ANY external service, use `search_database_first` to look for existing data.
   - This searches vendors, invoices, and subscriptions in BigQuery
   - If data exists, return it immediately - NO external calls needed!

2. **CHECK SERVICE STATUS** - Before using Gmail or external APIs, check if they're connected:
   - Use `check_gmail_status` before `search_gmail_invoices`
   - If not connected, the tool returns an HTML button the user can click to connect

3. **ONLY THEN USE EXTERNAL SERVICES** - If database is empty AND service is connected

## Your Tools (in priority order):

### Database First (ALWAYS START HERE):
- search_database_first: Search local database for vendors, invoices, subscriptions
- run_bigquery: Execute custom SQL queries

### Service Status:
- check_gmail_status: Check Gmail connection, get connect button if needed

### Gmail (after checking status):
- search_gmail_invoices: Search Gmail for invoices/receipts

### NetSuite:
- search_netsuite_vendor: Find vendors in NetSuite
- create_netsuite_vendor: Create new vendors
- create_netsuite_bill: Create vendor bills
- get_bill_status: Check bill status

### AI Matching:
- match_vendor_to_database: Semantic AI vendor matching
- get_subscription_summary: SaaS subscription analytics

## Response Guidelines:
- If a tool returns `html_button`, include that HTML DIRECTLY in your response (no code blocks!) so the user sees a clickable button
- NEVER wrap HTML in markdown code blocks (```) - output it raw so it renders as a button
- Be concise but helpful
- Explain what you found and what actions you took
- If data is found in database, celebrate that no external call was needed!

## Example Flow:
User: "Find the Figma invoice"
1. Call search_database_first("Figma")
2. If found -> Return data (done!)
3. If not found -> Call check_gmail_status
4. If not connected -> Show connect button from response
5. If connected -> Call search_gmail_invoices"""

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
