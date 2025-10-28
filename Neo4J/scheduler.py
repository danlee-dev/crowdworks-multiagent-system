import os
import sys
import glob
import json
from dotenv import load_dotenv
from .app.neo4j_query import run_cypher
import pandas as pd
from datetime import datetime

# === 공통 설정 ===
json_folder = "../elasticsearch/preprocessed_datas"   # JSON 원본 폴더
txt_output_folder = "./report_data"                   # JSON→TXT 출력 폴더
csv_output_folder = "./extracted_graph"               # TXT→CSV 출력 폴더
os.makedirs(txt_output_folder, exist_ok=True)
os.makedirs(csv_output_folder, exist_ok=True)

# utils import
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from utils.model_fallback import OpenAIClientFallbackManager

# .env 로드
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))


# ==============================
# 1. JSON → TXT 변환 단계
# ==============================
def normalize_name(name: str) -> str:
    return name.replace("凸", "").strip()

existing_txt_files = glob.glob(os.path.join(txt_output_folder, "*.txt"))
existing_names_normalized = {
    os.path.splitext(os.path.basename(p))[0]
    for p in existing_txt_files
}

json_files = sorted(glob.glob(os.path.join(json_folder, "*.json")))

new_txt_files = []  # 이번 실행에서 새로 생성된 TXT 경로 저장
processed_count = 0

for json_file_path in json_files:
    base_name_original = os.path.splitext(os.path.basename(json_file_path))[0]
    base_name_normalized = normalize_name(base_name_original)

    if base_name_normalized in existing_names_normalized:
        print(f"⏭️ 스킵(이미 존재): {base_name_normalized}.txt")
        continue

    try:
        with open(json_file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"⚠️ JSON 오류: {json_file_path} -> {e}")
        continue

    page_contents_processed = []
    for idx, item in enumerate(data):
        if not isinstance(item, dict):
            continue
        content = str(item.get("page_content", "")).strip()
        if idx == 0:
            page_contents_processed.append(content)
        else:
            if "\n\n" in content:
                content = content.split("\n\n", 1)[1].strip()
            page_contents_processed.append(content)

    file_text = "\n\n".join(page_contents_processed)

    safe_base = base_name_normalized or base_name_original
    output_path = os.path.join(txt_output_folder, safe_base + ".txt")
    try:
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(file_text)
        print(f"✅ 저장 완료: {output_path}")
        new_txt_files.append(output_path)
        processed_count += 1
        existing_names_normalized.add(base_name_normalized)
    except Exception as e:
        print(f"⚠️ 저장 오류: {output_path} -> {e}")

print(f"총 {len(json_files)}개 JSON 중 {processed_count}개 TXT 생성 완료")


# ==============================
# 2. TXT → CSV 변환 단계
# ==============================

def add_title_column(gpt_csv_output: str, base_name: str, final_text: str) -> str:
    """CSV 앞에 '문서제목' 컬럼 추가"""
    doc_title = final_text.splitlines()[0].strip() if final_text.strip() else base_name
    lines = gpt_csv_output.strip().splitlines()
    if not lines:
        return ""
    header = ["문서제목"] + lines[0].split(",")
    new_lines = [",".join(header)]
    for line in lines[1:]:
        if line.strip():
            new_lines.append(",".join([doc_title, line]))
    return "\n".join(new_lines)


prompt_template = """
다음 문서를 분석하여 등장하는 엔터티(품목·국가·기업 등)와 유형을 추출하고,
엔터티 간 관계 및 속성을 CSV로 출력해 주세요.
엔터티는 문서에서 키워드가 되는 단어이고 관계는 '대체품', '수입', '생산' 등의 관계를 의미합니다.
속성은 관계에 대한 추가 정보이며 그 관계가 설명되는 시간(연도), 수량 등의 정보를 포함합니다.
출력은 CSV 형식이며
CSV 헤더와 데이터 행 이외의 설명 문장은 금지합니다.

CSV 컬럼 순서:
엔터티1,엔터티1유형,관계,엔터티2,엔터티2유형,속성

다음의 출력 규칙을 꼭 준수해 주세요:
0. **헤더 준수**: 첫 행에 반드시 엔터티1,엔터티1유형,관계,엔터티2,엔터티2유형,속성 헤더만 포함합니다.
1. **무분별한 쉼표 사용 금지**(가장 중요): 하나의 컬럼 안에서는 절대 쉼표를 사용하지 않고 위 헤더에 해당하는 6개의 컬럼만 생성합니다.
    - **[잘못된 예시]** 국가:중국,시기:2025년 또는 수입량:31,000톤
    - **[올바른 예시]** 국가:중국;시기:2025년 또는 수입량:31000톤
2. **필수 컬럼**: 엔터티1, 엔터티1유형, 관계, 엔터티2, 엔터티2유형은 항상 값이 있어야 합니다.
3. **숫자 형식**: 모든 숫자에서 쉼표(,)를 반드시 제거합니다.
    - **[잘못된 예시]** 31,000 또는 1,234 또는 2,500,000달러 또는 $3,200~$3,500
    - **[올바른 예시]** 31000 또는 1234 또는 2500000달러 또는 $3200~$3500
4. **속성 쌍 생성**: 속성 컬럼은 반드시 속성명:속성값 형식으로 작성합니다. 둘 중 하나가 없으면 해당 속성은 생략합니다.
    - **[예시]** 국가:중국 또는 시기:2025년
    - **[잘못된 예시]** 중국 또는 2025년
5. **다중 속성 형식**: 속성이 여러 개일 경우, 각 속성명과 속성값을 세미콜론(;)으로 구분하여 각 컬럼에 나열합니다.
    - **[예시]** 속성 컬럼에 국가:중국;시기:2025년과 같이 작성합니다.
6. 하나의 속성명 안에 여러 속성값이 있을 경우, 파이프(|)를 사용하여 구분합니다.
    - **[잘못된 예시]** 국가:중국,미국 또는 국가:중국,미국,시기:2025년
    - **[올바른 예시]** 국가:중국|미국 또는 국가:중국|미국;시기:2025년 
7. **시기 정보**: 문서에 "2025년", "2024년 3월" 등 특정 시기 정보가 있다면, 반드시 시기라는 속성명으로 추출하여 속성에 포함합니다.
8. **중복 금지**: 엔터티1과 엔터티2는 서로 달라야 합니다. (엔터티1 ≠ 엔터티2)
9. **문서 제목 활용**: 문서의 제목(보통 첫 줄)에서 주요 정보를 파악하여, 모든 행의 속성에 기본 정보(예: 국가:중국;시기:2025년 3월)를 일관되게 포함시켜 컨텍스트를 유지합니다.
10. **관계 없는 엔터티 제외**: 문서에 등장하더라도 다른 엔터티와 관계를 맺지 않는 엔터티는 출력하지 않습니다.

문서:
{final_text}
"""

processed_csv_count = 0

# 새로 생성된 CSV들을 담을 리스트
new_csv_files = []

for file_path in new_txt_files:  # 이번에 새로 만든 TXT만 처리
    base_name = os.path.splitext(os.path.basename(file_path))[0]

    with open(file_path, "r", encoding="utf-8") as f:
        final_text = f.read().strip()

    if not final_text:
        print(f"⚠️ {base_name}.txt 비어있음 → 건너뜀")
        continue

    prompt = prompt_template.format(final_text=final_text)
    messages = [
        {"role": "system", "content": "당신은 문서 분석 및 엔터티 관계 추출 전문가입니다."
                "현재 당신은 식품 분야의 Knowledge Graph를 구축 중이며, "
                "문서에 등장하는 엔터티와 관계를 식품 데이터 관점에서 분석해야 합니다."},
        {"role": "user", "content": prompt}
    ]

    gpt_output = OpenAIClientFallbackManager.chat_completions_create_with_fallback(
        model="document-analysis",
        messages=messages,
        temperature=0
    )

    gpt_output_with_title = add_title_column(gpt_output, base_name, final_text)

    output_csv_path = os.path.join(csv_output_folder, base_name + ".csv")
    with open(output_csv_path, "w", encoding="utf-8", newline="") as csvfile:
        csvfile.write(gpt_output_with_title)

    print(f"✅ CSV 저장 완료: {output_csv_path}")
    new_csv_files.append(output_csv_path)
    processed_csv_count += 1

# ==============================
# 3. 새 CSV 병합 → import/report_YYYY-MM.csv 저장
# ==============================
if new_csv_files:
    dfs = [pd.read_csv(f, dtype=str, engine="python", on_bad_lines="skip") for f in new_csv_files]

    merged_df = pd.concat(dfs, ignore_index=True)

    # 핵심 컬럼 필터링
    key_cols = ["엔터티1","엔터티1유형","관계","엔터티2","엔터티2유형"]
    merged_df.dropna(subset=key_cols, inplace=True)
    for col in key_cols:
        merged_df = merged_df[merged_df[col].astype(str).str.strip() != ""]

    month_str = datetime.now().strftime("%Y-%m")
    merged_output_path = f"./import/report_{month_str}.csv"
    os.makedirs(os.path.dirname(merged_output_path), exist_ok=True)
    merged_df.to_csv(merged_output_path, index=False, encoding="utf-8-sig")

    print(f"✅ {len(new_csv_files)}개 CSV 병합 → {merged_output_path}")

    # ==============================
    # 4. Neo4j 로드 (병합된 CSV만)
    # ==============================
    cypher_query = f"""
    CREATE CONSTRAINT IF NOT EXISTS FOR (r:report) REQUIRE (r.name) IS UNIQUE;

    LOAD CSV WITH HEADERS FROM 'file:///report_{month_str}' AS row
    MERGE (e1:Entity {{name: row.엔터티1, type: row.엔터티1유형}})
    MERGE (e2:Entity {{name: row.엔터티2, type: row.엔터티2유형}})
    MERGE (e1)-[rel:relation {{type: row.관계, doc: row.문서제목}}]->(e2)
    WITH rel, split(row.속성, ';') AS kvPairs
    UNWIND kvPairs AS kv
    WITH rel, split(kv, ':') AS parts
    WHERE size(parts) = 2
    WITH rel, parts[0] AS key, parts[1] AS value
    SET rel[key] = value;
    """
    run_cypher(cypher_query)
    print(f"✅ Neo4j 로드 완료: {merged_output_path}")
else:
    print("⏭️ 새로 생성된 CSV가 없어 병합/Neo4j 로드를 건너뜁니다.")

print(f"총 {processed_count}개 JSON에서 {processed_csv_count}개 TXT 및 CSV 생성 완료")