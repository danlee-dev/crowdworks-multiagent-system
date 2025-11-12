from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
import requests
from pathlib import Path
from urllib.parse import urljoin
import time
from datetime import datetime, timedelta
import re
import json

BASE_URL = "https://www.kamis.or.kr/customer/trend/foreign_info/foreign_info.do"
DOWNLOAD_DIR = Path("/ReportPDF")
REFERENCE_PATH = Path("/elasticsearch/referenceURL.json")

DOWNLOAD_DIR.mkdir(exist_ok=True)
REFERENCE_PATH.parent.mkdir(parents=True, exist_ok=True)

# 기준일: 30일 전
threshold = datetime.now() - timedelta(days=30)

# referenceURL.json 로드
if REFERENCE_PATH.exists():
    with open(REFERENCE_PATH, "r", encoding="utf-8") as f:
        reference_data = json.load(f)
else:
    reference_data = {}

session = requests.Session()
session.headers.update({"User-Agent": "Mozilla/5.0"})

def fetch_with_retry(url, retries=3, backoff=3):
    for i in range(retries):
        try:
            r = session.get(url, stream=True, timeout=30)
            r.raise_for_status()
            return r
        except Exception as e:
            print(f"    ⚠️ 시도 {i+1} 실패: {e}")
            time.sleep(backoff)
    raise RuntimeError("최종 다운로드 실패")

def process_item(page, idx):
    items = page.query_selector_all("ul.thum_list li")
    item = items[idx]
    item.click()
    try:
        page.wait_for_load_state("networkidle", timeout=30000)
    except PlaywrightTimeoutError:
        page.wait_for_load_state("domcontentloaded")

    # 작성일 추출
    row = page.query_selector_all("table.tbl.row.board tbody tr")[1]
    tds = row.query_selector_all("td")
    if len(tds) < 2:
        print("    ❌ 작성일 셀을 찾을 수 없음 → 전체 종료")
        return False

    date_txt = tds[1].inner_text().strip()
    try:
        published = datetime.strptime(date_txt, "%Y-%m-%d")
    except ValueError:
        print(f"    ⚠️ 날짜 파싱 실패 ({date_txt}) → 이 페이지만 스킵")
        page.go_back(wait_until="networkidle")
        return True

    if published < threshold:
        print(f"    ⚠️ 게시일 {published.date()} (< {threshold.date()}) → 전체 종료")
        return False

    # 링크 및 파일명 추출
    link = page.query_selector("ul.file_li li a")
    if not link:
        print("    ❌ PDF 링크 없음 → 뒤로")
        page.go_back(wait_until="networkidle")
        return True

    href = link.get_attribute("href")
    title = link.get_attribute("title") or link.inner_text().strip() or "unknown.pdf"
    pdf_url = href if href.startswith("http") else urljoin(BASE_URL, href)

    safe = re.sub(r'[\\/:*?"<>|]', '_', title)
    if not safe.lower().endswith(".pdf"):
        safe += ".pdf"
    out = DOWNLOAD_DIR / safe

    # 이미 존재하면 스킵
    if out.exists():
        print(f"    · 이미 존재: {safe}")
    else:
        print(f"    ↓ 다운로드 중: {safe}")
        try:
            resp = fetch_with_retry(pdf_url)
            with open(out, "wb") as f:
                for chunk in resp.iter_content(1024):
                    if chunk:
                        f.write(chunk)
            print(f"      ✅ 저장됨: {safe}")
        except Exception as e:
            print(f"      ❌ 다운로드 실패: {e}")
            page.go_back(wait_until="networkidle")
            return True

    # referenceURL.json 기록
    if safe in reference_data:
        print(f"    · referenceURL.json에 이미 있음: {safe}")
    else:
        reference_data[safe] = page.url
        with open(REFERENCE_PATH, "w", encoding="utf-8") as f:
            json.dump(reference_data, f, ensure_ascii=False, indent=2)
        print(f"    📝 referenceURL.json에 추가됨: {safe}")

    page.go_back(wait_until="networkidle")
    time.sleep(1)
    return True

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        print(f"✅ 시작: {BASE_URL}")
        page.goto(BASE_URL, wait_until="networkidle")
        time.sleep(1)

        page_idx = 1
        while True:
            print(f"\n📄 리스트 페이지 {page_idx}")
            if page.query_selector("ul.thum_list li.no_data"):
                print("  ⚠️ 데이터 없음 → 종료")
                break

            total = len(page.query_selector_all("ul.thum_list li"))
            print(f"  → {total}개 항목 발견")

            for idx in range(total):
                print(f"  ▶ [{idx+1}/{total}] 처리 중…")
                ok = process_item(page, idx)
                if not ok:
                    browser.close()
                    return

            page_idx += 1
            next_url = f"{BASE_URL}?action=list&pagenum={page_idx}"
            print(f"➡️ 다음 리스트 페이지: {next_url}")
            page.goto(next_url, wait_until="networkidle")
            time.sleep(1)

        browser.close()
        print("\n🎉 완료!")

if __name__ == "__main__":
    main()
