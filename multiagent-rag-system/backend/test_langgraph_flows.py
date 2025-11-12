"""
LangGraph Flow Test Script

Tests the chat and task flows to ensure they work correctly.
Run this from the backend directory:

    python test_langgraph_flows.py
"""

import asyncio
import sys
import os

# Add app to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.core.workflows.state import create_initial_state
from app.core.workflows.main_graph import create_rag_graph


async def test_chat_flow():
    """Test chat flow with a simple question."""
    print("\n" + "="*80)
    print("🧪 TEST 1: Chat Flow - Simple Question")
    print("="*80 + "\n")

    query = "안녕하세요"

    print(f"Query: {query}")
    print(f"Expected: Chat flow (simple greeting)")

    # Create initial state
    initial_state = create_initial_state(
        query=query,
        conversation_id="test_chat_001",
        user_id="test_user",
        persona="기본"
    )

    # Create graph
    graph = create_rag_graph(checkpointer=None, enable_tracing=False)

    # Run
    try:
        final_state = await graph.ainvoke(
            initial_state,
            config={"configurable": {"thread_id": "test_chat_001"}}
        )

        print("\n" + "-"*80)
        print("RESULTS:")
        print("-"*80)
        print(f"✓ Flow Type: {final_state.get('flow_type')}")
        print(f"✓ Final Answer Length: {len(final_state.get('final_answer', ''))} chars")
        print(f"✓ Execution Log: {len(final_state.get('execution_log', []))} steps")

        # Print execution log
        print("\nExecution Steps:")
        for i, step in enumerate(final_state.get('execution_log', []), 1):
            print(f"  {i}. {step}")

        # Print answer preview
        answer = final_state.get('final_answer', '')
        print(f"\nAnswer Preview:")
        print(f"  {answer[:200]}..." if len(answer) > 200 else f"  {answer}")

        print("\n✅ Chat Flow Test PASSED")
        return True

    except Exception as e:
        print(f"\n❌ Chat Flow Test FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_task_flow():
    """Test task flow with a complex query."""
    print("\n" + "="*80)
    print("🧪 TEST 2: Task Flow - Complex Analysis Request")
    print("="*80 + "\n")

    query = "사과의 영양성분을 분석해줘"

    print(f"Query: {query}")
    print(f"Expected: Task flow (analysis + report)")

    # Create initial state
    initial_state = create_initial_state(
        query=query,
        conversation_id="test_task_001",
        user_id="test_user",
        persona="기본"
    )

    # Create graph
    graph = create_rag_graph(checkpointer=None, enable_tracing=False)

    # Run
    try:
        final_state = await graph.ainvoke(
            initial_state,
            config={"configurable": {"thread_id": "test_task_001"}}
        )

        print("\n" + "-"*80)
        print("RESULTS:")
        print("-"*80)
        print(f"✓ Flow Type: {final_state.get('flow_type')}")
        print(f"✓ Plan Steps: {len(final_state.get('plan', {}).get('steps', []))}")
        print(f"✓ Collected Data: {len(final_state.get('collected_data', []))} items")
        print(f"✓ Final Answer Length: {len(final_state.get('final_answer', ''))} chars")
        print(f"✓ Execution Log: {len(final_state.get('execution_log', []))} steps")

        # Print execution log
        print("\nExecution Steps:")
        for i, step in enumerate(final_state.get('execution_log', []), 1):
            print(f"  {i}. {step}")

        # Print plan summary
        plan = final_state.get('plan', {})
        if plan.get('steps'):
            print(f"\nPlan Summary:")
            for i, step in enumerate(plan['steps'], 1):
                queries = step.get('queries', [])
                print(f"  Step {i}: {len(queries)} queries")
                for j, q in enumerate(queries[:2], 1):  # Show first 2
                    print(f"    {j}. [{q.get('tool')}] {q.get('query', '')[:50]}...")

        # Print answer preview
        answer = final_state.get('final_answer', '')
        print(f"\nAnswer Preview:")
        print(f"  {answer[:300]}..." if len(answer) > 300 else f"  {answer}")

        print("\n✅ Task Flow Test PASSED")
        return True

    except Exception as e:
        print(f"\n❌ Task Flow Test FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_triage():
    """Test triage classification."""
    print("\n" + "="*80)
    print("🧪 TEST 3: Triage Classification")
    print("="*80 + "\n")

    test_cases = [
        ("안녕하세요", "chat"),
        ("최근 사과 시세 알려줘", "chat"),
        ("사과의 영양성분을 분석하고 보고서 작성해줘", "task"),
        ("건강기능식품 시장 분석 보고서 작성", "task"),
    ]

    graph = create_rag_graph(checkpointer=None, enable_tracing=False)

    results = []
    for query, expected_flow in test_cases:
        print(f"\nQuery: '{query}'")
        print(f"Expected: {expected_flow}")

        initial_state = create_initial_state(
            query=query,
            conversation_id=f"test_triage_{hash(query)}",
            user_id="test_user"
        )

        try:
            final_state = await graph.ainvoke(
                initial_state,
                config={"configurable": {"thread_id": f"test_{hash(query)}"}}
            )

            actual_flow = final_state.get('flow_type')
            print(f"Actual: {actual_flow}")

            if actual_flow == expected_flow:
                print("✅ PASS")
                results.append(True)
            else:
                print("❌ FAIL")
                results.append(False)

        except Exception as e:
            print(f"❌ ERROR: {e}")
            results.append(False)

    if all(results):
        print("\n✅ All Triage Tests PASSED")
        return True
    else:
        print(f"\n⚠️  Some Triage Tests FAILED ({sum(results)}/{len(results)} passed)")
        return False


async def main():
    """Run all tests."""
    print("\n" + "="*80)
    print("🚀 LangGraph Flow Tests")
    print("="*80)

    results = []

    # Test 1: Chat Flow
    try:
        result = await test_chat_flow()
        results.append(("Chat Flow", result))
    except Exception as e:
        print(f"❌ Chat Flow Test Exception: {e}")
        results.append(("Chat Flow", False))

    # Test 2: Task Flow
    try:
        result = await test_task_flow()
        results.append(("Task Flow", result))
    except Exception as e:
        print(f"❌ Task Flow Test Exception: {e}")
        results.append(("Task Flow", False))

    # Test 3: Triage
    try:
        result = await test_triage()
        results.append(("Triage", result))
    except Exception as e:
        print(f"❌ Triage Test Exception: {e}")
        results.append(("Triage", False))

    # Summary
    print("\n" + "="*80)
    print("📊 TEST SUMMARY")
    print("="*80)

    for test_name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"  {status} - {test_name}")

    total = len(results)
    passed = sum(1 for _, p in results if p)

    print(f"\nTotal: {passed}/{total} tests passed")

    if passed == total:
        print("\n🎉 ALL TESTS PASSED!")
        return 0
    else:
        print(f"\n⚠️  {total - passed} test(s) failed")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
