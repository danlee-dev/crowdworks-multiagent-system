"""
Main LangGraph Workflow for RAG System

This module creates the primary StateGraph that orchestrates the entire RAG workflow.
It includes:
- Triage node for request classification
- Conditional routing to chat or task flows
- Integration with LangSmith for full tracing
- Checkpoint support for resumability
"""

from typing import Optional
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

from .state import RAGState, create_initial_state, validate_state
from .nodes.common_nodes import triage_node, route_after_triage
from .chat_graph import create_chat_subgraph


# ============================================================================
# Main Graph Builder
# ============================================================================

def create_rag_graph(
    checkpointer: Optional[MemorySaver] = None,
    enable_tracing: bool = True
) -> StateGraph:
    """
    Create the main RAG workflow graph.

    This function builds the complete LangGraph workflow including:
    - Triage for request classification
    - Chat flow for simple Q&A
    - Task flow for complex reports
    - Conditional routing between flows

    Graph Structure:
    ```
    START → triage → [chat_flow | task_flow] → END
    ```

    Args:
        checkpointer: Optional checkpointer for state persistence
                     (defaults to MemorySaver for in-memory checkpoints)
        enable_tracing: Enable LangSmith tracing (default: True)

    Returns:
        Compiled StateGraph ready for execution
    """
    print(f"\n{'='*60}")
    print(f"🏗️  Building RAG Workflow Graph")
    print(f"{'='*60}\n")

    # Configure LangSmith tracing
    if enable_tracing:
        from ..config.langsmith_config import configure_langsmith
        configure_langsmith()

    # Create the graph with RAGState schema
    workflow = StateGraph(RAGState)

    # ========================================================================
    # Add Nodes
    # ========================================================================

    print("📍 Adding nodes...")

    # Triage node (classifies request)
    workflow.add_node("triage", triage_node)
    print("   ✓ triage")

    # Chat flow (real implementation)
    chat_subgraph = create_chat_subgraph()
    workflow.add_node("chat_flow", chat_subgraph)
    print("   ✓ chat_flow (LangGraph subgraph)")

    # Task flow (placeholder - will be implemented in Week 2)
    workflow.add_node("task_flow", _placeholder_task_flow)
    print("   ✓ task_flow (placeholder)")

    # ========================================================================
    # Add Edges
    # ========================================================================

    print("\n🔗 Adding edges...")

    # Entry point: START → triage
    workflow.add_edge(START, "triage")
    print("   ✓ START → triage")

    # Conditional routing after triage
    workflow.add_conditional_edges(
        "triage",
        route_after_triage,
        {
            "chat_flow": "chat_flow",
            "task_flow": "task_flow"
        }
    )
    print("   ✓ triage → [chat_flow | task_flow] (conditional)")

    # Both flows end at END
    workflow.add_edge("chat_flow", END)
    print("   ✓ chat_flow → END")

    workflow.add_edge("task_flow", END)
    print("   ✓ task_flow → END")

    # ========================================================================
    # Compile Graph
    # ========================================================================

    print("\n⚙️  Compiling graph...")

    # Use provided checkpointer or default to MemorySaver
    if checkpointer is None:
        checkpointer = MemorySaver()
        print("   Using MemorySaver for checkpoints")
    else:
        print(f"   Using custom checkpointer: {type(checkpointer).__name__}")

    # Compile the graph
    app = workflow.compile(checkpointer=checkpointer)

    print(f"\n{'='*60}")
    print(f"✅ RAG Workflow Graph compiled successfully")
    print(f"{'='*60}\n")

    return app


# ============================================================================
# Placeholder Flow Nodes
# ============================================================================

async def _placeholder_task_flow(state: RAGState) -> RAGState:
    """
    Placeholder for task flow.

    This will be replaced with the actual task subgraph in Week 2-3.

    For now, it just returns a simple message.
    """
    print(f"\n{'='*60}")
    print(f"📊 [Placeholder Task Flow]")
    print(f"   Query: {state['original_query']}")
    print(f"{'='*60}\n")

    new_state = dict(state)
    new_state["final_answer"] = f"[PLACEHOLDER] Task report for: {state['original_query']}"

    # Add to execution log
    execution_log = list(state.get("execution_log", []))
    execution_log.append(f"Task flow (placeholder) - Processed query")
    new_state["execution_log"] = execution_log

    return new_state


# ============================================================================
# Convenience Functions
# ============================================================================

async def run_rag_workflow(
    query: str,
    conversation_id: str,
    user_id: str = "default_user",
    **kwargs
) -> RAGState:
    """
    Convenience function to run the RAG workflow end-to-end.

    Args:
        query: User query
        conversation_id: Conversation ID
        user_id: User ID
        **kwargs: Additional arguments for create_initial_state

    Returns:
        Final state after workflow execution
    """
    # Create graph
    graph = create_rag_graph()

    # Create initial state
    initial_state = create_initial_state(
        query=query,
        conversation_id=conversation_id,
        user_id=user_id,
        **kwargs
    )

    # Validate state
    if not validate_state(initial_state):
        raise ValueError("Invalid initial state")

    # Configure execution
    config = {
        "configurable": {
            "thread_id": conversation_id
        }
    }

    # Run workflow
    print(f"\n{'='*60}")
    print(f"🚀 Running RAG Workflow")
    print(f"   Query: {query}")
    print(f"   Conversation: {conversation_id}")
    print(f"{'='*60}\n")

    final_state = await graph.ainvoke(initial_state, config=config)

    print(f"\n{'='*60}")
    print(f"✅ Workflow Completed")
    print(f"   Flow Type: {final_state.get('flow_type')}")
    print(f"   Answer Length: {len(final_state.get('final_answer', ''))} chars")
    print(f"{'='*60}\n")

    return final_state


async def stream_rag_workflow(
    query: str,
    conversation_id: str,
    user_id: str = "default_user",
    **kwargs
):
    """
    Stream the RAG workflow execution with events.

    This is the primary interface for the /query/stream endpoint.

    Args:
        query: User query
        conversation_id: Conversation ID
        user_id: User ID
        **kwargs: Additional arguments

    Yields:
        Events from workflow execution
    """
    # Create graph
    graph = create_rag_graph()

    # Create initial state
    initial_state = create_initial_state(
        query=query,
        conversation_id=conversation_id,
        user_id=user_id,
        **kwargs
    )

    # Configure execution
    config = {
        "configurable": {
            "thread_id": conversation_id
        }
    }

    print(f"\n{'='*60}")
    print(f"🌊 Streaming RAG Workflow")
    print(f"   Query: {query}")
    print(f"   Conversation: {conversation_id}")
    print(f"{'='*60}\n")

    # Stream events using astream_events (v2)
    async for event in graph.astream_events(initial_state, config, version="v2"):
        event_type = event.get("event")

        # Filter and transform events for frontend
        if event_type == "on_chain_start":
            node_name = event.get("name", "")
            yield {
                "type": "status",
                "data": {
                    "message": f"Starting {node_name}...",
                    "session_id": conversation_id
                }
            }

        elif event_type == "on_chain_end":
            node_name = event.get("name", "")
            yield {
                "type": "status",
                "data": {
                    "message": f"Completed {node_name}",
                    "session_id": conversation_id
                }
            }

        elif event_type == "on_chat_model_stream":
            # LLM streaming chunks
            chunk = event.get("data", {}).get("chunk", {})
            if hasattr(chunk, 'content') and chunk.content:
                yield {
                    "type": "content",
                    "data": {
                        "chunk": chunk.content,
                        "session_id": conversation_id
                    }
                }

    print(f"\n{'='*60}")
    print(f"✅ Streaming Completed")
    print(f"{'='*60}\n")
