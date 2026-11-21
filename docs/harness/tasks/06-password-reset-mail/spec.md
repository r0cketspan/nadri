# 06-password-reset-mail — 이메일 인증코드 비밀번호 재설정 (spec)

> 하네스 Phase 4 산출물 (spec-writer, 작성 2026-11-21). 상태: **초안 — 사용자 검토 대기**. 브랜치 `feat/06-password-reset-mail`, 의존 작업 05-auth-core.
> 입력: [PL]=program_list.md(G4 승인본) §2 표·§3 "06-password-reset-mail" · [A]=architecture.md §2.1(`mail`)·§3.5·§4(Gmail SMTP 실패 시 "로그, 응답 동일")·§6.1·§9 비밀값 표 · [R]=requirements.md FR-05·07, NFR-03·06·34, O2(10분·5회) · [S]=stack-options.md S7(Gmail SMTP + 앱 비밀번호) · **04 spec(`password_reset_codes`·`users`·`auth_sessions`·`rate_limits` 컬럼)** · **05 spec(비밀번호 규칙·세션 폐기·요청 제한·CSRF·오류 형식 — 재사용)**.
> **미확인** = 문서·공식 자료로 확인하지 못해 구현 중 확인해야 하는 사실.

---

## 1. 작업 목표

이메일로 6자리 인증코드를 보내 비밀번호를 다시 정하는 API 두 개와 Gmail SMTP 발송 모듈을 만든다 [PL §3].

- 끝나면: `request {email}` → (활성 사용자면) 6자리 코드를 해시로 저장하고 메일을 백그라운드로 보냄 → 가입 여부와 상관없이 같은 응답. `confirm {email, code, new_password}` → 코드가 맞고 10분 안·5회 안이면 비밀번호를 바꾸고 **그 사용자의 세션을 전부 끊고** 코드를 소모. 실패 이유는 하나의 문구로 통일.
- 추적: FR-05·07, NFR-03(재설정 문구 통일)·06(재설정 요청 제한)·34(이메일은 인증코드 발송에만), O2.

### 1.1 넣지 않는 것
| 하지 않는 것 | 담당 작업 |
|---|---|
| 재설정 화면(이메일 입력 → 코드·새 비밀번호 입력, 규칙 미리 표시) | 14 |
| 만료·사용된 코드 일괄 정리 | 21 (`password_reset_codes` 만료분 삭제 — [A] §3.3 9) |
| 승인 결과 메일 등 다른 메일 | 범위 밖([A] §13) |
| HTML 메일·메일 템플릿 엔진 | 범위 밖(텍스트 메일 한 종류) |
| 발송 실패 재시도·큐 | 범위 밖(실패는 로그만, 사용자가 다시 요청) |

---

## 2. 생성·수정 파일

| 파일 | 신규/수정 | 역할 |
|---|---|---|
| `nadri/api/mail.py` | 신규 | `MailMessage`·`Mailer` 인터페이스, Gmail `SmtpMailer`(SMTP over SSL, 스레드 실행), 재설정 메일 문안, 백그라운드 발송(실패는 로그만), `get_mailer` 의존성 (§6) |
| `nadri/api/auth/reset.py` | 신규 | `POST /api/auth/password-reset/request`·`/confirm` 라우터와 처리 함수, 코드 생성·해시, 재설정 요청 제한 규칙 (§4·§5) |
| `nadri/api/main.py` | 수정(02·05) | `app.state.mailer = build_mailer(settings)`, reset 라우터 등록 |
| `nadri/core/config.py` | 수정 | SMTP 설정 6개 (§3) |
| `.env.example` | 수정 | `SMTP_USER`·`SMTP_APP_PASSWORD`·`MAIL_FROM` 이름 추가 [PL] |
| `compose.yaml` | 수정 | api `environment`에 `SMTP_USER`·`SMTP_APP_PASSWORD`·`MAIL_FROM` 주입([A] §9 표) |
| `backend/tests/...` | 신규 | test.md |

> [PL] 파일 목록에 없는 것: `main.py`·`config.py`·`compose.yaml` 수정(설정 주입·라우터 등록에 필요).
> 05에서 그대로 가져다 쓰는 것(이름 고정): `service.normalize_email`·`validate_email`·`validate_password`·`hash_password`·`MSG_*`, `sessions.revoke_all_sessions`·`clear_session_cookie`, `csrf.issue_token`·`set_csrf_cookie`·`ANON`, `ratelimit.RateRule`·`allow`·`reset`·`key_hash`·`client_ip`·`retry_after`, `errors.ApiError`·`too_many`, `deps.get_db`·`get_now`·`get_secret`, 04 ORM `User`·`PasswordResetCode`.

---

## 3. 설정 · 환경변수

| 이름 | 타입·기본값 | 용도 |
|---|---|---|
| `SMTP_HOST` | `str = "smtp.gmail.com"` | |
| `SMTP_PORT` | `int = 465` | SMTP over SSL(확인 질문 Q2) |
| `SMTP_USER` | `str \| None = None` | Gmail 주소(로그인 아이디) |
| `SMTP_APP_PASSWORD` | `SecretStr \| None = None` | Gmail 앱 비밀번호 16자(**공백 없이** 입력 — Google 화면은 4자씩 띄워 보여 줌) |
| `MAIL_FROM` | `str \| None = None` | 보낸 사람 표시(예: `nadri <me@gmail.com>`). 없으면 `SMTP_USER`. Gmail은 인증한 계정이 아닌 주소를 From으로 쓰면 바꿔 버릴 수 있다(**미확인**) — 같은 주소에 이름만 붙이는 것을 권장 |
| `SMTP_TIMEOUT_S` | `float = 15.0` | 접속·전송 제한 시간 |

- `SMTP_USER`·`SMTP_APP_PASSWORD` 둘 중 하나라도 없으면 **api는 정상 기동**하고 기동 시 경고 로그 1줄("메일 설정이 없어 인증코드를 보내지 않습니다"), 재설정 요청은 코드를 저장하되 발송하지 않는다(응답은 같음) — Gmail 정보를 넣기 전에도 05·06 개발·테스트가 되도록(확인 질문 Q5).
- `.env.example` 추가 줄:
```
# Gmail 발신 — 2단계 인증을 켠 Google 계정의 "앱 비밀번호"(16자, 공백 없이)
SMTP_USER=
SMTP_APP_PASSWORD=
# 보낸 사람 표시(선택) — 예: nadri <me@gmail.com>
MAIL_FROM=
```

---

## 4. API

05의 CSRF 미들웨어가 그대로 적용된다(두 엔드포인트 모두 `POST` → `X-CSRF-Token` 필요). 로그인은 필요 없다.

### 4.1 엔드포인트
| 메서드·경로 | 요청 본문 | 성공 | 실패 |
|---|---|---|---|
| `POST /api/auth/password-reset/request` | `{"email": str(≤320)}` | **202** `{"message": MSG_RESET_SENT}` — 가입 여부·상태와 무관하게 항상 같음 | 400 `invalid_email` / 429 `too_many_requests`(+`Retry-After`) / 403 `csrf_failed` / 422 |
| `POST /api/auth/password-reset/confirm` | `{"email": str(≤320), "code": str(≤20), "new_password": str(≤1000)}` | 200 `{"message": MSG_RESET_DONE}` + 세션 쿠키 삭제 + 익명 CSRF 쿠키 | 400 `reset_failed` / 400 `weak_password`(+`reason`) / 400 `invalid_email` / 429 `too_many_requests` / 403 `csrf_failed` / 422 |

### 4.2 사용자에게 보이는 문구 (통일)
| code / 상황 | HTTP | 상수 (`errors.py`에 추가) | 문구 |
|---|---|---|---|
| 요청 접수(항상) | 202 | `MSG_RESET_SENT` | 입력한 이메일로 가입된 계정이 있으면 인증코드를 보냈어요. 10분 안에 입력해 주세요. |
| 재설정 완료 | 200 | `MSG_RESET_DONE` | 비밀번호를 바꿨어요. 새 비밀번호로 다시 로그인해 주세요. |
| `reset_failed` | 400 | `MSG_RESET_FAILED` | 인증코드가 맞지 않거나 만료됐어요. 확인 후 다시 입력하거나 인증코드를 새로 요청해 주세요. |
| `weak_password` | 400 | (05 그대로) | 05 §4.3 세 문구 |
| `invalid_email` | 400 | (05 그대로) | 이메일 형식이 올바르지 않아요. |
| `too_many_requests` | 429 | (05 그대로) | 요청이 너무 많아요. 잠시 후 다시 시도해 주세요. |

- `reset_failed` 하나로 묶는 경우: 없는 이메일, 활성 아닌 사용자, 발급된 코드 없음, 만료, 5회 초과, 코드 불일치, 코드 형식 오류(NFR-03 — 어떤 이유인지 알려 주지 않는다).

### 4.3 요청 제한 규칙 (NFR-06, 확인 질문 Q1)
| 규칙 상수 (`reset.py`) | 키 (05 §6.5 형식) | 값 |
|---|---|---|
| `RESET_REQUEST_IP_RULE` | `reset:ip:{ip}` | 1시간 10회 |
| `RESET_REQUEST_EMAIL_RULE` | `reset:email:{key_hash(email)}` | 1시간 3회(가입 안 된 이메일에도 똑같이 적용 → 존재 노출 없음) |
| `RESET_CONFIRM_IP_RULE` | `reset_confirm:ip:{ip}` | 15분 10회 |
- 모두 잠금 없는 `RateRule`(윈도가 끝나면 풀림), 05의 `allow()` 사용, 카운터는 **판정 직후 커밋**(뒤 단계 실패와 상관없이 셈).
- 코드 하나당 5회(O2)는 `password_reset_codes.attempts`로 따로 센다.

---

## 5. 처리 순서 · 시그니처 (`api/auth/reset.py`)

```python
CODE_TTL = timedelta(minutes=10)          # O2
CODE_MAX_ATTEMPTS = 5                     # O2
CODE_RE = re.compile(r"^\d{6}$")
RESET_REQUEST_IP_RULE = RateRule(limit=10, window=timedelta(hours=1))
RESET_REQUEST_EMAIL_RULE = RateRule(limit=3, window=timedelta(hours=1))
RESET_CONFIRM_IP_RULE = RateRule(limit=10, window=timedelta(minutes=15))

class ResetRequestIn(BaseModel): email: str = Field(max_length=320)
class ResetConfirmIn(BaseModel):
    email: str = Field(max_length=320); code: str = Field(max_length=20); new_password: str = Field(max_length=1000)

def generate_code() -> str:
    """secrets.randbelow로 000000~999999 중 하나를 6자리 문자열로 만든다."""
def normalize_code(raw: str) -> str:
    """입력 코드의 모든 공백을 지운다(메일에서 복사할 때 섞이는 공백 허용)."""
def hash_code(secret: str, user_id: int, code: str) -> str:
    """HMAC-SHA256(secret, f"reset|{user_id}|{code}") 16진. DB에는 이 값만 저장(확인 질문 Q6)."""
def code_matches(secret: str, user_id: int, code: str, code_hash: str) -> bool:
    """형식(6자리 숫자)이 맞고 hash_code가 같으면 True(compare_digest)."""

async def request_reset(db: AsyncSession, *, email: str, ip: str, now: datetime,
                        secret: str) -> tuple[User, str] | None:
    """요청 제한·코드 발급까지 처리한다. 활성 사용자면 (사용자, 원본 코드), 아니면 None.
    Raises: ApiError(400 invalid_email / 429 too_many_requests)."""
async def confirm_reset(db: AsyncSession, *, email: str, code: str, new_password: str, ip: str,
                        now: datetime, secret: str) -> User:
    """코드를 검증하고 비밀번호를 바꾼 뒤 세션 전부 폐기·코드 소모. Raises: ApiError(400·429)."""

@router.post("/api/auth/password-reset/request", status_code=202)
async def password_reset_request(body: ResetRequestIn, request: Request, background: BackgroundTasks,
                                 db=Depends(get_db), now=Depends(get_now), secret=Depends(get_secret),
                                 mailer: Mailer | None = Depends(get_mailer)) -> dict: ...
@router.post("/api/auth/password-reset/confirm")
async def password_reset_confirm(body: ResetConfirmIn, request: Request, response: Response,
                                 db=Depends(get_db), now=Depends(get_now), secret=Depends(get_secret)) -> dict: ...
```

### 5.1 `request_reset` 처리 순서 (FR-05, NFR-03·06)
1. `email = normalize_email(body.email)` → `validate_email` 실패면 400 `invalid_email`(형식 오류는 가입 여부와 무관해 정보 노출 없음).
2. `allow(reset:ip:{ip})` → `allow(reset:email:{key_hash(email)})` → 커밋. 둘 중 하나라도 거부면 429 `too_many_requests`(`Retry-After` = 둘 중 큰 값).
3. `user = SELECT users WHERE email = :email`. 없거나 `status != 'active'`면 → `None`(코드 없음, 메일 없음).
4. 활성이면: `DELETE password_reset_codes WHERE user_id = :id`(이전 코드 무효화 — 마지막 코드만 유효) → `code = generate_code()` → `INSERT (user_id, code_hash=hash_code(...), expires_at=now+10분, attempts=0)` → 커밋 → `(user, code)`.
- 라우터: 결과가 있으면 `background.add_task(send_reset_mail, mailer, build_reset_mail(user.email, code), user_id=user.id)` → 202 `MSG_RESET_SENT`. **원본 코드는 응답·로그·DB 어디에도 남기지 않는다**(메일 본문에만).
- 발송은 응답 뒤 백그라운드라, 메일 서버가 느리거나 실패해도 응답 시간·내용이 같다([A] §4 "로그, 응답 동일").

### 5.2 `confirm_reset` 처리 순서 (FR-05, O2)
1. `allow(reset_confirm:ip:{ip})` → 커밋 → 거부면 429.
2. `email` 정규화·형식 검사(400 `invalid_email`), `validate_password(new_password)`(400 `weak_password`) — **코드 시도 횟수를 쓰기 전에** 검사(규칙 위반으로 시도가 줄지 않게).
3. `user = SELECT users WHERE email = :email`. 없거나 `status != 'active'` → 400 `reset_failed`.
4. `row = SELECT password_reset_codes WHERE user_id = :id AND consumed_at IS NULL ORDER BY id DESC LIMIT 1 FOR UPDATE`(동시 확인 경합 방지). 없음 → `reset_failed`.
5. `now >= row.expires_at` 또는 `row.attempts >= 5` → `reset_failed`(시도 수 안 올림).
6. `code_matches(secret, user.id, normalize_code(code), row.code_hash)`가 아니면 → `row.attempts += 1` → 커밋 → `reset_failed`.
7. 성공: `user.password_hash = await hash_password(new_password)` → `row.consumed_at = now` → `revoke_all_sessions(db, user.id)`(예외 없이 전부 — FR-05 "기존 세션 모두 폐기") → `reset(db, f"login:acct:{key_hash(user.username)}")`(로그인 잠금 풀기 — 확인 질문 Q4) → 커밋.
- 라우터: 200 `MSG_RESET_DONE`, `clear_session_cookie(response)`, `set_csrf_cookie(response, issue_token(secret, ANON))`(세션이 모두 사라졌으므로 익명 토큰으로).

---

## 6. 메일 (`api/mail.py`) — Gmail SMTP (S7, FR-07)

```python
@dataclass(frozen=True)
class MailMessage:
    """보낼 메일 한 통(텍스트 본문)."""
    to: str
    subject: str
    body: str

class Mailer(Protocol):
    """메일 발송 인터페이스(테스트에서 가짜로 바꾼다)."""
    async def send(self, msg: MailMessage) -> None: ...

class SmtpMailer:
    """Gmail SMTP(SSL 465)로 보낸다. smtplib(표준 라이브러리)을 스레드에서 실행해 이벤트 루프를 막지 않는다."""
    def __init__(self, *, host: str, port: int, user: str, app_password: str, sender: str, timeout_s: float,
                 smtp_factory: Callable[..., smtplib.SMTP_SSL] = smtplib.SMTP_SSL) -> None: ...
    def _send_sync(self, msg: MailMessage) -> None:
        """1) EmailMessage(From=sender, To, Subject, text/plain UTF-8) 2) smtp_factory(host, port, timeout=…,
        context=ssl.create_default_context()) 3) login(user, app_password) 4) send_message 5) with 문으로 종료."""
    async def send(self, msg: MailMessage) -> None: ...   # anyio.to_thread.run_sync(self._send_sync, msg)

def build_mailer(settings: Settings) -> Mailer | None:
    """SMTP_USER·SMTP_APP_PASSWORD가 둘 다 있으면 SmtpMailer, 아니면 None(+경고 로그 1회)."""
def build_reset_mail(to: str, code: str) -> MailMessage:
    """비밀번호 재설정 인증코드 메일 문안을 만든다(§6.1)."""
async def send_reset_mail(mailer: Mailer | None, msg: MailMessage, *, user_id: int) -> None:
    """백그라운드 작업 본체. mailer가 None이면 경고 로그만. 실패는 잡아서 경고 로그(user_id·예외 클래스 이름만),
    다시 올리지 않는다. 성공하면 INFO 로그(user_id만)."""
def get_mailer(request: Request) -> Mailer | None:
    """app.state.mailer 를 돌려주는 FastAPI 의존성(테스트는 dependency_overrides로 가짜 주입)."""
```
- 로그에 **수신 주소·코드·메일 본문을 넣지 않는다**(NFR-34). 남기는 것: `event=reset_mail`, `user_id`, `result=sent|failed|skipped`, 실패면 예외 클래스 이름.
- 재시도 없음, 큐 없음. 실패하면 사용자가 다시 요청한다(코드는 다시 발급).

### 6.1 메일 문안
- 제목: `[nadri] 비밀번호 재설정 인증코드`
- 본문(텍스트):
```
nadri 비밀번호 재설정 인증코드입니다.

인증코드: 123456

10분 안에 입력해 주세요. 5번 틀리면 새 코드를 요청해야 해요.
직접 요청하지 않았다면 이 메일은 무시해 주세요. 비밀번호는 바뀌지 않아요.
```
- 링크를 넣지 않는다(피싱처럼 보이지 않게, 터널 주소가 바뀌어도 그대로 쓰도록).

---

## 7. 엣지케이스

| 상황 | 동작 |
|---|---|
| 가입 안 된 이메일 | 202 같은 문구, 코드·메일 없음, rate_limits 이메일 키는 생김 |
| `pending`·`rejected`·`disabled` 사용자 이메일 | 202 같은 문구, 코드·메일 없음 (확인 질문 Q3) |
| 이메일 대소문자·공백 다름 | 정규화 후 같은 사용자 |
| 코드 요청 2번 | 첫 코드 삭제 → 첫 코드로 확인하면 `reset_failed`, 두 번째 코드만 유효 |
| 같은 이메일 1시간 4번째 요청 | 429(가입 여부와 무관) |
| 틀린 코드 5번 → 맞는 코드 | `reset_failed`(시도 소진) — 새로 요청해야 함 |
| 10분 0초 정각에 확인 | 만료(`now >= expires_at`) |
| 코드에 공백 `"123 456"` | 공백 제거 후 비교 → 맞으면 성공 |
| 코드 `"12345a"`·`"1234567"` | `reset_failed`, 코드가 있으면 시도 1회로 셈 |
| 약한 새 비밀번호 + 맞는 코드 | 400 `weak_password`, 시도 수 그대로, 코드 그대로 유효 |
| 이미 사용한 코드 재사용 | `consumed_at`이 있어 후보에서 빠짐 → `reset_failed` |
| 동시에 같은 코드로 확인 2건 | `FOR UPDATE`로 하나만 성공, 다른 하나는 소모된 코드라 `reset_failed` |
| 요청 후 관리자가 비활성화, 그다음 확인 | `reset_failed` |
| 확인 성공 시 로그인 중인 기기들 | 전부 401(세션 행 삭제) |
| 확인 성공 시 로그인 잠금 상태 | 계정 키 해제(IP 키는 유지) |
| SMTP 미설정 | 코드 저장·202, 경고 로그, 메일 없음 |
| SMTP 인증 실패(앱 비밀번호 틀림)·타임아웃 | 202 그대로, 경고 로그(`SMTPAuthenticationError` 등) |
| CSRF 헤더 없음 | 403 `csrf_failed`(05 미들웨어) |

---

## 8. 상위 문서와의 차이 (구현 판단, 아키텍처 범위 안)

| # | 내용 | 근거·처리 |
|---|---|---|
| 1 | 요청 제한에 걸리면 429로 알린다([A] §3.5 "항상 같은 응답"은 **가입 여부와 무관하게 같은 응답**으로 해석) | 제한은 없는 이메일에도 똑같이 걸려 존재가 드러나지 않음 |
| 2 | 코드 발송 대상은 `active`만 | FR-05 문구엔 없지만 [PL] 06·[A] §3.5 "활성 사용자면" — 확인 질문 Q3 |
| 3 | 확인 성공 시 로그인 계정 잠금(`login:acct`)을 푼다 | 잠긴 사용자가 재설정으로 바로 복구 — 확인 질문 Q4 |
| 4 | 코드 해시 = `SESSION_SECRET` 키의 HMAC-SHA256 | 6자리 코드는 일반 해시면 DB 유출 시 바로 역산됨 — 확인 질문 Q6 |
| 5 | SMTP 미설정이어도 api 기동 | 확인 질문 Q5 |
| 6 | 요청 제한 수치(1시간 IP 10·이메일 3, 확인 15분 IP 10) | 문서에 수치 없음 — 확인 질문 Q1 |
| 7 | 확인 성공 응답이 세션 쿠키를 지우고 익명 CSRF 쿠키를 준다 | 세션이 전부 폐기되므로 화면 상태와 맞춤 |

---

## 9. 가정 판정
[PL] 06 "가정: 없음". 기록만 할 것:

| 항목 | 상태 | 기록 방법 |
|---|---|---|
| Gmail 일일 발송 한도([S] S7) | **미확인** — 데모 규모(하루 수 통)라 문제 없을 것으로 봄 | HITL 결과에 "확인 못 함" 또는 Google 도움말 수치 기록 |
| Gmail이 `MAIL_FROM` 표시 이름을 유지하는지 | **미확인** | HITL H-2에서 받은 메일의 보낸 사람 표시 기록 |
| 메일 도착 시간·스팸함 분류 | 측정 | HITL H-2 |

---

## 10. 완료 기준 (DoD)

1. test.md 단위·DB·API 테스트 전부 통과(SMTP는 가짜) — 만료(시계 주입)·5회·문구 통일·세션 폐기·코드 소모·요청 제한.
2. 가입 여부·상태와 무관하게 `request` 응답이 **바이트 단위로 같다**.
3. 원본 코드·수신 주소가 로그·DB에 남지 않는다(테스트).
4. HITL: 사용자가 `.env`에 Gmail 정보를 넣은 뒤 **실제 메일 1회 수신** → 그 코드로 재설정 → 새 비밀번호 로그인 성공, 기존 로그인 401.
5. 모든 함수·클래스에 한국어 docstring, 함수 안 단계 주석([CL]).
6. 커밋 `feat/06-password-reset-mail`, `[Feat] …` + 작업 목록 + `Author:` 줄, AI 공동작성 표기 없음(NFR-73). `dev` 병합은 G5 후. `PROGRESS.md` 갱신.

---

## 11. 확인 질문

| # | 질문 | 추천안 | 대안 |
|---|---|---|---|
| Q1 | 재설정 요청 제한 수치(문서에 없음) | **요청: IP별 1시간 10회 + 이메일별 1시간 3회 / 확인: IP별 15분 10회** (코드당 5회는 별도) | 더 느슨하게(이메일별 1시간 5회) / 이메일별만 |
| Q2 | Gmail 접속 방식 | **SSL 465(`SMTP_SSL`)** — 처음부터 암호화, 코드가 단순 | STARTTLS 587 |
| Q3 | 승인 대기(`pending`) 사용자도 재설정할 수 있게 할까 | **활성 사용자만**(FR·[A] 문구 그대로. 승인 대기 중엔 어차피 채팅 불가) | `pending` 포함(승인 전에 비밀번호를 잊은 경우 구제) |
| Q4 | 재설정 성공 시 로그인 잠금(아이디별)을 풀까 | **푼다**(코드를 메일로 받은 본인임이 확인됨). IP 잠금은 유지 | 풀지 않음(15분 기다림) |
| Q5 | Gmail 정보가 `.env`에 없을 때 | **api는 정상 기동, 경고 로그, 메일만 안 보냄**(응답 동일) | api 기동 실패(설정 누락을 바로 알 수 있지만 메일과 무관한 개발도 막힘) |
| Q6 | 인증코드 저장 방식 | **`SESSION_SECRET` 키 HMAC-SHA256**(DB만 유출돼선 6자리 코드를 못 맞춤, 추가 키 없음) | 일반 SHA-256(유출 시 100만 번 계산으로 역산) / Argon2(느리고 과함) / 별도 비밀키 추가 |
