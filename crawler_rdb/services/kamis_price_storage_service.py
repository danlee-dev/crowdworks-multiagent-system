import psycopg2
import os
import datetime
from dotenv import load_dotenv
from db.auto_table_creator import create_table_if_not_exists, get_table_name_from_script

load_dotenv()

def is_effectively_empty(row: dict) -> bool:
    for val in row.values():
        if isinstance(val, str) and val.strip().lower() in ("", "null", "none"):
            continue
        if val not in (None, "", [], {}, "null", "none"):
            return False
    return True

def parse_regday(value) -> datetime.date:
    if isinstance(value, datetime.date):
        return value
    if isinstance(value, str):
        value = value.strip()
        for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y%m%d"):
            try:
                return datetime.datetime.strptime(value, fmt).date()
            except ValueError:
                continue
    return datetime.date.today()

def to_float(val):
    if isinstance(val, str):
        val = val.replace(",", "").replace(" ", "")
        try:
            return float(val)
        except:
            return None
    return val

def normalize_string(s):
    return s.strip().replace(" ", "") if isinstance(s, str) else s

def insert_kamis_data_to_db(data_list, script_path):
    if not data_list:
        print("⚠️ 저장할 데이터가 없습니다.")
        return

    # ✅ 중복 제거 (latest_day, productName, item_name, unit 기준)
    seen = set()
    unique_data = []
    for row in data_list:
        key = (
            parse_regday(row.get("lastest_day")),
            normalize_string(row.get("productName")),
            normalize_string(row.get("item_name")),
            normalize_string(row.get("unit"))
        )
        if key not in seen:
            seen.add(key)
            unique_data.append(row)

    table_name = get_table_name_from_script(script_path)
    create_table_if_not_exists(data_list=unique_data, script_path=script_path)

    conn = psycopg2.connect(
        dbname=os.getenv("POSTGRES_DB"),
        user=os.getenv("POSTGRES_USER"),
        password=os.getenv("POSTGRES_PASSWORD"),
        host=os.getenv("POSTGRES_HOST"),
        port=os.getenv("POSTGRES_PORT")
    )
    cur = conn.cursor()

    cur.execute(f"""
        SELECT column_name FROM information_schema.columns 
        WHERE table_name = '{table_name}';
    """)
    existing_columns = set(row[0] for row in cur.fetchall())

    success_insert = 0
    success_update = 0

    for row in unique_data:
        if is_effectively_empty(row):
            print("⚠️ 무의미한 row 건너뜀:", row)
            continue

        row["regday"] = datetime.date.today()
        item_name = normalize_string(row.get("item_name"))
        product_name = normalize_string(row.get("productName"))
        unit = normalize_string(row.get("unit"))
        latest_day = parse_regday(row.get("lastest_day"))

        cur.execute(f"""
            SELECT "dpr1", "dpr2", "dpr3", "dpr4", "direction", "value"
            FROM "{table_name}"
            WHERE "item_name" = %s AND "productName" = %s AND "unit" = %s AND "lastest_day" = %s
        """, (item_name, product_name, unit, latest_day))
        existing = cur.fetchone()

        if existing:
            new_values = [
                to_float(row.get("dpr1")),
                to_float(row.get("dpr2")),
                to_float(row.get("dpr3")),
                to_float(row.get("dpr4")),
                to_float(row.get("direction")),
                to_float(row.get("value"))
            ]
            if list(existing) != new_values:
                cur.execute(f"""
                    UPDATE "{table_name}"
                    SET "dpr1" = %s, "dpr2" = %s, "dpr3" = %s, "dpr4" = %s, "direction" = %s, "value" = %s
                    WHERE "item_name" = %s AND "productName" = %s AND "unit" = %s AND "lastest_day" = %s
                """, new_values + [item_name, product_name, unit, latest_day])
                success_update += 1
        else:
            keys = [k for k in row.keys() if k in existing_columns]
            values = []
            for k in keys:
                v = row[k]
                if isinstance(v, str):
                    v = v.strip().replace(",", "").replace(" ", "")
                    try:
                        v = float(v)
                    except:
                        pass
                values.append(v)

            columns = ",".join(f'"{k}"' for k in keys)
            placeholders = ",".join(["%s"] * len(values))
            sql = f'INSERT INTO "{table_name}" ({columns}) VALUES ({placeholders})'

            try:
                cur.execute(sql, values)
                success_insert += 1
            except Exception as e:
                print(f"❌ 저장 실패 (무시됨): {e}")
                print(f"⛔ 실패한 데이터: {row}")
                conn.rollback()

    if success_insert > 0 or success_update > 0:
        conn.commit()
        print(f"✅ 저장 성공: {success_insert}건 삽입, {success_update}건 업데이트")
    else:
        print("⚠️ 저장된 데이터가 없습니다.")

    cur.close()
    conn.close()
