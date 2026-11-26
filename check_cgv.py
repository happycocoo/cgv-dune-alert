"""CGV 센텀시티 / 듄 파트 3 IMAX / 지정 날짜 예매 오픈 여부를 확인하고 카카오톡(나에게 보내기)으로 알림."""
import json
import os
import re
import sys
from pathlib import Path

import requests
from playwright.sync_api import sync_playwright

TARGET_DATE = os.environ.get("TARGET_DATE", "20270101")          # YYYYMMDD
THEATER_CODE = os.environ.get("THEATER_CODE", "0089")            # CGV 센텀시티
AREA_CODE = os.environ.get("AREA_CODE", "05,207")                # 부산/울산
MOVIE_KEYWORDS = [k.strip() for k in os.environ.get("MOVIE_KEYWORDS", "듄,Dune").split(",") if k.strip()]
FORMAT_KEYWORD = os.environ.get("FORMAT_KEYWORD", "IMAX")
DEBUG = os.environ.get("DEBUG", "false").lower() == "true"
DUMP_DIR = Path("dump")

URLS = [
    f"https://www.cgv.co.kr/common/showtimes/iframeTheater.aspx?areacode={AREA_CODE}&theatercode={THEATER_CODE}&date={TARGET_DATE}",
    f"https://www.cgv.co.kr/theaters/?areacode={AREA_CODE}&theaterCode={THEATER_CODE}&date={TARGET_DATE}",
    f"https://m.cgv.co.kr/WebApp/Reservation/Schedule.aspx?tc={THEATER_CODE}&ymd={TARGET_DATE}",
]

NO_SCHEDULE_PATTERNS = ["상영 스케줄이 없습니다", "상영스케줄이 없습니다", "조회 가능한 상영시간이 없습니다"]


def date_variants(d: str):
    y, m, dd = d[:4], d[4:6], d[6:]
    return {d, f"{y}-{m}-{dd}", f"{y}.{m}.{dd}", f"{y}/{m}/{dd}"}


def text_matches(text: str) -> bool:
    has_movie = any(k.lower() in text.lower() for k in MOVIE_KEYWORDS)
    return has_movie and FORMAT_KEYWORD.lower() in text.lower()


def collect_pages():
    """Playwright로 각 URL을 렌더링하고, 프레임 텍스트/HTML과 XHR JSON 응답을 모은다."""
    sources = []  # (label, content, is_date_scoped)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(
            locale="ko-KR",
            user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"),
        )
        page = ctx.new_page()
        json_bodies = []

        def on_response(resp):
            try:
                ct = resp.headers.get("content-type", "")
                if "json" in ct:
                    json_bodies.append((resp.url, resp.text()))
            except Exception:
                pass

        page.on("response", on_response)
        for url in URLS:
            try:
                page.goto(url, wait_until="networkidle", timeout=45000)
                page.wait_for_timeout(2000)
                for i, fr in enumerate(page.frames):
                    try:
                        html = fr.content()
                    except Exception:
                        continue
                    sources.append((f"{url} [frame {i}: {fr.url}]", html, True))
            except Exception as e:
                sources.append((f"{url} [ERROR]", f"ERROR: {e}", False))
        for u, body in json_bodies:
            sources.append((f"XHR {u}", body, False))
        browser.close()
    return sources


def evaluate(sources):
    dv = date_variants(TARGET_DATE)
    hits = []
    for label, content, date_scoped in sources:
        if content.startswith("ERROR"):
            continue
        if not text_matches(content):
            continue
        if any(pat in content for pat in NO_SCHEDULE_PATTERNS):
            continue
        # 날짜가 실제로 열렸는지: 페이지/응답 안에 대상 날짜가 등장해야 함
        if not any(v in content for v in dv):
            continue
        # 상영시간(HH:MM) 이 함께 있어야 실제 회차로 판단
        if not re.search(r"\b([01]?\d|2[0-3]):[0-5]\d\b", content):
            continue
        hits.append(label)
    return hits


def kakao_access_token():
    data = {
        "grant_type": "refresh_token",
        "client_id": os.environ["KAKAO_REST_API_KEY"],
        "refresh_token": os.environ["KAKAO_REFRESH_TOKEN"],
    }
    if os.environ.get("KAKAO_CLIENT_SECRET"):
        data["client_secret"] = os.environ["KAKAO_CLIENT_SECRET"]
    r = requests.post("https://kauth.kakao.com/oauth/token", data=data, timeout=20)
    r.raise_for_status()
    tok = r.json()
    if "refresh_token" in tok:
        print("::warning::카카오 refresh token이 갱신되었습니다. README의 '토큰 갱신' 절차로 KAKAO_REFRESH_TOKEN 시크릿을 업데이트하세요.")
    return tok["access_token"]


def send_kakao(text: str, link: str):
    token = kakao_access_token()
    template = {
        "object_type": "text",
        "text": text[:200],
        "link": {"web_url": link, "mobile_web_url": link},
        "button_title": "CGV 예매하기",
    }
    r = requests.post(
        "https://kapi.kakao.com/v2/api/talk/memo/default/send",
        headers={"Authorization": f"Bearer {token}"},
        data={"template_object": json.dumps(template, ensure_ascii=False)},
        timeout=20,
    )
    print("kakao:", r.status_code, r.text)
    r.raise_for_status()


def main():
    sources = collect_pages()
    hits = evaluate(sources)
    pretty_date = f"{TARGET_DATE[4:6].lstrip('0')}월 {TARGET_DATE[6:].lstrip('0')}일"
    link = URLS[1]

    if DEBUG:
        DUMP_DIR.mkdir(exist_ok=True)
        for i, (label, content, _) in enumerate(sources):
            (DUMP_DIR / f"{i:02d}.txt").write_text(label + "\n\n" + content, encoding="utf-8")

    print(f"sources={len(sources)} hits={hits}")
    found = bool(hits)

    if found:
        send_kakao(f"🎬 예매 오픈!\nCGV 센텀시티 듄: 파트 3 IMAX\n{pretty_date} 회차가 열렸습니다. 지금 예매하세요!", link)
    elif DEBUG:
        errs = sum(1 for _, c, _ in sources if c.startswith("ERROR"))
        send_kakao(f"[테스트] CGV 체크 동작 중\n{pretty_date} 듄3 IMAX: 아직 미오픈\n수집 {len(sources)}개 / 오류 {errs}개", link)

    gh_out = os.environ.get("GITHUB_OUTPUT")
    if gh_out:
        with open(gh_out, "a") as f:
            f.write(f"found={'true' if found else 'false'}\n")


if __name__ == "__main__":
    sys.exit(main())
