"""
Chat Flow Subgraph for LangGraph

This module creates the chat flow subgraph for simple Q&A.
It composes all chat nodes into a cohesive workflow.

Graph Structure:
    START → determine_search → parallel_search → memory_context → generate_answer → END

    parallel_search includes:
        - web_search_node (conditional)
        - vector_search_node (conditional)
        - scrape_node (conditional)
"""

from typing import Literal
from langgraph.graph import StateGraph, START, END

from .state import RAGState
from .nodes.chat_nodes import (
    determine_search_node,
    web_search_node,
    vector_search_node,
    scrape_node,
    memory_context_node,
    generate_answer_node
)


# ============================================================================
# Conditional Routing Functions
# ============================================================================

def route_to_searches(state: RAGState) -> list[str]:
    """
    Route to appropriate search nodes based on search_flags.

    This is a parallel routing - multiple nodes can execute concurrently.

    Returns:
        List of node names to execute
    """
    search_flags = state.get("search_flags", {})

    nodes_to_execute = []

    if search_flags.get("needs_web_search", False):
        nodes_to_execute.append("web_search")

    if search_flags.get("needs_vector_search", False):
        nodes_to_execute.append("vector_search")

    if search_flags.get("needs_scraping", False):
        nodes_to_execute.append("scrape")

    # If no searches needed, go directly to memory context
    if not nodes_to_execute:
        nodes_to_execute.append("memory_context")

    print(f"   🔀 Routing to: {', '.join(nodes_to_execute)}")

    return nodes_to_execute


def after_searches_route(state: RAGState) -> Literal["memory_context"]:
    """
    After searches complete, always route to memory_context.

    Returns:
        Node name
    """
    return "memory_context"


# ============================================================================
# Chat Subgraph Builder
# ============================================================================

def create_chat_subgraph() -> StateGraph:
    """
    Create the chat flow subgraph.

    This subgraph handles simple Q&A queries with:
    1. Search requirement determination
    2. Parallel search execution (web, vector, scraping)
    3. Memory context building
    4. Answer generation with streaming

    Graph Flow:
        START
          ↓
        determine_search
          ↓
        [web_search, vector_search, scrape] (parallel, conditional)
          ↓
        memory_context
          ↓
        generate_answer
          ↓
        END

    Returns:
        Compiled StateGraph for chat flow
    """
    print("\n" + "="*60)
    print("🏗️  Building Chat Flow Subgraph")
    print("="*60 + "\n")

    # Create graph
    workflow = StateGraph(RAGState)

    # ========================================================================
    # Add Nodes
    # ========================================================================

    print("📍 Adding chat flow nodes...")

    workflow.add_node("determine_search", determine_search_node)
    print("   ✓ determine_search")

    workflow.add_node("web_search", web_search_node)
    print("   ✓ web_search")

    workflow.add_node("vector_search", vector_search_node)
    print("   ✓ vector_search")

    workflow.add_node("scrape", scrape_node)
    print("   ✓ scrape")

    workflow.add_node("memory_context", memory_context_node)
    print("   ✓ memory_context")

    workflow.add_node("generate_answer", generate_answer_node)
    print("   ✓ generate_answer")

    # ========================================================================
    # Add Edges
    # ========================================================================

    print("\n🔗 Adding chat flow edges...")

    # Entry point
    workflow.add_edge(START, "determine_search")
    print("   ✓ START → determine_search")

    # Conditional routing to searches (can execute in parallel)
    # Note: LangGraph will execute selected nodes in parallel automatically
    workflow.add_conditional_edges(
        "determine_search",
        route_to_searches,
        {
            "web_search": "web_search",
            "vector_search": "vector_search",
            "scrape": "scrape",
            "memory_context": "memory_context"
        }
    )
    print("   ✓ determine_search → [web_search | vector_search | scrape | memory_context] (conditional)")

    # All search nodes route to memory_context
    workflow.add_edge("web_search", "memory_context")
    print("   ✓ web_search → memory_context")

    workflow.add_edge("vector_search", "memory_context")
    print("   ✓ vector_search → memory_context")

    workflow.add_edge("scrape", "memory_context")
    print("   ✓ scrape → memory_context")

    # Memory context → generate answer
    workflow.add_edge("memory_context", "generate_answer")
    print("   ✓ memory_context → generate_answer")

    # Generate answer → END
    workflow.add_edge("generate_answer", END)
    print("   ✓ generate_answer → END")

    # ========================================================================
    # Compile Graph
    # ========================================================================

    print("\n⚙️  Compiling chat subgraph...")

    # Note: Subgraphs don't need checkpointers, the main graph handles that
    app = workflow.compile()

    print("\n" + "="*60)
    print("✅ Chat Flow Subgraph compiled successfully")
    print("="*60 + "\n")

    return app


# ============================================================================
# Convenience Function for Testing
# ============================================================================

async def test_chat_flow(
    query: str,
    conversation_id: str = "test_chat",
    user_id: str = "test_user",
    persona: str = "기본"
):
    """
    Test the chat flow subgraph standalone.

    Args:
        query: User query
        conversation_id: Conversation ID
        user_id: User ID
        persona: Persona name

    Returns:
        Final state after chat flow
    """
    from .state import create_initial_state

    print("\n" + "="*60)
    print("🧪 Testing Chat Flow")
    print("="*60 + "\n")

    # Create initial state
    initial_state = create_initial_state(
        query=query,
        conversation_id=conversation_id,
        user_id=user_id,
        persona=persona
    )

    # Set flow type to chat
    initial_state["flow_type"] = "chat"

    # Create and run chat subgraph
    graph = create_chat_subgraph()

    config = {
        "configurable": {
            "thread_id": conversation_id
        }
    }

    final_state = await graph.ainvoke(initial_state, config=config)

    print("\n" + "="*60)
    print("✅ Chat Flow Test Complete")
    print(f"   Answer: {final_state.get('final_answer', '')[:100]}...")
    print(f"   Sources: {len(final_state.get('sources', []))} items")
    print("="*60 + "\n")

    return final_state
