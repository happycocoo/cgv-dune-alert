# CGV 센텀시티 · 듄: 파트 3 IMAX · 1월 1일 예매 오픈 카톡 알림

GitHub Actions가 GitHub 서버에서 **30분마다** 확인합니다. 내 컴퓨터가 꺼져 있어도 동작합니다.

CGV 사이트는 해외 서버(GitHub) 접속을 차단하므로, 네이버 플레이스의 날짜별 상영시간표
(`m.place.naver.com/place/13082085/movie?datefilter=YYYY-MM-DD`, CGV 데이터)를 읽습니다.
오픈이 감지되면 카톡 "나에게 보내기"로 알림을 1번 보내고, 워크플로는 스스로 꺼집니다.

## 1. 카카오 설정 (1회, 약 10분)
1. https://developers.kakao.com 로그인 → **내 애플리케이션 → 애플리케이션 추가**
2. **앱 키**에서 **REST API 키** 복사
3. **카카오 로그인** → 활성화 ON, **Redirect URI**에 `https://localhost` 등록
4. **동의항목** → **카카오톡 메시지 전송(talk_message)** 을 "선택 동의"로 설정
5. (보안 → Client Secret을 켰다면 그 값도 복사)
6. 브라우저 주소창에 입력 (REST_API_KEY 바꿔서):
   `https://kauth.kakao.com/oauth/authorize?client_id=REST_API_KEY&redirect_uri=https://localhost&response_type=code&scope=talk_message`
   → 동의 후 열리지 않는 페이지로 이동하는데, 주소창의 `code=` 뒤 값을 복사
7. refresh token 발급:
   `python get_kakao_token.py REST_API_KEY https://localhost 복사한코드`
   (코드는 몇 분 안에 만료되니 바로 실행)

## 2. GitHub 설정
1. GitHub에서 새 저장소 생성 (Private 권장) 후 이 폴더의 파일 전부 업로드
2. 저장소 **Settings → Secrets and variables → Actions → New repository secret**
   - `KAKAO_REST_API_KEY`
   - `KAKAO_REFRESH_TOKEN`
   - `KAKAO_CLIENT_SECRET` (켠 경우만)
3. **Actions** 탭 → 워크플로 활성화 → **Run workflow** (debug 체크) 실행
   → 카톡으로 "[테스트] CGV 체크 동작 중" 메시지가 오면 성공

## 참고
- refresh token은 약 2개월 유효합니다(1월 1일까지는 충분). 만료되면 1-6, 1-7을 다시 하고 시크릿을 바꿔 주세요.
- 날짜/영화/상영관은 워크플로 파일의 `TARGET_DATE`, `MOVIE_KEYWORDS`, `FORMAT_KEYWORD` 기본값에서 바꿀 수 있습니다.
- Actions → Run workflow 에서 날짜·영화를 바꿔 테스트할 수 있습니다 (수동 실행은 자동 중지되지 않음).
