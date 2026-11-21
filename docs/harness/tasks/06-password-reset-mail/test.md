# 06-password-reset-mail — 테스트 설계 (test)

> spec.md와 짝. 절 번호 §n은 spec.md 기준. 작성 2026-11-21. 상태: 초안 — 사용자 검토 대기.
> 두 방향: ① pytest(결정적 — SMTP는 가짜, DB는 04 테스트 DB 컨테이너, 시계 주입) ② HITL(사용자가 `.env`에 Gmail 앱 비밀번호를 넣고 실제 메일 1회 수신).

---

## 0. 실행 방법 · 공통 준비

```bash
cd ~/code/myAgent/backend
uv run pytest -m "not integration" -q
```
- 05 test.md §0의 픽스처·헬퍼(`clock`, `sleeps`, `fast_hasher`, `app`, `client`/`client2`, `make_user`, `get_csrf`, `post`, `login`, `set_cookie_attrs`)를 그대로 쓴다.
- 추가 대역 (`tests/fakes.py`에 추가)

| 대역 | 대체 대상 | 동작 |
|---|---|---|
| `FakeMailer` | `Mailer` | `send(msg)`가 `sent` 리스트에 쌓음. 옵션 `raise_exc`(예: `smtplib.SMTPAuthenticationError(535, b"x")`) |
| `FakeSMTP` | `smtplib.SMTP_SSL` (팩토리) | 생성 인자(host·port·timeout·context)를 기록, `login`·`send_message`·`__enter__/__exit__` 호출 기록. 옵션으로 `login`에서 예외 |
| `code_from(mailer)` | — | 마지막 메일 본문에서 `인증코드: (\d{6})`를 뽑음 |

- `app` 픽스처에서 `app.dependency_overrides[get_mailer] = lambda: fake_mailer`.
- 백그라운드 작업: httpx `ASGITransport`는 앱 호출이 끝날 때까지(응답 뒤 백그라운드 작업 포함) 기다린다고 보고, 요청 직후 `fake_mailer.sent`를 검사한다(**미확인** — 첫 실행에서 확인, 다르면 테스트에서 `await asyncio.sleep(0)` 반복으로 대기).

---

## ① pytest

### 1. 코드·메일 순수 함수 (DB 없음) — `tests/api/auth/test_reset_pure.py`, `tests/api/test_mail.py`

| ID | 대상 | 입력 | 기대 |
|---|---|---|---|
| U-CODE-1 | `generate_code` | 1,000회 | 모두 `^\d{6}$`, `"000123"`처럼 앞자리 0도 6자리 유지(`secrets.randbelow`를 고정값 123으로 바꿔 확인) |
| U-CODE-2 | `normalize_code` | `" 123 456 "`, `"123\t456"` | `"123456"` |
| U-CODE-3 | `hash_code` | 같은 (secret, user, code) 2회 / user만 다름 / secret만 다름 | 같음 / 다름 / 다름, 결과에 코드 원문 없음, 64자 16진 |
| U-CODE-4 | `code_matches` | 맞는 코드 / 틀린 코드 / `"12345a"` / `"1234567"` / `""` | True / False / False / False / False |
| U-MAIL-1 | `build_reset_mail("a@x.com", "012345")` | — | `to=="a@x.com"`, 제목 `[nadri] 비밀번호 재설정 인증코드`, 본문에 `인증코드: 012345`·`10분`·`5번`, 본문에 `http` 없음(링크 없음) |
| U-MAIL-2 | `SmtpMailer._send_sync` + `FakeSMTP` | host `smtp.gmail.com`, port 465, user `me@gmail.com`, 앱 비밀번호 `abcdabcdabcdabcd`, sender `nadri <me@gmail.com>` | 팩토리 인자 `("smtp.gmail.com", 465)`, `timeout=15.0`, `context`가 `ssl.SSLContext`; `login("me@gmail.com","abcdabcdabcdabcd")` 1회; 보낸 메시지 `From`·`To`·`Subject` 맞음, `Content-Type: text/plain; charset="utf-8"`, 한글 제목이 인코딩되어 들어감 |
| U-MAIL-3 | `SmtpMailer.send` | `FakeSMTP` | `_send_sync`가 다른 스레드에서 실행됨(`threading.get_ident()` 비교) |
| U-MAIL-4 | `build_mailer` | 둘 다 있음 / `SMTP_USER`만 / 둘 다 없음 | `SmtpMailer` / None + 경고 로그 / None + 경고 로그. 경고에 비밀값 없음 |
| U-MAIL-5 | `build_mailer` | `MAIL_FROM` 없음 | sender == `SMTP_USER` |
| U-MAIL-6 | `send_reset_mail(None, msg, user_id=7)` | — | 예외 없음, 로그 `result=skipped`, `user_id=7` |
| U-MAIL-7 | `send_reset_mail(FakeMailer(raise_exc=SMTPAuthenticationError))` | — | 예외 없음, 경고 로그에 `SMTPAuthenticationError`·`user_id`, 로그에 수신 주소·코드·본문 없음 |
| U-MAIL-8 | `send_reset_mail` 성공 | — | INFO 로그 `result=sent`, 주소·코드 없음 |

### 2. API (마커 `db`) — `tests/api/auth/test_reset_api.py`
준비: `make_user(..., username="alice", email="alice@x.com", status="active")`, 비밀번호 `P0 = "old-pass-123"`. 요청은 모두 `post()` 헬퍼(CSRF 포함), 기본 `X-Real-IP: 203.0.113.1`.

#### 2.1 request — 같은 응답 (NFR-03)
| ID | 상황 | 기대 |
|---|---|---|
| A-RQ-1 | active `alice@x.com` | 202 `{"message": MSG_RESET_SENT}`, `fake_mailer.sent` 1통(to=`alice@x.com`), DB `password_reset_codes` 1행: `expires_at == now+10분`, `attempts==0`, `consumed_at` NULL, `code_hash == hash_code(secret, id, code_from(mailer))` |
| A-RQ-2 | 가입 안 된 이메일 / `pending` / `rejected` / `disabled` 사용자 이메일 | 네 경우 모두 A-RQ-1과 **상태·헤더(쿠키 제외)·본문 바이트 동일**, 메일 0통, 코드 행 0 |
| A-RQ-3 | `" ALICE@X.COM "` | alice에게 발송 |
| A-RQ-4 | 형식 오류 `"alice"` | 400 `invalid_email`, 메일 0 |
| A-RQ-5 | 두 번 요청 | 코드 행 1개(마지막 것), 메일 2통, 첫 코드 ≠ 둘째 코드(고정 난수로 확인) |
| A-RQ-6 | 응답 본문·헤더 | 원본 코드 문자열 없음 |
| A-RQ-7 | CSRF 없음 | 403 `csrf_failed`, 메일 0 |
| A-RQ-8 | `fake_mailer`가 예외 | 202 그대로, 코드 행은 남음 |
| A-RQ-9 | `get_mailer` → None(SMTP 미설정) | 202 그대로, 코드 행 생성, 경고 로그 |

#### 2.2 request — 요청 제한 (NFR-06)
| ID | 상황 | 기대 |
|---|---|---|
| A-RL-1 | 같은 이메일 4번(1시간 안) | 1~3번째 202, 4번째 429 `too_many_requests` + `Retry-After` |
| A-RL-2 | 가입 안 된 이메일로 같은 절차 | A-RL-1과 같은 결과(존재 노출 없음) |
| A-RL-3 | 같은 IP·서로 다른 이메일 11번 | 11번째 429 |
| A-RL-4 | A-RL-1 후 `clock.advance(hours=1)` | 다시 202 |
| A-RL-5 | 키 확인 | `reset:ip:203.0.113.1`, `reset:email:<16자 해시>` — 이메일 원문 없음 |

#### 2.3 confirm (FR-05, O2)
기본 절차: request → `c = code_from(fake_mailer)`. 새 비밀번호 `P1 = "new-pass-456"`.

| ID | 상황 | 기대 |
|---|---|---|
| A-CF-1 | 맞는 코드, `P1` | 200 `MSG_RESET_DONE`, `__Host-session` `Max-Age=0`, 새 익명 `__Host-csrf`, DB `consumed_at == now`, `P0` 로그인 401·`P1` 로그인 200 |
| A-CF-2 | `client`·`client2`가 alice로 로그인한 상태에서 A-CF-1(세 번째 client로) | `client`·`client2` `/me` 401, alice의 `auth_sessions` 0행. 다른 사용자 세션은 그대로 |
| A-CF-3 | 틀린 코드 | 400 `{"code":"reset_failed","message":MSG_RESET_FAILED}`, `attempts==1` |
| A-CF-4 | 틀린 코드 5번 → 맞는 코드 | 6번째도 `reset_failed`, `attempts==5`(6번째는 안 올림), 비밀번호 그대로 |
| A-CF-5 | 틀린 코드 4번 → 맞는 코드 | 200 |
| A-CF-6 | `clock.advance(minutes=9, seconds=59)` → 맞는 코드 | 200 |
| A-CF-7 | `clock.advance(minutes=10)` → 맞는 코드 | `reset_failed`, `attempts` 그대로 |
| A-CF-8 | 성공 후 같은 코드로 다시 | `reset_failed` |
| A-CF-9 | 요청 2번 → **첫** 코드로 확인 | `reset_failed`. 둘째 코드로 200 |
| A-CF-10 | 코드 `" 12 34 56 "` 형태(맞는 코드에 공백) | 200 |
| A-CF-11 | 코드 `"abcdef"` | `reset_failed`, `attempts==1` |
| A-CF-12 | 새 비밀번호 9자 + 맞는 코드 | 400 `weak_password`(`reason=too_short`), `attempts==0`, 이어서 `P1`로 200 |
| A-CF-13 | 실패 문구 통일: 없는 이메일 / `pending` 사용자(코드 없음) / 코드 없음(active, 요청 안 함) / 만료 / 5회 초과 / 불일치 / 형식 오류 | 일곱 경우 **상태·본문 바이트 동일** |
| A-CF-14 | 요청 후 DB에서 `disabled`로 바꾸고 맞는 코드 | `reset_failed` |
| A-CF-15 | 같은 IP 확인 11번(15분 안) | 11번째 429. `X-Real-IP`를 바꾸면 계속 가능 |
| A-CF-16 | 로그인 잠금(`login:acct` 5회 실패로 잠김) 상태에서 A-CF-1 | `login:acct:<해시>` 행 삭제, `P1` 로그인 즉시 200. `login:ip:` 행은 남음 |
| A-CF-17 | 동시에 맞는 코드로 확인 2건(`asyncio.gather`, 서로 다른 client) | 200 하나, `reset_failed` 하나, `consumed_at` 1번만 설정 |
| A-CF-18 | CSRF 없음 | 403 `csrf_failed` |

#### 2.4 비밀값이 남지 않음
| ID | 절차 | 기대 |
|---|---|---|
| U-LOG-R1 | A-RQ-1·A-CF-3·A-CF-1을 한 테스트에서 실행하며 `caplog`(전체, DEBUG) | 원본 코드(6자리), 수신 이메일 주소, 새 비밀번호가 로그에 없음 |
| U-LOG-R2 | 같은 흐름 후 `password_reset_codes`·`rate_limits` 전 컬럼 | 원본 코드·이메일 원문 없음 |

### 통과 기준
- 위 전부 통과. 05 테스트 전체도 다시 통과(회귀).

---

## ② HITL (사용자가 직접 실행)

WSL2 Ubuntu `~/code/myAgent`. 05 test.md H-3의 셸 함수(`csrf`, `cookie`, `login`, `B`)를 다시 붙여 넣고 시작한다.

### H-0 Gmail 앱 비밀번호 준비 (사용자 작업)
1. 발신용 Google 계정에서 **2단계 인증**을 켠다(Google 계정 → 보안).
2. Google 계정 → 보안 → "앱 비밀번호"에서 새 앱 비밀번호를 만든다(이름 예: `nadri`). 16자가 4자씩 띄어 보인다(메뉴 위치는 Google 화면 개편으로 다를 수 있음 — **미확인**).
3. `.env`에 직접 입력(커밋 금지):
```
SMTP_USER=<발신 Gmail 주소>
SMTP_APP_PASSWORD=<16자, 공백 없이>
MAIL_FROM=nadri <발신 Gmail 주소>
```
4. api만 다시 만들기: `docker compose up -d --force-recreate api` → `docker compose logs api | grep -i 메일` 에 "메일 설정이 없어" 경고가 **없어야** 함.

### H-1 받을 계정 준비
- 05 HITL에서 만든 `tester1`(active)의 이메일이 **내가 받을 수 있는 주소**인지 확인. 아니면:
  `docker compose exec postgres psql -U postgres -d nadri -c "update users set email='<내 수신 주소 소문자>' where username='tester1'"`

### H-2 실제 메일 1회 수신 (이 작업의 핵심)
```bash
t=$(csrf); date +%T
curl -s -X POST $B/api/auth/password-reset/request -H 'Content-Type: application/json' \
  -H "X-CSRF-Token: $t" -H "Cookie: __Host-csrf=$t" -d '{"email":"<내 수신 주소>"}'
docker compose logs --since 2m api | grep reset_mail
```
확인:
- [ ] 응답 202, 문구 `입력한 이메일로 가입된 계정이 있으면…`
- [ ] api 로그 `event=reset_mail … result=sent`(주소·코드 없음)
- [ ] 메일 도착(받은편지함, 없으면 스팸함) — 도착까지 걸린 시간 기록
- [ ] 제목 `[nadri] 비밀번호 재설정 인증코드`, 본문 6자리 코드·"10분"·링크 없음, 한글 깨짐 없음
- [ ] 보낸 사람 표시가 `nadri`로 보이는지(spec §9 미확인 항목)

### H-3 코드로 재설정 → 세션 끊김
1. (선택) 브라우저(터널 주소)에서 05 H-4 방식으로 `tester1` 로그인해 둔다.
2. 틀린 코드 1번:
```bash
t=$(csrf); curl -s -X POST $B/api/auth/password-reset/confirm -H 'Content-Type: application/json' \
  -H "X-CSRF-Token: $t" -H "Cookie: __Host-csrf=$t" \
  -d '{"email":"<내 수신 주소>","code":"000000","new_password":"<새 10자 이상>"}'
```
   → 400 `reset_failed` 문구.
3. 메일의 코드로 같은 명령 → 200 `비밀번호를 바꿨어요…`.
4. 브라우저 콘솔 `await (await fetch('/api/auth/me')).status` → **401**.
5. `login tester1 '<새 비밀번호>'` → 200, 옛 비밀번호 → 401.

### H-4 가입 안 된 이메일
```bash
t=$(csrf); curl -s -X POST $B/api/auth/password-reset/request -H 'Content-Type: application/json' \
  -H "X-CSRF-Token: $t" -H "Cookie: __Host-csrf=$t" -d '{"email":"nobody-<아무 문자>@example.com"}'
```
- 기대: H-2와 **같은 응답**, 메일 없음, 로그에 `result=sent` 없음.

### H-5 (선택) 만료 확인
1. H-2대로 새 코드 요청.
2. `docker compose exec postgres psql -U postgres -d nadri -c "update password_reset_codes set expires_at = now() - interval '1 second'"`
3. 받은 코드로 확인 → `reset_failed`.

### H-6 비밀값 확인
```bash
docker compose logs api | grep -n -e '<받은 6자리 코드>' -e '<내 수신 주소>' || echo "없음"
git status --short .env   # 출력 없음이어야 함(.gitignore 대상)
```

### HITL 결과 보고 (구현자가 사용자에게)
| 항목 | 결과 |
|---|---|
| H-0 앱 비밀번호 설정·경고 로그 없음 | |
| H-2 메일 도착(받은편지함/스팸)·걸린 시간·보낸 사람 표시 | |
| H-3 틀린 코드 문구·재설정 성공·브라우저 401·새 비밀번호 로그인 | |
| H-4 같은 응답·메일 없음 | |
| H-5 만료(선택) | |
| H-6 로그에 코드·주소 없음 | |
| Gmail 일일 발송 한도(확인 못 했으면 "미확인") | |
