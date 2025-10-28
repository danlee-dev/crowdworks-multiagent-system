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
