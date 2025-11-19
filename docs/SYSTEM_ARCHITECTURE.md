# Multi-Agent RAG 시스템 아키텍처 및 구현 상세

## 목차
3.5 [AI 에이전트 구성](#35-ai-에이전트-구성)
- 3.5.1 [에이전트 아키텍처 개요](#351-에이전트-아키텍처-개요)
- 3.5.2 [에이전트 Workflow 최적화](#352-에이전트-workflow-최적화)
- 3.5.3 [에이전트 구성요소별 상세](#353-에이전트-구성요소별-상세)
- 3.5.4 [페르소나 기반 보고서 생성](#354-페르소나-기반-보고서-생성)
- 3.5.5 [리서치 리포트 구조 및 출처관리](#355-리서치-리포트-구조-및-출처관리)
- 3.5.6 [외부 도구 및 Multi-RAG 연동](#356-외부-도구-및-multi-rag-연동)

---

## 3.5 AI 에이전트 구성

### 3.5.1 에이전트 아키텍처 개요

#### 시스템 구성

본 시스템은 **4개의 전문화된 AI 에이전트**로 구성된 Multi-Agent 아키텍처 채택:

- **TriageAgent**: 사용자 요청을 분석하여 'chat' 또는 'task' 플로우로 분류
- **OrchestratorAgent**: 전체 워크플로우 관리 및 실행 계획 수립
- **DataGathererAgent**: Multi-RAG 방식으로 다양한 데이터 소스에서 정보 수집
- **ProcessorAgent**: 수집된 데이터 기반 고품질 보고서 생성

#### 데이터 흐름도

```
사용자 요청
   ↓
[TriageAgent] → 'chat' or 'task' 분류
   ↓
[OrchestratorAgent]
   ├─ 계획 수립 (generate_plan)
   ├─ Graph DB 프리체크 (_probe_graph_data_locations)
   └─ 워크플로우 실행 (execute_report_workflow)
       ↓
[DataGathererAgent] → Multi-RAG 병렬 검색
   ├─ Web Search
   ├─ Vector DB (Elasticsearch)
   ├─ Graph DB (Neo4j)
   ├─ RDB (PostgreSQL)
   ├─ PubMed
   └─ Arxiv
       ↓
[ProcessorAgent] → 보고서 생성
   ├─ 구조 설계 (_design_report_structure)
   ├─ 섹션 생성 (generate_section_streaming)
   └─ 차트 생성 (_create_charts)
       ↓
사용자에게 스트리밍 전송 (SSE)
```

---

### 3.5.2 에이전트 Workflow 최적화

#### Planning Agent의 동적 워크플로우 설정

##### 지능형 단계별 계획 수립

**위치**: [orchestrator.py:468-769](multiagent-rag-system/backend/app/core/agents/orchestrator.py#L468-L769)

**OrchestratorAgent**의 `generate_plan` 메서드 주요 기능:

- 사용자 요청 분석 및 최적의 실행 계획 동적 생성
- 의존성 고려한 단계별 계획 수립
- 페르소나 관점 반영한 계획 커스터마이징

```python
# 파일 위치: multiagent-rag-system/backend/app/core/agents/orchestrator.py:468-769

async def generate_plan(self, state: StreamingAgentState) -> StreamingAgentState:
    """페르소나 관점과 의존성을 반영하여 단계별 실행 계획(Hybrid Model)을 수립합니다."""
    print(f"\n>> Orchestrator: 지능형 단계별 계획 수립 시작")
    query = state["original_query"]
    kst = pytz.timezone('Asia/Seoul')
    current_date_str = datetime.now(kst).strftime("%Y년 %m월 %d일")

    # 페르소나 정보 추출
    persona_name = state.get("persona", "기본")
    persona_info = self.personas.get(persona_name, {})
    persona_description = persona_info.get("description", "일반적인 분석가")
    print(f"  - 계획 수립에 '{persona_name}' 페르소나 관점 적용")

    # Graph 프리-체크 결과를 플래닝 프롬프트에 주입
    graph_probe = state.get("metadata", {}).get("graph_probe", {}) or {}
    gp_isfrom = graph_probe.get("has_isfrom", False)
    gp_nutr = graph_probe.get("has_nutrients", False)
    gp_doc = graph_probe.get("has_docrels", False)
    gp_docrels_preview = ""
    for d in graph_probe.get("docrels", [])[:3]:
        gp_docrels_preview += f"- {d.get('source','?')} - {d.get('target','?')}" \
                              f"{' (type:'+d.get('rel_type','')+')' if d.get('rel_type') else ''}" \
                              f"{' [doc:'+d.get('doc','')+']' if d.get('doc') else ''}\n"

    # 방대한 계획 수립 프롬프트 (약 280줄)
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
**페르소나**: {persona_name} ({persona_description})

... (이하 프롬프트 생략) ...
"""

    # LLM 호출 및 계획 생성
    # ... (생략) ...

    return state
```

**주요 특징**:

- **Strict Adherence Mandate**: 사용자 요청을 확장하거나 추측하지 않는 4가지 엄격한 규칙
- **도구 명세 가이드**: 5가지 도구(rdb_search, vector_db_search, graph_db_search, pubmed_search, web_search)의 용도와 제약사항 명시
- **6단계 사고 프로세스**: 요청 분석 → Graph DB 프리체크 활용 → 하위 질문 도출 → 도구 선택 → 의존성 분석 → 최종 계획 수립
- **3가지 실행 패턴 예시**: 단순 병렬 실행, 순수 병렬 실행, 순차 의존 실행

##### Graph DB 프리체크 메커니즘

**위치**: [orchestrator.py:771-822](multiagent-rag-system/backend/app/core/agents/orchestrator.py#L771-L822)

```python
# 파일 위치: multiagent-rag-system/backend/app/core/agents/orchestrator.py:771-822

async def _probe_graph_data_locations(self, query: str) -> Dict[str, Any]:
    """Graph DB에 미리 쿼리하여 어떤 종류의 데이터가 존재하는지 파악"""
    print(f"\n>> Graph DB Pre-Check 시작: '{query}'")

    result = {
        "has_isfrom": False,
        "has_nutrients": False,
        "has_docrels": False,
        "docrels": []
    }

    # IS_FROM 관계 체크 (예: "무는 어디서 오나요?")
    # ... (로직 생략) ...

    # HAS_NUTRIENTS 관계 체크 (예: "무의 영양소는?")
    # ... (로직 생략) ...

    # DOCUMENT 관계 체크 (보고서, 논문 등)
    # ... (로직 생략) ...

    return result
```

**프리체크 메커니즘의 역할**:

- Graph DB에 미리 쿼리하여 데이터 존재 여부 파악
- IS_FROM 관계, HAS_NUTRIENTS 관계, DOCUMENT 관계 등 확인
- 프리체크 결과를 계획 수립 프롬프트에 주입하여 불필요한 Graph DB 검색 방지

**장점**:

- 불필요한 API 호출 감소
- 계획 수립 시 실제 데이터 존재 여부 기반 의사결정
- Graph DB 검색 효율성 향상

##### 의존성 주입 및 플레이스홀더 교체

**위치**: [orchestrator.py:824-871](multiagent-rag-system/backend/app/core/agents/orchestrator.py#L824-L871)

```python
# 파일 위치: multiagent-rag-system/backend/app/core/agents/orchestrator.py:824-871

def _inject_context_into_query(self, step_info: Dict, accumulated_context: Dict[int, str]) -> str:
    """이전 단계의 결과를 현재 단계의 쿼리에 주입"""
    query = step_info.get("query", "")

    # [step-X의 결과] 패턴 찾기
    pattern = r'\[step-(\d+)의 결과\]'
    matches = re.findall(pattern, query)

    for match in matches:
        step_num = int(match)
        if step_num in accumulated_context:
            # 이전 단계 결과로 치환
            placeholder = f"[step-{step_num}의 결과]"
            context_data = accumulated_context[step_num]
            query = query.replace(placeholder, context_data)

    return query
```

**의존성 주입 방식**:

- `[step-X의 결과]` 플레이스홀더를 실제 데이터로 치환
- 순차적 워크플로우에서 이전 단계 결과를 다음 단계에 전달
- 동적 쿼리 생성을 통한 컨텍스트 기반 검색

**예시**:
```
Step 1: "2024년 무 가격 동향" 검색
Step 2: "[step-1의 결과]를 바탕으로 가격 상승 원인 분석"
       → "2024년 무 가격은 전년 대비 15% 상승을 바탕으로 가격 상승 원인 분석"
```

##### 페르소나 기반 계획 커스터마이징

**위치**: [persona_prompts.json](multiagent-rag-system/backend/app/core/agents/prompts/persona_prompts.json)

```json
{
  "구매 담당자": {
    "description": "원가 절감과 품질 안정성에 집중하는 구매 담당자",
    "report_prompt": [
      "1. 원가와 시세 정보를 최우선으로 강조하세요.",
      "2. 수급 안정성과 공급망 리스크를 반드시 다루세요.",
      "3. 구체적인 숫자와 비교 데이터를 충분히 활용하세요.",
      "4. 실무적 의사결정에 도움이 되는 명확한 권장사항을 제시하세요."
    ],
    "chart_prompt": "원가 비교, 시세 변동, 공급량 추이 등을 시각화"
  },
  "급식 운영 담당자": {
    "description": "영양 균형과 원가, 직원·학생 만족도를 고려하는 급식 운영 담당자",
    "report_prompt": [
      "1. 영양학적 가치와 균형잡힌 식단 구성을 강조하세요.",
      "2. 원가 관리와 예산 효율성을 함께 고려하세요.",
      "3. 직원과 학생의 만족도 향상 방안을 제안하세요.",
      "4. 실제 급식 현장에 적용 가능한 구체적인 메뉴 아이디어를 포함하세요."
    ],
    "chart_prompt": "영양소 비교, 원가 대비 영양 효율, 만족도 조사 결과 등을 시각화"
  }
  // ... (이하 페르소나 생략) ...
}
```

**페르소나 시스템의 역할**:

- 5가지 페르소나별 맞춤형 분석 관점 제공
  - 구매 담당자: 원가, 시세, 수급 안정성 중점
  - 급식 운영 담당자: 영양 균형, 원가, 직원 만족도 중점
  - 마케팅 담당자: 시장 트렌드, 소비자 데이터, 경쟁사 분석
  - 제품 개발 연구원: 새로운 원료, 기술, 과학적 근거
  - 기본: 균형잡힌 종합 분석
- 계획 수립, 보고서 생성, 차트 작성 모두에 페르소나 관점 적용

#### 비동기 병렬 처리 최적화

##### Multi-RAG 병렬 검색

**위치**: [worker_agents.py:892-1011](multiagent-rag-system/backend/app/core/agents/worker_agents.py#L892-L1011)

```python
# 파일 위치: multiagent-rag-system/backend/app/core/agents/worker_agents.py:892-1011

async def execute_parallel(self, plan_steps: List[Dict], query: str) -> List[SearchResult]:
    """병렬 실행 단계들을 모아서 asyncio.gather로 한 번에 실행"""
    print(f"\n>> DataGatherer: execute_parallel 시작 (단계 수: {len(plan_steps)})")

    tasks = []
    for step in plan_steps:
        tool_name = step.get("tool")
        step_query = step.get("query")

        # Graph-to-Vector 모드 지원
        if tool_name == "graph_db_search" and step.get("mode") == "graph-to-vector":
            # Graph DB에서 관련 엔티티 추출 후 Vector DB 검색
            task = self._graph_to_vector_search(step_query)
        else:
            # 일반 도구 실행
            tool_func = self.available_tools.get(tool_name)
            if tool_func:
                task = tool_func(step_query)

        tasks.append(task)

    # 병렬 실행
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # 결과 병합 및 예외 처리
    all_results = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            print(f"  - 단계 {i+1} 실행 중 오류: {result}")
        else:
            all_results.extend(result)

    return all_results
```

**병렬 검색 메커니즘**:

- asyncio.gather를 사용한 동시 실행
- return_exceptions=True로 예외 격리
- Graph-to-Vector 모드 지원: Graph DB에서 엔티티 추출 후 Vector DB 검색

**장점**:

- 여러 데이터 소스에서 동시 검색
- 하나의 도구 실패가 전체 검색에 영향 주지 않음
- 검색 시간 효율 향상

##### ThreadPoolExecutor를 통한 비동기 실행

**위치**: [worker_agents.py:49-51](multiagent-rag-system/backend/app/core/agents/worker_agents.py#L49-L51)

```python
# 파일 위치: multiagent-rag-system/backend/app/core/agents/worker_agents.py:49-51

# 전역 ThreadPoolExecutor (앱 전체에서 재사용)
_global_executor = ThreadPoolExecutor(max_workers=10)
```

**사용 방식**:

```python
# 예시: RDB 검색 비동기 실행
loop = asyncio.get_event_loop()
search_results = await loop.run_in_executor(
    _global_executor,
    self.rdb_tool.search,
    query
)
```

**ThreadPoolExecutor 역할**:

- 동기 blocking I/O 작업을 비동기 환경에서 실행
- 전역 executor를 재사용하여 리소스 효율성 향상
- max_workers=10으로 동시 실행 제한

**적용 사례**:

- RDB 검색 (PostgreSQL)
- Web scraping
- 파일 I/O
- 외부 API 호출

##### 보고서 섹션별 병렬 생성

**위치**: [orchestrator.py:1219-1338](multiagent-rag-system/backend/app/core/agents/orchestrator.py#L1219-L1338)

```python
# 파일 위치: multiagent-rag-system/backend/app/core/agents/orchestrator.py:1219-1338 (일부 발췌)

# Producer-Consumer 패턴
section_queues = [asyncio.Queue() for _ in range(len(structure))]

async def _produce_section_content(section_index: int):
    """섹션 내용 생성 (Producer)"""
    section = structure[section_index]
    q = section_queues[section_index]

    try:
        async for chunk in self.processor.generate_section_streaming(
            section=section,
            full_data_dict=full_data_dict,
            original_query=query,
            use_indexes=section.get("use_indexes", []),
            awareness_context=awareness_context,
            state=state
        ):
            # Abort 체크
            if run_manager and run_manager.is_abort_requested(state.get("metadata", {}).get("run_id")):
                await q.put(None)
                return
            await q.put(chunk)
    except Exception as e:
        await q.put({"error": str(e)})
    finally:
        await q.put(None)  # 종료 신호

# 모든 섹션 Producer 시작
for i in range(len(structure)):
    asyncio.create_task(_produce_section_content(i))

# Consumer: 순차적으로 섹션 전송
for section_index, section in enumerate(structure):
    q = section_queues[section_index]

    while True:
        chunk = await q.get()
        if chunk is None:  # 종료 신호
            break

        # 차트 마커 감지 및 버퍼 관리
        if isinstance(chunk, str):
            buffer += chunk
            # [GENERATE_CHART] 마커 처리 로직
            # ... (생략) ...

        yield {"type": "content", "data": {"chunk": buffer}}
```

**Producer-Consumer 패턴**:

- Producer: 모든 섹션을 asyncio.create_task로 동시 생성
- Consumer: 섹션 순서대로 Queue에서 청크를 꺼내 전송
- asyncio.Queue를 사용한 섹션 간 통신

**주요 기능**:

- 섹션 병렬 생성으로 전체 보고서 생성 시간 단축
- 순차 전송으로 사용자에게 자연스러운 읽기 경험 제공
- 차트 생성 마커 `[GENERATE_CHART]` 감지 및 처리
- Abort 지원: 중단 요청 시 즉시 종료
- 예외 격리: 하나의 섹션 실패가 전체 보고서에 영향 주지 않음

#### 스트리밍 최적화

##### Server-Sent Events (SSE) 점진적 전송

**위치**: [main.py:640-648](multiagent-rag-system/backend/app/main.py#L640-L648)

```python
# 파일 위치: multiagent-rag-system/backend/app/main.py:640-648

def server_sent_event(event_type: str, data: dict) -> str:
    """SSE 형식으로 변환"""
    return f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

@app.post("/api/report/stream")
async def stream_report(request: ReportRequest):
    """보고서 생성 스트리밍 엔드포인트"""

    async def event_generator():
        async for event in orchestrator.execute_report_workflow(state):
            if event.get("type") == "content":
                # 콘텐츠 청크 전송
                yield server_sent_event("content", event["data"])
            elif event.get("type") == "status":
                # 상태 업데이트 전송
                yield server_sent_event("status", event["data"])

    return StreamingResponse(event_generator(), media_type="text/event-stream")
```

**SSE 스트리밍 방식**:

- `event: {type}\ndata: {json}\n\n` 형식으로 데이터 전송
- 데이터 생성 즉시 사용자에게 전달
- 프론트엔드는 청크 단위로 받아서 즉시 화면 렌더링

**이벤트 타입**:

- content: 보고서 본문 청크
- status: 진행 상태 업데이트
- chart: 차트 데이터
- full_data_dict: 전체 데이터 딕셔너리
- abort: 중단 알림

##### Abort 메커니즘

**위치**: [orchestrator.py:1013-1016](multiagent-rag-system/backend/app/core/agents/orchestrator.py#L1013-L1016)

```python
# 파일 위치: multiagent-rag-system/backend/app/core/agents/orchestrator.py:1013-1016

for i, step_info in enumerate(execution_steps):
    # Abort 체크
    if run_manager and run_manager.is_abort_requested(state.get("metadata", {}).get("run_id")):
        yield {"type": "abort", "data": {"message": "작업이 중단되었습니다"}}
        return
```

**중단 처리 메커니즘**:

- 각 단계 실행 전 중단 요청 확인
- 중단 요청 시 즉시 워크플로우 종료 및 사용자 알림
- 불필요한 계산 및 API 호출 방지로 리소스 절약
- run_manager를 통한 외부 실행 상태 관리

#### 캐싱 및 리소스 재사용

##### 모델 Lazy Loading & 캐싱

**위치**: [orchestrator.py:116-121](multiagent-rag-system/backend/app/core/agents/orchestrator.py#L116-L121)

```python
# 파일 위치: multiagent-rag-system/backend/app/core/agents/orchestrator.py:116-121

class OrchestratorAgent:
    def __init__(self):
        # 모델 Lazy Loading
        self.llm = ChatGoogleGenerativeAI(model="gemini-2.0-flash-lite", temperature=0.3)
        self.triage_agent = TriageAgent()
        self.data_gatherer = DataGathererAgent()
        self.processor = ProcessorAgent()
```

**캐싱 전략**:

- AI 모델은 앱 시작 시 한 번만 로드
- 이후 모든 요청에서 캐시된 모델 재사용
- 1.8GB 메모리를 효율적으로 사용
- DataGathererAgent와 ProcessorAgent도 한 번만 생성하여 재사용

**장점**:

- 요청마다 모델 로딩 오버헤드 제거
- 메모리 효율성 향상
- 응답 시간 단축

---

### 3.5.3 에이전트 구성요소별 상세

#### Triage Agent (요청 분류)

**위치**: [orchestrator.py:37-110](multiagent-rag-system/backend/app/core/agents/orchestrator.py#L37-L110)

**역할**: 사용자 요청을 분석하여 `chat` 또는 `task`로 분류

```python
# 파일 위치: multiagent-rag-system/backend/app/core/agents/orchestrator.py:37-110

class TriageAgent:
    """요청 분류 및 라우팅 담당 Agent"""

    def __init__(self, model: str = "gemini-2.5-flash-lite", temperature: float = 0.1):
        self.llm = ChatGoogleGenerativeAI(model=model, temperature=temperature)

    async def classify_request(self, user_message: str) -> str:
        """사용자 요청을 'chat' 또는 'task'로 분류"""

        prompt = f"""
다음 사용자의 메시지를 분석하여 'chat' 또는 'task' 중 하나로 분류하세요.

**분류 기준**:
- **task**: 상세한 조사가 필요한 요청 (보고서 생성)
  예: "무의 영양소와 효능 알려줘", "2024년 배추 가격 동향 분석해줘"
- **chat**: 간단한 대화나 인사
  예: "안녕", "고마워", "뭐 할 수 있어?"

사용자 메시지: "{user_message}"

응답 형식: {{"type": "chat"}} 또는 {{"type": "task"}}
"""

        response = await self.llm.ainvoke(prompt)
        result = json.loads(response.content)

        return result.get("type", "chat")
```

**분류 기준**:

- **task**: 상세한 조사가 필요한 요청 → 보고서 생성 워크플로우 실행
- **chat**: 간단한 대화나 인사 → 일반 채팅 응답

**시스템 통합**:

- TriageAgent의 분류 결과에 따라 `execute_report_workflow` 또는 일반 채팅 플로우 선택
- gemini-2.5-flash-lite 모델 사용으로 빠른 분류
- temperature=0.1로 일관성 있는 분류 보장

#### Orchestrator Agent (계획 수립 & 조율)

**위치**: [orchestrator.py:113-1338](multiagent-rag-system/backend/app/core/agents/orchestrator.py#L113-L1338)

**역할**:

- 전체 워크플로우 관리
- 동적 실행 계획 수립
- 에이전트 간 조율

##### 워크플로우 실행 (execute_report_workflow)

**위치**: [orchestrator.py:916-1115](multiagent-rag-system/backend/app/core/agents/orchestrator.py#L916-L1115)

```python
# 파일 위치: multiagent-rag-system/backend/app/core/agents/orchestrator.py:916-1115 (일부 발췌)

async def execute_report_workflow(self, state: StreamingAgentState, run_manager=None):
    """전체 보고서 생성 워크플로우 실행"""

    query = state.get("original_query", "")
    print(f"\n{'='*80}")
    print(f"[OrchestratorAgent] 보고서 생성 워크플로우 시작")
    print(f"  - 사용자 요청: {query}")
    print(f"{'='*80}\n")

    # 1. 메모리 컨텍스트 통합
    conversation_history = state.get("metadata", {}).get("conversation_history", [])
    memory_summary = self._generate_memory_summary_for_report(conversation_history, query)
    if memory_summary:
        print(f"\n>> 이전 대화 맥락 요약:\n{memory_summary}\n")

    # 2. 페르소나 확인
    selected_persona = state.get("persona")
    yield self._create_status_event("PLANNING", "PERSONA_CONFIRMED",
                                    f"선택된 페르소나: {selected_persona}")

    # 3. 누적 컨텍스트 초기화
    accumulated_context = {}
    accumulated_sections = []
    accumulated_charts = []
    accumulated_insights = []

    # 4. Graph DB 프리체크 (환경변수로 제어)
    disable_precheck = os.getenv("DISABLE_PRECHECK", "false").lower() == "true"
    if not disable_precheck:
        graph_probe = await self._probe_graph_data_locations(query)
        state["metadata"]["graph_probe"] = graph_probe

    # 5. 계획 수립
    yield self._create_status_event("PLANNING", "PLAN_GENERATION", "실행 계획 수립 중...")
    state = await self.generate_plan(state)

    # 6. 데이터 수집
    # ... (워크플로우 실행 로직) ...

    # 7. 전체 데이터 딕셔너리 생성 및 전송
    full_data_dict = {}
    for idx, data in enumerate(final_collected_data):
        full_data_dict[idx] = {
            "source": data.source,
            "title": data.title,
            "content": data.content,
            "url": data.url,
            "metadata": data.metadata
        }

    yield {"type": "full_data_dict", "data": {"data_dict": full_data_dict}}

    # 8. 보고서 구조 설계
    # ... (생략) ...

    # 9. 섹션 병렬 생성 및 순차 스트리밍
    # ... (생략) ...
```

**워크플로우 5단계**:

1. **메모리 컨텍스트 통합**: 이전 대화 히스토리 요약 후 보고서에 반영
2. **페르소나 확인**: 선택된 페르소나 검증 및 사용자 알림
3. **누적 컨텍스트 초기화**: 생성된 섹션, 차트, 인사이트 누적 관리
4. **Graph DB 프리체크**: `DISABLE_PRECHECK` 환경변수로 제어 가능
5. **계획 수립 → 데이터 수집 → 구조 설계 → 섹션 생성**

**주요 기능**:

- 전체 데이터 딕셔너리(full_data_dict)를 인덱스 기반으로 변환하여 프론트엔드 전송
- `[step-X의 결과]` 플레이스홀더를 실제 데이터로 치환하는 의존성 주입
- 각 단계마다 상태를 SSE로 실시간 스트리밍
- 각 단계 실행 전 Abort 요청 확인

#### DataGatherer Agent (데이터 수집)

**위치**: [worker_agents.py:54-1892](multiagent-rag-system/backend/app/core/agents/worker_agents.py#L54-L1892)

**역할**: Multi-RAG 데이터 수집 및 검색 최적화

**지원 검색 도구 (7개)**:

1. **web_search**: 최신 정보 및 시사 뉴스
2. **vector_db_search**: Elasticsearch 기반 문서 검색
3. **graph_db_search**: Neo4j 기반 관계 탐색
4. **rdb_search**: PostgreSQL 기반 정형 데이터 조회
5. **arxiv_search**: 학술 논문 검색
6. **pubmed_search**: 의학 논문 검색
7. **scrape_content**: URL 콘텐츠 스크래핑

**핵심 구현**:

```python
# 파일 위치: multiagent-rag-system/backend/app/core/agents/worker_agents.py:68-85

class DataGathererAgent:
    def __init__(self):
        # 3단계 Fallback: Gemini Key 1 → Gemini Key 2 → OpenAI
        self.llm = self._create_llm_with_fallback()

        # 도구 초기화
        self.vector_tool = VectorSearchTool()
        self.graph_tool = GraphSearchTool()
        self.rdb_tool = RDBSearchTool()
        # ... (기타 도구) ...

        # 도구 매핑
        self.available_tools = {
            "web_search": self._web_search,
            "vector_db_search": self._vector_db_search,
            "graph_db_search": self._graph_db_search,
            "arxiv_search": self._arxiv_search,
            "pubmed_search": self._pubmed_search,
            "rdb_search": self._rdb_search,
            "scrape_content": self._scrape_content,
        }
```

**시스템 특징**:

- **3단계 Fallback 메커니즘**: Gemini Key 1 → Gemini Key 2 → OpenAI로 안정적 서비스 제공
- **7개 도구 통합 관리**: 하나의 Agent에서 모든 검색 도구 관리
- **표준화된 인터페이스**: 모든 도구가 `List[SearchResult]` 반환
- **도구 매핑**: 도구 이름을 메서드와 매핑하여 동적 호출 가능
- **asyncio.gather를 통한 병렬 실행**: 여러 도구 동시 실행으로 효율적 데이터 수집

#### Processor Agent (보고서 생성)

**위치**: [worker_agents.py:1894-3656](multiagent-rag-system/backend/app/core/agents/worker_agents.py#L1894-L3656)

**역할**:

- 보고서 구조 설계
- 섹션별 내용 생성
- 차트 생성

##### 보고서 구조 설계

**위치**: [worker_agents.py:2064-2100](multiagent-rag-system/backend/app/core/agents/worker_agents.py#L2064-L2100)

```python
# 파일 위치: multiagent-rag-system/backend/app/core/agents/worker_agents.py:2064-2100

async def _design_report_structure(self, data: List[SearchResult], selected_indexes: List[int],
                                   query: str, state: Optional[Dict[str, Any]] = None):
    """보고서 구조 설계 + 섹션별 사용할 데이터 인덱스 선택"""

    print(f"\n>> 보고서 구조 설계 시작:")
    print(f"  - 전체 데이터 개수: {len(data)}")
    print(f"  - 선택된 인덱스: {selected_indexes}")

    # 페르소나 정보 추출
    persona_name = state.get("persona", "기본") if state else "기본"
    persona_info = self.personas.get(persona_name, {})

    # 구조 설계 프롬프트
    structure_prompt = f"""
당신은 전문 리서치 리포트 구조 설계자입니다.
수집된 데이터를 바탕으로 '{persona_name}' 관점의 보고서 구조를 설계하세요.

**페르소나**: {persona_name}
**사용자 질문**: {query}
**수집된 데이터 개수**: {len(data)}

... (프롬프트 생략) ...
"""

    # LLM 호출하여 구조 설계
    response = await self.llm_pro.ainvoke(structure_prompt)
    structure = json.loads(response.content)

    return structure
```

**구조 설계 특징**:

- 선택된 페르소나에 따라 보고서 구조 차별화
- 각 섹션이 사용할 데이터를 인덱스로 명시하여 중복 방지
- 데이터 특성 분석하여 차트 생성 필요 여부 판단
- Gemini 2.5 Pro 모델 사용으로 고품질 구조 설계

##### 섹션 스트리밍 생성

**위치**: [worker_agents.py:2492-2700+](multiagent-rag-system/backend/app/core/agents/worker_agents.py#L2492-L2700)

```python
# 파일 위치: multiagent-rag-system/backend/app/core/agents/worker_agents.py:2492-2700+

async def generate_section_streaming(
    self,
    section: Dict[str, Any],
    full_data_dict: Dict[int, Dict],
    original_query: str,
    use_indexes: List[int],
    awareness_context: str = "",
    state: Optional[Dict[str, Any]] = None
) -> AsyncGenerator[str, None]:
    """페르소나, 전체 구조 인지(awareness_context), 섹션 목표(description)를 반영하여 스트리밍 생성"""

    section_title = section.get("section_title", "제목 없음")
    content_type = section.get("content_type", "synthesis")
    description = section.get("description", "이 섹션의 내용을 요약합니다.")

    # 1. 섹션 제목 중복 체크
    # ... (로직 생략) ...

    # 2. full_data_dict에서 해당 섹션의 데이터만 추출
    section_data = []
    for idx in use_indexes:
        if idx in full_data_dict:
            section_data.append(full_data_dict[idx])

    # 3. 페르소나 프롬프트 생성
    persona_name = state.get("persona", "기본") if state else "기본"
    persona_guidelines = self.personas.get(persona_name, {}).get("report_prompt", [])

    # 4. 섹션 생성 프롬프트 (Awareness Context 포함)
    section_prompt = f"""
당신은 '{persona_name}' 관점의 전문 리서치 리포트 작성자입니다.

**전체 보고서 구조 (중복 방지용)**:
{awareness_context}

**현재 작성할 섹션**:
- 제목: {section_title}
- 목표: {description}

**페르소나 가이드라인**:
{chr(10).join(f'  {g}' for g in persona_guidelines)}

**노션 스타일 마크다운 지침**:
- 모든 문단에 **굵은 글씨** 2개 이상, *기울임체* 1개 이상 필수
- 비교 정보 3개 이상 시 마크다운 테이블 사용 필수
- 핵심 인사이트는 블록쿼트(>) 사용

**SOURCE 출처 표기 시스템**:
- 데이터 인덱스 번호를 기반으로 [SOURCE:숫자] 형식으로 출처 표기
- 반드시 할당된 인덱스 번호만 사용
- 존재하지 않는 번호 사용 금지

... (프롬프트 생략) ...
"""

    # 5. 스트리밍 생성
    async for chunk in self.llm_pro.astream(section_prompt):
        if chunk.content:
            yield chunk.content
```

**섹션 생성 주요 기능**:

- **섹션 제목 중복 체크**: 보고서 제목과 섹션 제목 유사 시 제목 출력 생략
- **full_data_dict 기반 데이터 매핑**: 인덱스 기반 데이터 딕셔너리에서 할당된 인덱스의 데이터만 추출
- **Awareness Context**: 전체 보고서 구조를 프롬프트에 포함하여 섹션 간 내용 중복 방지

**노션 스타일 마크다운 지침**:

- 모든 문단에 **굵은 글씨** 2개 이상, *기울임체* 1개 이상 필수
- 비교 정보 3개 이상 시 마크다운 테이블 사용 필수
- 핵심 인사이트는 블록쿼트(`>`) 사용

**SOURCE 출처 표기 시스템**:

- 데이터 인덱스 번호 기반 [SOURCE:숫자] 형식 사용
- 반드시 할당된 인덱스 번호만 사용하도록 강제
- 존재하지 않는 번호 사용 금지

**스트리밍 방식**:

- 페르소나 report_prompt에 따라 말투 및 분석 관점 유지
- Gemini 2.5 Pro의 astream() 사용하여 생성 즉시 청크 단위 전송
- 참고 데이터의 구체적 수치, 사실, 인용구 적극 활용

---

### 3.5.4 페르소나 기반 보고서 생성

#### 페르소나 정의

**파일 위치**: [persona_prompts.json](multiagent-rag-system/backend/app/core/agents/prompts/persona_prompts.json)

5가지 페르소나 정의 및 각 페르소나별 `description`, `report_prompt`, `chart_prompt` 3가지 속성 보유:

**1. 구매 담당자**

- **설명**: 원가 절감과 품질 안정성에 집중하는 구매 담당자
- **보고서 가이드라인**:
  - 원가와 시세 정보 최우선 강조
  - 수급 안정성과 공급망 리스크 필수 포함
  - 구체적 숫자와 비교 데이터 충분히 활용
  - 실무적 의사결정에 도움되는 명확한 권장사항 제시
- **차트 지침**: 원가 비교, 시세 변동, 공급량 추이 등 시각화

**2. 급식 운영 담당자**

- **설명**: 영양 균형과 원가, 직원·학생 만족도를 고려하는 급식 운영 담당자
- **보고서 가이드라인**:
  - 영양학적 가치와 균형잡힌 식단 구성 강조
  - 원가 관리와 예산 효율성 함께 고려
  - 직원과 학생의 만족도 향상 방안 제안
  - 실제 급식 현장에 적용 가능한 구체적 메뉴 아이디어 포함
- **차트 지침**: 영양소 비교, 원가 대비 영양 효율, 만족도 조사 결과 등 시각화

**3. 마케팅 담당자**

- **설명**: 소비 트렌드와 고객 니즈 파악에 집중하는 마케팅 담당자
- **보고서 가이드라인**:
  - 시장 트렌드와 소비자 행동 데이터 중점 분석
  - 경쟁사 동향 및 차별화 포인트 도출
  - 타겟 고객층별 니즈와 선호도 분석
  - 실행 가능한 마케팅 전략 및 캠페인 아이디어 제시
- **차트 지침**: 시장 점유율, 소비 트렌드, 고객 선호도, 경쟁사 비교 등 시각화

**4. 제품 개발 연구원**

- **설명**: 신제품 개발과 기술 혁신을 추구하는 연구원
- **보고서 가이드라인**:
  - 새로운 원료, 기술, 공법 등 혁신 요소 탐색
  - 과학적 근거와 연구 데이터 기반 분석
  - 제품 개선 가능성 및 차별화 요소 도출
  - 실험 가능한 구체적 개발 방향 제시
- **차트 지침**: 성분 비교, 기술 트렌드, 연구 결과 데이터 등 시각화

**5. 기본**

- **설명**: 균형잡힌 시각으로 전반적인 분석을 제공하는 일반 분석가
- **보고서 가이드라인**:
  - 객관적이고 균형잡힌 분석 유지
  - 다양한 관점 고려하여 종합적 정보 제공
  - 데이터 기반 사실 위주 서술
  - 명확하고 이해하기 쉬운 구조로 작성
- **차트 지침**: 주요 데이터를 효과적으로 시각화

#### 페르소나 활용 지점

페르소나는 시스템 전체에 걸쳐 활용됨:

1. **계획 수립 단계** (generate_plan):
   - 페르소나별 분석 관점 반영
   - 페르소나 설명을 프롬프트에 주입

2. **보고서 구조 설계** (_design_report_structure):
   - 페르소나에 따라 섹션 구성 차별화
   - 페르소나별 중요도에 따른 섹션 우선순위

3. **섹션 생성** (generate_section_streaming):
   - 페르소나의 report_prompt 4가지 가이드라인 적용
   - 페르소나별 말투 및 분석 깊이 조정

4. **차트 생성** (_create_charts):
   - 페르소나의 chart_prompt에 따른 시각화 스타일

---

### 3.5.5 리서치 리포트 구조 및 출처관리

#### SearchResult 모델 (출처 관리)

**위치**: [models.py:39-52](multiagent-rag-system/backend/app/core/models/models.py#L39-L52)

```python
# 파일 위치: multiagent-rag-system/backend/app/core/models/models.py:39-52

class SearchResult(BaseModel):
    """검색 결과 표준 형식"""
    source: str = Field(description="데이터 소스 (web, vector_db, graph_db, rdb 등)")
    title: str = Field(description="검색 결과 제목")
    content: str = Field(description="검색 결과 본문")
    url: Optional[str] = Field(default=None, description="원본 URL")
    score: float = Field(default=0.0, description="관련성 점수")
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())
    metadata: Dict[str, Any] = Field(default_factory=dict)
```

**SearchResult 모델 역할**:

- 모든 검색 도구가 동일한 형식으로 결과 반환하도록 표준화된 인터페이스 제공
- source, title, url 등을 통해 정보 출처 명확히 기록
- 추가 출처 정보는 metadata 필드에 저장

#### SourceInfo 모델

**위치**: [models.py:145-174](multiagent-rag-system/backend/app/core/models/models.py#L145-L174)

```python
# 파일 위치: multiagent-rag-system/backend/app/core/models/models.py:145-172

class SourceInfo(BaseModel):
    """출처 정보 상세 모델"""
    title: str = Field(description="문서 제목")
    url: Optional[str] = Field(default=None, description="원본 URL")
    author: Optional[str] = Field(default=None, description="작성자")
    organization: Optional[str] = Field(default=None, description="기관/회사명")
    published_date: Optional[str] = Field(default=None, description="발행일")
    access_date: str = Field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d"))
    document_type: str = Field(default="web", description="문서 타입")
    reliability_score: float = Field(default=0.8, ge=0.0, le=1.0, description="신뢰도 점수")

    def to_citation(self) -> str:
        """학술적 인용 형식 자동 생성"""
        citation_parts = []
        if self.author:
            citation_parts.append(f"{self.author}")
        if self.organization:
            citation_parts.append(f"{self.organization}")
        citation_parts.append(f"\"{self.title}\"")
        if self.published_date:
            citation_parts.append(f"({self.published_date})")
        if self.url:
            citation_parts.append(f"Retrieved from {self.url}")
        return ", ".join(citation_parts)
```

**SourceInfo 모델 특징**:

- 저자, 기관, 발행일, 신뢰도 등 상세한 출처 정보 기록
- `to_citation()` 메서드를 통해 학술적 인용 형식 자동 생성
- 0.0~1.0 범위의 신뢰도 점수로 출처 신뢰성 평가

---

### 3.5.6 외부 도구 및 Multi-RAG 연동

#### Multi-RAG 아키텍처 개요

본 시스템은 **7개의 이기종 데이터 소스** 통합 검색:

```
사용자 쿼리
    ↓
[DataGathererAgent]
    ├─ Web Search (실시간 정보)
    ├─ Vector DB (Elasticsearch - 문서)
    ├─ Graph DB (Neo4j - 관계)
    ├─ RDB (PostgreSQL - 정형 데이터)
    ├─ PubMed (의학 논문)
    ├─ Arxiv (학술 논문)
    └─ Scrape Content (URL 크롤링)
        ↓
[RRF 알고리즘으로 결과 융합]
        ↓
[ProcessorAgent로 보고서 생성]
```

**각 데이터 소스별 역할**:

- **Web Search**: 최신 뉴스, 트렌드, 시사 정보
- **Vector DB (Elasticsearch)**: 문서 유사도 기반 검색 (Dense + Sparse Hybrid)
- **Graph DB (Neo4j)**: 엔티티 간 관계 탐색 (IS_FROM, HAS_NUTRIENTS 등)
- **RDB (PostgreSQL)**: 농수축산물 시세 정보 등 정형 데이터 조회
- **PubMed**: 의학, 영양학 관련 학술 논문
- **Arxiv**: 과학, 기술 관련 학술 논문
- **Scrape Content**: 특정 URL의 콘텐츠 추출

#### RRF (Reciprocal Rank Fusion) 알고리즘

**위치**: Elasticsearch Hybrid 검색 내부

```python
# RRF 알고리즘 개념 코드

def reciprocal_rank_fusion(dense_results, sparse_results, k=60):
    """
    RRF 공식: score = Σ 1/(k + rank)

    - dense_results: 의미 기반 검색 결과 (순위별)
    - sparse_results: 키워드 기반 검색 결과 (순위별)
    - k: 기본값 60, 순위 간 차이 완화 파라미터
    """

    scores = {}

    # Dense 검색 결과 점수 계산
    for rank, doc in enumerate(dense_results, start=1):
        doc_id = doc['_id']
        scores[doc_id] = scores.get(doc_id, 0) + 1/(k + rank)

    # Sparse 검색 결과 점수 계산
    for rank, doc in enumerate(sparse_results, start=1):
        doc_id = doc['_id']
        scores[doc_id] = scores.get(doc_id, 0) + 1/(k + rank)

    # 점수 기준 정렬
    fused_list = sorted(scores.items(), key=lambda x: x[1], reverse=True)

    return fused_list
```

**RRF 알고리즘 특징**:

- Hybrid 검색: Dense(의미 기반) + Sparse(키워드 기반) 결과 통합
- RRF 공식 `score = Σ 1/(k + rank)`를 사용하여 각 검색 방법의 순위 조합
- K 파라미터 기본값 60으로 순위 간 차이 완화
- 여러 검색 방법에서 높은 순위를 받은 문서가 최종적으로 높은 점수 획득

#### 도구별 연동 인터페이스

모든 검색 도구는 표준화된 인터페이스로 연동:

```python
# 일반적인 도구 연동 패턴

async def _tool_name_search(self, query: str) -> List[SearchResult]:
    """도구별 검색 메서드"""
    try:
        # ThreadPoolExecutor를 통한 비동기 실행
        loop = asyncio.get_event_loop()
        search_results = await loop.run_in_executor(
            _global_executor,
            tool_function,
            query
        )

        # SearchResult 형식으로 변환
        return [
            SearchResult(
                source="tool_name",
                title=result.title,
                content=result.content,
                url=result.url,
                score=result.score,
                metadata=result.metadata
            )
            for result in search_results
        ]
    except Exception as e:
        print(f"[{tool_name}] 검색 오류: {e}")
        return []
```

**도구 연동 표준 패턴**:

- ThreadPoolExecutor를 통한 blocking I/O 비동기 실행
- 모든 도구가 `List[SearchResult]` 형식으로 결과 반환
- 예외 발생 시 빈 리스트 반환으로 전체 검색 프로세스 보호
- metadata에 도구별 추가 정보 저장 (스코어, 타임스탬프 등)

---

## 마무리

본 문서는 Multi-Agent RAG 시스템의 핵심 아키텍처와 구현 상세를 다룸.

### 핵심 특징 요약

1. **4개 전문 에이전트**: Triage, Orchestrator, DataGatherer, Processor
2. **동적 워크플로우**: 페르소나 기반 계획 수립 및 의존성 자동 해결
3. **병렬 처리 최적화**: asyncio.gather + ThreadPoolExecutor를 활용한 효율적인 병렬 실행
4. **실시간 스트리밍**: SSE를 통한 점진적 전송 및 Abort 메커니즘
5. **Multi-RAG 통합**: 7개 데이터 소스 통합 및 RRF 기반 결과 융합
6. **페르소나 시스템**: 5가지 역할별 맞춤형 보고서 생성

### 주요 파일 위치

- **Orchestrator Agent**: [orchestrator.py](multiagent-rag-system/backend/app/core/agents/orchestrator.py)
- **Worker Agents**: [worker_agents.py](multiagent-rag-system/backend/app/core/agents/worker_agents.py)
- **Data Models**: [models.py](multiagent-rag-system/backend/app/core/models/models.py)
- **Persona Prompts**: [persona_prompts.json](multiagent-rag-system/backend/app/core/agents/prompts/persona_prompts.json)
- **Main API**: [main.py](multiagent-rag-system/backend/app/main.py)

---

**문서 버전**: 2.0
**최종 업데이트**: 2025-11-14
**작성자**: AI 시스템 아키텍처 팀
