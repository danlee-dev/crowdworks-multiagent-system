# Crawler & RDB Service - Developer Documentation

> For project overview and architecture, see [root README](../README.md)

This document provides technical implementation details for the `crawler_rdb` data pipeline service. This service is responsible for extracting data from external sources (KAMIS Open API, Excel files), transforming it, and loading it into the PostgreSQL database, utilizing an LLM-based approach to automatically generate table schemas.

---

## System Architecture

### Project Structure (`crawler_rdb`)
```
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
```
### Core Architecture & Data Flows
This service executes two primary data pipelines via main.py.

#### 1. **KAMIS Price Data Flow** (LLM Auto-Schema)
This pipeline handles daily price data updates and features an LLM-driven automatic table creation mechanism.

1. **Execute**: Triggered via main.py --crawler kamis-latest (or cron).

2. **Crawl**: crawler/kamis_product_price_latest.py fetches XML data from KAMIS Open API.

3. **Store**: services/kamis_price_storage_service.py processes the raw data.

4. **Check Schema**: Calls db/auto_table_creator.py to check table existence.

5. **Generate Schema** (LLM): If the table (kamis_product_price_latest) is missing, it sends a data sample to Gemini LLM to generate a robust CREATE TABLE SQL statement automatically based on the JSON structure.

6. **Upsert**: Inserts new records or updates existing ones based on a composite unique key (RegDate + Product + Item + Unit).

**LLM Auto-Schema Prompt** (db/auto_table_creator.py):

```python

    prompt = f"""
    다음은 웹 API를 통해 수집된 실시간 JSON 데이터입니다.
    이 데이터를 기반으로 PostgreSQL CREATE TABLE 문을 생성해줘.
    테이블 이름은 "{table_name}"이고, 모든 키는 적절한 타입으로 매핑되어야 해.

    - 숫자는 가능한 INTEGER 또는 DOUBLE PRECISION으로
    - 날짜 형식은 가능한 DATE로 (예: regday, lastest_day 등은 DATE로 지정)
    - 문자열은 TEXT로
    - id 필드는 SERIAL PRIMARY KEY로 지정해줘 (없으면 새로 추가)
    - 주어진 데이터는 실시간 크롤링 결과이므로 JSON 키와 타입을 기준으로 자동 추론해서 생성해줘

    JSON 예시:
    {compact_json}
    """
```


#### 2. **Nutrition Facts Flow** (Excel ETL)
This pipeline performs a one-time heavy ETL process for the "National Standard Food Composition Table".

1. **Execute**: Triggered via main.py --mode nutrition-facts.

2. **Parse**: utils/nutrition_facts_parser.py reads the multi-header Excel file using pandas.

    - Cleans column names (removes special chars, unifies units).

    - Maps columns to normalized categories (foods, minerals, vitamins, etc.).

3. **Normalize & Store**: services/nutrition_facts_service.py creates a relational schema.

    - Parent Table: foods

    - Child Tables: proximates, minerals, vitamins, amino_acids, fatty_acids

    - Performs DROP TABLE -> CREATE TABLE -> INSERT for a clean build.


## Quick Start

### Prerequisites
- Python 3.10+
- Docker & Docker Compose
- API Keys: KAMIS, Gemini (or OpenAI for fallback)

### Installation

#### 1. Docker Compose (Recommended)
The service is designed to run alongside a PostgreSQL container.

```bash
# 1. Configure Environment Variables
# Create .env file based on the example below
vi .env

# 2. Start Database
docker-compose up -d db

# 3. Run Data Pipelines (One-off commands)

# Load Nutrition Facts (Heavy ETL)
docker-compose run --rm crawler python3 -B main.py --mode nutrition-facts

# Crawl KAMIS Price Data
docker-compose run --rm crawler python3 -B main.py --crawler kamis-latest
```

#### 2. Local Development
To run the Python scripts locally against the Dockerized DB.

```bash
# 1. Start DB only
docker-compose up -d db

# 2. Setup Python Environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

# 3. Export Env Vars (Override host for local)
export POSTGRES_HOST=localhost
export POSTGRES_PORT=5433
# ... export other keys ...

# 4. Run
python main.py --list
python main.py --crawler kamis-latest
```

## Configuration

### 환경 변수 (.env)

프로젝트 루트 디렉토리에 `.env` 파일을 생성하고 다음 변수들을 설정하세요:

```bash
# Database Configuration
# NOTE: Use 'db' host for Docker, 'localhost' for local run
POSTGRES_DB=crowdworks_db
POSTGRES_USER=crowdworks_user
POSTGRES_PASSWORD=your_password
POSTGRES_HOST=db
POSTGRES_PORT=5432

# KAMIS API Configuration (Required)
KAMIS_API_KEY=your_kamis_key
KAMIS_API_ID=your_kamis_id

# LLM Configuration (For Auto-Schema Generation)
# The system attempts Gemini first, then falls back to OpenAI
GEMINI_API_KEY_1=your_gemini_key
OPENAI_API_KEY=your_openai_key
```

## Usage
The main.py script serves as the single entry point for all crawler operations.

**Command Line Arguments**
- --list: Show all available crawlers.
- --crawler [name]: Run a specific crawler (e.g., kamis-latest).
- --mode [name]: Run a special mode (e.g., nutrition-facts).

**Examples**

```bash
# List available tasks
python main.py --list

# Run KAMIS Crawler
python main.py --crawler kamis-latest

# Run Nutrition ETL
python main.py --mode nutrition-facts
```

## Docker Commands

### System Management

```bash
# Start DB in background
docker-compose up -d db

# Build Crawler Image
docker-compose build crawler

# View Logs
docker-compose logs -f crawler
docker-compose logs -f db

# Stop Containers
docker-compose down
```

### Database Maintenance

```bash
# Connect to DB Shell
docker-compose exec db psql -U crowdworks_user -d crowdworks_db

# Check Tables
# \dt
```

## Troubleshooting
### Common Issues
1. **DB Connection Refused**
    - Docker: Ensure POSTGRES_HOST=db and POSTGRES_PORT=5432.
    - Local: Ensure POSTGRES_HOST=localhost and POSTGRES_PORT=5433 (mapped port).

2. **Schema Generation Failed**
    - Check GEMINI_API_KEY_1 in .env.
    - If Gemini fails, ensure OPENAI_API_KEY is set for fallback.
    - Check logs for "GPT 호출 실패" or API quota errors.

3. **Excel Parsing Errors**
    - Ensure the Excel file exists in data/.
    - The parser expects specific column names (e.g., "식품명", "에너지 (kcal/100g)"). If the Excel format changes, update utils/nutrition_facts_parser.py.
