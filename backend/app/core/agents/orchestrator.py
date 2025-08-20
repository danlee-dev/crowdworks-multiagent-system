import json
import sys
import asyncio
from typing import Dict, List, Any, Optional, Tuple, AsyncGenerator
from datetime import datetime
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
import re
import os
import aiofiles

from ..models.models import StreamingAgentState, SearchResult
from .worker_agents import DataGathererAgent, ProcessorAgent
from sentence_transformers import SentenceTransformer
from ...utils.session_logger import get_session_logger
from ...services.utils.deduplication import GlobalDeduplicator

# --- 페르소나 프롬프트 로드 ---
PERSONA_PROMPTS = {}
try:
    # 현재 파일(orchestrator.py)의 디렉토리 경로를 가져옵니다.
    current_dir = os.path.dirname(__file__)
    # JSON 파일의 절대 경로를 생성합니다.
    file_path = os.path.join(current_dir, "prompts", "persona_prompts.json")

    with open(file_path, "r", encoding="utf-8") as f:
        PERSONA_PROMPTS = json.load(f)
    print(f"OrchestratorAgent: 페르소나 프롬프트 로드 성공. (경로: {file_path})")
except FileNotFoundError:
    print(f"경고: 다음 경로에서 persona_prompts.json 파일을 찾을 수 없습니다: {file_path}")
except json.JSONDecodeError:
    print(f"경고: {file_path} 파일 파싱에 실패했습니다. JSON 형식을 확인해주세요.")
# -----------------------------

class TriageAgent:
    """요청 분류 및 라우팅 담당 Agent"""

    def __init__(self, model: str = "gemini-2.5-flash-lite", temperature: float = 0.1):
        self.llm = ChatGoogleGenerativeAI(model=model, temperature=temperature)

    async def classify_request(self, query: str, state: StreamingAgentState) -> StreamingAgentState:
        """요청을 분석하여 flow_type 결정"""
        session_id = state.get("session_id", "unknown")
        logger = get_session_logger(session_id, "TriageAgent")
        logger.info(f"요청 분류 시작 - '{query}'")

        classification_prompt = f"""
사용자 요청을 분석하여 적절한 처리 방식을 결정하세요:

사용자 요청: {query}

분류 기준:
1. **chat**: 간단한 질문, 일반적인 대화, 답담, 그리고 간단한 Web Search나, 내부 정보를 조회하여 답변할 수 있는 경우
   - 예: "안녕하세요", "감사합니다", "간단한 설명 요청", "최근 ~ 시세 알려줘", "최근 이슈 Top 10이 뭐야?"

2. **task**: 복합적인 분석, 데이터 수집, 리포트 생성이 필요, 정확히는 여러 섹션에 걸친 보고서 생성이 필요한 질문일 경우 또는, 자세한 영양 정보와 같은 RDB를 조회 해야하는 질문일 경우
   - 예: "~를 분석해줘", "~에 대한 자료를 찾아줘", "보고서 작성"

JSON으로 응답:
{{
    "flow_type": "chat" 또는 "task",
    "reasoning": "분류 근거 설명",
}}
"""

        try:
            response = await self.llm.ainvoke(classification_prompt)
            response_content = response.content.strip()

            # JSON 응답 추출 시도
            classification = None
            try:
                # 직접 파싱 시도
                classification = json.loads(response_content)
            except json.JSONDecodeError:
                # JSON 블록 찾기 시도
                import re
                json_match = re.search(r'\{.*\}', response_content, re.DOTALL)
                if json_match:
                    classification = json.loads(json_match.group())
                else:
                    raise ValueError("Valid JSON not found in response")

            # 필수 필드 확인
            required_fields = ["flow_type", "reasoning"]
            for field in required_fields:
                if field not in classification:
                    raise ValueError(f"Missing required field: {field}")

            # state 업데이트 (딕셔너리 접근 방식)
            state["flow_type"] = classification["flow_type"]
            state["metadata"].update({
                "triage_reasoning": classification["reasoning"],
                "classified_at": datetime.now().isoformat()
            })

            logger.info(f"분류 결과: {classification['flow_type']}")
            logger.info(f"근거: {classification['reasoning']}")

        except Exception as e:
            logger.error(f"분류 실패, 기본값(task) 적용: {e}")
            state["flow_type"] = "task"  # 기본값
            state["metadata"].update({
                "triage_error": str(e),
                "classified_at": datetime.now().isoformat()
            })

        return state


class OrchestratorAgent:
    """고성능 비동기 스케줄러 및 지능형 계획 수립 Agent"""

    def __init__(self, model: str = "gemini-2.5-pro", temperature: float = 0.2):
        self.llm = ChatGoogleGenerativeAI(model=model, temperature=temperature)
        self.llm_openai_mini = ChatOpenAI(model="gpt-4o", temperature=temperature)
        self.data_gatherer = DataGathererAgent()
        self.processor = ProcessorAgent()
        self.personas = PERSONA_PROMPTS

    def _build_memory_context(self, conversation_history: List[dict]) -> str:
        """현재 채팅방의 대화 히스토리를 메모리 컨텍스트로 변환 (OrchestratorAgent용)"""
        if not conversation_history:
            return ""

        memory_parts = []

        for msg in conversation_history:
            msg_type = msg.get("type", "")
            content = msg.get("content", "")

            if not content.strip():
                continue

            # 사용자 메시지
            if msg_type == "user":
                memory_parts.append(f"**사용자**: {content}")
            # 어시스턴트 메시지 (요약)
            elif msg_type == "assistant":
                # 긴 답변은 요약 (보고서는 더 짧게)
                if len(content) > 150:
                    summary = content[:150] + "..."
                    memory_parts.append(f"**AI**: {summary}")
                else:
                    memory_parts.append(f"**AI**: {content}")

        if memory_parts:
            context = "### 이 채팅방의 이전 대화 내용\n" + "\n\n".join(memory_parts[-3:]) + "\n"  # 보고서용은 3개만
            print(f"🧠 OrchestratorAgent 메모리 컨텍스트 생성: {len(memory_parts)}개 메시지 → {len(context)}자")
            return context

        return ""

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

    def _generate_memory_summary_for_report(self, conversation_history: List[dict], current_query: str) -> str:
        """보고서 생성용 메모리 요약 생성"""
        if not conversation_history:
            return ""

        # 연속성 키워드 확인
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

            # 이전 대화에서 핵심 데이터 추출
            extracted_data = {
                "regions": set(),
                "food_items": set(),
                "key_facts": set()
            }

            for msg in reversed(conversation_history):
                if msg.get("type") == "user" and not recent_user:
                    recent_user = msg.get("content", "")
                elif msg.get("type") == "assistant" and not recent_ai and recent_user:
                    recent_ai = msg.get("content", "")
                    # 핵심 데이터 추출
                    key_data = self._extract_key_data_from_content(recent_ai)
                    extracted_data["regions"].update(key_data["regions"])
                    extracted_data["food_items"].update(key_data["food_items"])
                    extracted_data["key_facts"].update(key_data["key_facts"])
                    break

            if recent_user and recent_ai:
                ai_summary = recent_ai[:80] + "..." if len(recent_ai) > 80 else recent_ai

                # 핵심 데이터를 포함한 요약 생성
                context_parts = []
                if extracted_data["regions"]:
                    context_parts.append(f"**관련 지역**: {', '.join(list(extracted_data['regions'])[:5])}")
                if extracted_data["food_items"]:
                    context_parts.append(f"**언급된 식재료**: {', '.join(list(extracted_data['food_items'])[:5])}")
                if extracted_data["key_facts"]:
                    context_parts.append(f"**핵심 사실**: {', '.join(list(extracted_data['key_facts'])[:3])}")

                context_info = "\n".join(context_parts) if context_parts else ""

                summary = f"""
## 이전 대화 요약

이전에 문의하신 **'{recent_user[:40]}{'...' if len(recent_user) > 40 else ''}'**에 대해 {ai_summary}라고 답변드렸으며, 이를 바탕으로 추가 분석을 진행하겠습니다.

{context_info}

---
"""
                print(f"🧠 보고서용 메모리 요약 생성: 지역 {len(extracted_data['regions'])}개, 식재료 {len(extracted_data['food_items'])}개")
                return summary

        return ""

    def get_available_personas(self) -> List[str]:
        """
        현재 로드된 모든 페르소나의 이름 목록을 반환합니다.
        프론트엔드에서 선택지를 동적으로 구성하는 데 사용할 수 있습니다.
        """
        if not self.personas:
            return []
        return list(self.personas.keys())

    async def suggest_team_for_query(self, query: str) -> str:
        """
        LLM이 쿼리 내용을 분석하여 가장 적합한 페르소나를 추천합니다.
        """
        if not self.personas:
            return "기본"

        # 사용 가능한 페르소나 목록과 설명 생성
        persona_descriptions = []
        for persona_name, persona_info in self.personas.items():
            description = persona_info.get("description", "설명 없음")
            persona_descriptions.append(f"- {persona_name}: {description}")

        personas_text = "\n".join(persona_descriptions)

        # LLM에게 페르소나 추천 요청
        prompt = f"""다음 사용자 질문을 분석하여 가장 적합한 전문가를 선택해주세요.

사용자 질문: "{query}"

사용 가능한 전문가들:
{personas_text}

위 전문가들 중에서 사용자의 질문에 가장 적합한 전문가 한 명을 선택하여, 정확히 그 이름만 답변해주세요.
예: 구매 담당자"""

        try:
            import os
            from langchain_openai import ChatOpenAI

            # OpenAI 클라이언트 생성
            openai_api_key = os.getenv("OPENAI_API_KEY")
            if not openai_api_key:
                print("🤖 OpenAI API 키가 없어서 기본 페르소나 사용")
                return "기본"

            llm = ChatOpenAI(
                model="gpt-4o-mini",
                temperature=0.1,
                max_tokens=50,
                api_key=openai_api_key
            )

            # LangChain HumanMessage, SystemMessage 방식으로 호출
            from langchain_core.messages import HumanMessage, SystemMessage

            messages = [
                SystemMessage(content="당신은 사용자의 질문을 분석하여 가장 적절한 전문가를 추천하는 AI입니다. 정확히 주어진 전문가 이름 중 하나만 답변하세요."),
                HumanMessage(content=prompt)
            ]

            response = await llm.ainvoke(messages)

            suggested_persona = response.content.strip()

            # 제안된 페르소나가 실제 목록에 있는지 확인
            if suggested_persona in self.personas:
                print(f"🤖 LLM 자동 라우팅: '{query[:30]}...' -> '{suggested_persona}'")
                return suggested_persona
            else:
                print(f"🤖 LLM 자동 라우팅: 잘못된 응답 '{suggested_persona}' -> '기본' 사용")
                return "기본"

        except Exception as e:
            print(f"🤖 LLM 자동 라우팅 오류: {e} -> '기본' 사용")
            return "기본"

    # ✅ 추가: 일관된 상태 메시지 생성을 위한 헬퍼 함수
    def _create_status_event(self, stage: str, sub_stage: str, message: str, details: Optional[Dict] = None) -> Dict:
        """표준화된 상태 이벤트 객체를 생성합니다."""
        return {
            "type": "status",
            "timestamp": datetime.now().isoformat(),
            "data": {
                "agent": "OrchestratorAgent",
                "stage": stage,
                "sub_stage": sub_stage,
                "message": message,
                "details": details or {}
            }
        }

    async def _invoke_with_fallback(self, prompt: str, primary_model, fallback_model):
        """Gemini API rate limit 시 OpenAI로 fallback 처리"""
        try:
            result = await primary_model.ainvoke(prompt)
            return result
        except Exception as e:
            error_str = str(e).lower()
            rate_limit_indicators = ['429', 'quota', 'rate limit', 'exceeded', 'resource_exhausted']

            if any(indicator in error_str for indicator in rate_limit_indicators):
                print(f"OrchestratorAgent: Gemini API rate limit 감지, fallback 시도: {e}")
                if fallback_model:
                    try:
                        result = await fallback_model.ainvoke(prompt)
                        print("OrchestratorAgent: fallback 성공")
                        return result
                    except Exception as fallback_error:
                        print(f"OrchestratorAgent: fallback도 실패: {fallback_error}")
                        raise fallback_error
                else:
                    print("OrchestratorAgent: fallback 모델이 초기화되지 않음")
                    raise e
            else:
                raise e

    def _inject_context_into_query(self, query: str, context: Dict[int, str]) -> str:
        """'[step-X의 결과]' 플레이스홀더를 실제 컨텍스트로 교체하는 헬퍼 함수"""
        match = re.search(r"\[step-(\d+)의 결과\]", query)
        if match:
            step_index = int(match.group(1))
            if step_index in context:
                print(f"  - {step_index}단계 컨텍스트 주입: '{context[step_index][:]}...'")
                # 플레이스홀더를 이전 단계의 요약 결과로 치환
                return query.replace(match.group(0), f"이전 단계 분석 결과: '{context[step_index]}'")
        return query

    async def generate_plan(self, state: StreamingAgentState) -> StreamingAgentState:
        """페르소나 관점과 의존성을 반영하여 단계별 실행 계획(Hybrid Model)을 수립합니다."""
        print(f"\n>> Orchestrator: 지능형 단계별 계획 수립 시작")
        query = state["original_query"]
        current_date_str = datetime.now().strftime("%Y년 %m월 %d일")

        # 페르소나 정보 추출
        persona_name = state.get("persona", "기본")
        persona_info = self.personas.get(persona_name, {})
        persona_description = persona_info.get("description", "일반적인 분석가")
        print(f"  - 계획 수립에 '{persona_name}' 페르소나 관점 적용")

        planning_prompt = f"""
당신은 **'{persona_name}'의 유능한 AI 수석 보좌관**이자 **실행 계획 설계 전문가**입니다.
당신의 임무는 사용자의 요청을 **있는 그대로** 분석하고, **'{persona_name}'의 전문성을 활용하여 가장 효율적인 데이터 수집 계획**을 수립하는 것입니다.

**### Strict Adherence Mandate (엄격한 준수 명령) ###**
**1. 절대 사용자 요청을 확장하거나 추측하지 마세요.** 사용자가 "A와 B를 알려줘"라고 했다면, 오직 A와 B에 대한 정보만 수집해야 합니다. 관련될 수 있는 C(예: 시장 규모, 소비자 선호도)를 묻지 않았다면 절대 계획에 포함하지 마세요.
**2. 페르소나는 '어떻게(How)' 데이터를 수집하고 분석할지에 대한 관점이지, '무엇을(What)' 수집할지를 결정하는 역할이 아닙니다.** 페르소나의 관심사를 이유로 사용자가 묻지 않은 새로운 주제를 추가해서는 안 됩니다.
**3. 최종 목표는 사용자의 질문에 대한 '직접적인 답변'을 찾는 것입니다.** 광범위한 배경 조사를 하는 것이 아닙니다.
**4. 논리적 계획 수립 (How to ask): 하위 질문들의 선후 관계를 분석하여, 의존성이 있는 작업은 순차적으로, 없는 작업은 병렬로 처리하는 최적의 실행 단계를 설계하세요.

**사용자 원본 요청**: "{query}"
**현재 날짜**: {current_date_str}

---
**## 보유 도구 명세서 및 선택 가이드**

**1. rdb_search (PostgreSQL) - 1순위 활용**
   - **데이터 종류**: 정형 데이터 (테이블 기반: 식자재 **영양성분**, 농·축·수산물 **시세/가격/거래량** 등 수치 데이터).
   - **사용 시점**: 영양성분, 현재가격, 시세변동, 가격비교, 순위/평균/합계 등 **정확한 수치 연산**이 필요할 때.
   - **특징**: 날짜·지역·품목 컬럼으로 **필터/집계** 최적화. 다중 조건(where)과 group by, order by를 통한 **통계/랭킹** 질의에 적합. (관계 그래프 탐색은 비권장)
   - **예시 질의 의도**: "사과 비타민C 함량", "지난달 제주 감귤 평균가", "전복 가격 추이", "영양성분 상위 TOP 10"

**2. vector_db_search (Elasticsearch) - 1순위 활용**
   - **데이터 종류**: 비정형 데이터 (뉴스기사, 논문, 보고서 전문).
   - **사용 시점**: 정책문서, 배경정보, 실무가이드 등 서술형 정보나 분석이 필요할 때.
   - **특징**: 의미기반 검색으로 질문의 맥락과 가장 관련성 높은 문서를 찾아줌.

**3. graph_db_search (Neo4j) - 1순위 활용**
   - **데이터 종류**: **관계형(그래프) 데이터**. 노드: 품목(농산물/수산물/축산물), **Origin(원산지: city/region)**, **Nutrient(영양소)**.
     관계: `(품목)-[:isFrom]->(Origin)`, `(품목)-[:hasNutrient]->(Nutrient)`. 수산물은 품목 노드에 `fishState`(활어/선어/냉동/건어) 속성 존재.
   - **사용 시점**: **품목 ↔ 원산지**, **품목 ↔ 영양소**처럼 **엔티티 간 연결**이 핵심일 때. 지역·상태(fishState) 조건을 얹은 **원산지/특산품 탐색**.
   - **특징**: 지식그래프 경로 탐색에 최적화. 키워드는 **품목명/지역명/영양소/수산물 상태(fishState)**로 간결히 표현하고, 질문은 **"A의 원산지", "A의 영양소", "지역 B의 특산품/원산지", "활어 A의 원산지"**처럼 **관계를 명시**할수록 정확도 상승.
   - **예시 질의 의도**: "사과의 원산지", "오렌지의 영양소", "제주도의 감귤 원산지", "활어 문어 원산지", "경상북도 사과 산지 연결"

**4. pubmed_search - 1순위 활용 (학술 연구 필요시)**
   - **데이터 종류**: 최신 학술 논문 (pubmed 프리프린트 논문).
   - **사용 시점**: 신제품 개발, 과학적 근거, 최신 연구 동향, 대체식품 연구, 지속가능성 연구가 필요할 때.
   - **특징**: **반드시 쿼리를 영어로 번역 후 검색 필수.** food science, biotechnology, alternative protein 등 영문 학술 용어로 검색. 예시: plant-based meat alternatives, alternative protein, functional food, sustainable food 등
   - **예시 질의 의도**: "Plant-based alternative meat development papers", "Latest research on fermentation technology", "Bioplastic packaging materials"

**5. web_search - 최신 정보 필수 시 우선 사용**
   - **데이터 종류**: 실시간 최신 정보, 시사 정보, 재해/재난 정보, 최근 뉴스.
   - **사용 조건**:
     * **필수 사용**: 2025년 특정 월/일, 최근, 현재, 기상이변, 집중폭우, 재해, 재난 등이 포함된 질문
     * **우선 사용**: 내부 DB에 없을 가능성이 높은 최신 사건/상황 정보
     * **보조 사용**: 내부 DB로 해결되지 않는 일반 지식
   - **사용 금지**: 일반적인 농축수산물 시세, 영양정보, 원산지 등은 내부 DB 우선 사용 후 보완적으로만 사용.

**도구 선택 우선순위:**
1. **⭐ 최신 정보/시사 (2025년 특정 시점, 재해, 기상이변, 뉴스)** → `web_search` **[최우선]**
2. **수치/통계 데이터 (식자재 영양성분, 농축수산물 시세)** → `rdb_search`
3. **관계/분류 정보 (품목-원산지, 품목-영양소, 지역-특산품, 수산물 상태별 원산지)** → `graph_db_search`
4. **분석/연구 문서 (시장분석, 소비자 조사)** → `vector_db_search`
5. **학술 논문/연구 (신제품 개발, 과학적 근거)** → `pubmed_search`

**각 도구별 적용 예시:**
- `rdb_search`: "식자재 영양성분", "농축수산물 시세", "가격 추이/비교", "영양성분 상위 TOP"
- `graph_db_search`: "사과의 원산지", "오렌지의 영양소", "제주-감귤 관계", "활어 문어 원산지", "지역별 특산품 연결"
- `vector_db_search`: "시장 분석 보고서", "소비자 행동 연구", "정책 문서"
- `pubmed_search`: "Plant-based alternative meat development papers", "Latest research on fermentation technology", "Bioplastic packaging materials"
- `web_search`: "2025년 최신 트렌드", "실시간 업계 동향", "2025년 7월 집중폭우 피해지역", "기상이변 농업 피해", "최근 재해 발생 지역", "현재 농산물 공급 상황"

---
**## 계획 수립을 위한 단계별 사고 프로세스 (반드시 준수할 것)**

**1단계: 사용자 요청 분해 (Decomposition)**
- 사용자의 원본 요청을 의미적, 논리적 단위로 나눕니다. 각 단위는 사용자가 명시적으로 요구한 하나의 정보 조각이어야 합니다.
- 예: "대체식품의 유형을 원료에 따라 구분하고, 미생물 발효 식품의 연구개발 현황을 분석해줘."
  - 단위 1: "대체식품의 유형을 원료에 따라 구분하여 정리"
  - 단위 2: "미생물 발효 식품의 연구개발 현황 분석 및 정리"

**2단계: 각 단위에 대한 하위 질문 생성**
- 1단계에서 분해된 각 단위를 해결하기 위해 필요한 구체적인 질문들을 생성합니다.
- 이 질문들은 페르소나의 전문성을 반영해야 합니다. (예: '제품 개발 연구원'은 기술, 성분, 논문에 초점을 맞춘 질문 생성)
- 예 (제품 개발 연구원 관점):
  - (단위 1 관련): "식물성, 곤충, 배양육 등 원료 기반 대체식품 유형별 기술적 정의 및 분류", "주요 원료별 대체식품의 핵심 성분 및 특성"
  - (단위 2 관련): "미생물 발효 대체식품 관련 최신 연구 논문 및 특허 동향", "미생물 발효 기술을 활용한 상용화 제품 사례 및 적용 기술"
- 각각 완결된 형태의 구체적인 질문으로 분해합니다.
- 생성된 모든 하위 질문은 원본 요청의 핵심 맥락(예: '대한민국', '건강기능식품')을 반드시 포함해야 합니다.

**3단계: 질문 간 의존성 분석 (가장 중요한 단계)**
- 분해된 질문들 간의 선후 관계를 분석합니다.
- **"어떤 질문이 다른 질문의 결과를 반드시 알아야만 제대로 수행될 수 있는가?"**를 판단합니다.
- 예시: `A분야의 시장 규모`를 알아야 `A분야의 주요 경쟁사`를 조사할 수 있으므로, 두 질문은 의존성이 있습니다. 반면, `A분야의 시장 규모`와 `B분야의 시장 규모` 조사는 서로 독립적입니다.

**4단계: 실행 단계 그룹화 (Grouping)**
- **Step 1**: 서로 의존성이 없는, 가장 먼저 수행되어야 할 병렬 실행 가능한 질문들을 배치합니다.
- **Step 2 이후**: 이전 단계의 결과(`[step-X의 결과]` 플레이스홀더 사용)를 입력으로 사용하는 의존성 있는 질문들을 배치합니다. (예: 1단계에서 찾은 '성장 분야'의 경쟁사 조사)

**5단계: 각 질문에 대한 최적 도구 선택 전략**
- '보유 도구 명세서'를 참고하여 각 하위 질문에 가장 적합한 도구를 **단 하나만** 신중하게 선택합니다.
- **중요**: 질문의 복잡성을 분석하여 **필요한 도구만 선택**합니다:
  * **단순 질문** → 1개 도구로 충분 (예: "사과 영양성분" → `rdb_search`)
  * **복합 질문** → 여러 도구 조합 필요 (예: "최신 재해 + 농업 분석" → 여러 단계)
    - **"성분", "영양", "시세", "가격"** 포함 → `rdb_search`
    - **"원산지", "관계", "제조사", "특산품", "fishState(활어/선어/냉동/건어)"** 포함 → `graph_db_search`
    - **"분석", "연구", "조사", "보고서", "동향"** 포함 → `vector_db_search`
    - **"신제품 개발", "과학적 근거", "논문", "학술", "대체식품", "지속가능성", "발효 기술"** 포함 → `pubmed_search`
    - **"최신 트렌드", "실시간 정보", "2025년", "최근", "현재", "기상이변", "집중폭우", "홍수", "태풍", "재해", "재난", "피해", "뉴스", "사건", "발생"** 등 최신성 강조 또는 시사 정보 관련 시 → `web_search`

**도구 선택 예시**:
- **단순 케이스**: "사과의 영양성분" → `rdb_search` 1개만
- **중간 케이스**: "2025년 식품 트렌드" → `web_search` 1개만
- **복합 케이스**: "최신 재해 피해지역 농업 현황" → `web_search` + `vector_db_search` + `graph_db_search` 조합
- **고도 복합**: "신제품 개발 전략" → `web_search` + `pubmed_search` + `vector_db_search` + `rdb_search` 조합

**6단계: 최종 JSON 형식화**
- 위에서 결정된 모든 내용을 아래 '최종 출력 포맷'에 맞춰 JSON으로 작성합니다.
- **중요**: `sub_questions` 키는 반드시 `execution_steps` 배열의 각 요소 안에만 존재해야 합니다.

---
**## 계획 수립 예시**

**[예시 1: 단순 조회 - 단일 Step, 단일 작업]**
**요청**: "사과의 영양성분과 칼로리 정보를 알려줘."
**생성된 계획(JSON)**:
{{
    "title": "사과 영양성분 및 칼로리 정보",
    "reasoning": "사용자의 요청은 '사과의 영양성분 및 칼로리'라는 단일 정보 조각으로 구성됩니다. 이는 RDB에서 직접 조회가 가능하므로, rdb_search 도구를 사용한 단일 단계 계획을 수립합니다.",
    "execution_steps": [
        {{
            "step": 1,
            "reasoning": "영양성분과 칼로리는 RDB에 정형화된 데이터이므로 rdb_search만으로 해결 가능합니다.",
            "sub_questions": [
                {{"question": "사과의 상세 영양성분 정보 및 칼로리", "tool": "rdb_search"}}
            ]
        }}
    ]
}}

**[예시 2: 병렬 조회 - 단일 Step, 다중 작업]**
**요청**: "대체식품의 유형을 원료에 따라 구분하여 정리하고 이중에서 미생물 발효 식품의 연구개발 현황을 분석하고 정리해줘."
**페르소나**: "제품 개발 연구원"
**생성된 계획(JSON)**:
{{
  "title": "원료별 대체식품 유형 및 미생물 발효 식품 R&D 현황 분석",
  "reasoning": "사용자 요청을 '원료별 유형 분류'와 '미생물 발효 식품 R&D 현황' 두 가지 독립적인 축으로 분해했습니다. 두 주제는 의존성이 없으므로 단일 단계에서 병렬로 정보를 수집하는 것이 가장 효율적입니다. '제품 개발 연구원'의 관점에 맞춰 기술 및 연구 자료 수집에 집중합니다.",
  "execution_steps": [
    {{
      "step": 1,
      "reasoning": "대체식품의 기술적 분류와 미생물 발효 식품의 연구 동향에 대한 기반 정보를 병렬로 수집합니다. 시장 동향 등 사용자가 묻지 않은 내용은 의도적으로 제외했습니다.",
      "sub_questions": [
        {{
          "question": "원료(식물, 곤충, 배양육, 균류 등)에 따른 대체식품의 기술적 유형 분류 및 정의",
          "tool": "vector_db_search"
        }},
        {{
          "question": "microbial fermentation for alternative protein or food ingredients latest research papers",
          "tool": "pubmed_search"
        }},
        {{
          "question": "국내외 미생물 발효 기술 기반 대체식품 연구 개발 프로젝트 또는 상용화 사례",
          "tool": "vector_db_search"
        }}
      ]
    }}
  ]
}}

**[예시 3: 순차(의존성) 조회 - 다중 Step]**
**요청**: "2025년 7월과 8월의 집중폭우 피해지역에서 생산되는 주요 식재료들 목록과 생산지를 표로 정리해줘"
**생성된 계획(JSON)**:
{{
    "title": "2025년 여름 집중폭우 피해지역의 주요 식재료 및 생산지 분석",
    "reasoning": "이 요청은 여러 정보가 논리적으로 연결되어야 해결 가능합니다. 먼저 '피해 지역'을 특정하고(Step 1), 그 지역의 '주요 식재료와 생산지'를 찾아(Step 2) 최종적으로 종합 분석(Step 3)하는 순차적인 계획이 필요합니다.",
    "execution_steps": [
        {{
            "step": 1,
            "reasoning": "가장 먼저 최신 재해 정보를 통해 '집중폭우 피해 지역'을 명확히 특정해야 합니다.",
            "sub_questions": [
                {{"question": "2025년 7월 8월 대한민국 집중호우 피해 심각 지역 목록", "tool": "web_search"}}
            ]
        }},
        {{
            "step": 2,
            "reasoning": "Step 1에서 식별된 피해 지역을 바탕으로 해당 지역에서 주로 생산되는 식재료 정보를 수집합니다.",
            "sub_questions": [
                {{"question": "[step-1의 결과]로 확인된 피해 지역들 각각의 주요 생산 농축수산물(특산품) 목록", "tool": "graph_db_search"}},
                {{"question": "[step-1의 결과]로 확인된 피해 지역들의 농업 피해 현황 분석 보고서", "tool": "vector_db_search"}}
            ]
        }},
        {{
            "step": 3,
            "reasoning": "Step 2까지 수집된 정보를 종합하여, 사용자가 최종적으로 요청한 '피해 지역별 주요 식재료 및 생산지' 목록을 완성합니다.",
            "sub_questions": [
                {{"question": "[step-2의 결과]를 바탕으로, 집중호우 피해 지역과 해당 지역의 주요 식재료 및 생산지를 연결하여 표 형태로 요약", "tool": "vector_db_search"}}
            ]
        }}
    ]
}}

---
**## 최종 출력 포맷**

**중요 규칙**:
- **질문 복잡성에 따라 적절한 도구 개수 선택**: 단순하면 1개, 복합적이면 필요한 만큼만
- **최신 정보** 포함 시 → **web_search 포함**, 추가로 필요한 분석/통계 도구만 보완
- **일반 정보** → 내부 DB(rdb, vector, graph, pubmed) 중 가장 적합한 것 선택
- **과도한 도구 사용 금지**: 불필요한 중복 검색으로 성능 저하 방지
- **pubmed_search 주의사항**: pubmed를 사용하는 경우, 영어로 쿼리를 번역한 후 question에 넣어야 함
- 반드시 아래 JSON 형식으로만 응답해야 합니다.

{{
    "title": "분석 보고서의 전체 제목",
    "reasoning": "이러한 단계별 계획을 수립한 핵심적인 이유.",
    "execution_steps": [
        {{
            "step": 1,
            "reasoning": "1단계 계획에 대한 설명. 병렬 실행될 작업들을 기술.",
            "sub_questions": [
                {{
                    "question": "1단계에서 병렬로 실행할 첫 번째 하위 질문",
                    "tool": "선택된 도구 이름"
                }},
                {{
                    "question": "1단계에서 병렬로 실행할 두 번째 하위 질문",
                    "tool": "선택된 도구 이름"
                }}
            ]
        }},
        {{
            "step": 2,
            "reasoning": "2단계 계획에 대한 설명. 1단계 결과에 의존함을 명시.",
            "sub_questions": [
                {{
                    "question": "2단계에서 실행할 하위 질문 (필요시 '[step-1의 결과]' 포함)",
                    "tool": "선택된 도구 이름"
                }}
            ]
        }}
    ]
}}
"""

        try:
            response = await self.llm.ainvoke(planning_prompt)
            content = response.content.strip()

            json_match = re.search(r'```json\s*(\{.*?\})\s*```', content, re.DOTALL)
            if not json_match:
                json_match = re.search(r'\{.*\}', content, re.DOTALL)

            if json_match:
                json_str = json_match.group(1) if '```' in json_match.group(0) else json_match.group(0)
                plan = json.loads(json_str)
            else:
                raise ValueError("Valid JSON plan not found in response")

            print(f"  - 지능형 단계별 계획 생성 완료: {plan.get('title', '제목 없음')}")
            print("  - 계획 JSON:")
            print(json.dumps(plan, ensure_ascii=False, indent=2))
            state["plan"] = plan

        except Exception as e:
            print(f"  - 지능형 계획 생성 실패, 단일 단계로 직접 검색 실행: {e}")
            state["plan"] = {
                "title": f"{query} 분석",
                "reasoning": "지능형 단계별 계획 수립에 실패하여, 사용자 원본 쿼리로 직접 검색을 실행합니다.",
                "execution_steps": [{
                    "step": 1,
                    "reasoning": "Fallback 실행",
                    "sub_questions": [{"question": query, "tool": "vector_db_search"}]
                }]
            }

        return state



    # ⭐ 핵심 수정: 요약된 내용이 아닌 전체 원본 내용을 LLM에게 제공
    async def _select_relevant_data_for_step(self, step_info: Dict, current_collected_data: List[SearchResult], query: str) -> List[int]:
        """현재 단계에서 수집된 데이터 중 관련 있는 것만 LLM이 선택 (전체 내용 기반)"""

        step_title = f"Step {step_info['step']}"
        step_reasoning = step_info.get('reasoning', '')
        sub_questions = step_info.get('sub_questions', [])

        # ⭐ 핵심 개선: 전체 원본 내용을 LLM에게 제공 (요약 없이)
        full_data_context = ""
        for i, res in enumerate(current_collected_data):
            source = getattr(res, 'source', 'Unknown')
            title = getattr(res, 'title', 'No Title')
            content = getattr(res, 'content', '')  # ⭐ 전체 내용 (요약 안함)

            full_data_context += f"""
    --- 데이터 인덱스 [{i}] ---
    출처: {source}
    제목: {title}
    전체 내용: {content}

    """

        # 현재 단계의 질문들
        questions_summary = ""
        for sq in sub_questions:
            questions_summary += f"- {sq.get('question', '')} ({sq.get('tool', '')})\n"

        # ⭐ 컨텍스트 길이 관리 (중요한 부분만 잘라내기)
        # 너무 길면 각 데이터당 최대 1000자로 제한
        if len(full_data_context) > 15000:
            print(f"  - 컨텍스트가 너무 긺 ({len(full_data_context)}자), 데이터별 1000자로 제한")

            truncated_context = ""
            for i, res in enumerate(current_collected_data):
                source = getattr(res, 'source', 'Unknown')
                title = getattr(res, 'title', 'No Title')
                content = getattr(res, 'content', '')[:1000]  # 1000자로 제한

                truncated_context += f"""
    --- 데이터 인덱스 [{i}] ---
    출처: {source}
    제목: {title}
    내용: {content}{"..." if len(getattr(res, 'content', '')) > 1000 else ""}

    """
            full_data_context = truncated_context

        selection_prompt = f"""
    당신은 데이터 분석 전문가입니다.
    수집된 데이터 중에서 **차트 생성과 보고서 작성에 필요한 데이터**를 효율적으로 선택해주세요.

    **전체 사용자 질문**: "{query}"

    **현재 단계 정보**:
    - {step_title}: {step_reasoning}
    - 실행한 질문들:
    {questions_summary}

    **수집된 전체 데이터** (전체 내용 포함):
    {full_data_context}

    **선택 기준**:
    1. **차트 생성용 수치/통계 데이터 최우선 선택**:
       - 매출액, 시장규모, 점유율, 생산량, 가격 등 수치 데이터
       - %, 억원, 조원, 천톤 등 단위가 포함된 데이터
       - 표, 통계, 현황표, 순위, 비교, 분석 데이터
       - 지역별/품목별/시기별 비교 데이터
       - 연도별, 월별 시계열 데이터
    2. **사용자 질문과 직접적으로 관련된 데이터**
    3. **배경 정보 및 컨텍스트 데이터** (중요한 것만)
    4. **중복 제거**: 완전히 동일한 내용은 하나만 선택

    **제외 기준**:
    - 질문과 전혀 관련 없는 주제
    - 완전히 중복되는 내용 (유사하지만 다른 관점이면 포함)
    - 광고성 내용 (단, 시장 데이터 포함시 선택)
    - 일반적인 설명만 있고 구체적 데이터가 없는 내용

    **목표**: 차트 생성에 필요한 충분한 데이터 확보 (품질 중심 선택)

    다음 JSON 형식으로만 응답하세요:
    {{
        "selected_indexes": [선택된 인덱스들],
        "reasoning": "선택된 각 데이터가 사용자 질문과 차트 생성에 어떻게 기여하는지 설명",
        "rejected_reason": "제외된 데이터들의 제외 이유"
    }}
    """

        try:
            response = await self._invoke_with_fallback(
                selection_prompt,
                self.llm,
                self.llm_openai_mini
            )

            # JSON 파싱
            result = json.loads(re.search(r'\{.*\}', response.content, re.DOTALL).group())
            selected_indexes = result.get("selected_indexes", [])
            reasoning = result.get("reasoning", "")
            rejected_reason = result.get("rejected_reason", "")

            # 인덱스 유효성 검증
            max_index = len(current_collected_data) - 1
            valid_indexes = [idx for idx in selected_indexes if isinstance(idx, int) and 0 <= idx <= max_index]

            # ⭐ 핵심 수정: 차트 생성용 최소 데이터 확보
            total_available = len(current_collected_data)
            min_selection = max(3, min(6, total_available))  # 최소 3개, 최대 6개 (전체 개수 고려)

            if len(valid_indexes) < min_selection:
                print(f"  - ⚠️ 차트 생성을 위해 최소 {min_selection}개 데이터가 필요하지만 {len(valid_indexes)}개만 선택됨")
                # 선택되지 않은 인덱스들 중에서 추가 선택 (첫 번째부터 순서대로)
                unselected = [i for i in range(total_available) if i not in valid_indexes]
                additional_needed = min_selection - len(valid_indexes)
                additional_selected = unselected[:additional_needed]
                valid_indexes.extend(additional_selected)
                valid_indexes = sorted(valid_indexes)
                print(f"  - 🔧 추가 선택된 인덱스: {additional_selected}")

            print(f"  - LLM 데이터 선택 완료:")
            print(f"    선택된 인덱스: {valid_indexes} (총 {len(valid_indexes)}/{total_available}개)")
            print(f"    선택 이유: {reasoning}")
            if rejected_reason:
                print(f"    제외 이유: {rejected_reason}")

            # 선택된 데이터 미리보기
            print(f"  - 선택된 데이터 목록:")
            for idx in valid_indexes:
                data_item = current_collected_data[idx]
                title = getattr(data_item, 'title', 'No Title')[:60]
                source = getattr(data_item, 'source', 'Unknown')
                print(f"    [{idx:2d}] {source:10s} | {title}")

            return valid_indexes

        except Exception as e:
            print(f"  - LLM 데이터 선택 실패: {e}")
            # fallback: 현재 단계에서 수집된 모든 데이터 유지
            return list(range(len(current_collected_data)))



    async def execute_report_workflow(self, state: StreamingAgentState) -> AsyncGenerator[str, None]:
        """단계별 계획에 따라 순차적, 병렬적으로 데이터 수집 및 보고서 생성"""
        query = state["original_query"]

        # 메모리 컨텍스트 추출 및 요약 생성
        conversation_history = state.get("metadata", {}).get("conversation_history", [])
        conversation_id = state.get("conversation_id", "unknown")
        memory_summary = self._generate_memory_summary_for_report(conversation_history, query)

        if memory_summary:
            print(f"🧠 채팅방 {conversation_id}: 보고서에 메모리 요약 포함 ({len(conversation_history)}개 메시지)")
        else:
            print(f"🧠 채팅방 {conversation_id}: 메모리 없음 (새 대화 또는 연속성 없음)")

        # --- 추가: 페르소나 확인 및 상태 알림 ---
        # 사용자가 선택한 페르소나가 state에 이미 포함되어 있다고 가정합니다.
        # 예: state['persona'] = '구매 담당자'
        selected_persona = state.get("persona")
        if not selected_persona or selected_persona not in self.personas:
            print(f"경고: 유효하지 않거나 지정되지 않은 페르소나 ('{selected_persona}'). '기본'으로 설정합니다.")
            selected_persona = "기본"
            state["persona"] = selected_persona

        yield self._create_status_event("PLANNING", "PERSONA_CONFIRMED", f"'{selected_persona}' 페르소나로 보고서 생성을 시작합니다.")

        # 차트 카운터 초기화
        state['chart_counter'] = 0

        # 누적 context 초기화
        accumulated_context = {
            "generated_sections": [],  # 생성된 섹션 내용들
            "chart_data": [],  # 생성된 차트 데이터들
            "insights": [],  # 각 섹션의 주요 인사이트
            "persona": selected_persona  # 선택된 페르소나
        }
        state['accumulated_context'] = accumulated_context

        # 1. 단계별 계획 수립
        yield self._create_status_event("PLANNING", "GENERATE_PLAN_START", "분석 계획 수립 중...")
        state_with_plan = await self.generate_plan(state)
        plan = state_with_plan.get("plan", {})

        yield {"type": "plan", "data": {"plan": plan}}

        yield self._create_status_event("PLANNING", "GENERATE_PLAN_COMPLETE", "분석 계획 수립 완료.", details={
            "plan_title": plan.get('title'),
            "plan_reasoning": plan.get('reasoning'),
            "step_count": len(plan.get("execution_steps", []))
        })

        await asyncio.sleep(0.01)

        # 2. 단계별 데이터 수집 실행
        execution_steps = plan.get("execution_steps", [])
        final_collected_data: List[SearchResult] = []
        step_results_context: Dict[int, str] = {}
        cumulative_selected_indexes: List[int] = []

        # 중복 제거를 위한 글로벌 디듀플리케이터 초기화
        deduplicator = GlobalDeduplicator()

        for i, step_info in enumerate(execution_steps):
            current_step_index = step_info["step"]
            yield self._create_status_event("GATHERING", "STEP_START", f"데이터 수집 ({i + 1}/{len(execution_steps)}) 시작.")

            tasks_for_this_step = []
            for sq in step_info.get("sub_questions", []):
                injected_query = self._inject_context_into_query(sq["question"], step_results_context)
                tasks_for_this_step.append({"tool": sq["tool"], "inputs": {"query": injected_query}})
            if not tasks_for_this_step:
                continue

            # step_collected_data를 SearchResult 객체 리스트로 초기화합니다.
            step_collected_data: List[SearchResult] = []

            async for event in self.data_gatherer.execute_parallel_streaming(tasks_for_this_step, state=state):
                if event["type"] == "search_results":
                    yield event
                elif event["type"] == "collection_complete":
                    # worker로부터 받은 dict 리스트를 다시 SearchResult 객체 리스트로 변환합니다.
                    collected_dicts = event["data"]["collected_data"]
                    step_collected_data = [SearchResult(**data_dict) for data_dict in collected_dicts]

            # 수집된 데이터에 대해 중복 제거 적용 (임시 비활성화)
            try:
                unique_step_data = self._apply_deduplication(step_collected_data, deduplicator)
            except AttributeError:
                print("⚠️ 중복 제거 메서드 로딩 중... 임시로 원본 데이터 사용")
                unique_step_data = step_collected_data

            # 이제 unique_step_data는 List[SearchResult] 타입이므로 .content 접근이 가능합니다.
            summary_of_step = " ".join([res.content for res in unique_step_data])
            step_results_context[current_step_index] = summary_of_step[:2000]
            final_collected_data.extend(unique_step_data)

            print(f">> {current_step_index}단계 완료: {len(step_collected_data)}개 수집 → {len(unique_step_data)}개 유지 (총 {len(final_collected_data)}개)")

            if len(final_collected_data) > 0:
                yield self._create_status_event("PROCESSING", "FILTER_DATA_START", "수집 데이터 선별 중...")

                # reasoning을 반환하지 않으므로 selected_indexes만 받습니다.
                selected_indexes = await self._select_relevant_data_for_step(
                    step_info, final_collected_data, state["original_query"]
                )

                yield self._create_status_event("PROCESSING", "FILTER_DATA_COMPLETE", f"핵심 데이터 {len(selected_indexes)}개 선별 완료.", details={
                    "selected_indices": selected_indexes
                })
                cumulative_selected_indexes = sorted(list(set(cumulative_selected_indexes + selected_indexes)))

        # >> 핵심 수정: 전체 데이터 딕셔너리를 프론트로 먼저 전송
        print(f"\n>> 전체 데이터 딕셔너리 생성 및 전송")

        # 전체 데이터를 인덱스:데이터 형태의 딕셔너리로 변환
        full_data_dict = {}
        print(f"\n🔍 === FULL_DATA_DICT 생성 디버깅 ===")
        print(f"final_collected_data 총 개수: {len(final_collected_data)}")

        for idx, data in enumerate(final_collected_data):
            full_data_dict[idx] = {
                "title": getattr(data, 'title', 'No Title'),
                "content": getattr(data, 'content', ''),
                "source": getattr(data, 'source', 'Unknown'),
                "url": getattr(data, 'url', ''),
                "source_url": getattr(data, 'source_url', ''),
                "score": getattr(data, 'score', 0.0),
                "document_type": getattr(data, 'document_type', 'unknown')
            }

            # 첫 5개와 마지막 5개만 상세 로그
            if idx < 5 or idx >= len(final_collected_data) - 5:
                print(f"  [{idx}]: 제목='{getattr(data, 'title', 'No Title')[:50]}...' 출처='{getattr(data, 'source', 'Unknown')}'")

        print(f"전체 데이터 딕셔너리 키들: {list(full_data_dict.keys())}")
        print(f"전체 데이터 딕셔너리 크기: {len(full_data_dict)}개")

        # 전체 데이터 딕셔너리를 프론트로 전송
        print(f"\n🚀 === 프론트엔드로 FULL_DATA_DICT 전송 ===")
        print(f"전송할 데이터 구조:")
        print(f"  type: 'full_data_dict'")
        print(f"  data.data_dict 키들: {list(full_data_dict.keys())}")
        print(f"  data.data_dict 크기: {len(full_data_dict)}")

        # 샘플 데이터 확인 (첫 번째 것만)
        if full_data_dict:
            first_key = list(full_data_dict.keys())[0]
            first_item = full_data_dict[first_key]
            print(f"  샘플 [{first_key}]: 제목='{first_item['title'][:30]}...' 출처='{first_item['source']}'")

        yield {"type": "full_data_dict", "data": {"data_dict": full_data_dict}}

        # 3. 섹션별 데이터 상태 분석 및 보고서 구조 설계
        # 중복된 full_data_dict 생성 및 전송 제거 (이미 위에서 처리됨)

        yield self._create_status_event("PROCESSING", "DESIGN_STRUCTURE_START", "보고서 구조 설계 중...")

        design = None
        async for result in self.processor.process("design_report_structure", final_collected_data, cumulative_selected_indexes, query, state=state):
            if result.get("type") == "result":
                design = result.get("data")
                break

        if not design or "structure" not in design or not design["structure"]:
            yield {"type": "error", "data": {"message": "보고서 구조 설계에 실패했습니다."}}
            return

        # ⭐ 핵심 추가: 데이터 부족 섹션 확인 및 추가 검색
        insufficient_sections = []
        for i, section in enumerate(design.get("structure", [])):
            if not section.get("is_sufficient", True):
                insufficient_sections.append({"original_index": i, "section_info": section})

        if insufficient_sections:
            print(f"🔍 데이터 부족 섹션 {len(insufficient_sections)}개 발견, 추가 데이터 수집 실행")
            yield self._create_status_event("GATHERING", "ADDITIONAL_SEARCH_START", f"{len(insufficient_sections)}개 항목에 대한 데이터 보강을 시작합니다.")

            additional_tasks = []
            for item in insufficient_sections:
                section = item["section_info"]
                feedback = section.get("feedback_for_gatherer", {})
                if isinstance(feedback, dict) and feedback:
                    tool = feedback.get("tool", "vector_db_search")
                    query_to_run = feedback.get("query", f"{section.get('section_title', '')} 상세 데이터")
                    additional_tasks.append({"tool": tool, "inputs": {"query": query_to_run}})

            additional_data_collected_objects: List[SearchResult] = []
            if additional_tasks:
                async for event in self.data_gatherer.execute_parallel_streaming(additional_tasks, state=state):
                    if event["type"] == "search_results":
                        yield event
                    elif event["type"] == "collection_complete":
                        additional_data_dicts = event["data"]["collected_data"]
                        for data_dict in additional_data_dicts:
                            additional_data_collected_objects.append(SearchResult(**data_dict))

            # if 문의 조건 변수를 additional_data_collected_objects로 변경합니다.
            if additional_data_collected_objects:
                print(f"✅ 총 {len(additional_data_collected_objects)}개 추가 데이터 수집 완료. 보고서 구조를 업데이트합니다.")
                yield self._create_status_event("PROCESSING", "DATA_ENHANCED", f"{len(additional_data_collected_objects)}개의 추가 데이터로 보고서 구조를 보강합니다.")

                original_data_count = len(final_collected_data)
                new_data_indexes = list(range(original_data_count, original_data_count + len(additional_data_collected_objects)))
                # final_collected_data에 추가하는 변수도 변경합니다.
                final_collected_data.extend(additional_data_collected_objects)

                for item in insufficient_sections:
                    section_index = item["original_index"]
                    section_info = item["section_info"]
                    original_indexes = section_info.get("use_contents", [])

                    updated_use_contents = await self._update_use_contents_after_recollection(
                        section_info, final_collected_data, original_indexes, new_data_indexes, query
                    )

                    design["structure"][section_index]["use_contents"] = updated_use_contents
                    design["structure"][section_index]["is_sufficient"] = True
                    design["structure"][section_index]["feedback_for_gatherer"] = ""

                print(f"🔄 데이터 보강 및 구조 업데이트 완료. 최종 데이터 수: {len(final_collected_data)}개")

            else:
                print(f"⚠️ 추가 데이터 수집 실패, 기존 데이터로 진행")

        # 5. 모든 데이터 수집/보강이 끝난 후, 최종 데이터 목록으로 full_data_dict 생성 및 전송
        print(f"\n>> 최종 데이터 목록으로 딕셔너리 생성 및 전송 (총 {len(final_collected_data)}개)")
        full_data_dict = {}
        for idx, data in enumerate(final_collected_data):
            # SearchResult 객체를 JSON으로 변환 가능한 dict로 변환
            full_data_dict[idx] = data.model_dump()

        yield {"type": "full_data_dict", "data": {"data_dict": full_data_dict}}

        section_titles = [s.get('section_title', '제목 없음') for s in design.get('structure', [])]
        yield self._create_status_event("PROCESSING", "DESIGN_STRUCTURE_COMPLETE", "보고서 구조 설계 완료.", details={
            "report_title": design.get("title"),
            "section_titles": section_titles
        })

        # 보고서 제목과 메모리 요약을 가장 먼저 스트리밍
        report_start = f"# {design.get('title', query)}\n\n"

        # 메모리 요약이 있으면 포함
        if memory_summary:
            report_start += memory_summary

        report_start += "---\n\n"

        yield {"type": "content", "data": {"chunk": report_start}}

        # 4. 전체 보고서 구조 컨텍스트 생성
        # 각 섹션 생성 Agent가 전체 그림을 인지하도록 컨텍스트를 만들어 전달합니다.
        awareness_context = "아래는 전체 보고서의 목차입니다. 당신은 이 중 하나의 섹션 작성을 담당합니다.\n\n"

        # 메모리 컨텍스트 추가
        if conversation_history:
            memory_context = self._build_memory_context(conversation_history)
            if memory_context:
                awareness_context += memory_context + "\n"

        structure = design.get("structure", [])
        for i, sec in enumerate(structure):
            awareness_context += f"- **섹션 {i+1}. {sec.get('section_title', '')}**: {sec.get('description', '')}\n"

        # 5. 각 섹션의 결과를 담을 Queue 리스트와 병렬 실행할 Task 리스트 생성
        section_queues = [asyncio.Queue() for _ in structure]
        producer_tasks = []

        # 백그라운드에서 각 섹션 내용을 생성하고 Queue에 넣는 코루틴
        async def _produce_section_content(section_index: int):
            section_info = structure[section_index]
            q = section_queues[section_index]

            use_contents = section_info.get("use_contents", [])

            try:
                # generate_section_streaming을 호출하여 비동기적으로 청크를 받음
                async for chunk in self.processor.generate_section_streaming(
                    section_info, full_data_dict, query, use_contents,
                    awareness_context=awareness_context,
                    state=state
                ):
                    await q.put(chunk)  # 받은 청크를 큐에 넣음
            except Exception as e:
                # 오류 발생 시 에러 메시지를 큐에 넣음
                error_message = f"*'{section_info.get('section_title', '')}' 섹션 생성 중 오류가 발생했습니다: {str(e)}*\n\n"
                await q.put(error_message)
                print(f">> 섹션 생성(Producer) 오류: {error_message}")
            finally:
                # 스트림이 끝나면 None을 넣어 종료를 알림
                await q.put(None)

        # 모든 섹션에 대한 Producer Task를 생성하고 실행 목록에 추가
        for i in range(len(structure)):
            task = asyncio.create_task(_produce_section_content(i))
            producer_tasks.append(task)

        # 6. 순차적으로 Queue에서 결과를 꺼내 스트리밍 (Consumer)
        for i, section in enumerate(structure):
            section_title = section.get('section_title', f'섹션 {i+1}')
            use_contents = section.get("use_contents", [])

            yield self._create_status_event("GENERATING", "GENERATE_SECTION_START", f"'{section_title}' 섹션 생성 중...", details={
                "section_index": i, "section_title": section_title, "using_indices": use_contents
            })

            buffer = ""
            # ✅ section_full_content 변수 초기화 추가
            section_full_content = ""
            section_data_list = [final_collected_data[idx] for idx in use_contents if 0 <= idx < len(final_collected_data)]
             # ✅ section_content_generated 변수 추가 (생성 실패 여부 확인용)
            section_content_generated = False

            # 해당 섹션의 Queue에서 결과가 나올 때까지 대기
            while True:
                chunk = await section_queues[i].get()

                # None을 받으면 해당 섹션 스트리밍이 끝난 것
                if chunk is None:
                    break

                # ✅ 청크를 받았다면 내용이 생성된 것으로 간주
                section_content_generated = True
                buffer += chunk
                # ✅ 전체 섹션 내용도 별도로 누적
                section_full_content += chunk

                # 차트 생성 마커가 있는지 확인
                if "[GENERATE_CHART]" in buffer:
                    parts = buffer.split("[GENERATE_CHART]", 1)

                    if parts[0]:
                        yield {"type": "content", "data": {"chunk": parts[0]}}

                    buffer = parts[1]

                    yield self._create_status_event("GENERATING", "GENERATE_CHART_START", f"'{section_title}' 차트 생성 중...")

                    # 차트 생성 과정의 상태 메시지를 위한 콜백
                    async def chart_yield_callback(event_data):
                        print(f"차트 생성 상태: {event_data}")
                        return event_data

                    # 이전까지 생성된 context를 차트 생성에 전달
                    chart_context = {
                        "previous_sections": accumulated_context["generated_sections"],
                        "previous_charts": accumulated_context["chart_data"],
                        "current_section_content": buffer
                    }
                    state['chart_context'] = chart_context

                    chart_data = None
                    async for result in self.processor.process("create_chart_data", section_data_list, section_title, buffer, "", chart_yield_callback, state=state):
                        if result.get("type") == "chart":
                            chart_data = result.get("data")
                            accumulated_context["chart_data"].append({
                                "section": section_title,
                                "chart": chart_data
                            })

                            # 차트 생성 검증 로그 기록
                            await self._log_chart_verification(query, section_title, section_data_list, chart_data, state)
                            break

                    if chart_data and "error" not in chart_data:
                        current_chart_index = state.get('chart_counter', 0)
                        chart_placeholder = f"\n\n[CHART-PLACEHOLDER-{current_chart_index}]\n\n"
                        yield {"type": "content", "data": {"chunk": chart_placeholder}}
                        yield {"type": "chart", "data": chart_data}
                        state['chart_counter'] = current_chart_index + 1
                    else:
                        print(f"   차트 생성 실패: {chart_data}")
                        yield self._create_status_event("GENERATING", "GENERATE_CHART_FAILURE", f"'{section_title}' 차트 생성이 완료되지 못했습니다.")
                        yield {"type": "content", "data": {"chunk": "\n\n*[데이터 부족으로 차트 표시가 제한됩니다]*\n\n"}}

                else:
                    # 텍스트 스트리밍을 위한 버퍼 관리
                    potential_chart_marker = "[GENERATE_CHART]"
                    # 버퍼 끝에 마커 일부가 걸쳐있는지 확인
                    has_partial_marker = any(potential_chart_marker.startswith(buffer[-j:]) for j in range(1, min(len(buffer) + 1, len(potential_chart_marker) + 1)))

                    should_flush = (
                        not has_partial_marker and (
                            len(buffer) >= 120 or
                            buffer.endswith(('.', '!', '?', '\n', '다.', '요.', '니다.', '습니다.', '됩니다.', '있습니다.')) or
                            '\n\n' in buffer
                        )
                    )

                    if should_flush:
                        yield {"type": "content", "data": {"chunk": buffer}}
                        buffer = ""

            # while 루프 종료 후 남은 버퍼 처리
            if buffer.strip():
                yield {"type": "content", "data": {"chunk": buffer}}

            # 생성된 섹션 내용을 누적 context에 추가
            if section_full_content:
                accumulated_context["generated_sections"].append({
                    "title": section_title,
                    "content": section_full_content,
                    "data_indices": use_contents
                })
                # 주요 인사이트 추출
                first_paragraph = section_full_content.split("\n\n")[0] if "\n\n" in section_full_content else section_full_content[:200]
                accumulated_context["insights"].append({
                    "section": section_title,
                    "insight": first_paragraph
                })

                # 섹션 생성 검증 로그 기록
                await self._log_section_verification(query, section_title, section_data_list, section_full_content, state)

            # 내용이 전혀 생성되지 않은 경우 경고 처리
            if not section_content_generated:
                print(f">> 경고: 섹션 '{section_title}' 내용 생성 실패")
                yield {"type": "content", "data": {"chunk": f"*'{section_title}' 섹션 생성 중 문제가 발생했습니다.*\n\n"}}

            # 각 섹션 사이에 공백 추가
            yield {"type": "content", "data": {"chunk": "\n\n"}}

        # 워크플로우 완료 후 출처 정보 설정 (실제 사용된 인덱스만)
        # 모든 섹션에서 사용된 인덱스들을 수집
        used_indexes = set()
        for section in design.get("structure", []):
            use_contents = section.get("use_contents", [])
            used_indexes.update(use_contents)

        print(f">> 실제 사용된 인덱스들: {sorted(used_indexes)}")
        print(f">> final_collected_data 길이: {len(final_collected_data) if final_collected_data else 0}")
        print(f">> used_indexes 길이: {len(used_indexes)}")

        # sources 이벤트는 더 이상 보내지 않음 (full_data_dict만 사용)
        # 대신 사용된 인덱스 정보만 로깅
        if final_collected_data and used_indexes:
            print(f">> 보고서에서 실제 사용된 인덱스들: {sorted(used_indexes)}")
            print(f">> 총 {len(used_indexes)}개 출처 사용 (전체 {len(final_collected_data)}개 중)")

        yield {"type": "complete", "data": {
            "message": "보고서 생성 완료"
        }}

    async def _update_use_contents_after_recollection(
    self,
    section_info: Dict,
    all_data: List[SearchResult],
    original_indexes: List[int],
    new_data_indexes: List[int],
    query: str
    ) -> List[int]:
        """보강 후 해당 섹션의 use_contents를 LLM이 업데이트 (전체 내용 기반)"""

        section_title = section_info.get('section_title', '섹션')

        # ⭐ 핵심 개선: 전체 내용을 LLM에게 제공
        data_summary = ""

        # 기존 데이터 (전체 내용)
        data_summary += "=== 기존 선택된 데이터 (전체 내용) ===\n"
        for idx in original_indexes[:3]:  # 처음 3개만 (길이 제한)
            if 0 <= idx < len(all_data):
                res = all_data[idx]
                content = getattr(res, 'content', '')[:800]  # 800자로 제한
                data_summary += f"""
    [{idx:2d}] [{getattr(res, 'source', 'Unknown')}] {getattr(res, 'title', 'No Title')}
    내용: {content}{"..." if len(getattr(res, 'content', '')) > 800 else ""}

    """

        # 새 데이터 (전체 내용)
        data_summary += "=== 새로 추가된 데이터 (전체 내용) ===\n"
        for idx in new_data_indexes:
            if 0 <= idx < len(all_data):
                res = all_data[idx]
                content = getattr(res, 'content', '')[:800]  # 800자로 제한
                data_summary += f"""
    [{idx:2d}] [NEW] [{getattr(res, 'source', 'Unknown')}] {getattr(res, 'title', 'No Title')}
    내용: {content}{"..." if len(getattr(res, 'content', '')) > 800 else ""}

    """

        update_prompt = f"""
    "{section_title}" 섹션을 위해 기존 데이터와 새로 추가된 데이터의 **전체 내용을 읽고** 가장 적합한 데이터들을 선택해주세요.

    **섹션**: "{section_title}"
    **전체 질문**: "{query}"

    {data_summary[:8000]}

    **선택 기준**:
    1. **각 데이터의 전체 내용을 읽고** 섹션 주제와의 관련성 판단
    2. 제목만 보고 결정하지 말고 **실제 내용의 질과 관련성** 확인
    3. 새 데이터는 해당 섹션을 위해 특별히 수집된 것이므로 적극 고려
    4. 실제로 유용한 정보가 담긴 데이터만 최대 8개 선별

    **원본**: {original_indexes}
    **새 데이터**: {new_data_indexes}

    JSON으로만 응답:
    {{
        "updated_use_contents": [0, 2, 5, 8],
        "reasoning": "각 데이터를 선택/제외한 구체적 이유 (내용 기반)"
    }}
    """

        try:
            response = await self._invoke_with_fallback(update_prompt, self.llm, self.llm_openai_mini)
            result = json.loads(re.search(r'\{.*\}', response.content, re.DOTALL).group())

            updated_indexes = result.get("updated_use_contents", [])
            reasoning = result.get("reasoning", "")

            # 유효성 검증
            max_index = len(all_data) - 1
            valid_indexes = [idx for idx in updated_indexes if isinstance(idx, int) and 0 <= idx <= max_index]

            print(f"  - use_contents 업데이트 완료 (전체 내용 기반):")
            print(f"    최종 선택: {valid_indexes}")
            print(f"    선택 이유: {reasoning}")

            return valid_indexes

        except Exception as e:
            print(f"  - use_contents 업데이트 실패: {e}")
            # fallback: 원본 + 새 데이터 합치기 (최대 8개)
            combined = original_indexes + new_data_indexes
            return combined[:8]

    async def _log_chart_verification(self, query: str, section_title: str, section_data_list: List[SearchResult], chart_data: dict, state: dict):
        """차트 생성 검증을 위한 상세 로그 기록"""
        try:
            # 로그 디렉토리 생성
            log_base_dir = "/app/logs"
            chart_verification_dir = f"{log_base_dir}/chart_verification"
            os.makedirs(chart_verification_dir, exist_ok=True)

            # 현재 시간으로 파일명 생성
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]  # 밀리초 포함
            session_id = state.get("session_id", "unknown")
            filename = f"chart_verification_{timestamp}_{session_id}.txt"
            filepath = f"{chart_verification_dir}/{filename}"

            # 검증 로그 내용 생성
            verification_log = self._generate_chart_verification_content(
                query, section_title, section_data_list, chart_data, timestamp
            )

            # 파일에 비동기로 쓰기
            async with aiofiles.open(filepath, 'w', encoding='utf-8') as f:
                await f.write(verification_log)

            print(f"📋 차트 검증 로그 저장완료: {filepath}")

        except Exception as e:
            print(f"❌ 차트 검증 로그 저장 실패: {e}")

    async def _log_section_verification(self, query: str, section_title: str, section_data_list: List[SearchResult], section_content: str, state: dict):
        """섹션 생성 검증을 위한 상세 로그 기록"""
        try:
            # 로그 디렉토리 생성
            log_base_dir = "/app/logs"
            section_verification_dir = f"{log_base_dir}/section_verification"
            os.makedirs(section_verification_dir, exist_ok=True)

            # 현재 시간으로 파일명 생성
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]  # 밀리초 포함
            session_id = state.get("session_id", "unknown")
            filename = f"section_verification_{timestamp}_{session_id}.txt"
            filepath = f"{section_verification_dir}/{filename}"

            # 검증 로그 내용 생성
            verification_log = self._generate_section_verification_content(
                query, section_title, section_data_list, section_content, timestamp
            )

            # 파일에 비동기로 쓰기
            async with aiofiles.open(filepath, 'w', encoding='utf-8') as f:
                await f.write(verification_log)

            print(f"📄 섹션 검증 로그 저장완료: {filepath}")

        except Exception as e:
            print(f"❌ 섹션 검증 로그 저장 실패: {e}")

    def _generate_chart_verification_content(self, query: str, section_title: str, section_data_list: List[SearchResult], chart_data: dict, timestamp: str) -> str:
        """차트 검증 로그 내용 생성"""
        content = f"""
================================================================================
                          차트 생성 검증 로그
================================================================================

생성 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
타임스탬프: {timestamp}

================================================================================
차트 생성 정보
================================================================================

사용자 쿼리:
{query}

섹션 제목:
{section_title}

================================================================================
섹션에서 사용한 데이터 (총 {len(section_data_list)}개)
================================================================================
"""

        # 섹션 데이터 상세 정보
        for i, data_item in enumerate(section_data_list):
            source = getattr(data_item, 'source', 'Unknown')
            title = getattr(data_item, 'title', 'No Title')
            content_text = getattr(data_item, 'content', '')
            url = getattr(data_item, 'url', '')
            score = getattr(data_item, 'score', 0.0)
            doc_type = getattr(data_item, 'document_type', 'unknown')

            content += f"""
[데이터 인덱스 {i}]
  출처: {source}
  제목: {title}
  URL: {url}
  점수: {score:.3f}
  타입: {doc_type}
  내용:
  {content_text[:]}

"""

        content += f"""
================================================================================
생성된 차트 데이터 (JSON)
================================================================================

{json.dumps(chart_data, ensure_ascii=False, indent=2)}

================================================================================
검증 포인트
================================================================================

1. 데이터 정확성: 차트의 수치가 실제 데이터와 일치하는가?
2. 데이터 출처: 차트에 사용된 정보가 위의 섹션 데이터에 기반하는가?
3. 논리적 일관성: 차트 유형이 데이터 특성에 적합한가?
4. 할루시네이션 여부: 실제 데이터에 없는 내용이 차트에 포함되었는가?

================================================================================
검증 완료 후 이 부분에 검토 결과를 기록하세요
================================================================================

[ ] 검증 완료
[ ] 데이터 정확성 확인
[ ] 할루시네이션 없음 확인
[ ] 차트 유형 적절성 확인

검증자: ___________
검증일: ___________
검증 결과:
_________________________________________________________________________

================================================================================
"""

        return content

    def _generate_section_verification_content(self, query: str, section_title: str, section_data_list: List[SearchResult], section_content: str, timestamp: str) -> str:
        """섹션 검증 로그 내용 생성"""
        content = f"""
================================================================================
                          섹션 생성 검증 로그
================================================================================

생성 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
타임스탬프: {timestamp}

================================================================================
섹션 생성 정보
================================================================================

사용자 쿼리:
{query}

섹션 제목:
{section_title}

================================================================================
섹션에서 사용한 데이터 (총 {len(section_data_list)}개)
================================================================================
"""

        # 섹션 데이터 상세 정보
        for i, data_item in enumerate(section_data_list):
            source = getattr(data_item, 'source', 'Unknown')
            title = getattr(data_item, 'title', 'No Title')
            content_text = getattr(data_item, 'content', '')
            url = getattr(data_item, 'url', '')
            score = getattr(data_item, 'score', 0.0)
            doc_type = getattr(data_item, 'document_type', 'unknown')

            content += f"""
[데이터 인덱스 {i}]
  출처: {source}
  제목: {title}
  URL: {url}
  점수: {score:.3f}
  타입: {doc_type}
  내용:
  {content_text[:]}

"""

        content += f"""
================================================================================
생성된 섹션 내용
================================================================================

{section_content}

================================================================================
검증 포인트
================================================================================

1. 내용 정확성: 섹션 내용이 실제 데이터에 기반하는가?
2. 데이터 출처: 섹션에 언급된 정보가 위의 섹션 데이터에서 나온 것인가?
3. 논리적 일관성: 섹션 구조와 내용이 논리적으로 일관된가?
4. 할루시네이션 여부: 실제 데이터에 없는 내용이 섹션에 포함되었는가?
5. 완성도: 섹션이 사용자 질문에 적절히 답변하고 있는가?

================================================================================
검증 완료 후 이 부분에 검토 결과를 기록하세요
================================================================================

[ ] 검증 완료
[ ] 내용 정확성 확인
[ ] 할루시네이션 없음 확인
[ ] 데이터 출처 적절성 확인
[ ] 완성도 확인

검증자: ___________
검증일: ___________
검증 결과:
_________________________________________________________________________

================================================================================
"""

        return content


    def _apply_deduplication(self, results: List[SearchResult], deduplicator: GlobalDeduplicator) -> List[SearchResult]:
        """SearchResult 객체 리스트에 중복 제거 적용"""
        if not results:
            return results

        # SearchResult 객체를 딕셔너리로 변환하여 중복 제거 적용
        results_as_dicts = []
        for result in results:
            result_dict = {
                "page_content": result.content,
                "meta_data": getattr(result, "metadata", {}),
                "name": result.title,
                "source": result.source,
                "url": getattr(result, "url", ""),
                "score": getattr(result, "score", 0.0),
                "document_type": getattr(result, "document_type", "unknown")
            }

            # meta_data에서 chunk_id 추출 시도
            if hasattr(result, "metadata") and result.metadata:
                result_dict["meta_data"] = result.metadata
            elif hasattr(result, "source") and result.source:
                # source 기반으로 고유성 판단
                result_dict["meta_data"] = {"chunk_id": f"source_{hash(result.source)}"}

            results_as_dicts.append(result_dict)

        # 소스별로 중복 제거 적용
        source_type = self._determine_source_type(results[0])
        unique_dicts = deduplicator.deduplicate_results(results_as_dicts, source_type)

        # 다시 SearchResult 객체로 변환
        unique_results = []
        for result_dict in unique_dicts:
            # 원본 SearchResult와 매칭하여 복원
            for original_result in results:
                if (original_result.content == result_dict.get("page_content", "") and
                    original_result.title == result_dict.get("name", "")):
                    unique_results.append(original_result)
                    break

        return unique_results

    def _determine_source_type(self, result: SearchResult) -> str:
        """SearchResult 객체로부터 소스 타입 결정"""
        source = getattr(result, "source", "").lower()

        if "elasticsearch" in source or "vector" in source:
            return "elasticsearch"
        elif "neo4j" in source or "graph" in source:
            return "neo4j"
        elif "web" in source or "google" in source:
            return "web"
        elif "rdb" in source or "postgres" in source:
            return "rdb"
        else:
            return "unknown"

