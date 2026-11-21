# 14-web-foundation — 테스트 설계 (test)

> spec.md와 짝. 절 번호 §n은 spec.md 기준. 작성 2026-11-21. 상태: 초안 — 사용자 검토 대기.
> ① 자동 테스트 — A: Vitest + React Testing Library(결정적, 서버 없음, `fetch` 가짜) / B: Playwright(실제 compose) ② HITL(휴대폰 PWA 설치 등 사용자가 직접).

---

## ① 자동 테스트

### 0. 실행 방법 · 공통 준비
```bash
cd ~/code/myAgent/web
npm ci
npm run typecheck
npm run test                       # Vitest (서버 불필요)
# Playwright: compose가 떠 있어야 함
docker compose -f ../compose.yaml up -d --build
npx playwright install --with-deps chromium   # 처음 1회(sudo 필요)
npm run e2e                        # 기본 http://localhost:8080
E2E_BASE_URL=https://<HOST> npm run e2e   # 05 A17이 localhost 실패였으면
```
- Vitest 공통 대역(`tests/unit/helpers.ts`):

| 이름 | 역할 |
|---|---|
| `mockFetch(routes)` | `globalThis.fetch`를 가짜로 — `"METHOD /path"` → `{status, json?, headers?}` 또는 함수. 호출 기록(`calls`: method, path, headers, body) |
| `setCookie(str)` | `document.cookie` 값 설정(jsdom) |
| `mockRouter()` | `vi.mock("next/navigation")` — `useRouter().replace/push` 기록 |

---

### A. Vitest

#### A1. `tests/unit/api.test.ts` — fetch 클라이언트 (§6)

| ID | 준비 | 동작 | 기대 |
|---|---|---|---|
| V-API-01 | — | `readCookie("__Host-csrf", "a=1; __Host-csrf=tok.sig; b=2")` | `"tok.sig"` |
| V-API-02 | — | `readCookie("x", "")` | `null` |
| V-API-03 | 쿠키 `__Host-csrf=T1` | `apiJson("/api/auth/login", {method:"POST", json:{…}})` | 헤더 `X-CSRF-Token: T1`, `Content-Type: application/json`, 본문 JSON, csrf GET 호출 0 |
| V-API-04 | 쿠키 없음, `GET /api/auth/csrf` → `{csrf_token:"T2"}` | POST | csrf GET 1회 → 본 요청 헤더 `T2` |
| V-API-05 | 쿠키 T1, 첫 POST 403 `{code:"csrf_failed"}`, csrf GET → T3, 두 번째 POST 200 | POST | 호출 순서 POST(T1) → GET csrf → POST(T3), 결과 성공 |
| V-API-06 | 두 POST 모두 403 csrf_failed | POST | `ApiError(403, "csrf_failed")`, POST는 **2번만** |
| V-API-07 | 403 `{code:"forbidden"}` | POST | 재시도 없음, `ApiError(403,"forbidden")` |
| V-API-08 | — | `apiFetch("/api/x")`(GET) | `X-CSRF-Token` 헤더 없음 |
| V-API-09 | — | `apiFetch("https://evil.example/api/x")`, `apiFetch("/other")` | Error(경로 규칙), fetch 호출 0 |
| V-API-10 | 422 FastAPI 본문 `{detail:[…]}` | — | `code "validation_error"`, 메시지 `입력값을 확인해 주세요.` |
| V-API-11 | fetch가 `TypeError` | — | `ApiError(0,"network_error")` |
| V-API-12 | 502, 본문 HTML | — | `code "server_error"` |
| V-API-13 | 429 `{code:"too_many_attempts", message:"…15분…"}` + `Retry-After: 900` | — | `retryAfterS === 900`, 메시지 그대로 |
| V-API-14 | 204 | `apiJson` | `undefined` |
| V-API-15 | 본문 `FormData` | POST | `Content-Type`을 직접 넣지 않음, CSRF 헤더 있음 |
| V-API-16 | AbortController로 중단 | — | `AbortError` 그대로 던짐(ApiError 아님) |
| V-API-17 | 429 `{code:"quota_exceeded", …, request_status:null}` | — | `err.body.request_status === null`(16이 사용) |

#### A2. `tests/unit/validation.test.ts` (§6.5)

| ID | 입력 | 기대 |
|---|---|---|
| V-VAL-01 | `checkUsername(" Alice_01 ")` | null(정규화 후 통과) |
| V-VAL-02 | `"abc"`, `"a".repeat(21)`, `"한글아이디"`, `"a-b-c-d"` | `USERNAME_RULE_TEXT` |
| V-VAL-03 | `checkEmail("a@b.co")` / `"a@b"` / `"a b@c.d"` | null / 문구 / 문구 |
| V-VAL-04 | `checkPassword("123456789")`(9자) | `비밀번호는 10자 이상이어야 해요.` |
| V-VAL-05 | `"a".repeat(10)` / `"a".repeat(128)` | null |
| V-VAL-06 | `"a".repeat(129)` | `비밀번호는 128자 이하여야 해요.` |
| V-VAL-07 | 이모지 9개 + 1자(코드포인트 10, UTF-16 길이 19) | null |
| V-VAL-08 | `checkPasswordConfirm("x","y")` | `두 비밀번호가 같지 않아요.` |
| V-VAL-09 | 문구 상수가 05 §4.3과 같은 글자 | 문자열 비교(테스트에 05 문구를 직접 적어 대조) |

#### A3. 화면 컴포넌트 — `tests/unit/auth-pages.test.tsx`

| ID | 화면 | 동작 | 기대 |
|---|---|---|---|
| V-PG-01 | login | 로그인 200 `status:"active"` | `router.replace("/")` |
| V-PG-02 | login | 200 `status:"pending"` | `replace("/pending")` |
| V-PG-03 | login | 401 `login_failed` | `role=alert`에 서버 문구, 이동 없음 |
| V-PG-04 | login | 제출 중 | 버튼 비활성, 두 번 클릭해도 요청 1회 |
| V-PG-05 | signup | 화면 처음 | `PASSWORD_RULE_TEXT`·`USERNAME_RULE_TEXT`가 입력 전부터 보임 |
| V-PG-06 | signup | 비밀번호 9자 제출 | 칸 아래 "10자 이상" 문구, fetch 0 |
| V-PG-07 | signup | 확인 칸 다름 | "두 비밀번호가 같지 않아요.", fetch 0 |
| V-PG-08 | signup | 400 `weak_password` reason `common` | 알림 "너무 흔한 비밀번호예요…" |
| V-PG-09 | signup | 201 | 폼 사라지고 서버 message + "로그인하러 가기", 로그인 요청 없음 |
| V-PG-10 | signup | 409 `email_taken` | 서버 문구 |
| V-PG-11 | reset | 이메일 제출 202 | 2단계(코드·새 비밀번호), 서버 message 표시, 규칙 문구 보임 |
| V-PG-12 | reset | 2단계 400 `reset_failed` | 알림, 입력 값 유지 |
| V-PG-13 | reset | "인증코드 다시 받기" | 1단계로, 이메일 칸 값 유지 |
| V-PG-14 | reset | 200 | 완료 문구 + 로그인 링크 |
| V-PG-15 | pending | "승인됐는지 확인" → me active | `replace("/")` |
| V-PG-16 | pending | me pending | "아직 승인 전이에요." |
| V-PG-17 | pending | "로그아웃" | POST logout → `replace("/login")` |
| V-PG-18 | account | 변경 성공 | 서버 message, 입력 비움 |
| V-PG-19 | account | 400 `wrong_current_password` | 알림 |

#### A4. `tests/unit/auth-gate.test.tsx` (§7.1)

| ID | me 응답 | 기대 |
|---|---|---|
| V-AG-01 | 200 active | children 렌더, `useMe().username` 사용 가능 |
| V-AG-02 | 200 pending | `replace("/pending")`, children 렌더 안 함 |
| V-AG-03 | 401 | `replace("/login")` |
| V-AG-04 | 502 | 오류 문구 + "다시 시도" → 다시 호출 → 200이면 children |

#### A5. `tests/unit/register-sw.test.tsx`, `tests/unit/no-storage.test.ts`

| ID | 내용 | 기대 |
|---|---|---|
| V-SW-01 | `NODE_ENV=production`, 가짜 `navigator.serviceWorker.register` | `("/sw.js", {scope:"/"})` 1회 |
| V-SW-02 | `NODE_ENV=test`/`development` | 호출 0 |
| V-SW-03 | `serviceWorker` 없는 브라우저 | 오류 없음 |
| V-ST-01 | `web/app`·`web/components`·`web/lib` 소스 텍스트 검색 | `localStorage`·`sessionStorage` 0건(NFR-04) |

---

### B. Playwright (실제 compose) — `web/e2e/`

`global-setup.ts`가 `e2e_` 사용자·요청 제한 카운터를 지운다(spec §10). 사용자 승인은 `helpers/db.ts`의 `approve(username)` = `update users set status='active', approved_at=now() where username=$1`(값은 psql `-v` 변수로 전달).

| ID | 파일 | 흐름 | 기대 |
|---|---|---|---|
| P-AU-01 | `auth.spec.ts` | `/` 접속(로그인 안 함) | `/login`으로 이동 |
| P-AU-02 | 〃 | `/signup`에서 `e2e_<시각>` 가입 | 성공 문구, DB `status='pending'` |
| P-AU-03 | 〃 | 그 계정 로그인 | `/pending`, 안내 문구 |
| P-AU-04 | 〃 | `approve()` 후 "승인됐는지 확인" | `/`(임시 채팅 화면) |
| P-AU-05 | 〃 | `/account` 비밀번호 변경 → 로그아웃 → 새 비밀번호 로그인 | 성공 |
| P-AU-06 | 〃 | 두 번째 브라우저 컨텍스트에서 같은 계정 로그인 → 첫 컨텍스트에서 비밀번호 변경 → 두 번째 컨텍스트 새로고침 | 두 번째가 `/login`(FR-03) |
| P-AU-07 | 〃 | 틀린 비밀번호 로그인 | "아이디 또는 비밀번호가 맞지 않아요." |
| P-AU-08 | 〃 | 가입 화면에 흔한 비밀번호(05 목록의 10자 이상 항목 1개, 예: 목록 첫 줄) | "너무 흔한 비밀번호예요…" |
| P-AU-09 | `reset.spec.ts` | `/reset` 이메일 입력 → 2단계 → 틀린 코드 `000000` | 202 문구 → `reset_failed` 문구(메일 발송은 06이 SMTP 없으면 생략) |
| P-AU-10 | `csrf.spec.ts` | 로그인 뒤 `__Host-csrf` 쿠키만 지움 → 계정 화면에서 틀린 현재 비밀번호로 변경 시도 | `GET /api/auth/csrf`가 먼저 불리고, 결과가 CSRF 오류가 아닌 `현재 비밀번호가 맞지 않아요.` |
| P-AU-11 | 〃 | 로그인 전 다른 컨텍스트에서 받은 **익명** 토큰을 `__Host-csrf`로 넣고 같은 시도 | 첫 요청 403 `csrf_failed` → 토큰 재발급 → 1번 재시도 → `현재 비밀번호가 맞지 않아요.` (네트워크 기록으로 순서 확인) |
| P-PWA-01 | `pwa.spec.ts` | `GET /manifest.webmanifest` | 200, `display:"standalone"`, 아이콘 3개, `start_url:"/"` |
| P-PWA-02 | 〃 | 아이콘 4개 URL | 200, `image/png` |
| P-PWA-03 | 〃 | `/sw.js` | 200, JavaScript(동적 라우트 `[sessionId]`가 생겨도 public 파일이 우선인지 — 15 병합 후에도 이 테스트로 확인) |
| P-PWA-04 | 〃 | 로그인 후 `navigator.serviceWorker.ready` 대기 → 페이지 새로고침 → `/api/auth/me` 응답 | `response.fromServiceWorker() === false` |
| P-PWA-05 | 〃 | `mobile-chrome` 프로젝트로 `/login` | 가로 스크롤 없음(`document.documentElement.scrollWidth <= innerWidth`) |

### 통과 기준
- A 전부 통과(서버 없이), B 전부 통과(compose 기동 상태). 실패 시 스크린샷·trace를 `test-results/`에 남긴다(커밋하지 않음 — `.gitignore`).

---

## ② HITL (사용자가 직접)

전제: 14 적용 compose 기동(`docker compose up -d --build`), 터널 주소 `<HOST>` 동작(05 H-4 통과), active 계정 1개.

### HITL-1 PWA 설치 (NFR-52, S17)
**Android(Chrome)**
1. 휴대폰 Chrome으로 `https://<HOST>/login` 접속.
2. 메뉴(⋮) → "앱 설치" 또는 주소창의 설치 아이콘이 보이는지 확인 → 설치.
3. 홈 화면 아이콘으로 실행 → 주소창 없는 **전체화면**, 상단 색 청록, 로그인 화면.
4. 로그인 → 임시 채팅 화면 → 앱을 닫았다 다시 열어도 로그인 유지.

**iOS(Safari)**
1. Safari로 `https://<HOST>/login` → 공유 버튼 → "홈 화면에 추가" → 이름 `nadri`, 아이콘 모양 확인.
2. 홈 화면에서 실행 → 전체화면(Safari 주소창 없음).
3. 로그인 → 앱 닫고 다시 열기 → 로그인 유지 여부 기록(iOS 홈 화면 앱은 Safari와 쿠키를 따로 쓰는 것으로 알려짐 — **미확인**, 결과 기록만).

### HITL-2 화면 흐름 (PC 브라우저 1회)
1. `/signup` — 비밀번호 규칙 문구가 입력 전에 보이는지, 9자 입력 시 문구.
2. 가입 → psql 승인(05 H-3 4번 명령) → 로그인 → `/`.
3. `/reset` — 실제 Gmail 설정이 있으면 코드 메일 받아 새 비밀번호로 바꾸기(06 HITL과 같은 메일).
4. `/account` — 비밀번호 변경 후 휴대폰 PWA에서 다음 동작 시 로그인 화면으로 가는지.
5. 휴대폰 세로·가로, PC 창 좁히기 — 글자 잘림·가로 스크롤 없는지.

### HITL 결과 보고 양식
| 항목 | 결과 (기기·브라우저 버전) |
|---|---|
| Android "앱 설치" 메뉴 표시·설치·전체화면 | |
| iOS "홈 화면에 추가"·전체화면·아이콘 | |
| iOS 홈 화면 앱 로그인 유지 여부 | |
| 비밀번호 규칙 미리 표시·거절 문구 | |
| 재설정 메일 실제 수신(선택) | |
| 비밀번호 변경 후 다른 기기 로그아웃 | |
| 반응형 깨짐 | |
