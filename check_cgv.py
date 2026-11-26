"""CGV 센텀시티 / 듄 파트 3 IMAX / 지정 날짜 예매 오픈 여부를 확인하고 카카오톡(나에게 보내기)으로 알림.

CGV 사이트는 해외(GitHub) 서버 접속을 차단하므로, 네이버 플레이스의 날짜별 상영시간표(CGV 데이터)를 읽는다.
"""
import json
import os
import re
import sys

import requests
from playwright.sync_api import sync_playwright

TARGET_DATE = os.environ.get("TARGET_DATE", "2027-01-01")        # YYYY-MM-DD
NAVER_PLACE_ID = os.environ.get("NAVER_PLACE_ID", "13082085")    # 네이버 플레이스: CGV 신세계백화점센텀시티점
MOVIE_KEYWORDS = [k.strip() for k in os.environ.get("MOVIE_KEYWORDS", "듄").split(",") if k.strip()]
FORMAT_KEYWORD = os.environ.get("FORMAT_KEYWORD", "IMAX")
DEBUG = os.environ.get("DEBUG", "false").lower() == "true"
NOTIFY = os.environ.get("NOTIFY", "true").lower() == "true"
BOOK_URL = "https://cgv.co.kr/cnm/bzplcCgv/0089001"
PLACE_URL = f"https://m.place.naver.com/place/{NAVER_PLACE_ID}/movie?datefilter={TARGET_DATE}"


def sq(s):
    return re.sub(r"\s+", " ", s or "").strip()


def check():
    """returns (status, detail). status: 'imax' | 'movie_no_imax' | 'date_no_movie' | 'no_date'"""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(
            locale="ko-KR", viewport={"width": 420, "height": 2400},
            user_agent=("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 "
                        "(KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"))
        pg = ctx.new_page()
        last_err = None
        for attempt in range(3):
            try:
                pg.goto(PLACE_URL, wait_until="networkidle", timeout=60000)
                pg.wait_for_timeout(2000)
                text = sq(pg.inner_text("body"))
                if "상영시간표" in text or re.search(r"\d{1,2}\.\d{1,2}\((?:오늘|[월화수목금토일])\)", text):
                    break
                last_err = "페이지에 상영 정보가 없음: " + text[:200]
            except Exception as e:
                last_err = str(e)
            pg.wait_for_timeout(5000)
        else:
            browser.close()
            raise RuntimeError(last_err)
        browser.close()

    text = text.split("이용약관")[0]
    labels = re.findall(r"(\d{1,2})\.(\d{1,2})\((?:오늘|[월화수목금토일])\)", text)
    print("dates on page:", [f"{m}.{d}" for m, d in labels])
    want = (str(int(TARGET_DATE[5:7])), str(int(TARGET_DATE[8:10])))
    if want not in labels:
        return "no_date", f"열린 날짜: {', '.join(f'{m}.{d}' for m, d in labels)}"

    hits = [i for k in MOVIE_KEYWORDS for i in [text.find(k)] if i >= 0]
    if not hits:
        if DEBUG:
            print("PAGE:", text[:2000])
        return "date_no_movie", text[:300]
    i = min(hits)
    s1 = text.find("상영시간표", i)
    s2 = text.find("상영시간표", s1 + 1)
    halls = text[s1 + len("상영시간표"): s2 if s2 > 0 else len(text)]
    detail = text[i:s1].split("개봉일")[0].strip() + " | " + halls.strip()
    print("movie block:", detail[:800])
    m = re.search(re.escape(FORMAT_KEYWORD) + r"[^0-9]*((?:\d{1,2}:\d{2}\s*)+)", halls, flags=re.I)
    if m:
        return "imax", m.group(0).strip()
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
        send_kakao(f"🎬 예매 오픈!\nCGV 센텀시티 듄: 파트 3 IMAX\n{pretty} 회차가 열렸습니다.\n{detail}\n지금 예매하세요!")
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
