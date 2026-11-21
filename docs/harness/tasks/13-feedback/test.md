# 13-feedback — 테스트 설계 (test)

> spec.md와 짝. 절 번호 §n은 spec.md 기준. 작성 2026-11-21. 상태: 초안 — 사용자 검토 대기.
> ① pytest(결정적 — 외부 호출 없음, DB는 04 테스트 컨테이너, 마커 `db`) ② HITL(사용자가 직접).

---

## ① pytest

### 0. 공통
- 실행: `cd ~/code/myAgent/backend && uv run pytest -m "not integration"` (Docker 필요). DB 없는 것만: `-m "not integration and not db"`.
- 재사용: 05 헬퍼(`app`·`client`·`client2`·`make_user`·`login`·`post`·`clock`), 04 `db_sf`, 09 `make_session(db_sf, user_id, *, turns=…)`, 12 `make_faq(db_sf, …)`.
- 추가 헬퍼(`tests/helpers/chat.py`에 덧붙임):

| 이름 | 역할 |
|---|---|
| `put_fb(client, mid, body)` | CSRF 헤더 붙여 `PUT /api/chat/messages/{mid}/feedback` |
| `del_fb(client, mid)` | CSRF 헤더 붙여 `DELETE` |
| `assistant_ids(db_sf, session_id)` | 그 세션 assistant 메시지 id 목록(turn_no 순) |
| `set_cache_hit(db_sf, message_id, faq_id)` | 메시지의 `from_cache=true`, `faq_cache_id` 직접 설정 |

### 1. 입력 모델 (DB 없음) — `tests/api/test_feedback_model.py`

| ID | 입력 | 기대 |
|---|---|---|
| U-FB-01 | `FeedbackIn(rating="up")` | 통과, reason None |
| U-FB-02 | `rating="down", reason="wrong"` (4개 사유 각각, 파라미터화) | 통과 |
| U-FB-03 | `rating="down", reason=None` | 통과 |
| U-FB-04 | `rating="up", reason="wrong"` | `ValidationError` |
| U-FB-05 | `rating="meh"` / `reason="bad"` / rating 없음 | `ValidationError` |
| U-FB-06 | `FeedbackIn` 사유 Literal 집합 == 04 `FEEDBACK_REASONS`, rating 집합 == `FEEDBACK_RATINGS` | 같음(상수 대조) |

### 2. API·권한 (마커 `db`) — `tests/api/test_feedback_api.py`

준비: `alice`(active) 로그인 → `make_session(db_sf, alice.id, turns=2)` → assistant id `a1`, `a2`, user id `u1`. `bob`(active) 별도 세션 `b1`.

| ID | 요청 | 기대 |
|---|---|---|
| A-FB-01 | alice `PUT a1 {"rating":"up"}` | 200 `{"rating":"up","reason":null}`, DB 1행(user_id=alice) |
| A-FB-02 | 이어서 `PUT a1 {"rating":"down","reason":"outdated"}` | 200, 행 1개 유지, rating down·reason outdated, `updated_at` = `clock.now`(advance 뒤 값) |
| A-FB-03 | 이어서 `PUT a1 {"rating":"down"}` | reason NULL |
| A-FB-04 | `DELETE a1` | 204, 행 0 |
| A-FB-05 | 피드백 없는 `a2`에 `DELETE` | 204 |
| A-FB-06 | alice가 bob의 `b1`에 PUT / DELETE | 404 `message_not_found`, 문구 = `MSG_MESSAGE_NOT_FOUND`, DB 변화 없음 |
| A-FB-07 | alice가 자기 user 메시지 `u1`에 PUT | 404 |
| A-FB-08 | 없는 id `999999` | 404 |
| A-FB-09 | 경로 `abc` / `0` / `9223372036854775808` | 422 |
| A-FB-10 | 본문 `{"rating":"up","reason":"wrong"}` | 422, DB 변화 없음 |
| A-FB-11 | CSRF 헤더 없이 PUT | 403 `csrf_failed` |
| A-FB-12 | 로그인 안 한 `client2` | 401 `unauthenticated` |
| A-FB-13 | pending 사용자 | 403 `pending_approval` |
| A-FB-14 | 세션 삭제(`DELETE /api/chat/sessions/{id}`) 뒤 | `message_feedback` 0행(연쇄) |

### 3. 👎 → 캐시 삭제 (마커 `db`) — `tests/api/test_feedback_cache.py`

| ID | 준비 | 동작 | 기대 |
|---|---|---|---|
| A-FC13-01 원본 | `make_faq(source_message_id=a1)` → 캐시 X | `PUT a1 down` | X 삭제, 응답 200 |
| A-FC13-02 적중 | 다른 세션의 메시지 `c1`이 원본인 캐시 Y, `set_cache_hit(a1, Y)` | `PUT a1 down` | Y 삭제, `a1.faq_cache_id` NULL, `c1`의 다른 데이터 그대로 |
| A-FC13-03 둘 다 | a1이 X의 원본이면서 Y 적중(인위적) | `PUT a1 down` | X·Y 모두 삭제 |
| A-FC13-04 👍 | 원본 캐시 X | `PUT a1 up` | X 그대로 |
| A-FC13-05 무관 캐시 | 캐시 Z(원본 c1, a1과 무관) | `PUT a1 down` | Z 그대로 |
| A-FC13-06 연쇄 NULL | X를 가리키는 다른 메시지 d1(`faq_cache_id=X`) | `PUT a1 down`(a1이 X 원본) | X 삭제, d1 `faq_cache_id` NULL, d1 남음 |
| A-FC13-07 두 번 | A-FC13-01 뒤 다시 `PUT a1 down` | 200, 캐시 삭제 0, 오류 없음 |
| A-FC13-08 되살리지 않음 | A-FC13-01 뒤 `PUT a1 up` | X 여전히 없음 |
| A-FC13-09 로그 | A-FC13-01 | `feedback` 로그 1줄에 `cache_deleted: 1`, 답변 본문·질문 글 없음(caplog) |

### 4. 캐시 저장 경합 (마커 `db`) — `tests/api/test_faq_save_feedback.py`

| ID | 준비 | 동작 | 기대 |
|---|---|---|---|
| A-FS13-01 | 메시지 a1에 `message_feedback(down)` 행 | 12 `save(db, source_message_id=a1, c=후보)` | None, `faq_cache` 0행 |
| A-FS13-02 | a1에 `up` 행 | `save` | id 반환, 1행 |
| A-FS13-03 | 피드백 없음 | `save` 2번 | 첫 번째 id, 두 번째 None(12 `DO NOTHING` 그대로) |
| A-FS13-04 흐름 | 09·12 실제 `DbTurnStore` + 가짜 그래프로 첫 질문 저장(캐시 조건 충족) → `run_spawned()` **전에** `PUT a1 down` → `run_spawned()` | `faq_cache` 0행 |

### 5. 세션 조회 응답 (마커 `db`) — `tests/api/chat/test_sessions_feedback.py`

| ID | 준비 | 기대 |
|---|---|---|
| A-SF-01 | a1 👎(wrong), a2 없음 | `GET /api/chat/sessions/{id}` → a1 `feedback == {"rating":"down","reason":"wrong"}`, a2 `feedback == null`, user 메시지 `feedback == null` |
| A-SF-02 | 메시지 20턴 세션 | SQL 문 수 = 피드백 넣기 전과 같음(SQLAlchemy `before_cursor_execute` 이벤트로 셈 — 메시지마다 추가 조회 없음) |
| A-SF-03 | `GET /api/chat/sessions`(목록) | 응답에 `feedback` 키 없음 |

### 6. 앞 작업 회귀
- 09·12 테스트 전체 재실행(spec §9 수정 반영). 05 문구 상수 목록 테스트가 있으면 `MSG_MESSAGE_NOT_FOUND` 추가.

### 통과 기준
- 위 전부 통과, `-m "not integration"`에서 실패 0.

---

## ② HITL

전제: 13 적용 compose, active 계정, 09 HITL 셸 함수(`login`·`new_session`·`ask`), 12 HITL-1을 한 상태(캐시 1행 있음)면 좋다.

### HITL-1 피드백·캐시 삭제
1. `S1=$(new_session); ask $S1 '경복궁 관람 시간과 휴무일 알려줘'` → `done`의 `assistant_message_id`를 `M`에 적는다.
2. 몇 초 뒤 캐시 확인:
   ```bash
   docker compose exec postgres psql -U postgres -d nadri -c "select id, source_message_id, hit_count from faq_cache order by id desc limit 3"
   ```
3. 👍: `curl -s -X PUT $B/api/chat/messages/$M/feedback -H 'Content-Type: application/json' -H "$CK" -H "X-CSRF-Token: $TK" -d '{"rating":"up"}'` → `{"rating":"up","reason":null}`.
4. 👎+사유: 같은 명령에 `-d '{"rating":"down","reason":"outdated"}'` → 2에서 본 `source_message_id = M` 캐시 행이 사라졌는지 2의 명령으로 확인.
5. 세션 조회: `curl -s $B/api/chat/sessions/$S1 -H "$CK"` → 해당 assistant 메시지에 `"feedback":{"rating":"down","reason":"outdated"}`.
6. 취소: `curl -s -X DELETE $B/api/chat/messages/$M/feedback -H "$CK" -H "X-CSRF-Token: $TK" -o /dev/null -w '%{http_code}\n'` → `204`, 5를 다시 보면 `"feedback":null`.
7. 남의 메시지: 다른 계정으로 `login` 후 3을 같은 `$M`으로 → 404 `message_not_found`.

### HITL 결과 보고
| 항목 | 결과 |
|---|---|
| 3·4 응답, 4에서 캐시 행 삭제 확인 | |
| 5·6 조회 응답의 `feedback` | |
| 7 남의 메시지 404 | |
