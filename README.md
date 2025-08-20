# Crowdworks Multiagent RAG System

크롤링, 벡터 데이터베이스, 그래프 데이터베이스를 활용한 Multi-Agent RAG (Retrieval-Augmented Generation) 시스템입니다.

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

- **멀티 에이전트 시스템**: LangGraph 기반 워크플로우
- **RAG (Retrieval-Augmented Generation)**: 다중 데이터소스 검색
- **실시간 웹 크롤링**: 농식품 관련 데이터 수집
- **벡터 검색**: Elasticsearch 기반 의미론적 검색
- **그래프 검색**: Neo4J 기반 관계형 데이터 분석
- **PDF 리포트 생성**: 자동화된 보고서 생성

## 빠른 시작

### 1. 환경 설정

```bash
# 저장소 클론
git clone https://github.com/danlee-dev/crowdworks-multiagent-system.git
cd crowdworks-multiagent-system

# 환경변수 설정
cp .env.example multiagent-rag-system/backend/.env
# .env 파일을 열어서 API 키들을 설정하세요
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

- `OPENAI_API_KEY`: OpenAI API 키
- `GOOGLE_API_KEY`: Google API 키  
- `SERPER_API_KEY`: Serper 웹 검색 API 키
- `LANGSMITH_API_KEY`: LangSmith 추적용 API 키
- `COHERE_API_KEY`: Cohere API 키

## 기여하기

1. 이슈를 생성하여 개선사항이나 버그를 보고해주세요
2. Pull Request를 통해 코드 기여를 환영합니다
3. 개발 가이드라인을 준수해주세요

## 라이센스

이 프로젝트는 MIT 라이센스 하에 배포됩니다.