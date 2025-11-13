# Crawler - Developer Documentation

> For project overview and architecture, see [root README](../README.md)

This document provides technical implementation details for developers working on the crawler.

---

## System Architecture

### Project Structure
```
crawler/
├── ReportPDF/  # 크롤링 후 보고서 보관 폴더, 크롤러 첫 실행 시 생성
├── ReferencePDF/  # KC 전처리 완료된 보고서 보관 폴더
│
├── crawler/
│   ├── atfis_investigation_reports_KREI.py	# 조사 보고서
│   ├── atfis_investigation_reports_related.py	# 유관 보고서
│   ├── atfis_Market_segment.py	 		# 세분시장 보고서
│   ├── atfis_newsletters.py				# 뉴스레터
│   ├── atfis_statistic_reports.py			# 통계 보고서
│   ├── KAMIS_foreign_reports.py			# 해외시장 보고서
│   ├── KAMIS_investigation_reports.py		# 조사 보고서
│   ├── KATI_export_country_reports.py	# 국가별 수출 보고서
│   ├── KATI_export_issue_reports.py	# 이슈별 수출 보고서
│   ├── KATI_export_item_reports.py	# 품목별 수출 보고서
│   └── KREI_observation_reports.py	# 관측 보고서
│
├── clear_report/
│   └── clear_ReportPDF.py	# ReportPDF->ReferencePDF 파일 이전
│
├── KC/
│   └── KC.py  #KC 전처리
│
├── docker-compose.yml  # 크롤러 실행용
├── Dockerfile
├── requirements.txt  # playwright, requests, aiohttp
├── .env  #KC API 키, CROWD_API_KEY = ‘your_api_key’
│
└── run.sh  # “크롤링 -> KC -> 파일 이전” 순차적 처리 목적 쉘


```

### Function Specification
#### /crawler
- atfis_investigation_reports_KREI.py, atfis_investigation_reports_related.py, atfis_statistic_reports.py
    - process_detail()
        - 입력
            - page: Playwright 페이지 인스턴스
            - detail_url: 상세페이지 url
        - 출력
            - True
                - (a) 게시일 파싱 성공 & 기준일 이상(최근글) → 첨부 처리 완료(또는 시도)
                - (b) 게시일 요소를 못 찾았거나 날짜 파싱 실패 → 해당 페이지만 스킵하고 다음 상세로 진행
            - False
                - 게시일이 threshold_date 이전 → 목록 순회 전체 종료 신호
        - 역할: 상세페이지 접속 후pdf 다운로드 및 출처 저장. 출처는 ../elasticsearch/referenceURL.json에 저장. 

- atfis_Market_segment.py
    - download_pdf_from_detail(): 
        - 입력
            - page: Playwright 페이지 인스턴스
            - api: page.request로 얻은 요청 컨텍스트
            - detail_url: 상세페이지 url
        - 출력
            - True
                - (a) 게시일 파싱 성공 & 기준일 이상(최근글) → 첨부 처리 완료(또는 시도)
                - (b) 게시일 요소를 못 찾았거나 날짜 파싱 실패 → 해당 페이지만 스킵하고 다음 상세로 진행
            - False
            - 게시일이 threshold_date 이전 → 목록 순회 전체 종료 신호
        - 역할: 사이트의 상세 페이지 열람하여 pdf 다운로드 링크 추출 후 download_pdf() 호출.
    - download_pdf()
        - 입력
            - api:  page.request로 얻은 요청 컨텍스트
            - pdf_url: 절대 PDF 다운로드 URL.
            - filename: 상세페이지에서 추출한 원래 파일명. 추출에 실패하거나 확장자가 없으면 URL 경로 basename을 사용.
            - detail_url: 상세페이지 url 
        - 출력: True
        - 역할: pdf 다운로드 및 출처 저장. 정상적으로 다운로드가 가능할 때만 호출되므로 항상 True를 반환함.

- KAMIS_foreign_reports.py, KAMIS_investigation_reports.py
    - fetch_with_retry(): 
        - 입력
            - url: 다운로드할 절대 URL
            - retries: 최대 재시도 횟수(기본 3)
            - backoff: 재시도 간 대기(초, 기본 3)
        - 출력: requests.Response — raise_for_status()가 성공한 응답 객체
        - 역할: HTTP GET 재시도 로직.
    - process_item()
        - 입력
            - page: Playwright 페이지 인스턴스
            - idx: 현재 페이지에서 처리할 항목의 0-기반 인덱스
        - 출력
            - True: 정상 처리 또는 해당 항목만 스킵
            - False: 게시일이 threshold_date 이전 → 목록 순회 전체 종료 신호
        - 역할: pdf 다운로드 및 출처 저장.

- KATI_export_country_reports.py, atfis_newsletters.py, KATI_export_issue_reports.py, KATI_export_item_reports.py
    - save_reference(): 
        - 입력
            - filename: 보고서 파일
            - detail_url: 보고서 출처 상세 URL
        - 출력: None
        - 역할: 출처 저장

- KREI_observation_reports.py
    - save_reference()
        - 입력
            - filename: 보고서 파일
        - 출력: None
        - 역할: 출처 저장. 해당 사이트는 출처 url이 고정되어 있으므로, 상세 url을 입력으로 받지 않음.
    - fetch_with_retry()
        - 입력
            - url: 다운로드할 절대 URL
            - retries: 최대 재시도 횟수(기본 3)
            - backoff: 재시도 간 대기(초, 기본 1)
        - 출력: requests.Response — raise_for_status()가 성공한 응답 객체
        - 역할: HTTP GET 재시도 로직.
    - download_all_pdfs_on_page()
        - 입력
            - page: Playwright 페이지 인스턴스
        - 출력: None
        - 역할: 해당 페이지에 있는 모든 pdf 다운로드.
    - wait_for_load()
        - 입력
            - page: 대상 페이지
            - timeout: 최대 대기 시간 (ms, 기본 30000)
        - 출력: None
        - 역할: networkidle 또는 domcontentloaded까지 대기(예외 핸들링).
    - set_radio_and_trigger()
        - 입력
            - page: 대상 페이지
            - selector_id: 라디오 input의 DOM id
        - 출력: None
        - 역할: 페이지 내 라디오 버튼 체크 및 change 이벤트 트리거(브라우저 JS 실행).

#### /KC
- KC.py
    - _sync_upload_with_requests()
        - 입력
            - pdf_path: 업로드할 PDF 경로
        - 출력: 서버에서 반환한 UUID
        - 역할: 동기 requests로 파일 업로드.
    - upload_and_process()
        - 입력
            - session: 공유 세션
            - pdf_path: 업로드할 PDF 경로
        - 출력: None
        - 역할: 비동기 파이프라인에서 _sync_upload_with_requests() 호출여 동기 업로드를 스레드로 실행. _wait_and_download() 호출하여 처리 완료 대기, json 다운로드 저장.
    - _wait_and_download()
        - 입력
            - session: 공유 세션
            - doc_id: 업로드 결과 문서 ID
            - stem: 출력 파일명
        - 출력: None
        - 역할: 문서 상태 폴링(status -> SUCCESS) 후 json을 받아 로컬에 저장.


---


## Execution Flow (run.sh)

1. **Start crawling**
   - `crawler/*.py` scripts except `clear_ReportPDF.py` run sequentially or in parallel.
   - Each crawler saves PDF reports into `ReportPDF/`.

2. **Run KC Preprocessing**
   - `KC/KC.py` processes downloaded reports.
   - Output is stored in `ReferencePDF/`.

3. **Post-processing**
   - `clear_ReportPDF.py` moves processed files from `ReportPDF/` → `ReferencePDF/`.

4. **Logging**
   - Execution logs are written to `run.log` and `log.out`.


---


## Configuration

### 환경 변수 (.env)

프로젝트 루트 디렉토리에 `.env` 파일을 생성하고 다음 변수들을 설정하세요:

```bash
CROWD_API_KEY = ‘your_api_key’
```
---

## Quick Start

### Prerequisites
- Python 3.10
- Docker 27.5.1+
- Docker Compose 1.29.2+
- API Keys: Knowledge Compiler

### Scheduling
- example
    - crontab -l
    - 0 0 10 * * cd /root/workspace/crowdworks/crawler && ./run.sh >> /root/workspace/crowdworks/crawler/run.log 2>&1
  