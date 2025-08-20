import pandas as pd
import re
import numpy as np

def clean_column_name(name: str) -> str:
    """컬럼명을 DB에 적합하게 정제합니다."""
    name = str(name)
    # 개행 문자 및 불필요한 공백 제거
    name = name.replace("\n", " ").replace("\r", " ").replace("\t", " ")
    name = re.sub(r"\s+", " ", name).strip()
    # 단위 통일
    name = name.replace("(mg)", "(mg/100g)").replace("(g)", "(g/100g)")
    name = name.replace("(kcal)", "(kcal/100g)")
    name = name.replace("(μg)", "(μg/100g)").replace("(ug)", "(μg/100g)")
    # 엑셀의 멀티헤더에서 발생하는 불필요한 부분 제거
    name = re.sub(r"\s*\(Unnamed:.*?\)", "", name)
    # 보이지 않는 공백 문자 제거
    name = name.replace("\u200b", "").replace(" ", " ")
    return name.strip()

def get_table_column_mapping(all_columns: list[str]) -> dict:
    """
    전체 컬럼 리스트를 받아 테이블별로 정확히 그룹화된 컬럼 맵을 반환합니다.
    """
    # 각 테이블에 속하는 컬럼들을 명시적으로 정의
    table_definitions = {
        "foods": [
            "DB10.2 색인", "10개정 책자 색인", "식품군", "식품명", "출처", "폐기율_percent" # '%' 기호 제거
        ],
        "proximates": [
            "에너지 (kcal/100g)", "수분 (g/100g)", "단백질 (g/100g)", "지방 (g/100g)", "회분 (g/100g)",
            "탄수화물 (g/100g)", "당류 (g/100g)", "자당 (g/100g)", "포도당 (g/100g)", "과당 (g/100g)",
            "유당 (g/100g)", "맥아당 (g/100g)", "갈락토오스 (g/100g)", "총 식이섬유 (g/100g)",
            "수용성 식이섬유 (g/100g)", "불용성 식이섬유 (g/100g)", "식염상당량 (g/100g)"
        ],
        "minerals": [
            "칼슘 (mg/100g)", "철 (mg/100g)", "마그네슘 (mg/100g)", "인 (mg/100g)", "칼륨 (mg/100g)",
            "나트륨 (mg/100g)", "아연 (mg/100g)", "구리 (mg/100g)", "망간 (mg/100g)", "셀레늄 (μg/100g)",
            "몰리브덴 (μg/100g)", "요오드 (μg/100g)"
        ],
        "vitamins": [
            "비타민 A (μg/100g)", "레티놀 (μg/100g)", "베타카로틴 (μg/100g)", "티아민 (mg/100g)",
            "리보플라빈 (mg/100g)", "니아신 (mg/100g)", "니아신당량(NE) (mg/100g)", "니코틴산 (mg/100g)",
            "니코틴아미드 (mg/100g)", "판토텐산 (mg/100g)", "비타민 B6 (mg/100g)", "피리독신 (mg/100g)",
            "비오틴 (μg/100g)", "엽산_ 엽산당량 (μg/100g)", "엽산_ 식품 엽산 (μg/100g)",
            "엽산_ 합성 엽산 (μg/100g)", "비타민 B12 (μg/100g)", "비타민 C (mg/100g)", "비타민 D (μg/100g)",
            "비타민 D2 (μg/100g)", "비타민 D3 (μg/100g)", "비타민 E (mg/100g)", "알파 토코페롤 (mg/100g)",
            "베타 토코페롤 (mg/100g)", "감마 토코페롤 (mg/100g)", "델타 토코페롤 (mg/100g)",
            "알파 토코트리에놀 (mg/100g)", "베타 토코트리에놀 (mg/100g)", "감마 토코트리에놀 (mg/100g)",
            "델타 토코트리에놀 (mg/100g)", "비타민 K (μg/100g)", "비타민 K1 (μg/100g)", "비타민 K2 (μg/100g)"
        ],
        "amino_acids": [
            "총 아미노산 (mg/100g)", "총 필수 아미노산 (mg/100g)", "이소류신 (mg/100g)", "류신 (mg/100g)",
            "라이신 (mg/100g)", "메티오닌 (mg/100g)", "페닐알라닌 (mg/100g)", "트레오닌 (mg/100g)",
            "트립토판 (mg/100g)", "발린 (mg/100g)", "히스티딘 (mg/100g)", "아르기닌 (mg/100g)",
            "티로신 (mg/100g)", "시스테인 (mg/100g)", "알라닌 (mg/100g)", "아스파르트산 (mg/100g)",
            "글루탐산 (mg/100g)", "글라이신 (mg/100g)", "프롤린 (mg/100g)", "세린 (mg/100g)", "타우린 (mg/100g)"
        ],
        "fatty_acids": [
            "콜레스테롤 (mg/100g)", "총 지방산 (g/100g)", "총 필수 지방산 (g/100g)", "총 포화 지방산 (g/100g)",
            "부티르산 (4:0) (mg/100g)", "카프로산 (6:0) (mg/100g)", "카프릴산 (8:0) (mg/100g)",
            "카프르산 (10:0) (mg/100g)", "라우르산 (12:0) (mg/100g)", "트라이데칸산 (13:0) (mg/100g)",
            "미리스트산 (14:0) (mg/100g)", "펜타데칸산 (15:0) (mg/100g)", "팔미트산 (16:0) (mg/100g)",
            "헵타데칸산 (17:0) (mg/100g)", "스테아르산 (18:0) (mg/100g)", "아라키드산 (20:0) (mg/100g)",
            "헨에이코산산 (21:0) (mg/100g)", "베헨산 (22:0) (mg/100g)", "트리코산산 (23:0) (mg/100g)",
            "리그노세르산 (24:0) (mg/100g)", "총 불포화 지방산 (g/100g)", "총 단일 불포화지방산 (g/100g)",
            "미리스톨레산 (14:1) (mg/100g)", "팔미톨레산 (16:1) (mg/100g)", "헵타데센산 (17:1) (mg/100g)",
            "올레산 (18:1(n-9)) (mg/100g)", "박센산 (18:1(n-7)) (mg/100g)", "가돌레산 (20:1) (mg/100g)",
            "에루크산 (22:1) (mg/100g)", "네르본산 (24:1) (mg/100g)", "총 다가 불포화지방산 (g/100g)",
            "리놀레산 (18:2(n-6)) (mg/100g)", "알파 리놀렌산 (18:3 (n-3)) (mg/100g)",
            "감마 리놀렌산 (18:3 (n-6)) (mg/100g)", "에이코사 디에노산 (20:2(n-6)) (mg/100g)",
            "디호모 리놀렌산 (20:3(n-3)) (mg/100g)", "에이코사 트리에노산 (20:3(n-6)) (mg/100g)",
            "아라키돈산 (20:4(n-6)) (mg/100g)", "에이코사 펜타에노산 (20:5(n-3)) (mg/100g)",
            "도코사 디에노산(22:2) (mg/100g)", "도코사 펜타에노산 (22:5(n-3)) (mg/100g)",
            "도코사 헥사에노산 (22:6(n-3)) (mg/100g)", "오메가3 지방산 (g/100g)", "오메가6 지방산 (g/100g)",
            "총 트랜스 지방산 (g/100g)", "트랜스 올레산(18:1(n-9)t) (mg/100g)",
            "트랜스 리놀레산(18:2t) (mg/100g)", "트랜스 리놀렌산(18:3t) (mg/100g)"
        ]
    }

    # 빠른 조회를 위해 컬럼명 -> 테이블명 역방향 맵 생성
    column_to_table_map = {}
    for table_name, columns in table_definitions.items():
        for column in columns:
            column_to_table_map[column] = table_name

    # 최종적으로 반환할 맵 구조 초기화
    final_mapping = {
        "foods": [], "proximates": [], "minerals": [],
        "vitamins": [], "amino_acids": [], "fatty_acids": [],
    }

    # 엑셀에서 읽어온 모든 컬럼을 순회하며 매핑
    for col in all_columns:
        table = column_to_table_map.get(col)
        if table:
            final_mapping[table].append(col)
        else:
            # 어떤 테이블에도 속하지 않는 컬럼이 있다면 경고 메시지 출력
            print(f"⚠️ 경고: '{col}' 컬럼이 어떤 테이블에도 할당되지 않았습니다.")

    return final_mapping

def load_nutrition_facts(file_path: str, sheet_name="국가표준식품성분 Database 10.2"):
    """
    엑셀 데이터를 로드하고, 모든 숫자 컬럼을 안정적으로 정제하여 DataFrame으로 반환합니다.
    """
    print(f"📥 엑셀 로딩 중: {file_path}")
    df = pd.read_excel(file_path, sheet_name=sheet_name, header=[1, 2])
    # 멀티 레벨 헤더를 병합하고 빈 값을 채움
    df.columns = df.columns.to_frame().ffill().apply(tuple, axis=1)
    print(f"📊 원본 shape: {df.shape}, columns: {len(df.columns)}")

    # 컬럼명 정제 및 생성
    column_names = []
    seen = set()
    for i, (c1, c2) in enumerate(df.columns):
        base = f"{str(c1)} ({str(c2)})" if not pd.isna(c2) and "Unnamed" not in str(c2) else str(c1)
        clean = clean_column_name(base)
        
        # 특수한 경우 컬럼명 강제 할당
        if i == 87:
            clean = "콜레스테롤 (mg/100g)"
        elif i == 135:
            clean = "식염상당량 (g/100g)"
        elif i == 136:
            # --- [FIX] ---
            # '%' 기호가 포함된 컬럼명을 DB 친화적으로 변경
            clean = "폐기율_percent"
            # --- [END OF FIX] ---
        
        # 중복 컬럼명 처리
        original = clean
        suffix = 1
        while clean in seen:
            clean = f"{original}_{suffix}"
            suffix += 1
        seen.add(clean)
        column_names.append(clean)

    # 최종 컬럼명 리스트에서 다시 한번 공백 제거
    column_names = [re.sub(r"[\n\r\t\xa0\u200b]", " ", c).strip() for c in column_names]
    df.columns = column_names
    
    # DB에 NULL로 넣어야 할 값들을 np.nan으로 변환
    df = df.replace(["-", "", "Tr", "( )"], np.nan) 

    # 숫자형이어야 하는 컬럼들을 명시적으로 찾아 숫자 타입으로 변경 (오류 시 NaN 처리)
    numeric_cols = [
        col for col in df.columns 
        if any(key in col for key in ["색인", "코드", "(g/100g)", "(mg/100g)", "(μg/100g)", "(kcal/100g)", "(%)", "_percent"])
    ]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors='coerce')

    # DataFrame 전체의 np.nan 값을 파이썬의 None으로 최종 변환
    df = df.where(pd.notnull(df), None)
    df = df.reset_index(drop=True)

    print(f"\n✅ 정제된 shape: {df.shape}, 최종 컬럼 수: {len(df.columns)}")
    
    return df
