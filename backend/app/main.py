import sys
import uuid
import json
import asyncio
from datetime import datetime
from typing import AsyncGenerator, Dict, Any, List, Optional

# Pydantic과 FastAPI는 웹 서버 구성을 위해 필요합니다.
from pydantic import BaseModel, Field
from fastapi import FastAPI, HTTPException, Depends
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware

# 데이터베이스 import 추가
from .database import ChatDatabase

from .core.config.env_checker import check_api_keys

check_api_keys()

# 비동기 모델 사전 로드 (백그라운드에서 실행)
async def preload_models_async():
    """백그라운드에서 비동기적으로 모델을 미리 로드"""
    try:
        print("\n" + "="*50)
        print("🚀 백그라운드 모델 로딩 시작...")
        from .services.database.elasticsearch.elastic_search_rag_tool import get_hf_model, get_bge_reranker, get_qwen3_model

        # 백그라운드에서 모델들을 순차적으로 로드
        loop = asyncio.get_event_loop()

        # 임베딩 모델 로드
        print("📥 임베딩 모델 로드 중...")
        await loop.run_in_executor(None, get_hf_model)
        print("✅ 임베딩 모델 로드 완료!")

        # 리랭킹 모델 로드
        print("📥 리랭킹 모델 로드 중...")
        await loop.run_in_executor(None, get_bge_reranker)
        print("✅ 리랭킹 모델 로드 완료!")

        # Qwen3 모델도 백그라운드에서 로드 (선택사항)
        print("📥 Qwen3 모델 로드 중...")
        await loop.run_in_executor(None, get_qwen3_model)
        print("✅ Qwen3 모델 로드 완료!")

        print("🎉 모든 모델 백그라운드 로딩 완료!")
        print("="*50 + "\n")
    except Exception as e:
        print(f"⚠️ 백그라운드 모델 로딩 중 오류 (서버는 계속 작동): {e}")


# 시스템 경로 설정을 통해 다른 폴더의 모듈을 임포트합니다.
# 실제 프로젝트 구조에 맞게 이 부분은 조정될 수 있습니다.
# sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# --- 모델 및 에이전트 클래스 임포트 ---
# 기존 에이전트들을 그래프 형태로 개선하되 스트리밍 유지
from .core.agents.orchestrator import TriageAgent, OrchestratorAgent
from .core.agents.conversational_agent import SimpleAnswererAgent
from .core.models.models import StreamingAgentState
from .utils.session_logger import get_session_logger, session_logger, set_current_session

# StreamingAgentState를 Pydantic 모델로 재정의
class StreamingAgentStateModel(BaseModel):
    original_query: str
    session_id: str
    message_id: str | None = None
    flow_type: str | None = None
    plan: dict | None = None
    design: dict | None = None
    metadata: dict = Field(default_factory=dict)
    persona: str | None = None  # 팀/페르소나 정보 추가

    # 필수 필드들 추가 (TypedDict와 호환성을 위해)
    conversation_id: str = ""
    user_id: str = ""
    start_time: str = Field(default_factory=lambda: datetime.now().isoformat())
    current_step_index: int = 0
    step_results: list = Field(default_factory=list)
    execution_log: list = Field(default_factory=list)
    needs_replan: bool = False
    replan_feedback: str | None = None
    final_answer: str | None = None

# --- Pydantic 모델 정의 ---
class QueryRequest(BaseModel):
    query: str
    session_id: str | None = Field(default_factory=lambda: str(uuid.uuid4()))
    message_id: str | None = Field(default_factory=lambda: str(uuid.uuid4()))
    team_id: str | None = None  # 사용자가 선택한 팀 ID
    project_id: str | None = None  # 프로젝트 ID 추가
    conversation_history: List[Dict] | None = None  # 대화 히스토리 추가

# --- FastAPI 애플리케이션 설정 ---
app = FastAPI(
    title="Intelligent RAG Agent System",
    description="A sophisticated, multi-agent system for handling complex queries.",
    version="3.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 서버 시작 이벤트에서 백그라운드 모델 로딩 시작
@app.on_event("startup")
async def startup_event():
    """FastAPI 서버 시작 시 백그라운드에서 모델 로딩 시작"""
    print("🚀 FastAPI 서버 시작!")
    print("📦 백그라운드에서 모델 로딩을 시작합니다...")
    # 백그라운드 태스크로 모델 로딩 시작 (서버 시작을 차단하지 않음)
    asyncio.create_task(preload_models_async())

# --- 데이터베이스 인스턴스 초기화 ---
db = ChatDatabase()

# --- 에이전트 인스턴스 초기화 ---
triage_agent = TriageAgent()
orchestrator_agent = OrchestratorAgent()
simple_answerer_agent = SimpleAnswererAgent()

# --- 데이터베이스 관련 Pydantic 모델 ---
# 프로젝트 관련 모델
class ProjectCreate(BaseModel):
    title: str
    description: Optional[str] = None
    user_id: Optional[str] = None
    id: Optional[str] = None  # 프론트엔드에서 지정한 ID 사용

class ProjectUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None

class ProjectResponse(BaseModel):
    id: str
    title: str
    description: Optional[str] = None
    created_at: str
    updated_at: str
    conversation_count: Optional[int] = 0

class ConversationCreate(BaseModel):
    title: str
    user_id: Optional[str] = None
    project_id: Optional[str] = None  # 프로젝트 ID 추가
    id: Optional[str] = None  # 프론트엔드에서 지정한 ID 사용

class ConversationResponse(BaseModel):
    id: str
    title: str
    project_id: Optional[str] = None
    created_at: str
    updated_at: str
    messages: Optional[List[Dict]] = None

class MessageCreate(BaseModel):
    conversation_id: str
    type: str  # "user" or "assistant"
    content: str
    timestamp: Optional[str] = None
    team_id: Optional[str] = None
    charts: Optional[List[Dict]] = None
    search_results: Optional[List[Dict]] = None
    sources: Optional[Dict] = None
    status: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    duration_ms: Optional[int] = None
    # 추가 필드들
    is_streaming: Optional[bool] = False
    was_aborted: Optional[bool] = False
    full_data_dict: Optional[Dict] = None
    section_data_dicts: Optional[Dict] = None
    message_state: Optional[Dict] = None
    section_headers: Optional[List[Dict]] = None
    status_history: Optional[List[Dict]] = None

class MessageUpdate(BaseModel):
    content: Optional[str] = None
    was_aborted: Optional[bool] = None
    is_streaming: Optional[bool] = None
    status: Optional[str] = None
    end_time: Optional[str] = None
    duration_ms: Optional[int] = None

class StreamingSessionData(BaseModel):
    current_message: str
    current_charts: List[Dict]
    status: str

# --- API 엔드포인트 정의 ---
@app.get("/")
async def root():
    return {"message": "Intelligent RAG Agent System is running."}

@app.post("/query/stream")
async def stream_query(request: QueryRequest):
    """
    사용자 쿼리를 받아, 유형에 따라 적절한 에이전트 워크플로우를 실행하고
    그 결과를 실시간으로 스트리밍하는 메인 엔드포인트입니다.
    """
    # 세션별 로거 생성
    logger = get_session_logger(request.session_id, "MainServer")
    logger.info(f"새 쿼리 요청 수신")
    logger.info(f"Query: {request.query}")
    logger.info(f"Team ID: {request.team_id}")

    async def event_stream_generator() -> AsyncGenerator[str, None]:
        """쿼리 처리 및 결과 스트리밍을 위한 비동기 생성기"""

        # 세션 컨텍스트 설정
        set_current_session(request.session_id)

        state = StreamingAgentStateModel(
            original_query=request.query,
            session_id=request.session_id,
            message_id=request.message_id,
            conversation_id=request.session_id,
            user_id="default_user"
        )

        # 대화 히스토리를 state에 추가
        if request.conversation_history:
            state.metadata["conversation_history"] = request.conversation_history
            print(f">> 대화 히스토리 포함: {len(request.conversation_history)}개 메시지")
        else:
            print(">> 대화 히스토리 없음 - 새 대화")
        
        # 프로젝트 정보를 state에 추가
        if request.project_id:
            try:
                print(f">> 프로젝트 ID로 조회 시도: {request.project_id}")
                project = db.get_project(request.project_id)
                if project:
                    project_title = project.get("title", "Unknown_Project")
                    state.metadata["project_name"] = project_title
                    state.metadata["project_id"] = request.project_id
                    print(f">> 프로젝트 정보 포함: {project_title} (ID: {request.project_id})")
                    print(f">> state.metadata 설정 완료: {state.metadata}")
                else:
                    print(f">> 프로젝트 조회 실패: {request.project_id} - DB에서 찾을 수 없음")
            except Exception as e:
                print(f">> 프로젝트 조회 중 오류: {e}")
                import traceback
                traceback.print_exc()
        else:
            print(">> 프로젝트 정보 없음 - request.project_id가 None")

        # 팀 정보를 state에 추가
        if request.team_id:
            state.metadata["team_id"] = request.team_id
            print(f">> 선택된 팀: {request.team_id}")
        else:
            print(">> 팀 선택 없음 - LLM이 자동 판단하거나 general 사용")

        try:
            # 1. Triage Agent 실행
            yield server_sent_event("status", {"message": "요청 유형 분석 중...", "session_id": state.session_id})
            state_dict = state.model_dump()

            # 🔑 핵심: 딕셔너리로 변환된 후에 persona 추가
            if request.team_id:
                state_dict["persona"] = request.team_id
                print(f"✅ state_dict에 persona '{request.team_id}' 추가됨")
                print(f"🔍 state_dict 내용 확인: {list(state_dict.keys())}")
                print(f"🎭 저장된 persona 값: {state_dict.get('persona')}")
            else:
                state_dict["persona"] = "기본"
                print("⚠️ team_id가 없어서 state_dict에 '기본' persona 추가됨")
                print(f"🔍 전달받은 team_id: {request.team_id} (falsy 값인지 확인)")

            updated_state_dict = await triage_agent.classify_request(request.query, state_dict)
            state = StreamingAgentStateModel(**updated_state_dict)
            flow_type = state.flow_type or "task"

            # 2. 분류된 유형에 따라 다른 워크플로우 실행
            if flow_type == "chat":
                print(">> Flow type: 'chat'. Starting SimpleAnswererAgent.")
                yield server_sent_event("status", {"message": "간단한 답변 생성 중...", "session_id": state.session_id})

                content_generated = False
                state_dict = state.model_dump()  # 딕셔너리로 변환

                async for chunk in simple_answerer_agent.answer_streaming(state_dict):
                    content_generated = True

                    # SimpleAnswerer에서 검색 결과 이벤트가 올 수 있는지 확인
                    if chunk.startswith('{"type": "search_results"'):
                        try:
                            # JSON 이벤트 파싱
                            search_event = json.loads(chunk.strip())
                            # 검색 결과 이벤트를 프론트엔드로 전달
                            yield server_sent_event("search_results", {
                                "step": search_event["step"],
                                "tool_name": search_event["tool_name"],
                                "query": search_event["query"],
                                "results": search_event["results"],
                                "session_id": state.session_id
                            })
                        except json.JSONDecodeError:
                            # JSON 파싱 실패 시 일반 텍스트로 처리
                            yield server_sent_event("content", {"chunk": chunk, "session_id": state.session_id})
                    elif chunk.startswith('{"type": "full_data_dict"'):
                        try:
                            # full_data_dict 이벤트 파싱
                            full_data_event = json.loads(chunk.strip())
                            # full_data_dict 이벤트를 프론트엔드로 전달
                            yield server_sent_event("full_data_dict", {
                                "data_dict": full_data_event["data_dict"],
                                "session_id": state.session_id
                            })
                        except json.JSONDecodeError:
                            # JSON 파싱 실패 시 일반 텍스트로 처리
                            yield server_sent_event("content", {"chunk": chunk, "session_id": state.session_id})
                    else:
                        # 일반 텍스트 청크
                        yield server_sent_event("content", {"chunk": chunk, "session_id": state.session_id})

                # 내용이 전혀 생성되지 않은 경우 처리
                if not content_generated:
                    print(">> 경고: SimpleAnswererAgent에서 내용이 전혀 생성되지 않음")
                    yield server_sent_event("error", {"message": "답변 생성 중 문제가 발생했습니다.", "session_id": state.session_id})

                # SimpleAnswerer 완료 후 출처 정보 전송 (업데이트된 state_dict에서 추출)
                # answer_streaming에서 state_dict가 업데이트되므로 다시 확인
                sources = state_dict.get("metadata", {}).get("sources")
                print(f">> SimpleAnswerer 출처 정보 확인: {sources}")  # 디버깅용
                if sources:
                    sources_data = {
                        "total_count": len(sources),
                        "sources": sources
                    }
                    print(f">> SimpleAnswerer 출처 정보 전송: {sources_data}")  # 디버깅용
                    yield server_sent_event("complete", {
                        "message": "답변 생성 완료",
                        "sources": sources_data,
                        "session_id": state.session_id
                    })
                else:
                    print(">> SimpleAnswerer 출처 정보 없음")  # 디버깅용

            else: # flow_type == "task"
                print(">> Flow type: 'task'. Starting OrchestratorAgent workflow.")

                # OrchestratorAgent의 워크플로우를 스트리밍하면서 상세한 상태 메시지 처리
                chart_index = 1
                content_generated = False
                # execute_report_workflow는 이제 텍스트/차트 외에 상태 정보도 함께 yield 합니다.

                async for event in orchestrator_agent.execute_report_workflow(state.model_dump()):
                    content_generated = True

                    event_type = event.get("type")
                    data = event.get("data")

                    # session_id를 모든 이벤트에 추가
                    if isinstance(data, dict):
                        data["session_id"] = state.session_id

                    if event_type == "chart":
                        print(f"Chart event received: {data}")
                        # 프론트엔드가 인식할 수 있는 최종 차트 객체로 변환하여 전송
                        chart_payload = {
                            "chart_data": data,
                            "session_id": state.session_id
                        }
                        yield server_sent_event("chart", chart_payload)
                        chart_index += 1
                    elif event_type == "complete":
                        print(f">> OrchestratorAgent complete 이벤트 수신: {data}")
                        # complete 이벤트를 그대로 전달
                        yield server_sent_event("complete", data)
                    else:
                        # status, plan, content_chunk 등 다른 모든 이벤트를 그대로 전달
                        yield server_sent_event(event_type, data if isinstance(data, dict) else {"data": data, "session_id": state.session_id})

                # OrchestratorAgent 완료 후 출처 정보 전송 (이제 불필요 - complete 이벤트에서 처리됨)
                # updated_state_dict = state.model_dump()
                # sources = updated_state_dict.get("metadata", {}).get("sources")
                # print(f">> OrchestratorAgent 출처 정보 확인: {sources}")  # 디버깅용
                # if sources:
                #     sources_data = {
                #         "total_count": len(sources),
                #         "sources": sources
                #     }
                #     print(f">> OrchestratorAgent 출처 정보 전송: {sources_data}")  # 디버깅용
                #     yield server_sent_event("complete", {
                #         "message": "보고서 생성 완료",
                #         "sources": sources_data,
                #         "session_id": state.session_id
                #     })
                # else:
                #     print(">> OrchestratorAgent 출처 정보 없음")  # 디버깅용

                # 내용이 전혀 생성되지 않은 경우 처리
                if not content_generated:
                    print(">> 경고: OrchestratorAgent에서 내용이 전혀 생성되지 않음")
                    yield server_sent_event("error", {"message": "보고서 생성 중 문제가 발생했습니다.", "session_id": state.session_id})

        except Exception as e:
            print(f"!! 스트리밍 중 심각한 오류 발생: {e}", file=sys.stderr)
            error_payload = {"message": f"오류가 발생했습니다: {str(e)}", "session_id": state.session_id}
            yield server_sent_event("error", error_payload)

        finally:
            print(f"Query processing finished for session: {request.session_id}\n{'='*57}")
            yield server_sent_event("final_complete", {"message": "모든 작업이 완료되었습니다.", "session_id": state.session_id})

    return StreamingResponse(event_stream_generator(), media_type="text/event-stream")

def server_sent_event(event_type: str, data: Dict[str, Any]) -> str:
    """Server-Sent Events (SSE) 형식에 맞는 문자열을 생성합니다."""
    # 프론트엔드가 기대하는 형식에 맞춰 type을 data에 포함
    data_with_type = {"type": event_type, "session_id": data.get("session_id"), **data}
    payload = json.dumps(data_with_type, ensure_ascii=False)
    return f"data: {payload}\n\n"


@app.get("/teams")
def get_teams():
    """사용 가능한 팀 목록을 반환합니다."""
    try:
        # orchestrator_agent에서 팀 정보 가져오기
        persona_names = orchestrator_agent.get_available_personas()
        # 문자열 배열을 객체 배열로 변환
        teams = []
        for persona_name in persona_names:
            teams.append({
                "id": persona_name,
                "name": persona_name,
                "description": f"{persona_name} 전용 응답"
            })
        return {"teams": teams}
    except Exception as e:
        print(f"팀 목록 조회 오류: {e}")
        # 기본 팀 목록 반환
        return {
            "teams": [
                {"id": "기본", "name": "기본", "description": "기본 응답"}
            ]
        }

@app.post("/teams/suggest")
async def suggest_team(request: dict):
    """쿼리 내용을 분석하여 적합한 팀을 추천합니다."""
    try:
        query = request.get("query", "")
        if not query:
            return {"error": "쿼리가 필요합니다"}

        # orchestrator_agent를 통해 팀 추천
        suggested_team = await orchestrator_agent.suggest_team_for_query(query)
        return {"suggested_team": suggested_team}
    except Exception as e:
        print(f"팀 추천 오류: {e}")
        return {"suggested_team": "general"}

@app.get("/memory/stats")
async def get_memory_stats(user_id: str = None):
    """메모리 통계 조회"""
    # 메모리 시스템이 구현되면 활성화
    return {"error": "메모리 시스템이 아직 구현되지 않았습니다"}


@app.post("/chat/generate-title")
async def generate_chat_title(request: dict):
    """사용자 쿼리를 바탕으로 LLM이 채팅방 제목을 생성합니다."""
    try:
        query = request.get("query", "")
        if not query:
            return {"error": "쿼리가 필요합니다"}

        # ChatOpenAI를 사용하여 제목 생성
        from langchain_openai import ChatOpenAI

        llm = ChatOpenAI(
            model="gpt-4o-mini",
            temperature=0.3,
            max_tokens=50
        )

        # 제목 생성 프롬프트
        title_prompt = f"""사용자의 질문을 바탕으로 간결하고 명확한 채팅방 제목을 생성해주세요.

사용자 질문: {query}

조건:
- 10글자 이내로 작성
- 핵심 키워드 포함
- 한국어로 작성
- 특수문자나 따옴표 사용 금지

제목만 답변해주세요:"""

        # LLM 호출
        response = llm.invoke(title_prompt)
        title = response.content.strip()

        # 제목 후처리 (특수문자 제거, 길이 제한)
        title = title.replace('"', '').replace("'", '').replace('\n', '').strip()
        if len(title) > 15:
            title = title[:15]

        return {"title": title}

    except Exception as e:
        print(f"채팅방 제목 생성 오류: {e}")
        # 기본 제목 반환
        return {"title": "새 채팅"}

# === 데이터베이스 API 엔드포인트 ===

# === 프로젝트 관련 API ===
@app.post("/api/projects", response_model=ProjectResponse)
async def create_project(project: ProjectCreate):
    """새 프로젝트 생성"""
    try:
        # 프론트엔드에서 ID를 지정했으면 사용, 아니면 새로 생성
        project_id = project.id or f"project_{int(datetime.now().timestamp() * 1000)}_{uuid.uuid4().hex[:8]}"

        print(f"🔄 프로젝트 생성 요청: ID={project_id}, Title={project.title}")

        result = db.create_project(
            project_id=project_id,
            title=project.title,
            description=project.description,
            user_id=project.user_id
        )

        print(f"✅ 프로젝트 생성 성공: {project_id}")
        return ProjectResponse(**result, conversation_count=0)
    except Exception as e:
        print(f"❌ 프로젝트 생성 실패: {project_id}, Error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/projects", response_model=List[ProjectResponse])
async def get_projects(user_id: Optional[str] = None):
    """모든 프로젝트 조회"""
    try:
        projects = db.get_all_projects(user_id=user_id)
        return [ProjectResponse(**proj) for proj in projects]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/projects/{project_id}", response_model=ProjectResponse)
async def get_project(project_id: str):
    """특정 프로젝트 조회"""
    try:
        project = db.get_project(project_id)
        if not project:
            raise HTTPException(status_code=404, detail="프로젝트를 찾을 수 없습니다")

        # 대화 개수 조회
        conversations = db.get_conversations_by_project(project_id)
        project["conversation_count"] = len(conversations)

        return ProjectResponse(**project)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/api/projects/{project_id}", response_model=ProjectResponse)
async def update_project(project_id: str, project_update: ProjectUpdate):
    """프로젝트 제목/설명 수정"""
    try:
        print(f"🔄 프로젝트 수정 요청: ID={project_id}, Data={project_update.model_dump()}")

        success = db.update_project_title(
            project_id=project_id,
            title=project_update.title,
            description=project_update.description
        )

        if not success:
            raise HTTPException(status_code=404, detail="프로젝트를 찾을 수 없습니다")

        # 업데이트된 프로젝트 조회
        updated_project = db.get_project(project_id)
        conversations = db.get_conversations_by_project(project_id)
        updated_project["conversation_count"] = len(conversations)

        print(f"✅ 프로젝트 수정 성공: {project_id}")
        return ProjectResponse(**updated_project)
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ 프로젝트 수정 실패: {project_id}, Error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/projects/{project_id}")
async def delete_project(project_id: str, hard_delete: bool = False):
    """프로젝트 삭제"""
    try:
        print(f"🔄 프로젝트 삭제 요청: ID={project_id}, Hard={hard_delete}")

        success = db.delete_project(project_id, soft_delete=not hard_delete)

        if not success:
            raise HTTPException(status_code=404, detail="프로젝트를 찾을 수 없습니다")

        print(f"✅ 프로젝트 삭제 성공: {project_id}")
        return {"message": "프로젝트가 삭제되었습니다"}
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ 프로젝트 삭제 실패: {project_id}, Error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/projects/{project_id}/conversations", response_model=List[ConversationResponse])
async def get_project_conversations(project_id: str, user_id: Optional[str] = None):
    """특정 프로젝트의 대화 목록 조회"""
    try:
        conversations = db.get_conversations_by_project(project_id, user_id)
        return [ConversationResponse(**conv) for conv in conversations]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# === 대화 관련 API ===
@app.post("/api/conversations", response_model=ConversationResponse)
async def create_conversation(conversation: ConversationCreate):
    """새 대화 생성"""
    try:
        # 프론트엔드에서 ID를 지정했으면 사용, 아니면 새로 생성
        conversation_id = conversation.id or str(uuid.uuid4())

        print(f"🔄 대화 생성 요청: ID={conversation_id}, Title={conversation.title}")

        result = db.create_conversation(
            conversation_id=conversation_id,
            title=conversation.title,
            user_id=conversation.user_id,
            project_id=conversation.project_id
        )

        print(f"✅ 대화 생성 성공: {conversation_id}")
        return ConversationResponse(**result)
    except Exception as e:
        print(f"❌ 대화 생성 실패: {conversation_id}, Error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/conversations", response_model=List[ConversationResponse])
async def get_conversations(user_id: Optional[str] = None, project_id: Optional[str] = None):
    """모든 대화 조회 (프로젝트별 필터링 지원)"""
    try:
        conversations = db.get_all_conversations(user_id=user_id, project_id=project_id)
        return [ConversationResponse(**conv) for conv in conversations]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/conversations/{conversation_id}", response_model=ConversationResponse)
async def get_conversation(conversation_id: str):
    """특정 대화 조회 (메시지 포함)"""
    try:
        conversation = db.get_conversation(conversation_id)
        if not conversation:
            raise HTTPException(status_code=404, detail="대화를 찾을 수 없습니다")

        # 메시지 조회
        messages = db.get_messages(conversation_id)
        conversation["messages"] = messages

        return ConversationResponse(**conversation)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/api/conversations/{conversation_id}/title")
async def update_conversation_title(conversation_id: str, request: dict):
    """대화 제목 수정"""
    try:
        title = request.get("title")
        if not title:
            raise HTTPException(status_code=400, detail="제목이 필요합니다")

        success = db.update_conversation_title(conversation_id, title)
        if not success:
            raise HTTPException(status_code=404, detail="대화를 찾을 수 없습니다")

        return {"message": "제목이 업데이트되었습니다"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/conversations/{conversation_id}")
async def delete_conversation(conversation_id: str, hard_delete: bool = False):
    """대화 삭제"""
    try:
        success = db.delete_conversation(conversation_id, soft_delete=not hard_delete)
        if not success:
            raise HTTPException(status_code=404, detail="대화를 찾을 수 없습니다")

        return {"message": "대화가 삭제되었습니다"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/messages")
async def create_message(message: MessageCreate):
    """새 메시지 생성"""
    try:
        message_id = db.create_message(
            conversation_id=message.conversation_id,
            message_data=message.model_dump()
        )
        print(f"✅ 메시지 생성 완료: ID={message_id}")
        return {"message_id": message_id, "message": "메시지가 생성되었습니다"}
    except Exception as e:
        print(f"❌ 메시지 생성 오류: {str(e)}")
        print(f"💾 요청 데이터: {message.model_dump()}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/conversations/{conversation_id}/messages")
async def get_messages(conversation_id: str):
    """대화의 모든 메시지 조회"""
    try:
        messages = db.get_messages(conversation_id)
        return {"messages": messages}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/api/messages/{message_id}")
async def update_message(message_id: int, updates: MessageUpdate):
    """메시지 업데이트"""
    try:
        success = db.update_message(message_id, updates.model_dump(exclude_unset=True))
        if not success:
            raise HTTPException(status_code=404, detail="메시지를 찾을 수 없습니다")

        return {"message": "메시지가 업데이트되었습니다"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/messages/{message_id}/status")
async def add_status_history(message_id: int, request: dict):
    """메시지 상태 히스토리 추가"""
    try:
        status_message = request.get("status_message")
        if not status_message:
            raise HTTPException(status_code=400, detail="상태 메시지가 필요합니다")

        status_id = db.add_status_history(
            message_id=message_id,
            status_message=status_message,
            step_number=request.get("step_number"),
            total_steps=request.get("total_steps")
        )

        return {"status_id": status_id, "message": "상태가 추가되었습니다"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/streaming-sessions/{conversation_id}")
async def save_streaming_session(conversation_id: str, session_data: StreamingSessionData):
    """스트리밍 세션 저장"""
    try:
        success = db.save_streaming_session(conversation_id, session_data.model_dump())
        if not success:
            raise HTTPException(status_code=500, detail="스트리밍 세션 저장 실패")

        return {"message": "스트리밍 세션이 저장되었습니다"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/streaming-sessions/{conversation_id}")
async def get_streaming_session(conversation_id: str):
    """스트리밍 세션 조회"""
    try:
        session = db.get_streaming_session(conversation_id)
        if not session:
            raise HTTPException(status_code=404, detail="스트리밍 세션을 찾을 수 없습니다")

        return session
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/streaming-sessions/{conversation_id}")
async def delete_streaming_session(conversation_id: str):
    """스트리밍 세션 삭제"""
    try:
        success = db.delete_streaming_session(conversation_id)
        # 스트리밍 세션이 없어도 성공으로 처리 (이미 삭제됨)
        if success:
            return {"message": "스트리밍 세션이 삭제되었습니다"}
        else:
            return {"message": "스트리밍 세션이 이미 삭제되었거나 존재하지 않습니다"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health_check():
    """헬스 체크 엔드포인트"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "version": "2.0"
    }

# PDF API 라우터 추가
try:
    from .api.pdf import router as pdf_router
    app.include_router(pdf_router, prefix="/api/pdf", tags=["PDF"])
    print("✅ PDF API 라우터가 성공적으로 로드되었습니다.")
except ImportError as e:
    print(f"⚠️ PDF API 라우터 로드 실패 (라이브러리 누락): {e}")
    print("⚠️ PDF 다운로드 기능을 사용하려면 requirements.txt의 PDF 관련 라이브러리를 설치하세요.")

# === 세션별 로그 관리 API ===
@app.get("/api/sessions/{session_id}/logs")
async def get_session_logs(session_id: str):
    """특정 세션의 로그 조회"""
    try:
        logs = session_logger.get_session_logs(session_id)
        return {"session_id": session_id, "logs": logs, "count": len(logs)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/sessions")
async def get_all_sessions():
    """모든 활성 세션 목록 조회"""
    try:
        sessions = session_logger.get_all_sessions()
        return {"sessions": sessions, "count": len(sessions)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/sessions/{session_id}/logs")
async def clear_session_logs(session_id: str):
    """특정 세션의 로그 삭제"""
    try:
        session_logger.clear_session_logs(session_id)
        return {"message": f"세션 {session_id}의 로그가 삭제되었습니다"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/sessions/cleanup")
async def cleanup_old_sessions(max_sessions: int = 50):
    """오래된 세션 로그 정리"""
    try:
        session_logger.cleanup_old_sessions(max_sessions)
        remaining_sessions = session_logger.get_all_sessions()
        return {
            "message": f"로그 정리 완료",
            "remaining_sessions": len(remaining_sessions),
            "max_sessions": max_sessions
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
