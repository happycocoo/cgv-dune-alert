"""최초 1회: 카카오 인가 코드 -> refresh token 발급 도우미.

사용법:
  1) 브라우저에서 아래 주소 접속 후 동의 (REST_API_KEY / REDIRECT_URI 바꿔서)
     https://kauth.kakao.com/oauth/authorize?client_id=REST_API_KEY&redirect_uri=REDIRECT_URI&response_type=code&scope=talk_message
  2) 이동된 주소의 ?code=XXXX 값을 복사
  3) python get_kakao_token.py <REST_API_KEY> <REDIRECT_URI> <CODE> [CLIENT_SECRET]
"""
import sys
import requests

key, redirect, code = sys.argv[1], sys.argv[2], sys.argv[3]
data = {"grant_type": "authorization_code", "client_id": key, "redirect_uri": redirect, "code": code}
if len(sys.argv) > 4:
    data["client_secret"] = sys.argv[4]
r = requests.post("https://kauth.kakao.com/oauth/token", data=data, timeout=20)
print(r.status_code)
j = r.json()
print("refresh_token =", j.get("refresh_token"))
print("(refresh token 유효기간 약 2개월)" if "refresh_token" in j else j)
