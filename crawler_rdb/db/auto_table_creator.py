import os
import sys
import json
import re
from db.database import get_connection
from dotenv import load_dotenv

# 상위 폴더의 utils 모듈을 import하기 위한 경로 추가
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))
from utils.model_fallback import OpenAIClientFallbackManager

# .env 파일 로드 (상위 폴더의 통합 .env 파일)
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '..', '.env'))

print("✅ Crawler RDB: Fallback 시스템 초기화 - Gemini 키 1 → Gemini 키 2 → OpenAI 순으로 시도")

def get_table_name_from_script(path: str) -> str:
    return os.path.splitext(os.path.basename(path))[0]

def merge_sample_fields(data_list: list) -> dict:
    merged = {}
    for row in data_list:
        merged.update(row)
    return merged

def quote_column_names(sql_code: str) -> str:
    """CREATE TABLE 구문에서 컬럼명을 자동으로 쌍따옴표로 감싸기"""
    def quote_column(line: str) -> str:
        line = line.strip()
        if not line or line.upper().startswith("CREATE TABLE") or line.upper().startswith("PRIMARY KEY"):
            return line

        match = re.match(r"([a-zA-Z_][a-zA-Z0-9_]*)\s+(.*)", line)
        if match:
            col_name, rest = match.groups()
            return f'    "{col_name}" {rest}'
        return line

    lines = sql_code.splitlines()
    quoted_lines = [quote_column(line) for line in lines]
    return "\n".join(quoted_lines)

def generate_create_table_sql(sample_data_merged: dict, table_name: str) -> str:
    compact_json = json.dumps(sample_data_merged, ensure_ascii=False, indent=2)

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

    try:
        full_response = OpenAIClientFallbackManager.chat_completions_create_with_fallback(
            model="gemini-2.5-pro",
            messages=[{"role": "user", "content": prompt}]
        )
        print("📄 GPT 응답:\n", full_response)

        match = re.search(r"(CREATE TABLE.*?;)", full_response, re.IGNORECASE | re.DOTALL)
        if not match:
            raise ValueError("GPT 응답에서 CREATE TABLE 구문을 찾지 못했습니다.")
        sql = match.group(1).strip()

        # ✅ 컬럼명 자동 따옴표 처리
        sql = quote_column_names(sql)

        return sql
    except Exception as e:
        print("❌ GPT 호출 실패 또는 응답 이상:", e)
        raise

def create_table_if_not_exists(data_list: list[dict], script_path: str):
    table_name = get_table_name_from_script(script_path)

    # ✅ 유효한 row만 필터링
    filtered_data_list = [row for row in data_list if any(v not in (None, "", [], {}) for v in row.values())]
    if not filtered_data_list:
        print("⚠️ CREATE TABLE 생략 — 유효한 데이터 없음")
        return

    conn = get_connection()
    cur = conn.cursor()

    # ✅ 테이블 존재 여부 확인
    cur.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables
            WHERE table_name = %s
        );
    """, (table_name,))
    exists = cur.fetchone()[0]

    if exists:
        print(f"✅ 테이블 '{table_name}' 이미 존재 — 생성 생략")
        cur.close()
        conn.close()
        return

    # 🔄 테이블 생성
    merged_sample = merge_sample_fields(filtered_data_list)
    try:
        sql = generate_create_table_sql(merged_sample, table_name)
    except Exception:
        print("⚠️ CREATE TABLE 문 생성 실패 — 테이블 생략됨")
        cur.close()
        conn.close()
        return

    try:
        cur.execute(sql)
        conn.commit()
        print(f"✅ 테이블 '{table_name}' 생성 성공 (from: {script_path})")

        # ✅ 실제 생성 여부 확인
        cur.execute(f"SELECT to_regclass('{table_name}');")
        existence = cur.fetchone()[0]
        print("🧪 생성된 테이블 존재 여부:", existence)

        if existence is None:
            raise Exception(f"⚠️ '{table_name}' 테이블이 실제로 생성되지 않았습니다!")
    except Exception as e:
        print(f"❌ 테이블 생성 실패: {e}")
        print("📄 실행하려던 SQL:\n", sql)
        conn.rollback()
    finally:
        cur.close()
        conn.close()
