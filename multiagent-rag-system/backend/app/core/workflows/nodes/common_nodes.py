"""
Common Nodes for RAG Workflow

Shared nodes used across both chat and task flows:
- triage_node: Classify request as 'chat' or 'task'
- abort_check_node: Check if execution should be aborted
"""

import json
import re
from datetime import datetime
from typing import Literal

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.runnables import RunnableConfig

from ..state import RAGState, log_state_transition


# ============================================================================
# Triage Node
# ============================================================================

async def triage_node(state: RAGState, config: RunnableConfig) -> RAGState:
    """
    Triage node: Classify request as 'chat' or 'task'.

    This node analyzes the user query and determines the appropriate workflow:
    - 'chat': Simple Q&A that can be answered with basic search + LLM
    - 'task': Complex analysis requiring multi-step data gathering and reporting

    Based on: TriageAgent.classify_request() from orchestrator.py:37-110

    Args:
        state: Current RAGState
        config: LangGraph runtime configuration

    Returns:
        Updated state with flow_type set
    """
    print(f"\n{'='*60}")
    print(f"🔍 [Triage Node] Classifying request")
    print(f"   Query: {state['original_query'][:100]}...")
    print(f"{'='*60}\n")

    query = state["original_query"]

    # Initialize LLM for classification
    llm = ChatGoogleGenerativeAI(
        model="gemini-2.5-flash-lite",
        temperature=0.1
    )

    classification_prompt = f"""
사용자 요청을 분석하여 적절한 처리 방식을 결정하세요:

사용자 요청: {query}

분류 기준:
1. **chat**: 간단한 질문, 일반적인 대화, 웹/벡터 검색으로 답변 가능한 경우
   - 예: "안녕하세요", "감사합니다", "간단한 설명 요청"
   - 예: "최근 ~ 시세 알려줘", "최근 이슈 Top 10이 뭐야?"
   - 예: "이 링크 내용이 뭐야?" (단순 확인)

2. **task**: 복합적인 분석, 데이터 수집, 리포트 생성이 필요한 경우
   - 예: "~를 분석해줘", "~에 대한 자료를 찾아줘", "보고서 작성"
   - 예: "자세한 영양 정보" (RDB 조회 필요)
   - 예: "이 링크를 바탕으로 상세한 보고서 작성해줘"
   - 예: "Graph DB 검색이 필요한 경우", "논문 검색이 필요한 경우"

JSON으로 응답:
{{
    "flow_type": "chat" 또는 "task",
    "reasoning": "분류 근거 설명"
}}
"""

    try:
        # LLM 호출 (LangSmith가 자동으로 추적)
        response = await llm.ainvoke(classification_prompt)
        response_content = response.content.strip()

        print(f"📝 LLM Response: {response_content[:200]}...")

        # Parse JSON response
        classification = None
        try:
            # Direct JSON parsing
            classification = json.loads(response_content)
        except json.JSONDecodeError:
            # Fallback: Extract JSON from markdown code block
            json_match = re.search(r'\{.*\}', response_content, re.DOTALL)
            if json_match:
                classification = json.loads(json_match.group())
            else:
                raise ValueError("Valid JSON not found in response")

        # Validate required fields
        required_fields = ["flow_type", "reasoning"]
        for field in required_fields:
            if field not in classification:
                raise ValueError(f"Missing required field: {field}")

        flow_type = classification["flow_type"]
        reasoning = classification["reasoning"]

        print(f"✅ Classification Result:")
        print(f"   Flow Type: {flow_type}")
        print(f"   Reasoning: {reasoning}")

        # Update state
        new_state = dict(state)
        new_state["flow_type"] = flow_type

        # Update metadata
        metadata = dict(state.get("metadata", {}))
        metadata["triage_reasoning"] = reasoning
        metadata["classified_at"] = datetime.now().isoformat()
        new_state["metadata"] = metadata

        # Add execution log
        new_state = log_state_transition(
            new_state,
            "triage_node",
            f"Classified as '{flow_type}': {reasoning}"
        )

        return new_state

    except Exception as e:
        print(f"⚠️  Classification failed: {e}")
        print(f"   Defaulting to 'task' flow")

        # Fallback to 'task' on error (safer default)
        new_state = dict(state)
        new_state["flow_type"] = "task"

        metadata = dict(state.get("metadata", {}))
        metadata["triage_error"] = str(e)
        metadata["classified_at"] = datetime.now().isoformat()
        new_state["metadata"] = metadata

        new_state = log_state_transition(
            new_state,
            "triage_node",
            f"Classification failed, defaulted to 'task': {str(e)}"
        )

        return new_state


# ============================================================================
# Routing Function
# ============================================================================

def route_after_triage(state: RAGState) -> Literal["chat_flow", "task_flow"]:
    """
    Conditional routing function after triage.

    Routes to appropriate subgraph based on flow_type:
    - "chat" → chat_flow (SimpleAnswerer)
    - "task" → task_flow (Orchestrator)

    Args:
        state: Current RAGState

    Returns:
        "chat_flow" or "task_flow"
    """
    flow_type = state.get("flow_type", "task")

    if flow_type == "chat":
        print(f"🔀 Routing → chat_flow")
        return "chat_flow"
    else:
        print(f"🔀 Routing → task_flow")
        return "task_flow"


# ============================================================================
# Abort Check Node
# ============================================================================

async def abort_check_node(state: RAGState, config: RunnableConfig) -> RAGState:
    """
    Check if execution should be aborted.

    This node checks the run_manager for abort requests.
    If abort is requested, it raises an interrupt to stop the workflow.

    Note: This will be integrated with RunManager in the full implementation.
    For now, it's a placeholder that checks metadata.

    Args:
        state: Current RAGState
        config: LangGraph runtime configuration

    Returns:
        Unchanged state if not aborted

    Raises:
        Exception: If abort is requested
    """
    metadata = state.get("metadata", {})
    run_id = metadata.get("run_id")

    # Check if abort flag is set in metadata
    if metadata.get("abort_requested", False):
        print(f"🛑 Abort requested for run_id: {run_id}")
        raise Exception(f"Execution aborted by user request: {run_id}")

    return state


# ============================================================================
# Status Update Node
# ============================================================================

async def status_update_node(
    state: RAGState,
    config: RunnableConfig,
    message: str
) -> RAGState:
    """
    Generic status update node.

    Adds a status message to execution log and can emit custom events.

    Args:
        state: Current RAGState
        config: LangGraph runtime configuration
        message: Status message

    Returns:
        Updated state with log entry
    """
    print(f"📊 Status: {message}")

    new_state = log_state_transition(state, "status_update", message)

    return new_state
