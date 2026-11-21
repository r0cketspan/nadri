# 14-web-foundation — Next.js 기반·인증 화면·PWA (spec)

> 하네스 Phase 4 산출물 (spec-writer, 작성 2026-11-21). 상태: **확정(2026-11-22)** — 확인 질문은 모두 추천안대로 결정(마지막 절 표). 브랜치 `feat/14-web-foundation`, 의존 작업 05-auth-core, 06-password-reset-mail.
> 근거: [PL]=program_list.md(G4 승인본) §2 표·§3 "14-web-foundation"·§5 Q7 · [A]=architecture.md(G3 재승인본) §1(프론트·PWA)·§2 컨테이너 표(`web`·`nginx`)·§2.1 web·§7 디렉터리·§9(컨테이너 격리)·ADR-12 · [R]=requirements.md FR-01~05, NFR-04·05·10·20·52·70 · [S]=stack-options.md S16·S17·S18·S19 · [CL]=CLAUDE.md(작업 환경·주석 규칙).
> **이어받는 확정 spec**: [02](`infra/nginx/nginx.conf` `/api/` 블록·`location / { return 404; }`·`compose.dev.yaml` nginx `127.0.0.1:8080`) · [05](엔드포인트·`UserOut`·오류 본문 `{"code","message"}`·문구 §4.3·쿠키 `__Host-session`/`__Host-csrf`·헤더 `X-CSRF-Token`·`GET /api/auth/csrf`·"csrf_failed면 토큰 새로 받아 1번만 재시도"·422 화면 문구·A17 결과) · [06](`password-reset/request`·`confirm`·문구 `MSG_RESET_*`).
> **미확인** = 문서·공식 자료로 확인하지 못한 사실(라이브러리 버전 동작 등).

---

## 1. 작업 목표

`web/` Next.js 앱의 뼈대를 만들고, 로그인·가입 신청·승인 대기·비밀번호 재설정·비밀번호 변경 화면과 CSRF 헤더를 붙이는 fetch 클라이언트, 설치 가능한 PWA(manifest·아이콘·최소 서비스워커)를 만든다. nginx가 `/`·`/admin`을 web으로 보낸다 [PL §3].

끝나면: 가입 신청 → (DB에서 수동 승인 — 관리자 화면은 18) → 로그인 → 승인 대기 화면 또는 채팅 자리(15가 채움)로 분기, 재설정 흐름이 화면으로 되고, Android Chrome "앱 설치"·iOS Safari "홈 화면에 추가"로 전체화면 실행된다.

### 1.1 넣지 않는 것
| 빠지는 것 | 들어오는 작업 / 이유 |
|---|---|
| 채팅 화면·SSE 파서·사이드바 | 15 (14는 `/` 자리에 임시 안내 화면만) |
| 피드백·한도 요청·위치·음성 | 16·17 |
| `/admin` 화면 | 18·19·25 (14는 nginx 라우팅만) |
| 오프라인 캐시·푸시 알림·백그라운드 동기화 | 범위 밖([A] §13) |
| 서버(Next.js)에서 api 호출(RSC·Route Handler·`proxy`) | ADR-12 — 데이터는 브라우저에서만 `/api` |
| 다크 모드·다국어 | 요구사항 없음 |
| 로그인 상태 저장(localStorage·sessionStorage) | NFR-04 — 쿠키만 |

---

## 2. 단계 분할 (하루를 넘길 때 — 같은 브랜치 안 커밋 3개)

| 단계 | 내용 | 끝 확인 |
|---|---|---|
| 14a 골격 | `package.json`·설정 파일·`Dockerfile`·compose `web`·nginx `/`·Tailwind·shadcn 초기화·`layout.tsx`·임시 `/` | `docker compose up -d --build` 후 `http://localhost:8080/`에 임시 화면, `npm run test`·`typecheck` 통과(빈 테스트 1개) |
| 14b 인증 | `lib/api.ts`·`lib/validation.ts`·`(auth)` 4화면·`(chat)/layout.tsx`·`account` | Vitest·Playwright 인증 흐름 통과 |
| 14c PWA | `manifest.ts`·아이콘·`sw.js`·`RegisterSW.tsx` | Playwright PWA 테스트·HITL 설치 |

작업 분리(별도 작업 id)는 하지 않는다 — 셋이 서로 붙어 있어야 HITL 한 번으로 확인된다.

---

## 3. 생성·수정 파일

| 파일 | 신규/수정 | 역할 |
|---|---|---|
| `web/package.json`, `web/package-lock.json` | 신규 | 의존성 고정(§4), 스크립트 |
| `web/next.config.ts` | 신규 | `output: "standalone"`, `poweredByHeader: false`, `reactStrictMode: true` |
| `web/tsconfig.json` | 신규 | strict, 경로 별칭 `@/*` → `./*` |
| `web/postcss.config.mjs`, `web/app/globals.css` | 신규 | Tailwind 4(`@import "tailwindcss"`) |
| `web/components.json`, `web/components/ui/{button,input,label,card}.tsx`, `web/lib/utils.ts` | 신규 | shadcn/ui 초기화 + 쓰는 컴포넌트 4개만(CLI가 생성) |
| `web/Dockerfile` | 신규 | 3단계(deps → build → runner), 비루트 (§9) |
| `web/.dockerignore` | 신규 | `node_modules`, `.next`, `e2e`, `test-results` 등 |
| `web/vitest.config.ts`, `web/vitest.setup.ts` | 신규 | jsdom, `@testing-library/jest-dom` |
| `web/playwright.config.ts` | 신규 | baseURL·프로젝트 (§10) |
| `web/app/layout.tsx` | 신규 | `<html lang="ko">`, metadata·viewport(PWA·iOS), `RegisterSW` |
| `web/app/(auth)/layout.tsx` | 신규 | 인증 화면 공통 틀(가운데 카드) — 서버 컴포넌트, 데이터 호출 없음 |
| `web/app/(auth)/login/page.tsx` | 신규 | 로그인 (§7.2) |
| `web/app/(auth)/signup/page.tsx` | 신규 | 가입 신청 (§7.3) |
| `web/app/(auth)/pending/page.tsx` | 신규 | 승인 대기 (§7.4) |
| `web/app/(auth)/reset/page.tsx` | 신규 | 비밀번호 재설정 2단계 (§7.5) |
| `web/app/(chat)/layout.tsx` | 신규 | 로그인 확인 게이트(`AuthGate`) (§7.1) |
| `web/app/(chat)/page.tsx` | 신규(임시) | "채팅 화면 준비 중" + 계정 링크 — **15가 교체** |
| `web/app/(chat)/account/page.tsx` | 신규 | 비밀번호 변경·로그아웃 (§7.6) |
| `web/components/AuthGate.tsx` | 신규 | `/api/auth/me`로 분기, `useMe()` 컨텍스트 제공 (§7.1) |
| `web/lib/api.ts` | 신규 | fetch 클라이언트·CSRF·오류 정규화·인증 API 함수 (§6) |
| `web/lib/validation.ts` | 신규 | 화면 입력 미리 검사(05 규칙과 같은 문구) (§6.4) |
| `web/app/manifest.ts` | 신규 | PWA manifest (§8.1) |
| `web/public/icons/{icon.svg,icon-192.png,icon-512.png,icon-maskable-512.png,apple-touch-icon.png}` | 신규 | 아이콘 (§8.2) |
| `web/public/sw.js` | 신규 | 최소 서비스워커 (§8.3) |
| `web/components/RegisterSW.tsx` | 신규 | 운영 빌드에서만 SW 등록 (§8.4) |
| `web/tests/unit/*.test.ts(x)` | 신규 | Vitest (test.md) |
| `web/e2e/*.spec.ts`, `web/e2e/helpers/db.ts`, `web/e2e/global-setup.ts` | 신규 | Playwright (test.md) |
| `compose.yaml` | 수정 | `web` 서비스, nginx `depends_on`에 web (§9) |
| `compose.dev.yaml` | 수정 | web 개발 모드(소스 마운트·`next dev`) (§9, 14-Q3) |
| `infra/nginx/nginx.conf` | 수정(02) | `location / { return 404; }` → web 프록시 (§9) |
| `CLAUDE.md` | 수정 | "명령어" 절에 web 명령 추가([CL] 지시). ("작업 환경"의 WSL Node(fnm) 줄·README 스택 표는 14-Q1 결정(2026-11-22) 때 문서 담당이 이미 반영 — 구현 때 Node 실제 버전만 맞춰 고침) |

> [PL] 파일 목록 밖: `(auth)/layout.tsx`, `(chat)/layout.tsx`, 임시 `(chat)/page.tsx`, `AuthGate.tsx`, `validation.ts`, shadcn 생성 파일, `tsconfig`·PostCSS·`globals.css`, 테스트 폴더, `compose.dev.yaml`, `CLAUDE.md`. 모두 화면 뼈대·로그인 확인·테스트 실행에 필요한 최소분.

---

## 4. 의존성 (`web/package.json`)

| 구분 | 패키지 | 버전 고정 |
|---|---|---|
| 런타임 | `next` | 16.x — 구현 시점 최신 16.x를 정확한 버전으로(S16 조회 당시 16.4.5) |
| | `react`, `react-dom` | 19.x (next가 요구하는 버전) |
| | `react-markdown`, `remark-gfm` | 구현 시점 최신(15가 사용, [PL]이 14에서 고정하라고 함) |
| | shadcn이 넣는 것 | `class-variance-authority`, `clsx`, `tailwind-merge`, `lucide-react`, Radix 패키지(이름은 shadcn CLI 결과 그대로 — **미확인**) |
| 개발 | `typescript`, `@types/react`, `@types/react-dom`, `@types/node` | |
| | `tailwindcss` 4.x, `@tailwindcss/postcss` | |
| | `vitest`, `@vitejs/plugin-react`, `jsdom`, `@testing-library/react`, `@testing-library/user-event`, `@testing-library/jest-dom` | |
| | `@playwright/test` | 1.x 최신(S19 조회 당시 1.65) |

- 모든 버전은 `^`·`~` 없이 **정확한 버전**으로 적고 `package-lock.json`을 커밋한다. 설치는 `npm ci`.
- 패키지 관리자: **npm**(Node에 들어 있음 — 추가 도구 없음, 14-Q2).
- 스크립트:
```json
{
  "dev": "next dev",
  "build": "next build",
  "start": "node .next/standalone/server.js",
  "typecheck": "tsc --noEmit",
  "test": "vitest run",
  "e2e": "playwright test"
}
```

---

## 5. 설정 (환경변수)

web에는 **비밀값이 없다**. 빌드·실행 환경변수:

| 이름 | 값 | 용도 |
|---|---|---|
| `NEXT_TELEMETRY_DISABLED` | `1` | Next.js 사용 통계 전송 끔(NFR-36 취지 — 외부 전송 없음) |
| `HOSTNAME` | `0.0.0.0` | standalone 서버가 컨테이너 밖(nginx)에서 받도록 |
| `PORT` | `3000` | |
| `E2E_BASE_URL` (Playwright만) | 기본 `http://localhost:8080` | 05 A17 결과가 "localhost 실패"면 터널 주소 `https://<HOST>` |

`.env.example` 변경 없음.

---

## 6. fetch 클라이언트 (`web/lib/api.ts`)

브라우저에서만 쓴다(파일 머리 `"use client"`는 붙이지 않음 — 함수 모듈. 서버 컴포넌트에서 import하지 않는다).

### 6.1 시그니처
```ts
/** 서버가 돌려준 오류(05 형식)를 화면용으로 정규화한 것 */
export class ApiError extends Error {
  constructor(
    public readonly status: number,              // HTTP 상태, 네트워크 오류면 0
    public readonly code: string,                // 05 code 또는 아래 화면 전용 코드
    message: string,                             // 사용자에게 그대로 보여 줄 문구
    public readonly body: Record<string, unknown>, // 원 본문(예: 11 quota_exceeded의 limit·used)
    public readonly retryAfterS: number | null,  // Retry-After 헤더(초)
  ) { super(message); }
}

export const CSRF_COOKIE = "__Host-csrf";
export const CSRF_HEADER = "X-CSRF-Token";

/** document.cookie에서 이름이 같은 쿠키 값을 꺼낸다(없으면 null). */
export function readCookie(name: string, cookieString?: string): string | null;

/** GET /api/auth/csrf로 새 토큰을 받아 돌려준다(쿠키도 브라우저에 저장됨). */
export async function refreshCsrf(): Promise<string>;

/**
 * /api/ 경로에 같은 출처 요청을 보낸다.
 * @param path - 반드시 "/api/"로 시작(아니면 Error — 다른 곳으로 쿠키·토큰이 새지 않게)
 * @param init - fetch 옵션 + json(있으면 JSON 직렬화·Content-Type 설정)
 * @returns 2xx Response(SSE·음성처럼 본문을 직접 읽는 곳에서 사용)
 * @throws ApiError — 2xx가 아니거나 네트워크 오류. AbortError는 그대로 던진다
 */
export async function apiFetch(path: string, init?: RequestInit & { json?: unknown }): Promise<Response>;

/** apiFetch 후 JSON을 돌려준다. 204면 undefined. */
export async function apiJson<T>(path: string, init?: RequestInit & { json?: unknown }): Promise<T>;
```

### 6.2 처리 순서 (`apiFetch`)
1. `path`가 `/api/`로 시작하는지 확인.
2. 메서드가 `POST`·`PUT`·`PATCH`·`DELETE`면: `token = readCookie(CSRF_COOKIE) ?? await refreshCsrf()` → 헤더 `X-CSRF-Token: token`.
3. `json`이 있으면 `body = JSON.stringify(json)`, `Content-Type: application/json`. `FormData` 본문은 그대로(브라우저가 경계 포함 Content-Type을 붙임 — 17).
4. `fetch(path, { credentials: "same-origin", ...init })`. 네트워크 실패(`TypeError`) → `ApiError(0, "network_error", MSG_NETWORK)`.
5. 응답이 **403이고 본문 `code == "csrf_failed"`** 이며 아직 재시도 안 했으면 → `refreshCsrf()` → 2~4를 **1번만** 다시(05 §6.4). 두 번째도 실패면 그 오류를 던진다.
6. 2xx → Response 반환. 아니면 §6.3으로 `ApiError`.

- 쿠키·토큰을 localStorage·sessionStorage·전역 변수에 두지 않는다(NFR-04). CSRF 토큰은 요청마다 쿠키에서 읽는다(로그인·로그아웃이 쿠키를 바꾸므로).
- `__Host-session`은 HttpOnly라 JS에서 보이지 않는다 — 읽으려 하지 않는다.

### 6.3 오류 정규화
| 응답 | `code` | `message` |
|---|---|---|
| JSON에 `code`·`message` 있음 | 그대로 | 그대로(05·06·09·11 문구) |
| 422 (FastAPI 기본 본문) | `validation_error` | `입력값을 확인해 주세요.` (05 §4.1) |
| 네트워크 오류 | `network_error` | `서버에 연결할 수 없어요. 인터넷 연결을 확인하고 다시 시도해 주세요.` |
| 그 밖(JSON 아님·필드 없음, 502·504 등) | `server_error` | `일시적인 오류가 발생했어요. 잠시 후 다시 시도해 주세요.` |

- `retryAfterS` = `Retry-After` 헤더 정수(없으면 null).
- 위 화면 전용 문구 3개는 `api.ts` 상수(`MSG_VALIDATION`·`MSG_NETWORK`·`MSG_SERVER`)로 둔다.

### 6.4 인증 API 함수 (같은 파일)
```ts
export type Me = { id: number; username: string; email: string; role: "user" | "admin"; status: "pending" | "active" };
export function getMe(): Promise<Me>;                                                    // GET  /api/auth/me
export function login(username: string, password: string): Promise<Me>;                 // POST /api/auth/login
export function logout(): Promise<void>;                                                  // POST /api/auth/logout (204)
export function signup(username: string, email: string, password: string): Promise<{ status: "pending"; message: string }>;
export function changePassword(current: string, next: string): Promise<{ message: string }>;          // POST /api/auth/password
export function requestPasswordReset(email: string): Promise<{ message: string }>;                    // 202
export function confirmPasswordReset(email: string, code: string, newPassword: string): Promise<{ message: string }>;
```

### 6.5 입력 미리 검사 (`web/lib/validation.ts`)
서버가 최종 판단한다. 화면은 **보내기 전에 명백한 것만** 막아 같은 문구를 보여 준다(G4 Q7 "거절 시 같은 문구로 이유 표시").
```ts
export const PASSWORD_RULE_TEXT = "비밀번호는 10자 이상, 흔한 비밀번호는 쓸 수 없어요.";   // 05 §4.3 화면 규칙 문구
export const USERNAME_RULE_TEXT = "아이디는 영문·숫자·밑줄(_)로 4~20자여야 해요.";         // 05 MSG_INVALID_USERNAME
/** 각 함수는 문제가 없으면 null, 있으면 화면에 보일 문구를 돌려준다. */
export function checkUsername(raw: string): string | null;    // trim·소문자 후 /^[a-z0-9_]{4,20}$/
export function checkEmail(raw: string): string | null;       // trim 후 /^[^@\s]+@[^@\s]+\.[^@\s]+$/, 254자 이하 → "이메일 형식이 올바르지 않아요."
export function checkPassword(pw: string): string | null;     // [...pw].length(코드포인트 — 05 Python len과 같음) <10 → "비밀번호는 10자 이상이어야 해요." / >128 → "비밀번호는 128자 이하여야 해요."
export function checkPasswordConfirm(pw: string, confirm: string): string | null;   // 다르면 "두 비밀번호가 같지 않아요."
```
- 문구는 05 §4.3과 글자까지 같게 둔다(파일 머리 주석에 "05 errors.py와 같게 유지" 명시). 흔한 비밀번호 검사는 서버만 한다(목록을 브라우저에 보내지 않음).

---

## 7. 화면

공통: 모든 페이지는 모바일 우선 반응형(한 열, 최대 폭 `max-w-sm`~`md`), 입력은 `<label>` 연결, 제출 중 버튼 비활성·"처리 중…" 표시, 오류는 폼 위 알림 영역(`role="alert"`)에 `ApiError.message`를 그대로. 인증 화면은 `"use client"` 컴포넌트, 라우팅은 `next/navigation`의 `useRouter`.

### 7.1 로그인 확인 게이트 (`components/AuthGate.tsx`, `app/(chat)/layout.tsx`)
```tsx
/** (chat) 아래 화면을 감싸 로그인·승인 상태를 확인하고, 통과하면 me를 컨텍스트로 내려준다. */
export function AuthGate({ children }: { children: React.ReactNode }): JSX.Element;
/** AuthGate 안에서 현재 사용자 정보를 꺼낸다. */
export function useMe(): Me;
```
상태 전이:
```
loading ──getMe 200 status=active──▶ ready(children 렌더, MeContext)
   ├──200 status=pending──▶ router.replace("/pending")
   ├──ApiError 401──▶ router.replace("/login")
   └──그 밖 오류──▶ error(문구 + "다시 시도" 버튼 → loading)
```
- `loading` 동안 빈 화면 + 작은 "불러오는 중…"(깜박임 최소).
- 서버 컴포넌트에서 쿠키를 읽어 판단하지 않는다(ADR-12). 권한 판단은 api.

### 7.2 로그인 `/login`
- 입력: 아이디, 비밀번호. 링크: "가입 신청" → `/signup`, "비밀번호를 잊었어요" → `/reset`.
- 제출 → `login()`:
  - 성공 `status=active` → `router.replace("/")`, `pending` → `/pending`.
  - `login_failed`·`too_many_attempts`(문구에 "N분" 포함)·`csrf_failed`·`network_error` → 알림에 문구.
- 미리 검사: 빈 칸만(형식 검사 없음 — 05: 틀린 형식도 "없는 아이디"와 같게).

### 7.3 가입 신청 `/signup`
- 입력: 아이디(아래 `USERNAME_RULE_TEXT` 도움말), 이메일, 비밀번호(아래 `PASSWORD_RULE_TEXT` **항상 표시**), 비밀번호 확인(14-Q4).
- 미리 검사: `checkUsername`·`checkEmail`·`checkPassword`·`checkPasswordConfirm` → 해당 칸 아래 문구, 서버 호출 안 함.
- 제출 → `signup()` → 201 → 폼을 숨기고 서버 `message`(05 `MSG_SIGNUP_OK`) + "로그인하러 가기" 버튼. **자동 로그인 안 함**(05).
- 서버 거절: `weak_password`(reason별 문구)·`invalid_*`·`username_taken`·`email_taken`·`too_many_requests` → 알림에 서버 문구.

### 7.4 승인 대기 `/pending`
- 내용: 05 `MSG_PENDING_APPROVAL` 문구와 같은 안내("관리자 승인을 기다리고 있어요. 승인되면 채팅을 쓸 수 있어요.") — 화면 고정 문구로 둔다(이 화면은 API 오류 응답 없이 도착하므로).
- 버튼: "승인됐는지 확인" → `getMe()` → active면 `/`, pending이면 "아직 승인 전이에요." 표시, 401이면 `/login`. "로그아웃" → `logout()` → `/login`.
- 자동 새로고침(폴링) 없음.

### 7.5 비밀번호 재설정 `/reset` (06)
상태 전이:
```
email ──requestPasswordReset 202──▶ code(서버 message 표시: "…있으면 인증코드를 보냈어요. 10분 안에…")
code ──confirmPasswordReset 200──▶ done(서버 MSG_RESET_DONE + "로그인하러 가기")
code ──reset_failed / weak_password / too_many_requests──▶ code(알림, 입력 유지)
code ──"인증코드 다시 받기"──▶ email(입력한 이메일 유지)
```
- 1단계: 이메일(`checkEmail`). 2단계: 인증코드(6자리 안내, `inputMode="numeric"`, `autoComplete="one-time-code"`, 공백은 서버가 지움), 새 비밀번호·확인(`PASSWORD_RULE_TEXT` 항상 표시, `checkPassword`·`checkPasswordConfirm`).
- `done` 화면에서 로그인 링크. 06이 세션 쿠키를 지우므로 로그인 상태였어도 다시 로그인해야 한다.

### 7.6 계정 `/account` ((chat) 아래 — AuthGate 통과 필요)
- 표시: 아이디·이메일(`useMe()`).
- 비밀번호 변경: 현재 비밀번호, 새 비밀번호(`PASSWORD_RULE_TEXT` 항상 표시), 확인 → `changePassword()` → 성공 시 서버 `MSG_PASSWORD_CHANGED`("…다른 기기의 로그인은 모두 해제됐어요.") 표시, 입력 비움. 거절 `wrong_current_password`·`weak_password`·`too_many_attempts` → 알림.
- "로그아웃" → `logout()` → `router.replace("/login")`.
- "채팅으로" 링크 → `/`.

### 7.7 임시 `/` ((chat)/page.tsx — 15가 교체)
- "채팅 화면은 준비 중이에요." + 아이디 표시 + "계정" 링크. 15 병합 시 이 파일 전체를 바꾼다.

### 7.8 루트 레이아웃 (`app/layout.tsx`)
```ts
export const metadata: Metadata = {
  title: "nadri — 서울·제주 여행 챗봇",
  description: "한국관광공사 공공데이터 기반 서울·제주 여행 안내",
  appleWebApp: { capable: true, title: "nadri", statusBarStyle: "default" },
  icons: { icon: "/icons/icon-192.png", apple: "/icons/apple-touch-icon.png" },
};
export const viewport: Viewport = { width: "device-width", initialScale: 1, viewportFit: "cover", themeColor: "#0f766e" };
```
- `<body>`에 `<RegisterSW />`.
- 폰트: 시스템 글꼴(외부 웹폰트 내려받기 없음 — `next/font/google`은 빌드 때 외부 호출).

---

## 8. PWA (NFR-52, S17)

### 8.1 `app/manifest.ts`
```ts
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "nadri — 서울·제주 여행 챗봇", short_name: "nadri", lang: "ko",
    start_url: "/", scope: "/", display: "standalone",
    background_color: "#ffffff", theme_color: "#0f766e",
    icons: [
      { src: "/icons/icon-192.png", sizes: "192x192", type: "image/png" },
      { src: "/icons/icon-512.png", sizes: "512x512", type: "image/png" },
      { src: "/icons/icon-maskable-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
    ],
  };
}
```
- 주소: `/manifest.webmanifest`(Next가 자동 연결).

### 8.2 아이콘
- 원본 `web/public/icons/icon.svg`(단색 바탕 + 글자 "나", maskable은 가장자리 여백 20%). PNG는 `docs/images` 그림과 같은 방식(debian 컨테이너 + `librsvg2-bin`의 `rsvg-convert` + `fonts-noto-cjk`)으로 **한 번 만들어 커밋**한다 — 빌드 때 변환하지 않음. 변환 명령은 `CLAUDE.md` 명령어 절에 한 줄 적는다.
- 크기: 192, 512, maskable 512, `apple-touch-icon.png` 180×180(iOS는 manifest 아이콘 대신 이것을 씀 — 알려진 동작, **미확인**).

### 8.3 서비스워커 `public/sw.js` (최소, 오프라인 캐시 없음)
```js
// nadri 최소 서비스워커 — 설치 조건 충족용. 캐시하지 않고 /api/* 는 절대 가로채지 않는다(SSE 보호, [A] §2.1).
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (e) => e.waitUntil(self.clients.claim()));
self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  // 1) 다른 출처·GET 아닌 요청·/api/ 는 손대지 않는다(브라우저 기본 처리)
  if (url.origin !== self.location.origin || event.request.method !== "GET" || url.pathname.startsWith("/api/")) return;
  // 2) 페이지 이동 요청만 네트워크로 그대로 넘긴다(캐시 없음)
  if (event.request.mode === "navigate") event.respondWith(fetch(event.request));
});
```
- `fetch` 핸들러를 두는 이유: Android Chrome 설치 조건에 fetch 핸들러가 필요한지가 **미확인**(S17 C안 미확인) — 무해한 통과용으로 둔다. HITL-1에서 설치 확인.
- 페이지 이동이 오프라인이면 브라우저 기본 오류 화면(오프라인 페이지 없음 — 범위 밖).

### 8.4 `components/RegisterSW.tsx`
```tsx
/** 운영 빌드에서만 /sw.js를 등록한다(개발 중엔 캐시 혼동 방지로 등록 안 함). 화면에 아무것도 그리지 않는다. */
export function RegisterSW(): null;
```
- `useEffect`: `process.env.NODE_ENV === "production" && "serviceWorker" in navigator` → `navigator.serviceWorker.register("/sw.js", { scope: "/" })`. 실패는 `console.warn` 1줄.

---

## 9. 컨테이너·nginx

### 9.1 `web/Dockerfile`
```
FROM node:<LTS>-alpine AS deps      # npm ci
FROM node:<LTS>-alpine AS build     # npm run build (NEXT_TELEMETRY_DISABLED=1)
FROM node:<LTS>-alpine AS runner    # .next/standalone + .next/static + public 복사
  USER node                          # 이미지에 있는 비루트 사용자(uid 1000)
  ENV NODE_ENV=production HOSTNAME=0.0.0.0 PORT=3000 NEXT_TELEMETRY_DISABLED=1
  CMD ["node", "server.js"]
FROM deps AS dev                    # compose.dev.yaml 전용: next dev
```
- `<LTS>`: Next 16이 지원하는 Node LTS 중 최신 메이저를 **태그까지 고정**(예상 `node:24-alpine` 계열 — **미확인**, 구현 시 Next 16 요구 버전 확인 후 기록). WSL에 설치하는 Node(14-Q1)와 메이저를 맞춘다.
- 헬스체크: `node -e "fetch('http://127.0.0.1:3000/manifest.webmanifest').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"`.

### 9.2 `compose.yaml`
| 서비스 | 변경 |
|---|---|
| `web` | **신규**. `build: {context: ./web, target: runner}`, 호스트 포트 없음, `user: "1000:1000"`, `cap_drop: [ALL]`, `security_opt: [no-new-privileges:true]`, 비밀값 주입 없음, `restart: unless-stopped`, 헬스체크(§9.1) |
| `nginx` | `depends_on`에 `web` 추가 |

### 9.3 `compose.dev.yaml` (14-Q3)
- `web`: `build.target: dev`, `command: npm run dev -- --hostname 0.0.0.0 --port 3000`, `./web:/app` 바인드 + `/app/node_modules`·`/app/.next` 익명 볼륨, `NODE_ENV=development`. 파일 감시가 바인드 마운트에서 안 잡히면 `WATCHPACK_POLLING=true`(**미확인** — WSL 리눅스 파일시스템에서는 필요 없을 것으로 예상).

### 9.4 `infra/nginx/nginx.conf` (02의 `location /` 교체)
```nginx
  location / {
    proxy_pass http://web:3000;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $client_ip;
    proxy_set_header Upgrade $http_upgrade;     # next dev 핫리로드(웹소켓) — 운영에선 쓰이지 않음
    proxy_set_header Connection $connection_upgrade;
  }
```
- `map $http_upgrade $connection_upgrade { default upgrade; "" ""; }`를 `http` 맥락(파일 위쪽)에 추가. 02의 `/api/` 블록은 그대로(`Connection ""` 유지).
- `/admin`은 같은 `location /`로 web에 간다(별도 블록 없음 — [A] §2 "`/`·`/admin`→web").

---

## 10. 테스트 도구 설정

- `vitest.config.ts`: `environment: "jsdom"`, `setupFiles: ["./vitest.setup.ts"]`, `include: ["tests/unit/**/*.test.{ts,tsx}"]`, 별칭 `@` → 프로젝트 루트, 플러그인 `@vitejs/plugin-react`.
- `playwright.config.ts`: `testDir: "e2e"`, `use.baseURL = process.env.E2E_BASE_URL ?? "http://localhost:8080"`, 프로젝트 `chromium`(데스크톱) + `mobile-chrome`(`devices["Pixel 7"]`), `globalSetup: "./e2e/global-setup.ts"`, `webServer` 없음(**compose가 떠 있어야 함**), `retries: 0`, `workers: 1`(같은 DB를 쓰므로).
- `e2e/helpers/db.ts`: 저장소 루트에서 `docker compose exec -T postgres psql -U postgres -d nadri -v ON_ERROR_STOP=1 -At -c <SQL>` 실행(`execFileSync`, 인자 배열 — 셸 문자열 조립 없음). 테스트 사용자는 아이디 접두어 `e2e_`만 만들고 지운다.
- `e2e/global-setup.ts`: `delete from users where username like 'e2e\_%'`, `delete from rate_limits where key like 'signup:%' or key like 'login:%' or key like 'reset%' or key like 'pwchange:%'` — 가입 IP 제한(1시간 5회)·로그인 잠금이 반복 실행을 막지 않게. **개발 DB에서만 실행**(운영 DB 없음 — 1인 데모).

Playwright가 쓰는 브라우저는 WSL에 설치한다: `npx playwright install --with-deps chromium`(시스템 라이브러리 설치에 `sudo` 필요 — 사용자에게 1회 요청).

---

## 11. 엣지케이스

| 상황 | 동작 |
|---|---|
| 첫 방문(CSRF 쿠키 없음)에서 로그인 | `refreshCsrf()` 후 요청 |
| 브라우저가 세션 쿠키만 지움(토큰 바인딩 불일치) | 403 `csrf_failed` → 새 토큰 → 1번 재시도 → 성공 |
| 재시도도 `csrf_failed` | 알림에 05 문구("…새로고침한 뒤…") |
| 로그인 응답 직후 다음 요청 | 로그인이 준 새 `__Host-csrf`를 읽어 사용 |
| `/`에 로그인 안 하고 접근 | `/login` |
| pending 사용자가 `/` 또는 `/account` | `/pending` |
| pending 사용자가 `/pending`에서 비밀번호 변경 | 화면 없음(계정 화면은 active만). 필요하면 재설정 사용 — 요구사항 범위 안(FR-04 "승인 대기 안내만") |
| disabled된 뒤 화면 사용 | 다음 api 호출 401 → `/login`(AuthGate·각 화면) |
| 로그인 5회 실패 | 429 문구 "N분 뒤" |
| 가입 이메일 중복 | 409 문구(재설정 안내) |
| 재설정 코드 틀림 5회 | 06 `reset_failed`(이유 숨김) — 화면은 같은 문구 |
| 비밀번호 9자 입력 | 서버 호출 없이 "10자 이상" 문구 |
| 이모지 포함 비밀번호 | 코드포인트로 길이 계산(서버와 같음) |
| 422(본문 형식) | "입력값을 확인해 주세요." |
| api 다운(502 HTML) | `server_error` 문구 |
| 오프라인 | `network_error` 문구 |
| 개발 모드(`next dev`) | SW 등록 안 함 |
| SW가 `/api/*` 요청을 받음 | 손대지 않음(`respondWith` 없음) |
| iOS 홈 화면 실행 | `apple-touch-icon`·`appleWebApp`으로 전체화면 |
| `localhost:8080`에서 `__Host-` 쿠키(A17 실패 시) | 브라우저 확인·Playwright는 터널 주소로(`E2E_BASE_URL`) |

---

## 12. 앞 작업과 달라지는 점 · 앞 작업 테스트 수정

| # | 내용 | 대상 | 처리 |
|---|---|---|---|
| 1 | nginx `location /`가 404 → web 프록시 | 02 nginx 관련 테스트·HITL(`/`가 404라는 기대가 있으면) | 기대를 "web 응답(200)"으로. `/api/` 동작은 불변 |
| 2 | compose에 `web` 추가 | 26 `test_compose_hardening.py`(아직 없음) | 26에서 web도 점검 대상에 포함 |
| 3 | `CLAUDE.md` 작업 환경에 Node(fnm) 추가(14-Q1 결정 2026-11-22) | 문서 | 문서 담당이 반영 완료 — 구현 때 버전만 확인 |
| 4 | 백엔드 코드 변경 없음 | — | — |

상위 문서와의 차이(구현 판단):
1. `(chat)/layout.tsx`·`AuthGate`·임시 `/` 추가 — [PL] 파일 목록에 없지만 로그인 분기(완료 기준 "승인 대기/채팅 진입 분기")에 필요.
2. 서비스워커에 통과용 `fetch` 핸들러(§8.3) — "최소"의 범위 안, 설치 조건 미확인 대비.
3. 가입·재설정·변경 화면의 "비밀번호 확인" 칸(14-Q4).

---

## 13. 완료 기준 (DoD)

1. `cd ~/code/myAgent/web && npm ci && npm run typecheck && npm run test` 통과.
2. compose 기동 상태에서 `npm run e2e` 통과(test.md ①-B), `E2E_BASE_URL` 기본값 또는 터널 주소.
3. 가입 신청 → psql 승인 → 로그인 → `/`(임시 화면), pending → `/pending`, 재설정 2단계 화면, 비밀번호 변경.
4. 가입·재설정·변경 화면에 비밀번호 규칙 문구가 **입력 전부터** 보이고, 서버 거절 이유가 같은 문구로 보인다(G4 Q7).
5. `/manifest.webmanifest`·아이콘·`/sw.js` 제공, `/api/*` 요청이 서비스워커를 거치지 않음(Playwright), HITL-1 Android 설치·iOS 홈 화면 추가 전체화면 확인.
6. web 컨테이너 비루트·`cap_drop: [ALL]`·`no-new-privileges`, 호스트 포트 없음.
7. localStorage·sessionStorage 사용 코드 없음(grep 테스트).
8. 모든 함수·컴포넌트에 한국어 JSDoc(요약·인자·반환), 함수 안 단계 주석([CL]).
9. `CLAUDE.md` 명령어 절에 web 명령 추가(Node 실제 버전이 문서와 다르면 CLAUDE.md·README도 맞춤). 커밋 `feat/14-web-foundation`, `[Feat] …` + 작업 목록 + `Author:`, AI 공동작성 표기 없음. `dev` 병합은 G5 후. `PROGRESS.md` 갱신.

---

## 14. 확인 질문

| # | 질문 | 추천안 | 대안 |
|---|---|---|---|
| 14-Q1 | 웹 테스트(Vitest·Playwright)와 `npm ci`를 어디서 돌릴까. CLAUDE.md는 WSL 개발 도구를 Python·uv만 적어 두었다 | **결정(2026-11-22): 추천안대로** — **WSL Ubuntu에 Node LTS 설치**(버전 관리 도구 `fnm` 또는 NodeSource 중 하나 — 추천 `fnm`), Playwright 브라우저도 WSL에. CLAUDE.md "작업 환경"에 한 줄 추가 | 웹 테스트도 Docker 컨테이너 안에서만 실행(WSL에 Node 없음, 명령이 길어지고 Playwright 이미지 필요) |
| 14-Q2 | 패키지 관리자 | **결정(2026-11-22): 추천안대로** — **npm**(Node 기본 포함, 추가 설치 없음) | pnpm(빠르고 디스크 절약, 도구 추가) |
| 14-Q3 | 개발 중 화면 수정을 어떻게 바로 볼까 | **결정(2026-11-22): 추천안대로** — **`compose.dev.yaml`에서 web을 `next dev`(소스 마운트)로** — api의 `--reload`와 같은 방식, 같은 `localhost:8080` 주소 | WSL에서 `npm run dev`를 직접 띄우고 nginx가 호스트로 넘기게(설정 추가) / 매번 `--build` |
| 14-Q4 | 가입·재설정·변경 화면에 "비밀번호 확인"(두 번 입력) 칸을 둘까(요구사항엔 없음) | **결정(2026-11-22): 추천안대로** — **둔다**(오타로 가입하면 메일 재설정을 거쳐야 함 — 칸 1개, 서버 변경 없음) | 두지 않음(요구사항 그대로) |
| 14-Q5 | 앱 아이콘 디자인 | **결정(2026-11-22): 추천안대로** — **임시 단색 아이콘("나" 글자, 청록 `#0f766e`)** — 나중에 파일만 바꾸면 됨 | 사용자가 아이콘을 준비 |
| 14-Q6 | Playwright가 테스트 사용자를 만들고 승인하는 방법(관리자 API는 18) | **결정(2026-11-22): 추천안대로** — **`docker compose exec postgres psql`로 직접 승인·정리**(`e2e_` 접두어 사용자만, 가입·로그인 요청 제한 카운터도 지움) | 테스트 전용 API 추가(운영 코드에 테스트 경로가 생김) |
| 14-Q7 | 승인 대기 화면에서 자동으로 승인 여부를 확인할까 | **결정(2026-11-22): 추천안대로** — **안 함 — "승인됐는지 확인" 버튼만**(폴링 없음) | 30초마다 `me` 조회 |
