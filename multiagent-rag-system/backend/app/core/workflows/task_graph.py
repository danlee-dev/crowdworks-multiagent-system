"""
Task Flow Subgraph for LangGraph

This module creates the task flow subgraph for complex analysis and report generation.
It composes all task nodes into a cohesive workflow.

Graph Structure:
    START → planning → data_gathering → processing → END

Note: This is a simplified version for Week 2. Replanning and loop logic
will be added in Week 3 when we integrate with main.py streaming.
"""

from typing import Literal
from langgraph.graph import StateGraph, START, END

from .state import RAGState
from .nodes.task_nodes import (
    planning_node,
    data_gathering_node,
    processing_node
)


# ============================================================================
# Task Subgraph Builder
# ============================================================================

def create_task_subgraph() -> StateGraph:
    """
    Create the task flow subgraph.

    This subgraph handles complex tasks with:
    1. Planning (OrchestratorAgent.generate_plan)
    2. Data gathering (DataGathererAgent multi-step execution)
    3. Report processing (ProcessorAgent report generation)

    Graph Flow:
        START
          ↓
        planning
          ↓
        data_gathering
          ↓
        processing
          ↓
        END

    Returns:
        Compiled StateGraph for task flow
    """
    print("\n" + "="*60)
    print("🏗️  Building Task Flow Subgraph")
    print("="*60 + "\n")

    # Create graph
    workflow = StateGraph(RAGState)

    # ========================================================================
    # Add Nodes
    # ========================================================================

    print("📍 Adding task flow nodes...")

    workflow.add_node("planning", planning_node)
    print("   ✓ planning (OrchestratorAgent.generate_plan)")

    workflow.add_node("data_gathering", data_gathering_node)
    print("   ✓ data_gathering (DataGathererAgent)")

    workflow.add_node("processing", processing_node)
    print("   ✓ processing (ProcessorAgent)")

    # ========================================================================
    # Add Edges
    # ========================================================================

    print("\n🔗 Adding task flow edges...")

    # Linear flow for now (Week 2 simplified version)
    workflow.add_edge(START, "planning")
    print("   ✓ START → planning")

    workflow.add_edge("planning", "data_gathering")
    print("   ✓ planning → data_gathering")

    workflow.add_edge("data_gathering", "processing")
    print("   ✓ data_gathering → processing")

    workflow.add_edge("processing", END)
    print("   ✓ processing → END")

    # ========================================================================
    # Compile Graph
    # ========================================================================

    print("\n⚙️  Compiling task subgraph...")

    app = workflow.compile()

    print("\n" + "="*60)
    print("✅ Task Flow Subgraph compiled successfully")
    print("="*60 + "\n")

    return app


# ============================================================================
# Convenience Function for Testing
# ============================================================================

async def test_task_flow(
    query: str,
    conversation_id: str = "test_task",
    user_id: str = "test_user",
    persona: str = "기본"
):
    """
    Test the task flow subgraph standalone.

    Args:
        query: User query
        conversation_id: Conversation ID
        user_id: User ID
        persona: Persona name

    Returns:
        Final state after task flow
    """
    from .state import create_initial_state

    print("\n" + "="*60)
    print("🧪 Testing Task Flow")
    print("="*60 + "\n")

    # Create initial state
    initial_state = create_initial_state(
        query=query,
        conversation_id=conversation_id,
        user_id=user_id,
        persona=persona
    )

    # Set flow type to task
    initial_state["flow_type"] = "task"

    # Create and run task subgraph
    graph = create_task_subgraph()

    config = {
        "configurable": {
            "thread_id": conversation_id
        }
    }

    final_state = await graph.ainvoke(initial_state, config=config)

    print("\n" + "="*60)
    print("✅ Task Flow Test Complete")
    print(f"   Plan steps: {len(final_state.get('plan', {}).get('steps', []))}")
    print(f"   Collected data: {len(final_state.get('collected_data', []))} items")
    print(f"   Report length: {len(final_state.get('final_answer', ''))} characters")
    print("="*60 + "\n")

    return final_state
