# Elasticsearch 문서 처리 및 인덱싱 시스템

이 디렉토리는 농식품 관련 문서들을 Elasticsearch에 인덱싱하고 검색 가능하도록 처리하는 시스템입니다.

## 📁 파일 구조

```
elasticsearch/
├── create_index_table.py      # 테이블 포함 문서용 인덱스 생성
├── create_index_text.py       # 텍스트 전용 문서용 인덱스 생성
├── docker-compose.yml         # Elasticsearch & Kibana 컨테이너 설정
├── embedding.py               # 문서 임베딩 생성
├── insert.py                  # Elasticsearch 문서 삽입
├── page_chunking.py          # 문서 청킹 및 전처리
├── referenceURL.json         # 문서 참조 URL 매핑
├── run_monthly_pipeline.sh   # 월간 파이프라인 실행 스크립트
└── README.md                 # 이 파일
```

## 🚀 시작하기

### 1. Elasticsearch & Kibana 실행

```bash
docker-compose up -d
```

- **Elasticsearch**: http://localhost:9200
- **Kibana**: http://localhost:5601
- **기본 인증**: elastic / changeme

### 2. 인덱스 생성

```bash
# 텍스트 전용 인덱스 생성
python create_index_text.py

# 테이블 포함 인덱스 생성
python create_index_table.py
```

### 3. 데이터 처리 파이프라인 실행

```bash
# 전체 파이프라인 실행
./run_monthly_pipeline.sh

# 또는 단계별 실행
python page_chunking.py    # 1. 문서 청킹 및 전처리
python embedding.py        # 2. 임베딩 생성
python insert.py          # 3. Elasticsearch 삽입
```

## 📊 시스템 구성 요소

### 1. 문서 전처리 (`page_chunking.py`)

- **입력**: `datas/` 폴더의 JSON 문서들
- **출력**: `preprocessed_datas/` 폴더의 전처리된 문서들
- **기능**:
  - 문서 청킹 및 계층 구조 병합
  - 의미없는 데이터 필터링
  - 텍스트 정규화 및 정리
  - 토큰 수 계산 (tiktoken 사용)

### 2. 임베딩 생성 (`embedding.py`)

- **모델**: `dragonkue/bge-m3-ko` (한국어 특화 BGE 모델)
- **배치 처리**: 20개 문서씩 병렬 처리
- **기능**:
  - 1024차원 벡터 임베딩 생성
  - 텍스트/테이블 문서 분류
  - 재시도 로직 포함

### 3. 인덱스 구조

#### 텍스트 인덱스 (`page_text`)
- **대상**: text, chunked_text, merged(text-only) 문서
- **분석기**: 한국어 Nori 토크나이저 기반
- **필드**: 
  - `page_content`: 메인 텍스트 (ngram, exact 서브필드 포함)
  - `embedding`: 1024차원 dense_vector (코사인 유사도)
  - `meta_data`: 문서 메타데이터

#### 테이블 인덱스 (`page_table`)
- **대상**: table, merged(table 포함) 문서
- **구조**: 텍스트 인덱스와 유사하지만 테이블 데이터 최적화
- **중첩 객체**: `merged_children`로 병합된 하위 문서 관리

### 4. 한국어 분석 설정

```json
{
  "tokenizer": "korean_nori_tokenizer",
  "char_filter": "korean_normalize_filter",
  "filters": [
    "korean_lowercase",
    "korean_stop",
    "korean_ngram"
  ]
}
```

- **정규화**: 전각문자 → 반각문자 변환
- **불용어**: 조사, 어미 등 제거
- **N-gram**: 2-3글자 단위 토큰 생성

## 🔧 설정 및 환경변수

### Elasticsearch 설정
- **호스트**: localhost:9200
- **인증**: elastic / changeme
- **샤드**: 1개 (단일 노드)
- **복제본**: 0개
- **최대 결과**: 10,000개

### 임베딩 모델 설정
- **배치 크기**: 20
- **최대 워커**: 20
- **배치 간 지연**: 1.5초
- **재시도**: 최대 3회

## 📈 모니터링 및 로그

### 로그 파일
- **위치**: `logs/monthly_pipeline_YYYY-MM-DD_HH-MM-SS.log`
- **내용**: 각 단계별 실행 결과 및 오류 정보

### Kibana 대시보드
- **URL**: http://localhost:5601
- **인덱스 패턴**: `page_text*`, `page_table*`
- **주요 메트릭**: 문서 수, 임베딩 품질, 검색 성능

## 🔍 사용 예시

### 1. 텍스트 검색
```python
from elasticsearch import Elasticsearch

es = Elasticsearch("http://localhost:9200", basic_auth=("elastic", "changeme"))

# 키워드 검색
result = es.search(
    index="page_text",
    body={
        "query": {
            "match": {
                "page_content": "농산물 가격"
            }
        }
    }
)
```

### 2. 벡터 유사도 검색
```python
# 임베딩 기반 유사도 검색
result = es.search(
    index="page_text",
    body={
        "query": {
            "script_score": {
                "query": {"match_all": {}},
                "script": {
                    "source": "cosineSimilarity(params.query_vector, 'embedding') + 1.0",
                    "params": {"query_vector": query_embedding}
                }
            }
        }
    }
)
```

## 🛠️ 트러블슈팅

### 일반적인 문제들

1. **Elasticsearch 연결 실패**
   ```bash
   # 컨테이너 상태 확인
   docker-compose ps
   
   # 로그 확인
   docker-compose logs elasticsearch
   ```

2. **메모리 부족 오류**
   ```bash
   # JVM 힙 크기 조정 (docker-compose.yml)
   ES_JAVA_OPTS=-Xms1g -Xmx1g
   ```

3. **임베딩 생성 실패**
   - GPU 메모리 확인
   - 배치 크기 조정 (BATCH_SIZE 변수)
   - 모델 다운로드 상태 확인

4. **인덱스 생성 오류**
   ```bash
   # 기존 인덱스 삭제 후 재생성
   curl -X DELETE "localhost:9200/page_text"
   python create_index_text.py
   ```
