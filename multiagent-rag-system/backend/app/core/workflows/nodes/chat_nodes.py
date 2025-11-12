"""
Chat Flow Nodes for LangGraph

This module implements the chat flow for simple Q&A, porting logic from
SimpleAnswererAgent (conversational_agent.py) into LangGraph nodes.

Node Structure:
    determine_search_node → [web_search_node, vector_search_node, scrape_node]
    → memory_context_node → generate_answer_node
"""

import json
import asyncio
import os
import sys
from typing import List, Dict, Any
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from langchain_core.runnables import RunnableConfig
from langchain_core.messages import AIMessage

# API Fallback system import
sys.path.append('/app/utils')
try:
    from api_fallback import api_manager
except ImportError:
    print("⚠️ api_fallback 모듈을 찾을 수 없음, 기본 방식 사용")
    api_manager = None

from ..state import RAGState
from ...models.models import SearchResult
from ....services.search.search_tools import (
    vector_db_search,
    debug_web_search,
    scrape_and_extract_content
)

# Global thread pool for search operations
_global_executor = ThreadPoolExecutor(max_workers=16, thread_name_prefix="chat_search_worker")

# Load persona prompts
PERSONA_PROMPTS = {}
try:
    # 올바른 경로: /app/app/core/workflows/nodes/chat_nodes.py에서
    # /app/app/core/agents/prompts/persona_prompts.json로 가려면
    # nodes -> workflows -> core 로 3단계 올라간 후 agents/prompts로 진입
    current_dir = os.path.dirname(os.path.abspath(__file__))
    file_path = os.path.join(current_dir, "../../agents/prompts", "persona_prompts.json")
    with open(file_path, "r", encoding="utf-8") as f:
        PERSONA_PROMPTS = json.load(f)
    print(f"Chat Nodes: 페르소나 프롬프트 로드 성공 ({len(PERSONA_PROMPTS)}개)")
except Exception as e:
    print(f"❌ Chat Nodes: 페르소나 프롬프트 로드 실패 - {e}")
    print(f"   시도한 경로: {file_path}")
    raise RuntimeError(f"페르소나 프롬프트 파일을 로드할 수 없습니다: {e}")


# ============================================================================
# Model Initialization with Fallback
# ============================================================================

def _initialize_models(temperature: float = 0.7):
    """
    Initialize LLM models with API fallback support.

    Returns:
        Tuple of (streaming_chat, llm_lite, llm_gemini_backup, llm_openai_mini)
    """
    # Primary models
    streaming_chat = ChatGoogleGenerativeAI(
        model="gemini-2.5-flash-lite",
        temperature=temperature
    )
    llm_lite = ChatGoogleGenerativeAI(
        model="gemini-2.5-flash-lite",
        temperature=temperature
    )

    # Fallback models
    if api_manager:
        try:
            llm_gemini_backup = api_manager.create_langchain_model(
                "gemini-2.5-flash-lite",
                temperature=temperature
            )
            llm_openai_mini = api_manager.create_langchain_model(
                "gpt-4o-mini",
                temperature=temperature
            )
            print(f"Chat Nodes: Fallback 모델 초기화 완료 (사용 API: {api_manager.last_successful_api})")
        except Exception as e:
            print(f"Chat Nodes: Fallback 모델 초기화 실패: {e}")
            llm_gemini_backup = None
            llm_openai_mini = None
    else:
        # Legacy fallback
        openai_api_key = os.getenv("OPENAI_API_KEY")
        if openai_api_key:
            llm_openai_mini = ChatOpenAI(
                model="gpt-4o-mini",
                temperature=temperature,
                api_key=openai_api_key
            )
            print("Chat Nodes: OpenAI fallback 모델 초기화 완료 (기존 방식)")
        else:
            llm_openai_mini = None
        llm_gemini_backup = None
        print("Chat Nodes: 경고: 통합 API 관리자 없음, 제한된 fallback 사용")

    return streaming_chat, llm_lite, llm_gemini_backup, llm_openai_mini


# Initialize models at module level
STREAMING_CHAT, LLM_LITE, LLM_GEMINI_BACKUP, LLM_OPENAI_MINI = _initialize_models()


# ============================================================================
# Fallback Utilities
# ============================================================================

async def _invoke_with_fallback(prompt: str, primary_model, fallback_model):
    """
    Invoke LLM with Gemini 키 2개 -> OpenAI 순차 fallback.

    Args:
        prompt: LLM prompt
        primary_model: Primary Gemini model
        fallback_model: OpenAI fallback model

    Returns:
        LLM response
    """
    # 1차: Primary Gemini (key 1)
    try:
        result = await primary_model.ainvoke(prompt)
        return result
    except Exception as e:
        error_str = str(e).lower()
        rate_limit_indicators = ['429', 'quota', 'rate limit', 'exceeded', 'resource_exhausted']

        if any(indicator in error_str for indicator in rate_limit_indicators):
            print(f"Chat Nodes: Gemini 키 1 rate limit 감지: {e}")

            # 2차: Gemini backup (key 2)
            if LLM_GEMINI_BACKUP:
                try:
                    print("Chat Nodes: Gemini 키 2로 fallback 시도")
                    result = await LLM_GEMINI_BACKUP.ainvoke(prompt)
                    print("Chat Nodes: Gemini 키 2 fallback 성공")
                    return result
                except Exception as backup_error:
                    print(f"Chat Nodes: Gemini 키 2도 실패: {backup_error}")

            # 3차: OpenAI fallback
            if fallback_model:
                try:
                    print("Chat Nodes: OpenAI fallback 시도")
                    result = await fallback_model.ainvoke(prompt)
                    print("Chat Nodes: OpenAI fallback 성공")
                    return result
                except Exception as openai_error:
                    print(f"Chat Nodes: OpenAI fallback도 실패: {openai_error}")
                    raise openai_error
            else:
                print("Chat Nodes: OpenAI 모델이 초기화되지 않음")
                raise e
        else:
            raise e


async def _astream_with_fallback(prompt: str, primary_model, fallback_model):
    """
    Stream LLM with Gemini 키 2개 -> OpenAI 순차 fallback.

    Args:
        prompt: LLM prompt
        primary_model: Primary Gemini model
        fallback_model: OpenAI fallback model

    Yields:
        LLM chunks
    """
    # 1차: Primary Gemini (key 1)
    try:
        async for chunk in primary_model.astream(prompt):
            yield chunk
        return
    except Exception as e:
        error_str = str(e).lower()
        rate_limit_indicators = ['429', 'quota', 'rate limit', 'exceeded', 'resource_exhausted']

        if any(indicator in error_str for indicator in rate_limit_indicators):
            print(f"Chat Nodes: Gemini 키 1 rate limit 감지: {e}")

            # 2차: Gemini backup (key 2)
            if LLM_GEMINI_BACKUP:
                try:
                    print("Chat Nodes: Gemini 키 2로 fallback 시도")
                    async for chunk in LLM_GEMINI_BACKUP.astream(prompt):
                        yield chunk
                    return
                except Exception as backup_error:
                    print(f"Chat Nodes: Gemini 키 2도 실패: {backup_error}")

            # 3차: OpenAI fallback
            if fallback_model:
                try:
                    print("Chat Nodes: OpenAI fallback으로 스트리밍 시작")
                    async for chunk in fallback_model.astream(prompt):
                        yield chunk
                    return
                except Exception as openai_error:
                    print(f"Chat Nodes: OpenAI fallback도 실패: {openai_error}")
                    raise openai_error
            else:
                print("Chat Nodes: OpenAI 모델이 초기화되지 않음")
                raise e
        else:
            raise e


# ============================================================================
# Node 1: Determine Search Requirements
# ============================================================================

async def determine_search_node(state: RAGState, config: RunnableConfig) -> RAGState:
    """
    Determine search requirements for the query.

    Ported from SimpleAnswererAgent._needs_search() and _needs_scraping().

    Updates state with:
        - search_flags: Dict with needs_web_search, needs_vector_search, needs_scraping
        - Corresponding query strings and URLs
    """
    print("\n" + "="*60)
    print("💬 [Chat Flow] Step 1: Determine Search Requirements")
    print("="*60 + "\n")

    query = state["original_query"]
    current_date = datetime.now().strftime('%Y년 %m월 %d일')

    # Determine web/vector search needs
    search_prompt = f"""
당신은 AI 어시스턴트입니다. 사용자의 질문에 답변하기 위해 검색이 필요한지 판단하세요.
질문: {query}
오늘 날짜 : {current_date}
Web 검색이 필요하면 True, 아니면 False를 반환하세요.
Vector DB 검색이 필요하면 True, 아니면 False를 반환하세요.
- Web 검색은 최근 정보, 이슈, 간단한 정보가 필요할 때 사용
- Vector DB 검색은 특정 데이터, 문서, 현황, 통계, 내부 정보가 필요할 때 사용

다음과 같은 순서/형식으로 응답하세요:
{{
    "needs_web_search": false,
    "web_search_query": "웹 검색 쿼리",
    "needs_vector_search": false,
    "vector_search_query": "벡터 DB 검색 쿼리"
}}

웹 검색 쿼리 예시
- "2025년 최신 건강기능식품 트렌드"
벡터 검색 쿼리 예시
- "2025년 유행하는 건강식품이 뭐가 있나요?"

웹 검색 쿼리는 키워드 기반 문장으로
벡터 검색 쿼리는 질문형식으로 작성하세요
"""

    try:
        response = await _invoke_with_fallback(search_prompt, LLM_LITE, LLM_OPENAI_MINI)
        response_content = response.content.strip()

        # Parse JSON response
        try:
            clean_response = response_content
            if "```json" in response_content:
                clean_response = response_content.split("```json")[1].split("```")[0].strip()
            elif "```" in response_content:
                clean_response = response_content.split("```")[1].split("```")[0].strip()

            response_json = json.loads(clean_response)
            needs_web_search = response_json.get("needs_web_search", False)
            web_search_query = response_json.get("web_search_query", "")
            needs_vector_search = response_json.get("needs_vector_search", False)
            vector_search_query = response_json.get("vector_search_query", "")

        except json.JSONDecodeError as e:
            print(f"   ⚠️ JSON 파싱 실패, fallback 파싱 사용: {e}")
            # Fallback: keyword matching
            needs_web_search = "needs_web_search\": true" in response_content or "needs_web_search\":true" in response_content
            needs_vector_search = "needs_vector_search\": true" in response_content or "needs_vector_search\":true" in response_content
            web_search_query = ""
            vector_search_query = ""

    except Exception as e:
        print(f"   ❌ Search determination error: {e}")
        needs_web_search = False
        web_search_query = ""
        needs_vector_search = False
        vector_search_query = ""

    # Determine scraping needs
    scraping_prompt = f"""
사용자의 질문을 분석하여 웹페이지 스크래핑이 필요한지 판단하세요.

질문: {query}

다음 경우에 스크래핑이 필요합니다:
1. 특정 URL/링크의 내용을 분석하라고 요청하는 경우
2. "이 링크", "해당 사이트", "이 페이지" 등의 표현이 있는 경우
3. URL이 직접 포함된 경우
4. 특정 웹사이트의 상세한 내용 분석을 요청하는 경우
5. "전체 내용", "상세 분석", "보고서 작성" 등의 키워드가 있으면서 검색을 요구하는 경우

응답 형식:
{{
    "needs_scraping": true/false,
    "urls": ["url1", "url2"]  // 발견된 URL들, 없으면 빈 배열
}}

URL 패턴: http://, https://로 시작하는 문자열을 찾아주세요.
"""

    needs_scraping = False
    scraping_urls = []

    try:
        response = await _invoke_with_fallback(scraping_prompt, LLM_LITE, LLM_OPENAI_MINI)
        response_content = response.content.strip()

        # Parse JSON
        try:
            clean_response = response_content
            if "```json" in response_content:
                clean_response = response_content.split("```json")[1].split("```")[0].strip()
            elif "```" in response_content:
                clean_response = response_content.split("```")[1].split("```")[0].strip()

            response_json = json.loads(clean_response)
            needs_scraping = response_json.get("needs_scraping", False)
            scraping_urls = response_json.get("urls", [])

        except json.JSONDecodeError:
            print("   ⚠️ Scraping JSON 파싱 실패, 직접 URL 추출 시도")

        # Always try direct URL extraction from query
        import re
        url_pattern = r'https?://[^\s]+'
        found_urls = re.findall(url_pattern, query)

        # Domain/path pattern (e.g., parking.airport.kr/reserve/6130_01)
        domain_pattern = r'[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}/[^\s]*'
        domain_urls = re.findall(domain_pattern, query)
        for domain_url in domain_urls:
            if not domain_url.startswith(('http://', 'https://')):
                found_urls.append(f"https://{domain_url}")

        scraping_urls.extend(found_urls)

        # Deduplicate and validate URLs
        valid_urls = []
        for url in set(scraping_urls):
            if url and (url.startswith(('http://', 'https://')) or ('.' in url and '/' in url)):
                if not url.startswith(('http://', 'https://')):
                    url = f"https://{url}"
                valid_urls.append(url)

        scraping_urls = valid_urls
        needs_scraping = len(scraping_urls) > 0

    except Exception as e:
        print(f"   ❌ Scraping determination error: {e}")
        needs_scraping = False
        scraping_urls = []

    # Update state
    new_state = dict(state)
    new_state["search_flags"] = {
        "needs_web_search": needs_web_search,
        "web_search_query": web_search_query,
        "needs_vector_search": needs_vector_search,
        "vector_search_query": vector_search_query,
        "needs_scraping": needs_scraping,
        "scraping_urls": scraping_urls
    }

    # Add to execution log
    execution_log = list(state.get("execution_log", []))
    execution_log.append(f"Search requirements determined: web={needs_web_search}, vector={needs_vector_search}, scrape={needs_scraping}")
    new_state["execution_log"] = execution_log

    print(f"   ✓ 웹 검색: {needs_web_search} ({web_search_query})")
    print(f"   ✓ 벡터 검색: {needs_vector_search} ({vector_search_query})")
    print(f"   ✓ 스크래핑: {needs_scraping} ({len(scraping_urls)}개 URL)")

    return new_state


# ============================================================================
# Node 2: Web Search
# ============================================================================

async def web_search_node(state: RAGState, config: RunnableConfig) -> RAGState:
    """
    Perform web search if needed.

    Ported from SimpleAnswererAgent._simple_web_search().

    Updates state with:
        - web_results: List of SearchResult dicts
    """
    print("\n" + "="*60)
    print("🌐 [Chat Flow] Step 2: Web Search")
    print("="*60 + "\n")

    search_flags = state.get("search_flags", {})
    needs_web_search = search_flags.get("needs_web_search", False)
    web_search_query = search_flags.get("web_search_query", "")

    if not needs_web_search or not web_search_query:
        print("   ⏭️  Web search not needed, skipping")
        return state

    print(f"   🔍 Performing web search: {web_search_query}")

    try:
        # Run web search in executor
        result_text = await asyncio.get_event_loop().run_in_executor(
            None,
            debug_web_search,
            web_search_query
        )

        # Parse results into SearchResult objects
        search_results = []
        if result_text and isinstance(result_text, str):
            lines = result_text.split('\n')
            current_result = {}

            for line in lines:
                line = line.strip()
                if line.startswith(('1.', '2.', '3.', '4.', '5.')):
                    # Save previous result
                    if current_result:
                        search_result = SearchResult(
                            source="web_search",
                            content=current_result.get("snippet", ""),
                            search_query=web_search_query,
                            title=current_result.get("title", "웹 검색 결과"),
                            url=current_result.get("link"),
                            relevance_score=0.9,
                            timestamp=datetime.now().isoformat(),
                            document_type="web",
                            metadata={"original_query": web_search_query, **current_result},
                            source_url=current_result.get("link", "웹 검색 결과")
                        )
                        search_results.append(search_result)

                    # Start new result
                    current_result = {"title": line[3:].strip()}
                elif line.startswith("출처 링크:"):
                    current_result["link"] = line[7:].strip()
                elif line.startswith("요약:"):
                    current_result["snippet"] = line[3:].strip()

            # Save last result
            if current_result:
                search_result = SearchResult(
                    source="web_search",
                    content=current_result.get("snippet", ""),
                    search_query=web_search_query,
                    title=current_result.get("title", "웹 검색 결과"),
                    url=current_result.get("link"),
                    relevance_score=0.9,
                    timestamp=datetime.now().isoformat(),
                    document_type="web",
                    metadata={"original_query": web_search_query, **current_result},
                    source_url=current_result.get("link", "웹 검색 결과")
                )
                search_results.append(search_result)

        # Take top 3 results
        search_results = search_results[:3]

        # Convert SearchResult objects to dicts for state
        web_results_dicts = [
            {
                "source": r.source,
                "content": r.content,
                "search_query": r.search_query,
                "title": r.title,
                "url": r.url if hasattr(r, 'url') else None,
                "relevance_score": r.relevance_score if hasattr(r, 'relevance_score') else 0.9,
                "score": getattr(r, 'score', 0.9),
                "timestamp": r.timestamp if hasattr(r, 'timestamp') else datetime.now().isoformat(),
                "document_type": r.document_type if hasattr(r, 'document_type') else "web",
                "metadata": r.metadata if hasattr(r, 'metadata') else {},
                "source_url": r.source_url if hasattr(r, 'source_url') else ""
            }
            for r in search_results
        ]

        # Update state (reducer will accumulate)
        new_state = dict(state)
        new_state["web_results"] = web_results_dicts

        # Add to execution log
        execution_log = list(state.get("execution_log", []))
        execution_log.append(f"Web search completed: {len(search_results)} results")
        new_state["execution_log"] = execution_log

        print(f"   ✓ Web search completed: {len(search_results)} results")

        return new_state

    except Exception as e:
        print(f"   ❌ Web search error: {e}")
        # Return state unchanged
        return state


# ============================================================================
# Node 3: Vector Search
# ============================================================================

async def vector_search_node(state: RAGState, config: RunnableConfig) -> RAGState:
    """
    Perform vector DB search if needed.

    Ported from SimpleAnswererAgent._simple_vector_search().

    Updates state with:
        - vector_results: List of SearchResult dicts
    """
    print("\n" + "="*60)
    print("📚 [Chat Flow] Step 3: Vector Search")
    print("="*60 + "\n")

    search_flags = state.get("search_flags", {})
    needs_vector_search = search_flags.get("needs_vector_search", False)
    vector_search_query = search_flags.get("vector_search_query", "")

    if not needs_vector_search or not vector_search_query:
        print("   ⏭️  Vector search not needed, skipping")
        return state

    print(f"   🔍 Performing vector search: {vector_search_query}")

    try:
        # Run vector search in executor
        loop = asyncio.get_event_loop()
        results = await loop.run_in_executor(
            _global_executor,
            vector_db_search,
            vector_search_query
        )

        # Convert to SearchResult objects
        search_results = []
        for result in results[:3]:  # Top 3 results
            if isinstance(result, dict):
                doc_link = result.get("source_url", "")
                page_number = result.get("page_number", [])
                doc_title = result.get("title", "")
                meta_data = result.get("meta_data", {})

                # Add page numbers to title
                full_title = f"{doc_title}, ({', '.join([f'p.{num}' for num in page_number])})".strip()
                score = result.get("score", 5.2)
                chunk_id = result.get("chunk_id", "")

                search_result = SearchResult(
                    source="vector_db",
                    content=result.get("content", ""),
                    search_query=vector_search_query,
                    title=full_title,
                    document_type="database",
                    score=score,
                    metadata=meta_data,
                    url=doc_link,
                    chunk_id=chunk_id,
                )
                search_results.append(search_result)

        # Convert to dicts for state
        vector_results_dicts = [
            {
                "source": r.source,
                "content": r.content,
                "search_query": r.search_query,
                "title": r.title,
                "url": r.url if hasattr(r, 'url') else None,
                "score": r.score if hasattr(r, 'score') else 0.7,
                "relevance_score": getattr(r, 'relevance_score', 0.7),
                "document_type": r.document_type if hasattr(r, 'document_type') else "database",
                "metadata": r.metadata if hasattr(r, 'metadata') else {},
                "chunk_id": r.chunk_id if hasattr(r, 'chunk_id') else ""
            }
            for r in search_results
        ]

        # Update state
        new_state = dict(state)
        new_state["vector_results"] = vector_results_dicts

        # Add to execution log
        execution_log = list(state.get("execution_log", []))
        execution_log.append(f"Vector search completed: {len(search_results)} results")
        new_state["execution_log"] = execution_log

        print(f"   ✓ Vector search completed: {len(search_results)} results")

        return new_state

    except Exception as e:
        print(f"   ❌ Vector search error: {e}")
        return state


# ============================================================================
# Node 4: Scraping
# ============================================================================

async def scrape_node(state: RAGState, config: RunnableConfig) -> RAGState:
    """
    Scrape content from URLs if needed.

    Ported from SimpleAnswererAgent._scrape_content().

    Updates state with:
        - scraped_content: List of SearchResult dicts
    """
    print("\n" + "="*60)
    print("🔗 [Chat Flow] Step 4: Web Scraping")
    print("="*60 + "\n")

    search_flags = state.get("search_flags", {})
    needs_scraping = search_flags.get("needs_scraping", False)
    scraping_urls = search_flags.get("scraping_urls", [])

    if not needs_scraping or not scraping_urls:
        print("   ⏭️  Scraping not needed, skipping")
        return state

    print(f"   🔍 Scraping {len(scraping_urls)} URLs")

    query = state["original_query"]
    scraping_results = []

    # Process up to 3 URLs
    for url in scraping_urls[:3]:
        try:
            print(f"   📄 Scraping: {url}")

            # Run scraping in executor
            loop = asyncio.get_event_loop()
            content = await loop.run_in_executor(
                _global_executor,
                scrape_and_extract_content,
                json.dumps({"url": url, "query": query})
            )

            # Extract title from URL
            title = url.split("/")[-1] if "/" in url else url
            if title.endswith('.pdf'):
                title = f"PDF: {title}"

            search_result = SearchResult(
                source="scraper",
                content=content,
                search_query=query,
                title=title,
                url=url,
                document_type="web_scraping",
                score=1.0,
                metadata={
                    "scraping_query": query,
                    "original_url": url,
                    "content_length": len(content)
                },
                chunk_id=f"scrape_{hash(url)}"
            )
            scraping_results.append(search_result)

            print(f"      ✓ Scraped: {len(content)} characters")

        except Exception as e:
            print(f"      ❌ Scraping error for {url}: {e}")
            # Add error result
            error_result = SearchResult(
                source="scraper",
                content=f"스크래핑 실패: {str(e)}",
                search_query=query,
                title="스크래핑 오류",
                url=url,
                document_type="error",
                score=0.0,
                metadata={"error": str(e)},
                chunk_id=f"error_{hash(url)}"
            )
            scraping_results.append(error_result)

    # Convert to dicts
    scraped_dicts = [
        {
            "source": r.source,
            "content": r.content,
            "search_query": r.search_query,
            "title": r.title,
            "url": r.url if hasattr(r, 'url') else None,
            "score": r.score if hasattr(r, 'score') else 1.0,
            "document_type": r.document_type if hasattr(r, 'document_type') else "web_scraping",
            "metadata": r.metadata if hasattr(r, 'metadata') else {},
            "chunk_id": r.chunk_id if hasattr(r, 'chunk_id') else ""
        }
        for r in scraping_results
    ]

    # Update state
    new_state = dict(state)
    new_state["scraped_content"] = scraped_dicts

    # Add to execution log
    execution_log = list(state.get("execution_log", []))
    execution_log.append(f"Scraping completed: {len(scraping_results)} results")
    new_state["execution_log"] = execution_log

    print(f"   ✓ Scraping completed: {len(scraping_results)} results")

    return new_state


# ============================================================================
# Helper Functions for Answer Generation
# ============================================================================

def _build_memory_context(conversation_history: List[dict]) -> str:
    """
    Build memory context from conversation history.

    Ported from SimpleAnswererAgent._build_memory_context().
    """
    if not conversation_history:
        return ""

    memory_parts = []
    extracted_data = {
        "regions": set(),
        "food_items": set(),
        "numbers": [],
        "dates": set(),
        "key_facts": set()
    }

    for msg in conversation_history:
        msg_type = msg.get("type", "")
        content = msg.get("content", "")

        if not content.strip():
            continue

        # User message
        if msg_type == "user":
            memory_parts.append(f"**사용자**: {content}")
        # Assistant message
        elif msg_type == "assistant":
            # Extract key data
            key_data = _extract_key_data_from_content(content)
            extracted_data["regions"].update(key_data["regions"])
            extracted_data["food_items"].update(key_data["food_items"])
            extracted_data["numbers"].extend(key_data["numbers"])
            extracted_data["dates"].update(key_data["dates"])
            extracted_data["key_facts"].update(key_data["key_facts"])

            # Summarize long responses
            if len(content) > 200:
                summary = content[:200] + "..." + content[-100:] if len(content) > 300 else content[:200] + "..."
                memory_parts.append(f"**AI**: {summary}")
            else:
                memory_parts.append(f"**AI**: {content}")

    if memory_parts:
        # Basic conversation context
        context = "### 이 채팅방의 이전 대화 내용\n" + "\n\n".join(memory_parts[-4:]) + "\n"

        # Add extracted key data
        if any([extracted_data["regions"], extracted_data["food_items"], extracted_data["key_facts"]]):
            context += "\n### 이전 대화에서 언급된 핵심 정보\n"

            if extracted_data["regions"]:
                context += f"**언급된 지역**: {', '.join(list(extracted_data['regions'])[:10])}\n"

            if extracted_data["food_items"]:
                context += f"**언급된 식재료/농산물**: {', '.join(list(extracted_data['food_items'])[:10])}\n"

            if extracted_data["key_facts"]:
                context += f"**핵심 사실**: {', '.join(list(extracted_data['key_facts'])[:5])}\n"

            if extracted_data["dates"]:
                context += f"**관련 기간**: {', '.join(list(extracted_data['dates'])[:5])}\n"

        print(f"   🧠 Memory context generated: {len(memory_parts)} messages → {len(context)} chars")
        return context

    return ""


def _extract_key_data_from_content(content: str) -> dict:
    """Extract key data from AI response content."""
    import re

    extracted = {
        "regions": [],
        "food_items": [],
        "numbers": [],
        "dates": [],
        "key_facts": []
    }

    # Extract regions
    region_patterns = [
        r'(경기|충남|충북|전남|전북|경남|경북|강원|제주)\s*([가-힣]+[시군구]?)',
        r'([가-힣]+[시군구])',
        r'([가-힣]+군|[가-힣]+시)'
    ]
    for pattern in region_patterns:
        matches = re.findall(pattern, content)
        for match in matches:
            if isinstance(match, tuple):
                region = ' '.join(match).strip()
            else:
                region = match.strip()
            if region and len(region) > 1 and region not in extracted["regions"]:
                extracted["regions"].append(region)

    # Extract food items
    food_keywords = ["포도", "배", "사과", "쌀", "채소", "과일", "농산물", "축산물", "수산물", "곡물", "닭고기", "돼지고기", "소고기"]
    for keyword in food_keywords:
        if keyword in content and keyword not in extracted["food_items"]:
            extracted["food_items"].append(keyword)

    # Extract numbers
    number_patterns = [
        r'(\d+(?:\.\d+)?)\s*%',
        r'(\d+(?:,\d+)*)\s*억',
        r'(\d+(?:,\d+)*)\s*만',
        r'(\d+(?:\.\d+)?)\s*톤',
        r'(\d+(?:,\d+)*)\s*원'
    ]
    for pattern in number_patterns:
        matches = re.findall(pattern, content)
        for match in matches:
            if match not in extracted["numbers"]:
                extracted["numbers"].append(match)

    # Extract dates
    date_patterns = [
        r'20\d{2}년\s*\d+월',
        r'\d+월\s*\d+일',
        r'20\d{2}년'
    ]
    for pattern in date_patterns:
        matches = re.findall(pattern, content)
        for match in matches:
            if match not in extracted["dates"]:
                extracted["dates"].append(match)

    # Extract key facts
    key_fact_patterns = [
        r'(특별재난지역)',
        r'(집중호우\s*피해)',
        r'(생산량\s*[증가감소])',
        r'(가격\s*[상승하락])'
    ]
    for pattern in key_fact_patterns:
        matches = re.findall(pattern, content)
        for match in matches:
            if match not in extracted["key_facts"]:
                extracted["key_facts"].append(match)

    return extracted


def _generate_memory_summary(conversation_history: List[dict], current_query: str) -> str:
    """Generate memory summary guidance."""
    if not conversation_history:
        return "새로운 대화를 시작합니다."

    # Check for continuation keywords
    continuation_keywords = [
        "그", "그것", "그거", "위", "앞서", "이전", "방금", "아까", "저기", "거기",
        "그 중", "그중", "그런데", "그럼", "그래서", "따라서", "이어서", "계속해서",
        "추가로", "더", "또한", "그리고", "또", "한편", "반면", "대신"
    ]

    has_continuation = any(keyword in current_query for keyword in continuation_keywords)

    if has_continuation and len(conversation_history) >= 2:
        # Find recent user question and AI answer
        recent_user = None
        recent_ai = None

        for msg in reversed(conversation_history):
            if msg.get("type") == "user" and not recent_user:
                recent_user = msg.get("content", "")
            elif msg.get("type") == "assistant" and not recent_ai and recent_user:
                recent_ai = msg.get("content", "")
                break

        if recent_user and recent_ai:
            ai_summary = recent_ai[:100] + "..." if len(recent_ai) > 100 else recent_ai

            return f"""이전 대화 맥락을 고려하여 답변하세요.
답변 시작 시 다음 형식으로 이전 대화를 간단히 요약해주세요:
"이전에 문의하신 '{recent_user[:50]}{'...' if len(recent_user) > 50 else ''}'에 대해 {ai_summary}라고 답변드렸는데, 이를 바탕으로 말씀드리겠습니다."
그 다음 본격적인 답변을 이어서 해주세요."""

    return "이전 대화 내용을 참고하여 답변하세요."


def _create_enhanced_prompt_with_memory(
    query: str,
    all_search_results: List[Dict],
    state: RAGState
) -> str:
    """
    Create enhanced prompt with persona, memory, and search results.

    Ported from SimpleAnswererAgent._create_enhanced_prompt_with_memory().
    """
    current_date_str = datetime.now().strftime("%Y년 %m월 %d일")

    # Get persona
    persona_name = state.get("persona", "기본")
    persona_instruction = PERSONA_PROMPTS.get(persona_name, {}).get(
        "prompt",
        "당신은 친절하고 도움이 되는 AI 어시스턴트입니다."
    )

    # Get memory context
    memory_context = state.get("memory_context", "")
    memory_info = f"\n{memory_context}\n" if memory_context else ""

    # Create search results summary
    context_summary = ""
    if all_search_results:
        summary_parts = []
        for i, result in enumerate(all_search_results[:3]):
            content = result.get("content", "")
            title = result.get("title", "자료")

            # URL info
            url_info = ""
            if result.get("url"):
                url_info = f"\n  **출처 링크**: {result['url']}"
            elif result.get("source_url") and not result["source_url"].startswith(('웹 검색', 'Vector DB')):
                url_info = f"\n  **출처 링크**: {result['source_url']}"

            summary_parts.append(f"**[참고자료 {i}]** **{title}**: {content[:200]}...{url_info}")
        context_summary = "\n\n".join(summary_parts)

    # Memory summary
    memory_summary = ""
    conversation_history = state.get("metadata", {}).get("conversation_history", [])
    if memory_context and conversation_history:
        memory_summary = _generate_memory_summary(conversation_history, query)

    return f"""{persona_instruction}

위의 당신의 역할과 원칙을 반드시 지키면서 답변해주세요.

현재 날짜: {current_date_str}

{memory_info}

## 참고 정보
{context_summary if context_summary else "추가 참고 정보 없음"}

## 사용자 질문
{query}

## 응답 가이드
- **메모리 기반 답변**: {memory_summary}
- **페르소나 유지**: 당신의 역할에 맞는 말투와 관점을 일관되게 유지하세요.
- 자연스럽고 친근한 톤으로 답변
- 참고 정보가 있으면 이를 활용하되, 정확한 정보만 사용
- 불확실한 내용은 명시적으로 표현
- 간결하면서도 도움이 되는 답변 제공
- 필요시 추가 질문을 권유
- 마크다운 형식으로 답변 작성
- 마크다운의 '-', '*', '+', '##', '###' 등을 사용하여 가독성 좋은 답변 작성
- **중요**: 참고 정보를 사용할 때는 다음 형식으로 출처를 표기하세요:
  * 문장 끝에 [SOURCE:숫자1, 숫자2, 숫자3, ...] 형식으로 출처 번호를 표기 (숫자만 사용, "데이터"나 "문서" 등의 단어 사용 금지)
  * 예시: "건강기능식품 시장 규모는 6조 440억 원입니다 [SOURCE:0]"
  * 예시: "경쟁사의 경우 바이럴을 통한 마케팅 전략을 사용합니다 [SOURCE:1]"
  * 잘못된 예시: [SOURCE:데이터 1], [SOURCE:문서 1] (이런 형식 사용 금지)
  * 참고 정보의 인덱스 순서대로 0, 1, 2... 번호를 사용하세요

답변:"""


# ============================================================================
# Node 5: Memory Context
# ============================================================================

async def memory_context_node(state: RAGState, config: RunnableConfig) -> RAGState:
    """
    Build memory context from conversation history.

    Updates state with:
        - memory_context: String with formatted conversation context
    """
    print("\n" + "="*60)
    print("🧠 [Chat Flow] Step 5: Memory Context")
    print("="*60 + "\n")

    conversation_history = state.get("metadata", {}).get("conversation_history", [])
    conversation_id = state.get("conversation_id", "unknown")

    memory_context = _build_memory_context(conversation_history)

    if memory_context:
        print(f"   ✓ Memory context built: {len(conversation_history)} messages, {len(memory_context)} chars")
    else:
        print(f"   ℹ️  No memory context (new conversation)")

    # Update state
    new_state = dict(state)
    new_state["memory_context"] = memory_context

    # Add to execution log
    execution_log = list(state.get("execution_log", []))
    execution_log.append(f"Memory context built: {len(conversation_history)} messages")
    new_state["execution_log"] = execution_log

    return new_state


# ============================================================================
# Node 6: Generate Answer (Streaming)
# ============================================================================

async def generate_answer_node(state: RAGState, config: RunnableConfig) -> RAGState:
    """
    Generate final answer with streaming LLM.

    Ported from SimpleAnswererAgent.answer_streaming().

    Updates state with:
        - final_answer: Generated answer string
        - sources: List of source data for frontend
        - messages: AIMessage with generated content
    """
    print("\n" + "="*60)
    print("✨ [Chat Flow] Step 6: Generate Answer")
    print("="*60 + "\n")

    query = state["original_query"]

    # Validate and set persona
    selected_persona = state.get("persona", "기본")
    if selected_persona not in PERSONA_PROMPTS:
        print(f"   ⚠️  Unknown persona '{selected_persona}', using '기본'")
        selected_persona = "기본"

    print(f"   🎭 Using persona: '{selected_persona}'")

    # Gather all search results
    web_results = state.get("web_results", [])
    vector_results = state.get("vector_results", [])
    scraped_content = state.get("scraped_content", [])

    all_search_results = []
    all_search_results.extend(web_results)
    all_search_results.extend(vector_results)
    all_search_results.extend(scraped_content)

    print(f"   📚 Total search results: {len(all_search_results)} (web={len(web_results)}, vector={len(vector_results)}, scraped={len(scraped_content)})")

    # Create prompt
    prompt = _create_enhanced_prompt_with_memory(query, all_search_results, state)

    # Generate answer with streaming
    full_response = ""

    try:
        chunk_count = 0
        content_generated = False

        async for chunk in _astream_with_fallback(prompt, STREAMING_CHAT, LLM_OPENAI_MINI):
            chunk_count += 1
            if hasattr(chunk, 'content') and chunk.content:
                content_generated = True
                full_response += chunk.content
                print(f"   📝 Chunk {chunk_count}: {len(chunk.content)} chars", end='\r')

        print(f"\n   ✓ Answer generated: {chunk_count} chunks, {len(full_response)} chars")

        # Fallback if no content generated
        if not content_generated or not full_response.strip():
            print("   ⚠️  No content generated, using fallback response")
            full_response = f"""죄송합니다. 현재 시스템에 일시적인 문제가 있어 답변을 생성할 수 없습니다.

**사용자 질문**: {query}

다시 시도해 주시거나, 잠시 후에 다시 문의해 주세요."""

    except Exception as e:
        print(f"   ❌ LLM error: {e}")
        full_response = f"""죄송합니다. 현재 시스템에 일시적인 문제가 있어 답변을 생성할 수 없습니다.

**사용자 질문**: {query}

다시 시도해 주시거나, 잠시 후에 다시 문의해 주세요."""

    # Update state
    new_state = dict(state)
    new_state["final_answer"] = full_response

    # Add AIMessage to messages
    messages = list(state.get("messages", []))
    messages.append(AIMessage(content=full_response))
    new_state["messages"] = messages

    # Prepare sources for frontend
    if all_search_results:
        sources_data = []
        full_data_dict = {}

        for idx, result in enumerate(all_search_results[:10]):  # Max 10 sources
            source_data = {
                "id": idx + 1,
                "title": result.get("title", "자료"),
                "content": result.get("content", "")[:300] + "..." if len(result.get("content", "")) > 300 else result.get("content", ""),
                "url": result.get("url"),
                "source_url": result.get("source_url"),
                "source_type": result.get("source", "unknown")
            }
            sources_data.append(source_data)

            # full_data_dict (0-indexed)
            full_data_dict[idx] = {
                "title": result.get("title", "자료"),
                "content": result.get("content", ""),
                "source": result.get("source", "unknown"),
                "url": result.get("url", ""),
                "source_url": result.get("source_url", ""),
                "score": result.get("score", result.get("relevance_score", 0.0)),
                "document_type": result.get("document_type", "unknown")
            }

        # Add sources to metadata
        metadata = dict(state.get("metadata", {}))
        metadata["sources"] = sources_data
        metadata["full_data_dict"] = full_data_dict
        metadata["simple_answer_completed"] = True
        new_state["metadata"] = metadata

        # Add sources to state.sources (for LangGraph accumulation)
        new_state["sources"] = [
            {
                "title": result.get("title", "자료"),
                "content": result.get("content", ""),
                "url": result.get("url"),
                "source": result.get("source", "unknown"),
                "score": result.get("score", result.get("relevance_score", 0.0))
            }
            for result in all_search_results[:10]
        ]

        print(f"   📑 Sources prepared: {len(sources_data)} items")

    # Add to execution log
    execution_log = list(state.get("execution_log", []))
    execution_log.append(f"Answer generated: {len(full_response)} chars")
    new_state["execution_log"] = execution_log

    return new_state
