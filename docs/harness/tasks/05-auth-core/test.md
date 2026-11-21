# 05-auth-core — 테스트 설계 (test)

> spec.md와 짝. 절 번호 §n은 spec.md 기준. 작성 2026-11-21. 상태: 초안 — 사용자 검토 대기.
> 두 방향: ① pytest(결정적 — 외부 API·실모델 없음. DB는 04의 **테스트 DB 컨테이너**, 시계·대기는 주입) ② HITL(터널 주소와 `localhost`에서 브라우저 쿠키 확인 등 사용자가 직접).

---

## 0. 실행 방법 · 공통 준비

```bash
cd ~/code/myAgent/backend
uv sync --no-group reranker
uv run pytest -m "not integration" -q                 # 단위 + DB + API (Docker 필요)
uv run pytest -m "not integration and not db" -q      # DB 없는 단위만
```
- 프레임워크: `pytest` + `pytest-asyncio`(`asyncio_mode=auto`), API는 `httpx.AsyncClient(transport=ASGITransport(app=app), base_url="https://testserver")`.
  - **`https://`로 둔다** — httpx 쿠키 저장소는 `Secure` 쿠키를 http 주소로 보내지 않는다.
  - `ASGITransport`는 lifespan을 실행하지 않는다 → spec §6.7대로 엔진은 `create_app` 안에서 만든다.
- DB 픽스처: 04 spec §7의 `pg_container`·`db_engine`·`db_sf`(테스트마다 앱 테이블 TRUNCATE). DB를 쓰는 파일은 `pytestmark = pytest.mark.db`.
- 02의 대역(`tests/fakes.py`)·네트워크 차단 픽스처를 그대로 쓴다(`db` 마크 테스트의 Docker 소켓·`127.0.0.1` 허용은 04에서 이미 수정).

**05 픽스처·헬퍼** (`tests/api/conftest.py`, `tests/helpers/auth.py`)
| 이름 | 역할 |
|---|---|
| `FakeClock` / `clock` | `now` 속성(기본 `2026-11-21T00:00:00+00:00`), `advance(**timedelta_kwargs)`. `app.dependency_overrides[get_now] = lambda: clock.now` |
| `sleeps` | 기록용 가짜 sleep — 호출된 초를 리스트에 쌓고 바로 반환. `get_sleep` 덮어쓰기 |
| `fast_hasher` (autouse) | `service.password_hasher`를 `PasswordHasher(time_cost=1, memory_cost=1024, parallelism=1)`로 바꿈(테스트 속도). 해시 형식(`$argon2id$`)은 같음 |
| `app` | 테스트 설정(`SESSION_SECRET="t"*32`, DB = 테스트 컨테이너)으로 `create_app`, 위 덮어쓰기 적용, 02 채팅 런타임은 02 대역으로 덮어씀 |
| `client`, `client2` | 같은 `app`에 붙은 독립 쿠키 저장소 2개(두 기기 흉내) |
| `make_user(db_sf, username, password, *, status="active", role="user", email=None)` | DB에 직접 사용자 생성(해시 포함) |
| `get_csrf(client)` | `GET /api/auth/csrf` → 토큰 반환(쿠키는 client에 저장됨) |
| `post(client, url, json)` | 현재 `__Host-csrf` 쿠키 값을 `X-CSRF-Token` 헤더에 넣어 POST |
| `login(client, username, password)` | `get_csrf` → `post(/login)` 응답 반환 |
| `anon_csrf(client, secret)` | 서버 호출 없이 익명 토큰을 만들어 쿠키 설정 + 헤더 dict 반환(02 테스트용) |
| `set_cookie_attrs(resp, name)` | `Set-Cookie` 헤더를 이름별로 파싱해 속성 dict(`path`, `secure`, `httponly`, `samesite`, `max-age`) 반환 |
| `verify_spy` | `service.verify_password`를 감싸 호출 수·인자(None 여부) 기록 |

---

## ① pytest

### 1. 입력 규칙·비밀번호 (DB 없음) — `tests/api/auth/test_policy.py`

| ID | 대상 | 입력 | 기대 |
|---|---|---|---|
| U-NORM-1 | `normalize_username` | `"  Alice_01 "` | `"alice_01"` |
| U-NORM-2 | `validate_username` | `"abcd"`, `"a"*20`, `"user_1"` | 통과 |
| U-NORM-3 | 〃 | `"abc"`, `"a"*21`, `"한글아이디"`, `"bad-name"`, `"a b c d"`, `""` | `ApiError(400, invalid_username)` |
| U-NORM-4 | `normalize_email`·`validate_email` | `" A@Example.COM "` | `"a@example.com"`, 통과 |
| U-NORM-5 | `validate_email` | `"a@b"`, `"a b@c.d"`, `"@c.d"`, 255자 | `invalid_email` |
| U-PW-1 | `validate_password` | 10자 `"xk3!pQ9#zr"` / 128자 | 통과 |
| U-PW-2 | 〃 | 9자 | `weak_password`, `extra["reason"]=="too_short"`, 메시지 = `MSG_PASSWORD_TOO_SHORT` |
| U-PW-3 | 〃 | 129자 | `reason=="too_long"` |
| U-PW-4 | 〃 | 목록 파일의 첫 항목을 대문자로 바꾼 값 | `reason=="common"` (대소문자 무시) |
| U-PW-5 | 〃 | 한글 10자 `"가나다라마바사아자차"` | 통과(문자 수 기준) |
| U-PW-6 | 〃 | 앞뒤 공백 포함 `" xk3!pQ9#z "` | 통과, 공백 유지(해시 입력이 원문 그대로인지 U-HASH-3에서) |
| U-CPL-1 | `load_common_passwords()` | 실제 파일 | 비어 있지 않음, 모든 항목 `len >= 10`, 모두 소문자, `#` 주석 줄 미포함 |
| U-CPL-2 | 파일 형식 | 실제 파일 텍스트 | 머리 주석에 `source:`·`license:`·`filter:`·`count:` 줄 존재, `count:` 값 == 실제 항목 수, 항목 줄이 정렬·중복 없음 |
| U-CPL-3 | 캐시 | 2회 호출 | 같은 객체(`is`) |
| U-HASH-1 | `hash_password` → `verify_password` | 맞는 비밀번호 / 틀린 것 | True / False, 해시가 `$argon2id$`로 시작, 같은 비밀번호 두 번 해시 → 다른 문자열(솔트) |
| U-HASH-2 | `verify_password(None, "x")` | — | False, 내부적으로 해시 검사 1회 수행(더미) |
| U-HASH-3 | `verify_password(hash(" a…"), "a…")` | 공백 차이 | False |
| U-HASH-4 | `verify_password("not-a-hash", "x")` | 깨진 해시 | False(예외 없음) |

### 2. 세션·CSRF·요청 제한 순수 함수 — `tests/api/auth/test_tokens.py`, `tests/api/test_ratelimit_pure.py`

| ID | 대상 | 입력 | 기대 |
|---|---|---|---|
| U-SES-1 | `new_token` | 100회 | 길이 ≥ 43, 모두 다름 |
| U-SES-2 | `hash_token("abc")` | — | sha256 16진 64자, 결정적 |
| U-SES-3 | `is_valid` 표 | `created=0`, `last_seen=0`, `expires=7d`: now=1h59m / 2h / 2h+1s, last_seen=6d23h·now=7d-1s / 7d | True / False / False, True / False (경계: `now < …` 엄격) |
| U-SES-4 | `set_session_cookie` | 토큰 `T` | 헤더 `__Host-session=T; Max-Age=604800; Path=/; SameSite=lax; Secure; HttpOnly` 속성 모두(순서 무관), `Domain` 없음 |
| U-SES-5 | `clear_session_cookie` | — | 같은 이름, `Max-Age=0`, `Path=/`, `Secure` |
| U-CSRF-1 | `issue_token`·`verify_token` | 같은 secret·binding | True, 형식 `nonce.sig` |
| U-CSRF-2 | `verify_token` | binding 다름(`anon` vs 세션 해시) | False |
| U-CSRF-3 | 〃 | secret 다름 / 서명 1글자 변조 / `"abc"` / `""` / 점 2개 | 모두 False(예외 없음) |
| U-CSRF-4 | `binding_for` | `None` / `"tok"` | `"anon"` / `hash_token("tok")` |
| U-CSRF-5 | `set_csrf_cookie` | — | `__Host-csrf`, `Path=/`, `Secure`, `SameSite=lax`, `Max-Age=604800`, **HttpOnly 없음** |
| U-RL-1 | `failure_delay_s` | 0,1,2,3,4,5,9 | 0,0,1,2,4,4,4 |
| U-RL-2 | `key_hash("alice")` | — | 16자 16진, 결정적, `"alice"` 미포함 |
| U-RL-3 | `retry_after` | until=now+0.2s / +900s / 과거 | 1 / 900 / 1 |
| U-RL-4 | `client_ip` | `X-Real-IP: 203.0.113.5` / 헤더 없음(client `10.0.0.2`) / 둘 다 없음 | `203.0.113.5` / `10.0.0.2` / `unknown` |
| U-ERR-1 | `api_error_handler` | `too_many("too_many_attempts", 61)` | 429, `Retry-After: 61`, 본문 `{"code","message","retry_after_s":61}`, 메시지에 "2분" |
| U-ERR-2 | 〃 | `ApiError(400,"weak_password",…, extra={"reason":"common"})` | 본문에 `reason` |

### 3. 요청 제한 DB 동작 (마커 `db`) — `tests/api/test_ratelimit_db.py`
규칙 `R = RateRule(limit=5, window=15분, lock=15분)`, `S = RateRule(limit=3, window=1시간)`, 시각은 고정 값을 넘긴다.

| ID | 절차 | 기대 |
|---|---|---|
| D-RL-1 | `hit(k, R, t0)` × 4 | count 1→4, `locked_until` None, `window_start == t0` |
| D-RL-2 | 이어서 5번째 | count 5, `locked_until == t0+15분`(5번째 시각 기준), `get_lock(k, t0+1분)` == 그 시각 |
| D-RL-3 | `get_lock(k, 잠금 해제 시각)` | None(경계: `>` 엄격) |
| D-RL-4 | 4회 → `t0+16분`에 `hit` | count 1, `window_start == t0+16분` |
| D-RL-5 | `allow(k2, S, t)` × 4 | allowed T,T,T,F, 4번째 `retry_after_s == ceil(window_start+1h - t)` |
| D-RL-6 | `allow` 윈도 지난 뒤 | allowed T, count 1 |
| D-RL-7 | `allow`(잠금 규칙)에서 잠금 중 | allowed F, 카운터 증가 없음 |
| D-RL-8 | `reset(k)` | 행 없음, 없는 키 reset도 오류 없음 |
| D-RL-9 | 동시성: 세션 10개로 같은 키 `hit` 동시 실행(`asyncio.gather`, 각자 커밋) | 최종 count 10(원자적 upsert) |

### 4. 세션 저장소 (마커 `db`) — `tests/api/auth/test_sessions_db.py`
| ID | 절차 | 기대 |
|---|---|---|
| D-SES-1 | `create_session(user, t0)` | 원본 토큰 반환, DB `id_hash == hash_token(토큰)`, 토큰 원본은 DB 어디에도 없음(`auth_sessions` 전 컬럼 검색), `expires_at == t0+7일` |
| D-SES-2 | `load_session(토큰, t0+30초)` | 행 반환, `last_seen_at` 그대로 |
| D-SES-3 | `load_session(토큰, t0+61초)` | `last_seen_at == t0+61초` 커밋됨 |
| D-SES-4 | `load_session(토큰, t0+2시간+1초)` (중간 갱신 없음) | None, 행 삭제됨 |
| D-SES-5 | 없는 토큰 | None |
| D-SES-6 | 사용자 세션 3개 → `revoke_all_sessions(user, except_id_hash=두번째)` | 반환 2, 두 번째만 남음. 다른 사용자 세션 영향 없음 |

### 5. API (마커 `db`) — `tests/api/auth/test_auth_api.py`

#### 5.1 CSRF
| ID | 요청 | 기대 |
|---|---|---|
| A-CSRF-1 | `GET /api/auth/csrf` | 200, 본문 `csrf_token` == 쿠키 값, 쿠키 속성 U-CSRF-5와 같음 |
| A-CSRF-2 | `POST /api/auth/signup` 헤더 없이(쿠키는 있음) | 403 `{"code":"csrf_failed","message":MSG_CSRF_FAILED}`, `users` 0행 |
| A-CSRF-3 | 헤더 ≠ 쿠키 | 403 |
| A-CSRF-4 | 헤더=쿠키=`"nonce.위조서명"` | 403 |
| A-CSRF-5 | 로그인 전 익명 토큰을 로그인 후에도 계속 사용 → `POST /logout` | 403. 로그인 응답의 새 쿠키로 보내면 204 |
| A-CSRF-6 | 로그인한 active 사용자, 채팅 POST에 CSRF 없음 | 403 `csrf_failed`(SSE 아님, 그래프 대역 호출 0회) |
| A-CSRF-7 | `GET /api/auth/me`·`GET /api/health` CSRF 없음 | 200 |
| A-CSRF-8 | `PUT`·`DELETE`·`PATCH` `/api/anything` CSRF 없음 | 403(경로가 없어도 미들웨어가 먼저) |

#### 5.2 가입 (FR-04)
| ID | 요청 | 기대 |
|---|---|---|
| A-SU-1 | 정상 `{"username":"Alice_01","email":"A@x.com","password":"xk3!pQ9#zr"}` | 201 `{"status":"pending","message":MSG_SIGNUP_OK}`, DB `username='alice_01'`, `email='a@x.com'`, `status='pending'`, `role='user'`, 해시 `$argon2id$…`, 응답에 `__Host-session` 쿠키 **없음** |
| A-SU-2 | 형식 오류 아이디·이메일·약한 비밀번호 각각 | 400, `code`·`message`(·`reason`) = spec §4.3 표 |
| A-SU-3 | 아이디·이메일·비밀번호 모두 틀림 | 400 `invalid_username`(검사 순서 — 첫 실패만) |
| A-SU-4 | 같은 아이디(대소문자만 다름) 재가입 | 409 `username_taken` |
| A-SU-5 | 다른 아이디·같은 이메일 | 409 `email_taken` |
| A-SU-6 | 같은 `X-Real-IP`로 6번 가입 시도(1시간 안, 일부는 400으로 실패) | 1~5번째는 각각의 결과, 6번째 429 `too_many_requests` + `Retry-After`. 다른 IP는 허용. `clock.advance(hours=1)` 뒤 허용 |
| A-SU-7 | 필드 누락·`password` 1001자 | 422 |
| A-SU-8 | 동시 가입 2건 같은 아이디(`asyncio.gather`) | 201 하나, 409 하나 |

#### 5.3 로그인 (FR-01, NFR-02·03)
| ID | 상황 | 기대 |
|---|---|---|
| A-LI-1 | active 사용자 정상 로그인 | 200 `UserOut`(`password_hash` 등 다른 필드 없음), `__Host-session` 속성 U-SES-4와 같음, 새 `__Host-csrf`(로그인 전 값과 다름), DB 세션 1행 `id_hash == sha256(쿠키)` |
| A-LI-2 | 틀린 비밀번호 / 없는 아이디 / `rejected` + 맞는 비밀번호 / `disabled` + 맞는 비밀번호 / 형식이 틀린 아이디 | 다섯 경우 **상태·본문 바이트 단위 동일**(401 `login_failed`), `verify_spy` 각 1회(없는 아이디·형식 오류는 `None` 인자) |
| A-LI-3 | 아이디 `"  ALICE_01 "` | 200 |
| A-LI-4 | 같은 계정 4번 실패 | `sleeps == [1, 2, 4]`(1번째 실패는 지연 0이라 sleep 호출 없음) |
| A-LI-5 | 5번 실패 → 6번째 맞는 비밀번호 | 6번째 429 `too_many_attempts`, `Retry-After: 900`, 메시지 "15분", `verify_spy` 호출 없음 |
| A-LI-6 | A-LI-5 뒤 `clock.advance(minutes=15, seconds=1)` → 맞는 비밀번호 | 200, `login:acct:…` 행 없음, `login:ip:…` 행은 남음 |
| A-LI-7 | 같은 IP에서 서로 다른 없는 아이디 5개로 실패 → 실제 사용자 로그인 | 429. `X-Real-IP`를 바꾸면 200 |
| A-LI-8 | 없는 아이디 `ghost`로 5번 실패 → 6번째 | 429(있는 계정과 같은 동작 — 열거 불가) |
| A-LI-9 | 4번 실패 → `advance(minutes=16)` → 1번 실패 → 6번째 시도 | 6번째도 401(잠기지 않음, 새 윈도 카운트 1~2) |
| A-LI-10 | 같은 client로 두 번 로그인 | 첫 세션 행 삭제, 세션 1행만, 쿠키 값 바뀜 |
| A-LI-11 | `pending` 사용자 로그인 | 200 `status:"pending"` |
| A-LI-12 | rate_limits 키 확인 | `login:ip:<IP 그대로>`, `login:acct:<16자 해시>` — 아이디 원문 없음 |

#### 5.4 세션 수명·현재 사용자 (NFR-04, FR-06)
| ID | 상황 | 기대 |
|---|---|---|
| A-ME-1 | 쿠키 없음 `GET /me` | 401 `unauthenticated` |
| A-ME-2 | 로그인 → `advance(hours=1, minutes=59)` → `/me` → 다시 `advance(hours=1, minutes=59)` → `/me` | 둘 다 200(유휴 시간이 갱신됨) |
| A-ME-3 | 로그인 → `advance(hours=2, seconds=1)` → `/me` | 401, 세션 행 삭제 |
| A-ME-4 | 1시간마다 `/me`로 7일 유지 → 7일+1초 | 7일 전까지 200, 이후 401 |
| A-ME-5 | 로그인 중 DB에서 `status='disabled'` | 다음 `/me` 401, 세션 행 삭제 |
| A-ME-6 | 30초 간격 2회 / 61초 뒤 1회 | `last_seen_at` 변화 없음 / 갱신 |

#### 5.5 로그아웃·비밀번호 변경 (FR-02·03)
| ID | 상황 | 기대 |
|---|---|---|
| A-LO-1 | 로그인 → `POST /logout` | 204, 세션 쿠키 `Max-Age=0`, 새 익명 CSRF 쿠키, 세션 행 없음, 이어서 `/me` 401, 새 CSRF로 `POST /signup` 가능 |
| A-LO-2 | 세션 없이 `POST /logout`(익명 CSRF) | 204 |
| A-PW-1 | `client`·`client2`로 같은 계정 로그인 → `client`에서 변경 | 200 `MSG_PASSWORD_CHANGED`, `client2` `/me` 401, `client` `/me` 200, 옛 비밀번호 로그인 401·새 비밀번호 200 |
| A-PW-2 | 현재 비밀번호 틀림 | 400 `wrong_current_password`, `sleeps`에 지연 기록(2번째부터) |
| A-PW-3 | 현재 비밀번호 5번 틀림 → 6번째(맞음) | 429 `too_many_attempts` |
| A-PW-4 | 새 비밀번호 9자 | 400 `weak_password`, `pwchange:user:<id>` 행 없음(시도로 안 셈) |
| A-PW-5 | 로그인 안 함 | 401 |
| A-PW-6 | `pending` 사용자 | 200 |

#### 5.6 채팅 연결·관리자 의존성
| ID | 상황 | 기대 |
|---|---|---|
| A-CH-1 | 세션 없이(익명 CSRF) 채팅 POST | 401 JSON `unauthenticated`, `content-type` `application/json`, 그래프 대역 호출 0회 |
| A-CH-2 | `pending` 로그인 → 채팅 POST | 403 `pending_approval` |
| A-CH-3 | `active` 로그인 → 채팅 POST | 200 `text/event-stream`, 첫 이벤트 `status checking`, 02 정상 시나리오(U-SSE-01)와 같은 이벤트 순서(CSRF 미들웨어가 스트림을 막지 않음) |
| A-CH-4 | `active` 로그인 후 DB에서 `disabled` | 401 |
| A-ADM-1 | 테스트 전용 라우트 `GET /api/_test/admin`(`require_admin`, 테스트 app에만 추가) — user active / admin active / admin pending / 미로그인 | 403 `forbidden` / 200 / 403 / 401 |

#### 5.7 로그 (DB·로그에 비밀값 없음)
| ID | 절차 | 기대 |
|---|---|---|
| U-LOG-1 | A-SU-1·A-LI-1·A-LI-2·A-PW-1을 한 테스트에서 실행하며 `caplog`(전체 로거, DEBUG) 수집 | 비밀번호 문자열, 세션 토큰 원본, CSRF 토큰이 로그에 없음 |
| U-LOG-2 | 같은 흐름 후 DB 전 테이블 텍스트 덤프(`users`·`auth_sessions`·`rate_limits`) | 비밀번호·세션 토큰 원본 없음, 아이디 원문은 `users`에만 |

### 6. CLI (마커 `db`, 동기 테스트) — `tests/test_cli_create_admin.py`
환경변수로 테스트 DB를 가리키고 `get_settings.cache_clear()` 후 `nadri.cli.main([...])` 호출.

| ID | 입력 | 기대 |
|---|---|---|
| C-ADM-1 | `create-admin --username Admin --email a@x.com --password-stdin`, stdin `"xk3!pQ9#zr\n"` | 종료 0, 출력에 `id=`·`아이디=admin`, DB `role='admin'`, `status='active'`, `approved_at` 채움, `approved_by` NULL. 이어서 API 로그인 → `role:"admin"` |
| C-ADM-2 | 같은 아이디로 다시 | 종료 1, `MSG_USERNAME_TAKEN` 출력, 행 1개 |
| C-ADM-3 | 비밀번호 `"password"`(짧음) | 종료 2, `MSG_PASSWORD_TOO_SHORT` |
| C-ADM-4 | `--password-stdin` 없이, 가짜 `getpass_fn`이 두 번 다른 값 | 종료 2, 행 없음 |
| C-ADM-5 | 출력·로그 | 비밀번호 문자열 없음 |

### 7. 02 회귀
| ID | 절차 | 기대 |
|---|---|---|
| R-02-1 | 02 테스트 전체(spec §6.8대로 `require_active` 덮어쓰기 + `anon_csrf` 헤더) | 기대값 변경 없이 통과 |

### 통과 기준
- 위 전부 통과. 테스트 실행 시간 기록(argon2 저비용 설정 덕분에 수십 초 이내 예상 — **미확인**).

---

## ② HITL (사용자가 직접 실행)

WSL2 Ubuntu `~/code/myAgent`. `<HOST>` = 터널 주소(예: `chat.<내 도메인>.dev`).

### H-0 준비
- [ ] `.env`에 `SESSION_SECRET` 추가: `echo "SESSION_SECRET=$(openssl rand -hex 32)" >> .env`
- [ ] 04 HITL H-0(Docker 권한) 통과 상태.

### H-1 기동 — cloudflared 상시 (G4 Q1)
```bash
docker compose -f compose.yaml -f compose.dev.yaml up -d --build
docker compose ps
curl -s http://127.0.0.1:8080/api/health
```
- 기대: `cloudflared`가 `--profile` 없이 `running`, api `healthy`, 헬스 `{"status":"ok"}`.

### H-2 첫 관리자 만들기 (FR-80)
```bash
docker compose run --rm api nadri create-admin --username admin --email <내 이메일>
```
- 비밀번호를 두 번 입력(화면에 안 보임). 기대: `관리자 계정을 만들었어요: id=1, 아이디=admin`. 9자 비밀번호를 넣어 거절 문구도 1번 확인.

### H-3 curl로 전체 흐름 (로컬)
아래 함수를 셸에 붙여 넣는다(쿠키를 헤더로 직접 다룬다 — curl 쿠키 저장소가 http 주소에서 `__Host-` 쿠키를 다루는 방식이 **미확인**이라 피함).
```bash
B=http://127.0.0.1:8080
csrf() { curl -s $B/api/auth/csrf | python3 -c 'import sys,json;print(json.load(sys.stdin)["csrf_token"])'; }
cookie() { sed -n "s/^set-cookie: $1=\([^;]*\).*/\1/Ip"; }   # 응답 헤더에서 쿠키 값 꺼내기
login() {  # login <아이디> <비밀번호>  → 전역 CK(쿠키 헤더)·TK(CSRF 토큰) 설정
  local t=$(csrf) h
  h=$(curl -s -D - -o /dev/null -X POST $B/api/auth/login -H 'Content-Type: application/json' \
      -H "X-CSRF-Token: $t" -H "Cookie: __Host-csrf=$t" -d "{\"username\":\"$1\",\"password\":\"$2\"}")
  echo "$h" | head -1
  SID=$(echo "$h" | cookie __Host-session); TK=$(echo "$h" | cookie __Host-csrf)
  CK="Cookie: __Host-session=$SID; __Host-csrf=$TK"
}
```
절차:
1. 가입 신청: `t=$(csrf); curl -s -X POST $B/api/auth/signup -H 'Content-Type: application/json' -H "X-CSRF-Token: $t" -H "Cookie: __Host-csrf=$t" -d '{"username":"tester1","email":"<받을 수 있는 메일>","password":"<10자 이상>"}'` → 201 `pending`.
2. `login tester1 '<비밀번호>'` → `HTTP/1.1 200`. `curl -s $B/api/auth/me -H "$CK"` → `"status":"pending"`.
3. 채팅: `curl -s -X POST $B/api/chat/sessions/x/messages -H 'Content-Type: application/json' -H "$CK" -H "X-CSRF-Token: $TK" -d '{"text":"경복궁 관람 시간"}'` → 403 `pending_approval`.
4. 승인(18 전까지 DB 직접): `docker compose exec postgres psql -U postgres -d nadri -c "update users set status='active', approved_at=now() where username='tester1'"`
5. 3을 `-N`으로 다시 → SSE 이벤트가 흐름(02 HITL-2와 같은 모양).
6. CSRF 빼고 3 반복(`X-CSRF-Token` 헤더 제거) → 403 `csrf_failed`.

### H-4 브라우저 쿠키 — 터널 주소와 localhost (A17, 이 작업의 핵심)
Windows Chrome에서 두 주소 각각: ① `https://<HOST>/api/health` ② `http://localhost:8080/api/health` 를 연 뒤 DevTools(F12) → Console에 붙여 넣기(`tester1`의 비밀번호로 바꿈):
```js
const t = (await (await fetch('/api/auth/csrf')).json()).csrf_token;
const r = await fetch('/api/auth/login', {method:'POST', headers:{'Content-Type':'application/json','X-CSRF-Token':t},
  body: JSON.stringify({username:'tester1', password:'<비밀번호>'})});
console.log(r.status, await (await fetch('/api/auth/me')).json());
```
확인:
- [ ] 콘솔: `200 {…"status":"active"}`
- [ ] Application → Cookies: `__Host-session` — HttpOnly ✓, Secure ✓, SameSite `Lax`, Path `/`, 만료 7일 뒤. `__Host-csrf` — HttpOnly ✗, Secure ✓.
- [ ] `document.cookie`에 `__Host-session`이 **안 보이고** `__Host-csrf`만 보임.
- 판정: 두 주소 모두 통과 → A17 통과. localhost만 실패(콘솔 `/me` 401 또는 쿠키 없음) → "브라우저 확인은 터널 주소로만" 기록(spec §11). 터널도 실패 → 작업 중단하고 보고.
- (선택) 휴대폰 브라우저로 터널 주소에서 같은 확인(PWA는 14).

### H-5 잠금·실제 IP (NFR-02, ADR-10)
```bash
for i in 1 2 3 4 5 6; do login tester1 wrong-password-$i; done      # 마지막 줄: 429
login tester1 '<맞는 비밀번호>'                                       # 429 (잠금 중)
docker compose exec postgres psql -U postgres -d nadri -c "select key, count, locked_until from rate_limits"
```
- 기대: 2~4번째 응답이 점점 늦게 옴(1·2·4초). 6번째부터 429, 메시지 "15분 뒤". `login:acct:` 키는 해시라 아이디가 안 보임.
- 터널 주소에서 1번 틀린 뒤 같은 표를 보면 `login:ip:<내 공인 IP>`가 생김(로컬 시도는 도커 내부 IP) → 실제 IP 전달 확인.
- 해제: `docker compose exec postgres psql -U postgres -d nadri -c "delete from rate_limits where key like 'login:%'"`.

### H-6 비밀번호 변경 → 다른 세션 끊김 (FR-03)
1. 브라우저(터널)에서 H-4대로 `tester1` 로그인 상태 유지.
2. 셸에서 `login tester1 '<비밀번호>'` 후:
   `curl -s -X POST $B/api/auth/password -H 'Content-Type: application/json' -H "$CK" -H "X-CSRF-Token: $TK" -d '{"current_password":"<비밀번호>","new_password":"<새 10자 이상>"}'`
3. 브라우저 콘솔 `await (await fetch('/api/auth/me')).status` → **401**. 셸 `curl -s $B/api/auth/me -H "$CK"` → 200.
4. 새 비밀번호로 브라우저 재로그인 → 200.

### H-7 로그 확인
```bash
docker compose logs api | grep -n -i -e '<비밀번호 일부>' -e "$SID" || echo "없음"
```
- 기대: `없음`.

### HITL 결과 보고 (구현자가 사용자에게)
| 항목 | 결과 |
|---|---|
| H-1 cloudflared 상시 기동 | |
| H-2 create-admin | |
| H-3 가입→pending→403→승인→SSE, CSRF 403 | |
| H-4 A17: 터널 / localhost 쿠키 | 통과·실패 + 브라우저 버전 |
| H-5 잠금·지연·실제 IP | |
| H-6 다른 세션 401 | |
| H-7 로그에 비밀값 없음 | |
| `common_passwords.txt` 항목 수·출처 커밋 | |
| Argon2 실제 파라미터 | |
