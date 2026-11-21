# 11-quota-usage — 테스트 설계 (test)

> spec.md와 짝. 절 번호 §n은 spec.md 기준. 작성 2026-11-21. 상태: 초안 — 사용자 검토 대기.
> ① pytest(결정적, DB는 04 테스트 컨테이너 — 마커 `db`) ② HITL. 실호출은 `@pytest.mark.integration`.

---

## ① pytest

### 0. 공통
- 실행: `cd ~/code/myAgent/backend && uv run pytest -m "not integration"` (Docker 필요).
- 05 헬퍼(`app`·`client`·`make_user`·`login`·`post`·`clock`), 09 헬퍼(`make_session`·`chat`·`run_spawned`), 02·08 대역을 그대로 쓴다.
- 추가 헬퍼: `set_quota(db_sf, user_id, day, used, extra=0)`, `add_request(db_sf, user_id, day, status)`, `usage_rows(db_sf)`(usage_events 전체를 dict 목록으로).
- 시계: `clock.now` 기본 `2026-11-21T00:00:00+00:00` = KST 09:00.

### 1. 단가·비용 — `tests/core/test_pricing.py`

| ID | 입력 | 기대 |
|---|---|---|
| U-PR-01 | answer, model `gpt-6-luna`, input 1,000,000, cached 0, write 0, output 0 | `0.10000000` |
| U-PR-02 | input 1,000,000(캐시 읽기 600,000 포함), output 0 | `0.4×0.10 + 0.6×0.01 = 0.04600000` |
| U-PR-03 | input 1,000,000, cache_write 1,000,000 | `0.12500000`(1.25배) |
| U-PR-04 | output 1,000,000 | `0.50000000` |
| U-PR-05 | [A] §10 "답변(최종 작성)" 예: input 7,000·cached 3,500·output 500 | `(3500×0.10 + 3500×0.01 + 500×0.50)/1e6 = 0.00063500` |
| U-PR-06 | model `gpt-6-luna-2026-11-01` | `gpt-6-luna` 단가 |
| U-PR-07 | model `gpt-7` | `0`, WARNING 로그에 모델명만 |
| U-PR-08 | 토큰 모두 None | `0` |
| U-PR-09 | cached > input(이상 응답) | 캐시 안 된 입력 0으로, 음수 없음 |
| U-PR-10 | embed, `text-embedding-3-small`, input 1,000,000 | `0.02000000` |
| U-PR-11 | stt, `gpt-transcribe`, units 90(초) | `0.00675000` |
| U-PR-12 | moderation·web_search·tts | `0` |
| U-PR-13 | `LLM_KINDS ∪ FREE_KINDS ∪ {"embed","stt"}` | 04 `USAGE_KINDS`와 같은 집합 |

### 2. 사용량 행 — `tests/api/test_usage.py`

| ID | 입력 | 기대 |
|---|---|---|
| U-US-01 | `usage_row(UsageRecord(kind="answer", model="gpt-6-luna", input_tokens=100, cached_tokens=80, cache_write_tokens=0, output_tokens=20, units=None, ms=1200), user_id=1, message_id=9)` | `total_ms=1200`, `tool_ms=None`, `ttft_ms=None`, `cost_usd` = U-PR 식, 토큰 그대로 |
| U-US-02 | kind web_search, units 1, ms 800 | `tool_ms=800`, `cost_usd=0`, `units=1` |
| U-US-03 | 토큰 None | 컬럼 None(0 아님) |
| U-US-04 | 02 `UsageRecord.kind`의 Literal 값 | 04 `USAGE_KINDS`의 부분집합 |
| U-US-05 (`db`) | `record_usage(db, [3건], user_id=u, message_id=None)` + 커밋 | 3행, CHECK 위반 없음 |
| U-US-06 (`db`) | 빈 목록 | 0행 |

### 3. 한도 순수 함수 — `tests/api/test_quota_pure.py`

| ID | 입력 | 기대 |
|---|---|---|
| U-QT-01 | `kst_day(2026-11-21T14:59:59Z)` / `…T15:00:00Z` | `2026-11-21` / `2026-11-22` |
| U-QT-02 | naive 시각 | `ValueError` |
| U-QT-03 | `seconds_to_kst_midnight(2026-11-21T14:59:00Z)` | `60` |
| U-QT-04 | `…T15:00:00Z`(KST 자정 정각) | `86400` |

### 4. 한도 DB — `tests/api/test_quota_db.py` (마커 `db`)

| ID | 준비 | 기대 |
|---|---|---|
| D-QT-01 | 행 없음 | `get_status` → limit 50, used 0, remaining 50, request_status None |
| D-QT-02 | used 49 | `ensure_quota` 통과 |
| D-QT-03 | used 50 | `ensure_quota` → 429 `quota_exceeded`, 본문 `limit 50·used 50·request_status null`, `Retry-After`, 문구 `MSG_QUOTA_EXCEEDED`(`{limit}`=50) |
| D-QT-04 | used 50 + 요청 pending | 429, 문구 `MSG_QUOTA_PENDING`, `request_status "pending"` |
| D-QT-05 | used 50, extra 50(승인) | 통과, remaining 50 |
| D-QT-06 | used 100, extra 50, 요청 approved | 429 `MSG_QUOTA_DONE_TODAY` |
| D-QT-07 | used 50 + 요청 rejected | 429 `MSG_QUOTA_DONE_TODAY` |
| D-QT-08 | `charge` 2회(행 없음에서) | used 2, 반환 48 |
| D-QT-09 | 어제 날짜 used 50, 오늘 없음 | 오늘 통과(날짜별) |
| D-QT-10 | `charge`를 `clock` KST 23:59:59 → 다음 날 00:00:01로 | 다음 날 행 used 1 |
| D-QT-11 | `charge` 동시 2건(gather) | used 2(원자적) |

### 5. 추가 요청 API — `tests/api/test_quota_requests_api.py` (마커 `db`)

| ID | 요청 | 기대 |
|---|---|---|
| A-QR-01 | used 50 → `POST /api/quota/requests` | 201 `{id, day:"2026-11-21", status:"pending", message: MSG_QUOTA_REQUESTED}`, 행 1개 |
| A-QR-02 | used 10 | 409 `quota_not_exhausted` |
| A-QR-03 | 같은 날 두 번째 | 409 `quota_request_exists` |
| A-QR-04 | 동시 2건 | 201 하나, 409 하나 |
| A-QR-05 | CSRF 없음 / pending 사용자 | 403 `csrf_failed` / 403 `pending_approval` |
| A-QR-06 | 다음 날(clock +1일) used 0에서 요청 | 409 `quota_not_exhausted`(날짜별) |

### 6. 채팅 입장 검사 — `tests/api/chat/test_admission.py` (마커 `db`)

| ID | 상황 | 기대 |
|---|---|---|
| A-AD-01 | 같은 분 안 10회 POST(정상) | 모두 200 |
| A-AD-02 | 11번째 | 429 `too_many_requests`, `Retry-After` 1~60, 그래프 호출 없음, 차감 없음 |
| A-AD-03 | 61초 뒤(clock) | 다시 200 |
| A-AD-04 | used 50 | 429 `quota_exceeded`(JSON, SSE 아님), 그래프·Moderation 호출 0 |
| A-AD-05 | used 50 + 남의 세션 id | 429(한도 검사가 세션 404보다 먼저) |
| A-AD-06 | 분당 10회 초과 + used 50 | 429 `too_many_requests`(분당 제한이 먼저) |
| A-AD-07 | 없는 세션으로 POST | 404, 분당 카운터는 1 증가(`rate_limits` 키 `chat:user:<id>` count 1) |
| A-AD-08 | `GET /api/chat/sessions` 20회 | 분당 제한 없음 |

### 7. 차감 규칙 표 — `tests/api/chat/test_charge_rules.py` (마커 `db`, spec §5 전 행)

각 행: 시작 used 10, 실제 `DbTurnStore`, 가짜 그래프·Moderation·분류기.

| ID | 대본 | `daily_quota.used` | `done.quota_remaining` | `usage_events` |
|---|---|---|---|---|
| C-01 | 정상 passed (02 U-SSE-01) | 11 | 39 | answer 2·verify 1·moderation 2·classify 1, 모두 `message_id` = assistant id, `user_id` = 사용자 |
| C-02 | failed(사실 실패 소진) | 11 | 39 | answer 4·verify 3·moderation 4·classify 1 |
| C-03 | security_replaced | 11 | 39 | 기록 |
| C-04 | blocked jailbreak | 11 | 39 | moderation 1·classify 1, `message_id` NULL |
| C-05 | blocked self_harm(Moderation) | 11 | 39 | moderation 1(classify 없음) |
| C-06 | blocked unsafe | 11 | 39 | moderation 1 |
| C-07 | 입력 Moderation 장애 | 10 | (done 없음) | 0행(실패 호출은 기록 안 함) |
| C-08 | 분류기 장애 | 10 | — | moderation 1 (classify 없음) |
| C-09 | 답변 모델 장애(첫 호출) | 10 | — | moderation 1·classify 1 |
| C-10 | 출력 Moderation 장애 | 10 | — | moderation 1(입력)·classify 1·answer 2·verify 0 또는 1(가짜 순서에 따라 — 받은 만큼) |
| C-11 | 타임아웃 | 10 | — | 그때까지 받은 것 |
| C-12 | 연결 끊김(첫 delta 뒤) | 10 | — | `run_spawned()` 뒤 moderation 1·classify 1·answer(끝난 호출만) |
| C-13 | 저장 실패(세션 삭제) | 10 | — | `finish_error`로 기록 |
| C-14 | web_search 호출 포함 정상 | 11 | 39 | web_search 1행 `units 1`·`cost 0`·`tool_ms` |
| C-15 | `tour_live` 가짜 툴 호출 포함 정상 | 11 | 39 | `tour_live` 관련 usage 행 없음(kind 없음), `chat_messages.tool_results`에 `tour_live` 항목·`ms` |
| C-16 | used 49 → 성공 | 50 | 0 | — |
| C-17 | `finish_blocked` DB 오류(가짜) | 10 | `null` | 로그 클래스명만, `blocked`→`done` 순서 유지 |

### 8. 배경 사용량 — `tests/api/chat/test_background_usage.py` (마커 `db`)

| ID | 상황 | 기대 |
|---|---|---|
| A-BU-01 | 첫 턴 저장 → 제목 생성 | `usage_events` kind `title` 1행, `message_id` = 1턴 assistant id |
| A-BU-02 | 11턴째 → 요약 | kind `summary` 1행 |
| A-BU-03 | 로그 | `chat_background` 줄 없음(09에서 지움) |

### 9. 통합 (`@pytest.mark.integration`, 실 OpenAI)

| ID | 내용 | 통과 기준 |
|---|---|---|
| I-Q-01 | 실제 그래프로 같은 질문 2턴(실 DB) | `usage_events` answer·verify·classify 행 토큰 non-null, 2턴째 answer `cached_tokens > 0`(또는 프리픽스 수치 기록), `cost_usd > 0`. `input_tokens ≥ cached_tokens + cache_write_tokens`인지 출력(§7 미확인 확정) |

---

## ② HITL

전제: 11 적용 compose, active 계정, 05 H-3 셸 함수 + 09 HITL `new_session`·`ask`.

### HITL-1 한도·추가 요청
1. 남은 횟수 확인: `S=$(new_session); ask $S '경복궁 관람 시간'` → `done`의 `quota_remaining`(예: 49).
2. 한도 소진 흉내:
   ```bash
   docker compose exec postgres psql -U postgres -d nadri -c "insert into daily_quota(user_id, day, used) select id, (now() at time zone 'Asia/Seoul')::date, 50 from users where username='<아이디>' on conflict (user_id, day) do update set used=50"
   curl -s -i -X POST $B/api/chat/sessions/$S/messages -H 'Content-Type: application/json' -H "$CK" -H "X-CSRF-Token: $TK" -d '{"text":"하나 더"}' | sed -n '1p;/^retry-after/Ip;$p'
   ```
   기대: `429`, `Retry-After`(자정까지 초), 본문 `quota_exceeded`·`request_status:null`·문구 `MSG_QUOTA_EXCEEDED`.
3. 추가 요청: `curl -s -X POST $B/api/quota/requests -H "$CK" -H "X-CSRF-Token: $TK"` → 201. 다시 → 409 `quota_request_exists`. 채팅 → 429 문구 "관리자가 확인하고 있어요".
4. 승인 흉내(18 전): `update daily_quota set extra=50 …; update quota_requests set status='approved', decided_at=now() …` → 채팅 200, `quota_remaining` 49.

### HITL-2 분당 10회
```bash
for i in $(seq 1 11); do curl -s -o /dev/null -w '%{http_code} ' -X POST $B/api/chat/sessions/$S/messages -H 'Content-Type: application/json' -H "$CK" -H "X-CSRF-Token: $TK" -d '{"text":"안녕"}'; done; echo
```
기대: 앞 10개 `200`, 11번째 `429`. (한도가 10회 소모되니 HITL-1 뒤에 할 것)

### HITL-3 비용 대조 (A14 연계, 기록만)
하루 사용 뒤:
```bash
docker compose exec postgres psql -U postgres -d nadri -c "select kind, count(*), sum(input_tokens), sum(cached_tokens), sum(output_tokens), sum(cost_usd) from usage_events where created_at::date = current_date group by kind order by kind"
```
OpenAI 대시보드 같은 날 금액과 비교해 차이를 보고한다(LightRAG 인덱싱·키워드 추출은 앱 집계에 없음 — 19에서 "추정" 표기).
