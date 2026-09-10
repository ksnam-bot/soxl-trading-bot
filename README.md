# SOXL 매매 신호 봇

두 개의 개인 트레이딩 전략 스프레드시트(공격형 "종사종팔 V4", 안정형 "4989 매매법")의 매수/매도
로직을 그대로 재구현한 신호 계산기입니다. **실제 주문은 자동으로 넣지 않습니다.** 매일 아침
"오늘 넣어야 할 LOC 주문 리스트"와 "어제 체결 결과", "현재 수익률"을 계산해서 카카오톡으로
보내주기만 하고, 실제 매수/매도 버튼은 사용자가 증권 앱에서 직접 누릅니다.

## 왜 회사 PC가 아니라 GitHub Actions에서 도는가

회사 PC는 Python이 설치되어 있지 않고(회사 보안 정책상 설치가 제한될 수 있음), 매일 새벽 스케줄이
돌려면 PC가 항상 켜져 있어야 하는 문제도 있습니다. 그래서 이 저장소를 GitHub에 올려두고
**GitHub Actions**가 매일 한국시간 7:30에 자동으로 실행하도록 만들었습니다. 상태(보유 티어,
현금, 시드)는 `state/*.json` 파일로 저장소 안에 있고, 실행할 때마다 자동으로 커밋되어 이력도
남습니다. 카카오톡 인증 토큰은 GitHub의 암호화된 Secrets에만 저장되고 코드에는 들어가지 않습니다.

> ⚠️ **검증 상태**: 회사 PC에 Python을 임시로 설치해서 문법 검사와, 실제 시드 값을 넣은 매수/매도
> 시뮬레이션(체결/미체결/목표매도/손절 각 경로)까지 돌려봤고 스프레드시트의 실제 체결 수량과
> 대조해서 라더링 계산식의 오차(ODCOUNT당 추가 단계 수 off-by-one)도 하나 잡아서 고쳤습니다.
> 다만 **yfinance로 실제 인터넷에서 종가를 받아오는 부분은 이 회사 네트워크의 SSL 검사(사설
> 인증서)에 막혀서 로컬에서는 확인하지 못했습니다** (GitHub Actions는 이 문제와 무관한 별도
> 클라우드 환경이라 영향 없음). 그래도 처음 며칠은 **Actions 탭에서 수동 실행(`workflow_dispatch`)
> 결과를 스프레드시트와 비교**해보는 걸 권장합니다.

## 폴더 구조

```
soxl_bot/            핵심 로직 (엔진, 캘린더, 가격조회, 카카오, 알림메시지)
config/presets.json  전략 파라미터 (공격형/안정형)
config/portfolios.json  운용 중인 계좌 목록 (여러 개 추가 가능)
state/*.json         계좌별 현재 상태 (보유 티어, 현금, 시드) — 매일 자동 갱신+커밋 (비공개 정보 포함)
docs/latest.json     모바일 대시보드용 요약 (현금·총자산 등 민감정보는 제외) — 매일 자동 갱신
docs/index.html      모바일 대시보드 페이지 (GitHub Pages로 서빙, 홈화면에 추가해서 앱처럼 사용)
run_daily.py          매일 실행되는 진입점
.github/workflows/daily.yml   GitHub Actions 스케줄
```

## 시작하기 — GitHub에 올리기 (git 설치 없이, 웹 UI로)

1. https://github.com/signup 에서 계정 생성
2. 로그인 후 우측 상단 `+` → **New repository** → 이름 예: `soxl-trading-bot` → **Private** 선택 → Create
3. 만들어진 빈 저장소 페이지에서 **uploading an existing file** 링크 클릭
4. 이 폴더(`C:\Users\<나>\Documents\SOXL-trading-bot`) 안의 내용을 전부 드래그 앤 드롭으로 업로드
   (모던 브라우저는 하위 폴더 구조까지 그대로 유지해서 올려줍니다)
5. **Commit changes** 클릭

## 카카오톡 "나에게 보내기" 인증 (최초 1회, 사용자가 직접)

1. https://developers.kakao.com 에서 로그인 → **내 애플리케이션** → **애플리케이션 추가하기**
   (앱 이름 예: `soxl-bot`, 회사명은 아무거나)
2. 앱 선택 → **제품 설정 > 카카오 로그인** 활성화 ON
3. **카카오 로그인 > Redirect URI** 에 `https://localhost.com` 같은 아무 URI나 하나 등록
   (실제로 접속되진 않아도 되고, 인증 코드만 받으면 됩니다)
4. **제품 설정 > 카카오 로그인 > 동의항목**에서 "카카오톡 메시지 전송" 항목을 켜기
   (없으면 **카카오톡 메시지 > 나에게 보내기** 쪽에서 활성화)
5. **앱 키** 메뉴에서 **REST API 키** 복사해두기 (`KAKAO_REST_API_KEY`)
6. 아래 URL의 `{REST_API_KEY}`와 `{REDIRECT_URI}`를 3, 5번 값으로 바꿔서 브라우저 주소창에 입력:
   ```
   https://kauth.kakao.com/oauth/authorize?client_id={REST_API_KEY}&redirect_uri={REDIRECT_URI}&response_type=code
   ```
7. 카카오 로그인/동의 후, 리다이렉트된 주소창의 `?code=` 뒤에 붙은 값을 복사 (인증 코드)
8. 그 코드를 저에게 알려주시면, 제가 이 세션의 PowerShell로 아래 요청을 대신 실행해서
   **refresh_token**을 받아드립니다 (토큰 교환만 대신 실행하는 것이고, 실제 카카오 로그인 자체는
   위 4-7번처럼 브라우저에서 사용자가 직접 진행):
   ```
   POST https://kauth.kakao.com/oauth/token
   grant_type=authorization_code&client_id={REST_API_KEY}&redirect_uri={REDIRECT_URI}&code={인증코드}
   ```
9. 받은 `refresh_token`과 2번의 REST API 키를 GitHub 저장소 **Settings > Secrets and variables >
   Actions > New repository secret**에 각각 `KAKAO_REFRESH_TOKEN`, `KAKAO_REST_API_KEY` 이름으로 등록

## 아이폰/아이패드에서 앱처럼 열어보기 (모바일 대시보드)

카카오톡 푸시 알림과는 별개로, 매일 계산된 결과를 홈 화면에서 앱처럼 열어볼 수 있는 페이지도
같이 만들어뒀습니다 (`docs/index.html`). 다만 아이폰 브라우저는 보안상 Yahoo Finance 같은
외부 서버에 직접 종가를 요청할 수 없어서, 이 페이지는 GitHub Actions가 미리 계산해서 저장소에
커밋해둔 `docs/latest.json`을 그냥 읽어서 보여주기만 합니다.

> ⚠️ **주의**: GitHub Pages 무료 요금제는 **퍼블릭(공개) 저장소에서만** 페이지를 서빙할 수
> 있습니다. `docs/latest.json`에는 **현금 잔고·총 평가금액 같은 민감한 숫자는 일부러
> 빼뒀고**, 매수/매도 지정가·수량·티어 번호 같은 신호 정보만 담았습니다. 그래도 URL을 아는
> 사람은 누구나 볼 수 있는 페이지라는 점은 감안해주세요. 완전히 비공개로 하고 싶다면 GitHub
> Pro(유료)로 업그레이드해서 프라이빗 저장소로 Pages를 쓰거나, 이 페이지 없이 카카오톡
> 알림만 쓰는 것도 방법입니다.

**설정 방법**
1. 저장소가 아직 Private이면 **Settings > General > Danger Zone > Change visibility > Public**
   으로 바꾸기 (또는 처음부터 Public으로 저장소를 만들어도 됩니다 — 코드/전략 자체가 공개돼도
   괜찮다면)
2. **Settings > Pages** → Source를 **Deploy from a branch** → Branch `main`, 폴더 `/docs` 선택 → Save
3. 몇 분 뒤 `https://<내계정>.github.io/<저장소이름>/` 로 접속 가능
4. 아이폰/아이패드 Safari로 그 주소를 열고 **공유 버튼 → 홈 화면에 추가** → 아이콘이 생기고
   탭하면 앱처럼 전체화면으로 열립니다

## 여러 계좌/전략 동시 운용하기

`config/portfolios.json`에 항목을 추가하면 됩니다. 각 항목은 `state/<id>.json` 상태 파일을
따로 가지므로 서로 완전히 독립적으로 돕니다. 새 계좌를 원금부터 새로 시작하려면
`state/<새id>.json`을 아래 형태로 만들고 `as_of_date`를 시작 전날(실제 첫 매수는 그 다음 거래일부터
시작됩니다), `pending_order`는 `null`로 두면 됩니다.

```json
{
  "portfolio_id": "새계좌",
  "as_of_date": "2026-09-08",
  "cash": 15000,
  "total_shares": 0,
  "open_positions": [],
  "pending_order": null,
  "compounded_principal": 15000,
  "slot_seed": {},
  "slot_profit": {},
  "history": []
}
```
(`compounded_principal`은 안정형처럼 `seed_mode: "global"` 프리셋에만 필요하고, 공격형처럼
`seed_mode: "per_slot"`이면 `null`로 두면 됩니다.)

## 지금 들어있는 초기 상태

`state/jong_aggressive.json`, `state/maemae_stable.json`은 2026-09-08 종가 기준으로 사용자가
제공한 두 스프레드시트의 실제 현재 상태(보유 티어, 현금, 대기 중인 주문)를 그대로 옮겨온 것입니다.
즉 지금 실제로 운용 중인 계좌와 이어서 자동화가 시작됩니다.

## 참고 — 스프레드시트에서 확인/확정한 내용

원본 스펙 문서의 미확정 항목들은 실제 수식을 대조해서 다음과 같이 확정했습니다:
- **MOC매수 OFF일 때**: 오늘 손절/기한정리로 빠지는 티어가 있으면, 그날의 신규 매수 주문 자체를
  생략합니다 (겹치는 것 방지).
- **안정형의 "매수목표 -0.0001" 필드**: 별도 필드가 아니라 ODGAP(전일 종가 대비 매수 상한)을
  티어마다 -0.01%로 설정해둔 것이었습니다.
- **손절 정리 체결가**: 정리 예정일 당일 종가로 체결됩니다.
- **시드 복리**: 공격형은 슬롯(티어 순번)별로 "직전에 그 슬롯을 썼을 때의 시드 + 그 사이클
  실현손익×복리율/시드분할수"로 계산하고, 손실이었으면 복리를 더하지 않습니다(단, 시드가 줄지도
  않습니다). 안정형은 계좌 전체 단위로 매일 실현손익×복리율을 더해나가는 방식입니다.

## 알려진 단순화

- NYSE 휴장일은 스프레드시트에 하드코딩된 목록 대신, 표준 규칙(신정/MLK/대통령의날/성금요일/
  현충일/준틴스/독립기념일/노동절/추수감사절/성탄절)으로 계산합니다. 몇 년이 지나도 계속 정확하게
  동작합니다.
- 매도 목표가·손절 판정은 "매일 종가 기준"으로만 봅니다(장중가 사용 안 함) — 스펙 요구사항과 동일.
