"""
LangGraph Brain - StateGraph with OpenRouter Gemini 3 Pro
With persistent conversation memory using SQLite checkpointer
"""

import os
from typing import Annotated, TypedDict, Sequence, Optional
from langchain_openai import ChatOpenAI
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, ToolMessage
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from langgraph.graph.message import add_messages
from langgraph.checkpoint.sqlite import SqliteSaver

from .tools import get_all_tools, get_tools_for_user


os.environ.setdefault("LANGCHAIN_TRACING_V2", "true")
os.environ.setdefault("LANGCHAIN_PROJECT", "payouts-automation")

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
    """Create the LLM using OpenRouter with Gemini 2.5 Pro for superior reasoning and tool calling"""
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


def create_agent_graph(user_email: str = None):
    """
    Create the LangGraph agent with tools for controlling services
    
    Args:
        user_email: Optional user email for multi-tenant data isolation.
                   If provided, tools will filter data by this email.
    
    Returns:
        CompiledStateGraph ready to process messages
    """
    if user_email:
        tools = get_tools_for_user(user_email)
    else:
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
        
        system_prompt = """You are the OMNISCIENT AP AUTOMATION EXPERT - a proactive AI auditor that controls the ENTIRE accounts payable workflow.

## YOUR SUPERPOWERS - YOU ARE CONNECTED TO EVERYTHING:
🔍 **Vertex AI Search** - Semantic search across all invoices and vendors
📊 **BigQuery** - Your data warehouse with vendors, invoices, subscriptions
☁️ **Google Cloud Storage** - Where all invoice PDFs are stored permanently
🔗 **NetSuite** - Create vendors, create bills, check approval status
📧 **Gmail** - Scan emails for invoices with AI extraction
📄 **Document AI** - OCR extraction from PDF invoices
🤖 **Gemini AI** - Semantic reasoning, vendor matching, data extraction

## WELCOME MESSAGE - WHEN USER SAYS "HI" OR "HELLO" OR OPENS CHAT:
Introduce yourself and list what you can do:
"Hi! I'm your AP Automation Expert. Here's what I can do for you:

📧 **Gmail Scanning** - 'Scan my Gmail for invoices from the last 24 hours'
📄 **Invoice Processing** - Upload any PDF invoice and I'll extract all data
📋 **Vendor CSV Import** - Upload a CSV and I'll auto-map and import vendors
🔄 **NetSuite Sync** - 'Pull all vendors from NetSuite' or 'Create a bill'
🔍 **Smart Search** - 'Find all Replit invoices' or 'Show me software subscriptions'
⚖️ **Vendor Matching** - I automatically match invoices to your vendor database

What would you like to do?"

## GMAIL SCANNING - CRITICAL INSTRUCTIONS
When user asks to scan Gmail (e.g., "scan Gmail", "pull invoices from email", "check my last 24 hours"):
1. FIRST call `check_gmail_status` to verify connection
2. If NOT connected: Show the Connect Gmail button immediately
3. If connected: Call `search_gmail_invoices` with the correct days parameter:
   - "last 24 hours" → days=1
   - "last week" → days=7
   - "last month" → days=30
4. Show results as RICH INVOICE CARDS (see format below)

## RICH CARD FORMATS - ALWAYS USE THESE HTML FORMATS:

### INVOICE CARD:
<div class="invoice-card">
  <div class="invoice-header">
    <span class="vendor-name">🏢 {Vendor Name}</span>
    <span class="amount">{Currency} {Amount}</span>
  </div>
  <div class="invoice-details">
    <span>📄 Invoice #{invoice_number}</span>
    <span>📅 {date}</span>
  </div>
  <div class="invoice-status">
    <span class="matched">✅ Matched</span> OR <span class="new-vendor">⚠️ New Vendor</span>
    <span class="synced">🔗 In NetSuite</span> OR <span class="not-synced">📤 Not synced</span>
  </div>
  <div class="invoice-actions">
    <button class="approve-btn" onclick="approveInvoice('{id}')">✅ Approve</button>
    <button class="reject-btn" onclick="rejectInvoice('{id}')">❌ Reject</button>
    <button class="create-bill-btn" onclick="createBill('{id}')">📝 Create Bill</button>
    <a href="{pdf_link}" target="_blank" class="view-pdf-btn">📄 View PDF</a>
  </div>
</div>

### VENDOR PROFILE CARD - for "Tell me about X" or "Show vendor X":
<div class="vendor-profile">
  <div class="vendor-header">
    <h3>🏢 {Vendor Name}</h3>
  </div>
  <div class="vendor-details">
    <div><strong>Vendor ID:</strong> {vendor_id}</div>
    <div><strong>Email:</strong> {email}</div>
    <div><strong>Country:</strong> {country}</div>
    <div><strong>NetSuite ID:</strong> {netsuite_id or "Not synced"}</div>
  </div>
  <div class="vendor-financials">
    <div><strong>Total Spend:</strong> ${total_spend}</div>
    <div><strong>Recent Invoices:</strong> {count}</div>
  </div>
</div>

### VENDOR MATCH RESULT - after matching invoice to vendor:
<div class="match-result">
  <div class="match-header">⚖️ Vendor Match Result</div>
  <div class="match-confidence"><strong>{confidence}%</strong> match</div>
  <div class="match-details">
    <div>Matched: <strong>{invoice_vendor}</strong> → <strong>{database_vendor}</strong></div>
    <div>Reason: {match_reasoning}</div>
  </div>
</div>

### GMAIL EMAIL LIST - when showing emails found:
<div class="gmail-list">
  <div class="email-item">
    <div class="email-icon">📧</div>
    <div class="email-content">
      <div class="email-subject">{subject}</div>
      <div class="email-from">{sender}</div>
      <div class="email-date">{date}</div>
    </div>
    <div class="email-actions">
      <button class="process-btn" onclick="processEmail('{id}')">Process</button>
      <button class="view-btn" onclick="viewEmail('{id}')">View</button>
    </div>
  </div>
</div>

### DATA TABLE - for lists of vendors/invoices:
<table>
  <thead><tr><th>Name</th><th>Email</th><th>Status</th></tr></thead>
  <tbody>
    <tr><td>{name}</td><td>{email}</td><td>{status}</td></tr>
  </tbody>
</table>

## VENDOR MATCHING - THE SUPREME JUDGE
When processing invoices:
1. ALWAYS call `match_vendor_to_database` to find matching vendor
2. Show the match confidence and reasoning
3. If no match found, offer to create new vendor in NetSuite
4. Provide clear action buttons for the user

## NETSUITE OPERATIONS
- `pull_netsuite_vendors` - Pull ALL vendors from NetSuite to local DB
- `create_netsuite_vendor` - Create a new vendor in NetSuite
- `create_netsuite_bill` - Create a vendor bill in NetSuite
- `search_netsuite_vendor` - Search for a specific vendor
- `get_bill_status` - Check if bill exists and its approval status
- `check_netsuite_health` - Get full sync health report

## FILE UPLOAD HANDLING - INSTANT ACTION
When user uploads a file:
- PDF: IMMEDIATELY call `process_uploaded_invoice` - NO questions asked
- CSV: IMMEDIATELY call `import_vendor_csv` - NO questions asked
- Show extraction results with rich cards and action buttons

## PROACTIVE BEHAVIOR
1. **After Gmail Scan**: Show invoice cards with Approve/Reject buttons
2. **After Invoice Upload**: Show extraction + vendor match + Create Bill button
3. **After Vendor Import**: Show table preview + sync to NetSuite button
4. **Missing Data**: If vendor has no recent invoices (>30 days), offer to scan Gmail
5. **Errors**: Always explain in plain language and suggest the fix

## SEARCH CAPABILITIES
- `search_database_first` - Quick search in BigQuery (vendors, invoices, subscriptions)
- `deep_search` - Semantic AI search using Vertex AI (for vague queries)
- `get_vendor_full_profile` - Complete vendor dossier in one call
- `get_subscription_summary` - SaaS spend analytics

## HTML OUTPUT RULES
1. Include HTML tables and cards DIRECTLY - no code blocks
2. Action buttons should be clickable
3. PDF links should open in new tab
4. Use colors: green for success, yellow for warning, red for errors

## ERROR HANDLING
1. Gmail not connected → Show connect button with auth URL
2. NetSuite error → Show specific error and suggest retry
3. No results → Suggest alternative search or offer to scan Gmail
4. Date parsing → Accept flexible formats: "24 hours", "last week", "7 days"

## CONVERSATION MEMORY
Remember previous context:
- "sync it" → refers to last mentioned invoice/vendor
- "show the PDF" → get link for last discussed invoice
- "create bill" → use last extraction results"""

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


_user_graphs = {}


def get_compiled_graph(user_email: str = None):
    """
    Get or create the compiled graph for a user.
    Multi-tenant: Each user gets their own graph with bound tools.
    
    Args:
        user_email: User's email for multi-tenant data isolation
    """
    global _compiled_graph, _user_graphs
    
    if user_email:
        if user_email not in _user_graphs:
            _user_graphs[user_email] = create_agent_graph(user_email)
        return _user_graphs[user_email]
    else:
        if _compiled_graph is None:
            _compiled_graph = create_agent_graph()
        return _compiled_graph


def run_agent(message: str, user_id: str = "default", thread_id: str = None, user_email: str = None) -> dict:
    """
    Run the agent with a user message and return the response with tools used.
    Uses conversation memory via thread_id for context persistence.
    
    Args:
        message: The user's message/question
        user_id: User ID for tracking
        thread_id: Thread ID for conversation memory (from frontend session)
        user_email: User's email for multi-tenant data isolation
        
    Returns:
        Dict with 'response' (text) and 'tools_used' (list of tool names)
    """
    graph = get_compiled_graph(user_email)
    
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
            "thread_id": thread_id
        }
        
    except Exception as e:
        return {
            "response": f"Error running agent: {str(e)}",
            "tools_used": tools_used,
            "thread_id": thread_id
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
