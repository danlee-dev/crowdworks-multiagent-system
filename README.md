# Crowdworks Multi-Agent RAG System v5.0 (Enterprise Edition)

## Overview
크라우드웍스의 산학 프로젝트로 개발된 차세대 B2B AI Agent 시스템입니다. **Gemini API 우선 폴백 시스템**과 **3단계 API 키 관리**를 통해 비용을 최적화하면서 안정적인 서비스를 제공합니다.

## Team Members
- **이성민**: AI Agent 아키텍처 설계 및 백엔드 개발
- **김민재**: 프론트엔드 UI/UX 개발 및 실시간 스트리밍 시스템
- **김희은**: 데이터 파이프라인 구축 및 벡터 데이터베이스 최적화
- **강민선**: 크롤링 시스템 개발 및 데이터 전처리
- **이동영**: Neo4j 그래프 데이터베이스 설계 및 관계형 데이터 분석

## 주요 특징 (v5.0)
- **3단계 API 폴백 시스템**: Gemini Key1 → Gemini Key2 → OpenAI 순차 시도로 비용 최적화
- **통합 환경 변수 관리**: 중앙화된 .env 파일로 모든 서비스 설정 관리
- **Custom AFLOW 아키텍처**: 동적 계획 수립 및 실행
- **실시간 스트리밍**: Claude 스타일 검색 결과 및 보고서 생성
- **다중 모델 지원**: Gemini 1.5 Pro (2M 컨텍스트), Gemini 2.5 시리즈 (1M 컨텍스트)
- **Docker 볼륨 최적화**: utils 폴더 공유로 모든 컨테이너에서 공통 모듈 접근

## 시스템 구성

```
crowdworks-multiagent-system/
├── multiagent-rag-system/     # 메인 AI 애플리케이션 (Frontend + Backend)
├── crawler_rdb/               # 크롤러 및 PostgreSQL 데이터베이스
├── elasticsearch/             # Elasticsearch 벡터 데이터베이스
├── Neo4J/                     # Neo4J 그래프 데이터베이스
├── docker-compose.yml         # 전체 시스템 통합 실행
└── README.md                  # 이 파일
```

## 주요 기능

### 💰 비용 최적화
- **3단계 API 폴백**: Gemini API 우선 사용으로 OpenAI 대비 최대 90% 비용 절감
- **스마트 모델 선택**: 작업별 최적 모델 자동 선택 (Gemini 2.5-pro, 2.5-flash, 2.5-flash-lite, 1.5-pro)

### 🤖 AI 에이전트 시스템
- **멀티 에이전트 워크플로우**: LangGraph 기반 동적 실행 계획
- **RAG (Retrieval-Augmented Generation)**: 다중 데이터소스 통합 검색
- **실시간 스트리밍**: Claude 스타일 UI로 검색 과정 실시간 표시

### 📊 데이터 통합
- **실시간 웹 크롤링**: 농식품 관련 최신 데이터 자동 수집
- **벡터 검색**: Elasticsearch 기반 의미론적 문서 검색
- **그래프 검색**: Neo4j 기반 관계형 데이터 분석
- **구조화된 데이터**: PostgreSQL 기반 정형 데이터 관리

## 빠른 시작

### 1. 환경 설정

```bash
# 저장소 클론
git clone https://github.com/danlee-dev/crowdworks-multiagent-system.git
cd crowdworks-multiagent-system

# 통합 환경변수 설정
cp .env.example .env
# 3단계 API 키 설정:
# GEMINI_API_KEY_1=your_gemini_api_key_here  # 1차 시도
# GEMINI_API_KEY_2=your_backup_gemini_key_here  # 2차 시도
# OPENAI_API_KEY=your-openai-key                              # 최종 폴백
```

### 2. 전체 시스템 실행

```bash
# 모든 서비스 실행
docker-compose up -d

# 로그 확인
docker-compose logs -f
```

### 3. 서비스 접속

- **메인 애플리케이션**: http://localhost:3000
- **백엔드 API**: http://localhost:8000
- **Elasticsearch**: http://localhost:9200
- **Kibana**: http://localhost:5601
- **Neo4J Browser**: http://localhost:7474

## 개별 서비스 설명

### MultiAgent RAG System
- **Frontend**: Next.js 기반 웹 인터페이스
- **Backend**: FastAPI 기반 API 서버
- **Agents**: 데이터 수집, 분석, 리포트 생성 에이전트

### Crawler RDB
- **PostgreSQL**: 크롤링된 데이터 저장
- **Crawler**: 농식품 관련 웹사이트 크롤링

### Elasticsearch
- **벡터 데이터베이스**: 문서 임베딩 저장 및 검색
- **Kibana**: 데이터 시각화 도구

### Neo4J
- **그래프 데이터베이스**: 관계형 데이터 저장
- **Graph Data Science**: 그래프 알고리즘 지원

## 개발 환경

### 개별 서비스 개발
```bash
# 백엔드만 개발할 때
cd multiagent-rag-system/backend
docker-compose up -d postgres elasticsearch neo4j
python -m uvicorn app.main:app --reload

# 프론트엔드만 개발할 때
cd multiagent-rag-system/frontend
npm run dev
```

### 로그 확인
```bash
# 전체 로그
docker-compose logs -f

# 특정 서비스 로그
docker-compose logs -f backend
docker-compose logs -f elasticsearch
```

## 문제 해결

### 1. 포트 충돌
기본 포트가 사용 중이면 docker-compose.yml에서 포트 번호를 변경하세요.

### 2. 메모리 부족
Elasticsearch가 메모리 부족으로 실행되지 않으면:
```bash
# Linux/Mac에서
sudo sysctl -w vm.max_map_count=262144
```

### 3. 권한 문제
```bash
# 볼륨 권한 설정
sudo chown -R $USER:$USER ./Neo4J/data ./postgresql
```

## 환경변수 설정

`.env` 파일에서 다음 항목들을 설정해야 합니다:

- `GEMINI_API_KEY_1`: Gemini API 키 (1차 폴백)
- `GEMINI_API_KEY_2`: Gemini API 키 (2차 폴백)
- `OPENAI_API_KEY`: OpenAI API 키 (최종 폴백)
- `SERPER_API_KEY`: Serper 웹 검색 API 키
- `LANGSMITH_API_KEY`: LangSmith 추적용 API 키
- `COHERE_API_KEY`: Cohere API 키

## API 사용 예시

### 3단계 폴백 시스템 사용

```python
from utils.model_fallback import ModelFallbackManager

# LangChain 모델 폴백 사용
response = ModelFallbackManager.try_invoke_with_fallback(
    prompt="농산품 가격 동향을 분석해주세요",
    gemini_model="gemini-2.5-flash",  # 1차: Gemini 2.5 Flash
    openai_model="gpt-4o-mini"        # 3차: OpenAI 폴백
)

# OpenAI SDK 직접 사용
response = ModelFallbackManager.try_openai_with_fallback(
    messages=[{"role": "user", "content": "질문"}],
    model="gpt-4o-mini"
)
```

### 스트리밍 응답

```python
# 스트리밍으로 응답 받기
for chunk in ModelFallbackManager.try_invoke_with_fallback(
    prompt="농산품 시장 분석",
    stream=True
):
    print(chunk, end="")
```

## 버전 히스토리

### v5.0.0 (Enterprise Edition) - 2024년 12월
- **주요 변경사항**:
  - 3단계 API 폴백 시스템 도입 (Gemini Key1 → Gemini Key2 → OpenAI)
  - 통합 환경변수 관리 (.env 중앙화)
  - Docker 볼륨 최적화로 utils 폴더 공유
  - Git 저장소 정리 (3,749개 불필요한 파일 제거)
- **비용 최적화**: Gemini API 우선 사용으로 최대 90% 비용 절감
- **안정성 향상**: 다중 API 키 폴백으로 서비스 중단 방지
- **개발 효율성**: 중앙화된 model_fallback.py로 일관된 API 관리

### v4.x - 이전 버전
- **v4.2**: Neo4j 그래프 데이터베이스 최적화
- **v4.1**: Elasticsearch 벡터 검색 성능 개선
- **v4.0**: Custom AFLOW 아키텍처 도입

### v3.x - 이전 버전
- **v3.1**: 실시간 스트리밍 UI 구현
- **v3.0**: LangGraph 기반 멀티 에이전트 시스템

### v2.x - 이전 버전
- **v2.1**: 웹 크롤링 시스템 구축
- **v2.0**: RAG 시스템 기본 구조 완성

### v1.x - 초기 버전
- **v1.1**: 프론트엔드 UI 개발
- **v1.0**: 프로젝트 초기 설정

## 개발 브랜치 관리

### 브랜치 구조
- `main`: 프로덕션 안정 버전
- `develop/v5.0.0`: v5.0 개발 브랜치
- `feature/*`: 기능 개발 브랜치
- `hotfix/*`: 긴급 수정 브랜치

### 개발 워크플로우
```bash
# 개발 브랜치로 전환
git checkout develop/v5.0.0

# 새 기능 개발
git checkout -b feature/new-feature
# 개발 완료 후
git checkout develop/v5.0.0
git merge feature/new-feature

# 프로덕션 배포
git checkout main
git merge develop/v5.0.0
git tag v5.0.0
```

## 성능 최적화

### 모델 선택 가이드
- **대용량 문서 처리**: Gemini 1.5 Pro (2M 컨텍스트)
- **일반적인 쿼리**: Gemini 2.5 Flash (1M 컨텍스트, 빠른 응답)
- **간단한 작업**: Gemini 2.5 Flash Lite (경량화)
- **OpenAI 호환**: 최종 폴백으로만 사용

### 비용 최적화 팁
```python
# 작업에 따른 모델 선택
light_tasks = ModelFallbackManager.try_invoke_with_fallback(
    prompt=prompt,
    gemini_model="gemini-2.5-flash-lite"  # 가장 경제적
)

heavy_tasks = ModelFallbackManager.try_invoke_with_fallback(
    prompt=long_document,
    gemini_model="gemini-1.5-pro"  # 대용량 처리
)
```

## 기여하기

1. 이슈를 생성하여 개선사항이나 버그를 보고해주세요
2. Pull Request를 통해 코드 기여를 환영합니다
3. 개발 가이드라인을 준수해주세요

## 라이센스

이 프로젝트는 MIT 라이센스 하에 배포됩니다.
