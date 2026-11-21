# 12-faq-cache — FAQ 유사도 캐시 (spec)

> 하네스 Phase 4 산출물 (spec-writer, 작성 2026-11-21). 상태: **초안 — 사용자 검토 대기**. 브랜치 `feat/12-faq-cache`, 의존 작업 11-quota-usage(→ 09·08·04·02).
> 근거: [PL]=program_list.md(G4 승인본) §2 표·§3 "12-faq-cache"·§1.2(13·21이 사용) · [A]=architecture.md(G3 재승인본) §2.1 `faq_cache`·§3.1 6)·11)·§3.3 6)·§3.9·§4(임베딩 실패 → 캐시 건너뜀)·§5.1 `faq_cache`·ADR-11·13·16 · [R]=requirements.md FR-60·92·103, NFR-31·32·35 · [PG]=PROGRESS.md G3 Q5(캐시 적중도 +1).
> **이어받는 확정 spec**: [02](SSE 이벤트·`extract_urls`·`build_chat_model`) · [03](껍데기 행 = `detail_synced_at IS NULL`, 03-Q6 "껍데기 행도 검색에 보임") · [04](`FaqCache`·`EMBEDDING_DIM=1536`·`uq_faq_cache_source_message_id`·`fk_chat_messages_faq_cache_id` SET NULL) · [08](`TurnInput`·`TurnStore`·`CompletedTurn`·`chat_event_stream` 순서·`spawn`) · [09](`DbTurnStore.finish_done` 트랜잭션·`AfterTurnJob`·`run_after_turn`·`TurnInput.turn_count`·`location`) · [10](`tour_live` 툴 이름) · [11](`UsageRecord(kind="embed")` 저장·`EMBED_PRICES`·차감 규칙 "cached +1").
> **미확인** = 문서·공식 자료로 확인하지 못한 사실.

---

## 1. 작업 목표

세션 **첫 질문**이고 **위치가 없으면** 가린 질문을 임베딩해 이전에 **검증 통과한** 답변 중 코사인 유사도 0.95 이상을 찾아 그대로 보여 준다(그래프·검증 없이). 못 찾으면 평소대로 답하고, 조건을 만족한 답변은 저장 뒤 캐시에 넣는다 [PL §3], ADR-13.

- 적중 흐름: `meta → status checking → (입력 검사 통과) → status answering → delta(캐시 답변) → draft_done → verified → done{cached:true, verify_status:"cached"}` — 한도 +1(11 표), 대화에 `from_cache=true`·`faq_cache_id`·`verify_status=cached`로 저장.
- 저장 조건(ADR-13): 첫 질문 && 위치 없음 && `verify_status=passed` && 툴 기록에 `web_search`·`get_datetime`·`tour_live` 없음 && 답변이 인용한 관광 contentid ≥ 1 (+ §5.2 추가 조건).
- 무효화 함수 `invalidate_by_contentids()` — 21(매일 현행화)이 바뀐·삭제된 contentid로 부른다(FR-60 "기준일이 바뀌면 무효화").
- 임베딩·조회 실패 → 캐시를 건너뛰고 정상 진행([A] §4).

### 1.1 넣지 않는 것
| 빠지는 것 | 들어오는 작업 |
|---|---|
| 👎 받은 답변의 캐시 삭제 | 13 (`faq_cache` 중 `source_message_id = id` 또는 그 메시지의 `faq_cache_id` 행 삭제 — [A] §3.9) |
| 현행화에서 무효화 호출 | 21 |
| 임계값 조정 | 22 평가 결과로(설정값만 변경) |
| 벡터 인덱스(HNSW) | 넣지 않음 — 1~5명 규모, 전체 비교로 충분(04 §1.1). 행이 수천 개를 넘으면 그때 추가 |
| 캐시 만료 시간(TTL) | 없음 — 원 메시지가 90일 뒤 지워지면 연쇄 삭제(04 FK, 21) |

---

## 2. 생성·수정 파일

| 파일 | 신규/수정 | 역할 |
|---|---|---|
| `nadri/api/faq_cache.py` | 신규 | 조회 조건·조회·저장 조건·저장·무효화·임베딩 호출 (§4·§5·§6) |
| `nadri/core/llm.py` | 수정 | `EMBED_MODEL`, `build_embeddings(settings)` (§4.1) |
| `nadri/core/config.py` | 수정 | `FAQ_CACHE_THRESHOLD`, `FAQ_EMBED_TIMEOUT_S` (§3) |
| `nadri/api/chat/sse.py` | 수정(08·09) | 입력 검사 통과 뒤 캐시 조회, 적중 시 이벤트 흐름 (§7) |
| `nadri/api/chat/store.py` | 수정(09·11) | `faq_lookup`, 적중 턴 저장(`hit_count+1`), 저장 뒤 작업에 캐시 후보 넘기기 (§8) |
| `nadri/api/chat/background.py` | 수정(09) | `run_after_turn`에 캐시 저장 단계 (§8.3) |
| `nadri/api/main.py` | 수정 | 런타임에 `embed` 연결 |
| `nadri/agent/state.py` | 수정 | `UsageRecord.kind`에 `"embed"` |
| `backend/tests/...` | 신규·수정 | test.md |

> [PL] 파일 목록 밖: `config.py`·`store.py`·`background.py`·`sse.py`·`main.py`·`state.py` — 조회는 스트림 안(입력 검사 뒤), 저장은 09의 저장 뒤 작업이 자리이기 때문.

---

## 3. 설정 (환경변수)

| 이름 | 타입·기본값 | 용도 |
|---|---|---|
| `FAQ_CACHE_THRESHOLD` | `float = 0.95` (0 < x ≤ 1, 범위 밖이면 설정 오류로 기동 실패) | 코사인 유사도 하한(ADR-13 "보수적 0.95 시작"). 22에서 조정 |
| `FAQ_EMBED_TIMEOUT_S` | `float = 5.0` | 임베딩 호출 제한 시간. 넘으면 캐시 건너뜀 |

상수: `EMBED_MODEL = "text-embedding-3-small"`(`core/llm.py`, NFR-32 — 04 `EMBEDDING_DIM=1536`과 짝), `NO_CACHE_TOOLS = frozenset({"web_search", "get_datetime", "tour_live"})`(`faq_cache.py`, ADR-13 — 10 spec 툴 이름).

---

## 4. 임베딩·조회

### 4.1 임베딩
```python
# core/llm.py
EMBED_MODEL = "text-embedding-3-small"
def build_embeddings(settings: Settings) -> OpenAIEmbeddings:
    """OpenAIEmbeddings(model=EMBED_MODEL, api_key=…, max_retries=0). 차원은 모델 기본 1536."""

# api/faq_cache.py
async def embed_question(embeddings: OpenAIEmbeddings, text: str, *, timeout_s: float) -> tuple[list[float], UsageRecord]:
    """
    가린 질문을 임베딩한다.
    Returns: (1536차원 벡터, UsageRecord(kind="embed", model=EMBED_MODEL, input_tokens=토큰 수, ms))
    Raises: EmbedUnavailable — 타임아웃·API 오류·차원 불일치
    """
```
- 토큰 수: `OpenAIEmbeddings`는 사용량을 돌려주지 않는다(**미확인** — langchain-openai 1.8.5에서 확인). 그래서 `tiktoken.get_encoding("cl100k_base")`로 센다(text-embedding-3-small의 인코딩 — 공개 자료 기준, **미확인**). `tiktoken`이 langchain-openai 의존에 들어 있는지 확인하고 없으면 추가(§11).
- 임베딩 대상은 **가린 텍스트만**(NFR-35). 위치는 원래 조회 조건에서 빠진다.
- OpenAI SDK가 아니라 LangChain을 쓰는 이유: [A] §1·ADR-11("OpenAI SDK 직접은 STT·Moderation만").

### 4.2 조회
```python
@dataclass(frozen=True)
class FaqHit:
    """캐시 적중 1건."""
    id: int; answer: str; sources: list[dict]; contentids: list[str]; similarity: float

def should_lookup(turn: TurnInput) -> bool:
    """세션 첫 질문(turn.turn_count == 0) && 위치 없음(turn.location is None)."""
def is_hit(similarity: float, threshold: float) -> bool:
    """similarity >= threshold (경계값 포함)."""
async def lookup(db: AsyncSession, embedding: Sequence[float], *, threshold: float) -> FaqHit | None:
    """가장 가까운 1건을 찾아 is_hit이면 돌려준다."""
```
SQL(pgvector 코사인 거리 `<=>`, SQLAlchemy `FaqCache.embedding.cosine_distance(vec)`):
```sql
SELECT id, answer, sources, contentids, 1 - (embedding <=> :q) AS similarity
FROM faq_cache ORDER BY embedding <=> :q LIMIT 1
```

---

## 5. 저장 조건·저장

### 5.1 조건 (정본)
```python
def cache_candidate(turn: CompletedTurn, *, turn_no: int, has_location: bool) -> FaqCandidate | None:
    """아래 조건을 모두 만족하면 저장 후보, 아니면 None(순수 함수)."""
```
| # | 조건 | 근거 |
|---|---|---|
| 1 | `turn_no == 1` (세션 첫 질문) | ADR-13 |
| 2 | 위치 없음 | ADR-13 (위치 기반 답변은 남에게 맞지 않음) |
| 3 | `verify_status == "passed"` | FR-92 |
| 4 | `from_cache == False` (적중 답변을 다시 넣지 않음) | 중복 방지 |
| 5 | `question_embedding is not None` (조회 때 만든 벡터 재사용 — 두 번 부르지 않음) | 비용 |
| 6 | 툴 기록 이름 중 `NO_CACHE_TOOLS`(`web_search`·`get_datetime`·`tour_live`)가 없음 (오류 기록 포함) | ADR-13 — 시간·외부 자료에 따라 바뀌는 답변 |
| 7 | `sources` 중 `type == "tour"` contentid ≥ 1 | ADR-13 |
| 8 | (DB 확인, §5.2) 그 contentid가 모두 **상세 수집 완료·삭제 안 됨** | 03 껍데기 행 문제(Q2) |

`FaqCandidate = {question: 가린 텍스트, embedding, answer: 저장된 assistant content(강등·좌표 지우기 뒤), sources, contentids: tour 출처 contentid(등장 순)}`.

### 5.2 껍데기 행 제외 (03 연계, Q2)
- 03 적재 동안 `tour_items`에 상세 없는 껍데기 행(`detail_synced_at IS NULL`)이 있고 `data_query`에 보인다(03-Q6). 그 행을 인용한 답변("운영시간 자료 없음")을 캐시하면, 나중에 03이 상세를 채워도 21의 무효화(현행화 변경분)에 걸리지 않아 **낡은 답이 남는다**.
- 그래서 저장 직전 `SELECT count(*) FROM tour_items WHERE contentid = ANY(:ids) AND (detail_synced_at IS NULL OR deleted_at IS NOT NULL)`가 0일 때만 저장한다.
- 03 코드는 바꾸지 않는다(api는 `nadri_app` 롤이라 `tour_items` 조회 가능).

### 5.3 저장
```python
async def save(db: AsyncSession, *, source_message_id: int, c: FaqCandidate) -> int | None:
    """INSERT … ON CONFLICT (source_message_id) DO NOTHING RETURNING id. 커밋은 호출자."""
```

---

## 6. 무효화 (21이 사용)
```python
async def invalidate_by_contentids(db: AsyncSession, contentids: Iterable[str]) -> int:
    """contentids 배열이 겹치는(&&) faq_cache 행을 지우고 지운 수를 돌려준다. 빈 입력이면 0(쿼리 안 함). 커밋은 호출자."""
```
```sql
DELETE FROM faq_cache WHERE contentids && CAST(:ids AS text[])
```
- 지우면 그 캐시를 가리키던 `chat_messages.faq_cache_id`는 NULL이 된다(04 SET NULL) — 이력은 남는다.
- 21의 [A] §3.3 6) "변경·삭제 contentid ∩ ≠ ∅" 그대로. 13의 👎 삭제는 13이 별도 쿼리로 한다.

---

## 7. 스트림 연결 (`api/chat/sse.py`, 08 §10.2에 끼움)

```python
@dataclass
class ChatRuntime:            # 08 + 필드
    ...
    embed: Callable[[str], Awaitable[tuple[list[float], UsageRecord]]] | None = None   # None이면 캐시 끔
```
08 순서 4) 입력 검사 통과 뒤, 5) 그래프 전:
```
4a) vec = None
    if runtime.embed and should_lookup(turn):
        try: vec, u = await runtime.embed(masked.text); usage.append(u)
        except EmbedUnavailable: 로그(클래스명) → 캐시 건너뜀
        if vec: try: hit = await store.faq_lookup(vec)  except 예외: 로그 → hit=None
        if hit: → 4b
4b) 적중:
    status{answering} → delta{text: hit.answer} (한 번에) → draft_done → verified
    turn = CompletedTurn(…, final_text=hit.answer, verify_status="cached", rewrite_count=0,
                         sources=hit.sources, allowed_urls=dedup(extract_urls(hit.answer)),
                         tool_records=[], verify_log=[], answer_texts={}, from_cache=True,
                         faq_cache_id=hit.id, question_embedding=None, timings=…)
    ids = await store.finish_done(ref, turn, events, usage)   # 실패하면 09 규칙(error)
    done{cached:true, verify_status:"cached", rewrite_count:0, sources, allowed_urls, quota_remaining, …ids}
5) 미적중 → 평소 그래프. CompletedTurn.question_embedding = vec
```
- `CompletedTurn`에 필드 추가: `from_cache: bool = False`, `faq_cache_id: int | None = None`, `question_embedding: list[float] | None = None`. `verify_status` Literal에 `"cached"`.
- 캐시 답변은 **출력 검사를 다시 하지 않는다**(저장 때 검증 통과본 — FR-92, 강등·좌표 지우기 끝난 본문). §13 Q4.
- `allowed_urls`: 저장 본문은 이미 강등돼 남은 URL은 원래 허용분(09 Q1과 같은 근거). 캐시 조건상 웹 결과가 없어 대개 관광지 홈페이지 URL뿐.
- timings: `ttft_ms` = 캐시 delta까지, `draft_ms` 같은 시점, `tool_ms`·`verify_ms` = 0, `guard_ms` 입력 검사.
- 턴 로그에 `cached: true`(02 로그 키 추가).

---

## 8. 저장소 (`api/chat/store.py`, `background.py`)

### 8.1 `TurnStore`에 메서드 추가
```python
async def faq_lookup(self, embedding: Sequence[float]) -> FaqHit | None: ...
```
- `DbTurnStore`: 새 세션 → `lookup(db, embedding, threshold=settings.FAQ_CACHE_THRESHOLD)`. 08 `MemoryTurnStore`는 기본 `None`(옵션 `hits` 목록).

### 8.2 `finish_done` (적중 턴)
09 트랜잭션 4)에서 `from_cache=True`면:
1. `UPDATE faq_cache SET hit_count = hit_count + 1 WHERE id = :id RETURNING id` → 행이 없으면(그 사이 21 무효화·13 👎로 지워짐) `faq_cache_id = None`(FK 위반 방지, `from_cache`는 true 유지).
2. assistant 행: `from_cache=true`, `faq_cache_id`, `verify_status="cached"`, `tool_results=NULL`, `verification=NULL`, `rewrite_count=0`, `sources=hit.sources`, `content=hit.answer`.
3. 11 차감 +1, 사용량(classify·moderation·embed) — 11 표 "cached +1".

### 8.3 저장 뒤 작업 (캐시 저장)
- `AfterTurnJob`에 `faq: FaqCandidate | None` 추가. `finish_done`이 커밋 뒤 `cache_candidate(turn, turn_no, has_location=ref.location is not None)`(조건 1~7)를 붙여 넘긴다(content는 저장한 강등·좌표 지우기 본문).
- `run_after_turn`: 제목 → 요약 → **캐시 저장**(후보가 있을 때): 조건 8 확인 → `save` → 커밋. 실패는 로그(클래스명)만.
- 저장을 백그라운드에서 하는 이유: [A] §3.1 11) — 응답 지연에 넣지 않음.

---

## 9. 사용자에게 보이는 것

새 문구 없음. 적중 시 화면은 평소의 "✓ 확인됨"과 같은 흐름(`verified`)이고, `done.cached = true`를 화면이 표시할지는 15가 정한다.

---

## 10. 엣지케이스

| 상황 | 동작 |
|---|---|
| 두 번째 질문 이후 | 조회 안 함(임베딩 호출 없음) |
| 첫 질문 + 위치 | 조회 안 함, 저장 안 함 |
| 입력 검사 차단·오류 | 조회 전에 끝남(임베딩 호출 없음) |
| 유사도 정확히 0.95 | 적중(≥) |
| 0.9499 | 미적중 → 그래프 |
| 캐시 테이블 비어 있음 | 미적중 |
| 임베딩 타임아웃·오류 | 캐시 건너뜀, 그래프 진행, embed usage 없음, 이 턴은 저장 후보 아님(벡터 없음) |
| DB 조회 오류 | 캐시 건너뜀(로그) |
| 적중 직후 그 캐시가 무효화됨 | `faq_cache_id` NULL로 저장, 답변은 그대로 |
| 검증 다시 쓰기 뒤 통과 | `passed`라 저장 후보 |
| `tour_live`·`get_datetime`·`web_search` 호출(오류 포함) | 저장 안 함 |
| 인용 contentid 중 하나가 껍데기 행 | 저장 안 함(§5.2) |
| 스몰토크(툴 없음, 출처 없음) | 저장 안 함(contentid 0) |
| 같은 원 메시지로 저장 2번 | `DO NOTHING` |
| 거의 같은 질문이 연달아 미적중으로 저장 | 각각 저장(0.95 미만이라 다른 질문으로 봄) |
| 개인정보가 가려진 질문 | 가린 텍스트로 임베딩·저장(원문 없음) |
| 세션 삭제(90일·사용자) | 원 메시지 연쇄로 캐시 행 삭제, 그 캐시를 쓴 다른 메시지는 `faq_cache_id` NULL |

---

## 11. 앞 작업과 달라지는 점 · 테스트 수정

| # | 내용 | 대상 | 처리 |
|---|---|---|---|
| 1 | `ChatRuntime.embed` 추가(기본 None) | 02·08·09·11 테스트 런타임 | 수정 없음(None = 캐시 끔). 09·11 DB 테스트 중 실제 `get_chat_runtime`으로 만드는 앱이 있으면 테스트 앱 팩토리에서 `embed=None`으로 덮어씀 |
| 2 | `TurnStore.faq_lookup` 추가 | 08 `MemoryTurnStore` | 메서드 추가(기본 None) |
| 3 | `CompletedTurn`·`AfterTurnJob` 필드 추가(기본값) | 08·09 | 수정 없음 |
| 4 | `UsageRecord.kind`에 `embed` | 11 U-US-04 | 그대로 통과(04 `USAGE_KINDS`에 이미 있음) |
| 5 | 의존 `tiktoken` | `pyproject.toml` | langchain-openai 의존에 없으면 추가(**미확인**) |

상위 문서와의 차이:
1. **껍데기 행 인용 답변 제외**(§5.2 조건 8) — ADR-13에 없는 조건. 03 적재와 21 무효화 사이의 빈틈을 막음(Q2).
2. **적중 답변 재검사 안 함**(Q4).
3. 적중 시 `draft_done`도 보냄(15 상태 기계가 실시간 답변과 같은 순서를 받게) — [A] §3.1 6)은 "delta → verified"만 적었다.
4. 임베딩 토큰 수를 tiktoken으로 셈(§4.1).

---

## 12. 완료 기준 (DoD)

1. test.md ① 전부 통과(저장 조건 표, 임계값 경계, 무효화, 임베딩 실패 우회, 적중 SSE 순서 스냅샷).
2. 적중 턴: 한도 +1, `chat_messages`에 `from_cache=true`·`faq_cache_id`·`verify_status=cached`, `hit_count+1`, 그래프·검증 호출 0회.
3. 임베딩이 받은 텍스트가 가린 텍스트(테스트).
4. HITL-1(같은 질문 두 세션) 결과 보고.
5. 한국어 docstring·단계 주석. 커밋 `feat/12-faq-cache`, `[Feat] …` + `Author:`, AI 공동작성 표기 없음. `dev` 병합은 G5 후. `PROGRESS.md` 갱신.

---

## 13. 확인 질문

| # | 질문 | 추천안 | 대안 |
|---|---|---|---|
| Q1 | 캐시 답변을 화면에 어떻게 흘릴까 | **결정(2026-11-21): 추천안대로** — **delta 1번에 전체 → draft_done → verified**(지연 없음, 화면 흐름은 평소와 같음) | 몇 글자씩 나눠 일부러 천천히 흘림 |
| Q2 | 적재 중 껍데기 행(상세 없음)을 인용한 답변 | **결정(2026-11-21): 추천안대로** — **캐시에 넣지 않음**(저장 전 `tour_items` 확인 — 상세가 채워져도 21 무효화에 안 걸려 낡은 답이 남는 것 방지) | 03 적재가 상세를 채울 때 `invalidate_by_contentids` 호출(03 코드 수정 필요) |
| Q3 | 임베딩 토큰 수 | **결정(2026-11-21): 추천안대로** — **tiktoken으로 세어 기록**(비용이 매우 작아 근사 허용) | 토큰 NULL·비용 0으로 두고 건수만 |
| Q4 | 캐시 적중 답변을 다시 출력 검사(Moderation 등)할까 | **결정(2026-11-21): 추천안대로** — **안 함**(저장 때 검증 통과본, 강등·좌표 지우기 끝남) | 출력 Moderation만 다시(호출 1회 추가, 무료) |
| Q5 | 임계값 0.95를 22 평가 전까지 그대로 둘까 | **결정(2026-11-21): 추천안대로** — **그대로**(ADR-13 보수적 시작, 설정값 `FAQ_CACHE_THRESHOLD`) | 0.97로 더 보수적으로 시작 |
