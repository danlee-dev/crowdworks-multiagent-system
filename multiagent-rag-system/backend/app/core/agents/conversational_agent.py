import json
import asyncio
import os
import sys
from typing import AsyncGenerator, List
from datetime import datetime
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI

# API Fallback 시스템 import
sys.path.append('/app/utils')
try:
    from api_fallback import api_manager
except ImportError:
    print("⚠️ api_fallback 모듈을 찾을 수 없음, 기본 방식 사용")
    api_manager = None

from ..models.models import StreamingAgentState, SearchResult
from ...services.search.search_tools import vector_db_search
from ...services.search.search_tools import debug_web_search, scrape_and_extract_content
from .orchestrator import OrchestratorAgent
from concurrent.futures import ThreadPoolExecutor

_global_executor = ThreadPoolExecutor(max_workers=16, thread_name_prefix="search_worker")

# 추가: 페르소나 프롬프트 로드
PERSONA_PROMPTS = {}
try:
    import os
    current_dir = os.path.dirname(os.path.abspath(__file__))
    file_path = os.path.join(current_dir, "prompts", "persona_prompts.json")
    with open(file_path, "r", encoding="utf-8") as f:
        PERSONA_PROMPTS = json.load(f)
    print(f"SimpleAnswererAgent: 페르소나 프롬프트 로드 성공 ({len(PERSONA_PROMPTS)}개).")
except Exception as e:
    print(f"SimpleAnswererAgent: 페르소나 프롬프트 로드 실패 - {e}")


class SimpleAnswererAgent:
    """단순 질문 전용 Agent - 새로운 아키텍처에 맞게 최적화"""

    def __init__(self, model: str = "gemini-2.5-flash-lite", temperature: float = 0.7):
        # 기본 모델들 (기존 방식 유지)
        self.streaming_chat = ChatGoogleGenerativeAI(
            model=model, temperature=temperature
        )
        self.llm_lite = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash-lite", temperature=temperature
        )

        # Fallback 모델들 (새로운 통합 시스템 사용)
        if api_manager:
            try:
                self.llm_gemini_backup = api_manager.create_langchain_model("gemini-2.5-flash-lite", temperature=temperature)
                self.llm_openai_mini = api_manager.create_langchain_model("gpt-4o-mini", temperature=temperature)
                print(f"SimpleAnswererAgent: Fallback 모델 초기화 완료 (사용 API: {api_manager.last_successful_api})")
            except Exception as e:
                print(f"SimpleAnswererAgent: Fallback 모델 초기화 실패: {e}")
                self.llm_gemini_backup = None
                self.llm_openai_mini = None
        else:
            # 기존 방식 fallback
            self.openai_api_key = os.getenv("OPENAI_API_KEY")
            if self.openai_api_key:
                self.llm_openai_mini = ChatOpenAI(
                    model="gpt-4o-mini",
                    temperature=temperature,
                    api_key=self.openai_api_key
                )
                print("SimpleAnswererAgent: OpenAI fallback 모델 초기화 완료 (기존 방식)")
            else:
                self.llm_openai_mini = None
            self.llm_gemini_backup = None
            print("SimpleAnswererAgent: 경고: 통합 API 관리자 없음, 제한된 fallback 사용")

        self.agent_type = "SIMPLE_ANSWERER"
        self.personas = PERSONA_PROMPTS

    async def _astream_with_fallback(self, prompt, primary_model, fallback_model):
        """
        스트리밍을 위한 Gemini 키 2개 -> OpenAI 순차 fallback 처리
        """
        # 1차: 기본 Gemini 모델 (키 1) 시도
        try:
            async for chunk in primary_model.astream(prompt):
                yield chunk
            return
        except Exception as e:
            error_str = str(e).lower()
            rate_limit_indicators = ['429', 'quota', 'rate limit', 'exceeded', 'resource_exhausted']

            if any(indicator in error_str for indicator in rate_limit_indicators):
                print(f"SimpleAnswererAgent: Gemini 키 1 rate limit 감지: {e}")

                # 2차: Gemini 백업 모델 (키 2) 시도
                if self.llm_gemini_backup:
                    try:
                        print("SimpleAnswererAgent: Gemini 키 2로 fallback 시도")
                        async for chunk in self.llm_gemini_backup.astream(prompt):
                            yield chunk
                        return
                    except Exception as backup_error:
                        print(f"SimpleAnswererAgent: Gemini 키 2도 실패: {backup_error}")

                # 3차: OpenAI fallback 시도
                if fallback_model:
                    try:
                        print("SimpleAnswererAgent: OpenAI fallback으로 스트리밍 시작")
                        async for chunk in fallback_model.astream(prompt):
                            yield chunk
                        return
                    except Exception as openai_error:
                        print(f"SimpleAnswererAgent: OpenAI fallback도 실패: {openai_error}")
                        raise openai_error
                else:
                    print("SimpleAnswererAgent: OpenAI 모델이 초기화되지 않음")
                    raise e
            else:
                raise e

    async def _invoke_with_fallback(self, prompt, primary_model, fallback_model):
        """
        Gemini 키 2개 -> OpenAI 순차 fallback 처리
        """
        # 1차: 기본 Gemini 모델 (키 1) 시도
        try:
            result = await primary_model.ainvoke(prompt)
            return result
        except Exception as e:
            error_str = str(e).lower()
            rate_limit_indicators = ['429', 'quota', 'rate limit', 'exceeded', 'resource_exhausted']

            if any(indicator in error_str for indicator in rate_limit_indicators):
                print(f"SimpleAnswererAgent: Gemini 키 1 rate limit 감지: {e}")

                # 2차: Gemini 백업 모델 (키 2) 시도
                if self.llm_gemini_backup:
                    try:
                        print("SimpleAnswererAgent: Gemini 키 2로 fallback 시도")
                        result = await self.llm_gemini_backup.ainvoke(prompt)
                        print("SimpleAnswererAgent: Gemini 키 2 fallback 성공")
                        return result
                    except Exception as backup_error:
                        print(f"SimpleAnswererAgent: Gemini 키 2도 실패: {backup_error}")

                # 3차: OpenAI fallback 시도
                if fallback_model:
                    try:
                        print("SimpleAnswererAgent: OpenAI fallback 시도")
                        result = await fallback_model.ainvoke(prompt)
                        print("SimpleAnswererAgent: OpenAI fallback 성공")
                        return result
                    except Exception as openai_error:
                        print(f"SimpleAnswererAgent: OpenAI fallback도 실패: {openai_error}")
                        raise openai_error
                else:
                    print("SimpleAnswererAgent: OpenAI 모델이 초기화되지 않음")
                    raise e
            else:
                raise e

    async def answer_streaming(self, state: StreamingAgentState, run_manager=None) -> AsyncGenerator[str, None]:
        """스트리밍으로 페르소나 기반 답변을 생성하는 메서드"""
        print("\n>> SimpleAnswerer: 스트리밍 답변 시작")

        query = state["original_query"]  # 딕셔너리 접근 방식 사용

        # --- 수정: state에 페르소나 정보가 있는지 확인 ---
        print(f"🔍 SimpleAnswerer - state 내용: {list(state.keys())}")
        print(f"🎭 SimpleAnswerer - state에서 가져온 persona: {state.get('persona')} (기본값 전 raw)")

        selected_persona = state.get("persona", "기본")
        print(f"🎯 SimpleAnswerer - 최종 selected_persona: '{selected_persona}'")
        print(f"📝 SimpleAnswerer - 사용 가능한 personas: {list(self.personas.keys())}")

        # 선택된 페르소나가 유효한지 확인 (없으면 기본으로 설정)
        if selected_persona not in self.personas:
            print(f"❌ 알 수 없는 페르소나 '{selected_persona}', '기본'으로 설정")
            selected_persona = "기본"
            state["persona"] = selected_persona

        print(f"✅ 채팅에 '{selected_persona}' 페르소나 적용")
        # ---------------------------------------------

        # 간단한 벡터 검색 수행 (필요시)
        search_results = []
        need_web_search, web_search_query, need_vector_search, vector_search_query = await self._needs_search(query)

        print(f"- 검색 필요 여부: 웹={need_web_search}, 벡터={need_vector_search}")

        # 웹 검색 수행 및 결과 스트리밍
        if need_web_search:
            print(f"- 웹 검색 필요: {web_search_query}")
            web_results = await self._simple_web_search(web_search_query)
            if web_results:
                search_results.extend(web_results)
                # 웹 검색 결과를 프론트엔드로 스트리밍 (JSON 이벤트로)
                search_event = {
                    "type": "search_results",
                    "step": 1,
                    "tool_name": "web_search",
                    "query": web_search_query,
                    "results": [
                        {
                            "title": result.title,
                            "content_preview": result.content[:200] + "..." if len(result.content) > 200 else result.content,
                            "url": result.url if hasattr(result, 'url') else None,
                            "source": result.source,
                            "score": getattr(result, 'score', getattr(result, 'relevance_score', 0.9)),
                            "document_type": getattr(result, 'document_type', 'web')
                        }
                        for result in web_results
                    ],
                    # 🆕 Chat 모드 검색임을 표시
                    "is_intermediate_search": False,
                    "section_context": None,
                    "message_id": state.get("message_id")
                }
                yield json.dumps(search_event)
                print(f"- 웹 검색 결과 스트리밍 완료: {len(web_results)}개 결과")

        # 벡터 검색 수행 및 결과 스트리밍
        if need_vector_search:
            # Abort 체크
            if run_manager and run_manager.is_abort_requested(state.get("metadata", {}).get("run_id")):
                return
            
            print(f"- 벡터 검색 필요: {vector_search_query}")
            vector_results = await self._simple_vector_search(vector_search_query)
            if vector_results:
                search_results.extend(vector_results)
                # 벡터 검색 결과를 프론트엔드로 스트리밍 (JSON 이벤트로)
                search_event = {
                    "type": "search_results",
                    "step": 2,
                    "tool_name": "vector_db_search",
                    "query": vector_search_query,
                    "results": [
                        {
                            "title": result.title,
                            "content_preview": result.content[:200] + "..." if len(result.content) > 200 else result.content,
                            "url": result.url if hasattr(result, 'url') else None,
                            "source": result.source,
                            "score": getattr(result, 'relevance_score', getattr(result, 'score', 0.7)),
                            "document_type": result.document_type

                        }
                        for result in vector_results
                    ],
                    # 🆕 Chat 모드 검색임을 표시
                    "is_intermediate_search": False,
                    "section_context": None,
                    "message_id": state.get("message_id")
                }
                yield json.dumps(search_event)
                print(f"- 벡터 검색 결과 스트리밍 완료: {len(vector_results)}개 결과")

        # 스크래핑 수행 및 결과 스트리밍
        needs_scraping, urls = await self._needs_scraping(query)
        if needs_scraping and urls:
            # Abort 체크
            if run_manager and run_manager.is_abort_requested(state.get("metadata", {}).get("run_id")):
                return
            
            print(f"- 스크래핑 필요: {len(urls)}개 URL")
            scraping_results = []
            for url in urls[:3]:  # 최대 3개 URL만 처리
                # 각 URL 처리 전 abort 체크
                if run_manager and run_manager.is_abort_requested(state.get("metadata", {}).get("run_id")):
                    break
                    
                scrape_result = await self._scrape_content(url, query)
                scraping_results.append(scrape_result)
            
            if scraping_results:
                search_results.extend(scraping_results)
                # 스크래핑 결과를 프론트엔드로 스트리밍
                search_event = {
                    "type": "search_results", 
                    "step": 3,
                    "tool_name": "scraper",
                    "query": query,
                    "results": [
                        {
                            "title": result.title,
                            "content_preview": result.content[:200] + "..." if len(result.content) > 200 else result.content,
                            "url": result.url,
                            "source": result.source,
                            "score": result.score,
                            "document_type": result.document_type
                        }
                        for result in scraping_results
                    ],
                    "is_intermediate_search": False,
                    "section_context": None,
                    "message_id": state.get("message_id")
                }
                yield json.dumps(search_event)
                print(f"- 스크래핑 결과 스트리밍 완료: {len(scraping_results)}개 결과")

        # 대화 히스토리 추출 및 메모리 컨텍스트 생성
        conversation_history = state.get("metadata", {}).get("conversation_history", [])
        conversation_id = state.get("conversation_id", "unknown")
        memory_context = self._build_memory_context(conversation_history)
        if memory_context:
            print(f"- 채팅방 {conversation_id}: 메모리 컨텍스트 사용 ({len(conversation_history)}개 메시지, {len(memory_context)}자)")
        else:
            print(f"- 채팅방 {conversation_id}: 메모리 없음 (새 대화 또는 첫 메시지)")

        full_response = ""
        prompt = self._create_enhanced_prompt_with_memory(
            query, search_results, state
        )

        try:
            chunk_count = 0
            content_generated = False

            async for chunk in self._astream_with_fallback(
                prompt,
                self.streaming_chat,
                self.llm_openai_mini
            ):
                # 각 chunk 전에 abort 체크
                if run_manager and run_manager.is_abort_requested(state.get("metadata", {}).get("run_id")):
                    print(f"🛑 SimpleAnswerer LLM 스트리밍 중단됨")
                    return
                
                chunk_count += 1
                if hasattr(chunk, 'content') and chunk.content:
                    content_generated = True
                    full_response += chunk.content
                    yield chunk.content
                    print(f">> SimpleAnswerer 청크 {chunk_count}: {len(chunk.content)} 문자")

            print(f">> SimpleAnswerer 완료: 총 {chunk_count}개 청크, {len(full_response)} 문자")

            # 내용이 전혀 생성되지 않은 경우 fallback 처리
            if not content_generated or not full_response.strip():
                print(">> 경고: SimpleAnswerer에서 내용이 생성되지 않음, fallback 실행")
                fallback_response = f"""죄송합니다. 현재 시스템에 일시적인 문제가 있어 답변을 생성할 수 없습니다.

**사용자 질문**: {query}

다시 시도해 주시거나, 잠시 후에 다시 문의해 주세요."""
                yield fallback_response
                full_response = fallback_response

        except Exception as e:
            print(f"- LLM 스트리밍 오류: {e}")
            # fallback 응답
            fallback_response = f"""죄송합니다. 현재 시스템에 일시적인 문제가 있어 답변을 생성할 수 없습니다.

**사용자 질문**: {query}

다시 시도해 주시거나, 잠시 후에 다시 문의해 주세요."""

            yield fallback_response
            full_response = fallback_response

        state["final_answer"] = full_response
        state["metadata"]["simple_answer_completed"] = True

        # 출처 정보 저장 (프론트엔드에서 사용)
        if search_results:
            sources_data = []
            full_data_dict = {}

            for idx, result in enumerate(search_results[:10]):  # 최대 10개로 증가
                source_data = {
                    "id": idx + 1,
                    "title": getattr(result, 'metadata', {}).get("title", result.title or "자료"),
                    "content": result.content[:300] + "..." if len(result.content) > 300 else result.content,
                    "url": result.url if hasattr(result, 'url') else None,
                    "source_url": result.source_url if hasattr(result, 'source_url') else None,
                    "source_type": result.source if hasattr(result, 'source') else "unknown"
                }
                sources_data.append(source_data)

                # full_data_dict 생성 (0부터 시작하는 인덱스 사용)
                full_data_dict[idx] = {
                    "title": getattr(result, 'metadata', {}).get("title", result.title or "자료"),
                    "content": result.content,
                    "source": result.source if hasattr(result, 'source') else "unknown",
                    "url": result.url if hasattr(result, 'url') else "",
                    "source_url": result.source_url if hasattr(result, 'source_url') else "",
                    "score": getattr(result, 'relevance_score', getattr(result, 'score', 0.0)),
                    "document_type": getattr(result, 'document_type', 'unknown')
                }

            state["metadata"]["sources"] = sources_data

            # full_data_dict를 프론트엔드로 전송 (JSON 이벤트로)
            if full_data_dict:
                full_data_event = {
                    "type": "full_data_dict",
                    "data_dict": full_data_dict
                }
                yield json.dumps(full_data_event)
                print(f"- SimpleAnswerer full_data_dict 전송 완료: {len(full_data_dict)}개 항목")

        print(f"- 스트리밍 답변 생성 완료 (길이: {len(full_response)}자)")

    def _extract_key_data_from_content(self, content: str) -> dict:
        """AI 답변에서 핵심 데이터를 추출"""
        import re

        extracted = {
            "regions": [],
            "food_items": [],
            "numbers": [],
            "dates": [],
            "key_facts": []
        }

        # 지역명 추출 (예: 경기 가평, 충남 서산, 경남 산청 등)
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

        # 식재료/농산물 추출
        food_keywords = ["포도", "배", "사과", "쌀", "채소", "과일", "농산물", "축산물", "수산물", "곡물", "닭고기", "돼지고기", "소고기"]
        for keyword in food_keywords:
            if keyword in content and keyword not in extracted["food_items"]:
                extracted["food_items"].append(keyword)

        # 수치 정보 추출 (퍼센트, 억원, 톤 등)
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

        # 날짜/기간 추출
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

        # 특별재난지역, 피해지역 등 핵심 키워드 추출
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

    def _build_memory_context(self, conversation_history: List[dict]) -> str:
        """현재 채팅방의 대화 히스토리를 메모리 컨텍스트로 변환"""
        if not conversation_history:
            return ""

        # 최근 메시지부터 처리 (프론트엔드에서 이미 현재 채팅방의 slice(-6) 되어있음)
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

            # 사용자 메시지
            if msg_type == "user":
                memory_parts.append(f"**사용자**: {content}")
            # 어시스턴트 메시지 (요약 + 핵심 데이터 추출)
            elif msg_type == "assistant":
                # 핵심 데이터 추출
                key_data = self._extract_key_data_from_content(content)
                extracted_data["regions"].update(key_data["regions"])
                extracted_data["food_items"].update(key_data["food_items"])
                extracted_data["numbers"].extend(key_data["numbers"])
                extracted_data["dates"].update(key_data["dates"])
                extracted_data["key_facts"].update(key_data["key_facts"])

                # 긴 답변은 요약
                if len(content) > 200:
                    # 핵심 정보 추출 (첫 200자 + 마지막 100자)
                    summary = content[:200] + "..." + content[-100:] if len(content) > 300 else content[:200] + "..."
                    memory_parts.append(f"**AI**: {summary}")
                else:
                    memory_parts.append(f"**AI**: {content}")

        if memory_parts:
            # 기본 대화 컨텍스트
            context = "### 이 채팅방의 이전 대화 내용\n" + "\n\n".join(memory_parts[-4:]) + "\n"

            # 추출된 핵심 데이터 추가
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

            print(f"🧠 채팅방별 메모리 컨텍스트 생성: {len(memory_parts)}개 메시지 → {len(context)}자")
            print(f"   - 추출된 지역: {list(extracted_data['regions'])[:5]}")
            print(f"   - 추출된 식재료: {list(extracted_data['food_items'])[:5]}")
            return context

        return ""

    def _generate_memory_summary(self, conversation_history: List[dict], current_query: str) -> str:
        """이전 대화 내용과 현재 질문을 분석하여 메모리 요약 가이드 생성"""
        if not conversation_history:
            return "새로운 대화를 시작합니다."

        # 현재 질문에서 연속성 키워드 확인
        continuation_keywords = [
            "그", "그것", "그거", "위", "앞서", "이전", "방금", "아까", "저기", "거기",
            "그 중", "그중", "그런데", "그럼", "그래서", "따라서", "이어서", "계속해서",
            "추가로", "더", "또한", "그리고", "또", "한편", "반면", "대신"
        ]

        has_continuation = any(keyword in current_query for keyword in continuation_keywords)

        if has_continuation and len(conversation_history) >= 2:
            # 최근 사용자 질문과 AI 답변 추출
            recent_user = None
            recent_ai = None

            # 역순으로 찾기 (최근 것부터)
            for msg in reversed(conversation_history):
                if msg.get("type") == "user" and not recent_user:
                    recent_user = msg.get("content", "")
                elif msg.get("type") == "assistant" and not recent_ai and recent_user:
                    recent_ai = msg.get("content", "")
                    break

            if recent_user and recent_ai:
                # AI 답변 요약 (첫 100자)
                ai_summary = recent_ai[:100] + "..." if len(recent_ai) > 100 else recent_ai

                return f"""이전 대화 맥락을 고려하여 답변하세요.
답변 시작 시 다음 형식으로 이전 대화를 간단히 요약해주세요:
"이전에 문의하신 '{recent_user[:50]}{'...' if len(recent_user) > 50 else ''}'에 대해 {ai_summary}라고 답변드렸는데, 이를 바탕으로 말씀드리겠습니다."
그 다음 본격적인 답변을 이어서 해주세요."""

        return "이전 대화 내용을 참고하여 답변하세요."

    async def _simple_web_search(self, query: str) -> List[SearchResult]:
        """간단한 웹 검색"""
        try:
            result_text = await asyncio.get_event_loop().run_in_executor(
                None, debug_web_search, query
            )

            # 결과가 문자열인 경우 파싱
            search_results = []
            if result_text and isinstance(result_text, str):
                # 간단한 파싱으로 SearchResult 객체 생성
                lines = result_text.split('\n')
                current_result = {}

                for line in lines:
                    line = line.strip()
                    if line.startswith(('1.', '2.', '3.', '4.', '5.')):
                        # 이전 결과 저장
                        if current_result:
                            search_result = SearchResult(
                                source="web_search",
                                content=current_result.get("snippet", ""),
                                search_query=query,
                                title=current_result.get("title", "웹 검색 결과"),
                                url=current_result.get("link"),
                                relevance_score=0.9,  # 웹검색 결과는 높은 점수
                                timestamp=datetime.now().isoformat(),
                                document_type="web",
                                metadata={"original_query": query, **current_result},
                                source_url=current_result.get("link", "웹 검색 결과")
                            )
                            search_results.append(search_result)

                        # 새 결과 시작
                        current_result = {"title": line[3:].strip()}  # 번호 제거
                    elif line.startswith("출처 링크:"):
                        current_result["link"] = line[7:].strip()  # "출처 링크:" 제거
                    elif line.startswith("요약:"):
                        current_result["snippet"] = line[3:].strip()

                # 마지막 결과 저장
                if current_result:
                    search_result = SearchResult(
                        source="web_search",
                        content=current_result.get("snippet", ""),
                        search_query=query,
                        title=current_result.get("title", "웹 검색 결과"),
                        url=current_result.get("link"),
                        relevance_score=0.9,
                        timestamp=datetime.now().isoformat(),
                        document_type="web",
                        metadata={"original_query": query, **current_result},
                        source_url=current_result.get("link", "웹 검색 결과")
                    )
                    search_results.append(search_result)

            print(f"- 웹 검색 완료: {len(search_results)}개 결과")
            return search_results[:3]  # 상위 3개 결과만
        except Exception as e:
            print(f"웹 검색 오류: {e}")
            return []

    async def _simple_vector_search(self, query: str) -> List[SearchResult]:
        """간단한 벡터 검색"""
        try:
            print(f">> Simple Vector 검색 시작: {query}")

            # 전역 ThreadPoolExecutor 사용하여 병렬 처리
            loop = asyncio.get_event_loop()
            results = await loop.run_in_executor(
                _global_executor,  # 전역 executor 사용
                vector_db_search,
                query
            )

            search_results = []
            for result in results[:3]:  # 상위 3개만
                if isinstance(result, dict):
                    # 새로운 doc_link와 page_number 필드 사용
                    doc_link = result.get("source_url", "")
                    page_number = result.get("page_number", [])
                    # 문서 제목 추출
                    doc_title = result.get("title", "")
                    meta_data = result.get("meta_data", {})
                    # 제목에 페이지 번호 추가
                    full_title = f"{doc_title}, ({', '.join([f'p.{num}' for num in page_number])})".strip()
                    score = result.get("score", 5.2)
                    chunk_id = result.get("chunk_id", "")

                    search_result = SearchResult(
                        source="vector_db",
                        content=result.get("content", ""),
                        search_query=query,
                        title=full_title,
                        document_type="database",
                        score=score,
                        metadata=meta_data,
                        url=doc_link,  # 새 필드 추가
                        chunk_id=chunk_id,
                    )
                    search_results.append(search_result)

            print(f"  - Simple Vector 검색 완료: {len(search_results)}개 결과")
            return search_results
        except Exception as e:
            print(f"Simple Vector 검색 오류: {e}")
            return []

    async def _needs_search(self, query: str):
        """질문에 대한 검색이 필요한지 여부를 판단"""
        try:
            prompt = f"""
당신은 AI 어시스턴트입니다. 사용자의 질문에 답변하기 위해 검색이 필요한지 판단하세요.
질문: {query}
오늘 날짜 : {datetime.now().strftime('%Y년 %m월 %d일')}
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
            response = await self._invoke_with_fallback(
                prompt,
                self.llm_lite,
                self.llm_openai_mini
            )
            response_content = response.content.strip()

            # JSON 파싱 시도 - 개선된 파싱 로직
            try:
                # 코드 블록 제거
                clean_response = response_content
                if "```json" in response_content:
                    clean_response = response_content.split("```json")[1].split("```")[0].strip()
                elif "```" in response_content:
                    clean_response = response_content.split("```")[1].split("```")[0].strip()

                # JSON 파싱
                response_json = json.loads(clean_response)
                needs_web_search = response_json.get("needs_web_search", False)
                web_search_query = response_json.get("web_search_query", "")
                needs_vector_search = response_json.get("needs_vector_search", False)
                vector_search_query = response_json.get("vector_search_query", "")

                print(f"- 검색 판단 완료: 웹={needs_web_search}, 벡터={needs_vector_search}")
                return needs_web_search, web_search_query, needs_vector_search, vector_search_query

            except json.JSONDecodeError as e:
                print(f"- JSON 파싱 오류: {e}")
                print(f"- LLM 응답: {response_content[:200]}...")

                # 문자열 패턴 매칭으로 fallback 파�ing
                needs_web_search = False
                needs_vector_search = False

                # 응답에서 키워드 기반으로 판단
                if "needs_web_search" in response_content:
                    if "needs_web_search\": true" in response_content or "needs_web_search\":true" in response_content:
                        needs_web_search = True

                if "needs_vector_search" in response_content:
                    if "needs_vector_search\": true" in response_content or "needs_vector_search\":true" in response_content:
                        needs_vector_search = True

                print(f"- Fallback 파싱 결과: 웹={needs_web_search}, 벡터={needs_vector_search}")
                # 기본값 반환 (간단한 인사는 검색 불필요)
                return needs_web_search, "", needs_vector_search, ""

        except Exception as e:
            print(f"- _needs_search 오류: {e}")
            # 오류 시 기본값 반환
            return False, "", False, ""

    async def _scrape_content(self, url: str, query: str) -> SearchResult:
        """웹페이지 또는 PDF 내용을 스크래핑하여 SearchResult로 반환"""
        try:
            print(f">> 콘텐츠 스크래핑 시작: {url}")
            
            # scrape_and_extract_content 호출
            loop = asyncio.get_event_loop()
            content = await loop.run_in_executor(
                _global_executor,
                scrape_and_extract_content,
                json.dumps({"url": url, "query": query})
            )
            
            # URL에서 제목 추출 시도
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
                score=1.0,  # 명시적 스크래핑이므로 높은 점수
                metadata={
                    "scraping_query": query,
                    "original_url": url,
                    "content_length": len(content)
                },
                chunk_id=f"scrape_{hash(url)}"
            )
            
            print(f"  - 스크래핑 완료: {len(content)}자")
            return search_result
            
        except Exception as e:
            print(f"스크래핑 오류: {e}")
            # 오류 발생 시 빈 결과 반환
            return SearchResult(
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

    async def _needs_scraping(self, query: str) -> tuple[bool, list[str]]:
        """스크래핑이 필요한지 판단하고 URL 추출"""
        try:
            prompt = f"""
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
            
            response = await self._invoke_with_fallback(
                prompt,
                self.llm_lite,
                self.llm_openai_mini
            )
            response_content = response.content.strip()
            
            # JSON 파싱
            try:
                clean_response = response_content
                if "```json" in response_content:
                    clean_response = response_content.split("```json")[1].split("```")[0].strip()
                elif "```" in response_content:
                    clean_response = response_content.split("```")[1].split("```")[0].strip()
                
                response_json = json.loads(clean_response)
                needs_scraping = response_json.get("needs_scraping", False)
                urls = response_json.get("urls", [])
                
                # 추가로 query에서 URL 직접 추출 (더 정확한 패턴)
                import re
                # 기본 URL 패턴
                url_pattern = r'https?://[^\s]+'
                found_urls = re.findall(url_pattern, query)
                
                # 특수한 경우들 처리
                # 1. 도메인/path 형태 (예: parking.airport.kr/reserve/6130_01)
                domain_pattern = r'[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}/[^\s]*'
                domain_urls = re.findall(domain_pattern, query)
                for domain_url in domain_urls:
                    if not domain_url.startswith(('http://', 'https://')):
                        found_urls.append(f"https://{domain_url}")
                
                # 2. 숫자가 포함된 특수 ID (예: 6130_01)를 기존 URL에 추가
                if '6130_01' in query and any('parking.airport.kr' in url for url in found_urls):
                    base_urls = [url for url in found_urls if 'parking.airport.kr' in url]
                    for base_url in base_urls:
                        if not base_url.endswith('6130_01'):
                            if base_url.endswith('/'):
                                found_urls.append(f"{base_url}6130_01")
                            else:
                                found_urls.append(f"{base_url}/6130_01")
                
                urls.extend(found_urls)
                
                # 중복 제거 및 유효한 URL만 필터링
                valid_urls = []
                for url in set(urls):
                    if url and (url.startswith(('http://', 'https://')) or 
                               ('.' in url and '/' in url)):
                        if not url.startswith(('http://', 'https://')):
                            url = f"https://{url}"
                        valid_urls.append(url)
                
                urls = valid_urls
                
                print(f"- 스크래핑 판단: {needs_scraping}, URLs: {urls}")
                return needs_scraping, urls
                
            except json.JSONDecodeError:
                print(f"JSON 파싱 실패, 직접 URL 추출 시도")
                # 직접 URL 추출
                import re
                url_pattern = r'https?://[^\s]+'
                urls = re.findall(url_pattern, query)
                needs_scraping = len(urls) > 0
                return needs_scraping, urls
                
        except Exception as e:
            print(f"_needs_scraping 오류: {e}")
            return False, []


    def _create_enhanced_prompt_with_memory(
        self, query: str, search_results: List[SearchResult], state: StreamingAgentState
    ) -> str:
        """페르소나, 메모리, 검색 결과를 포함한 향상된 프롬프트를 생성합니다."""
        current_date_str = datetime.now().strftime("%Y년 %m월 %d일")

        # state에서 페르소나와 메모리 정보 추출
        persona_name = state.get("persona", "기본")
        persona_instruction = self.personas.get(persona_name, {}).get("prompt", "당신은 친절하고 도움이 되는 AI 어시스턴트입니다.")

        # 대화 히스토리에서 메모리 컨텍스트 생성
        conversation_history = state.get("metadata", {}).get("conversation_history", [])
        memory_context = self._build_memory_context(conversation_history)

        # 검색 결과 요약
        context_summary = ""
        if search_results:
            summary_parts = []
            for i, result in enumerate(search_results[:3]):
                content = result.content
                title = getattr(result, 'metadata', {}).get("title", result.title or "자료")

                # URL 정보 추가 (웹 검색 결과인 경우)
                url_info = ""
                if hasattr(result, 'url') and result.url:
                    url_info = f"\n  **출처 링크**: {result.url}"
                elif hasattr(result, 'source_url') and result.source_url and not result.source_url.startswith(('웹 검색', 'Vector DB')):
                    url_info = f"\n  **출처 링크**: {result.source_url}"

                summary_parts.append(f"**[참고자료 {i}]** **{title}**: {content[:200]}...{url_info}")
            context_summary = "\n\n".join(summary_parts)

        # 메모리 컨텍스트 처리
        memory_info = f"\n{memory_context}\n" if memory_context else ""

        # 메모리 기반 답변인지 확인하고 컨텍스트 요약 생성
        memory_summary = ""
        if memory_context and conversation_history:
            memory_summary = self._generate_memory_summary(conversation_history, query)

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
