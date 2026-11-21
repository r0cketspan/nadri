# 09-chat-sessions — 테스트 설계 (test)

> spec.md와 짝. 절 번호 §n은 spec.md 기준. 작성 2026-11-21. 상태: 초안 — 사용자 검토 대기.
> ① pytest(결정적 — 가짜 그래프·가짜 LLM, DB는 04 테스트 컨테이너, 마커 `db`) ② HITL(사용자가 직접). 실호출은 `@pytest.mark.integration`.

---

## ① pytest

### 0. 공통
- 실행: `cd ~/code/myAgent/backend && uv run pytest -m "not integration"` (Docker 필요). DB 없이: `-m "not integration and not db"`.
- 02 대역(`ScriptedChatModel`·`fake_verifier`·`FakeModeration`·`fake_tool`), 05 헬퍼(`app`·`client`·`client2`·`make_user`·`login`·`post`·`clock`), 04 `db_sf`, 08 대역(`FakeClassifier`·`MemoryTurnStore`)을 그대로 쓴다.
- **추가 헬퍼** (`tests/helpers/chat.py`)

| 이름 | 역할 |
|---|---|
| `make_session(db_sf, user_id, *, turns=0, title=None, summary=None)` | 세션 + `turns`개 턴(user `"질문 n"`·assistant `"답변 n"`) 직접 생성, `turn_count=turns` |
| `chat(client, session_id, text, location=None)` | CSRF 헤더 붙여 POST → SSE 본문을 02 `parse_sse`로 파싱해 반환 |
| `dump_text(db_sf)` | 앱 테이블 14개의 모든 text·text[]·jsonb 컬럼 값을 한 문자열로 이어 붙여 반환(좌표·원문 검색용) |
| `FakeBgModel(outputs)` | 제목·요약용 가짜 Runnable — 호출마다 다음 `AIMessage`(usage 포함) 반환, 받은 메시지 기록, 옵션 `raise_on_call` |
| `run_spawned()` | 08 `spawn`이 만든 태스크가 끝날 때까지 기다림(테스트 전용 — 모듈 set을 `asyncio.gather`) |

- 위치 상수: `LOC = {"lat": 37.579617, "lng": 126.977041}` → 검색 문자열 `"37.579"`, `"126.977"`, `"37.5796"`, `"126.9770"`.

---

### 1. 컨텍스트 순수 함수 — `tests/api/chat/test_context.py`

| ID | 입력 | 기대 |
|---|---|---|
| U-CTX-01 | `parse_summary("[요약 범위: 1~12턴]\n본문")` | `(12, "본문")` |
| U-CTX-02 | `parse_summary(None)`, `parse_summary("머리줄 없는 글")` | `(0, None)` |
| U-CTX-03 | `format_summary(3, "x")` → `parse_summary` | `(3, "x")` 왕복 |
| U-CTX-04 | `summary_message(12, "a</이전 대화 요약>b")` | SystemMessage, 태그 `<이전 대화 요약 범위="1~12턴">`로 시작·`</이전 대화 요약>`로 끝, 본문의 닫는 태그는 `[/이전 대화 요약` |
| U-CTX-05 | `question_message("경복궁", None)` | HumanMessage 내용 == `"경복궁"` |
| U-CTX-06 | `question_message("내 주변 박물관", Location(**LOC))` | 내용에 `[현재 위치] 위도 37.5796, 경도 126.9770` |
| U-CTX-07 | `history_messages(ctx)` (요약 있음, 최근 2턴) | `[SystemMessage(요약), Human(질문1), AI(답변1), Human(질문2), AI(답변2)]` |
| U-CTX-08 | 요약 없음 | 요약 SystemMessage 없음 |
| U-CTX-09 | `prev_turn(ctx)` 최근 턴 있음 / 없음 | 마지막 턴의 `PrevTurn` / `None` |

### 2. 컨텍스트 읽기 (마커 `db`) — `tests/api/chat/test_context_db.py`

| ID | 준비 | 기대 |
|---|---|---|
| D-CTX-01 | 남의 세션 | `load_session_context` → None |
| D-CTX-02 | 3턴, 요약 없음 | recent = 1~3턴 |
| D-CTX-03 | 15턴, 요약 `[요약 범위: 1~5턴]` | recent = 6~15턴(10개) |
| D-CTX-04 | 15턴, 요약 `1~3턴`(2턴 늦음) | recent = 4~15턴(12개) |
| D-CTX-05 | 20턴, 요약 `1~2턴`(많이 늦음) | recent = 9~20턴(12개 — `RECENT_TURNS_MAX`), 경고 로그 1줄 |
| D-CTX-06 | 15턴, 요약 형식 깨짐 | `summary_upto=0`, recent = 4~15턴(12개) |

### 3. 저장 포장 순수 함수 — `tests/api/chat/test_store_pack.py`

| ID | 입력 | 기대 |
|---|---|---|
| U-PK-01 | 툴 기록 1개(content 500자) | 항목 키 8개, `truncated: false`, content 그대로 |
| U-PK-02 | content 3,000자 1개 | 2,000자, `truncated: true` |
| U-PK-03 | 2,000자 × 6개 | 앞 5개 2,000자, 6번째 `""`·`truncated: true`, 합계 10,000 |
| U-PK-04 | 2,000자 × 4 + 1,500자 + 2,000자 | 5번째 1,500자, 6번째 500자 |
| U-PK-05 | content 3,000자 끝부분에만 contentid `999` | `contentids`에 `"999"` 있음(자르기 전 원문 기준) |
| U-PK-06 | `is_error=True` 기록 | `is_error: true`, contentids·urls 빈 목록 |
| U-PK-07 | args `{"area":"서울","near":{"lat":37.5796,"lng":126.977,"radius_km":2}}`, loc=LOC | `near` 키 없음, `area` 그대로 |
| U-PK-08 | loc=None, 같은 args (`tour_live` `{"op":"nearby","near":{…}}`) | `near` 키 없음(위치 동의 없어도 항상), `op` 그대로 |
| U-PK-08b | content `{"items":[{"contentid":"1","lat":37.6,"distance_km":0.42}],"count":1}`, loc=None | 저장 content에 `distance_km` 없음, `contentid`·`lat` 그대로, `contentids == ["1"]` |
| U-PK-08c | content가 JSON 아님(`"오류: 예산 소진"`) | 그대로 |
| U-PK-08d | args 다른 키에 좌표(`{"x": 37.5796}`), loc=LOC | `scrub_json`으로 `None` |
| U-PK-09 | `pack_verification` — rewrite_count 2, verify_status failed | attempts 3개, 0·1에 `draft`, 2에 없음, `max_rewrites` 기록 |
| U-PK-10 | verify_status `security_replaced`, rewrite_count 2 | 0·1·2 모두 `draft` |
| U-PK-11 | draft 3,000자 | 2,000자 |
| U-PK-12 | `scrub_text("현재 위치 37.5796, 126.9770 근처 1.5km", LOC)` | `"현재 위치 [위치], [위치] 근처 1.5km"` |
| U-PK-13 | `scrub_text("경복궁 37.5788, 서울역 37.5547", LOC)` | `37.5788` → `[위치]`(0.01 안), `37.5547` 그대로 |
| U-PK-14 | `scrub_text("요금 3,000원 09:00~18:00 (#126508)", LOC)` | 그대로 |
| U-PK-15 | `scrub_json({"a":[37.58,{"b":"126.977"}], "c": 5}, LOC)` | `{"a":[None,{"b":"[위치]"}], "c": 5}` |

### 4. 세션 API (마커 `db`) — `tests/api/chat/test_sessions_api.py`

| ID | 요청 | 기대 |
|---|---|---|
| A-SS-01 | 로그인 후 `POST /api/chat/sessions` | 201, `id` UUID, `title:null`, `turn_count:0` |
| A-SS-02 | CSRF 없이 POST | 403 `csrf_failed` |
| A-SS-03 | pending 사용자 | 403 `pending_approval` |
| A-SS-04 | `GET /api/chat/sessions` — 내 세션 3개(턴 2·0·5, updated_at 서로 다름) + 남의 세션 1개 | 2개만(턴 0 제외), `updated_at` 내림차순, 남의 것 없음 |
| A-SS-05 | `GET /api/chat/sessions/{id}` 2턴 세션 | messages 4개, 순서 user1·assistant1·user2·assistant2, user에 `pii_types`, assistant에 `sources`·`verify_status`·`rewrite_count`·`from_cache`·`allowed_urls`, 응답에 `summary`·`tool_results`·`verification`·`timings` 키 없음 |
| A-SS-06 | assistant content에 `[홈](https://www.royalpalace.go.kr/)` | `allowed_urls == ["https://www.royalpalace.go.kr/"]` |
| A-SS-07 | 남의 세션 GET | 404 `session_not_found`, 문구 §4.3 |
| A-SS-08 | `GET /api/chat/sessions/abc` | 404 (422 아님) |
| A-SS-09 | `DELETE` 내 세션 | 204, `chat_sessions`·`chat_messages` 행 없음 |
| A-SS-10 | `DELETE` 남의 세션 | 404, 그 세션 그대로 |
| A-SS-11 | 메시지·FAQ 캐시·피드백·채점·보안 이벤트가 달린 세션 DELETE | 메시지·`message_feedback`·`faq_cache`·`eval_scores` 삭제, `security_events.session_id` NULL로 남음 |

### 5. 메시지 엔드포인트 (마커 `db`) — `tests/api/chat/test_messages_api.py`

런타임: 02 가짜 그래프(대본 = 02 U-SSE-01 "경복궁 … (#126508)"), `FakeModeration`(깨끗), `FakeClassifier`(normal), **실제 `DbTurnStore`**, 백그라운드 모델 `FakeBgModel`.

| ID | 요청 | 기대 |
|---|---|---|
| A-MS-01 | 새 세션에 `"제 번호 010-1234-5678로 경복궁 예약"` | SSE `done{user_message_id, assistant_message_id: 정수}`; DB: user content = 가린 텍스트, `pii_types={phone}`; assistant `verify_status=passed`, `tool_results[0].name="rag_query"`, `verification.attempts` 1개, `timings` 6키; `turn_count=1`; `updated_at` 갱신 |
| A-MS-02 | 같은 흐름 `dump_text` | `1234-5678` 없음 |
| A-MS-03 | 남의 세션으로 POST | 404, 그래프 호출 0회 |
| A-MS-04 | `turn_count=50` 세션 | 409 `session_full`, SSE 아님(content-type JSON) |
| A-MS-05 | `turn_count=49` | 200, 저장 뒤 50 |
| A-MS-06 | 분류기 `jailbreak` | `blocked` → `done{blocked:true}`; `chat_messages` 0행, `turn_count` 0, `security_events` 행의 `session_id` = 세션, `message_id` NULL |
| A-MS-07 | 모델 첫 호출 예외 | `error{llm_unavailable}`; 메시지 0행 |
| A-MS-08 | 출력 Moderation 장애 | `error{guard_unavailable}`; 메시지 0행 |
| A-MS-09 | 사실 실패 소진(02 U-SSE-04 대본) | `warning` → `done{failed}`; 저장됨, assistant `verify_status=failed`, `rewrite_count=2`, `verification.attempts[0..1].draft` 있음 |
| A-MS-10 | 보안 실패 소진(02 U-SSE-05) | 저장, content = `fixed_messages().safe_replacement`, `verify_status=security_replaced`, 출력 이벤트 `message_id` = assistant id |
| A-MS-11 | 최종본에 `[예약](https://evil.kr/x?d=1)` + 사실 실패 소진(링크가 남은 채 `warning`) | 저장 content에 `evil.kr` 없음(`예약`으로 강등) |
| A-MS-12 | 첫 delta 뒤 클라이언트 연결 끊기(스트림 `aclose`) | 메시지 0행, `run_spawned()` 뒤 보안 이벤트만(있으면) |
| A-MS-13 | 응답 도중 다른 클라이언트가 세션 DELETE(가짜 모델 `delay_s`로 틈 만들기) | `error{llm_unavailable}`, 메시지 0행 |
| A-MS-14 | 같은 세션 동시 POST 2건(48턴) | 둘 다 저장, turn_no 49·50, UNIQUE 위반 없음 |
| A-MS-15 | 저장 중 DB 오류(`DbTurnStore`의 커밋을 예외로 바꾼 가짜) | `error{llm_unavailable}`, `done` 없음 |

### 6. 컨텍스트가 그래프에 들어가는지 — `tests/api/chat/test_context_flow.py` (마커 `db`)

| ID | 준비 | 기대 (가짜 답변 모델이 받은 메시지) |
|---|---|---|
| A-CF-01 | 3턴 세션에 질문 | `[System(answer.md), Human(질문1), AI(답변1), …, Human(질문3)·AI(답변3), Human(이번 질문)]` |
| A-CF-02 | 15턴 + 요약 `1~5턴` | 두 번째 메시지가 요약 SystemMessage, 그 뒤 6~15턴, 마지막 이번 질문 |
| A-CF-03 | 위치 포함 질문 | 마지막 HumanMessage에 `[현재 위치] 위도 37.5796, 경도 126.9770`; 검증 러너블 `<질문>`에는 좌표 없음; Moderation·분류기 입력에 좌표 없음 |
| A-CF-04 | 2턴 세션 | 분류기가 받은 `prev_turn` = 2턴 user·assistant |
| A-CF-05 | 저장된 assistant content가 강등본 | 다음 턴 히스토리의 AIMessage도 강등본 |

### 7. 좌표 미저장·미기록 — `tests/api/chat/test_location_privacy.py` (마커 `db`)

| ID | 대본 | 기대 |
|---|---|---|
| A-LP-01 | 위치 질문, 모델이 `data_query(near={lat:37.5796,lng:126.977})` 호출 → 답변 본문에 "현재 위치(37.5796, 126.9770) 근처" | 저장 후 `dump_text`에 LOC 검색 문자열 4개 모두 없음 |
| A-LP-02 | 같은 흐름 + 사실 실패 1회 다시 쓰기(초안에도 좌표) | `verification` draft에도 없음 |
| A-LP-03 | A-LP-01 전체 `caplog`(모든 로거, DEBUG) | 로그 전체에 LOC 검색 문자열 없음 |
| A-LP-04 | 위치 질문이 차단됨(분류기) | `security_events`에 좌표 없음(입력 excerpt는 가린 질문 — 좌표 없음 확인) |
| A-LP-05 | 위치 질문 + 출력 보안 실패(excerpt에 좌표가 든 답변) | `security_events.excerpt`에 `[위치]` |

### 8. 제목·요약 — `tests/api/chat/test_background.py` (마커 `db`)

| ID | 준비 | 기대 |
|---|---|---|
| A-BG-01 | 새 세션 첫 턴 저장, `FakeBgModel(["\"경복궁 관람 정보.\"\n둘째 줄"])` | `run_spawned()` 뒤 `title == "경복궁 관람 정보"`, `updated_at` 저장 직후 값과 같음 |
| A-BG-02 | 제목 생성 예외 | 제목 NULL, 예외 클래스명만 로그. 다음 턴 저장 뒤 다시 호출되어 생성 |
| A-BG-03 | 제목 이미 있음 | 모델 호출 0회 |
| A-BG-04 | 제목 50자 응답 | 40자 |
| A-BG-05 | 제목 모델이 받은 메시지 | System = title.md, Human에 `<첫 질문>`·`<첫 답변>`(답변 500자 이하) |
| A-BG-06 | 10턴 저장 시점 | 요약 호출 0회 |
| A-BG-07 | 11턴째 저장 | 요약 호출 1회, 입력에 `[턴 1]`만, 결과 `summary`가 `[요약 범위: 1~1턴]\n…` |
| A-BG-08 | 요약 `1~1턴` 상태에서 13턴 저장(12턴 요약 작업이 실패했었음) | 한 번에 턴 2·3을 넣어 `1~3턴` |
| A-BG-09 | 요약 결과 2,000자 | 본문 1,500자 |
| A-BG-10 | 두 요약 작업 동시 실행(같은 old 값) | 하나만 반영, 예외 없음 |
| A-BG-11 | 요약 작업 | `updated_at` 바뀌지 않음 |
| A-BG-12 | 배경 사용량 | `on_usage`가 `[UsageRecord(kind="title")]`·`[UsageRecord(kind="summary")]`와 assistant id로 호출됨; 09 로그 `chat_background` 줄에 제목·요약 글자 없음 |
| A-BG-13 | 차단 턴 | 배경 작업 없음 |
| A-BG-14 | `build_chat_model(settings, reasoning_effort="low")` | 모델 `reasoning_effort == "low"`(필드명은 langchain-openai 1.8.5 기준 — 다르면 맞춤), `None`이면 02와 같음 |

### 9. 통합 (`@pytest.mark.integration`, 실 OpenAI)

| ID | 내용 | 통과 기준 |
|---|---|---|
| I-S-01 | 실제 모델로 제목 1회·요약 1회 | 400 오류 없음, 제목 1~40자 한국어, `reasoning_effort` 값이 받아들여짐(거부되면 메시지 기록 후 §10대로 변경) |
| I-S-02 | 실제 그래프로 요약 SystemMessage가 든 대화 1회 | 400 오류 없음(앞쪽 system 2개 허용 확인). 실패 시 HumanMessage 방식으로 바꾸고 재실행 |

---

## ② HITL (사용자가 직접 실행)

전제: 09 적용 compose 기동, active 계정. 05 H-3 셸 함수(`B`·`csrf`·`cookie`·`login`) 붙여 넣고 `login …`. 아래 함수 추가:
```bash
new_session() { curl -s -X POST $B/api/chat/sessions -H "$CK" -H "X-CSRF-Token: $TK" | python3 -c 'import sys,json;print(json.load(sys.stdin)["id"])'; }
ask() {  # ask <세션id> '<질문>' [위도 경도]
  body=$(python3 -c 'import json,sys;a=sys.argv;d={"text":a[2]};
if len(a)>4: d["location"]={"lat":float(a[3]),"lng":float(a[4])}
print(json.dumps(d))' x "$2" "$3" "$4")
  curl -sN -X POST $B/api/chat/sessions/$1/messages -H 'Content-Type: application/json' -H "$CK" -H "X-CSRF-Token: $TK" -d "$body" | grep -E '^event: (meta|done|error|blocked|warning)' -A1
}
```

### HITL-1 12턴 이상 대화 — 요약이 컨텍스트에 들어가는지 (DoD 8)
1. `S=$(new_session)`.
2. 1턴째에 기억할 조건을 말한다: `ask $S '다음 주 토요일에 부모님이랑 서울 여행 가. 아버지가 무릎이 안 좋으셔서 많이 걷는 곳은 피하고 싶어.'`
3. 2~12턴: 서로 다른 관광 질문 11개(예: "경복궁 관람 시간", "근처 점심 먹을 곳", "덕수궁 야간 개장", "국립중앙박물관 휴관일", …).
4. DB 확인:
   ```bash
   docker compose exec postgres psql -U postgres -d nadri -c "select turn_count, left(summary, 200), title from chat_sessions where id='$S'"
   ```
   기대: `turn_count=12`, summary가 `[요약 범위: 1~2턴]`으로 시작하고(12 − 10) 1턴의 "부모님·무릎·많이 걷지 않기"가 들어 있음, 제목이 1턴 내용을 반영.
5. 13턴: `ask $S '처음에 내가 말한 조건 기억해? 그 조건에 맞게 오후 일정 하나 짜줘'` → 답변이 "부모님 동행·걷기 적게"를 반영하는지 눈으로 확인.
6. 결과(요약 본문 일부, 13턴 답변이 조건을 반영했는지)를 보고한다.

### HITL-2 세션 목록·삭제
1. `curl -s $B/api/chat/sessions -H "$CK"` → HITL-1 세션이 제목과 함께 맨 위. 빈 세션(`new_session`만 한 것)은 안 보임.
2. `curl -s -X DELETE $B/api/chat/sessions/$S -H "$CK" -H "X-CSRF-Token: $TK" -o /dev/null -w '%{http_code}\n'` → `204`. 다시 GET → 404.

### HITL-3 위치 (NFR-33)
1. `S=$(new_session); ask $S '내 주변 박물관 알려줘' 37.5796 126.9770`
2. 답변이 경복궁·국립고궁박물관 근처 결과인지 확인.
3. 좌표 흔적 검색:
   ```bash
   docker compose exec postgres psql -U postgres -d nadri -Atc "select count(*) from chat_messages where content like '%37.579%' or tool_results::text like '%37.579%' or verification::text like '%37.579%' or content like '%126.97%' or tool_results::text like '%126.97%'"
   docker compose logs api --since 5m | grep -c -E '37\.579|126\.97'
   ```
   기대: 둘 다 `0`.

### HITL-4 50턴 상한
```bash
docker compose exec postgres psql -U postgres -d nadri -c "update chat_sessions set turn_count=50 where id='$S'"
ask $S '하나 더 물어볼게'
```
기대: SSE가 아니라 409 JSON `session_full`과 §4.3 문구(`ask`의 grep 때문에 안 보이면 `curl -s …` 그대로 실행).

### HITL 결과 보고 (구현자 → 사용자)
- HITL-1 요약·13턴 답변 판단, HITL-3 검색 결과(0·0), I-S-01·02 결과와 §10 확인 사항(system 2개 허용·reasoning effort 값).
