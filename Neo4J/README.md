# Neo4J 지식 그래프 구축 시스템

이 디렉토리는 농식품 관련 문서에서 엔터티와 관계를 추출하여 Neo4J 지식 그래프를 구축하는 시스템입니다.

## 📁 파일 구조

```
Neo4J/
├── app/                          # Neo4J 연결 및 쿼리 앱
│   ├── Dockerfile               # 앱 컨테이너 설정
│   ├── main.py                  # 메인 실행 파일
│   ├── neo4j_query.py          # Neo4J 쿼리 유틸리티
│   └── requirements.txt         # Python 의존성
├── docker-compose.yml           # Neo4J & 앱 컨테이너 설정
├── extracted_graph/             # 추출된 그래프 데이터 (CSV) <- 실제 사용
├── extracted_graph0/            # 그래프 추출 결과 (버전 0)
├── extracted_graph1/            # 그래프 추출 결과 (버전 1)
├── import/                      # Neo4J 가져오기용 CSV 파일
├── graph_extract2.py           # 통합 그래프 추출 스크립트
├── merge_csv.py                # CSV 파일 병합 스크립트
├── preprocess_file.py          # JSON → TXT 전처리 스크립트
├── scheduler.py                # 전체 파이프라인 스케줄러
└── README.md                   # 이 파일
```

## 🚀 시작하기

### 1. 환경 설정

```bash
# 환경변수 설정 (.env 파일 생성)
NEO4J_PASSWORD=your_password_here
```

### 2. Neo4J 및 앱 실행

```bash
# Neo4J와 앱 컨테이너 시작
docker-compose up -d

# Neo4J 브라우저 접속
# http://localhost:7474
# 사용자명: neo4j
# 비밀번호: ${NEO4J_PASSWORD}
```

### 3. 데이터 처리 파이프라인

#### 방법 1: 통합 스크립트 실행 (권장)
```bash
python scheduler.py
```

#### 방법 2: 단계별 실행
```bash
# 1단계: JSON → TXT 변환
python preprocess_file.py

# 2단계: TXT → CSV 그래프 추출
python graph_extraction.py

# 3단계: CSV 병합
python merge_csv.py

# 4단계: Neo4J 로드 (수동)
# Neo4J 브라우저에서 Cypher 쿼리 실행
```

## 📊 시스템 워크플로우

### 1. 데이터 전처리 (`preprocess_file.py`)

- **입력**: `../elasticsearch/preprocessed_datas/*.json`
- **출력**: `./report_data/*.txt`
- **기능**:
  - JSON 문서를 텍스트로 변환
  - 파일명 정규화 (특수문자 제거)
  - 첫 번째 페이지는 제목 포함, 나머지는 제목 제거
  - 중복 파일 스킵

### 2. 그래프 추출 (`graph_extract2.py`)

#### 한국어 특화 추출 (`graph_extract2.py`)
- **모델**: Gemini/OpenAI Fallback 시스템
- **출력 형식**: CSV (엔터티1, 엔터티1유형, 관계, 엔터티2, 엔터티2유형, 속성)
- **특징**:
  - 한국어 농식품 도메인 특화
  - 시간, 수량, 국가 정보 포함
  - 문서 제목 자동 추가

### 3. 통합 파이프라인 (`scheduler.py`)

전체 프로세스를 자동화하는 스케줄러:

1. **JSON → TXT 변환**
2. **TXT → CSV 그래프 추출** 
3. **CSV 병합 및 정리**
4. **Neo4J 자동 로드**

### 4. CSV 병합 (`merge_csv.py`)

- 개별 CSV 파일들을 하나로 통합
- 문서 제목 컬럼 추가
- 필수 컬럼 검증 및 정리
- Neo4J 가져오기 형식으로 저장

## 🔧 Neo4J 연결 및 쿼리

### 연결 설정

```python
from app.neo4j_query import run_cypher

# 기본 연결 (환경변수 사용)
# NEO4J_URI: bolt://localhost:7687
# NEO4J_USER: neo4j  
# NEO4J_PASSWORD: 환경변수에서 읽음
```

### 쿼리 예시

```python
# 전체 노드 수 확인
result = run_cypher("MATCH (n) RETURN count(n) AS total_nodes")

# 엔터티 타입별 분포
result = run_cypher("""
    MATCH (e:Entity) 
    RETURN e.type, count(*) AS count 
    ORDER BY count DESC
""")

# 특정 엔터티의 관계 조회
result = run_cypher("""
    MATCH (e1:Entity {name: '중국'})-[r]-(e2:Entity)
    RETURN e1.name, r.type, e2.name, r.시기
    LIMIT 10
""")

# 문서별 엔터티 관계 네트워크
result = run_cypher("""
    MATCH (e1:Entity)-[r:relation {doc: '특정문서제목'}]-(e2:Entity)
    RETURN e1.name, e1.type, r.type, e2.name, e2.type
""")
```

## 📈 데이터 스키마

### 원산지 정보

#### Source 노드 (Ingredient)
```cypher
(:Ingredient {
    product: "식재료명",
    category: "식자재 분류",
    fishState: "어류 상태"  // 수산물 일 때만
})
```

#### 관계 (isFrom)
```cypher
()-[:isFrom {
    farm: "농장수",
    count: "축산물수",  // 축산물 일 때만
    association: "수산물 수협",   // 수산물 일 때만
    sold: "수산물 위판장"  // 수산물 일 때만
}]->()
```

#### Target 노드 (Origin)
```cypher
(:Origin {
    city: "시/군/구",
    region: "시/도"
})
```

### 영양소 정보

#### Source 노드 (Food)
```cypher
(:Food {
    product: "식품명",
    category: "식품분류",
    source: "출처"
})
```

#### 관계 (hasNutrient)
```cypher
()-[:hasNutrient {
    value: "양(수치)"
}]->()
```

#### Target 노드 (Nutrient)
```cypher
(:Nutrient {
    name: "영양소명"
})
```

### 문서 내 관계

#### 노드 (Entity)
```cypher
(:Entity {
    name: "엔터티명",
    type: "엔터티유형" // 품목, 국가, 기업 등
})
```

#### 관계 (relation)
```cypher
()-[:relation {
    type: "관계유형",        // 수입, 생산, 대체품 등
    doc: "문서제목",         // 출처 문서
    시기: "2025년",          // 시간 정보
    국가: "중국",            // 관련 국가
    수량: "31000톤"          // 수량 정보
    // 기타 동적 속성들...
}]->()
```

## 🛠️ 설정 및 커스터마이징

### 1. 모델 설정 (Fallback 시스템)

```python
# utils/model_fallback.py에서 설정
# 1순위: Gemini API 키 1
# 2순위: Gemini API 키 2  
# 3순위: OpenAI API 키
```

### 2. 그래프 추출 프롬프트 커스터마이징

`graph_extract2.py`의 `prompt_template` 수정:
- 엔터티 유형 추가/변경
- 관계 유형 정의
- 속성 추출 규칙 조정
- 도메인별 특화 규칙 추가

### 3. Neo4J 메모리 튜닝

`docker-compose.yml`에서 메모리 설정:
```yaml
environment:
  NEO4J_server_memory_heap_initial__size: "2G"
  NEO4J_server_memory_heap_max__size: "4G" 
  NEO4J_server_memory_pagecache_size: "2G"
```

### 4. Apache Lucene 서치 인덱스 설정

#### origin_idx (원산지 정보 검색)
```cypher
CREATE FULLTEXT INDEX origin_idx
FOR (n:Origin|Ingredient)
ON EACH [n.product, n.category, n.city, n.region]
OPTIONS {
  indexConfig: {
    `fulltext.analyzer`: 'cjk'   // 한글·중국어·일본어에 최적화된 bi-gram 분석기
  }
};
```

#### nutrient_idx (영양소 정보 검색)
```cypher
CREATE FULLTEXT INDEX nutrient_idx
FOR (n:Nutrient|Food)
ON EACH [n.name, n.product, n.category]
OPTIONS {
  indexConfig: {
    `fulltext.analyzer`: 'cjk'   // 한글·중국어·일본어에 최적화된 bi-gram 분석기
  }
};
```

#### doc_idx (문서 내 관계 정보 검색 - 노드 기준)
```cypher
CREATE FULLTEXT INDEX doc_idx
FOR (n:Entity)
ON EACH [n.name]
OPTIONS {
  indexConfig: {
    `fulltext.analyzer`: 'cjk'   // 한글·중국어·일본어에 최적화된 bi-gram 분석기
  }
};
```

#### rel_idx (문서 내 관게 검색 - 엣지 기준)
```cypher
CREATE FULLTEXT INDEX rel_idx
FOR ()-[r:relation]-()
ON EACH [r.국가, r.doc, r.type, r.시기]
OPTIONS {
  indexConfig: {
    `fulltext.analyzer`: 'cjk'   // 한글·중국어·일본어에 최적화된 bi-gram 분석기
  }
};
```

## 📊 모니터링 및 분석

### 1. 데이터 품질 확인

```cypher
// 고아 노드 (관계 없는 엔터티) 확인
MATCH (e:Entity)
WHERE NOT (e)-[:relation]-()
RETURN count(e) AS orphan_nodes

// 관계 유형별 분포
MATCH ()-[r:relation]->()
RETURN r.type, count(*) AS count
ORDER BY count DESC

// 문서별 추출된 관계 수
MATCH ()-[r:relation]->()
RETURN r.doc, count(*) AS relations
ORDER BY relations DESC
LIMIT 10
```

### 2. 네트워크 분석

```cypher
// 중심성이 높은 엔터티 (연결 수 기준)
MATCH (e:Entity)-[r:relation]-()
RETURN e.name, e.type, count(r) AS degree
ORDER BY degree DESC
LIMIT 20

// 특정 엔터티 간 최단 경로
MATCH path = shortestPath((e1:Entity {name: '중국'})-[*]-(e2:Entity {name: '한국'}))
RETURN path
```

## 🔍 트러블슈팅

### 일반적인 문제들

1. **Neo4J 연결 실패**
   ```bash
   # 컨테이너 상태 확인
   docker-compose ps
   
   # 로그 확인
   docker-compose logs neo4j
   ```

2. **메모리 부족 오류**
   - `docker-compose.yml`에서 JVM 힙 크기 조정
   - 시스템 메모리 확인 및 증설

3. **CSV 형식 오류**
   ```python
   # CSV 파일 검증
   import pandas as pd
   df = pd.read_csv("./import/report.csv")
   print(df.info())
   print(df.isnull().sum())
   ```

4. **그래프 추출 실패**
   - API 키 확인 (Gemini/OpenAI)
   - 프롬프트 길이 제한 확인
   - 모델 응답 형식 검증

5. **중복 데이터 문제**
   ```cypher
   // 중복 관계 확인 및 정리
   MATCH (e1)-[r:relation]->(e2)
   WITH e1, e2, r.type AS rel_type, collect(r) AS rels
   WHERE size(rels) > 1
   UNWIND rels[1..] AS duplicate
   DELETE duplicate
   ```

## 📚 참고 자료

- [Neo4J 공식 문서](https://neo4j.com/docs/)
- [Cypher 쿼리 언어](https://neo4j.com/docs/cypher-manual/current/)
- [Neo4J Python 드라이버](https://neo4j.com/docs/python-manual/current/)
- [GraphRAG 방법론](https://github.com/microsoft/graphrag)
- [APOC 프로시저](https://neo4j.com/labs/apoc/)
- [Graph Data Science 라이브러리](https://neo4j.com/docs/graph-data-science/current/)

## 🔄 확장 가능성

### 1. 실시간 업데이트
- 새 문서 자동 감지 및 처리
- 증분 업데이트 시스템 구축

### 2. 고급 분석
- 커뮤니티 탐지 알고리즘
- 중심성 분석 (PageRank, Betweenness)
- 시계열 그래프 분석

### 3. 시각화 연동
- Neo4J Bloom 연동
- Gephi 내보내기
- 웹 기반 그래프 시각화

### 4. 다중 도메인 지원
- 다른 산업 분야로 확장
- 도메인별 온톨로지 적용
- 크로스 도메인 관계 분석
