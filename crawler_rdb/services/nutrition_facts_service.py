import traceback
import math
import time
import numpy as np  # numpy 타입 확인을 위해 추가
import pandas as pd  # pandas의 isna 함수 사용을 위해 추가
from db.database import get_connection
# DataFrame을 직접 사용하므로 load_nutrition_facts와 get_table_column_mapping만 import
from utils.nutrition_facts_parser import load_nutrition_facts, get_table_column_mapping

def get_column_type(name: str) -> str:
    """컬럼명에 따라 PostgreSQL 데이터 타입을 결정합니다."""
    if any(key in name for key in ["색인", "코드"]):
        return "BIGINT"
    elif any(key in name for key in ["출처", "식품군", "식품명"]):
        return "TEXT"
    # --- [FIX] ---
    # 변경된 컬럼명 '_percent'를 숫자 타입으로 인식하도록 추가
    elif any(unit in name for unit in ["(g/100g)", "(mg/100g)", "(μg/100g)", "(kcal/100g)", "(%)", "_percent"]):
    # --- [END OF FIX] ---
        return "DOUBLE PRECISION"
    return "TEXT"

def generate_create_table_sql(table_name: str, columns: list[str], primary_table: bool = False) -> str:
    """
    테이블 생성 SQL 쿼리를 동적으로 생성합니다.
    자식 테이블의 경우 food_id 외래 키를 추가합니다.
    """
    col_defs = [f'"{col}" {get_column_type(col)}' for col in columns]
    
    if primary_table:
        # foods 기본 테이블
        all_defs = ['"id" BIGSERIAL PRIMARY KEY'] + col_defs
    else:
        # 자식 영양성분 테이블
        all_defs = [
            '"id" BIGSERIAL PRIMARY KEY',
            # foods 테이블의 id를 참조하는 외래키. foods 데이터 삭제 시 관련 영양성분 데이터도 자동 삭제됨.
            '"food_id" BIGINT NOT NULL REFERENCES foods(id) ON DELETE CASCADE'
        ] + col_defs
        
    return f'CREATE TABLE IF NOT EXISTS "{table_name}" (\n  ' + ',\n  '.join(all_defs) + '\n);'

def sanitize_value(value):
    """
    DB에 들어가기 직전, 값을 DB 친화적인 파이썬 기본 타입으로 변환합니다.
    - pandas/numpy의 NA/NaN/None 값 -> None
    - numpy 숫자 타입 -> 파이썬 숫자 타입
    """
    # pd.isna는 None, np.nan, pd.NA 등을 모두 True로 처리하여 가장 안정적입니다.
    if pd.isna(value):
        return None
    
    # numpy의 정수형 타입(int64, int32 등)을 파이썬 int로 변환
    if isinstance(value, np.integer):
        return int(value)
    
    # numpy의 부동소수점 타입(float64, float32 등)을 파이썬 float으로 변환
    if isinstance(value, np.floating):
        return float(value)
    
    # 순수 파이썬 float의 nan 값 처리 (이중 안전장치)
    if isinstance(value, float) and math.isnan(value):
        return None
        
    return value

def insert_nutrition_facts_data(file_path: str):
    """엑셀 파일 데이터를 파싱하여 정규화된 DB 테이블들에 삽입합니다."""
    start_time = time.time()
    
    # 1. 데이터 로딩 및 테이블-컬럼 매핑
    df = load_nutrition_facts(file_path)
    table_column_map = get_table_column_mapping(df.columns.tolist())

    conn = get_connection()
    cur = conn.cursor()

    try:
        # 2. 테이블 구조 생성 (트랜잭션 외부에서 실행)
        print("\n===> 테이블 구조 생성을 시작합니다...")
        
        for table_name in reversed(list(table_column_map.keys())):
            cur.execute(f'DROP TABLE IF EXISTS "{table_name}" CASCADE;')
            print(f"  - 기존 '{table_name}' 테이블 삭제 완료.")

        for table_name, columns in table_column_map.items():
            is_primary = (table_name == "foods")
            create_sql = generate_create_table_sql(table_name, columns, primary_table=is_primary)
            cur.execute(create_sql)
            print(f"  - '{table_name}' 테이블 생성 완료.")
        
        conn.commit()

        # 3. 데이터 삽입 (새로운 트랜잭션 내에서 진행)
        print("\n===> 데이터 삽입을 시작합니다...")
        
        success_count = 0
        for idx, row in df.iterrows():
            food_cols = None
            food_values = None
            insert_food_sql = None
            try:
                # 3-1. 기본 'foods' 테이블에 데이터 삽입
                food_cols = table_column_map['foods']
                food_values = [sanitize_value(row[c]) for c in food_cols]
                
                food_cols_part = ", ".join([f'"{c}"' for c in food_cols])
                food_placeholders = ", ".join(["%s"] * len(food_cols))
                
                insert_food_sql = f'INSERT INTO "foods" ({food_cols_part}) VALUES ({food_placeholders}) RETURNING id;'
                cur.execute(insert_food_sql, tuple(food_values))
                
                result = cur.fetchone()
                if not result:
                    raise Exception("데이터 삽입 후 ID를 반환받지 못했습니다.")
                food_id = result[0]

                # 3-2. 나머지 자식 테이블에 데이터 삽입
                for table_name, columns in table_column_map.items():
                    if table_name == "foods":
                        continue
                    
                    child_values = [sanitize_value(row[c]) for c in columns]
                    
                    if all(v is None for v in child_values):
                        continue
                        
                    child_cols_part = ", ".join([f'"food_id"'] + [f'"{c}"' for c in columns])
                    child_placeholders = ", ".join(["%s"] * (len(columns) + 1))
                    
                    insert_child_sql = f'INSERT INTO "{table_name}" ({child_cols_part}) VALUES ({child_placeholders});'
                    cur.execute(insert_child_sql, (food_id,) + tuple(child_values))

                success_count += 1
                if (idx + 1) % 100 == 0:
                    print(f"  - {idx + 1}/{len(df)} 행 처리 중...")

            except Exception as e:
                # 오류 발생 시 상세한 디버깅 정보를 출력하도록 수정
                print(f"\n{'='*25}")
                print(f"🚨 오류 발생: {idx + 1}번째 행(Row) 처리 중 INSERT 실패!")
                db_error_message = e.diag.message_primary if hasattr(e, 'diag') else str(e)
                print(f"- 오류 메시지: {db_error_message}")
                print(f"- 오류 타입: {type(e).__name__}")
                print(f"\n[디버깅 정보]")
                print(f"1. 실행된 SQL:\n{insert_food_sql}")
                print(f"\n2. 컬럼 리스트 (총 {len(food_cols) if food_cols else 0}개):\n{food_cols}")
                print(f"\n3. 값 리스트 (총 {len(food_values) if food_values else 0}개):")
                if food_values and food_cols:
                    for col, val in zip(food_cols, food_values):
                        print(f"   - {col:<30} | 값: {val} (타입: {type(val).__name__})")
                print(f"{'='*25}\n")
                
                conn.rollback()
                raise

        conn.commit()
        print("\n✅ 모든 데이터가 성공적으로 삽입되어 커밋되었습니다.")

    except Exception as e:
        conn.rollback()
        print("\n❌ 작업 중 오류가 감지되어 모든 변경사항을 롤백했습니다.")
        # 전체 스크립트가 중단되었음을 알리기 위해 트레이스백 출력
        traceback.print_exc()

    finally:
        print(f"\n--- 최종 결과 ---")
        print(f"총 시도: {len(df)}행")
        print(f"성공: {success_count}행")
        
        cur.close()
        conn.close()
        end_time = time.time()
        print(f"⏱️ 총 소요 시간: {round(end_time - start_time, 2)}초")
