# 19-admin-usage — 관리자: 사용량 대시보드 (spec)

> 하네스 Phase 4 산출물 (spec-writer, 작성 2026-11-22). 상태: **확정(2026-11-22)** — 확인 질문은 모두 추천안대로 결정(마지막 절 표). 브랜치 `feat/19-admin-usage`, 의존 작업 18-admin-users(→ 11·14·05·04).
> 근거: [PL]=program_list.md(G4 승인본, 2026-11-22 개정) §2 표·§3 "19-admin-usage"·§4 · [A]=architecture.md(G3 재승인본) §2.1 `admin`·`usage` 모듈·§3.2(stt·tts 기록)·§5.1 `usage_events`·§6.1 `GET /api/admin/usage?from=&to=`·§9 끝줄("선택: 서비스별 OpenAI 키 분리(A14 보완)")·§10 비용·지표 기록 범위·§12.2 A14·A28 · [R]=requirements.md FR-61·63·83, NFR-43·61 · [S]=stack-options.md S20(ElevenLabs 플랜 크레딧 미확인)·S21 · [PG]=PROGRESS.md 결정 로그(11-Q2 장애 턴도 비용 기록, 17-Q1 STT 초 = 브라우저 녹음 길이, 2026-11-22 한도 추가 요청 삭제·관리자 한도 없음).
> **이어받는 확정 spec**: [04](`UsageEvent`·`USAGE_KINDS` 13종·`usage_events` 컬럼·`user_id` SET NULL·토큰 NULL 허용·`users.role`) · [05](`require_admin`(`api/deps.py`)·`CurrentUser`·`get_db`·`get_now`·`ApiError`·`errors.py`·`forbidden`·`unauthenticated` 문구) · [11](`record_usage`·`cost_usd` 8자리(`COST_QUANT`)·kind별 비용 규칙(moderation·web_search·tts 0)·`units` 의미·`kst_day`·장애 턴도 기록(11-Q2)·성공한 호출만 기록·관리자도 사용량 기록) · [12](`embed`) · [14](`apiJson`·`ApiError`(web)·Playwright 설정·`e2e/helpers/db.ts`·`global-setup.ts`·`approve()`) · [17](`stt` units = 초(60초 상한, 17-Q1)·`tts` units = 글자 수·실패 호출은 기록 없음).
> **병렬 작성 중인 앞 작업**: 18-admin-users spec **초안**(2026-11-22, 확인 질문 대기) §9 "19·25가 넓히는 방법"을 따른다 — `nadri/api/admin/router.py`의 `admin_router`(접두어 `/api/admin`, 라우터 전체에 `Depends(require_admin)`)에 `include_router` 1줄, `web/components/admin/AdminShell.tsx`의 `ADMIN_NAV`에 항목 1개, `web/e2e/helpers/db.ts`의 `makeAdmin`. `web/app/admin/layout.tsx`는 고치지 않는다. 18이 확정되며 이름이 바뀌면 이 spec의 연결 부분만 맞춘다(19-Q8).
> **미확인** = 문서·공식 자료로 확인하지 못한 사실.

---

## 1. 작업 목표

11이 쌓은 `usage_events`를 관리자가 한 화면에서 본다 [R] FR-83, [A] §6.1.

- `GET /api/admin/usage?from=&to=` (관리자만): 기간(한국 날짜) 안의 **종류(kind)별·일자별·사용자별** 호출 수·토큰(입력·캐시 읽기·캐시 쓰기·출력)·비용, 그리고 외부 서비스 사용량(Moderation 건수, Tavily 크레딧, ElevenLabs 글자 수, STT 초 — NFR-43).
- **이번 달(KST 달력 월) 누적 OpenAI 비용**과 **$10 초과 경고 플래그**(FR-63 — 경고만, 차단 없음).
- `/admin/usage` 화면: 경고 배너, 이번 달 카드("앱 기록 기준 추정" 표기 — LightRAG 내부 호출 미포함, A14), 기간 조회, 표 3개.
- 관리자 메뉴(18 `AdminShell.tsx`의 `ADMIN_NAV`)에 "사용량" 링크 1개.

### 1.1 넣지 않는 것
| 빠지는 것 | 들어오는 작업 / 이유 |
|---|---|
| 사용량 **기록**(행 만들기)·단가표 | 11(`record_usage`·`pricing.py`), 12·17·20·24가 각자 호출 |
| 비용 초과 시 채팅 차단·메일 알림 | FR-63 "차단은 하지 않음", 메일 알림 요구 없음 |
| LightRAG 내부 OpenAI 호출(인덱싱·키워드 추출) 집계 | 앱이 못 셈(A14) — "추정" 표기만. 서비스별 키 분리는 19-Q5 |
| 차트·그래프 | 요구는 "표시"뿐 — 표로 충분(19-Q2) |
| 사용자별 질문 횟수(`daily_quota`) 표시 | 요구사항은 토큰·비용(FR-83). 한도 화면은 없음(2026-11-22 추가 요청 삭제) |
| CSV 내려받기·사용자 필터·월말 예상치 | 요구 없음 |
| 단가가 바뀌었을 때 지난 행 비용 다시 계산 | 행의 `cost_usd`는 기록 시점 단가(11) — 그대로 합산 |
| `usage_events` 90일 정리 | 요구 없음([A] §3.3 9)에 없음) — 비용 기록은 계속 남김 |
| `usage_events.created_at` 인덱스 | 1~5명 규모(NFR-61)라 전체 훑기로 충분(19-Q7) |
| 관리자 화면 틀·관리자 로그인 확인 | 18 |

---

## 2. 생성·수정 파일

경로의 `nadri/`는 `backend/src/nadri/`.

| 파일 | 신규/수정 | 역할 |
|---|---|---|
| `nadri/api/admin/usage.py` | 신규 | 응답 모델, 기간 계산, 집계 SQL, `GET /api/admin/usage` 라우트 (§4·§5) |
| `nadri/api/admin/router.py` | 수정(18) | `admin_router.include_router(usage.router)` 1줄 (§4.6, 19-Q8) |
| `nadri/api/errors.py` | 수정(05) | `invalid_range` 코드·문구 (§4.5) |
| `web/lib/admin-usage.ts` | 신규 | 응답 타입, `getAdminUsage()`, 금액·숫자 서식, kind 한글 이름·단위 (§6.1) — 18 `admin-api.ts`와 따로 둠(18 §9 "별도 파일 가능") |
| `web/app/admin/usage/page.tsx` | 신규 | 사용량 화면 (§6.2) |
| `web/components/admin/AdminShell.tsx` | 수정(18) | `ADMIN_NAV`에 `{ href: "/admin/usage", label: "사용량" }` (§6.4) |
| `web/e2e/global-setup.ts` | 수정(14) | `e2e_` 사용자의 `usage_events` 삭제 1줄 (§8 #3, 19-Q9) |
| `backend/tests/...`, `web/tests/unit/admin-usage.test.ts`, `web/e2e/admin-usage.spec.ts`, `web/e2e/fixtures/usage/*.json` | 신규 | test.md |

> [PL] 파일 목록 밖: `admin/router.py`·`AdminShell.tsx`(18 파일에 연결 1줄씩), `errors.py`, `web/lib/admin-usage.ts`(서식 함수를 Vitest로 검사하려고 페이지에서 분리), `global-setup.ts`(e2e 사용량 행 정리).

---

## 3. 설정 · 상수

새 환경변수 없음(요구사항이 정한 고정값 — 05·11과 같은 판단).

| 상수 | 위치 | 값 | 근거 |
|---|---|---|---|
| `MONTHLY_WARN_USD` | `admin/usage.py` | `Decimal("10")` | FR-63 ("넘으면" → `>`) |
| `TAVILY_FREE_CREDITS` | `admin/usage.py` | `1000` | NFR-43, A28 (월 무료 크레딧 — 표시용) |
| `NON_OPENAI_KINDS` | `admin/usage.py` | `frozenset({"web_search", "tts"})` | Tavily·ElevenLabs는 OpenAI 비용이 아님(11에서 둘 다 비용 0) |
| `MAX_RANGE_DAYS` | `admin/usage.py` | `366` | 19-Q6 |
| `KST` | `core/tourapi.py`(01) | `ZoneInfo("Asia/Seoul")` | 재사용 |
| `kst_day` | `api/quota.py`(11) | — | 재사용 |
| `USAGE_KINDS` | `core/models/quota.py`(04) | 13종 | kind 표시 순서·대조 테스트 |

---

## 4. API

### 4.1 엔드포인트
| 메서드·경로 | 쿼리 | 성공 | 실패 |
|---|---|---|---|
| `GET /api/admin/usage` | `from`, `to` — 둘 다 선택, `YYYY-MM-DD`(한국 날짜, **양 끝 포함**) | 200 `UsageReport` | 400 `invalid_range` / 422(날짜 형식) / 401 `unauthenticated` / 403 `forbidden`(05 `require_admin` — pending도 같음) |

- GET이라 CSRF 검사 없음(05 미들웨어 규칙). 요청 제한 없음(관리자만, 외부 호출 없음).
- 로그: `admin_usage` 이벤트 이름, 관리자 id, `from`·`to`만.

### 4.2 응답 모델 (`admin/usage.py`)
금액은 **문자열**(`f"{d:.8f}"`, 11 `COST_QUANT`와 같은 8자리 — JSON 숫자로 바꾸며 생기는 반올림을 피한다). 토큰·호출 수·사용량은 정수.

```python
class UsageSums(BaseModel):
    """호출 묶음의 합계."""
    calls: int                 # 행 수
    input_tokens: int          # NULL은 0으로 더함(아래 §7 "토큰 NULL")
    cached_tokens: int
    cache_write_tokens: int
    output_tokens: int
    cost_usd: str              # "0.00190000"

class KindRow(UsageSums):
    """종류별 합계."""
    kind: str                  # USAGE_KINDS 중 하나
    units: int                 # moderation·web_search 건(크레딧), stt 초, tts 글자, 그 밖 0

class DayRow(UsageSums):
    """한국 날짜별 합계."""
    day: date

class UserRow(UsageSums):
    """사용자별 합계. user_id None = 시스템(ingest 배치 — 허브·평가·개선안)."""
    user_id: int | None
    username: str | None

class ExternalUsage(BaseModel):
    """OpenAI 토큰이 아닌 사용량(NFR-43)."""
    moderation_calls: int      # kind=moderation 행 수(무료)
    tavily_credits: int        # kind=web_search units 합
    elevenlabs_chars: int      # kind=tts units 합
    stt_seconds: int           # kind=stt units 합

class MonthSummary(BaseModel):
    """이번 달(KST 달력 월, 1일 ~ 오늘) 누적 — 조회 기간과 무관하게 항상 이번 달."""
    month: str                 # "2026-11"
    start: date                # 그 달 1일
    end: date                  # 오늘(KST)
    openai_cost_usd: str       # NON_OPENAI_KINDS를 뺀 cost_usd 합
    warn_threshold_usd: str    # "10.00"
    warning: bool              # openai_cost_usd > MONTHLY_WARN_USD
    external: ExternalUsage
    tavily_free_credits: int   # TAVILY_FREE_CREDITS

class UsageReport(BaseModel):
    """GET /api/admin/usage 응답."""
    model_config = ConfigDict(populate_by_name=True)
    from_: date = Field(serialization_alias="from")
    to: date
    timezone: Literal["Asia/Seoul"] = "Asia/Seoul"
    totals: UsageSums
    external: ExternalUsage
    by_kind: list[KindRow]     # USAGE_KINDS 순서, 행이 있는 kind만
    by_day: list[DayRow]       # 최근 날짜가 위(내림차순), 행이 있는 날만
    by_user: list[UserRow]     # 비용 큰 순 → username 순, 시스템(None)은 같은 비용이면 맨 아래
    month: MonthSummary
```
- 라우트는 `response_model=UsageReport, response_model_by_alias=True`(기본값) — JSON 키는 `"from"`.

### 4.3 시그니처
```python
def fmt_usd(d: Decimal) -> str:
    """Decimal 금액을 소수 8자리 문자열로. None·NaN은 오지 않는다(SUM은 COALESCE로 0)."""

def resolve_range(from_: date | None, to: date | None, now: datetime) -> tuple[date, date]:
    """조회 기간(한국 날짜, 양 끝 포함)을 정한다.
    - to 없음 → 오늘(kst_day(now)). from 없음 → to가 속한 달의 1일.
    - from > to 또는 (to − from).days + 1 > MAX_RANGE_DAYS → ApiError(400, invalid_range)."""

def kst_bounds(start_day: date, end_day: date) -> tuple[datetime, datetime]:
    """한국 날짜 구간 [start_day, end_day]를 UTC 반열린 구간 [시작 00:00 KST, end_day+1 00:00 KST)로 바꾼다."""

def month_range(now: datetime) -> tuple[date, date]:
    """이번 달 (1일, 오늘) — 둘 다 KST 날짜."""

async def sum_by_kind(db: AsyncSession, start: datetime, end: datetime) -> list[KindRow]: ...
async def sum_by_day(db: AsyncSession, start: datetime, end: datetime) -> list[DayRow]: ...
async def sum_by_user(db: AsyncSession, start: datetime, end: datetime) -> list[UserRow]: ...

def totals_from(rows: Sequence[KindRow]) -> UsageSums:
    """종류별 합계를 모두 더한다(쿼리 추가 없이)."""
def external_from(rows: Sequence[KindRow]) -> ExternalUsage:
    """종류별 합계에서 외부 사용량 4개를 꺼낸다. 없는 kind는 0."""
def openai_cost(rows: Sequence[KindRow]) -> Decimal:
    """NON_OPENAI_KINDS를 뺀 비용 합."""

async def build_report(db: AsyncSession, from_: date | None, to: date | None, now: datetime) -> UsageReport:
    """§4.4 순서로 응답을 만든다. 읽기만 한다(커밋 없음)."""

router = APIRouter()

@router.get("/usage", response_model=UsageReport)
async def get_usage(from_: date | None = Query(None, alias="from"), to: date | None = Query(None),
                    cu: CurrentUser = Depends(require_admin), db: AsyncSession = Depends(get_db),
                    now: datetime = Depends(get_now)) -> UsageReport:
    """관리자 사용량 대시보드 데이터. 18 admin_router(/api/admin, require_admin 일괄 적용) 아래에 붙는다.
    cu는 로그에 관리자 id를 남기려고 받는다(라우터의 require_admin과 같은 요청 안에서 한 번만 실행됨)."""
```

### 4.4 처리 순서 (`build_report`)
1. `from_, to = resolve_range(from_, to, now)` — 잘못이면 400.
2. `start, end = kst_bounds(from_, to)`.
3. 기간 집계 3개: `sum_by_kind`·`sum_by_day`·`sum_by_user`(같은 `start`·`end`).
4. `totals = totals_from(by_kind)`, `external = external_from(by_kind)`.
5. 이번 달: `m_start_day, m_end_day = month_range(now)` → `kst_bounds` → `month_kinds = sum_by_kind(...)` → `cost = openai_cost(month_kinds)`, `warning = cost > MONTHLY_WARN_USD`, `external_from(month_kinds)`.
6. `UsageReport` 조립. 쿼리는 모두 4개(기간 3 + 이번 달 1) — 행마다 추가 조회 없음.

### 4.5 SQL
공통 조건: `created_at >= :start AND created_at < :end`(UTC 반열린 구간 — §5).

종류별:
```sql
SELECT kind,
       count(*)                          AS calls,
       coalesce(sum(input_tokens), 0)    AS input_tokens,
       coalesce(sum(cached_tokens), 0)   AS cached_tokens,
       coalesce(sum(cache_write_tokens), 0) AS cache_write_tokens,
       coalesce(sum(output_tokens), 0)   AS output_tokens,
       coalesce(sum(units), 0)           AS units,
       coalesce(sum(cost_usd), 0)        AS cost_usd
FROM usage_events
WHERE created_at >= :start AND created_at < :end
GROUP BY kind
```
→ Python에서 `USAGE_KINDS` 순서로 정렬. `units`는 `int(round(값))`(실제 값은 모두 정수 — 11·17).

일자별:
```sql
SELECT (created_at AT TIME ZONE 'Asia/Seoul')::date AS day, count(*) AS calls, …(토큰·비용 합 같은 식)
FROM usage_events
WHERE created_at >= :start AND created_at < :end
GROUP BY 1 ORDER BY 1 DESC
```

사용자별:
```sql
SELECT e.user_id, u.username, count(*) AS calls, …(토큰·비용 합 같은 식)
FROM usage_events e LEFT JOIN users u ON u.id = e.user_id
WHERE e.created_at >= :start AND e.created_at < :end
GROUP BY e.user_id, u.username
ORDER BY cost_usd DESC, u.username ASC NULLS LAST
```
- 앱이 쓰는 DB 롤 `nadri_app`은 `users`·`usage_events` 읽기 권한이 있다(04 — api 롤).

### 4.6 라우터 연결 (18 `admin/router.py`, 18 spec §9 약속)
- `usage.py`에 `router = APIRouter()`(접두어 없음, 경로 `/usage`) → 18 `router.py`에 `admin_router.include_router(usage.router)` 1줄 → 경로 `/api/admin/usage`.
- 권한 검사는 18 `admin_router`의 `dependencies=[Depends(require_admin)]`가 한다. 19 엔드포인트의 `cu = Depends(require_admin)` 인자는 로그용 관리자 id를 얻기 위한 것(FastAPI가 같은 의존성을 요청당 한 번만 실행 — 검사가 두 번 돌지 않음).
- 18 test A-ADR-06("`/api/admin`으로 시작하는 모든 경로에 `require_admin`")이 19 경로도 자동 검사한다.

### 4.7 사용자 문구 (`errors.py`에 추가)
| code | HTTP | 상수 | 문구 |
|---|---|---|---|
| `invalid_range` | 400 | `MSG_INVALID_RANGE` | 조회 기간을 확인해 주세요. 시작일은 종료일보다 늦을 수 없고, 최대 366일까지 볼 수 있어요. |

- 날짜 형식 오류(`from=2026-13-01`, `abc`)는 FastAPI 기본 422 → 화면은 14 `MSG_VALIDATION`("입력값을 확인해 주세요.").
- 일반 사용자 → 05 `forbidden` 403 "접근 권한이 없어요.", 로그인 안 함 → 401.

---

## 5. 기간·월 경계 (KST)

| 구간 | 한국 날짜 | UTC 반열린 구간 |
|---|---|---|
| 하루 2026-11-21 | 11-21 | `[2026-11-20T15:00Z, 2026-11-21T15:00Z)` |
| 11월 전체 | 11-01 ~ 11-30 | `[2026-10-31T15:00Z, 2026-11-30T15:00Z)` |
| 12월 → 1월 넘어감 | 2026-12-01 ~ 2026-12-31 | 끝 = `2027-01-01 00:00 KST` = `2026-12-31T15:00Z` |

- "하루"·"이번 달"은 프로젝트 전체 규칙대로 **KST**([A] §5.1, 11 한도와 같은 날짜). OpenAI 청구 화면이 쓰는 날짜 기준(UTC로 알려짐)은 **미확인** — 대조(HITL-2)에서 UTC 날짜로도 합을 뽑아 비교한다(19-Q1).
- `kst_bounds`는 `datetime.combine(day, time(0), tzinfo=KST)`를 UTC로 바꿔 만든다(한국은 서머타임 없음 — 하루 = 24시간).
- 이번 달 카드는 조회 기간과 무관하게 `now` 기준 이번 달. 지난달을 기간으로 골라도 카드는 이번 달.
- 매달 1일 00:00 KST에 누적이 0부터 다시 시작한다(경고도 풀림).

---

## 6. 화면

### 6.1 `web/lib/admin-usage.ts`
```ts
/** GET /api/admin/usage 응답(서버 §4.2와 같은 모양) */
export type UsageSums = { calls: number; input_tokens: number; cached_tokens: number; cache_write_tokens: number; output_tokens: number; cost_usd: string };
export type KindRow = UsageSums & { kind: UsageKind; units: number };
export type DayRow = UsageSums & { day: string };
export type UserRow = UsageSums & { user_id: number | null; username: string | null };
export type ExternalUsage = { moderation_calls: number; tavily_credits: number; elevenlabs_chars: number; stt_seconds: number };
export type MonthSummary = { month: string; start: string; end: string; openai_cost_usd: string; warn_threshold_usd: string; warning: boolean; external: ExternalUsage; tavily_free_credits: number };
export type UsageReport = { from: string; to: string; timezone: "Asia/Seoul"; totals: UsageSums; external: ExternalUsage; by_kind: KindRow[]; by_day: DayRow[]; by_user: UserRow[]; month: MonthSummary };
export type UsageKind = "answer" | "verify" | "classify" | "moderation" | "title" | "summary" | "embed" | "stt" | "tts" | "web_search" | "hub" | "eval" | "proposal";

/** 기간을 붙여 사용량을 받아 온다. 빈 값은 쿼리에서 뺀다(서버 기본값 사용). */
export function getAdminUsage(from?: string, to?: string): Promise<UsageReport>;   // apiJson("/api/admin/usage?from=…&to=…")
/** 금액 문자열을 화면용으로: 0 → "$0", 1 미만 → 소수 4자리("$0.0019"), 1 이상 → 소수 2자리("$3.12"). */
export function formatUsd(s: string): string;
/** 정수를 천 단위 쉼표로("12,345"). */
export function formatInt(n: number): string;
/** kind 한글 이름(아래 표). */
export const KIND_LABELS: Record<UsageKind, string>;
/** kind별 units 단위 — 없으면 null(표에 "—"). */
export function unitLabel(kind: UsageKind): string | null;
```
- `formatUsd`는 표시용이라 `Number()` 변환을 써도 된다(합계 비교는 서버가 함).

| kind | 한글 이름 | units 단위 |
|---|---|---|
| `answer` | 답변 | — |
| `verify` | 답변 검증 | — |
| `classify` | 질문 분류(입력 검사) | — |
| `moderation` | 안전 검사(Moderation, 무료) | 건 |
| `title` | 대화 제목 | — |
| `summary` | 대화 요약 | — |
| `embed` | FAQ 임베딩 | — |
| `stt` | 음성 인식(STT) | 초 |
| `tts` | 음성 읽기(ElevenLabs) | 자 |
| `web_search` | 웹 검색(Tavily) | 크레딧 |
| `hub` | 지역 안내 페이지 작성 | — |
| `eval` | 품질 평가 | — |
| `proposal` | 개선안 작성 | — |

### 6.2 `web/app/admin/usage/page.tsx` (`"use client"`)
상태: `loading → ready | error`. 처음 열면 `getAdminUsage()`(기간 없음 → 서버가 이번 달 1일~오늘), 응답의 `from`·`to`로 날짜 칸을 채운다.

위에서 아래 순서:
1. **경고 배너**(`month.warning`일 때만, `role="alert"`, 눈에 띄는 색): "이번 달 OpenAI 비용이 $10를 넘었어요(현재 {formatUsd(openai_cost_usd)}). 사용은 막지 않아요. OpenAI 대시보드에서 실제 금액을 확인해 주세요."
2. **이번 달 카드**: 제목 "이번 달 비용 ({YYYY}년 {M}월, 한국 시간)" · 큰 글씨 `formatUsd(openai_cost_usd)` + " / 경고 기준 $10" · 배지 **"앱 기록 기준 추정"** · 설명 한 줄(§6.3 `ESTIMATE_NOTE`) · 외부 사용량 4줄:
   - "웹 검색(Tavily): {tavily_credits} / {tavily_free_credits} 크레딧(무료 한도)"
   - "음성 읽기(ElevenLabs): {elevenlabs_chars}자"
   - "음성 인식(STT): {stt_seconds}초(약 {ceil(초/60)}분)"
   - "안전 검사(Moderation): {moderation_calls}건(무료)"
3. **기간 조회 폼**: `<input type="date">` 시작일·종료일(라벨 연결) + [조회] 버튼. 제출 → `getAdminUsage(from, to)`. 제출 중 버튼 비활성.
4. **기간 합계**: 호출 수·입력·캐시 읽기·캐시 쓰기·출력 토큰·비용 한 줄 + 외부 사용량(기간) 같은 4줄 형식.
5. **종류별 표**: 열 = 종류 · 호출 · 입력 · 캐시 읽기 · 캐시 쓰기 · 출력 · 사용량(`units` + 단위, 단위 없으면 "—") · 비용.
6. **일자별 표**: 날짜 · 호출 · 입력 · 캐시 읽기 · 캐시 쓰기 · 출력 · 비용.
7. **사용자별 표**: 사용자(`username`, `user_id`가 null이면 "시스템(배치)") · 호출 · 토큰 4종 · 비용.

- 기간에 행이 없으면 4~7 자리에 "이 기간에 기록된 사용량이 없어요." 한 줄(이번 달 카드는 그대로).
- 표는 가로 스크롤 상자(`overflow-x-auto`) 안 — 휴대폰 화면 폭에서 페이지 전체가 가로로 넘치지 않게.
- 오류: `ApiError.message`를 폼 위 알림(`role="alert"`)에 그대로. 401이면 `router.replace("/login")`(18 사용자 화면과 같은 규칙), 403 `forbidden`이면 문구만(보통은 18 `AdminShell`이 먼저 막음).
- 데이터는 브라우저에서만 `/api` 호출(ADR-12). 자동 새로고침 없음.

### 6.3 화면 고정 문구 (`admin-usage.ts` 상수)
| 상수 | 문구 |
|---|---|
| `ESTIMATE_NOTE` | 앱이 기록한 호출만 더한 추정치예요. LightRAG 내부 호출(문서 색인·키워드 추출)은 빠져 있어 실제 청구액보다 적을 수 있어요. |
| `MSG_WARN` | 이번 달 OpenAI 비용이 $10를 넘었어요(현재 {cost}). 사용은 막지 않아요. OpenAI 대시보드에서 실제 금액을 확인해 주세요. |
| `MSG_EMPTY` | 이 기간에 기록된 사용량이 없어요. |
| `SYSTEM_USER_LABEL` | 시스템(배치) |

### 6.4 관리자 메뉴 (18 `components/admin/AdminShell.tsx`)
- `ADMIN_NAV`에 `{ href: "/admin/usage", label: "사용량" }`을 `사용자` 뒤에 더한다. 현재 경로 강조(`aria-current="page"`)는 18 방식 그대로.
- 관리자 확인은 18 `AdminShell`이 한다(`useMe().role !== "admin"`이면 children을 그리지 않음 → 사용량 API 호출도 없음). 서버 판단은 api(`require_admin`).
- `/admin` 첫 화면은 18대로 사용자 목록(`redirect("/admin/users")`) — 바꾸지 않는다.

---

## 7. 엣지케이스

| 상황 | 동작 |
|---|---|
| 쿼리 없음 | 이번 달 1일 ~ 오늘(KST) |
| `to`만 2026-10-15 | 2026-10-01 ~ 2026-10-15 |
| `from`만 2026-11-05, 오늘 11-22 | 11-05 ~ 11-22 |
| `from`만, 미래 날짜(오늘보다 뒤) | `from > to(오늘)` → 400 `invalid_range` |
| `from`·`to` 둘 다 미래 | 200, 빈 표(오류 아님) |
| `from > to` | 400 `invalid_range` |
| 366일 / 367일 | 200 / 400 |
| `from=2026-13-01`·`abc` | 422 |
| 행의 `created_at` = 2026-11-21T14:59:59Z / 15:00:00Z | 일자별 11-21 / 11-22 |
| 기간 끝 날의 KST 23:59:59 행 | 포함(끝은 다음 날 00:00 KST 미만) |
| 토큰 NULL 행(Moderation·STT·web_search, 또는 usage 미수신 — A19) | `calls`에는 셈, 토큰 합에는 0으로(COALESCE). 비용은 행에 기록된 값 |
| 단가 모르는 모델로 기록된 행(11: 비용 0 + WARNING) | 그대로 0으로 더함 — 추정치가 낮아질 수 있음(HITL-2에서 드러남) |
| 장애 턴(미차감)의 비용 행 | 포함(11-Q2 — 실제 나간 비용) |
| 실패해서 기록 안 된 호출(Moderation 장애·STT 502·TTS 502) | 없음 — 화면에도 없음 |
| `user_id` NULL 행(배치·평가) | 사용자별 "시스템(배치)" 한 줄 |
| 관리자 본인 사용량 | 다른 사용자와 똑같이 집계(관리자는 한도만 없음) |
| 사용자 삭제로 `user_id`가 NULL이 된 행 | "시스템(배치)"에 합쳐짐 — 앱에 사용자 삭제 기능이 없어(18은 비활성화만) 실제로는 생기지 않음 |
| 이번 달 OpenAI 비용 정확히 $10.00000000 | 경고 없음(`>`) |
| $10.00000001 | 경고 |
| tts 행에 비용이 있다면(11이 바뀌는 경우) | `openai_cost_usd`에서 빠짐(`NON_OPENAI_KINDS`), 기간 `totals.cost_usd`에는 포함 |
| Tavily 이번 달 크레딧 1,000 이상 | 숫자만 "1,034 / 1,000 크레딧"(경고 없음 — 19-Q4). Tavily 쪽 월 초기화 날짜가 달력 월인지 **미확인** |
| 매월 1일 00:00 KST 직후 | 이번 달 누적 0(행 없음), 경고 없음 |
| 일반 사용자·pending 사용자 | 403 `forbidden`(05 `require_admin`) |
| disabled 관리자 | 401(05 `current_user` — 세션이 지워짐, 18) |
| `POST /api/admin/usage` | 405 |
| 휴대폰 폭 | 표만 가로 스크롤 |

---

## 8. 앞 작업과 달라지는 점 · 앞 작업 테스트 수정

| # | 내용 | 대상 | 처리 |
|---|---|---|---|
| 1 | 18 `admin/router.py`에 usage 라우터 포함 1줄 | 18 라우터 테스트 | 수정 없음(경로 추가만) |
| 2 | 18 `ADMIN_NAV`에 "사용량" | 18 Vitest V-AS-02(링크 모두 표시)·V-AS-03(`ADMIN_NAV[0]` = 사용자) | 수정 없음(맨 뒤에 붙이므로 `[0]` 그대로, V-AS-02는 목록을 순회). 목록 길이를 고정 비교하는 테스트가 생기면 2로 |
| 3 | 14 `global-setup.ts`에 `delete from usage_events where user_id in (select id from users where username like 'e2e\_%')`를 **사용자 삭제보다 먼저** 추가 | 14·18 Playwright | 수정 없음(정리만 늘어남). 이게 없으면 e2e 사용자(18 `makeAdmin`의 `e2e_admin_*` 포함)를 지울 때 `user_id`가 NULL(SET NULL)이 돼 가짜 사용량이 "시스템(배치)"로 개발 DB에 남는다 |
| 4 | `errors.py`에 `invalid_range` | 05 문구 상수 목록 테스트(목록을 고정 비교하면) | 목록에 추가 |
| 5 | 백엔드 다른 코드 변경 없음(읽기 전용) | — | — |

상위 문서와의 차이·발견(구현 판단):
1. **월 경계 = KST 달력 월**([A] §5.1 "하루는 KST" 연장). OpenAI 청구 기준(UTC 추정, **미확인**)과 하루 9시간 어긋날 수 있다 → HITL-2에서 UTC 날짜 합도 뽑는다(19-Q1).
2. "$10 경고"의 대상은 **OpenAI 비용**(FR-63 문구) — `web_search`·`tts`를 뺀 합. 지금은 둘 다 비용 0이라 전체 합과 같다.
3. [A] §7 디렉터리 주석에 `admin/(users, quota, usage, quality/)`가 남아 있다 — `quota` 화면은 2026-11-22 한도 추가 요청 삭제로 없어졌다. [PL] §1.2 그래프의 `18 admin-users-quota` 이름도 옛 이름. 19는 따르지 않는다(문서 정리 필요 — 보고만).
4. [PL] 의존은 18만 적었지만 실제로 읽는 데이터는 11(`usage_events`·비용)·12·17·20·24가 쓴다. 19는 행이 있는 kind만 보여 주므로 17·20·24 병합 전이어도 동작한다.

---

## 9. 가정 판정

| ID | 확인 방법 | 통과 기준 | 실패 시 |
|---|---|---|---|
| **A14** LightRAG 내부 사용량 집계 불가 | HITL-3: LightRAG 서버 OpenAPI 경로 목록에서 사용량·토큰 관련 경로 유무 확인 + HITL-2 차이 기록 | 사용량 경로 없음 → "앱 기록 기준 추정" 표기 유지(가정대로) | 경로가 있으면 **멈추고 사용자에게 보고**(집계에 넣을지 결정 — 범위 변경). 차이가 커서 문제면 19-Q5 대안(서비스별 OpenAI 키) |
| **A28** Tavily 월 1,000크레딧 안 | HITL-5: 이번 달 `tavily_credits`와 Tavily 대시보드 사용량 비교, 하루 평균 × 30 계산 | 월 1,000 안으로 예상 | [A] 대안: 웹 툴 설명에 "공공데이터에 없을 때만" 강화(08·02 프롬프트 작업 — 사용자 확인 후) |
| 비용 대조 | HITL-2: 하루 단위 앱 합계 vs OpenAI 대시보드 | 차이와 이유를 **기록만**(통과·실패 없음) | 차이가 앱 기록 누락으로 보이면(예: 단가 모르는 모델 0원) 11 단가표 수정 제안 |

결과는 이 spec 끝 또는 `PROGRESS.md` 결정 로그에 남긴다([PL] §1.1 8).

---

## 10. 완료 기준 (DoD)

1. test.md ① pytest 전부 통과(`cd ~/code/myAgent/backend && uv run pytest -m "not integration"`), §8 앞 작업 테스트 수정 후 통과.
2. `cd ~/code/myAgent/web && npm run typecheck && npm run test && npm run e2e` 통과(① Vitest·Playwright).
3. 관리자만 200, 일반 사용자 403, 로그인 안 함 401.
4. KST 날짜·월 경계(UTC 15:00, 12월→1월), 기간 검사(366/367일, from>to), $10 경계(같음 → 경고 없음, 넘음 → 경고) 테스트 통과.
5. 화면에 "앱 기록 기준 추정"과 LightRAG 미포함 설명이 항상 보이고, 경고는 이번 달 OpenAI 비용이 $10를 넘을 때만 보인다.
6. HITL-1~5 결과 보고, §9 A14·A28 판정 기록.
7. 모든 함수·클래스·컴포넌트에 한국어 docstring/JSDoc, 함수 안 단계 주석([CL]). 커밋 `feat/19-admin-usage`, `[Feat] …` + 작업 목록 + `Author:`, AI 공동작성 표기 없음. `dev` 병합은 G5 후. `PROGRESS.md` 갱신.

---

## 11. 확인 질문

| # | 질문 | 추천안 | 대안 |
|---|---|---|---|
| 19-Q1 | "이번 달"·"하루"를 어느 시간대로 자를까. 프로젝트 규칙은 KST, OpenAI 청구 화면은 UTC로 알려져 있다(**미확인**) | **결정(2026-11-22): 추천안대로** — **KST 달력 월·KST 날짜**(한도·평가 등 앱 전체와 같음). 대조할 때만 UTC 날짜 합을 따로 뽑는다(HITL-2) | UTC 월·날짜(OpenAI 청구와 맞음, 대신 화면 날짜가 앱의 다른 곳과 9시간 어긋남) |
| 19-Q2 | 화면 구성 | **결정(2026-11-22): 추천안대로** — **표 3개(종류별·일자별·사용자별) + 이번 달 카드**, 차트 없음 | 일자×사용자×종류 전체 표(행 많음) / 일자별 막대 차트(차트 라이브러리 추가) |
| 19-Q3 | $10 경고를 어디에 보일까 | **결정(2026-11-22): 추천안대로** — **사용량 화면에만**(FR-63 "관리자 대시보드에 경고") | 모든 관리자 화면 위(18 `AdminShell`이 화면마다 사용량 API 호출) |
| 19-Q4 | Tavily 월 1,000크레딧 | **결정(2026-11-22): 추천안대로** — **"n / 1,000 크레딧" 숫자만**, 경고 없음(A28은 추이 확인) | 800 이상이면 노란 경고도 표시 |
| 19-Q5 | LightRAG 내부 비용(앱 집계 불가, A14) | **결정(2026-11-22): 추천안대로** — **"앱 기록 기준 추정" 표기만**. 서비스별 OpenAI 키 분리는 HITL-2 차이를 본 뒤 다시 결정 | 지금 lightrag 전용 OpenAI 키를 따로 발급해 OpenAI 대시보드에서 키별로 보기([A] §9 "선택", `.env`·compose 변경 — 26 범위) |
| 19-Q6 | 조회 기간 기본값·상한 | **결정(2026-11-22): 추천안대로** — **기본 이번 달 1일~오늘, 최대 366일** | 상한 없음 / 최대 92일 |
| 19-Q7 | `usage_events.created_at` 인덱스 | **결정(2026-11-22): 추천안대로** — **만들지 않음**(1~5명, 하루 수백 행 — 전체 훑기로 충분) | 새 테이블 생성 스크립트(`0004`)로 `ix_usage_events_created_at` 추가 |
| 19-Q8 | 18과의 연결 — 18 spec도 아직 초안 | **결정(2026-11-22): 추천안대로** — **18 초안 §9 약속대로**: `admin_router.include_router(usage.router)` 1줄, `ADMIN_NAV`에 "사용량" 1개, 화면 API 함수는 별도 파일 `web/lib/admin-usage.ts`, e2e 관리자는 18 `makeAdmin` | API 함수를 18 `admin-api.ts`에 합침 / 18 확정본이 바뀌면 그 구조를 따름 |
| 19-Q9 | Playwright 실제 compose 테스트가 넣는 가짜 사용량 행 정리 | **결정(2026-11-22): 추천안대로** — **14 `global-setup.ts`에 e2e 사용자의 `usage_events` 삭제를 추가**(사용자 삭제 전에) | 19 테스트가 끝날 때만 지움(테스트가 중간에 실패하면 남음) |
