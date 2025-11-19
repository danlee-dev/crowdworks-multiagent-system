# Crawler & RDB Service - Developer Documentation

> For project overview and architecture, see [root README](../README.md)

This document provides technical implementation details for the `crawler_rdb` data pipeline service. This service is responsible for extracting data from external sources (KAMIS Open API, Excel files), transforming it, and loading it into the PostgreSQL database, using an LLM to automatically generate table schemas.

---

## System Architecture

### Project Structure (`crawler_rdb`)
```text
crawler_rdb/
├── crawler/
│   └── kamis_product_price_latest.py  # KAMIS Open API 시세 수집 로직
├── data/
│   └── 국가표준식품성분표_250426공개.xlsx # 식약처 영양성분 원본 엑셀
├── db/
│   ├── auto_table_creator.py            # LLM(Gemini)을 이용한 스키마 자동 생성기
│   └── database.py                        # PostgreSQL 연결 유틸리티
├── services/
│   ├── kamis_price_storage_service.py   # KAMIS 시세 데이터 저장/업데이트 서비스
│   └── nutrition_facts_service.py     # 영양성분 데이터 파싱 및 저장 서비스
├── utils/
│   └── nutrition_facts_parser.py        # 영양성분 엑셀 파서 (정규화 로직)
│
├── .dockerignore
├── .env                                 # 환경 변수 (DB, API 키)
├── .gitignore
├── cron.log                             # (예시) Cron 실행 로그
├── docker-compose.yml                   # Docker Compose (PostgreSQL + Crawler App)
├── Dockerfile                           # Crawler 서비스용 Dockerfile
├── main.py                              # 메인 실행기 (Entrypoint)
├── requirements.txt
└── settings.json