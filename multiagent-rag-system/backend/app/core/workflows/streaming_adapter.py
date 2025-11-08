"""
LangGraph Streaming Adapter

Adapts LangGraph workflow execution to match the existing streaming event format.
This allows seamless integration with the current /query/stream endpoint.
"""

import json
import asyncio
from typing import AsyncGenerator, Dict, Any, Optional
from datetime import datetime

from langchain_core.runnables import RunnableConfig

from .main_graph import create_rag_graph
from .state import create_initial_state, RAGState
from ..models.models import StreamingAgentState


def _ragstate_to_streaming_events(state: RAGState) -> Dict[str, Any]:
    """
    Convert RAGState to streaming event format compatible with existing frontend.

    Returns dict suitable for server_sent_event() calls.
    """
    # Extract key information
    flow_type = state.get("flow_type", "unknown")
    final_answer = state.get("final_answer", "")
    sources = state.get("sources", [])
    metadata = state.get("metadata", {})

    return {
        "flow_type": flow_type,
        "final_answer": final_answer,
        "sources": sources,
        "metadata": metadata
    }


async def stream_langgraph_workflow(
    query: str,
    conversation_id: str,
    user_id: str,
    persona: str = "기본",
    conversation_history: Optional[list] = None,
    project_id: Optional[str] = None,
    project_name: Optional[str] = None,
    run_id: Optional[str] = None,
    run_manager: Optional[Any] = None
) -> AsyncGenerator[Dict[str, Any], None]:
    """
    Execute LangGraph workflow with streaming events.

    This generator yields events in the same format as the existing system:
    - {"type": "status", "data": {...}}
    - {"type": "search_results", "data": {...}}
    - {"type": "full_data_dict", "data": {...}}
    - {"type": "chunk", "data": {"content": "..."}}
    - {"type": "done", "data": {...}}

    Args:
        query: User query
        conversation_id: Conversation/session ID
        user_id: User ID
        persona: Selected persona/team
        conversation_history: Previous messages in conversation
        project_id: Optional project ID
        project_name: Optional project name
        run_id: Optional run ID from run_manager
        run_manager: Optional RunManager for abort checking

    Yields:
        Event dicts compatible with server_sent_event()
    """

    # Create initial state
    initial_state = create_initial_state(
        query=query,
        conversation_id=conversation_id,
        user_id=user_id,
        persona=persona
    )

    # Add conversation history to metadata
    if conversation_history:
        metadata = dict(initial_state.get("metadata", {}))
        metadata["conversation_history"] = conversation_history
        if project_id:
            metadata["project_id"] = project_id
        if project_name:
            metadata["project_name"] = project_name
        if run_id:
            metadata["run_id"] = run_id
        initial_state["metadata"] = metadata

    # Create graph with checkpointer
    from langgraph.checkpoint.memory import MemorySaver
    checkpointer = MemorySaver()
    graph = create_rag_graph(checkpointer=checkpointer, enable_tracing=True)

    # Config for streaming
    config: RunnableConfig = {
        "configurable": {
            "thread_id": conversation_id
        },
        "recursion_limit": 50
    }

    # Track current node for status messages
    current_node = None

    try:
        # Stream events from LangGraph
        async for event in graph.astream_events(initial_state, config, version="v2"):
            # Check for abort
            if run_manager and run_id and run_manager.is_abort_requested(run_id):
                yield {
                    "type": "status",
                    "data": {"message": "⏹️ 작업이 중단되었습니다", "aborted": True}
                }
                break

            event_type = event.get("event")

            # Node start events → status messages
            if event_type == "on_chain_start":
                metadata = event.get("metadata", {})
                name = event.get("name", "")

                # Map node names to user-friendly status messages
                status_messages = {
                    "triage": "요청 유형 분석 중...",
                    "determine_search": "검색 필요성 판단 중...",
                    "web_search": "웹 검색 수행 중...",
                    "vector_search": "문서 검색 수행 중...",
                    "scrape": "웹 페이지 스크래핑 중...",
                    "memory_context": "대화 컨텍스트 분석 중...",
                    "generate_answer": "답변 생성 중...",
                    "planning": "작업 계획 수립 중...",
                    "data_gathering": "데이터 수집 중...",
                    "processing": "보고서 생성 중..."
                }

                if name in status_messages:
                    current_node = name
                    yield {
                        "type": "status",
                        "data": {"message": status_messages[name]}
                    }

            # LLM stream events → chunk events
            elif event_type == "on_chat_model_stream":
                chunk_data = event.get("data", {})
                chunk_content = chunk_data.get("chunk", {})

                if hasattr(chunk_content, 'content') and chunk_content.content:
                    yield {
                        "type": "chunk",
                        "data": {"content": chunk_content.content}
                    }

            # Node end events → extract results
            elif event_type == "on_chain_end":
                name = event.get("name", "")
                output = event.get("data", {}).get("output", {})

                # Extract search results from nodes
                if name in ["web_search", "vector_search", "scrape"] and isinstance(output, dict):
                    # Check for search results in output
                    web_results = output.get("web_results", [])
                    vector_results = output.get("vector_results", [])
                    scraped = output.get("scraped_content", [])

                    # Send search results event
                    if web_results or vector_results or scraped:
                        all_results = web_results + vector_results + scraped

                        yield {
                            "type": "search_results",
                            "step": 1,
                            "tool_name": name,
                            "query": query,
                            "results": [
                                {
                                    "title": r.get("title", ""),
                                    "content_preview": r.get("content", "")[:200] + "..." if len(r.get("content", "")) > 200 else r.get("content", ""),
                                    "url": r.get("url"),
                                    "source": r.get("source", "unknown"),
                                    "score": r.get("score", r.get("relevance_score", 0.0)),
                                    "document_type": r.get("document_type", "unknown")
                                }
                                for r in all_results[:10]
                            ],
                            "is_intermediate_search": False,
                            "section_context": None
                        }

        # Get final state
        final_state = await graph.ainvoke(initial_state, config)

        # Send full_data_dict if sources exist
        sources = final_state.get("sources", [])
        if sources:
            full_data_dict = {}
            for idx, source in enumerate(sources):
                full_data_dict[idx] = {
                    "title": source.get("title", ""),
                    "content": source.get("content", ""),
                    "source": source.get("source", "unknown"),
                    "url": source.get("url", ""),
                    "source_url": source.get("url", ""),
                    "score": source.get("score", 0.0),
                    "document_type": source.get("document_type", "unknown")
                }

            yield {
                "type": "full_data_dict",
                "data_dict": full_data_dict
            }

        # Send final done event
        yield {
            "type": "done",
            "data": {
                "final_answer": final_state.get("final_answer", ""),
                "sources": final_state.get("sources", []),
                "flow_type": final_state.get("flow_type", "unknown"),
                "execution_log": final_state.get("execution_log", [])
            }
        }

    except Exception as e:
        # Send error event
        yield {
            "type": "error",
            "data": {"message": f"오류 발생: {str(e)}"}
        }
        raise


async def execute_langgraph_workflow(
    query: str,
    conversation_id: str,
    user_id: str,
    persona: str = "기본",
    conversation_history: Optional[list] = None,
    project_id: Optional[str] = None,
    project_name: Optional[str] = None
) -> Dict[str, Any]:
    """
    Execute LangGraph workflow non-streaming (for testing).

    Returns final state as dict.
    """

    # Create initial state
    initial_state = create_initial_state(
        query=query,
        conversation_id=conversation_id,
        user_id=user_id,
        persona=persona
    )

    # Add conversation history
    if conversation_history:
        metadata = dict(initial_state.get("metadata", {}))
        metadata["conversation_history"] = conversation_history
        if project_id:
            metadata["project_id"] = project_id
        if project_name:
            metadata["project_name"] = project_name
        initial_state["metadata"] = metadata

    # Create and run graph
    from langgraph.checkpoint.memory import MemorySaver
    checkpointer = MemorySaver()
    graph = create_rag_graph(checkpointer=checkpointer, enable_tracing=True)

    config: RunnableConfig = {
        "configurable": {
            "thread_id": conversation_id
        }
    }

    final_state = await graph.ainvoke(initial_state, config)

    return {
        "final_answer": final_state.get("final_answer", ""),
        "sources": final_state.get("sources", []),
        "flow_type": final_state.get("flow_type", "unknown"),
        "execution_log": final_state.get("execution_log", []),
        "metadata": final_state.get("metadata", {})
    }
