# 18-admin-users — 테스트 설계 (test)

> spec.md와 짝. 절 번호 §n은 spec.md 기준. 작성 2026-11-22. 상태: **확정(2026-11-22)**.
> ① 자동 테스트 — A. pytest(결정적 — 외부 호출 없음, DB는 04 테스트 컨테이너, 마커 `db`) · B. Vitest(서버 없음, api 함수 목킹) · C. Playwright(실제 compose) ② HITL(사용자가 직접).

---

## ① 자동 테스트

### A. pytest

#### 0. 공통
- 실행: `cd ~/code/myAgent/backend && uv run pytest -m "not integration"` (Docker 필요). DB 없는 것만: `-m "not integration and not db"`.
- 재사용: 05 헬퍼(`app`·`client`·`client2`·`make_user(db_sf, username, password, *, status, role, email)`·`login`·`post`·`get_csrf`·`clock`), 04 `db_sf`, 02 대역(채팅 그래프 가짜), 09 `make_session`.
- 추가 헬퍼(`tests/helpers/admin.py`):

| 이름 | 역할 |
|---|---|
| `admin_client(app, db_sf)` | `make_user(..., "boss", PW, role="admin", status="active")` → 새 `client`로 `login` → 그 client 반환 |
| `act(client, uid, action)` | CSRF 헤더 붙여 `POST /api/admin/users/{uid}/{action}` |
| `user_row(db_sf, uid)` | `users` 행(status·approved_at·approved_by) 조회 |
| `session_count(db_sf, uid)` | 그 사용자의 `auth_sessions` 행 수 |

#### 1. 상태 전이 표 (DB 없음) — `tests/api/admin/test_transitions.py`

| ID | 입력 | 기대 |
|---|---|---|
| U-TR-01 | `next_status(action, current)` — 동작 3개 × 상태 4개 = 12칸(파라미터화) | spec §5 표와 같음: `("approve","pending")→"active"`, `("reject","pending")→"rejected"`, `("disable","active")→"disabled"`, 나머지 9칸 `None` |
| U-TR-02 | `ADMIN_ACTIONS`의 모든 상태 값 | 04 `USER_STATUSES` 안에 있음(상수 대조) |
| U-TR-03 | `AdminUserOut.model_fields` | `password_hash` 없음, `role`·`status` Literal 집합 == 04 `USER_ROLES`·`USER_STATUSES` |

#### 2. 권한 (마커 `db`) — `tests/api/admin/test_admin_guard.py`

준비: `alice`(user, active), `penny`(user, pending), `boss`(admin, active), `sleepy`(admin, pending — DB 직접 생성).

| ID | 요청 | 기대 |
|---|---|---|
| A-ADR-01 | 로그인 안 한 client: `GET /api/admin/users` | 401 `unauthenticated` |
| A-ADR-02 | alice / penny / sleepy 로그인 후 `GET /api/admin/users` | 각각 403 `forbidden`, 문구 = `MSG_FORBIDDEN` |
| A-ADR-03 | boss `GET /api/admin/users` | 200 |
| A-ADR-04 | alice: `GET /api/admin/users?status=deleted`, `POST /api/admin/users/abc/approve`(CSRF 있음), `POST /api/admin/users/999999/approve` | 셋 다 403 `forbidden`(422·404가 아님 — 형식·존재를 드러내지 않음). **실제로 422가 먼저 나오면** 테스트를 실패로 두지 말고 결과를 spec §4.1 "미확인"에 기록한 뒤 기대를 422로 바꾼다 |
| A-ADR-05 | boss가 CSRF 헤더 없이 `POST …/{penny}/approve` | 403 `csrf_failed`, penny 상태 그대로 |
| A-ADR-06 누락 방지 | `create_app` 결과의 `app.routes` 중 경로가 `/api/admin`으로 시작하는 모든 `APIRoute` — `route.dependant`의 의존성 트리를 재귀로 펼친 호출 대상 목록 | 모두 `require_admin` 포함, 대상 경로 수 ≥ 2(18의 2개 — 19·25가 늘림) |
| A-ADR-07 | 05 A-ADM-1 그대로 실행 | 통과(회귀) |

#### 3. 목록 (마커 `db`) — `tests/api/admin/test_admin_users_list.py`

준비: `clock`으로 created_at을 다르게 해 사용자 5명 — `p1`(pending, 가장 오래됨), `p2`(pending), `a1`(active), `r1`(rejected), `d1`(disabled) + `boss`.

| ID | 요청 | 기대 |
|---|---|---|
| A-UL-01 | boss `GET /api/admin/users?status=pending` | `users` = [p2, p1](created_at 내림차순) |
| A-UL-02 | `?status=active` | a1·boss만(boss는 `role:"admin"`) |
| A-UL-03 | `?status=rejected` / `?status=disabled` | [r1] / [d1] |
| A-UL-04 | status 없음 | 6명 전부, created_at 내림차순(같으면 id 내림차순) |
| A-UL-05 | 응답 항목 키 | 정확히 `id, username, email, role, status, created_at, approved_at` — `password_hash`·`approved_by` 없음 |
| A-UL-06 | `created_at` 문자열 | ISO 8601, `+00:00`(또는 `Z`)로 끝남 |
| A-UL-07 | `?status=deleted` (boss) | 422 |
| A-UL-08 | pending 0명일 때 `?status=pending` | 200 `{"users": []}` |

#### 4. 동작 (마커 `db`) — `tests/api/admin/test_admin_users_actions.py`

| ID | 준비 | 동작 | 기대 |
|---|---|---|---|
| A-UA-01 승인 | p1 pending | boss `approve` | 200 응답 `status:"active"`, `approved_at` = `clock.now`(ISO), DB `approved_by = boss.id` |
| A-UA-02 승인 후 사용 | A-UA-01 뒤 p1 로그인 | `GET /api/auth/me` · `POST /api/chat/sessions`(09) | `status:"active"` · 201(채팅 세션 생성 가능 — LLM 없음) |
| A-UA-03 거절 | p1 pending, p1이 client2로 로그인해 둠 | boss `reject` | 200 `status:"rejected"`, `approved_at` null. client2 `GET /api/auth/me` → 401, 그 뒤 `session_count(p1) == 0`(05 `current_user`가 지움) |
| A-UA-04 거절 후 로그인 | A-UA-03 뒤 | p1 `login` | 401 `login_failed`, 문구 = 없는 아이디와 같음 |
| A-UA-05 비활성화 | a1 active, client2(a1)·client3(a1) 두 기기 로그인 | boss `disable` | 200 `status:"disabled"`, **응답 직후** `session_count(a1) == 0`(요청 없이도 0), boss 세션 수 그대로 |
| A-UA-06 즉시 차단 | A-UA-05 뒤 client2 | `POST /api/chat/sessions` · `POST /api/chat/sessions/{기존 세션}/messages`(CSRF 있음) | 둘 다 401 `unauthenticated`, 02 그래프 대역 호출 0회 |
| A-UA-07 재로그인 | A-UA-05 뒤 | a1 `login`(맞는 비밀번호) | 401 `login_failed` |
| A-UA-08 전이 표 | 상태 4개 사용자 × 동작 3개(12칸, 파라미터화) | boss 동작 | 허용 3칸은 200·상태 변경, 나머지 9칸은 409 `user_status_conflict`, 본문 `status` = 현재 상태, DB 변화 없음(approved_at 그대로) |
| A-UA-09 두 번 | A-UA-01 뒤 `clock.advance(minutes=5)` | 다시 `approve` | 409, `approved_at`은 첫 승인 값 그대로 |
| A-UA-10 관리자 대상 | 다른 관리자 `boss2`(active), boss 자신 | `disable` boss2 / `disable` boss / `approve` boss | 모두 409 `admin_target`, 상태·세션 그대로 |
| A-UA-11 없는 사용자 | — | `approve` 999999 | 404 `user_not_found` |
| A-UA-12 경로 형식 | — | `/users/abc/approve`, `/users/0/approve`, `/users/9223372036854775808/approve`, `/users/1/delete` | 모두 422 |
| A-UA-13 동시 | p1 pending | `asyncio.gather`로 `approve`·`reject` 동시 2건(각각 별도 client, 둘 다 boss 세션) | 하나 200·하나 409, 최종 상태는 200 받은 쪽 결과(행 잠금) |
| A-UA-14 로그 | A-UA-05 실행하며 `caplog` | `admin_user_action` 1줄: `admin_id`·`user_id`·`action=disable`·`from=active`·`to=disabled`·`sessions_revoked=2`, 그리고 a1의 아이디·이메일 문자열이 로그에 없음 |
| A-UA-15 관리자 한도 | (회귀) 11 A-AD-09 그대로 | 통과 — 18이 한도 규칙을 바꾸지 않음 |

#### 5. 앞 작업 회귀
- 05 전체(특히 A-ADM-1, 문구 상수 목록 테스트에 `MSG_USER_NOT_FOUND`·`MSG_USER_STATUS_CONFLICT`·`MSG_ADMIN_TARGET` 추가), 09 세션 API, 11 한도 테스트 재실행.

---

### B. Vitest — `web/tests/unit/`

#### B1. `admin-api.test.ts`

| ID | 내용 | 기대 |
|---|---|---|
| V-AA-01 | `listUsers()` / `listUsers("pending")` (`apiJson` 목킹) | 호출 경로 `/api/admin/users` / `/api/admin/users?status=pending`, 응답의 `users` 배열 반환 |
| V-AA-02 | `applyUserAction(7, "disable")` | `POST /api/admin/users/7/disable`, 본문 없음 |
| V-AA-03 | `formatKst("2026-11-21T15:00:00+00:00")` | `"2026-11-22 00:00"`(KST 자정 — `24:00`이 아님) |
| V-AA-04 | `formatKst("2026-11-22T05:07:00Z")` | `"2026-11-22 14:07"` |
| V-AA-05 | `STATUS_LABEL` 키 | 4개 상태 모두, 값 = spec §3 |

#### B2. `admin-shell.test.tsx` (`useMe` 목킹)

| ID | me | 기대 |
|---|---|---|
| V-AS-01 | `role:"user"` | "접근 권한이 없어요." + "채팅으로" 링크, children 안 그림 |
| V-AS-02 | `role:"admin"` | children 그림, `ADMIN_NAV` 링크 모두 표시, 현재 경로 항목 `aria-current="page"`(`usePathname` 목킹) |
| V-AS-03 | `ADMIN_NAV[0]` | `{href:"/admin/users", label:"사용자"}` |

#### B3. `admin-users-page.test.tsx` (`admin-api` 목킹, `window.confirm` 목킹)

| ID | 준비 | 동작 | 기대 |
|---|---|---|---|
| V-AU-01 | 첫 렌더 | — | `listUsers("pending")` 1회, "승인 대기" 탭 선택됨 |
| V-AU-02 | 탭 "전체" 클릭 | — | `listUsers(undefined)` |
| V-AU-03 | pending 1명 | — | 줄에 아이디·이메일·"승인 대기"·가입 신청 일시(`formatKst`)·승인 일시 "—", 버튼 [승인] [거절] |
| V-AU-04 | active user 1명 + active admin 1명 | — | user 줄에 [비활성화], admin 줄에 "관리자" 표시·버튼 없음 |
| V-AU-05 | rejected·disabled 사용자 | — | 버튼 없음 |
| V-AU-06 | [승인] 클릭 | — | `confirm` 호출 0회, `applyUserAction(id,"approve")`, 성공 알림 `"{아이디} 님을 승인했어요."`, `listUsers` 다시 호출 |
| V-AU-07 | [거절] 클릭, confirm → false | — | `applyUserAction` 호출 0회 |
| V-AU-08 | [거절] 클릭, confirm → true | — | confirm 문구 = spec §6.3, `applyUserAction(id,"reject")`, 성공 알림 |
| V-AU-09 | [비활성화], confirm true | — | confirm 문구 = spec §6.3, 성공 알림 `"… 비활성화했어요."` |
| V-AU-10 | `applyUserAction`이 `ApiError(409,"user_status_conflict", 서버문구)` | 승인 | 오류 알림에 서버 문구, `listUsers` 다시 호출 |
| V-AU-11 | `ApiError(401,…)` | 승인 | `router.replace("/login")` |
| V-AU-12 | `listUsers`가 `ApiError(403,"forbidden",…)` | 첫 렌더 | 오류 알림 "접근 권한이 없어요.", 목록 없음 |
| V-AU-13 | 처리 중(Promise 대기) | 승인 | 그 줄 버튼만 비활성·"처리 중…", 다른 줄 버튼 활성 |
| V-AU-14 | 빈 목록, 탭별 | — | spec §6.3 빈 목록 문구 5종 |

#### B4. `account-admin-link.test.tsx`

| ID | me | 기대 |
|---|---|---|
| V-AL-01 | `role:"admin"` | "관리자 화면" 링크 `href="/admin"` |
| V-AL-02 | `role:"user"` | 링크 없음 |

---

### C. Playwright (실제 compose) — `web/e2e/admin.spec.ts`

준비: 14 `global-setup.ts`(`e2e_` 사용자·요청 제한 카운터 정리). `helpers/db.ts`에 추가:
- `makeAdmin(username, password)` = API로 가입 신청(`GET /api/auth/csrf` → `POST /api/auth/signup`, Playwright `request` 컨텍스트) → psql `update users set role='admin', status='active', approved_at=now() where username=$1`. 아이디는 `e2e_admin_<시각>`. (비밀번호 해시를 psql로 만들 수 없어 가입 API를 쓴다 — 05 CLI는 TTY·컨테이너 실행이 필요해 테스트에 쓰지 않음)

| ID | 흐름 | 기대 |
|---|---|---|
| P-AD-01 승인 | 컨텍스트 U: `/signup`에서 `e2e_u_<시각>` 가입 → 로그인 → `/pending`. 컨텍스트 A: 관리자 로그인 → `/account`의 "관리자 화면" → `/admin/users` | 승인 대기 탭에 그 사용자 → [승인] → 성공 알림, 줄이 사라짐. U에서 "승인됐는지 확인" → `/`(채팅 화면), 그 페이지에서 `GET /api/chat/sessions` 응답 200(네트워크 기록) |
| P-AD-02 거절 | 새 사용자 가입 → A에서 [거절] → 확인 창 수락(`page.on("dialog", d => d.accept())`) | 성공 알림. U가 로그인 → "아이디 또는 비밀번호가 맞지 않아요." |
| P-AD-03 비활성화 | 승인된 사용자 U가 `/`에 있음 → A "활성" 탭에서 [비활성화] → 수락 → U 새로고침 | U가 `/login`으로 이동. U 다시 로그인 → 로그인 실패 문구 |
| P-AD-04 확인 창 취소 | A에서 [거절] → `dialog.dismiss()` | 상태 그대로(줄 남음), `POST /api/admin/…` 요청 0회 |
| P-AD-05 일반 사용자 | active 일반 사용자로 `/admin/users` 접속 | "접근 권한이 없어요.", `/api/admin/` 요청 0회, `/account`에 "관리자 화면" 링크 없음 |
| P-AD-06 직접 호출 | 일반 사용자 로그인 상태의 `page.request.get("/api/admin/users")` | 403 |
| P-AD-07 미로그인 | `/admin` 접속 | `/login` |
| P-AD-08 이동 | 관리자로 `/admin` 접속 | `/admin/users` |
| P-AD-09 모바일 | `mobile-chrome` 프로젝트로 관리자 `/admin/users`(사용자 3명 이상) | 가로 스크롤 없음(`scrollWidth <= innerWidth`), 버튼 보임 |

### 통과 기준
- A·B 전부 통과(`-m "not integration"`, `npm run test`), C 전부 통과(compose 기동). 실패 시 스크린샷·trace는 `test-results/`(커밋 안 함).

---

## ② HITL

전제: 18 적용 compose 기동(`docker compose up -d --build`), 터널 주소 `<HOST>` 동작, 관리자 계정 있음(05 H-2 `create-admin`). PC 브라우저 1개 + 휴대폰 1대(또는 PC 시크릿 창).

### HITL-1 가입 신청 → 화면에서 승인 → 채팅 (FR-04·80·81)
1. 휴대폰 `https://<HOST>/signup`에서 `tester2` 가입 신청 → 로그인 → "승인 대기" 화면.
2. PC에서 관리자로 로그인 → `/account` → "관리자 화면" → `/admin/users`.
3. "승인 대기" 탭에 `tester2`(아이디·이메일·가입 신청 일시가 한국 시간으로 맞는지) → [승인] → "tester2 님을 승인했어요."
4. 휴대폰에서 "승인됐는지 확인" → 채팅 화면 → 질문 1개(`경복궁 관람 시간`) → 답변이 흐르는지.
5. "활성" 탭에서 `tester2`의 승인 일시 확인.
6. DB 확인: `docker compose exec postgres psql -U postgres -d nadri -c "select username, status, approved_at, approved_by from users where username='tester2'"` → `active`, 승인 관리자 id가 관리자 계정 id.

### HITL-2 비활성화 → 즉시 로그아웃 (FR-84)
1. 휴대폰에서 `tester2`가 채팅 화면에 있는 상태.
2. PC `/admin/users` "활성" 탭 → `tester2` [비활성화] → 확인 창 문구 확인 → 확인.
3. 휴대폰에서 새 질문 보내기 또는 새로고침 → 로그인 화면으로 이동.
4. `tester2`로 다시 로그인 → "아이디 또는 비밀번호가 맞지 않아요."
5. 세션 확인: `docker compose exec postgres psql -U postgres -d nadri -c "select count(*) from auth_sessions s join users u on u.id=s.user_id where u.username='tester2'"` → `0`.
6. (선택) 되돌리기 명령(spec §8)으로 다시 active → 로그인 되는지.

### HITL-3 권한 (FR-80)
1. 일반 사용자로 PC 브라우저 로그인 → 주소창에 `/admin/users` → "접근 권한이 없어요."
2. 같은 브라우저 DevTools 콘솔: `(await fetch('/api/admin/users')).status` → `403`.
3. 관리자 화면에서 관리자 자신 줄에 버튼이 없는지.

### HITL 결과 보고
| 항목 | 결과 |
|---|---|
| HITL-1 화면 승인 → 휴대폰 채팅 | |
| HITL-1 일시 표시(한국 시간) | |
| HITL-2 비활성화 후 휴대폰 로그아웃·재로그인 실패·세션 0 | |
| HITL-3 일반 사용자 화면·API 403 | |
| spec §4.1 미확인(관리자 아닌 사람의 형식 오류 요청 = 403 / 422) 결과 | |
