import os
import sys
import glob
from dotenv import load_dotenv
import csv

def add_title_column(gpt_csv_output: str, base_name: str, final_text: str) -> str:
    """
    GPT가 생성한 CSV 문자열(gpt_csv_output)에 '문서제목' 컬럼을 앞에 추가하고
    모든 행에 문서 제목을 넣어 반환.
    """
    # 문서 제목: TXT의 첫 줄, 없으면 파일명 사용
    doc_title = final_text.splitlines()[0].strip() if final_text.strip() else base_name

    lines = gpt_csv_output.strip().splitlines()
    if not lines:
        return ""

    # 첫 줄(헤더) 수정
    header = lines[0].split(",")
    header = ["문서제목"] + header

    new_lines = [",".join(header)]

    # 나머지 데이터 행 수정
    for line in lines[1:]:
        if not line.strip():
            continue
        new_lines.append(",".join([doc_title, line]))

    return "\n".join(new_lines)

# 상위 폴더의 utils 모듈 import
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from utils.model_fallback import OpenAIClientFallbackManager

# .env 파일 로드
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

print("✅ Fallback 시스템 초기화 완료: Gemini 키 1 → Gemini 키 2 → OpenAI 순으로 시도")

# 입력/출력 폴더 설정
txt_folder = "./report_data"
output_folder = "./extracted_graph"
os.makedirs(output_folder, exist_ok=True)

# TXT / CSV 파일 목록
txt_files = sorted(glob.glob(os.path.join(txt_folder, "*.txt")))
existing_csv_files = {
    os.path.splitext(os.path.basename(p))[0]
    for p in glob.glob(os.path.join(output_folder, "*.csv"))
}

# GPT 프롬프트 템플릿
prompt_template = """
다음 문서를 분석하여 등장하는 엔터티(품목·국가·기업 등)와 유형을 추출하고,
엔터티 간 관계 및 속성을 CSV로 출력해 주세요.
엔터티는 문서에서 키워드가 되는 단어이고 관계는 '대체품', '수입', '생산' 등의 관계를 의미합니다.
속성은 관계에 대한 추가 정보이며 그 관계가 설명되는 시간(연도), 수량 등의 정보를 포함합니다.
출력은 CSV 형식이며
CSV 헤더와 데이터 행 이외의 설명 문장은 금지합니다.

CSV 컬럼 순서:
엔터티1,엔터티1유형,관계,엔터티2,엔터티2유형,속성

(중략: 규칙 동일)
문서:
{final_text}
"""

processed_count = 0
skipped_exists = 0
skipped_empty = 0

# TXT 파일 처리
for file_path in txt_files:
    base_name = os.path.splitext(os.path.basename(file_path))[0]

    # 이미 CSV가 있으면 스킵
    if base_name in existing_csv_files:
        print(f"⏭️ 스킵(이미 존재): {base_name}.csv")
        skipped_exists += 1
        continue

    with open(file_path, "r", encoding="utf-8") as f:
        final_text = f.read().strip()

    if not final_text:
        print(f"⚠️ {base_name}.txt 파일이 비어있습니다. 건너뜁니다.")
        skipped_empty += 1
        continue

    # 프롬프트 생성
    prompt = prompt_template.format(final_text=final_text)

    messages = [
        {"role": "system", "content": "당신은 문서 분석 및 엔터티 관계 추출 전문가입니다. "
                "현재 당신은 식품 분야의 Knowledge Graph를 구축 중이며, "
                "문서에 등장하는 엔터티와 관계를 식품 데이터 관점에서 분석해야 합니다."},
        {"role": "user", "content": prompt}
    ]

    # Gemini → OpenAI Fallback 호출
    gpt_output = OpenAIClientFallbackManager.chat_completions_create_with_fallback(
        model="document-analysis",
        messages=messages,
        temperature=0
    )

    # 문서제목 컬럼 추가
    gpt_output_with_title = add_title_column(gpt_output, base_name, final_text)

    # CSV 저장
    output_csv_path = os.path.join(output_folder, base_name + ".csv")
    with open(output_csv_path, "w", encoding="utf-8", newline="") as csvfile:
        csvfile.write(gpt_output_with_title)

    print(f"✅ {base_name} → {output_csv_path} 저장 완료")
    processed_count += 1

print(
    f"총 {len(txt_files)}개 TXT 중 {processed_count}개 처리 완료, "
    f"{skipped_exists}개 스킵(이미 CSV 존재), {skipped_empty}개 스킵(빈 파일)"
)
