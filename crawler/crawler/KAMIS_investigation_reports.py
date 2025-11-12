from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
import requests
from pathlib import Path
from urllib.parse import urljoin
import time
from datetime import datetime, timedelta
import re
import json

BASE_DOMAIN = "https://www.kamis.or.kr"
TAB_PATHS = [
    "/customer/nature/domestic.do",
    "/customer/nature/agriculture.do",
    "/customer/nature/schoolfood.do",
    "/customer/nature/market.do",
    "/customer/nature/customer.do",
    "/customer/nature/overseas.do",
]
DOWNLOAD_DIR = Path("/ReportPDF")
DOWNLOAD_DIR.mkdir(exist_ok=True)

REFERENCE_PATH = Path("/elasticsearch/referenceURL.json")
REFERENCE_PATH.parent.mkdir(parents=True, exist_ok=True)

# 30일 전 기준일
threshold = datetime.now() - timedelta(days=30)

# referenceURL.json 로딩
if REFERENCE_PATH.exists():
    with open(REFERENCE_PATH, "r", encoding="utf-8") as f:
        reference_data = json.load(f)
else:
    reference_data = {}

session = requests.Session()
session.headers.update({"User-Agent": "Mozilla/5.0"})

def fetch_with_retry(url, retries=3, backoff=3):
    for attempt in range(1, retries + 1):
        try:
            r = session.get(url, stream=True, timeout=30)
            r.raise_for_status()
            return r
        except Exception as e:
            print(f"    ⚠️ 시도 {attempt} 실패: {e}")
            if attempt == retries:
                raise
            time.sleep(backoff)

def process_item(page, idx):
    """
    클릭 → 작성일 체크 → 30일 이내면 다운로드
    30일 이전이면 False 반환 → 이 탭(loop) 건너뛸 신호
    """
    items = page.query_selector_all("ul.thum_list li:not(.no_data)")
    item = items[idx]
    item.click()
    try:
        page.wait_for_load_state("networkidle", timeout=30000)
    except PlaywrightTimeoutError:
        page.wait_for_load_state("domcontentloaded")

    # 작성일 읽기 (XPath)
    date_td = page.query_selector(
        "//th[normalize-space(text())='작성일']/following-sibling::td"
    )
    if not date_td:
        print("    ⚠️ 작성일을 찾을 수 없음 → 이 페이지만 스킵")
        page.go_back(wait_until="networkidle")
        return True

    date_text = date_td.inner_text().strip()
    try:
        published = datetime.strptime(date_text, "%Y-%m-%d")
    except ValueError:
        print(f"    ⚠️ 날짜 파싱 실패 ({date_text}) → 이 페이지만 스킵")
        page.go_back(wait_until="networkidle")
        return True

    if published < threshold:
        print(f"    ⚠️ 게시일 {published.date()} (< {threshold.date()}) → 이 탭 건너뜀")
        page.go_back(wait_until="networkidle")
        return False  # signal to skip rest of this tab

    # PDF 링크 & 다운로드
    link = page.query_selector("ul.file_li li a")
    if not link:
        print("    ❌ PDF 링크 없음 → 뒤로")
        page.go_back(wait_until="networkidle")
        return True

    href = link.get_attribute("href")
    title = link.get_attribute("title") or link.inner_text().strip() or "unknown.pdf"
    pdf_url = href if href.startswith("http") else urljoin(BASE_DOMAIN, href)

    safe = re.sub(r'[\\/:*?"<>|]', "_", title)
    if not safe.lower().endswith(".pdf"):
        safe += ".pdf"
    out = DOWNLOAD_DIR / safe

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

    # referenceURL 기록
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

        for tab_path in TAB_PATHS:
            tab_url = f"{BASE_DOMAIN}{tab_path}"
            print(f"\n==============\n▶ 탭: {tab_url}")
            page.goto(tab_url, wait_until="networkidle")
            time.sleep(1)

            page_idx = 1
            while True:
                print(f"\n📄 페이지 {page_idx}")
                if page.query_selector("ul.thum_list li.no_data"):
                    print("  ⚠️ 데이터 없음 → 탭 종료")
                    break

                items = page.query_selector_all("ul.thum_list li:not(.no_data)")
                total = len(items)
                print(f"  → {total}개 항목 발견")

                # 이 탭에서 날짜 미달 시 빠져나오는 플래그
                skip_tab = False

                for idx in range(total):
                    print(f"  ▶ [{idx+1}/{total}] 처리 중…")
                    ok = process_item(page, idx)
                    if not ok:
                        skip_tab = True
                        break

                if skip_tab:
                    print("  ⏭️ 이 탭 건너뛰고 다음 탭으로 이동합니다.")
                    break  # exit while True for this tab

                # 다음 페이지 이동
                page_idx += 1
                next_url = f"{tab_url}?action=list&pagenum={page_idx}"
                print(f"➡️ 다음 페이지: {next_url}")
                page.goto(next_url, wait_until="networkidle")
                time.sleep(1)

        browser.close()
        print("\n🎉 모든 PDF 다운로드 및 referenceURL 기록 완료!")

if __name__ == "__main__":
    main()
