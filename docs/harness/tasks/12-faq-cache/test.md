# 12-faq-cache — 테스트 설계 (test)

> spec.md와 짝. 절 번호 §n은 spec.md 기준. 작성 2026-11-21. 상태: 초안 — 사용자 검토 대기.
> ① pytest(결정적 — 가짜 임베딩, DB는 04 테스트 컨테이너(pgvector 포함) 마커 `db`) ② HITL. 실호출은 `@pytest.mark.integration`.

---

## ① pytest

### 0. 공통
- 실행: `cd ~/code/myAgent/backend && uv run pytest -m "not integration"` (Docker 필요).
- 02·08·09·11 대역·헬퍼 재사용. 추가:

| 이름 | 역할 |
|---|---|
| `unit_vec(i, j=None, cos=None)` | 1536차원 벡터. `unit_vec(0)` = e0. `unit_vec(0, 1, cos=c)` = `c·e0 + √(1−c²)·e1`(e0과 코사인 c) |
| `FakeEmbed(vectors \| exc)` | `ChatRuntime.embed` 대역. 호출마다 다음 벡터와 `UsageRecord(kind="embed", input_tokens=12)` 또는 예외. 받은 텍스트 기록. 옵션 `delay_s` |
| `make_faq(db_sf, *, source_message_id, embedding, answer="경복궁은 09:00~18:00 (#126508)", contentids=["126508"], sources=[tour 126508])` | 캐시 행 직접 생성 |
| `make_tour(db_sf, contentid, *, detail=True, deleted=False)` | `tour_items` 행(상세 완료 여부·삭제 여부) |

### 1. 순수 함수 — `tests/api/test_faq_pure.py`

| ID | 입력 | 기대 |
|---|---|---|
| U-FQ-01 | `is_hit(0.95, 0.95)` / `(0.9499, 0.95)` / `(1.0, 0.95)` | True / False / True |
| U-FQ-02 | `should_lookup(TurnInput(turn_count=0, location=None))` | True |
| U-FQ-03 | `turn_count=1` | False |
| U-FQ-04 | `turn_count=0`, location 있음 | False |
| U-FQ-05 | `NO_CACHE_TOOLS` | `{"web_search","get_datetime","tour_live"}` |

**저장 조건 표** — `cache_candidate(turn, turn_no, has_location)`, 기본 turn = passed·tool_records [rag_query]·sources [tour 126508]·embedding 있음·from_cache False

| ID | 바꾼 것 | 기대 |
|---|---|---|
| U-CC-01 | (기본) turn_no 1 | 후보(question = 가린 텍스트, contentids ["126508"]) |
| U-CC-02 | turn_no 2 | None |
| U-CC-03 | has_location True | None |
| U-CC-04 | verify_status `failed` / `security_replaced` / `cached` | None |
| U-CC-05 | from_cache True | None |
| U-CC-06 | question_embedding None | None |
| U-CC-07 | tool_records에 `web_search` 추가 | None |
| U-CC-08 | `get_datetime` 추가 | None |
| U-CC-09 | `tour_live` 추가 | None |
| U-CC-10 | `tour_live`가 `is_error=True`(오류 기록) | None |
| U-CC-11 | sources `[]` | None |
| U-CC-12 | sources web 항목만 | None |
| U-CC-13 | sources tour 2개(126508, 2) | 후보, contentids ["126508","2"] 등장 순 |
| U-CC-14 | rewrite_count 1, passed | 후보 |

### 2. 임베딩 — `tests/api/test_faq_embed.py`

| ID | 입력 | 기대 |
|---|---|---|
| U-EM-01 | `build_embeddings(settings)` | `model == "text-embedding-3-small"`, `max_retries == 0` |
| U-EM-02 | 가짜 `OpenAIEmbeddings.aembed_query`가 1536차원 반환 | `(vec, UsageRecord(kind="embed", model="text-embedding-3-small", input_tokens = tiktoken 수))` |
| U-EM-03 | 1535차원 반환 | `EmbedUnavailable` |
| U-EM-04 | `delay_s` > `timeout_s` | `EmbedUnavailable` |
| U-EM-05 | API 예외 | `EmbedUnavailable`, 로그에 텍스트 없음 |

### 3. 조회·저장·무효화 DB — `tests/api/test_faq_db.py` (마커 `db`)

| ID | 준비 | 기대 |
|---|---|---|
| D-FQ-01 | 캐시 비어 있음 | `lookup` → None |
| D-FQ-02 | 행 e0, 질의 `unit_vec(0,1,cos=0.951)` | 적중, similarity ≈ 0.951 |
| D-FQ-03 | 질의 cos 0.949 | None |
| D-FQ-04 | 행 2개(cos 0.96, 0.99) | 0.99 쪽 |
| D-FQ-05 | `save` 같은 source_message_id 2번 | 두 번째 None, 행 1개 |
| D-FQ-06 | 행 A contentids [1,2], B [3], C [] | `invalidate_by_contentids(["2","9"])` → 1, A만 삭제 |
| D-FQ-07 | `invalidate_by_contentids([])` | 0, 쿼리 없음 |
| D-FQ-08 | A를 가리키는 메시지 있음 → A 무효화 | 메시지 남고 `faq_cache_id` NULL |

### 4. 적중 흐름 스냅샷 — `tests/api/chat/test_faq_stream.py`

`MemoryTurnStore(hits=[FaqHit(id=7, answer="경복궁은 09:00~18:00 운영해요 (#126508)\n[홈](https://www.royalpalace.go.kr/)", sources=[tour 126508], …)])`, `FakeEmbed([e0])`, `turn_count=0`.

| ID | 상황 | 기대 이벤트 열 |
|---|---|---|
| U-FS-01 적중 | — | `meta` → `status checking` → `status answering` → `delta`(= 캐시 답변 전체, 1개) → `draft_done` → `verified` → `done{cached:true, verify_status:"cached", rewrite_count:0, sources:[126508], allowed_urls:["https://www.royalpalace.go.kr/"], blocked:false}`. 답변 모델·검증·출력 Moderation 호출 0회. `tool`·`status verifying` 없음 |
| U-FS-02 | 적중 store 호출 | `finish_done` turn: `from_cache=True`, `faq_cache_id=7`, `verify_status="cached"`, usage에 embed 1·moderation 1·classify 1 |
| U-FS-03 미적중 | hits 비어 있음 | 평소 그래프 흐름(02 U-SSE-01 + meta), `CompletedTurn.question_embedding == e0` |
| U-FS-04 임베딩 실패 | `FakeEmbed(exc)` | 평소 흐름, usage에 embed 없음, `question_embedding None` |
| U-FS-05 조회 예외 | store `faq_lookup` 예외 | 평소 흐름, 로그 클래스명만 |
| U-FS-06 두 번째 질문 | `turn_count=1` | 임베딩 호출 0회 |
| U-FS-07 위치 | location 있음 | 임베딩 호출 0회 |
| U-FS-08 입력 차단 | 분류기 `jailbreak` | 임베딩 호출 0회 |
| U-FS-09 가린 텍스트 | 질문 `"010-1234-5678 경복궁"` | `FakeEmbed`가 받은 텍스트 = `"010-****-**** 경복궁"` |
| U-FS-10 캐시 끔 | `runtime.embed=None` | 임베딩·조회 없음 |
| U-FS-11 로그 | U-FS-01 | `chat_turn` 로그 `cached: true` |

### 5. 저장소·한도 DB — `tests/api/chat/test_faq_store.py` (마커 `db`)

실제 `DbTurnStore`, 가짜 그래프, `FakeEmbed`.

| ID | 상황 | 기대 |
|---|---|---|
| A-FC-01 | 세션 A 첫 질문(미적중, rag_query, 126508 인용, passed), `make_tour(126508)` | `run_spawned()` 뒤 `faq_cache` 1행: question = 가린 텍스트, answer = 저장 content, contentids `{126508}`, source_message_id = assistant id |
| A-FC-02 | 이어서 새 세션 B 첫 질문, `FakeEmbed`가 cos 0.99 벡터 | 적중: B의 assistant `from_cache=true`, `faq_cache_id`=A 캐시 id, `verify_status=cached`, `tool_results` NULL; `hit_count=1`; `daily_quota.used` +1; 캐시 행 추가 없음 |
| A-FC-03 | A-FC-01인데 126508이 껍데기(`detail=False`) | 캐시 0행 |
| A-FC-04 | 삭제된 행(`deleted=True`) 인용 | 캐시 0행 |
| A-FC-05 | 첫 질문 + `get_datetime` 호출 | 캐시 0행 |
| A-FC-06 | 둘째 질문(passed, 조건 충족) | 캐시 0행 |
| A-FC-07 | 적중 직후(저장 전) 캐시 행 삭제(가짜 `faq_lookup`가 지운 행 id를 돌려줌) | 저장 성공, `from_cache=true`, `faq_cache_id NULL` |
| A-FC-08 | 캐시 원 세션 A 삭제 | 캐시 행 연쇄 삭제, B 메시지 `faq_cache_id` NULL |
| A-FC-09 | 캐시 저장 중 DB 오류 | 로그만, 답변·턴 저장은 이미 끝남 |
| A-FC-10 | 적중 턴 `usage_events` | embed 1행(`cost_usd` = 토큰×0.02/1M), answer·verify 없음 |

### 6. 통합 (`@pytest.mark.integration`)

| ID | 내용 | 통과 기준 |
|---|---|---|
| I-F-01 | 실제 `OpenAIEmbeddings`로 "경복궁 관람 시간 알려줘" / "경복궁 몇 시에 열어?" / "제주 맛집" | 차원 1536, 앞 두 문장 유사도 값 출력(0.95 넘는지 기록 — 22 임계값 판단 재료), 셋째와는 낮음. tiktoken 토큰 수 출력 |
| I-F-02 | `OpenAIEmbeddings`가 사용량을 돌려주는지 | 돌려주면 §4.1을 그 값으로 바꾸는 것을 기록 |

---

## ② HITL

전제: 12 적용 compose, 01·03 적재 데이터(경복궁 상세 수집 완료), active 계정, 09 HITL 셸 함수.

### HITL-1 같은 질문 두 세션
1. `S1=$(new_session); ask $S1 '경복궁 관람 시간과 휴무일 알려줘'` → 정상 답변(`cached:false`). 몇 초 뒤:
   ```bash
   docker compose exec postgres psql -U postgres -d nadri -c "select id, left(question,40), contentids, hit_count from faq_cache order by id desc limit 3"
   ```
   기대: 1행(답변이 rag_query/data_query만 쓰고 `(#contentid)`를 인용했을 때). 안 생겼으면 그 턴의 `tool_results` 툴 이름·`verify_status`를 확인해 조건(§5.1) 중 무엇에 걸렸는지 기록.
2. `S2=$(new_session); ask $S2 '경복궁 관람 시간과 휴무일 알려줘'` → `done`에 `"cached":true`, 응답이 바로 옴. `hit_count` 1.
3. `S3=$(new_session); ask $S3 '경복궁 몇 시에 열고 언제 쉬어?'` → 적중 여부와 (로그에 없으므로) 결과만 기록 — 0.95 임계값이 말 바꾼 질문을 잡는지 감 잡기(22 입력).
4. `ask $S2 '거기 주차는?'` → 두 번째 질문이라 캐시 안 씀(`cached:false`).

### HITL-2 무효화 수동 확인 (21 전)
```bash
docker compose exec api python - <<'PY'
import asyncio
from nadri.core.config import get_settings
from nadri.core.db import create_engine, session_factory
from nadri.api.faq_cache import invalidate_by_contentids
async def main():
    sf = session_factory(create_engine(get_settings()))
    async with sf() as db:
        n = await invalidate_by_contentids(db, ["<HITL-1의 contentid>"]); await db.commit(); print("deleted", n)
asyncio.run(main())
PY
```
기대: `deleted 1`, 이후 S2 이력 조회는 그대로(`from_cache` true 유지), 새 세션에서 같은 질문은 다시 미적중.

### HITL 결과 보고
- HITL-1 적중 여부·응답 시간 체감, HITL-1-3(말 바꾼 질문) 결과, I-F-01 유사도 값 → 22에 넘길 임계값 메모.
