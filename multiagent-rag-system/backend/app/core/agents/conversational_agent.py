import json
import asyncio
import os
import sys
from typing import AsyncGenerator, List
from datetime import datetime
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI

# Fallback 시스템 import (Docker 볼륨 마운트된 utils 폴더)
sys.path.append('/app')
from utils.model_fallback import ModelFallbackManager

from ..models.models import StreamingAgentState, SearchResult
from ...services.search.search_tools import vector_db_search
from ...services.search.search_tools import debug_web_search
from .orchestrator import OrchestratorAgent

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
        self.streaming_chat = ChatGoogleGenerativeAI(
            model=model, temperature=temperature
        )
        self.llm_lite = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash-lite", temperature=temperature
        )

        # Gemini 백업 키와 OpenAI fallback 모델들
        # ModelFallbackManager는 이미 상단에서 import됨
        
        # Gemini 백업 모델 (두 번째 키)
        try:
            self.llm_gemini_backup = ChatGoogleGenerativeAI(
                model="gemini-2.5-flash-lite",
                temperature=temperature,
                google_api_key=ModelFallbackManager.GEMINI_KEY_2
            )
            print("SimpleAnswererAgent: Gemini 백업 모델 (키 2) 초기화 완료")
        except Exception as e:
            print(f"SimpleAnswererAgent: Gemini 백업 모델 초기화 실패: {e}")
            self.llm_gemini_backup = None
        
        # OpenAI fallback 모델
        self.openai_api_key = os.getenv("OPENAI_API_KEY")
        if self.openai_api_key:
            self.llm_openai_mini = ChatOpenAI(
                model="gpt-4o-mini",
                temperature=temperature,
                api_key=self.openai_api_key
            )
            print("SimpleAnswererAgent: OpenAI fallback 모델 초기화 완료")
        else:
            self.llm_openai_mini = None
            print("SimpleAnswererAgent: 경고: OPENAI_API_KEY가 설정되지 않음")

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

    async def answer_streaming(self, state: StreamingAgentState) -> AsyncGenerator[str, None]:
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
            results = await asyncio.get_event_loop().run_in_executor(
                None, vector_db_search, query
            )

            search_results = []
            for result in results[:3]:  # 상위 3개만
                if isinstance(result, dict):
                    search_result = SearchResult(
                        source="vector_db",
                        content=result.get("content", ""),
                        search_query=query,
                        title=result.get("title", "벡터 DB 문서"),
                        url=None,
                        relevance_score=result.get("similarity_score", 0.7),
                        timestamp=datetime.now().isoformat(),
                        document_type="database",
                        similarity_score=result.get("similarity_score", 0.7),
                        metadata=result
                    )
                    search_results.append(search_result)

            return search_results
        except Exception as e:
            print(f"벡터 검색 오류: {e}")
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
  * 문장 끝에 [SOURCE:숫자] 형식으로 출처 번호를 표기 (숫자만 사용, "데이터"나 "문서" 등의 단어 사용 금지)
  * 예시: "건강기능식품 시장 규모는 6조 440억 원입니다 [SOURCE:0]"
  * 예시: "경쟁사의 경우 바이럴을 통한 마케팅 전략을 사용합니다 [SOURCE:1]"
  * 잘못된 예시: [SOURCE:데이터 1], [SOURCE:문서 1] (이런 형식 사용 금지)
  * 참고 정보의 인덱스 순서대로 0, 1, 2... 번호를 사용하세요

답변:"""
