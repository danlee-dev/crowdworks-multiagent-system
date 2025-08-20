import os
import sys
import glob
import csv
from dotenv import load_dotenv

# 상위 폴더의 utils 모듈을 import하기 위한 경로 추가
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from utils.model_fallback import OpenAIClientFallbackManager

# .env 파일 로드 (상위 폴더의 .env 파일)
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

print("✅ Fallback 시스템 초기화 완료: Gemini 키 1 → Gemini 키 2 → OpenAI 순으로 시도")

# TXT 파일이 있는 폴더
txt_folder = "./report_data"
txt_files = sorted(glob.glob(os.path.join(txt_folder, "*.txt")))

# 결과 저장 폴더
output_folder = "./extracted_graph"
os.makedirs(output_folder, exist_ok=True)

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
0.  **헤더 준수**: 첫 행에 반드시 `엔터티1,엔터티1유형,관계,엔터티2,엔터티2유형,속성` 헤더만 포함합니다.
1.  **무분별한 쉼표 사용 금지**(가장 중요): 하나의 컬럼 안에서는 절대 쉼표를 사용하지 않고 위 헤더에 해당하는 6개의 컬럼만 생성합니다.
    -   **[잘못된 예시]** `국가:중국,시기:2025년` 또는 `수입량:31,000톤`
    -   **[올바른 예시]** `국가:중국;시기:2025년` 또는 `수입량:31000톤`
2.  **필수 컬럼**: `엔터티1`, `엔터티1유형`, `관계`, `엔터티2`, `엔터티2유형`은 항상 값이 있어야 합니다.
3.  **숫자 형식**: 모든 숫자에서 쉼표(,)를 반드시 제거합니다.
    -   **[잘못된 예시]** `31,000` 또는 `1,234` 또는 `2,500,000달러` 또는 `$3,200~$3,500`
    -   **[올바른 예시]** `31000` 또는 `1234` 또는 `2500000달러` 또는 `$3200~$3500`
4.  **속성 쌍 생성**: `속성` 컬럼은 반드시 `속성명:속성값` 형식으로 작성합니다. 둘 중 하나가 없으면 해당 속성은 생략합니다.
    -   **[예시]** `국가:중국` 또는 `시기:2025년`
    -   **[잘못된 예시]** `중국` 또는 `2025년`
5.  **다중 속성 형식**: 속성이 여러 개일 경우, 각 속성명과 속성값을 세미콜론(`;`)으로 구분하여 각 컬럼에 나열합니다.
    -   **[예시]** `속성` 컬럼에 `국가:중국;시기:2025년`과 같이 작성합니다.
6.  하나의 `속성명` 안에 여러 `속성값`이 있을 경우, 파이프(|)를 사용하여 구분합니다.
    -   **[잘못된 예시]** `국가:중국,미국` 또는 `국가:중국,미국,시기:2025년`
    -   **[올바른 예시]** `국가:중국|미국` 또는 `국가:중국|미국;시기:2025년`
7.  **시기 정보**: 문서에 "2025년", "2024년 3월" 등 특정 시기 정보가 있다면, 반드시 `시기`라는 속성명으로 추출하여 속성에 포함합니다.
8.  **중복 금지**: `엔터티1`과 `엔터티2`는 서로 달라야 합니다. (`엔터티1 ≠ 엔터티2`)
9.  **문서 제목 활용**: 문서의 제목(보통 첫 줄)에서 주요 정보를 파악하여, 모든 행의 속성에 기본 정보(예: `국가:중국;시기:2025년 3월`)를 일관되게 포함시켜 컨텍스트를 유지합니다.
10. **관계 없는 엔터티 제외**: 문서에 등장하더라도 다른 엔터티와 관계를 맺지 않는 엔터티는 출력하지 않습니다.


문서:
{final_text}
"""

# 모든 txt 파일 처리
for file_path in txt_files:
    with open(file_path, "r", encoding="utf-8") as f:
        final_text = f.read().strip()

    # 빈 파일인 경우 건너뜀
    if not final_text:
        print(f"⚠️ {base_name}.txt 파일이 비어있습니다. 건너뜁니다.")
        continue

    # 프롬프트 생성
    prompt = prompt_template.format(final_text=final_text)

    # Gemini → OpenAI Fallback 호출
    messages = [
        {"role": "system", "content": "당신은 문서 분석 및 엔터티 관계 추출 전문가입니다. "
                "현재 당신은 식품 분야의 Knowledge Graph를 구축 중이며, "
                "문서에 등장하는 엔터티와 관계를 식품 데이터 관점에서 분석해야 합니다. "
                "식품 품목, 원산지, 시간(연도) 정보 등을 정확하게 식별하고, "
                "관계와 그 관계의 속성을 명확하게 추출해 주세요."},
        {"role": "user", "content": prompt}
    ]
    
    gpt_output = OpenAIClientFallbackManager.chat_completions_create_with_fallback(
        model="document-analysis",  # 대용량 문서 처리용 모델 (gemini-1.5-pro, 2M context)
        messages=messages,
        temperature=0
    )

    # 응답은 이미 gpt_output 변수에 저장됨

    # CSV 저장 경로
    base_name = os.path.splitext(os.path.basename(file_path))[0]
    output_csv_path = os.path.join(output_folder, base_name + ".csv")

    # GPT 출력이 CSV이므로 그대로 저장
    with open(output_csv_path, "w", encoding="utf-8", newline="") as csvfile:
        csvfile.write(gpt_output)

    print(f"✅ {base_name} → {output_csv_path} 저장 완료")

print(f"총 {len(txt_files)}개 TXT 파일 처리 완료")
