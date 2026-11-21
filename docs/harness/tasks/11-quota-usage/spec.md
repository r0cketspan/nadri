# 11-quota-usage — 일일 한도·분당 제한·사용량 기록 (spec)

> 하네스 Phase 4 산출물 (spec-writer, 작성 2026-11-21). 상태: **초안 — 사용자 검토 대기**. 브랜치 `feat/11-quota-usage`, 의존 작업 09-chat-sessions(→ 08·05·04·02).
> 근거: [PL]=program_list.md(G4 승인본) §2 표·§3 "11-quota-usage"·§4 · [A]=architecture.md(G3 재승인본) §2.1 `quota`·`usage`·`ratelimit`·§3.1 2)·3)·10)·§3.6·§5.1 `daily_quota`·`quota_requests`·`usage_events`·§10·ADR-10·27 · [R]=requirements.md FR-61·62, NFR-06·40·43·60 · [PG]=PROGRESS.md G3 Q5("성공·캐시 적중 차감, 장애 미차감")·G3 재검토 Q2("입력 차단 +1, Moderation 장애 미차감").
> **이어받는 확정 spec**: [02](`UsageRecord`·`usage_from_message`) · [04](`DailyQuota`·`QuotaRequest`·`UsageEvent`·`USAGE_KINDS`·`QUOTA_REQUEST_STATUSES`·`uq_quota_requests_user_id_day`) · [05](`RateRule`·`allow`·`retry_after`·`too_many`·`ApiError`·`constraint_name`·`get_now`·`require_active`·키 `chat:user:{user_id}`) · [08](`TurnStore`·`DbTurnStore.finish_*`·`spawn`) · [09](`DbTurnStore.finish_done` 트랜잭션·`chat_turn_context`·`BackgroundDeps.on_usage`) · [10](`tour_live` — TourAPI 실시간 몫은 `LiveBudget`가 따로 셈).
> **미확인** = 문서·공식 자료로 확인하지 못한 사실.

---

## 1. 작업 목표

- 채팅 메시지 요청에 **분당 10회**(NFR-06)와 **일일 한도 50 + 승인 추가분**(FR-62)을 건다. 넘으면 SSE 시작 전 429.
- [A] §3.6 차감 규칙을 턴 결과마다 한 곳(`DbTurnStore`)에서 적용한다: 성공·캐시 적중 +1, 입력 검사 차단 +1, 장애·중단·Moderation 장애 0.
- `POST /api/quota/requests` — 그날 1건 추가 요청(승인은 18).
- 모든 LLM·외부 호출을 `usage_events`에 1행씩(종류·모델명·입력/캐시 읽기/캐시 쓰기/출력 토큰·건수·비용) 남긴다(FR-61, NFR-40·43). 단가표는 `core/pricing.py`.
- `done.quota_remaining`을 채운다.

### 1.1 넣지 않는 것
| 빠지는 것 | 들어오는 작업 |
|---|---|
| 추가 요청 승인·거절(extra += 50) API·화면 | 18 (11은 `EXTRA_STEP` 상수만 둠) |
| 사용량 대시보드·월 $10 경고 | 19 |
| 429 화면·"추가 요청" 버튼 | 16 |
| STT·TTS·허브·평가·개선안 사용량 **기록 호출** — 11은 `record_usage`·단가를 만들고, 호출은 각 작업이 함 | 17·20·24 |
| FAQ 캐시 임베딩 사용량(`embed`) 생성 | 12 (11 단가표에 임베딩 단가는 둠) |
| TourAPI 호출 수(적재·`tour_live`) | 03·10의 `ingest_state` 공유 카운터(`tourapi_calls:<날짜>`의 `ingest`·`live`). `usage_events` 종류에 TourAPI가 없고(04 `USAGE_KINDS`) 비용도 없으므로 기록하지 않는다 |

---

## 2. 생성·수정 파일

| 파일 | 신규/수정 | 역할 |
|---|---|---|
| `nadri/api/quota.py` | 신규 | 한도 계산·검사·차감, 추가 요청 서비스·라우터, 채팅 입장 검사 의존성 (§4·§5) |
| `nadri/api/usage.py` | 신규 | `UsageRecord` → `usage_events` 행(비용 포함) (§6) |
| `nadri/core/pricing.py` | 신규 | 단가표·비용 계산 (§7) |
| `nadri/api/chat/router.py` | 수정(09) | `chat_turn_context`의 사용자 의존성을 `chat_admission`으로 교체 |
| `nadri/api/chat/store.py` | 수정(09) | `finish_done`·`finish_blocked`·`finish_error`에 차감·사용량 기록, `clock` 주입 (§8) |
| `nadri/api/chat/background.py` | 수정(09) | `on_usage`를 로그 → `usage_events` 저장으로 |
| `nadri/api/main.py` | 수정 | quota 라우터 등록 |
| `nadri/api/errors.py` | 수정(05) | 한도 관련 코드·문구 (§4.4) |
| `backend/tests/...` | 신규·수정 | test.md, 앞 작업 테스트 수정(§10) |

> [PL] 파일 목록 밖: `store.py`·`background.py`·`main.py`·`errors.py` 수정 — 차감·기록 자리가 08·09가 만든 `DbTurnStore`이기 때문.

---

## 3. 설정 · 상수

새 환경변수 없음(요구사항이 정한 고정값 — 05와 같은 판단).

| 상수 | 위치 | 값 | 근거 |
|---|---|---|---|
| `DAILY_LIMIT` | `quota.py` | `50` | FR-62 |
| `EXTRA_STEP` | `quota.py` | `50` | FR-62 (18이 승인 때 사용) |
| `CHAT_RULE` | `quota.py` | `RateRule(limit=10, window=timedelta(minutes=1))` (잠금 없음) | NFR-06 |
| 레이트 키 | — | `chat:user:{user_id}` | 05 §6.5 정본 |
| `KST` | `core/tourapi.py`(01) | `ZoneInfo("Asia/Seoul")` | 재사용 |

---

## 4. 한도 (`api/quota.py`)

### 4.1 규칙
- 하루 = **KST 날짜**. 한도 = `DAILY_LIMIT + extra`, 남은 횟수 = `max(0, 한도 − used)`. 행이 없으면 used 0·extra 0.
- **검사는 요청 시작 때, 차감은 턴이 끝날 때**(답변 결과를 알아야 차감 여부가 정해짐 — [A] §3.6). 그래서 동시에 진행 중인 요청 수만큼(분당 10회 안) 한도를 넘을 수 있다 — 1~5명 규모에서 받아들임(§12 Q3). 차감 쿼리는 상한 없이 +1 한다.
- 차감 날짜 = **차감 시각**의 KST 날짜(자정 넘어 끝난 턴은 다음 날로).

### 4.2 시그니처
```python
@dataclass(frozen=True)
class QuotaStatus:
    """오늘 한도 상태."""
    day: date
    limit: int
    used: int
    remaining: int
    request_status: Literal["pending", "approved", "rejected"] | None   # 오늘 추가 요청 상태(없으면 None)

def kst_day(now: datetime) -> date:
    """tz-aware 시각의 KST 날짜. naive면 ValueError."""
def seconds_to_kst_midnight(now: datetime) -> int:
    """다음 KST 00:00까지 남은 초(올림, 최소 1) — 429 Retry-After."""
async def get_status(db: AsyncSession, user_id: int, now: datetime) -> QuotaStatus: ...
async def ensure_quota(db: AsyncSession, user_id: int, now: datetime) -> QuotaStatus:
    """남은 횟수가 0이면 ApiError(429, quota_exceeded) — §4.4 문구·extra 필드·Retry-After."""
async def charge(db: AsyncSession, user_id: int, now: datetime) -> int:
    """used +1 (upsert) 후 남은 횟수를 돌려준다. 커밋은 호출자."""
async def create_request(db: AsyncSession, user_id: int, now: datetime) -> QuotaRequest:
    """오늘 추가 요청 1건. 남은 횟수가 있으면 409 quota_not_exhausted, 이미 있으면 409 quota_request_exists. 커밋까지."""
async def chat_admission(cu: CurrentUser = Depends(require_active), db: AsyncSession = Depends(get_db),
                         now: datetime = Depends(get_now)) -> CurrentUser:
    """채팅 메시지 입장 검사: ① 분당 10회(allow → 커밋, 거부면 429 too_many_requests) ② ensure_quota."""
```
`charge` SQL:
```sql
INSERT INTO daily_quota (user_id, day, used) VALUES (:uid, :day, 1)
ON CONFLICT (user_id, day) DO UPDATE SET used = daily_quota.used + 1
RETURNING used, extra
```

### 4.3 채팅 엔드포인트 순서 ([A] §3.1 1)~4))
1. (05) 쿠키·CSRF·active
2. **분당 10회** → 429 `too_many_requests` (05 `too_many`, `Retry-After`) — 시도마다 셈(한도 초과·404·409 요청도 1회로 셈)
3. **일일 한도** → 429 `quota_exceeded`
4. (09) 세션 소유 404 → 50턴 409

구현: 09 `chat_turn_context`의 `cu: CurrentUser = Depends(require_active)`를 **`Depends(chat_admission)`** 으로 바꾼다(의존성 사슬로 순서 보장). 세션 CRUD·추가 요청에는 분당 제한을 걸지 않는다.

### 4.4 API·사용자 문구
| 메서드·경로 | 인증 | 요청 | 성공 | 실패 |
|---|---|---|---|---|
| `POST /api/quota/requests` | active, CSRF | 본문 없음 | 201 `{"id", "day": "YYYY-MM-DD", "status": "pending", "message": MSG_QUOTA_REQUESTED}` | 409 `quota_not_exhausted` / 409 `quota_request_exists` |

| code | HTTP | 상수 | 문구 |
|---|---|---|---|
| `quota_exceeded`(요청 없음) | 429 | `MSG_QUOTA_EXCEEDED` | 오늘 질문 {limit}회를 모두 썼어요. 더 필요하면 '추가 요청'을 눌러 관리자에게 요청해 주세요. |
| `quota_exceeded`(요청 대기 중) | 429 | `MSG_QUOTA_PENDING` | 추가 요청을 관리자가 확인하고 있어요. 승인되면 바로 이어서 쓸 수 있어요. |
| `quota_exceeded`(요청 승인·거절됨) | 429 | `MSG_QUOTA_DONE_TODAY` | 오늘은 더 질문할 수 없어요. 내일 0시(한국 시간)에 다시 50회가 채워져요. |
| `quota_not_exhausted` | 409 | `MSG_QUOTA_NOT_EXHAUSTED` | 아직 오늘 질문이 남아 있어요. 다 쓴 뒤에 요청해 주세요. |
| `quota_request_exists` | 409 | `MSG_QUOTA_REQUEST_EXISTS` | 오늘은 이미 추가 요청을 보냈어요. |
| (성공) | 201 | `MSG_QUOTA_REQUESTED` | 추가 요청을 보냈어요. 관리자가 승인하면 오늘 50회를 더 쓸 수 있어요. |

- `quota_exceeded` 본문: `{"code","message","limit","used","request_status"}` + `Retry-After: 다음 KST 자정까지 초`. 16 화면은 `request_status`가 `null`일 때만 "추가 요청" 버튼, `pending`이면 "요청 대기 중" 표시.
- `quota_request_exists`: 먼저 `SELECT`로 확인하고, 동시 요청 경합은 `IntegrityError` → `constraint_name == "uq_quota_requests_user_id_day"`로 같은 409(05 헬퍼).

---

## 5. 차감 규칙 (정본 표 — [A] §3.6, ADR-27, G3 Q5·재검토 Q2)

| 턴 결과 | 한도 | 대화 저장(09) | `usage_events` | `done.quota_remaining` |
|---|---|---|---|---|
| `done` passed·failed·security_replaced | **+1** | 저장 | 기록(`message_id` = assistant) | 차감 후 남은 횟수 |
| `done` cached (12 FAQ 적중) | **+1** | 저장 | 기록(classify·moderation·embed) | 〃 |
| `blocked` unsafe·self_harm·jailbreak·injection·off_topic | **+1** | 안 함 | 기록(`message_id` NULL) | 〃 |
| `error` guard_unavailable(Moderation 장애) | 0 | 안 함 | 기록(`message_id` NULL) | — (`done` 없음) |
| `error` llm_unavailable(분류기·답변·검증·MCP·저장 실패) | 0 | 안 함 | 기록 | — |
| `error` timeout | 0 | 안 함 | 기록 | — |
| 연결 끊김 | 0 | 안 함 | 기록(`spawn`) | — |
| 429·409·404·422·401·403 (SSE 전) | 0 | — | 없음(호출 없음) | — |

- 장애 턴도 **사용량은 기록**한다: 이미 부른 LLM 비용은 실제로 나갔고(FR-61), 한도 차감과 비용 기록은 다른 일이다(§12 Q2).
- `tour_live` 호출이 섞인 턴도 같은 규칙. `tour_live`의 TourAPI 호출은 10의 `LiveBudget`(실시간 몫 200)이 세며 `usage_events`에는 없다. 툴 소요 시간은 09 `tool_results[].ms`에 남는다.

---

## 6. 사용량 기록 (`api/usage.py`)

```python
def usage_row(record: UsageRecord, *, user_id: int | None, message_id: int | None) -> dict:
    """UsageRecord 1건을 usage_events 행 값으로 바꾼다(순수 함수, 비용 포함)."""
async def record_usage(db: AsyncSession, records: Sequence[UsageRecord], *, user_id: int | None,
                       message_id: int | None) -> None:
    """usage_events에 add_all. 빈 목록이면 아무것도 안 함. 커밋은 호출자."""
```
| `usage_events` 컬럼 | 값 |
|---|---|
| kind·model | `record.kind`·`record.model` (응답 모델명, 없으면 NULL) |
| input_tokens·cached_tokens·cache_write_tokens·output_tokens | 그대로 — **NULL은 NULL**(0으로 꾸미지 않음, 02 §12.1·A19) |
| units | `record.units` (moderation·web_search 건수 1, stt 초, tts 글자 — 17) |
| cost_usd | `pricing.cost_usd(record)` |
| total_ms | `record.ms` (그 호출 소요) |
| tool_ms | kind = `web_search`이면 `record.ms`, 아니면 NULL |
| ttft_ms | NULL — 턴 단위 첫 토큰 지연은 `chat_messages.timings.ttft_ms`(09)에 있다(§12 Q4) |
| user_id | 사용자(배치·시스템 호출은 NULL — 20·24) |
| message_id | 저장된 턴이면 assistant 메시지 id, 아니면 NULL |

- `UsageRecord.kind` Literal은 04 `USAGE_KINDS`의 부분집합이어야 한다(테스트로 대조).
- 사용량 수집 위치는 02 A19 판정(스트리밍 `usage_metadata` 또는 `updates` 완성 메시지)을 따른다 — 11은 받은 `UsageRecord`를 저장만 한다.

---

## 7. 단가표 (`core/pricing.py`)

```python
@dataclass(frozen=True)
class LlmPrice:
    """LLM 1M 토큰당 USD."""
    input: Decimal; cached: Decimal; cache_write: Decimal; output: Decimal

LLM_PRICES: dict[str, LlmPrice] = {
    "gpt-6-luna": LlmPrice(Decimal("0.10"), Decimal("0.01"), Decimal("0.125"), Decimal("0.50")),
}
EMBED_PRICES: dict[str, Decimal] = {"text-embedding-3-small": Decimal("0.02")}   # 1M 토큰당
STT_PRICE_PER_MIN: dict[str, Decimal] = {"gpt-transcribe": Decimal("0.0045")}
LLM_KINDS = frozenset({"answer", "verify", "classify", "title", "summary", "hub", "eval", "proposal"})
FREE_KINDS = frozenset({"moderation", "web_search", "tts"})
COST_QUANT = Decimal("0.00000001")

def find_price(table: Mapping[str, T], model: str | None) -> T | None:
    """모델명이 키와 같거나 '키-'로 시작하면(날짜 붙은 응답 모델명, 예: gpt-6-luna-2026-…) 그 단가. 가장 긴 키 우선."""
def llm_cost(price: LlmPrice, *, input_tokens: int | None, cached_tokens: int | None,
             cache_write_tokens: int | None, output_tokens: int | None) -> Decimal:
    """((입력 − 캐시 읽기 − 캐시 쓰기)×input + 캐시 읽기×cached + 캐시 쓰기×cache_write + 출력×output) / 1M.
    None은 0으로 계산, 캐시 안 된 입력이 음수면 0."""
def cost_usd(record: UsageRecord) -> Decimal:
    """kind별 비용(아래 표), COST_QUANT로 반올림. 단가를 모르는 모델이면 0 + WARNING 로그 1줄(모델명만)."""
```
| kind | 계산 |
|---|---|
| answer·verify·classify·title·summary·hub·eval·proposal | `llm_cost` |
| embed | `input_tokens × EMBED_PRICES / 1M` |
| stt | `units(초) / 60 × STT_PRICE_PER_MIN` |
| moderation | 0 (무료 [A] §12.1) |
| web_search | 0 — 월 1,000크레딧 무료 안(A28), `units`로 크레딧 수만 셈 |
| tts | 0 — ElevenLabs 플랜 요금(사용량은 `units` 글자 수) |

- 단가 근거: [PL] 11·[A] §10·[S F3](gpt-6-luna 입력 0.10·캐시 0.01·캐시 쓰기 0.125(1.25배)·출력 0.50 /1M), 임베딩 0.02, STT $0.0045/분.
- **미확인**: `usage_metadata.input_tokens`가 캐시 읽기·캐시 쓰기 토큰을 **포함한 합계**인지(OpenAI는 cached_tokens를 input_tokens에 포함해 보고하는 것으로 알려짐, 캐시 쓰기는 미확인). 위 식은 "포함"을 가정한다. I-Q-01에서 실제 응답으로 확인하고 다르면 식만 고친다(§11).
- 출력 토큰에 추론 토큰이 포함되는지(포함으로 알려짐, **미확인**) — 포함이면 위 식 그대로.

---

## 8. 저장소 연결 (`api/chat/store.py`, `background.py`)

```python
class DbTurnStore:
    def __init__(self, sf, *, after_turn=None, clock: Callable[[], datetime] = lambda: datetime.now(UTC)) -> None: ...
```
| 메서드 | 08·09 동작에 더하는 것 (같은 트랜잭션) | 반환 |
|---|---|---|
| `finish_done` | 09 저장 5) 뒤: `remaining = charge(db, user_id, clock())`, `record_usage(db, usage, user_id, message_id=assistant_id)` | `DoneIds(…, quota_remaining=remaining)` |
| `finish_blocked` | 이벤트 + `record_usage(…, message_id=None)` + `charge` | `remaining` |
| `finish_error` | 이벤트 + `record_usage(…, message_id=None)` (차감 없음) | None |

- `finish_blocked`가 DB 오류로 실패하면 08 규칙대로 로그만 남기고 `blocked`→`done`은 그대로 보낸다(`quota_remaining: null`) — 차감 1회가 빠질 수 있음(드문 장애, 받아들임).
- `finish_done`의 차감·사용량은 턴 저장과 **같은 트랜잭션**이라 저장이 실패하면 차감도 안 된다(09 Q7 — 미저장·미차감).
- 09 `BackgroundDeps.on_usage` = `record_usage_tx(sf)`: 새 세션에서 `record_usage(…, user_id, message_id)` 후 커밋(제목·요약). 09의 `chat_background` 로그 줄은 지운다(사용량은 DB에).

---

## 9. 엣지케이스

| 상황 | 동작 |
|---|---|
| 오늘 used 49 → 질문 성공 | 50, `quota_remaining: 0` |
| used 50, extra 0 | 429 `quota_exceeded`, `request_status: null`, 그래프 호출 없음 |
| used 50 + 추가 요청 pending | 429, 문구 `MSG_QUOTA_PENDING` |
| 승인(extra 50) 후 used 50 | 통과(남은 50) |
| used 100, extra 50, 승인됨 | 429 `MSG_QUOTA_DONE_TODAY` |
| 같은 분 11번째 요청 | 429 `too_many_requests`(`Retry-After` ≤ 60) — 한도 검사 전 |
| 분당 10회 + 한도 초과 동시 | 분당 제한이 먼저(429 too_many_requests) |
| KST 23:59:59 검사, 00:00:01 끝남 | 다음 날 행에 +1 |
| UTC 15:00 = KST 자정 | `kst_day`가 다음 날 |
| 동시 요청 2건, used 49 | 둘 다 통과 → 51(초과 1 허용, Q3) |
| Moderation 장애 | 차감 0. 실패한 Moderation 호출은 `UsageRecord`를 만들지 않는다(성공한 호출만 기록 — 08 `screen_input`·02 verify 규칙). 그 전에 성공한 호출(예: 출력 단계 앞의 입력 Moderation·classify·answer)은 기록 |
| 응답 모델명이 `gpt-6-luna-2026-11-01` | `gpt-6-luna` 단가 |
| 모르는 모델명 | 비용 0 + WARNING |
| 토큰 None | 컬럼 NULL, 비용은 0으로 계산 |
| 추가 요청: 한도 남음 | 409 `quota_not_exhausted` |
| 추가 요청 2번째 | 409 `quota_request_exists` |
| 추가 요청 동시 2건 | 하나 201, 하나 409(UNIQUE) |

---

## 10. 앞 작업 테스트 수정

| # | 대상 | 이유 | 처리 |
|---|---|---|---|
| 1 | 09 test §5·§6·§7·§8 중 한 테스트에서 **11번 이상** 메시지를 보내는 것(A-BG-07·08 등 — 11턴 이상) | 분당 10회 | 05 `clock` 픽스처로 질문마다 `clock.advance(seconds=7)`(10번에 70초) — 헬퍼 `chat()`에 `advance_s=7` 기본값 추가. 기대값 불변 |
| 2 | 09 A-MS·08 A-GD (실 `DbTurnStore`) | `done.quota_remaining`이 정수로 바뀜, `daily_quota`·`usage_events` 행이 생김 | `quota_remaining`을 비교하는 기대는 `null` → 정수(예: 첫 성공 49). 행 수를 세는 테스트가 없으므로 그 밖 불변 |
| 3 | 08 `MemoryTurnStore` | 반환 그대로(None) | 수정 없음 — 02·08 스냅샷의 `quota_remaining: null` 유지 |
| 4 | 09 A-BG-12 | 사용량이 로그가 아니라 DB | 기대를 "`usage_events`에 kind title·summary 행, `message_id` = assistant id"로 변경 |
| 5 | 09 테스트의 DB 오버라이드(`chat_turn_context`) | 사용자 의존성이 `chat_admission`으로 바뀜 | DB 없는 02 API 테스트는 `chat_turn_context`를 통째로 덮어쓰므로 수정 없음 |

상위 문서와의 차이(구현 판단):
1. **장애 턴도 사용량 기록**(차감은 안 함) — [A] §3.1 10)은 성공 턴 기록만 적었지만 FR-61(비용 기록)을 따름(Q2).
2. **검사 시작·차감 끝** 사이 경합으로 한도 소폭 초과 허용(Q3).
3. **추가 요청은 한도를 다 쓴 뒤에만**(Q1).
4. `usage_events.ttft_ms` 비움(Q4).
5. web_search·tts 비용 0(무료 크레딧·플랜) — 수량은 `units`.

---

## 11. 가정 판정

| ID | 확인 방법 | 통과 기준 | 실패 시 |
|---|---|---|---|
| **A19**(사용량 수집 위치·캐시 토큰) | 02 §13 결과 이어받기 + I-Q-01: 실제 답변 1턴 뒤 `usage_events`의 answer·verify·classify 행 | 토큰 컬럼 non-null, 두 번째 같은 질문에서 answer `cached_tokens > 0`(프리픽스 1,024토큰 미만이면 "해당 없음") | 02 대안 그대로. 단가 식(§7)의 "입력 합계에 캐시 포함" 가정이 틀리면 `llm_cost`만 수정 |
| 비용 대조 | HITL-3: 하루 사용 뒤 `usage_events` 합계 vs OpenAI 대시보드 | 차이 기록만(LightRAG 내부 호출은 앱 집계 불가 — A14, 19) | — |

---

## 12. 완료 기준 (DoD)

1. test.md ① 전부 통과, §10 앞 작업 테스트 수정 후 통과.
2. 한도 경계(49→50, 50+추가분), KST 날짜 경계, 차감 규칙 표(§5) 전 행, 비용 계산(캐시 쓰기 1.25배), 분당 10회 테스트 통과.
3. `done.quota_remaining`이 실제 남은 횟수.
4. HITL-1·2 결과 보고, §11 결과 기록.
5. 모든 함수·클래스 한국어 docstring, 단계 주석. 커밋 `feat/11-quota-usage`, `[Feat] …` + `Author:`, AI 공동작성 표기 없음. `dev` 병합은 G5 후. `PROGRESS.md` 갱신.

---

## 13. 확인 질문

| # | 질문 | 추천안 | 대안 |
|---|---|---|---|
| Q1 | 추가 요청을 언제 받을까 | **결정(2026-11-21): 추천안대로** — **오늘 한도를 다 썼을 때만**(남아 있으면 409) — 버튼이 429 때만 보이는 FR-62와 같은 뜻, 미리 요청해 두는 것 방지 | 아무 때나 받음 |
| Q2 | 장애로 끝난 턴(미차감)의 LLM 비용을 `usage_events`에 남길까 | **결정(2026-11-21): 추천안대로** — **남긴다**(실제 나간 비용 — FR-61·19 대시보드 정확도) | 성공·차단 턴만 기록([A] §3.1 10) 문자 그대로) |
| Q3 | 동시 요청으로 한도를 1~2회 넘는 경합 | **결정(2026-11-21): 추천안대로** — **허용**(검사는 시작, 차감은 끝 — 1~5명·분당 10회) | 시작 때 미리 1회 예약하고 실패·장애면 되돌림(코드 복잡) |
| Q4 | `usage_events.ttft_ms` | **결정(2026-11-21): 추천안대로** — **비움**(턴 지연은 `chat_messages.timings`) | answer 첫 행에 턴 `ttft_ms`를 복사 |
| Q5 | 한도 초과 문구 3종(§4.4) | **결정(2026-11-21): 추천안대로** — **표 그대로** | 사용자가 수정 |
| Q6 | Tavily `web_search` 비용 | **결정(2026-11-21): 추천안대로** — **0으로 두고 `units`(크레딧)만 셈**(월 1,000 무료 안 — A28). 유료 단가는 **미확인** | 유료 단가를 넣어 "무료가 아니었다면"의 비용 표시 |
