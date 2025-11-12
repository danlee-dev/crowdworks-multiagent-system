from playwright.sync_api import sync_playwright
import requests
from pathlib import Path
from urllib.parse import urljoin
import re
import time
from datetime import datetime, timedelta
import json

BASE_URL = "https://www.kati.net/board/etcReportList.do?menu_dept3=367"
DOWNLOAD_DIR = Path("ReportPDF")
REFERENCE_PATH = Path("/elasticsearch/referenceURL.json")

DOWNLOAD_DIR.mkdir(exist_ok=True)
REFERENCE_PATH.parent.mkdir(parents=True, exist_ok=True)

# referenceURL.json 로딩
if REFERENCE_PATH.exists():
    with open(REFERENCE_PATH, "r", encoding="utf-8") as f:
        reference_data = json.load(f)
else:
    reference_data = {}

def save_reference(filename: str, detail_url: str):
    if filename in reference_data:
        print(f"      · referenceURL.json에 이미 있음: {filename} → 건너뜁니다.")
        return
    reference_data[filename] = detail_url
    with open(REFERENCE_PATH, "w", encoding="utf-8") as f:
        json.dump(reference_data, f, ensure_ascii=False, indent=2)
    print(f"      📝 referenceURL.json에 추가됨: {filename}")

# 30일 전 기준일
threshold = datetime.now() - timedelta(days=30)

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        print(f"🌐 이동: {BASE_URL}")
        page.goto(BASE_URL, wait_until="domcontentloaded", timeout=60000)
        print(f"✅ 페이지 도착: {page.title()}")

        page_num = 1
        while True:
            print(f"\n📄 페이지 {page_num}")
            report_items = page.query_selector_all("div.report-row div.report-item")
            print(f"🔍 {len(report_items)}개의 보고서 발견")

            for idx, item in enumerate(report_items, start=1):
                title = item.query_selector("em.report-tit").inner_text().strip()
                raw_date = item.query_selector("span.report-date").inner_text().strip()

                m = re.search(r"\d{4}-\d{2}-\d{2}", raw_date)
                if not m:
                    print(f"⚠️ 날짜 형식 이상 ({raw_date}) → 스킵")
                    continue
                date_str = m.group(0)
                print(f"\n▶️ [{idx}] {date_str} | {title}")

                published = datetime.strptime(date_str, "%Y-%m-%d")
                if published < threshold:
                    print(f"🚫 게시일 {published.date()} (< {threshold.date()}) → 전체 종료")
                    browser.close()
                    return

                if "2023" in title:
                    print("🚫 2023년 자료 → 스킵")
                    continue

                link = item.query_selector("div.download-area a[href*='file/down.do']")
                if not link:
                    print("⚠️ 다운로드 링크 없음 → 스킵")
                    continue

                href = link.get_attribute("href")
                full_url = href if href.startswith("http") else urljoin(BASE_URL, href)

                safe_name = re.sub(r'[\\/:*?"<>|]', "_", f"{title}.pdf")
                out_path = DOWNLOAD_DIR / safe_name

                if out_path.exists():
                    print("✔️ 이미 존재 → 스킵")
                    continue

                print(f"⬇️ 다운로드 중: {safe_name}")
                try:
                    res = requests.get(full_url, stream=True, timeout=60)
                    res.raise_for_status()
                    with open(out_path, "wb") as f:
                        for chunk in res.iter_content(1024):
                            if chunk:
                                f.write(chunk)
                    print(f"✅ 저장됨: {out_path}")
                    save_reference(safe_name, full_url)
                except Exception as e:
                    print(f"❌ 다운로드 실패: {e}")

            # 다음 페이지 찾기
            next_el = page.query_selector("div.paging a.current + a")
            onclick = next_el.get_attribute("onclick") if next_el else None
            if not onclick:
                print("✅ 마지막 페이지 도달 → 종료")
                break

            m2 = re.search(r"getPaging\((\d+)\)", onclick)
            if not m2:
                print("⚠️ 다음 페이지 번호 없음 → 종료")
                break

            next_page = int(m2.group(1))
            print(f"➡️ 다음 페이지로 이동: {next_page}")
            page.evaluate("num => getPaging(num)", next_page)
            time.sleep(1.5)
            page_num = next_page

        print("\n🎉 모든 다운로드 완료!")
        browser.close()

if __name__ == "__main__":
    main()
