"""CGV 센텀시티 / 듄 파트 3 IMAX / 지정 날짜 예매 오픈 여부를 확인하고 카카오톡(나에게 보내기)으로 알림.

CGV 사이트는 해외(GitHub) 서버 접속을 차단하므로, 네이버 검색의 극장 상영시간표(CGV 데이터)를 읽는다.
"""
import json
import os
import re
import sys
from urllib.parse import quote

import requests
from playwright.sync_api import sync_playwright

TARGET_DATE = os.environ.get("TARGET_DATE", "2027-01-01")        # YYYY-MM-DD
SEARCH_QUERY = os.environ.get("SEARCH_QUERY", "CGV 센텀시티 상영시간표")
MOVIE_KEYWORDS = [k.strip() for k in os.environ.get("MOVIE_KEYWORDS", "듄").split(",") if k.strip()]
FORMAT_KEYWORD = os.environ.get("FORMAT_KEYWORD", "IMAX")
DEBUG = os.environ.get("DEBUG", "false").lower() == "true"
NOTIFY = os.environ.get("NOTIFY", "true").lower() == "true"
BOOK_URL = "https://cgv.co.kr/cnm/bzplcCgv/0089001"
SEARCH_URL = "https://search.naver.com/search.naver?query=" + quote(SEARCH_QUERY)


def sq(s):
    return re.sub(r"\s+", " ", s or "").strip()


def check():
    """returns (status, detail). status: 'imax' | 'movie_no_imax' | 'date_no_movie' | 'no_date'"""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(locale="ko-KR", viewport={"width": 1400, "height": 2200})
        pg = ctx.new_page()
        pg.goto(SEARCH_URL, wait_until="networkidle", timeout=60000)

        dates = pg.eval_on_selector_all(
            'a[href*="datefilter"]',
            "els => els.map(e => [e.getAttribute('href').match(/datefilter%3D([0-9-]+)|datefilter=([0-9-]+)/), e.innerText])",
        )
        date_list = []
        for m, txt in dates:
            d = next((x for x in (m or [])[1:] if x), None) if m else None
            date_list.append(d or txt)
        print("dates on page:", date_list)
        if not dates:
            raise RuntimeError("네이버 상영시간표 날짜 목록을 찾지 못함 (페이지 구조 변경?)")
        if not any(TARGET_DATE in (d or "") for d in date_list):
            browser.close()
            return "no_date", f"날짜 목록: {', '.join(str(d) for d in date_list)}"

        # 날짜 클릭 (새 탭으로 가는 기본 동작은 막고 페이지 내 핸들러만 실행)
        sel = f'a[href*="datefilter%3D{TARGET_DATE}"], a[href*="datefilter={TARGET_DATE}"]'
        pg.eval_on_selector(sel, "e => { e.addEventListener('click', ev => ev.preventDefault(), {once:true}); e.click(); }")
        pg.wait_for_timeout(2500)
        pressed = pg.eval_on_selector(sel, "e => e.getAttribute('aria-pressed')")
        print("target date pressed:", pressed)
        if pressed != "true":
            raise RuntimeError("대상 날짜 선택 실패")

        # 대상 날짜의 영화 목록에서 키워드 영화의 '상영시간표' 펼치기
        section = pg.locator('a[href*="datefilter"]').first.locator(
            "xpath=ancestor::*[.//*[contains(text(),'상영시간표')]][1]")
        sec_text = sq(section.inner_text())
        if DEBUG:
            print("SECTION:", sec_text[:1500])
        if not any(k in sec_text for k in MOVIE_KEYWORDS):
            # 영화 목록이 '더보기'로 접혀 있을 수 있음
            more = section.locator("text=더보기")
            if more.count():
                try:
                    more.first.evaluate("e => e.click()")
                    pg.wait_for_timeout(1500)
                    sec_text = sq(section.inner_text())
                except Exception:
                    pass
        if not any(k in sec_text for k in MOVIE_KEYWORDS):
            browser.close()
            return "date_no_movie", sec_text[:300]

        buttons = section.locator("text=상영시간표")
        detail = ""
        for i in range(buttons.count()):
            btn = buttons.nth(i)
            block = btn.locator("xpath=ancestor::*[self::li or self::div][.//*[contains(text(),'개봉')]][1]")
            try:
                bt = sq(block.inner_text())
            except Exception:
                continue
            if any(k in bt for k in MOVIE_KEYWORDS):
                btn.evaluate("e => e.click()")
                pg.wait_for_timeout(2000)
                detail = sq(block.inner_text())
                break
        print("movie block:", detail[:800])
        browser.close()
        if FORMAT_KEYWORD.lower() in detail.lower() and re.search(r"\d{1,2}:\d{2}", detail):
            return "imax", detail
        return "movie_no_imax", detail


def kakao_access_token():
    data = {
        "grant_type": "refresh_token",
        "client_id": os.environ["KAKAO_REST_API_KEY"],
        "refresh_token": os.environ["KAKAO_REFRESH_TOKEN"],
    }
    if os.environ.get("KAKAO_CLIENT_SECRET"):
        data["client_secret"] = os.environ["KAKAO_CLIENT_SECRET"]
    r = None
    for attempt in range(3):
        try:
            r = requests.post("https://kauth.kakao.com/oauth/token", data=data, timeout=40)
            break
        except requests.exceptions.RequestException as e:
            print(f"kakao token attempt {attempt+1} failed: {e}")
            if attempt == 2:
                raise
    print("kakao token:", r.status_code, r.text[:200] if r.status_code != 200 else "ok")
    r.raise_for_status()
    if "refresh_token" in r.json():
        print("::warning::카카오 refresh token이 갱신되었습니다. KAKAO_REFRESH_TOKEN 시크릿을 업데이트하세요.")
    return r.json()["access_token"]


def send_kakao(text):
    if not NOTIFY:
        print("[NOTIFY=false] would send:", text)
        return
    token = kakao_access_token()
    template = {
        "object_type": "text",
        "text": text[:200],
        "link": {"web_url": BOOK_URL, "mobile_web_url": BOOK_URL},
        "button_title": "CGV 예매하기",
    }
    for attempt in range(3):
        try:
            r = requests.post(
                "https://kapi.kakao.com/v2/api/talk/memo/default/send",
                headers={"Authorization": f"Bearer {token}"},
                data={"template_object": json.dumps(template, ensure_ascii=False)},
                timeout=40,
            )
            break
        except requests.exceptions.RequestException as e:
            print(f"kakao send attempt {attempt+1} failed: {e}")
            if attempt == 2:
                raise
    print("kakao:", r.status_code, r.text)
    r.raise_for_status()


def main():
    y, m, d = TARGET_DATE.split("-")
    pretty = f"{int(m)}월 {int(d)}일"
    status, detail = check()
    print("STATUS:", status)
    found = status == "imax"
    if found:
        times = " ".join(re.findall(r"IMAX[^0-9]*?((?:\d{1,2}:\d{2}\s*)+)", detail, flags=re.I)) or ""
        send_kakao(f"🎬 예매 오픈!\nCGV 센텀시티 듄: 파트 3 IMAX\n{pretty} 회차가 열렸습니다.\n{times}\n지금 예매하세요!")
    elif DEBUG:
        label = {"no_date": "날짜 미오픈", "date_no_movie": "날짜는 열림, 듄 없음",
                 "movie_no_imax": "듄 있음, IMAX 없음"}.get(status, status)
        send_kakao(f"[테스트] CGV 체크 정상 동작\n{pretty} 듄3 IMAX: {label}\n(오픈되면 다시 알려드려요)")

    gh_out = os.environ.get("GITHUB_OUTPUT")
    if gh_out:
        with open(gh_out, "a") as f:
            f.write(f"found={'true' if found else 'false'}\n")


if __name__ == "__main__":
    sys.exit(main())
