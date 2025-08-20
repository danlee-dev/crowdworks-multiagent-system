import argparse
import time
import os
from services.kamis_price_storage_service import insert_kamis_data_to_db
from crawler.kamis_product_price_latest import crawl_kamis_product_price_latest
from services.nutrition_facts_service import insert_nutrition_facts_data

# 시세 크롤러 등록
CRAWLER_REGISTRY = {
    "kamis-latest": {
        "function": crawl_kamis_product_price_latest,
        "description": "KAMIS - 최근일자 도소매 시세",
        "handler": insert_kamis_data_to_db
    }
}


def main():
    parser = argparse.ArgumentParser(description="🧺 농축수산물 시세/영양정보 크롤러 실행기")
    parser.add_argument("--crawler", type=str, choices=CRAWLER_REGISTRY.keys(), help="시세 크롤러 실행")
    parser.add_argument("--mode", type=str, choices=["nutrition-facts"], help="기타 모드 실행")
    parser.add_argument("--list", action="store_true", help="사용 가능한 시세 크롤러 목록 보기")

    args = parser.parse_args()

    # ✅ nutrition-facts 실행 (OpenAI 기반)
    if args.mode == "nutrition-facts":
        start = time.time()
        print("\n🥗 영양성분표(nutrition_facts) 처리 시작")
        try:
            insert_nutrition_facts_data('./data/국가표준식품성분표_250426공개.xlsx')
        except Exception as e:
            print(f"❌ 오류 발생: {e}")
        print(f"⏱️ 총 소요 시간: {time.time() - start:.2f}초")
        return

    if args.list:
        print("\n📦 사용 가능한 시세 크롤러 목록:\n")
        for key, val in CRAWLER_REGISTRY.items():
            print(f"  {key:<22} → {val['description']}")
        return

    if not args.crawler:
        print("❌ --crawler 또는 --mode 옵션을 지정하거나 --list로 목록을 확인하세요.")
        return

    selected = CRAWLER_REGISTRY[args.crawler]
    print(f"\n🚀 실행 중: {args.crawler} ({selected['description']})")
    start = time.time()

    try:
        data = selected["function"]()

        if data:
            handler = selected.get("handler")
            if handler:
                if "category" in selected and "unit" in selected:
                    handler(data, category=selected["category"], unit=selected["unit"])
                else:
                    handler(data, script_path=selected["function"].__code__.co_filename)
            print(f"✅ DB 저장 완료 (총 {len(data)}건)")
        else:
            print("⚠️ 가져온 데이터가 없습니다.")
    except Exception as e:
        print(f"❌ 오류 발생: {e}")

    print(f"⏱️ 총 소요 시간: {time.time() - start:.2f}초")


if __name__ == "__main__":
    main()
