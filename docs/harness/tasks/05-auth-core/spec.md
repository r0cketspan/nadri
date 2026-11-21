# 05-auth-core — 가입 신청·로그인·세션·CSRF·잠금·관리자 CLI (spec)

> 하네스 Phase 4 산출물 (spec-writer, 작성 2026-11-21). 상태: **초안 — 사용자 검토 대기**. 브랜치 `feat/05-auth-core`, 의존 작업 02-e2e-chat-slice, 04-db-schema.
> 입력: [PL]=program_list.md(G4 승인본) §2 표·§3 "05-auth-core"·§5 Q1·Q7 · [A]=architecture.md §2.1(`auth`·`ratelimit`·`cli`)·§3.4·§6.1·§9 "인증·세션"·ADR-10·12·15·§12 A17 · [R]=requirements.md FR-01~04·06·80, NFR-01~06·10·34 · [E]=ERD · [SG]=SECURITY_GUIDE.md · 01 spec(config·CLI·compose) · 02 spec(api 앱·채팅 엔드포인트·nginx·cloudflared) · **04 spec(테이블·ORM 이름 정본)**.
> 06(비밀번호 재설정)은 이 작업의 세션·비밀번호 규칙·요청 제한·오류 형식을 그대로 재사용한다 — §6의 이름이 06과의 약속이다.
> **미확인** = 문서·공식 자료로 확인하지 못해 구현 중 확인해야 하는 사실.

---

## 1. 작업 목표

인증 API 전체(재설정 제외)와 첫 관리자 CLI를 만들고, 02의 채팅 엔드포인트를 **활성 사용자만** 쓰게 막은 뒤, `cloudflared`를 상시 기동으로 바꾼다(G4 Q1) [PL §3].

- 끝나면: 가입 신청 → (관리자 승인 — 05에서는 DB 직접 수정, 화면·API는 18) → 로그인 → 채팅. `pending`은 로그인되지만 채팅 403, `rejected`·`disabled`는 로그인 실패와 같은 문구. 상태 변경 요청은 CSRF 토큰이 없으면 403. 5회 실패 → 15분 잠금. 비밀번호를 바꾸면 다른 세션이 모두 끊긴다. 터널 주소에서 로그인 쿠키가 동작한다.
- 추적: FR-01·02·03·04(API)·06·80(CLI), NFR-01~05·06(로그인)·10·34, ADR-10·15, A17.

### 1.1 넣지 않는 것
| 하지 않는 것 | 담당 작업 |
|---|---|
| 비밀번호 재설정(인증코드 메일) | 06 |
| 로그인·가입·승인 대기·비밀번호 변경 **화면**, 프론트 fetch 클라이언트 | 14 |
| 관리자 승인·거절·비활성화 API·화면 | 18 (05는 `require_admin`만 만들어 둠) |
| 채팅 분당 10회 제한·일일 한도 | 11 (05의 `ratelimit` 모듈을 그대로 씀) |
| 대화 세션 소유 확인(`session_id`가 내 것인지) | 09 |
| 만료 세션·오래된 `rate_limits` 일괄 정리 | 21 (05는 접근 시 만료 세션만 지움) |
| 비밀번호 해시 재계산(`check_needs_rehash`), 동시 로그인 수 제한, "모든 기기 로그아웃" 버튼 | 범위 밖(요구사항 없음) |

---

## 2. 생성·수정 파일

경로의 `nadri/`는 `backend/src/nadri/`.

| 파일 | 신규/수정 | 역할 |
|---|---|---|
| `nadri/api/errors.py` | 신규 | `ApiError` 예외 + 핸들러(`{"code","message"}` 본문), 사용자 문구 상수 (§4.3) |
| `nadri/api/auth/__init__.py` | 신규 | 빈 파일 |
| `nadri/api/auth/router.py` | 신규 | `signup`·`login`·`logout`·`password`·`me`·`csrf` 엔드포인트 (§4) |
| `nadri/api/auth/service.py` | 신규 | 아이디·이메일 정규화·검사, 비밀번호 규칙, Argon2id, 가입·인증·비밀번호 변경·관리자 생성 (§6.2) |
| `nadri/api/auth/sessions.py` | 신규 | 서버 세션(해시 저장·만료·재발급·폐기), 세션 쿠키 (§6.3) |
| `nadri/api/auth/csrf.py` | 신규 | 서명된 double-submit 토큰, CSRF 쿠키, ASGI 미들웨어 (§6.4) |
| `nadri/api/ratelimit.py` | 신규 | `rate_limits` 고정 윈도 카운터·잠금·점진 지연·실제 IP (§6.5) — 06·11·17이 재사용 |
| `nadri/api/deps.py` | 신규 | `get_db`·`get_now`·`get_sleep`·`current_user`·`require_active`·`require_admin` (§6.6) |
| `nadri/core/data/common_passwords.txt` | 신규 | 흔한 비밀번호 목록(SecLists 공개 목록 중 10자 이상, §5.3) |
| `nadri/api/main.py` | 수정(02) | DB 엔진·세션 팩토리를 앱 상태에, `ApiError` 핸들러, CSRF 미들웨어, auth 라우터 등록, `SESSION_SECRET` 필수 검사 (§6.7) |
| `nadri/api/chat/router.py` | 수정(02) | `post_message`에 `Depends(require_active)` 추가 (§6.8) |
| `nadri/core/config.py` | 수정(01·02) | `SESSION_SECRET` 추가 (§3) |
| `nadri/cli.py` | 수정(01) | `nadri create-admin` (§7) |
| `compose.yaml` | 수정 | `cloudflared`의 `profiles` 제거(상시), api에 DB·`SESSION_SECRET` 주입, api 기동 순서 (§8) |
| `.env.example` | 수정 | `SESSION_SECRET` 이름 추가 |
| `backend/pyproject.toml`, `uv.lock` | 수정 | `argon2-cffi` 추가 |
| `backend/tests/...` | 신규·수정 | test.md. **02의 `tests/api/test_main.py`·`test_chat_stream.py` 중 엔드포인트 호출 테스트를 인증·CSRF에 맞게 수정**(§6.8) |

> [PL] 파일 목록에 없는 것: `errors.py`(오류 본문 형식을 06·09 이후가 공유), `auth/__init__.py`, `main.py`·`config.py`·`.env.example`·`pyproject.toml` 수정, 02 테스트 수정, `GET /api/auth/csrf`(§9 차이 3).

---

## 3. 설정 · 환경변수

| 이름 | 타입·기본값 | 용도 |
|---|---|---|
| `SESSION_SECRET` | `SecretStr \| None = None`. api 기동 시 **필수, 32자 이상** — 아니면 `create_app`이 한국어 메시지와 함께 `RuntimeError` | CSRF 토큰 서명(06에서 인증코드 해시 키로도 사용) |
| `DB_USER`·`DB_PASSWORD` 등 | 01 그대로 | api도 이제 DB 사용(`nadri_app`) |

- 세션 시간·잠금 횟수 등은 요구사항이 정한 고정값이라 **설정으로 빼지 않고 코드 상수**로 둔다(§6.3·§6.5).
- `.env.example` 추가 줄: `# 세션·CSRF 서명 키 — openssl rand -hex 32 로 생성` / `SESSION_SECRET=`

---

## 4. API

모든 경로는 `/api/auth/*`. 응답 본문은 JSON(UTF-8). 쿠키 이름·속성은 §6.3·§6.4.

### 4.1 엔드포인트

| 메서드·경로 | 인증 | CSRF | 요청 본문 | 성공 응답 | 실패 응답 (§4.3 코드) |
|---|---|---|---|---|---|
| `GET /api/auth/csrf` | 없음 | — | — | 200 `{"csrf_token": str}` + `__Host-csrf` 쿠키 | — |
| `POST /api/auth/signup` | 없음 | 필요 | `{"username", "email", "password"}` | 201 `{"status":"pending","message": MSG_SIGNUP_OK}` | 400 `invalid_username`·`invalid_email`·`weak_password` / 409 `username_taken`·`email_taken` / 429 `too_many_requests` / 422 |
| `POST /api/auth/login` | 없음 | 필요 | `{"username", "password"}` | 200 `UserOut` + `__Host-session`·`__Host-csrf` 쿠키 | 401 `login_failed` / 429 `too_many_attempts`(+`Retry-After`) / 422 |
| `POST /api/auth/logout` | 선택 | 필요 | — | 204, 세션 쿠키 삭제 + 새 익명 `__Host-csrf` | — (세션 없어도 204) |
| `POST /api/auth/password` | 필요(pending·active) | 필요 | `{"current_password", "new_password"}` | 200 `{"message": MSG_PASSWORD_CHANGED}` | 401 `unauthenticated` / 400 `wrong_current_password`·`weak_password` / 429 `too_many_attempts` / 422 |
| `GET /api/auth/me` | 필요(pending·active) | — | — | 200 `UserOut` | 401 `unauthenticated` |
| (02) `POST /api/chat/sessions/{id}/messages` | **active만** | 필요 | 02 그대로 | 02 그대로(SSE) | 401 `unauthenticated` / 403 `pending_approval` / 403 `csrf_failed` (SSE 시작 전) |

- `UserOut = {"id": int, "username": str, "email": str, "role": "user"|"admin", "status": "pending"|"active"}`.
- 요청 본문 모델(pydantic): 모든 필드 `str`, 필수. 길이 상한만 둔다(터무니없는 입력 차단, 넘으면 FastAPI 기본 422): `username ≤ 100`, `email ≤ 320`, `password`·`current_password`·`new_password ≤ 1000`. 형식·규칙 검사는 서비스가 해서 400 코드로 돌려준다(화면에 이유를 보여 주기 위해).
- 422 본문은 FastAPI 기본 형식을 그대로 둔다(02 테스트와 같음). 화면(14)은 422를 "입력값을 확인해 주세요."로 표시한다.
- `CSRF 필요` = §6.4 미들웨어가 `/api/` 아래 `POST`·`PUT`·`PATCH`·`DELETE` 전부에 적용(로그인 전 요청 포함 — 확인 질문 Q5).

### 4.2 처리 순서

**signup** (FR-04, NFR-01)
1. `allow(db, f"signup:ip:{ip}", SIGNUP_RULE, now)` → **바로 커밋**(뒤 단계가 실패해도 시도는 셈) → 거부면 429 `too_many_requests`(+`Retry-After`) (확인 질문 Q4).
2. `username = normalize_username(raw)` → `validate_username` / `email = normalize_email(raw)` → `validate_email` / `validate_password(password)` — 이 순서로 첫 실패를 400.
3. `password_hash = await hash_password(password)`(스레드에서 실행 — 이벤트 루프 막지 않음).
4. `INSERT users(username, email, password_hash)` — `role='user'`, `status='pending'`은 DB 기본값.
5. `IntegrityError` → `constraint_name(exc)`가 `uq_users_username`이면 409 `username_taken`, `uq_users_email`이면 409 `email_taken`(확인 질문 Q3).
6. 커밋 → 201. **로그인시키지 않는다**(세션·쿠키 없음).

**login** (FR-01, FR-04, NFR-02·03)
1. `username = normalize_username(raw)`(형식 검사는 하지 않음 — 틀린 형식도 "없는 아이디"와 같게 처리), `ip = client_ip(request)`.
2. 키 `ip_key = f"login:ip:{ip}"`, `acct_key = f"login:acct:{key_hash(username)}"`. 둘 중 하나라도 `get_lock(...)`이 잠금 중이면 → 429 `too_many_attempts`, `Retry-After` = 늦은 쪽 해제까지 초(올림). **비밀번호 검사도 하지 않는다.**
3. `user = SELECT users WHERE username = :username`.
4. `ok = await verify_password(user.password_hash if user else None, password)` — 사용자가 없으면 더미 해시로 검사해 응답 시간을 맞추고 False.
5. `ok and user.status in ("pending", "active")`가 아니면(없는 아이디·틀린 비밀번호·`rejected`·`disabled` 전부) → 실패:
   - `s1 = hit(ip_key, LOGIN_FAILURE_RULE)`, `s2 = hit(acct_key, LOGIN_FAILURE_RULE)` → 커밋
   - `await sleep(failure_delay_s(max(s1.count, s2.count)))`
   - 401 `login_failed`(이번 응답은 401. 5번째 실패로 잠겼다면 **다음 요청부터** 429)
6. 성공: `reset(acct_key)`(IP 카운터는 그대로 — 자기 계정 성공으로 IP 카운터를 지우는 우회 방지) → 요청에 기존 세션 쿠키가 있으면 그 세션 행 삭제(세션 고정 방지, FR-01 "재발급") → `token = await create_session(db, user.id, now)` → 커밋.
7. 응답 200 `UserOut`, `set_session_cookie(resp, token)`, `set_csrf_cookie(resp, issue_token(secret, binding_for(token)))`.

**logout** (FR-02)
1. 세션 쿠키가 있으면 `revoke_session(db, hash_token(token))` → 커밋(없는 세션이어도 오류 아님).
2. 204, `clear_session_cookie(resp)`, `set_csrf_cookie(resp, issue_token(secret, ANON))`.

**password** (FR-03, NFR-01)
1. `cu = current_user`(pending·active).
2. `key = f"pwchange:user:{cu.user.id}"`. 잠금 중 → 429 `too_many_attempts`.
3. `validate_password(new_password)` 실패 → 400 `weak_password`(시도 횟수 안 셈).
4. `verify_password(cu.user.password_hash, current_password)` 실패 → `hit(key, PASSWORD_CHANGE_FAILURE_RULE)` → 커밋 → 점진 지연 → 400 `wrong_current_password`.
5. 성공: `password_hash` 갱신 → `revoke_all_sessions(db, user.id, except_id_hash=cu.session_hash)` → `reset(key)` → 커밋 → 200. **현재 세션은 유지**한다(확인 질문 Q6).

**me**: `current_user` → 200 `UserOut`.

**csrf**: `binding = binding_for(요청의 세션 쿠키 값 또는 None)` → `token = issue_token(secret, binding)` → 200 `{"csrf_token": token}` + 쿠키.

### 4.3 사용자에게 보이는 문구 (통일 — `errors.py` 상수)

| code | HTTP | 상수 | 문구 |
|---|---|---|---|
| `unauthenticated` | 401 | `MSG_UNAUTHENTICATED` | 로그인이 필요해요. |
| `login_failed` | 401 | `MSG_LOGIN_FAILED` | 아이디 또는 비밀번호가 맞지 않아요. |
| `too_many_attempts` | 429 | `MSG_TOO_MANY_ATTEMPTS` | 시도가 너무 많아요. {minutes}분 뒤에 다시 시도해 주세요. |
| `too_many_requests` | 429 | `MSG_TOO_MANY_REQUESTS` | 요청이 너무 많아요. 잠시 후 다시 시도해 주세요. |
| `pending_approval` | 403 | `MSG_PENDING_APPROVAL` | 관리자 승인을 기다리고 있어요. 승인되면 채팅을 쓸 수 있어요. |
| `forbidden` | 403 | `MSG_FORBIDDEN` | 접근 권한이 없어요. |
| `csrf_failed` | 403 | `MSG_CSRF_FAILED` | 보안 확인에 실패했어요. 페이지를 새로고침한 뒤 다시 시도해 주세요. |
| `invalid_username` | 400 | `MSG_INVALID_USERNAME` | 아이디는 영문·숫자·밑줄(_)로 4~20자여야 해요. |
| `invalid_email` | 400 | `MSG_INVALID_EMAIL` | 이메일 형식이 올바르지 않아요. |
| `weak_password` (reason `too_short`) | 400 | `MSG_PASSWORD_TOO_SHORT` | 비밀번호는 10자 이상이어야 해요. |
| `weak_password` (reason `too_long`) | 400 | `MSG_PASSWORD_TOO_LONG` | 비밀번호는 128자 이하여야 해요. |
| `weak_password` (reason `common`) | 400 | `MSG_PASSWORD_COMMON` | 너무 흔한 비밀번호예요. 다른 비밀번호를 써 주세요. |
| `username_taken` | 409 | `MSG_USERNAME_TAKEN` | 이미 사용 중인 아이디예요. |
| `email_taken` | 409 | `MSG_EMAIL_TAKEN` | 이미 가입 신청된 이메일이에요. 비밀번호를 잊었다면 비밀번호 재설정을 이용해 주세요. |
| `wrong_current_password` | 400 | `MSG_WRONG_CURRENT_PASSWORD` | 현재 비밀번호가 맞지 않아요. |

성공 문구: `MSG_SIGNUP_OK` = "가입 신청이 접수됐어요. 관리자가 승인하면 채팅을 쓸 수 있어요." / `MSG_PASSWORD_CHANGED` = "비밀번호를 바꿨어요. 다른 기기의 로그인은 모두 해제됐어요."

- 오류 본문: `{"code": str, "message": str}`. `weak_password`는 `"reason"` 필드 추가. 429는 `Retry-After` 헤더(초)와 본문 `"retry_after_s"`.
- `{minutes}` = `ceil(retry_after_s / 60)`, 최소 1.
- 계정 열거 방지(NFR-03): 없는 아이디·틀린 비밀번호·`rejected`·`disabled`는 **같은 코드·문구·상태**, 지연 규칙도 같다. 잠금 키도 없는 아이디에 똑같이 생기므로 `too_many_attempts`로 계정 존재를 알 수 없다.
- 화면(14)이 미리 보여 줄 규칙 문구(G4 Q7): "비밀번호는 10자 이상, 흔한 비밀번호는 쓸 수 없어요." — 거절 이유는 위 `weak_password` 문구로 표시.

---

## 5. 입력 규칙

### 5.1 아이디 (확인 질문 Q1)
- `normalize_username(raw) = raw.strip().lower()`.
- 유효: 정규식 `^[a-z0-9_]{4,20}$`(정규화 뒤). 저장은 정규화 값 → 대소문자만 다른 아이디는 같은 아이디.

### 5.2 이메일
- `normalize_email(raw) = raw.strip().lower()`.
- 유효: 길이 ≤ 254, 정규식 `^[^@\s]+@[^@\s]+\.[^@\s]+$`. 실제 수신 가능 여부는 확인하지 않는다(가입은 관리자 승인, 메일은 06에서만 사용 — NFR-34).

### 5.3 비밀번호 (NFR-01, G4 Q7)
- 길이: `len(password)`(유니코드 문자 수) 10 이상 128 이하. 앞뒤 공백을 지우지 않는다(그대로 해시).
- 흔한 비밀번호: `password.lower() in load_common_passwords()` 이면 거절.
- 해시: `argon2-cffi`의 `PasswordHasher()` 기본값(Argon2id. 기본 파라미터 — time_cost 3·memory 64MiB·parallelism 4로 알려짐, **미확인** → 구현 시 실제 값을 이 절에 기록). 평문·가역 암호화 저장 없음.
- `common_passwords.txt` 만들기(구현자 1회 작업, 결과 파일을 커밋):
  1. 출처: SecLists(`github.com/danielmiessler/SecLists`, 라이선스 MIT — **미확인**, 구현 시 LICENSE 확인)의 상위 10만 목록 `Passwords/Common-Credentials/10-million-password-list-top-100000.txt`(경로 **미확인** — 저장소 구조가 바뀌었으면 같은 성격의 "상위 10만" 파일을 고르고 기록).
  2. 커밋 해시를 고정해 내려받는다.
  3. 걸러내기: 앞뒤 줄바꿈만 제거 → `len(line) >= 10` → 소문자 → 중복 제거 → 정렬.
  4. 파일 머리에 `#` 주석 줄: 출처 URL(커밋 해시 포함), 라이선스, 거르기 규칙, 항목 수, 만든 날짜. 로더는 `#`로 시작하는 줄과 빈 줄을 건너뛴다(그 때문에 `#`로 시작하는 비밀번호 몇 개가 빠지는 것은 받아들인다).
  - 항목 수는 **미확인**(수천 개로 예상) — 구현 시 기록.
- 로드: `importlib.resources.files("nadri.core").joinpath("data/common_passwords.txt")`, 프로세스당 1회(`lru_cache`). 패키지 빌드가 `.txt`를 포함하는지 이미지에서 확인(**미확인** — 01 Dockerfile 설치 방식에 따름).

---

## 6. 모듈별 시그니처

주석 규칙([CL]): 모든 함수·클래스에 한국어 docstring(요약 → Args → Returns → Raises/부수효과), 함수 안 단계 주석 `# 1) …`. 아래는 요약 한 줄만 적었다.

### 6.1 `api/errors.py`
```python
class ApiError(Exception):
    """사용자에게 보여 줄 오류. 핸들러가 {"code","message", **extra} JSON과 headers로 바꾼다."""
    def __init__(self, status: int, code: str, message: str, *,
                 extra: dict | None = None, headers: dict[str, str] | None = None) -> None: ...

async def api_error_handler(request: Request, exc: ApiError) -> JSONResponse: ...
def too_many(code: Literal["too_many_attempts", "too_many_requests"], retry_after_s: int) -> ApiError:
    """429 오류를 만든다(Retry-After 헤더, 본문 retry_after_s, too_many_attempts면 {minutes} 채움)."""
# + §4.3 문구 상수 MSG_*
```

### 6.2 `api/auth/service.py`
```python
USERNAME_RE: re.Pattern; EMAIL_RE: re.Pattern
PASSWORD_MIN_LEN = 10; PASSWORD_MAX_LEN = 128
LOGIN_FAILURE_RULE = RateRule(limit=5, window=timedelta(minutes=15), lock=timedelta(minutes=15))
PASSWORD_CHANGE_FAILURE_RULE = LOGIN_FAILURE_RULE
SIGNUP_RULE = RateRule(limit=5, window=timedelta(hours=1))       # 잠금 없음 — 윈도가 끝나면 풀림

def normalize_username(raw: str) -> str: ...
def normalize_email(raw: str) -> str: ...
def validate_username(username: str) -> None:
    """정규화된 아이디가 규칙에 맞지 않으면 ApiError(400, invalid_username)."""
def validate_email(email: str) -> None: ...
def validate_password(password: str) -> None:
    """길이·흔한 비밀번호 규칙. 어긋나면 ApiError(400, weak_password, extra={"reason": ...})."""
@lru_cache
def load_common_passwords() -> frozenset[str]: ...
def constraint_name(exc: IntegrityError) -> str | None:
    """IntegrityError에서 위반한 제약 이름을 꺼낸다(asyncpg 원인 예외의 constraint_name, 없으면 메시지에서 검색)."""

password_hasher: PasswordHasher          # 모듈 전역 — 테스트는 저비용 설정으로 바꿔 끼운다
def hash_password_sync(password: str) -> str: ...
async def hash_password(password: str) -> str:
    """hash_password_sync를 스레드에서 실행한다(anyio.to_thread.run_sync)."""
async def verify_password(password_hash: str | None, password: str) -> bool:
    """해시와 비밀번호가 맞으면 True. password_hash가 None이면 더미 해시로 같은 시간만큼 검사하고 False.
    VerifyMismatchError·InvalidHashError 등은 False로 바꾼다."""

async def signup(db: AsyncSession, *, username: str, email: str, password: str, ip: str, now: datetime) -> User: ...
async def authenticate(db: AsyncSession, *, username: str, password: str, ip: str, now: datetime,
                       sleep: Callable[[float], Awaitable[None]]) -> User:
    """§4.2 login 1~5단계. 성공 시 User, 실패 시 ApiError(401 login_failed / 429 too_many_attempts)."""
async def change_password(db: AsyncSession, *, cu: CurrentUser, current_password: str, new_password: str,
                          now: datetime, sleep: Callable[[float], Awaitable[None]]) -> None: ...
async def create_admin(db: AsyncSession, *, username: str, email: str, password: str, now: datetime) -> User:
    """정규화·검사 후 role=admin, status=active, approved_at=now, approved_by=NULL 로 만든다. 중복이면 ApiError(409)."""
```
- 함수가 커밋까지 한다(`signup`·`authenticate`의 실패 기록·`change_password`·`create_admin`). 라우터는 세션 생성·쿠키만 다룬다.
- `user_out(user: User) -> dict` — `UserOut` 만들기(같은 파일).

### 6.3 `api/auth/sessions.py` (NFR-04)
```python
SESSION_COOKIE = "__Host-session"
IDLE_TIMEOUT = timedelta(hours=2)
ABSOLUTE_TIMEOUT = timedelta(days=7)
TOUCH_INTERVAL = timedelta(minutes=1)      # last_seen_at 갱신 최소 간격(매 요청 쓰기 방지)

def new_token() -> str:            """secrets.token_urlsafe(32)."""
def hash_token(token: str) -> str: """sha256 16진 — auth_sessions.id_hash 에 저장하는 값."""
def is_valid(row: AuthSession, now: datetime) -> bool:
    """now < expires_at 이고 now < last_seen_at + IDLE_TIMEOUT 이면 True."""
async def create_session(db, user_id: int, now: datetime) -> str:
    """auth_sessions 행(created_at=last_seen_at=now, expires_at=now+7일)을 만들고 원본 토큰을 돌려준다. 커밋은 호출자."""
async def load_session(db, token: str, now: datetime) -> AuthSession | None:
    """토큰 해시로 행을 찾는다. 만료면 행을 지우고(커밋) None. 유효하고 TOUCH_INTERVAL 이상 지났으면 last_seen_at=now 커밋."""
async def revoke_session(db, id_hash: str) -> None: ...
async def revoke_all_sessions(db, user_id: int, *, except_id_hash: str | None = None) -> int:
    """그 사용자의 세션을 모두(제외 1개 빼고) 지우고 지운 수를 돌려준다. 06·18이 재사용."""
def set_session_cookie(response: Response, token: str) -> None:
    """__Host-session=<token>; Path=/; Secure; HttpOnly; SameSite=Lax; Max-Age=604800."""
def clear_session_cookie(response: Response) -> None:
    """같은 이름·속성으로 Max-Age=0."""
```
- DB에는 토큰 원본을 저장하지 않는다(해시만). 쿠키에는 원본만.
- 쿠키 `Max-Age`는 절대 만료(7일)와 같게 로그인 시 1번 정한다. 유휴 만료는 서버가 판단.
- `__Host-` 접두어 규칙상 `Domain` 속성을 넣지 않는다.

### 6.4 `api/auth/csrf.py` (NFR-05, ADR-15)
```python
CSRF_COOKIE = "__Host-csrf"
CSRF_HEADER = "X-CSRF-Token"
ANON = "anon"
UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

def binding_for(session_token: str | None) -> str:
    """세션 쿠키가 있으면 hash_token(토큰), 없으면 'anon'. 토큰을 로그인 상태에 묶는 값."""
def issue_token(secret: str, binding: str) -> str:
    """nonce = token_urlsafe(16), sig = base64url(HMAC-SHA256(secret, f"csrf|{binding}|{nonce}")) → f"{nonce}.{sig}"."""
def verify_token(secret: str, binding: str, token: str) -> bool:
    """형식이 맞고 서명이 binding에 대해 유효하면 True(compare_digest)."""
def set_csrf_cookie(response: Response, token: str) -> None:
    """__Host-csrf=<token>; Path=/; Secure; SameSite=Lax; Max-Age=604800 (HttpOnly 아님 — 화면 JS가 읽어 헤더에 넣음)."""

class CsrfMiddleware:
    """/api/ 아래 상태 변경 요청에서 CSRF 쿠키·헤더·서명을 검사하는 순수 ASGI 미들웨어(SSE 응답을 감싸지 않음)."""
    def __init__(self, app: ASGIApp, secret: str) -> None: ...
    async def __call__(self, scope, receive, send) -> None: ...
```
미들웨어 판정 (`scope["type"] == "http"`이고 경로가 `/api/`로 시작하고 메서드가 `UNSAFE_METHODS`일 때만):
1. 쿠키 `__Host-csrf`와 헤더 `X-CSRF-Token`이 둘 다 있고 `compare_digest(header, cookie)`.
2. `verify_token(secret, binding_for(세션 쿠키), header)`.
3. 하나라도 아니면 403 `{"code":"csrf_failed","message":MSG_CSRF_FAILED}` — 내부 앱을 부르지 않는다. 본문은 읽지 않는다.
- 쿠키·헤더 읽기는 `starlette.requests.HTTPConnection(scope)`(본문을 소비하지 않음).
- 로그인하면 바인딩이 바뀌므로 로그인 응답이 새 CSRF 쿠키를 준다. 세션 쿠키만 사라진 경우(브라우저 정리 등) 403이 나는데, 화면(14)이 `GET /api/auth/csrf`로 새로 받아 **1번만** 다시 보낸다(14 spec에 전달).
- 브라우저 연결에 Origin 검사는 추가하지 않는다(요구사항은 SameSite + double-submit).

### 6.5 `api/ratelimit.py` (NFR-02·06, ADR-10)
```python
@dataclass(frozen=True)
class RateRule:
    """고정 윈도 제한 규칙."""
    limit: int                       # 윈도 안에서 허용하는 횟수
    window: timedelta
    lock: timedelta | None = None    # limit에 도달하면 이 시간 동안 잠금(None이면 윈도 끝까지만 거부)

@dataclass(frozen=True)
class RateState:
    """카운터를 올린 직후 상태."""
    count: int; window_start: datetime; locked_until: datetime | None

@dataclass(frozen=True)
class RateDecision:
    """요청 허용 여부."""
    allowed: bool; retry_after_s: int     # 허용이면 0

async def get_lock(db, key: str, now: datetime) -> datetime | None:
    """locked_until > now 이면 그 시각, 아니면 None."""
async def hit(db, key: str, rule: RateRule, now: datetime) -> RateState:
    """카운터를 원자적으로 1 올린다. 윈도가 지났으면 now부터 1로 다시 센다. lock 규칙이고 count >= limit 이면
    locked_until = now + lock. 커밋은 호출자."""
async def allow(db, key: str, rule: RateRule, now: datetime) -> RateDecision:
    """요청 수 제한용: 잠금 중이면 거부, 아니면 hit 후 count <= limit 이면 허용. 커밋은 호출자."""
async def reset(db, key: str) -> None:
    """키 행을 지운다(성공 로그인 등)."""
def retry_after(until: datetime, now: datetime) -> int:
    """until까지 남은 초(올림, 최소 1)."""
def failure_delay_s(count: int) -> float:
    """점진 지연: 1회 0초, 2회 1초, 3회 2초, 4회 이상 4초 = 0 if count<=1 else min(2**(count-2), 4)."""
def key_hash(value: str) -> str:
    """키에 넣을 식별자(아이디·이메일)의 sha256 16진 앞 16자 — rate_limits에 원문을 남기지 않는다."""
def client_ip(request: Request | HTTPConnection) -> str:
    """X-Real-IP 헤더(nginx가 CF-Connecting-IP로 채움), 없으면 request.client.host, 그것도 없으면 'unknown'."""
```
`hit`의 SQL(한 문장, 원자적):
```sql
INSERT INTO rate_limits (key, window_start, count, locked_until) VALUES (:key, :now, 1, NULL)
ON CONFLICT (key) DO UPDATE SET
  window_start = CASE WHEN rate_limits.window_start + :window <= :now THEN :now ELSE rate_limits.window_start END,
  count        = CASE WHEN rate_limits.window_start + :window <= :now THEN 1 ELSE rate_limits.count + 1 END
RETURNING count, window_start, locked_until
```
그 뒤 `rule.lock`이 있고 `count >= rule.limit`이면 `UPDATE rate_limits SET locked_until = :now + :lock WHERE key = :key`.
- **키 형식(정본, 06·11·17이 이어서 씀)**: `login:ip:{ip}`, `login:acct:{key_hash(username)}`, `signup:ip:{ip}`, `pwchange:user:{user_id}`. (06: `reset:ip:{ip}`, `reset:email:{key_hash(email)}`, `reset_confirm:ip:{ip}` / 11: `chat:user:{user_id}` / 17: `stt:user:{user_id}` — 각 spec에서 확정.)
- IP를 믿는 근거: api는 호스트 포트가 없고 nginx만 닿는다(ADR-10, 02 §9). 개발 접속(`127.0.0.1:8080`)은 모두 같은 IP로 보인다(HITL에서 잠기면 §9 해제 명령).
- 잠금은 계정 단위 서비스 거부(남이 내 아이디로 5번 틀려 15분 잠금)를 허용한다 — NFR-02가 정한 동작, 데모 규모라 수용.

### 6.6 `api/deps.py`
```python
@dataclass(frozen=True)
class CurrentUser:
    """로그인한 사용자와 이번 요청의 세션 해시."""
    user: User
    session_hash: str

async def get_db(request: Request) -> AsyncIterator[AsyncSession]:
    """앱 상태의 세션 팩토리로 요청당 AsyncSession 1개를 연다."""
def get_now() -> datetime:
    """현재 UTC 시각(tz-aware). 테스트에서 dependency_overrides로 바꾼다."""
def get_sleep() -> Callable[[float], Awaitable[None]]:
    """asyncio.sleep. 테스트에서 기록용 가짜로 바꾼다."""
def get_secret(request: Request) -> str:
    """앱 상태에 둔 SESSION_SECRET 원문."""
async def current_user(request: Request, db=Depends(get_db), now=Depends(get_now)) -> CurrentUser:
    """세션 쿠키 → load_session → users 조회. 없음·만료 → 401 unauthenticated.
    status가 rejected·disabled면 그 세션을 지우고 401."""
async def require_active(cu: CurrentUser = Depends(current_user)) -> CurrentUser:
    """status=active가 아니면(pending) 403 pending_approval (FR-04·06)."""
async def require_admin(cu: CurrentUser = Depends(current_user)) -> CurrentUser:
    """role=admin이고 status=active가 아니면 403 forbidden (FR-80). 05에서는 테스트로만 확인, 사용은 18부터."""
```

### 6.7 `api/main.py` 변경
`create_app(settings)` 처리 순서에 추가:
1. `SESSION_SECRET`이 없거나 32자 미만이면 `RuntimeError("SESSION_SECRET이 없거나 32자 미만입니다. .env를 확인하세요")`(§3). 값은 `secret`으로 꺼내 둔다.
2. `engine = create_engine(settings)`, `app.state.sf = session_factory(engine)`, `app.state.secret = secret` — **`create_app` 안에서 바로** 만든다(httpx `ASGITransport`는 lifespan을 실행하지 않음, 연결은 첫 쿼리 때). 종료 시 `engine.dispose()`는 lifespan shutdown에서.
3. `app.add_exception_handler(ApiError, api_error_handler)`.
4. `app.add_middleware(CsrfMiddleware, secret=secret)`.
5. `app.include_router(auth_router)`.
- 02의 `GET /api/health`·런타임 지연 생성은 그대로.

### 6.8 02 채팅 엔드포인트 연결
```python
@router.post("/api/chat/sessions/{session_id}/messages")
async def post_message(session_id: str, body: ChatRequest, request: Request,
                       cu: CurrentUser = Depends(require_active)) -> StreamingResponse:
```
- 인증·활성 검사는 **SSE 시작 전**(의존성)이라 401/403은 일반 JSON 응답이다. `cu`는 05에서는 쓰지 않는다(09가 세션 소유 확인·저장에 사용).
- 02 테스트 수정: 엔드포인트를 부르는 02 테스트는 `app.dependency_overrides[require_active] = lambda: CurrentUser(가짜 active User, "h")`로 인증을 대신하고, CSRF는 테스트 헬퍼 `anon_csrf(client, secret)`(익명 토큰을 쿠키·헤더에 넣음)로 통과시킨다. 02 테스트의 기대값은 바꾸지 않는다.
- 02 HITL의 `curl` 명령은 이제 로그인 쿠키·CSRF 헤더가 필요하다 — 05 test.md HITL의 셸 함수로 대체.

---

## 7. 관리자 CLI — `nadri create-admin` (FR-80)

```
nadri create-admin --username <아이디> --email <이메일> [--password-stdin]
```
- 실행 위치: api 컨테이너 — `docker compose run --rm api nadri create-admin --username admin --email you@example.com`.
- 비밀번호: 기본은 `getpass`로 두 번 입력(화면·셸 기록에 남지 않음), 다르면 종료 코드 2. `--password-stdin`이면 표준입력 첫 줄(끝 줄바꿈만 제거) — 자동화·테스트용.

```python
def cmd_create_admin(args: argparse.Namespace, *, stdin: TextIO = sys.stdin,
                     getpass_fn: Callable[[str], str] = getpass.getpass) -> int:
    """관리자 계정을 만들고 종료 코드를 돌려준다(0 성공, 1 중복 등 실행 실패, 2 입력 오류)."""
```
처리 순서: 1) 비밀번호 받기 2) `create_admin`(정규화·검사 포함) — `ApiError` 400 → 메시지 출력 후 2, 409 → 메시지 출력 후 1 3) 성공 출력 `관리자 계정을 만들었어요: id=<id>, 아이디=<username>` → 0.
- 관리자가 이미 있어도 추가로 만들 수 있다(제한 없음). 비밀번호 규칙은 일반 사용자와 같다.

---

## 8. Compose · 터널 (G4 Q1)

| 서비스 | 변경 |
|---|---|
| `api` | `environment`에 `DB_USER=nadri_app`, `DB_PASSWORD=${APP_DB_PASSWORD}`, `SESSION_SECRET=${SESSION_SECRET}` 추가. `depends_on`: `postgres(service_healthy)`, `ingest(service_completed_successfully)`(테이블이 생긴 뒤 기동), 02의 `tour-tools` 유지 |
| `cloudflared` | `profiles: [tunnel]` **제거** → 기본 기동, `restart: unless-stopped`. 그 외(토큰 환경변수 `TUNNEL_TOKEN`) 02 그대로 |

- 이제 인증 없는 공개 경로는 `/api/health`·`/api/auth/csrf`·`signup`·`login`(+06의 재설정)뿐이고, 모두 요청 제한이 걸린다. 채팅(OpenAI 비용)은 active 사용자만.
- 개발 중 잠금 해제(HITL용): `docker compose exec postgres psql -U postgres -d nadri -c "delete from rate_limits where key like 'login:%'"`.

---

## 9. 엣지케이스

| 상황 | 동작 |
|---|---|
| 아이디 대소문자만 다르게 가입 (`Admin` vs `admin`) | 같은 아이디 → 409 `username_taken` |
| 로그인 아이디 앞뒤 공백·대문자 | 정규화 후 비교 → 성공 |
| 없는 아이디로 5번 실패 | 그 아이디 키도 잠김(계정 존재 노출 없음) |
| 같은 IP에서 서로 다른 아이디로 5번 실패 | IP 키 잠김 → 그 IP의 모든 로그인 429(15분) |
| 잠금 중 올바른 비밀번호 | 429(비밀번호 검사 안 함) |
| 성공 로그인 후 같은 IP의 실패 카운터 | 유지(계정 카운터만 지움) |
| 4번 실패 → 15분 경과 → 1번 실패 | 윈도가 지나 카운트 1부터 다시 |
| `pending` 로그인 | 200, `status:"pending"`. 채팅 403 `pending_approval`, `me` 200 |
| `rejected`·`disabled` + 맞는 비밀번호 | 401 `login_failed`, 실패로 셈 |
| 로그인 중 관리자가 `disabled`로 바꿈(18) | 다음 요청에서 `current_user`가 세션 삭제 → 401 |
| 유휴 2시간 초과 / 로그인 후 7일 초과 | 401, 세션 행 삭제 |
| 1분 안 연속 요청 | `last_seen_at` 쓰기 없음 |
| 로그인할 때 이미 세션 쿠키가 있음 | 기존 세션 행 삭제 후 새 세션(재발급) |
| 다른 사용자의 세션 쿠키를 가진 채 로그인 | 그 세션도 삭제됨(쿠키를 가진 쪽이 그 세션의 주인이라 문제없음) |
| CSRF 헤더 없음·쿠키 없음·값 불일치·서명 위조·다른 세션에 묶인 토큰 | 403 `csrf_failed`, 라우터 미실행 |
| 로그인 전 받은 익명 CSRF 토큰으로 로그인 후 요청 | 403(로그인 응답이 새 토큰을 줬으므로 화면은 새 쿠키를 씀) |
| `GET` 요청에 CSRF 없음 | 통과 |
| 비밀번호 변경: 현재 비밀번호 5번 틀림 | `pwchange:user:<id>` 잠금 → 429 15분 |
| 비밀번호 변경 성공 | 다른 세션 전부 삭제, 현재 세션 유지 |
| 새 비밀번호 = 현재 비밀번호 | 허용(요구사항 없음) |
| 비밀번호 9자 / 129자 / 흔한 목록(대소문자 무시) | 400 `weak_password` + reason |
| 가입 시 이메일 중복 | 409 `email_taken` (확인 질문 Q3) |
| 같은 IP 가입 6번째(1시간 안) | 429 `too_many_requests` |
| 동시에 같은 아이디로 가입 2건 | 하나는 201, 하나는 DB UNIQUE로 409 |
| `SESSION_SECRET` 없음·짧음 | api 기동 실패(명확한 메시지) |
| `X-Real-IP` 없음(테스트·직접 접근) | `request.client.host` |
| 없는 `/api/` 경로에 POST·PUT·DELETE | 미들웨어가 라우팅보다 먼저 돌아 CSRF가 없으면 403, 있으면 404 |

---

## 10. 상위 문서와의 차이 (구현 판단, 아키텍처 범위 안)

| # | 내용 | 근거·처리 |
|---|---|---|
| 1 | NFR-02 "5회 실패"의 **집계 기간을 15분**으로 정함, 점진 지연 0·1·2·4초 | 문서에 기간·지연 수치 없음 — 확인 질문 Q2 |
| 2 | 잠금 상태는 `login_failed`와 다른 429 `too_many_attempts`로 알린다 | 없는 아이디도 같은 잠금이 생겨 계정 존재가 드러나지 않음(NFR-03 유지) — 확인 질문 Q8 |
| 3 | `GET /api/auth/csrf` 추가([A] §6.1 표에 없음) | 로그인 전 화면이 처음 CSRF 토큰을 받을 방법 — 확인 질문 Q5 |
| 4 | CSRF를 로그인 전 요청(가입·로그인·재설정)에도 적용 | NFR-05 "상태 변경 요청" 전부 — 확인 질문 Q5 |
| 5 | 가입에 IP별 1시간 5회 제한 추가(NFR-06 목록에 가입은 없음) | 터널 상시 공개 후 가입 스팸 방지 — 확인 질문 Q4 |
| 6 | 비밀번호 변경 시 현재 세션은 유지(재발급 안 함) | FR-03은 "다른 세션" 폐기만 요구 — 확인 질문 Q6 |
| 7 | 오류 본문 형식 `{"code","message"}`과 `api/errors.py` 신설 | [A] §3.1 `{code:"quota_exceeded"}` 형식과 같은 계열, 06·09·11·18이 공유 |
| 8 | 비밀번호 상한 128자 | 문서에 상한 없음(NIST는 최소 64자 허용 요구) — 확인 질문 Q9 |
| 9 | `rate_limits` 키에 아이디·이메일 원문 대신 해시 앞 16자 | NFR-34(개인정보 최소). ERD 예시 `login:ip:1.2.3.4`의 IP는 그대로 |
| 10 | 02 테스트·HITL 명령이 인증 때문에 바뀜 | §6.8 |

---

## 11. 가정 판정 — A17 (localhost에서 `__Host-` 쿠키)

| 항목 | 내용 |
|---|---|
| 가정 | Windows 브라우저가 `http://localhost:8080`(WSL 전달)에서도 `Secure`·`__Host-` 쿠키를 저장·전송한다(브라우저가 localhost를 안전한 출처로 취급 — Chrome·Firefox는 그렇다고 알려짐, **미확인**) |
| 확인 방법 | test.md HITL H-4: 터널 주소와 `localhost:8080` 각각에서 DevTools 콘솔로 csrf → login → me, Application 탭에서 쿠키 속성 확인 |
| 통과 | 두 주소 모두 `me` 200, `__Host-session`이 HttpOnly·Secure·SameSite=Lax·Path=/ 로 저장 |
| 실패 시 | localhost만 실패 → 브라우저 확인은 **터널 주소로만** 한다([A] §12 대안, 코드 변경 없음, 결과 기록). 터널에서도 실패 → 멈추고 사용자에게(NFR-04·22 영향) |
| 결과 | (구현 시 기록 + `PROGRESS.md` 결정 로그) |

---

## 12. 완료 기준 (DoD)

1. test.md 단위·DB 테스트 전부 통과(`-m "not integration"`), 02 테스트도 수정 후 전부 통과.
2. §4.1 엔드포인트가 §4.2 순서·§4.3 코드/문구대로 동작(테스트로 확인).
3. CSRF 없는 상태 변경 요청은 경로와 무관하게 403 `csrf_failed`.
4. 5회 실패 → 15분 잠금(계정·IP 각각), 점진 지연 적용(가짜 sleep 기록으로 확인).
5. 비밀번호 변경 → 같은 사용자의 다른 세션 401, 현재 세션 유지.
6. `pending`은 로그인·`me` 가능, 채팅 403. `rejected`·`disabled`는 `login_failed`.
7. `nadri create-admin`으로 active 관리자 생성, 그 계정으로 로그인 → `role:"admin"`.
8. `docker compose up -d` 시 `cloudflared`가 프로필 없이 뜨고, **터널 주소에서 로그인 쿠키 동작**(HITL H-4), A17 판정 기록.
9. `common_passwords.txt` 머리에 출처·커밋·라이선스·거르기 규칙·항목 수가 있고 §5.3 규칙으로 만들어졌다.
10. 로그·DB 어디에도 비밀번호·세션 토큰 원본·CSRF 토큰이 남지 않는다(테스트 U-LOG).
11. 모든 함수·클래스에 한국어 docstring, 함수 안 단계 주석([CL]).
12. 커밋 `feat/05-auth-core`, `[Feat] …` + 작업 목록 + `Author:` 줄, AI 공동작성 표기 없음(NFR-73). `dev` 병합은 G5 후. `PROGRESS.md` 갱신.

---

## 13. 확인 질문

| # | 질문 | 추천안 | 대안 |
|---|---|---|---|
| Q1 | 아이디 규칙이 문서에 없다 | **영문·숫자·밑줄 4~20자, 소문자로 저장**(대소문자만 다른 아이디는 같은 아이디) | 한글 허용 / 이메일을 아이디로 사용(FR-04는 아이디·이메일을 따로 받음) |
| Q2 | "5회 실패"를 어느 기간 안에서 셀지, 점진 지연 크기 | **15분 안 5회 → 15분 잠금, 지연 0·1·2·4초**(2번째 실패부터) | 기간 1시간 / 지연 없음(잠금만) |
| Q3 | 가입 시 이미 쓰인 이메일을 알려 줄까(이메일이 가입돼 있는지 드러남) | **알려 준다**(409 + "재설정을 이용하세요"). 가입은 관리자 승인이고 사용자 1~5명이라 열거 위험이 낮고, 안 알려 주면 본인이 영원히 승인 대기로 착각 | 가입 성공과 같은 응답을 주고 행은 만들지 않음(열거 방지, 본인 혼란) |
| Q4 | 가입 신청 요청 제한(NFR-06 목록에 없음) | **IP별 1시간 5회** — 터널 상시 공개 후 가입 스팸으로 관리자 목록이 차는 것을 막음 | 제한 없음 |
| Q5 | 로그인 전 요청(가입·로그인·재설정)에도 CSRF를 요구하고, 이를 위해 `GET /api/auth/csrf`를 추가할까 | **요구 + 추가**(모든 상태 변경 요청에 같은 규칙 — 예외 경로가 없어 실수가 적음, 로그인 CSRF도 막음) | 로그인 전 요청은 CSRF 면제(SameSite만), 엔드포인트 추가 없음 |
| Q6 | 비밀번호 변경 시 지금 쓰는 세션은? | **유지**(다른 세션만 폐기 — FR-03 문구 그대로) | 현재 세션도 새로 발급(쿠키 교체) |
| Q7 | 흔한 비밀번호 목록 파일·비교 방식 | **SecLists "상위 10만" 중 10자 이상, 소문자로 비교** (G4 Q7 결정의 구체화) | 대소문자 그대로 비교(`Password123!`과 `password123!`을 다르게 봄) |
| Q8 | 잠금 중일 때 문구를 로그인 실패와 다르게 보여 줄까 | **다르게**(429 "시도가 너무 많아요. N분 뒤…") — 없는 아이디도 똑같이 잠겨 계정 존재가 드러나지 않음 | 잠금도 `login_failed`와 같은 문구(사용자는 왜 안 되는지 모름) |
| Q9 | 비밀번호 최대 길이 | **128자** | 상한 없음(아주 긴 입력으로 해시 비용 공격 가능) / 64자 |
