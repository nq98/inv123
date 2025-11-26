"""
LangGraph Brain - StateGraph with OpenRouter Gemini 2.5 Pro
With INTENT-BASED TOOL ROUTING for maximum efficiency
"""

import os
import re
from typing import Annotated, TypedDict, Sequence, Optional, List
from langchain_openai import ChatOpenAI
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, ToolMessage
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from langgraph.graph.message import add_messages
from langgraph.checkpoint.sqlite import SqliteSaver

from .tools import get_all_tools, get_tools_for_user


os.environ.setdefault("LANGCHAIN_TRACING_V2", "true")
os.environ.setdefault("LANGSMITH_TRACING", "true")
os.environ.setdefault("LANGSMITH_ENDPOINT", "https://api.smith.langchain.com")
os.environ.setdefault("LANGCHAIN_PROJECT", "pr-impressionable-instructor-1")
os.environ.setdefault("LANGSMITH_PROJECT", "pr-impressionable-instructor-1")

# Use langapi secret for LangSmith API key
if os.getenv("langapi"):
    os.environ["LANGCHAIN_API_KEY"] = os.getenv("langapi")
    os.environ["LANGSMITH_API_KEY"] = os.getenv("langapi")

_checkpointer = None
_compiled_graph = None


def get_checkpointer():
    """Get or create the SQLite checkpointer for conversation memory"""
    global _checkpointer
    if _checkpointer is None:
        import sqlite3
        os.makedirs('data', exist_ok=True)
        conn = sqlite3.connect('data/agent_memory.db', check_same_thread=False)
        _checkpointer = SqliteSaver(conn)
    return _checkpointer


class AgentState(TypedDict):
    """State for the agent graph"""
    messages: Annotated[Sequence[BaseMessage], add_messages]
    user_id: str
    user_email: Optional[str]
    last_entity: Optional[str]


def create_llm():
    """Create the LLM using OpenRouter with Gemini 2.5 Pro"""
    api_key = os.getenv("OPENROUTERA")
    if not api_key:
        raise ValueError("OPENROUTERA environment variable not set")
    
    return ChatOpenAI(
        model="google/gemini-2.5-pro",
        api_key=api_key,
        base_url="https://openrouter.ai/api/v1",
        temperature=0.1,
        max_tokens=8192
    )


# =============================================================================
# INTENT ROUTER - Semantic AI-first tool selection
# =============================================================================

def classify_intent(message: str) -> dict:
    """
    AI-first semantic intent classification.
    Returns the intent category and restricted tool list.
    This runs BEFORE the LLM to constrain available tools.
    """
    msg = message.lower().strip()
    
    # Startup intent - dashboard only
    if msg == "__startup__" or msg == "":
        return {
            "intent": "startup",
            "tools": ["get_dashboard_status"],
            "prompt_hint": "Show dashboard status with greeting."
        }
    
    # Greeting intent - dashboard
    if msg in ["hi", "hello", "hey", "good morning", "good afternoon"]:
        return {
            "intent": "greeting",
            "tools": ["get_dashboard_status"],
            "prompt_hint": "Show friendly greeting with dashboard status."
        }
    
    # VENDOR QUERIES - Most common, most specific routing
    
    # NetSuite synced vendors
    if any(phrase in msg for phrase in [
        "from netsuite", "netsuite vendor", "synced vendor", "vendors synced",
        "vendors from netsuite", "netsuite list", "show synced", "synced to netsuite"
    ]):
        return {
            "intent": "vendor_synced",
            "tools": ["show_vendors_table"],
            "prompt_hint": "Call show_vendors_table with filter_type='synced' to show NetSuite-synced vendors.",
            "tool_args": {"filter_type": "synced"}
        }
    
    # Unsynced vendors
    if any(phrase in msg for phrase in [
        "unsynced", "not synced", "not in netsuite", "need to sync", "haven't synced"
    ]):
        return {
            "intent": "vendor_unsynced",
            "tools": ["show_unsynced_vendors"],
            "prompt_hint": "Show vendors that are not yet synced to NetSuite."
        }
    
    # All vendors / general vendor list
    if any(phrase in msg for phrase in [
        "all vendor", "list vendor", "show vendor", "view vendor", "vendors table",
        "vendor list", "vendors list", "bring vendor", "get vendor"
    ]) and not any(x in msg for x in ["netsuite", "synced", "unsynced"]):
        return {
            "intent": "vendor_all",
            "tools": ["show_vendors_table"],
            "prompt_hint": "Show all vendors table."
        }
    
    # Specific vendor lookup
    if "vendor" in msg and any(x in msg for x in ["find", "search", "lookup", "profile", "about", "tell me about"]):
        return {
            "intent": "vendor_search",
            "tools": ["get_vendor_full_profile", "search_database_first"],
            "prompt_hint": "Find the specific vendor the user is asking about."
        }
    
    # INVOICE QUERIES
    
    # Invoice list
    if any(phrase in msg for phrase in [
        "all invoice", "list invoice", "show invoice", "view invoice", "invoices table",
        "invoice list", "bring invoice", "get invoice"
    ]):
        return {
            "intent": "invoice_list",
            "tools": ["show_invoices_table"],
            "prompt_hint": "Show invoices table."
        }
    
    # Specific invoice lookup
    if "invoice" in msg and any(x in msg for x in ["find", "search", "lookup", "inv-", "number"]):
        return {
            "intent": "invoice_search",
            "tools": ["show_invoices_table", "deep_search"],
            "prompt_hint": "Find the specific invoice."
        }
    
    # GMAIL OPERATIONS
    
    if any(phrase in msg for phrase in ["scan gmail", "check gmail", "gmail scan", "scan email", "search gmail"]):
        return {
            "intent": "gmail_scan",
            "tools": ["check_gmail_status", "search_gmail_invoices"],
            "prompt_hint": "Check Gmail connection first, then scan for invoices if connected."
        }
    
    if "gmail" in msg and any(x in msg for x in ["connect", "status", "connected"]):
        return {
            "intent": "gmail_status",
            "tools": ["check_gmail_status"],
            "prompt_hint": "Check Gmail connection status."
        }
    
    # NETSUITE OPERATIONS
    
    if any(phrase in msg for phrase in ["sync from netsuite", "pull from netsuite", "import from netsuite", "netsuite pull"]):
        return {
            "intent": "netsuite_pull",
            "tools": ["pull_netsuite_vendors"],
            "prompt_hint": "Pull/sync vendors from NetSuite into local database."
        }
    
    if any(phrase in msg for phrase in ["netsuite stat", "netsuite dashboard", "netsuite status"]):
        return {
            "intent": "netsuite_stats",
            "tools": ["get_netsuite_statistics"],
            "prompt_hint": "Show NetSuite statistics and sync status."
        }
    
    if any(phrase in msg for phrase in ["sync to netsuite", "push to netsuite", "create vendor in netsuite"]):
        return {
            "intent": "netsuite_push",
            "tools": ["sync_vendor_to_netsuite"],
            "prompt_hint": "Sync vendor to NetSuite."
        }
    
    if any(phrase in msg for phrase in ["create bill", "netsuite bill", "make bill"]):
        return {
            "intent": "netsuite_bill",
            "tools": ["create_netsuite_bill"],
            "prompt_hint": "Create a bill in NetSuite."
        }
    
    # SPEND / ANALYTICS
    
    if any(phrase in msg for phrase in ["top vendor", "spend", "spending", "highest spend", "most spend"]):
        return {
            "intent": "spend_analytics",
            "tools": ["get_top_vendors_by_spend"],
            "prompt_hint": "Show top vendors by spend."
        }
    
    if any(phrase in msg for phrase in ["subscription", "saas", "recurring"]):
        return {
            "intent": "subscriptions",
            "tools": ["get_subscription_summary"],
            "prompt_hint": "Show subscription/SaaS summary."
        }
    
    # SEARCH / DEEP QUERIES
    
    if any(phrase in msg for phrase in ["search", "find", "lookup", "where is"]):
        return {
            "intent": "search",
            "tools": ["search_database_first", "deep_search"],
            "prompt_hint": "Search the database for user's query."
        }
    
    # DEFAULT - Full access but with efficiency warning
    return {
        "intent": "general",
        "tools": None,  # None = all tools available
        "prompt_hint": "Answer the user's question efficiently. Use minimum tools needed."
    }


def get_intent_system_prompt(intent_info: dict) -> str:
    """Generate a focused, minimal system prompt based on intent."""
    
    base_prompt = """You are an AP Automation Expert. Be direct and efficient.

RULES:
1. Call ONLY the tools needed - usually 1-2 max
2. Never apologize - state facts directly
3. Show data in clean HTML tables
4. After data, suggest ONE logical next action

"""
    
    # Add intent-specific guidance
    intent = intent_info.get("intent", "general")
    hint = intent_info.get("prompt_hint", "")
    tool_args = intent_info.get("tool_args")
    
    if intent == "startup":
        return base_prompt + """
This is the startup message. Call get_dashboard_status and show a friendly greeting:

<div style="margin-bottom: 12px;">👋 <strong>Hi! I'm your AP Automation Expert.</strong></div>
<div style="margin-bottom: 16px;">Here's your current status:</div>

[Show vendor count, invoice count, pending in cards]

Quick Actions:
📧 Scan Gmail | 🧾 View Invoices | 📋 View Vendors
"""

    if intent == "vendor_synced":
        return base_prompt + f"""
User wants NetSuite-synced vendors.
Call: show_vendors_table(filter_type="synced")
Show results in a table with Name, NetSuite ID, Email, Status columns.
"""

    if intent == "vendor_unsynced":
        return base_prompt + """
User wants unsynced vendors.
Call: show_unsynced_vendors()
Show results in a table.
"""

    if intent == "vendor_all":
        return base_prompt + """
User wants all vendors.
Call: show_vendors_table()
Show results in a paginated table.
"""

    if intent == "invoice_list":
        return base_prompt + """
User wants invoice list.
Call: show_invoices_table()
Show results in a table with Invoice #, Vendor, Amount, Date, Status.
"""

    if intent == "gmail_scan":
        return base_prompt + """
User wants to scan Gmail.
1. First call check_gmail_status to verify connection
2. If not connected, show Connect Gmail button
3. If connected but no date range specified, ask how far back to scan
4. If connected with date range, call search_gmail_invoices with days parameter
"""

    if intent == "netsuite_pull":
        return base_prompt + """
User wants to pull vendors FROM NetSuite.
Call: pull_netsuite_vendors()
Show summary of vendors pulled and any updates.
"""

    if intent == "netsuite_stats":
        return base_prompt + """
User wants NetSuite statistics.
Call: get_netsuite_statistics()
Show the stats in a clean format.
"""

    if intent == "spend_analytics":
        return base_prompt + """
User wants spend analysis.
Call: get_top_vendors_by_spend()
Show top vendors in a ranked table.
"""

    # Default for general queries
    return base_prompt + f"""
Hint: {hint}

Available tools are limited. Use them efficiently.
If data not found, state it directly and suggest an alternative.
"""


def filter_tools_by_intent(all_tools: List, intent_info: dict) -> List:
    """Filter tools based on intent classification."""
    allowed_tool_names = intent_info.get("tools")
    
    # None means all tools allowed
    if allowed_tool_names is None:
        return all_tools
    
    # Filter to only allowed tools
    return [t for t in all_tools if t.name in allowed_tool_names]


# =============================================================================
# AGENT GRAPH CREATION
# =============================================================================

def create_agent_graph(user_email: str = None, intent_info: dict = None):
    """
    Create the LangGraph agent with tools filtered by intent.
    
    Args:
        user_email: Optional user email for multi-tenant data isolation.
        intent_info: Intent classification result for tool filtering.
    
    Returns:
        CompiledStateGraph ready to process messages
    """
    # Get all available tools
    if user_email:
        all_tools = get_tools_for_user(user_email)
    else:
        all_tools = get_all_tools()
    
    # Filter tools by intent if provided
    if intent_info:
        tools = filter_tools_by_intent(all_tools, intent_info)
    else:
        tools = all_tools
    
    llm = create_llm()
    llm_with_tools = llm.bind_tools(tools)
    
    # Get appropriate system prompt
    system_prompt = get_intent_system_prompt(intent_info or {"intent": "general"})
    
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
    
    checkpointer = get_checkpointer()
    return workflow.compile(checkpointer=checkpointer)


def run_agent(message: str, user_id: str = "default", thread_id: str = None, user_email: str = None) -> dict:
    """
    Run the agent with INTENT-BASED TOOL ROUTING.
    
    This is the key efficiency improvement:
    1. Classify intent BEFORE calling LLM
    2. Restrict available tools based on intent
    3. Use focused system prompt
    4. LLM can only call allowed tools
    
    Args:
        message: The user's message/question
        user_id: User ID for tracking
        thread_id: Thread ID for conversation memory
        user_email: User's email for multi-tenant data isolation
        
    Returns:
        Dict with 'response' (text) and 'tools_used' (list of tool names)
    """
    
    # STEP 1: Classify intent BEFORE LLM
    intent_info = classify_intent(message)
    
    # STEP 2: Create graph with filtered tools
    graph = create_agent_graph(user_email, intent_info)
    
    if not thread_id:
        thread_id = f"thread_{user_id}_{os.urandom(4).hex()}"
    
    config = {"configurable": {"thread_id": thread_id}}
    
    input_state = {
        "messages": [HumanMessage(content=message)],
        "user_id": user_id,
        "user_email": user_email,
        "last_entity": None
    }
    
    tools_used = []
    
    try:
        result = graph.invoke(input_state, config=config)
        
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
            "tools_used": tools_used,
            "thread_id": thread_id,
            "intent": intent_info.get("intent", "unknown")
        }
        
    except Exception as e:
        return {
            "response": f"Error running agent: {str(e)}",
            "tools_used": tools_used,
            "thread_id": thread_id,
            "intent": intent_info.get("intent", "unknown")
        }


def stream_agent(message: str, user_id: str = "default", user_email: str = None):
    """
    Stream the agent's response with intent-based tool routing.
    
    Yields:
        Streaming chunks of the agent's response
    """
    # Classify intent first
    intent_info = classify_intent(message)
    
    graph = create_agent_graph(user_email, intent_info)
    
    initial_state = {
        "messages": [HumanMessage(content=message)],
        "user_id": user_id,
        "user_email": user_email
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
