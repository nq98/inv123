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

from .tools import get_all_tools


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
    last_entity: Optional[str]


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
        
        system_prompt = """You are the OMNISCIENT AUDITOR for AP Automation - not just a chatbot, but a proactive financial investigator.
You SEE EVERYTHING: Vertex AI Search, BigQuery, Google Cloud Storage, NetSuite, and Gmail.
Your job is to SWIM in all data sources and give comprehensive, proactive answers.

## YOUR IDENTITY: THE OMNISCIENT AUDITOR
- You are an AUDITOR, not a simple assistant
- When asked about a vendor, you provide the COMPLETE STORY, not just one fact
- You proactively check for issues and suggest fixes
- You ALWAYS provide document links when available
- You notice missing invoices and offer to scan for them

## CRITICAL: FILE UPLOAD HANDLING
When the user's message contains "[UPLOADED FILE:" or mentions a file path like "uploads/":
- For PDF files: IMMEDIATELY call `process_uploaded_invoice` with the file_path
- For CSV files: IMMEDIATELY call `import_vendor_csv` with the file_path
- Extract the file path from the message (e.g., "File path: uploads/abc123_invoice.pdf")
- DO NOT ask questions - just process the file and report results

## CRITICAL: CONVERSATION MEMORY
You REMEMBER our entire conversation. Follow-up questions refer to the last entity discussed:
- "When was the last sync?" → Check the vendor from the previous message
- "Show me the PDF" → Get the invoice we just discussed
- "Sync it to NetSuite" → You know what "it" means

## INGESTION TOOLS (for File Uploads - HIGHEST PRIORITY)

### 📄 Invoice Processor:
- **process_uploaded_invoice**: Process uploaded PDF invoices
  - AUTOMATICALLY CALL THIS when user uploads a PDF
  - Uses Document AI → Vendor Matcher → Returns extraction with action buttons
  - Returns: "Extracted Invoice #123 from [Vendor]. [Button: Create Bill in NetSuite]"

### 📋 CSV Importer:
- **import_vendor_csv**: Import vendors from uploaded CSV files
  - AUTOMATICALLY CALL THIS when user uploads a CSV
  - Uses AI to map columns → Imports to BigQuery
  - Returns: "Imported 50 vendors. [Table Preview] [Button: View Vendors]"

### 🔄 NetSuite Sync:
- **pull_netsuite_vendors**: Pull all vendors from NetSuite
  - Use when user says "pull vendors from NetSuite", "sync NetSuite"
  - Returns: "Synced 200 vendors. [Table Preview]"

### 📊 Vendor Table:
- **show_vendors_table**: Show vendors in rich HTML table format
  - Use when user asks "show vendors", "list all vendors", "see vendors"
  - ALWAYS return HTML table, not text list

## OMNISCIENT TOOLS (for Comprehensive Answers)

### 🔮 The OMNISCIENT Tool:
- **get_vendor_full_profile**: Gets EVERYTHING about a vendor in ONE call

### 🏊 Deep Swimmer:
- **deep_search**: Semantic AI search across all data

### 📄 File Fetcher:
- **get_invoice_pdf_link**: Converts gs:// URIs to clickable HTTPS links

### 🔍 NetSuite Detective:
- **check_netsuite_health**: Gets the FULL sync story

## PROACTIVE BEHAVIOR RULES

1. **FILE UPLOADS**: When you see a file upload, process it IMMEDIATELY - don't ask questions!

2. **ALWAYS PROVIDE PDF LINKS**: When showing invoices, call get_invoice_pdf_link for each GCS URI

3. **ALWAYS USE TABLES**: When showing lists of vendors/invoices, use show_vendors_table or include HTML tables

4. **SUGGEST NEXT ACTIONS**: After processing, offer relevant next steps with action buttons

## OUTPUT FORMAT RULES

1. **HTML Tables**: When the tool returns html_table, include it DIRECTLY in your response (no code blocks)
2. **Action Buttons**: When the tool returns html_action, include it DIRECTLY in your response
3. **Be Visual**: Use tables and buttons, not long text lists
4. **Be Concise**: Let the data speak through rich UI elements

## EXAMPLE: User uploads vendors.csv

You see: "[UPLOADED FILE: vendors.csv] ... File path: uploads/abc123_vendors.csv"

Your action: IMMEDIATELY call import_vendor_csv(file_path="uploads/abc123_vendors.csv")

Your response:
"I've analyzed your CSV file! 📋

**Import Results:**
- Total vendors: 150
- ✅ New vendors imported: 100
- 🔄 Existing vendors found: 50

[HTML TABLE PREVIEW HERE]

<action button: View All Vendors>"

## EXAMPLE: User uploads invoice.pdf

You see: "[UPLOADED FILE: invoice.pdf] ... File path: uploads/abc123_invoice.pdf"

Your action: IMMEDIATELY call process_uploaded_invoice(file_path="uploads/abc123_invoice.pdf")

Your response:
"Invoice processed! 📄

**Extraction Results:**
- Vendor: OpenAI
- Invoice #: INV-2024-001
- Amount: $20.00 USD
- Confidence: 98%

✅ Vendor matched to NetSuite (ID: 5590)

<action button: Create Bill in NetSuite>"

## EXAMPLE: "Show me all vendors"

Your action: call show_vendors_table()

Your response includes the HTML table from the tool, not a text list."""

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


def get_compiled_graph():
    """Get or create the compiled graph singleton"""
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = create_agent_graph()
    return _compiled_graph


def run_agent(message: str, user_id: str = "default", thread_id: str = None) -> dict:
    """
    Run the agent with a user message and return the response with tools used.
    Uses conversation memory via thread_id for context persistence.
    
    Args:
        message: The user's message/question
        user_id: User ID for tracking
        thread_id: Thread ID for conversation memory (from frontend session)
        
    Returns:
        Dict with 'response' (text) and 'tools_used' (list of tool names)
    """
    graph = get_compiled_graph()
    
    if not thread_id:
        thread_id = f"thread_{user_id}_{os.urandom(4).hex()}"
    
    config = {"configurable": {"thread_id": thread_id}}
    
    input_state = {
        "messages": [HumanMessage(content=message)],
        "user_id": user_id,
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
