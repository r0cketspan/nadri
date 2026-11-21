# 13-feedback — 👍/👎 피드백 API (spec)

> 하네스 Phase 4 산출물 (spec-writer, 작성 2026-11-21). 상태: **확정(2026-11-22)** — 확인 질문은 모두 추천안대로 결정(마지막 절 표). 브랜치 `feat/13-feedback`, 의존 작업 12-faq-cache(→ 11·09·08·05·04).
> 근거: [PL]=program_list.md(G4 승인본) §2 표·§3 "13-feedback" · [A]=architecture.md(G3 재승인본) §2.1 `feedback`·§3.9·§5.1 `message_feedback`·`faq_cache`(비고 "저장 조건에 검증 통과·👎 없음")·§6.1·ADR-13 · [R]=requirements.md FR-103·104, NFR-31.
> **이어받는 확정 spec**: [04](`MessageFeedback`·`FEEDBACK_RATINGS`·`FEEDBACK_REASONS`·`ck_message_feedback_reason`·`pk_message_feedback`·FK CASCADE) · [05](`require_active`·`CurrentUser`·`get_db`·`get_now`·`ApiError`·`errors.py`·CSRF 미들웨어) · [09](`MessageOut`·`SessionDetailOut`·`GET /api/chat/sessions/{id}`·`make_session` 헬퍼) · [12](`faq_cache.py`·`save`·`FaqCache`·`chat_messages.faq_cache_id` SET NULL·`run_after_turn` 캐시 저장 단계).
> **미확인** = 문서·공식 자료로 확인하지 못한 사실.

---

## 1. 작업 목표

답변(assistant 메시지)마다 👍/👎를 남기고 바꾸고 취소하는 API를 만든다. 👎이면 그 답변과 연결된 FAQ 캐시 행을 지워 같은 답이 다시 나가지 않게 한다 [A] §3.9, [R] FR-103.

- `PUT /api/chat/messages/{id}/feedback {rating, reason?}` → 본인 세션의 assistant 메시지인지 확인 → 메시지당 1행 upsert → `down`이면 `faq_cache` 중 `source_message_id = id` 또는 `id = 그 메시지의 faq_cache_id` 행 삭제(같은 트랜잭션).
- `DELETE` 같은 경로 → 피드백 취소(행 삭제).
- 세션 조회 응답(`GET /api/chat/sessions/{id}`)의 assistant 메시지마다 내 피드백(`feedback`)을 넣는다 — 화면(16)이 새로고침 뒤에도 눌린 상태를 그린다.
- 12의 캐시 저장(저장 뒤 백그라운드)에 "👎 없음" 조건을 더한다 — 답변 직후 바로 👎를 누른 경우 백그라운드 저장이 늦게 돌아 캐시에 들어가는 빈틈을 막는다([A] §5.1 `faq_cache` 비고, §11 차이 1).

### 1.1 넣지 않는 것
| 빠지는 것 | 들어오는 작업 / 이유 |
|---|---|
| 👍/👎 버튼·사유 선택 화면 | 16 |
| 피드백을 평가에 쓰기(👎 먼저 채점, 점수 일치율) | 24 |
| 👎 사유 자유 입력(글) | 요구사항은 "사유 선택"만(FR-103) — 넣지 않음 |
| 👎 → 👍로 바꿀 때 지운 캐시 되살리기 | 넣지 않음(캐시는 다음 첫 질문에서 다시 생길 수 있음) |
| 피드백 요청 제한(분당) | 넣지 않음 — 외부 호출·비용 없음, active 사용자만, 메시지당 1행 |
| 90일 삭제 | 04 FK CASCADE + 21(대화와 함께 삭제) |

---

## 2. 생성·수정 파일

경로의 `nadri/`는 `backend/src/nadri/`.

| 파일 | 신규/수정 | 역할 |
|---|---|---|
| `nadri/api/feedback.py` | 신규 | 요청·응답 모델, `put_feedback`·`delete_feedback` 서비스, 라우터(`PUT`·`DELETE`) (§4·§5) |
| `nadri/api/chat/router.py` | 수정(09) | `GET /api/chat/sessions/{id}` 응답에 `feedback` 채우기 (§6) |
| `nadri/api/faq_cache.py` | 수정(12) | `save`에 "원 메시지에 👎 없음" 조건 (§7) |
| `nadri/api/errors.py` | 수정(05) | `message_not_found` 코드·문구 (§4.3) |
| `nadri/api/main.py` | 수정 | feedback 라우터 등록 |
| `backend/tests/...` | 신규·수정 | test.md, 앞 작업 테스트 수정(§9) |

> [PL] 파일 목록 밖: `faq_cache.py`(👎 경합 빈틈 — §7), `errors.py`, `main.py`, `chat/router.py`([PL]은 "세션 조회 응답에 내 피드백 포함"이라고만 적음 — 그 자리가 09 라우터).

---

## 3. 설정 · 상수

새 환경변수 없음. 허용값은 04 상수를 그대로 쓴다.

| 상수 | 위치 | 값 |
|---|---|---|
| `FEEDBACK_RATINGS` | `core/models/quality.py`(04) | `("up", "down")` |
| `FEEDBACK_REASONS` | 〃 | `("wrong", "outdated", "misunderstood", "other")` |

사유 코드 ↔ 화면 문구(16이 표시, FR-103): `wrong` 틀린 정보 · `outdated` 오래된 정보 · `misunderstood` 질문 이해 못함 · `other` 기타.

---

## 4. API

모두 `require_active`(pending은 메시지가 없으므로 사실상 해당 없음), `PUT`·`DELETE`는 05 CSRF 미들웨어 적용. 오류 본문은 05 형식 `{"code","message"}`.

### 4.1 엔드포인트
| 메서드·경로 | 요청 본문 | 성공 | 실패 |
|---|---|---|---|
| `PUT /api/chat/messages/{message_id}/feedback` | `{"rating": "up"\|"down", "reason"?: "wrong"\|"outdated"\|"misunderstood"\|"other"\|null}` | 200 `FeedbackOut` | 404 `message_not_found` / 422(본문·경로 형식) / 401·403(05) |
| `DELETE /api/chat/messages/{message_id}/feedback` | 없음 | 204 (피드백이 없었어도 204) | 404 `message_not_found` / 422 / 401·403 |

```python
class FeedbackIn(BaseModel):
    """피드백 요청 본문."""
    rating: Literal["up", "down"]
    reason: Literal["wrong", "outdated", "misunderstood", "other"] | None = None

    @model_validator(mode="after")
    def _reason_only_for_down(self) -> "FeedbackIn":
        """rating=up인데 reason이 있으면 ValueError(→ 422). DB CHECK(ck_message_feedback_reason)와 같은 규칙."""

class FeedbackOut(BaseModel):
    """피드백 응답·세션 조회 응답에 넣는 모양."""
    rating: Literal["up", "down"]
    reason: Literal["wrong", "outdated", "misunderstood", "other"] | None
```
- 경로 `message_id: int = Path(ge=1, le=2**63 - 1)` — 정수가 아니거나 범위 밖이면 FastAPI 기본 422(bigint 넘침으로 500이 나지 않게).
- `PUT` 응답 = `FeedbackOut`(저장된 값). 처음 만들 때와 바꿀 때 모두 200(화면은 둘을 구분할 필요 없음).

### 4.2 처리 순서

**PUT** ([A] §3.9)
1. `target = await load_owned_assistant(db, message_id, cu.user.id)` → 없으면 404 `message_not_found`.
2. upsert(§5.1). `user_id = cu.user.id`, `created_at`(새 행일 때)·`updated_at` = `now`(05 `get_now`).
3. `rating == "down"`이면 `deleted = await drop_cache_for(db, message_id, target.faq_cache_id)`(§5.2).
4. 커밋 → 200 `FeedbackOut`. 로그 1줄: `feedback` 이벤트 이름, `message_id`, `rating`, `reason`, `cache_deleted` 수(사용자 글·답변 본문은 넣지 않음).

**DELETE**
1. 1과 같음(없으면 404).
2. `DELETE FROM message_feedback WHERE message_id = :id` → 커밋 → 204.
- 취소해도 이미 지운 캐시는 되살리지 않는다.

### 4.3 사용자에게 보이는 문구 (`errors.py`에 추가)
| code | HTTP | 상수 | 문구 |
|---|---|---|---|
| `message_not_found` | 404 | `MSG_MESSAGE_NOT_FOUND` | 답변을 찾을 수 없어요. 삭제된 대화일 수 있어요. |

- 없는 메시지·남의 메시지·user 메시지는 **모두 같은 404**(존재 여부를 드러내지 않음 — 09 `session_not_found`와 같은 원칙).
- 17(TTS)도 같은 "본인 assistant 메시지" 확인과 같은 코드를 쓴다. **13이 먼저 병합되면 17은 이 상수를 재사용**하고, 17이 먼저면 17이 같은 이름·문구로 추가한다(§11 Q4).

---

## 5. 서비스 (`api/feedback.py`)

```python
@dataclass(frozen=True)
class OwnedMessage:
    """본인 소유가 확인된 assistant 메시지의 필요한 값."""
    id: int
    faq_cache_id: int | None

async def load_owned_assistant(db: AsyncSession, message_id: int, user_id: int) -> OwnedMessage | None:
    """chat_messages ⋈ chat_sessions 로 '그 사용자 세션의 assistant 메시지'를 찾는다. 없으면 None. (17 TTS도 재사용)"""

async def put_feedback(db: AsyncSession, *, user_id: int, message_id: int, body: FeedbackIn,
                       now: datetime) -> tuple[FeedbackOut, int]:
    """§4.2 PUT 1~3을 처리하고 (저장된 피드백, 지운 캐시 행 수)를 돌려준다. 커밋까지 한다.
    Raises: ApiError(404 message_not_found)."""

async def delete_feedback(db: AsyncSession, *, user_id: int, message_id: int) -> None:
    """§4.2 DELETE. 커밋까지. Raises: ApiError(404)."""

async def drop_cache_for(db: AsyncSession, message_id: int, faq_cache_id: int | None) -> int:
    """👎 답변과 연결된 faq_cache 행을 지우고 지운 수를 돌려준다. 커밋은 호출자."""
```

### 5.1 SQL
본인 확인:
```sql
SELECT m.id, m.faq_cache_id
FROM chat_messages m JOIN chat_sessions s ON s.id = m.session_id
WHERE m.id = :mid AND m.role = 'assistant' AND s.user_id = :uid
```
upsert:
```sql
INSERT INTO message_feedback (message_id, user_id, rating, reason, created_at, updated_at)
VALUES (:mid, :uid, :rating, :reason, :now, :now)
ON CONFLICT (message_id) DO UPDATE
  SET rating = EXCLUDED.rating, reason = EXCLUDED.reason, updated_at = EXCLUDED.updated_at
RETURNING rating, reason
```
- `👎 + 사유` → `👎(사유 없음)`으로 다시 PUT하면 `reason`은 NULL로 바뀐다(본문이 정본 — 부분 갱신 없음).
- `user_id`는 세션 주인과 항상 같다(본인 확인을 통과했으므로).

### 5.2 캐시 삭제 ([A] §3.9)
```sql
DELETE FROM faq_cache WHERE source_message_id = :mid OR id = :faq_cache_id
```
- `faq_cache_id`가 NULL이면 `OR` 쪽은 아무 행에도 맞지 않는다(SQL NULL 비교). 바인딩은 그대로 NULL.
- 두 경우: ① 이 메시지가 **캐시의 원본**(12 저장) ② 이 메시지가 **캐시 적중 답변**(그 캐시 행). 지워지면 그 캐시를 가리키던 다른 메시지의 `faq_cache_id`는 04 FK로 NULL(이력은 남음).
- 같은 메시지에 👎를 여러 번 눌러도 두 번째부터는 0행(오류 아님).

---

## 6. 세션 조회 응답 (`api/chat/router.py`, 09 §4.1 확장)

```python
class MessageOut(BaseModel):        # 09 + 필드
    ...
    feedback: FeedbackOut | None = None     # assistant만, 피드백 없으면 None (user는 항상 None)
```
- `GET /api/chat/sessions/{id}`의 메시지 조회에 `LEFT JOIN message_feedback f ON f.message_id = m.id`를 붙여 assistant 행에 `FeedbackOut(rating, reason)`을 넣는다. 쿼리 1개 유지(메시지마다 따로 조회하지 않음).
- `GET /api/chat/sessions`(목록)에는 넣지 않는다.

---

## 7. FAQ 캐시 저장 경합 막기 (`api/faq_cache.py`, 12 §5.2·§5.3 확장)

문제: 12는 답변 저장 **뒤 백그라운드**(`run_after_turn`)에서 캐시를 저장한다. 사용자가 답을 보자마자 👎를 누르면 순서가 ① 👎 저장(지울 캐시 없음) → ② 백그라운드가 캐시 저장이 될 수 있다. 그러면 👎 받은 답이 캐시에 남는다([A] §5.1 "저장 조건에 '👎 없음'"과 어긋남).

처리: 12의 조건 8 확인과 `save`를 다음처럼 바꾼다(조건 9).
```sql
INSERT INTO faq_cache (source_message_id, question, embedding, answer, sources, contentids)
SELECT :src, :q, :emb, :ans, :sources, :cids
WHERE NOT EXISTS (SELECT 1 FROM message_feedback WHERE message_id = :src AND rating = 'down')
ON CONFLICT (source_message_id) DO NOTHING
RETURNING id
```
- 반환 None = 저장 안 함(👎 있음 또는 이미 있음). 12 `save`의 시그니처·반환 의미("None이면 저장 안 됨")는 그대로.
- 남는 빈틈: 백그라운드의 `INSERT`와 👎 트랜잭션이 정확히 동시에 커밋되면(READ COMMITTED) 하나를 놓칠 수 있다. 사람이 버튼을 누르는 시간 단위에서는 사실상 일어나지 않고, 일어나도 다음 👎(재클릭) 또는 21의 무효화로 지워진다 — 받아들인다(§11 Q2).

---

## 8. 엣지케이스

| 상황 | 동작 |
|---|---|
| 남의 메시지 id | 404 `message_not_found` |
| 내 user 메시지 id | 404 (assistant만) |
| 없는 id / 삭제된 세션의 메시지 | 404 |
| `abc` / `0` / `2**63` | 422 |
| `{"rating":"up","reason":"wrong"}` | 422 |
| `{"rating":"down"}` | 저장(사유 NULL) |
| `{"rating":"meh"}` / `{"reason":"bad"}` | 422 |
| 👍 → 👎 | 행 1개, rating down, 캐시 삭제 |
| 👎(wrong) → 👎(null) | reason NULL |
| 👎 → 👍 | rating up, reason NULL, 지운 캐시는 그대로 없음 |
| 👎 두 번 | 200 두 번, 행 1개, 두 번째 캐시 삭제 0 |
| 피드백 없는 메시지에 DELETE | 204 |
| 캐시 원본 메시지 👎 | 그 캐시 행 삭제, 적중했던 다른 메시지들의 `faq_cache_id` NULL |
| 캐시 적중 메시지 👎 | 그 캐시 행 삭제(원본 메시지의 다른 데이터는 그대로) |
| 캐시 적중 메시지인데 캐시가 이미 무효화됨(`faq_cache_id` NULL) | 삭제 0, 피드백만 저장 |
| 답변 직후 👎 → 백그라운드 캐시 저장 | 저장 안 됨(§7) |
| `security_replaced`·`failed` 답변 | 피드백 가능(평가 재료). 캐시는 원래 없음 |
| 세션 삭제 | 피드백 연쇄 삭제(04) |
| CSRF 헤더 없음 | 403 `csrf_failed`(05) |
| pending·disabled 사용자 | 403 / 401(05) |

---

## 9. 앞 작업과 달라지는 점 · 앞 작업 테스트 수정

| # | 내용 | 대상 | 처리 |
|---|---|---|---|
| 1 | `MessageOut.feedback` 필드 추가(기본 None) | 09 세션 조회 테스트(응답 메시지 dict를 통째로 비교하는 것이 있으면) | 기대 dict에 `"feedback": null` 추가. 필드별 비교면 수정 없음 |
| 2 | 12 `save`가 👎 있으면 None | 12 D-FQ-05·A-FC 계열 | 수정 없음(피드백 행을 만들지 않으므로 그대로 통과). 새 테스트 추가(test.md) |
| 3 | `errors.py`에 `message_not_found` | 05 문구 상수 테스트(상수 목록을 고정 비교하면) | 목록에 추가 |

상위 문서와의 차이(구현 판단):
1. **캐시 저장에 "👎 없음" 조건**(§7): [A] §5.1 `faq_cache` 비고에는 있지만 12 spec 조건 표(§5.1 조건 1~8)에는 빠져 있었다 — 13에서 채운다(Q1).
2. `DELETE`는 피드백이 없어도 204(멱등).
3. `rating=up` + `reason`은 422(DB CHECK와 같은 규칙을 입력 단계에서).

---

## 10. 완료 기준 (DoD)

1. test.md ① 전부 통과(`cd ~/code/myAgent/backend && uv run pytest -m "not integration"`), §9 앞 작업 테스트 수정 후 통과.
2. 권한: 남의 메시지·user 메시지 → 404, CSRF 없음 → 403.
3. upsert·변경·취소, 메시지당 1행.
4. 👎 시 캐시 삭제 두 경우(원본 메시지·캐시 적중 메시지) 테스트 통과, 👎 뒤 백그라운드 저장이 캐시를 만들지 않음.
5. 세션 조회 응답에 `feedback`.
6. HITL-1 결과 보고.
7. 한국어 docstring·단계 주석([CL]). 커밋 `feat/13-feedback`, `[Feat] …` + 작업 목록 + `Author:`, AI 공동작성 표기 없음. `dev` 병합은 G5 후. `PROGRESS.md` 갱신.

---

## 11. 확인 질문

| # | 질문 | 추천안 | 대안 |
|---|---|---|---|
| 13-Q1 | 12 spec의 캐시 저장 조건에 "👎 없음"이 빠져 있다([A] §5.1에는 있음). 13에서 `faq_cache.save`를 고쳐 채울까 | **결정(2026-11-22): 추천안대로** — **채운다**(`INSERT … WHERE NOT EXISTS(👎)` 한 줄 — 답변 직후 👎 경합 방지) | 고치지 않음(👎를 다시 누르면 지워지므로 드문 경합은 그대로 둠) |
| 13-Q2 | §7의 동시 커밋 극단 경합(밀리초 단위)까지 막을까 | **결정(2026-11-22): 추천안대로** — **받아들임**(사람 클릭 속도에서 사실상 없음, 생겨도 21 무효화·재클릭으로 지워짐) | `message_feedback` 행 잠금·직렬화 격리 수준(코드 복잡) |
| 13-Q3 | `DELETE`를 피드백이 없을 때도 204로 할까 | **결정(2026-11-22): 추천안대로** — **204**(멱등 — 화면이 빠르게 두 번 눌러도 오류 없음) | 404 `feedback_not_found` |
| 13-Q4 | 13과 17이 같은 "본인 assistant 메시지 확인"·`message_not_found`를 쓴다. 정의 위치 | **결정(2026-11-22): 추천안대로** — **13 `feedback.py`의 `load_owned_assistant`·`MSG_MESSAGE_NOT_FOUND`를 17이 재사용**(병합 순서가 17이 먼저면 17이 같은 이름으로 만들고 13이 재사용) | 각자 따로 만듦(중복) |
| 13-Q5 | 👎 → 👍로 바꾸면 지운 캐시를 되살릴까 | **결정(2026-11-22): 추천안대로** — **되살리지 않음**(요구사항 없음, 캐시는 다음 첫 질문에서 다시 생김) | 되살림(지운 행 보관 필요) |
