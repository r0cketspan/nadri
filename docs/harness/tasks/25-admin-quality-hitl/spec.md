# 25-admin-quality-hitl — 관리자: 품질 리포트·개선안 결정 (spec)

> 하네스 Phase 4 산출물 (spec-writer, 작성 2026-11-22). 상태: **초안 — 확인 질문 대기**(마지막 절 표). 브랜치 `feat/25-admin-quality-hitl`, 의존 작업 18-admin-users(→ 05·14), 24-eval-daily-quality(→ 23·22·…).
> 근거: [PL]=program_list.md(G4 승인본, 2026-11-22 개정) §2 표·§3 "25-admin-quality-hitl"·"24-eval-daily-quality"·§5 X-d · [A]=architecture.md(G3 재승인본) §2.1 web(`/admin` 품질 리포트)·§3.7(03:00 평가 → 개선안 → HITL)·§3.8 끝줄·§5.1 `eval_reports`·`eval_scores`·`improvement_proposals`·§6.1 품질 API 4개·§7(`web/app/admin/quality/`)·ADR-12·ADR-23·§13("보안 이벤트 전용 화면" 없음, "개선안 자동 적용·자동 PR" 없음) · [R]=requirements.md FR-100·101·102·105, NFR-05·10·14·36 · [E]=erd.md(한글 명칭 정본) · [PG]=PROGRESS.md 결정 로그(18~22 확인 질문 결정, 21-Q7).
> **이어받는 확정 spec**: [04](`EvalReport`·`EvalScore`·`ImprovementProposal`·`EVAL_REPORT_STATUSES`(running·done·skipped·failed)·`PROPOSAL_TARGETS`(7종)·`PROPOSAL_PRIORITIES`(high·medium·low)·`PROPOSAL_STATUSES`(new·adopted·held·rejected)·`improvement_proposals.report_id` SET NULL·`decided_by` SET NULL·`FEEDBACK_REASONS`·`VERIFY_STATUSES`) · [05](`require_admin`·`CurrentUser`·`get_db`·`get_now`·`ApiError(status, code, message, extra=)`·`errors.py`·`MSG_FORBIDDEN`·CSRF 미들웨어(POST 전부)·테스트 헬퍼 `make_user`·`login`·`post`·`clock`) · [11](`kst_day`) · [14](`apiJson`·`ApiError`(web)·`MSG_VALIDATION`·Playwright 설정·`e2e/helpers/db.ts`·`global-setup.ts`) · [15](`SafeMarkdown`) · [16](`REASON_LABELS` — 👎 사유 한글 이름) · [18](`admin_router`(`/api/admin`, `require_admin` 일괄)·A-ADR-06 권한 누락 검사·`AdminShell.tsx`의 `ADMIN_NAV`·`formatKst`·`makeAdmin`) · [19](`invalid_range`·`MSG_INVALID_RANGE`·`MAX_RANGE_DAYS` 366 — 25-Q6) · [21](90일 정리 C3·C4·C5 — 보류 → 나중에 기각 전이를 전제, 21-Q7) · [23](`ATTACK_TYPES` 9개) · [24](`stats` §9·`body_md` §10.2·개선안 §12.4·상태 §4.1·§4.2·계약 §16).
> **24·23 확정본 반영(2026-11-22)**: 집계 JSON 키·모양은 24 spec §9(정본 표)·§16(25 계약), 보고서 상태·단계 실패는 24 §4.1·§4.2, 개선안 필드·대상은 24 §12.4, 공격 유형 9개는 23 spec §4.2(`ATTACK_TYPES`)를 따른다. 24-Q1(대상 `faq_cache` 추가)이 채택되면 대상 이름표에 1줄이 붙는다.
> **미확인** = 문서·공식 자료로 확인하지 못한 사실.

---

## 1. 작업 목표

24가 매일 만든 **품질 보고서**(`eval_reports`)와 **개선안**(`improvement_proposals`, status=new)을 관리자가 읽고, 개선안마다 **채택·보류·기각 + 메모**를 남긴다 [R] FR-102, [A] §3.7 HITL.

- `GET /api/admin/quality/reports?from=&to=` — 보고서 목록(대상 날짜·상태·핵심 지표 몇 개·개선안 결정 현황).
- `GET /api/admin/quality/reports/{id}` — 보고서 1개: 본문(요약문)·집계 JSON 전체·그 보고서의 개선안 목록. 공격 질문 세트 결과(방어율·유형별·실패 id)는 집계 JSON의 `attack_set`에 있다(FR-105, 24 §9).
- `GET /api/admin/quality/proposals?status=` — 개선안 목록. `status=adopted` = **개발 후보** 목록.
- `POST /api/admin/quality/proposals/{id}/decision {status, note}` — 결정 기록 → `status`·`decision_note`·`decided_by`·`decided_at`.
- 화면 3개: `/admin/quality`(보고서 목록) · `/admin/quality/[reportId]`(보고서 + 개선안 결정) · `/admin/quality/proposals`(개선안 목록, 기본 탭 = 개발 후보).
- 관리자 메뉴(18 `ADMIN_NAV`)에 "품질" 1개.
- **채택해도 아무것도 자동으로 바뀌지 않는다**(ADR-23). 결정 API는 `improvement_proposals` 1행만 고친다 — 프롬프트·설정·파일·다른 테이블을 건드리는 코드가 없다(§9 DoD 4, test A-QH-30).

### 1.1 넣지 않는 것
| 빠지는 것 | 들어오는 작업 / 이유 |
|---|---|
| 보고서·개선안 **만들기**, 채점 기준, 집계 계산 | 24 |
| 공격 질문 세트 내용·판정 | 23(세트)·24(매일 실행·집계) |
| 실패한 보고서 다시 실행 버튼 | 24 CLI `nadri eval quality --date`(화면 없음 — [A] §3.7 8) "CLI로 수동") |
| 채택안 자동 적용·자동 PR·프롬프트 자동 교체 | 범위 밖(ADR-23, [A] §13) |
| 보안 이벤트 전용 화면 | 범위 밖([A] §13) — 보고서의 보안 이벤트 요약으로 대신 |
| 턴별 채점(`eval_scores`) 목록·대화 원문 보기 | 넣지 않음(25-Q5) — 24 본문(`body_md`)에 "점수가 낮은 턴(최대 10)"이 이미 있고, 집계·근거 발췌로 충분. 대화 노출 범위를 늘리지 않음 |
| 결정 이력(누가 언제 무엇을 바꿨는지 여러 번) | ERD에 테이블 없음 — 마지막 결정만 행에 남고, 바뀔 때마다 로그 1줄(25-Q3) |
| 결정 대기 개선안 수 배지(메뉴)·알림 | 요구 없음 — 메뉴가 화면마다 API를 불러야 함(25-Q8) |
| 개선안 목록 페이지 나누기·검색 | 하루 몇 건 × 90일(new·rejected는 21이 지움) — 넣지 않음(25-Q9) |
| 개선안 내용(문제·제안 등) 수정 | 요구 없음 — 사람은 결정과 메모만 쓴다 |
| 차트 | 19와 같은 판단 — 표·숫자로 충분 |
| 관리자 화면 틀·관리자 확인 | 18 |

---

## 2. 생성·수정 파일

경로의 `nadri/`는 `backend/src/nadri/`.

| 파일 | 신규/수정 | 역할 |
|---|---|---|
| `nadri/api/admin/quality.py` | 신규 | 요청·응답 모델, 조회·결정 서비스 함수, 엔드포인트 4개 (§4·§5) |
| `nadri/api/admin/router.py` | 수정(18) | `admin_router.include_router(quality.router)` 1줄 (§4.7) |
| `nadri/api/errors.py` | 수정(05) | `report_not_found`·`proposal_not_found`·`proposal_status_conflict` 코드·문구 (§4.6) |
| `web/lib/admin-quality.ts` | 신규 | 타입, API 함수 4개, 한글 이름표, 집계 JSON 나누기(`splitStats`)·서식 함수 (§6.1) — 19 `admin-usage.ts`처럼 18 `admin-api.ts`와 따로 둠 |
| `web/components/admin/ProposalCard.tsx` | 신규 | 개선안 1건 카드 + 결정 버튼·메모 (§6.5) — 보고서 화면·개선안 목록 화면이 함께 씀 |
| `web/app/admin/quality/page.tsx` | 신규 | 보고서 목록 (§6.2) |
| `web/app/admin/quality/[reportId]/page.tsx` | 신규 | 보고서 1개 + 개선안 결정 (§6.3) |
| `web/app/admin/quality/proposals/page.tsx` | 신규 | 개선안 목록(기본 = 개발 후보) (§6.6) |
| `web/components/admin/AdminShell.tsx` | 수정(18) | `ADMIN_NAV`에 `{ href: "/admin/quality", label: "품질" }`, 현재 메뉴 판정을 "앞부분 일치"로 (§6.7, 25-Q8) |
| `web/e2e/helpers/db.ts` | 수정(14·18) | `makeQualityReport()` 헬퍼 (test.md C) |
| `web/e2e/global-setup.ts` | 수정(14) | e2e 보고서·개선안 정리 2줄 (§8 #4) |
| `backend/tests/api/admin/test_quality_*.py`, `web/tests/unit/admin-quality.test.ts`, `web/tests/unit/proposal-card.test.tsx`, `web/e2e/admin-quality.spec.ts`, `web/e2e/fixtures/quality/*.json` | 신규 | test.md |

> [PL] 파일 목록 밖: `admin/router.py`·`AdminShell.tsx`(18 약속대로 연결 1줄씩), `errors.py`, `web/lib/admin-quality.ts`(나누기·서식 함수를 Vitest로 검사하려고 페이지에서 분리), `ProposalCard.tsx`(두 화면에서 같은 결정 UI를 씀 — 25-Q4), e2e 헬퍼·정리.

---

## 3. 설정 · 상수

새 환경변수 없음. DB 변경 없음(04 테이블 그대로). compose·nginx 변경 없음(`/admin/*`는 14 nginx가 web으로, `/api/admin/*`는 api로).

| 상수 | 위치 | 값 | 근거 |
|---|---|---|---|
| `DECISION_STATUSES` | `admin/quality.py` | `("adopted", "held", "rejected")` | [A] §6.1 결정 값. `new`로 되돌리기 없음(25-Q2) |
| `NOTE_MAX_LEN` | `admin/quality.py` | `1000` | 메모 글자 수 상한(25-Q3) |
| `DEFAULT_RANGE_DAYS` | `admin/quality.py` | `30` | 목록 기본 기간 = 최근 30일(25-Q6) |
| `MAX_RANGE_DAYS` | `admin/usage.py`(19) | `366` | 재사용(25-Q6) |
| `PRIORITY_ORDER` | `admin/quality.py` | `{"high": 0, "medium": 1, "low": 2}` | 개선안 정렬 |
| `HEADLINE_PATHS` | `admin/quality.py` | §5.2 표 (24 §16 "목록 표에 쓸 값") | 목록의 핵심 지표 |
| `STEP_NAMES` | `admin/quality.py` | `("collect", "scoring", "attack_set", "summary", "proposals")` | 24 §4.2 `stats.steps` 키 |
| `kst_day` | `api/quota.py`(11) | — | 재사용 |
| `PROPOSAL_STATUSES`·`PROPOSAL_TARGETS`·`PROPOSAL_PRIORITIES`·`EVAL_REPORT_STATUSES` | `core/models/quality.py`(04) | — | 쿼리 검사·Literal 대조 테스트 |

---

## 4. API

모두 18 `admin_router` 아래(관리자만). 오류 본문은 05 `{"code","message"}`. POST는 05 CSRF 미들웨어 적용.

### 4.1 엔드포인트
| 메서드·경로 | 요청 | 성공 | 실패 |
|---|---|---|---|
| `GET /api/admin/quality/reports` | 쿼리 `from`·`to` — 둘 다 선택, `YYYY-MM-DD`(`report_date` 기준, 양 끝 포함) | 200 `ReportListOut` | 400 `invalid_range` / 422 / 401 / 403 |
| `GET /api/admin/quality/reports/{report_id}` | — | 200 `ReportDetailOut` | 404 `report_not_found` / 422(경로 형식) / 401 / 403 |
| `GET /api/admin/quality/proposals` | 쿼리 `status?: new\|adopted\|held\|rejected`(없으면 전체) | 200 `ProposalListOut` | 422(허용 밖 status) / 401 / 403 |
| `POST /api/admin/quality/proposals/{proposal_id}/decision` | `DecisionIn` | 200 `ProposalOut`(바뀐 뒤 값) | 404 `proposal_not_found` / 409 `proposal_status_conflict` / 422 / 403 `csrf_failed` / 401 / 403 |

- 경로 id: `Path(ge=1, le=2**63 - 1)`(18과 같은 방식 — bigint 넘침 500 방지).
- 요청 제한 없음(관리자만, 외부 호출·비용 없음 — 18·19와 같은 판단).
- 권한 검사 순서는 18 §4.1 그대로(CSRF → `require_admin` → 형식 검사).

### 4.2 모델 (`admin/quality.py`)
```python
ProposalStatus = Literal["new", "adopted", "held", "rejected"]
DecisionStatus = Literal["adopted", "held", "rejected"]
ReportStatus = Literal["running", "done", "skipped", "failed"]

class ProposalCounts(BaseModel):
    """보고서 1개의 개선안 결정 현황(없는 상태는 0)."""
    new: int
    adopted: int
    held: int
    rejected: int

class ReportSummaryOut(BaseModel):
    """보고서 목록의 한 줄."""
    id: int
    report_date: date
    status: ReportStatus
    started_at: datetime
    finished_at: datetime | None
    headline: dict[str, int | float | str | None]   # HEADLINE_PATHS의 이름 → 값(없거나 숫자·문자열이 아니면 None)
    steps: dict[str, str]                            # stats.steps 중 STEP_NAMES 키이고 값이 문자열인 것만(없으면 {}) — 목록의 "일부 실패" 표시용
    proposal_counts: ProposalCounts

class ReportListOut(BaseModel):
    """GET /reports 응답."""
    model_config = ConfigDict(populate_by_name=True)
    from_: date = Field(serialization_alias="from")
    to: date
    reports: list[ReportSummaryOut]                   # report_date 최신순

class ProposalOut(BaseModel):
    """개선안 1건. 화면에 그대로 보여 준다(글은 모두 24가 만든 가린·익명 텍스트)."""
    id: int
    report_id: int | None              # 90일 정리로 보고서가 지워지면 None(04 SET NULL, 21 C5)
    report_date: date | None           # eval_reports LEFT JOIN — report_id가 None이면 None
    seq: int
    target: str                        # PROPOSAL_TARGETS(24-Q1 채택 시 faq_cache 포함)
    title: str
    problem: str
    evidence: list[Any]                # jsonb 그대로 — 24 §12.4: [{type: turn|stat|attack|security, ref, quote|null, note}] 1~5개. 90일 지나면 [](21 C4)
    cause: str | None
    proposal: str
    expected_effect: str | None
    cost_note: str | None
    risk: str | None
    priority: str                      # PROPOSAL_PRIORITIES
    status: ProposalStatus
    decision_note: str | None
    decided_by: int | None
    decided_by_username: str | None    # users LEFT JOIN
    decided_at: datetime | None
    created_at: datetime

class ReportDetailOut(BaseModel):
    """GET /reports/{id} 응답."""
    id: int
    report_date: date
    status: ReportStatus
    model: str | None
    started_at: datetime
    finished_at: datetime | None
    error: str | None                  # status=failed일 때 24가 남긴 오류 메시지
    body_md: str | None                # 평가 에이전트 요약문(마크다운)
    stats: dict[str, Any]              # 집계 JSON 그대로 — 해석은 화면(§6.4)
    proposals: list[ProposalOut]       # 이 보고서의 개선안, §4.4 정렬

class ProposalListOut(BaseModel):
    """GET /proposals 응답."""
    proposals: list[ProposalOut]

class DecisionIn(BaseModel):
    """개선안 결정 요청."""
    model_config = ConfigDict(extra="forbid")
    status: DecisionStatus
    note: str | None = None            # 앞뒤 공백 제거 후 빈 문자열이면 None, 1000자 넘으면 422

    @field_validator("note")
    @classmethod
    def _clean_note(cls, v: str | None) -> str | None:
        """메모 앞뒤 공백을 지우고, 비면 None, NOTE_MAX_LEN을 넘으면 ValueError(→ 422)."""
```
- `stats`는 서버가 해석하지 않고 그대로 넘긴다 — 키가 24에서 바뀌어도 API는 안 바뀐다(25-Q1).

### 4.3 시그니처
```python
def resolve_report_range(from_: date | None, to: date | None, now: datetime) -> tuple[date, date]:
    """목록 기간을 정한다(report_date 기준, 양 끝 포함).
    - to 없음 → 오늘(kst_day(now)). from 없음 → to − (DEFAULT_RANGE_DAYS − 1)일.
    - from > to 또는 (to − from).days + 1 > MAX_RANGE_DAYS → ApiError(400, "invalid_range", MSG_INVALID_RANGE)."""

def pick_headline(stats: dict[str, Any]) -> dict[str, int | float | str | None]:
    """HEADLINE_PATHS의 경로로 stats에서 값을 꺼낸다. 경로가 없거나 값이 int·float·str가 아니면(bool 포함) None.
    failed 보고서(stats에 schema·rubric_version·report_date·steps만 — 24 §9)는 모두 None."""

def pick_steps(stats: dict[str, Any]) -> dict[str, str]:
    """stats.steps에서 STEP_NAMES 키의 문자열 값만 꺼낸다. 모양이 다르면 {}."""

def decision_allowed(current: str, to: str) -> bool:
    """current 상태에서 to 결정으로 바꿀 수 있는지(§5.1 표). 순수 함수 — 표 테스트 대상."""

async def list_reports(db: AsyncSession, start: date, end: date) -> list[ReportSummaryOut]: ...
async def get_report(db: AsyncSession, report_id: int) -> ReportDetailOut:
    """Raises: ApiError(404 report_not_found)."""
async def list_proposals(db: AsyncSession, *, status: str | None = None,
                         report_id: int | None = None) -> list[ProposalOut]:
    """status·report_id 조건으로 개선안을 §4.4 순서로 돌려준다(report_date·결정 관리자 이름 포함)."""
async def decide(db: AsyncSession, *, admin_id: int, proposal_id: int,
                 status: str, note: str | None, now: datetime) -> ProposalOut:
    """§4.5 1~5를 처리하고 바뀐 개선안을 돌려준다. 커밋까지 한다.
    Raises: ApiError(404 proposal_not_found / 409 proposal_status_conflict)."""

router = APIRouter(prefix="/quality")
# @router.get("/reports") · @router.get("/reports/{report_id}") · @router.get("/proposals")
# @router.post("/proposals/{proposal_id}/decision") — 결정만 cu: CurrentUser = Depends(require_admin)로 관리자 id를 받는다(18 §4.1 — 검사는 요청당 1번)
```

### 4.4 조회 처리
**목록** (`list_reports`) — 쿼리 1개:
```sql
SELECT r.id, r.report_date, r.status, r.started_at, r.finished_at, r.stats,
       count(p.id) FILTER (WHERE p.status = 'new')      AS new,
       count(p.id) FILTER (WHERE p.status = 'adopted')  AS adopted,
       count(p.id) FILTER (WHERE p.status = 'held')     AS held,
       count(p.id) FILTER (WHERE p.status = 'rejected') AS rejected
FROM eval_reports r LEFT JOIN improvement_proposals p ON p.report_id = r.id
WHERE r.report_date BETWEEN :start AND :end
GROUP BY r.id
ORDER BY r.report_date DESC
```
→ 행마다 `headline = pick_headline(stats)`, `steps = pick_steps(stats)`. `stats` 전체는 목록 응답에 넣지 않는다(공격 실패 id 등으로 커질 수 있음).

**상세** (`get_report`) — 쿼리 2개: `SELECT … FROM eval_reports WHERE id = :id`(없으면 404) + `list_proposals(report_id=id)`.

**개선안** (`list_proposals`) — 쿼리 1개:
```sql
SELECT p.*, r.report_date, u.username AS decided_by_username
FROM improvement_proposals p
LEFT JOIN eval_reports r ON r.id = p.report_id
LEFT JOIN users u ON u.id = p.decided_by
[WHERE p.status = :status] [AND p.report_id = :report_id]
ORDER BY CASE p.priority WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END,
         p.created_at DESC, p.seq, p.id
```
- 정렬 = 우선순위 높은 것 → 최근 보고서 것 → 보고서 안 순번. 개발 후보 목록에서 급한 것이 위에 온다.

### 4.5 결정 처리 (`decide`)
1. `SELECT … FROM improvement_proposals WHERE id = :pid FOR UPDATE` → 없으면 404 `proposal_not_found`.
2. `decision_allowed(현재 status, 요청 status)`가 거짓이면 409 `proposal_status_conflict`, 본문에 `"status": 현재 상태`.
3. `UPDATE improvement_proposals SET status = :to, decision_note = :note, decided_by = :admin_id, decided_at = :now WHERE id = :pid` — **이 행만** 고친다(다른 테이블·파일·설정 없음, ADR-23).
4. 커밋 → `list_proposals`와 같은 JOIN으로 1건 다시 읽어 200 `ProposalOut`.
5. 로그 1줄(INFO): 이벤트 이름 `admin_proposal_decision`, `admin_id`, `proposal_id`, `from`, `to`, `note_len`(메모 글자 수). **메모 내용은 로그에 넣지 않는다**(결정 이력 대신 — 25-Q3).

- 메모는 **덮어쓴다**: 결정을 바꾸면서 `note`를 비워 보내면 이전 메모도 지워진다(화면은 현재 메모를 입력칸에 미리 채워 실수를 줄인다 — §6.5).
- 1의 행 잠금 때문에 같은 개선안에 동시 요청 2건이 오면 차례로 처리된다. 둘이 같은 결정이면 두 번째는 2에서 409(버튼 두 번).

### 4.6 사용자 문구 (`errors.py`에 추가)
| code | HTTP | 상수 | 문구 |
|---|---|---|---|
| `report_not_found` | 404 | `MSG_REPORT_NOT_FOUND` | 품질 보고서를 찾을 수 없어요. |
| `proposal_not_found` | 404 | `MSG_PROPOSAL_NOT_FOUND` | 개선안을 찾을 수 없어요. 90일이 지나 정리됐을 수 있어요. |
| `proposal_status_conflict` | 409 | `MSG_PROPOSAL_STATUS_CONFLICT` | 이미 처리된 개선안이에요. 목록을 새로고침했어요. |
| (19) `invalid_range` | 400 | `MSG_INVALID_RANGE` | 19 문구 그대로 |
| (05) `forbidden` | 403 | `MSG_FORBIDDEN` | 접근 권한이 없어요. |

- `proposal_status_conflict` 본문: `{"code","message","status"}`. 화면은 문구를 보여 주고 목록을 다시 불러온다(그래서 "새로고침했어요" — 18 `user_status_conflict`와 같은 방식).
- 메모 1000자 초과·`status: "new"`·모르는 필드 → FastAPI 기본 422 → 화면 14 `MSG_VALIDATION`("입력값을 확인해 주세요."). 화면은 입력칸 `maxLength=1000`으로 미리 막는다.

### 4.7 라우터 연결 (18 §9 약속)
- `quality.py`에 `router = APIRouter(prefix="/quality")` → 18 `router.py`에 `admin_router.include_router(quality.router)` 1줄 → 경로 `/api/admin/quality/...`.
- 권한 검사는 18 `admin_router`가 한다. 18 test A-ADR-06이 25 경로 4개도 자동 검사한다.

---

## 5. 상태 전이·핵심 지표

### 5.1 결정 전이 (정본 표, 25-Q2 추천안)
| 현재 상태 \ 요청 | adopted | held | rejected |
|---|---|---|---|
| `new`(결정 대기) | → 채택 | → 보류 | → 기각 |
| `held`(보류) | → 채택 | 409 | → 기각 |
| `adopted`(채택) | 409 | → 보류 | → 기각 |
| `rejected`(기각) | → 채택 | → 보류 | 409 |

- 규칙 한 줄: **결정은 다른 결정으로 언제든 바꿀 수 있다. 같은 결정을 다시 보내면 409. `new`로 되돌리기는 없다**(요청 값에 `new`가 없음 → 422).
- `decided_by`·`decided_at`은 바꿀 때마다 새 값으로 덮어쓴다.
- 21과의 관계: 보류 → 기각이 가능해야 21 C3("보고서가 지워진 뒤 기각된 개선안 정리")이 의미가 있다. 이 표는 그 전제를 만족한다. 90일이 지나 보고서가 지워진 개선안도 결정을 바꿀 수 있다(채택·보류만 남아 있으므로 개선안 목록 화면에서) — 기각으로 바꾸면 21 C3이 다음 정리 때 지운다.
- 결정 메모만 고치고 싶을 때(상태는 그대로): 지원하지 않는다(같은 결정 = 409). 필요하면 25-Q3 대안.

### 5.2 목록 핵심 지표 (`HEADLINE_PATHS` — 24 §16 "목록 표에 쓸 값")
| 이름(응답 키) | stats 경로(24 §9) | 화면 열 이름 | 서식 |
|---|---|---|---|
| `turns_answered` | `("conversation", "turns_answered")` | 답변 수 | 정수 |
| `good_rate` | `("scoring", "good_rate")` | 좋은 턴 비율 | 0~1 → % (null → "—") |
| `verify_pass_rate` | `("verification", "pass_rate")` | 검증 통과율 | 0~1 → % |
| `attack_defense_rate` | `("attack_set", "defense_rate")` | 공격 방어율 | 0~1 → % |
| `proposals_created` | `("eval_run", "proposals_created")` | 만든 개선안 | 정수 |

- 응답 키(왼쪽 열)는 25가 정한다 — 화면은 이 키만 본다. 24 키가 바뀌면 **가운데 열만** 바꾼다.
- 경로가 없거나(failed 보고서 — 24 §9 예외, running의 `{}`) 값이 null이면 `None` → 화면 "—". 목록이 깨지지 않는다.
- 목록의 상태 칸: `status`가 `done`인데 `steps` 값 중 `partial`·`failed`가 있으면 "완료(일부 실패)"로 표시(24 §4.2 — 단계 실패여도 `done` 유지).

---

## 6. 화면

공통: 14 규칙(모바일 우선, `<label>` 연결, 처리 중 버튼 비활성, 오류는 `role="alert"`에 `ApiError.message` 그대로, 401이면 `router.replace("/login")`). 데이터는 브라우저에서만 `/api/admin/quality/*` 호출(ADR-12). 일시는 18 `formatKst`(KST `YYYY-MM-DD HH:mm`). 표는 가로 스크롤 상자(`overflow-x-auto`) 안(19와 같음). 자동 새로고침 없음.

**보안**: 보고서 본문·개선안 글·근거 발췌는 **사용자 대화와 공격 질문 세트에서 나온 LLM 글**이다(간접 인젝션 문장·악성 링크가 섞일 수 있음). 그래서
- `body_md`는 15 `SafeMarkdown`으로 그리되 `allowedUrls=[]`, `linksEnabled=false` — raw HTML·이미지 없음, **링크는 모두 클릭 안 되는 글**(25-Q7).
- 개선안의 모든 글 필드·근거 발췌는 **마크다운 없이 일반 텍스트**(React 기본 이스케이프, `whitespace-pre-wrap`). `dangerouslySetInnerHTML` 금지.

### 6.1 `web/lib/admin-quality.ts`
```ts
export type ProposalStatus = "new" | "adopted" | "held" | "rejected";
export type DecisionStatus = Exclude<ProposalStatus, "new">;
export type ReportStatus = "running" | "done" | "skipped" | "failed";
export type ProposalTarget = "system_prompt" | "tool_description" | "reranker" | "verifier" | "guard" | "faq_cache" | "data_scope" | "other";  // faq_cache는 24-Q1 채택 시
/** 개선안 근거 1개(24 §12.4). 화면은 이 모양이 아니어도 깨지지 않게 evidenceLines로 처리 */
export type Evidence = { type: "turn" | "stat" | "attack" | "security"; ref: string; quote: string | null; note: string | null };
export type ProposalPriority = "high" | "medium" | "low";
export type Proposal = { id: number; report_id: number | null; report_date: string | null; seq: number;
  target: ProposalTarget; title: string; problem: string; evidence: unknown[]; cause: string | null;
  proposal: string; expected_effect: string | null; cost_note: string | null; risk: string | null;
  priority: ProposalPriority; status: ProposalStatus; decision_note: string | null; decided_by: number | null;
  decided_by_username: string | null; decided_at: string | null; created_at: string };
export type ReportSummary = { id: number; report_date: string; status: ReportStatus; started_at: string;
  finished_at: string | null; headline: Record<string, number | string | null>; steps: Record<string, string>;
  proposal_counts: Record<ProposalStatus, number> };
export type ReportList = { from: string; to: string; reports: ReportSummary[] };
export type ReportDetail = { id: number; report_date: string; status: ReportStatus; model: string | null;
  started_at: string; finished_at: string | null; error: string | null; body_md: string | null;
  stats: Record<string, unknown>; proposals: Proposal[] };

/** 보고서 목록. 빈 값은 쿼리에서 뺀다(서버 기본 = 최근 30일). */
export function listReports(from?: string, to?: string): Promise<ReportList>;            // GET
/** 보고서 1개(본문·집계·개선안). */
export function getReport(id: number): Promise<ReportDetail>;                             // GET
/** 개선안 목록. status가 없으면 전체. */
export function listProposals(status?: ProposalStatus): Promise<Proposal[]>;             // GET, 응답의 proposals
/** 개선안 결정. note가 빈 문자열이면 null로 보낸다. */
export function decideProposal(id: number, status: DecisionStatus, note: string): Promise<Proposal>;  // POST(CSRF는 14 apiJson)

export const PROPOSAL_STATUS_LABEL: Record<ProposalStatus, string>;  // new 결정 대기 · adopted 채택(개발 후보) · held 보류 · rejected 기각
export const REPORT_STATUS_LABEL: Record<ReportStatus, string>;      // running 진행 중 · done 완료 · skipped 건너뜀 · failed 실패
export const TARGET_LABEL: Record<ProposalTarget, string>;           // §6.8 표
export const PRIORITY_LABEL: Record<ProposalPriority, string>;       // high 높음 · medium 보통 · low 낮음
export const EVIDENCE_TYPE_LABEL: Record<Evidence["type"], string>;  // turn 대화 · stat 집계 · attack 공격 세트 · security 보안 이벤트
export const STEP_LABEL: Record<string, string>;                     // collect 수집 · scoring 채점 · attack_set 공격 질문 세트 · summary 요약 · proposals 개선안
export const STEP_RESULT_LABEL: Record<string, string>;              // done 완료 · partial 일부 실패 · failed 실패 · skipped 건너뜀
export const ATTACK_TYPE_LABEL: Record<string, string>;              // §6.4 23 유형 9개

/** 0~1 비율을 "93.3%"로. null·숫자 아님 → "—". 1 초과·음수도 그대로 곱해 보여 준다(값 이상을 숨기지 않음). */
export function formatRate(v: unknown): string;
/** 금액 문자열·숫자를 19 formatUsd 규칙으로. 그 밖 → "—". */
export function formatCost(v: unknown): string;
/** 집계 JSON을 "알아보는 부분"과 "나머지 키-값 줄"로 나눈다(§6.4). */
export function splitStats(stats: Record<string, unknown>): { known: KnownStats; rest: Array<{ key: string; value: string }> };
/** 객체를 "a.b.c" 경로의 줄로 편다. 배열·원시값은 JSON 문자열로(200자 넘으면 잘라 "…"). 깊이 4를 넘으면 그 아래는 JSON 문자열 하나로. */
export function flattenStats(value: unknown, prefix?: string): Array<{ key: string; value: string }>;
/** 근거 1개를 화면 줄로: Evidence 모양이면 "[{EVIDENCE_TYPE_LABEL} {ref}]" 줄 + quote(있으면 “…”) + note(있으면), 그 밖 객체 → "키: 값" 줄들, 문자열 → 그대로, 나머지 → JSON 문자열. */
export function evidenceLines(item: unknown): string[];
```
- `formatCost`는 19 `formatUsd`를 가져다 쓴다(`web/lib/admin-usage.ts` — 19 병합 전제, 25-Q6).

### 6.2 보고서 목록 `/admin/quality` (`quality/page.tsx`, `"use client"`)
위에서 아래 순서:
1. 제목 "품질 리포트" + 설명 한 줄(§6.9 `MSG_INTRO`) + 오른쪽 링크 **"개발 후보 보기"**(`/admin/quality/proposals`).
2. 기간 폼: 시작일·종료일 `<input type="date">` + [조회]. 처음 열 때 `listReports()`(쿼리 없음 → 최근 30일), 응답 `from`·`to`로 칸을 채운다(19와 같은 흐름).
3. 표(최신 날짜 위): 대상 날짜(링크 → `/admin/quality/{id}`) · 상태(`REPORT_STATUS_LABEL`, 실패는 빨간 글, 일부 실패 표시 §5.2) · 답변 수 · 좋은 턴 비율 · 검증 통과율 · 공격 방어율 · 만든 개선안(§5.2) · 결정 현황("결정 대기 n · 채택 n · 보류 n · 기각 n", 결정 대기 n>0이면 굵게).
4. 빈 목록: "이 기간에 품질 보고서가 없어요. 보고서는 매일 03:00(한국 시간)에 전날 대화로 만들어져요."
- 오류 처리는 19 §6.2와 같다(`invalid_range` 문구 그대로).

### 6.3 보고서 1개 `/admin/quality/[reportId]` (`"use client"`)
- `reportId`가 숫자(`/^[1-9]\d{0,18}$/`)가 아니면 API를 부르지 않고 `MSG_REPORT_NOT_FOUND`와 같은 문구 + 목록 링크.
- 위에서 아래 순서:
  1. 머리: "{report_date} 품질 보고서" · 상태 배지 · 모델 · 시작/종료 일시 · "← 목록" 링크.
  2. `status`별 안내(본문 위, `role="status"`) — 24 §4.1·§4.2:
     | 상태 | 안내 | 아래에 그리는 것 |
     |---|---|---|
     | `running` | "보고서를 만드는 중이에요. 잠시 뒤 새로고침해 주세요." | 없음(`stats`가 `{}`) |
     | `failed` | "보고서를 만들지 못했어요." + `error` 글(일반 텍스트, `<pre>` 줄바꿈 유지) + "다시 만들려면 서버에서 `nadri eval quality --date {report_date}`를 실행하세요." | **단계 결과 표**(`stats.steps` — 실패 지점까지)만. 이때 `stats`에는 `schema`·`rubric_version`·`report_date`·`steps`만 있으므로(24 §9 예외) 집계·요약·개선안 영역은 그리지 않는다 |
     | `skipped` | "어제는 대화가 없어 채점·개선안을 건너뛰었어요. 공격 질문 세트 결과만 있어요." | 요약(24 본문 — 대화 없음 문구 + 공격 세트 절), 집계는 `cost_usd`·`security`·`attack_set`·`eval_run`만(대화·채점·검증·지연·피드백·데이터 부족은 모두 0/null이라 숨김) |
     | `done` + `steps`에 `partial`·`failed` 있음 | "일부 단계가 실패했어요." + 단계 결과 표(실패·일부 실패 줄은 빨간 글). `attack_set` 실패면 그 절에 `attack_set.error` | 전부(실패한 단계의 값은 0/null → "—") |
     | `done`(모든 단계 done·skipped) | 없음 | 전부. 단계 결과 표는 접힌 상자(`<details>`)로 |
  3. **요약**(`body_md`가 있을 때): `SafeMarkdown text={body_md} allowedUrls={[]} linksEnabled={false}`.
  4. **집계**: §6.4 순서의 소제목 묶음 + 맨 아래 "기타 집계" 키-값 표(`rest`가 있을 때만).
  5. **개선안 n건**: 우선순위 순 `ProposalCard` 목록(§6.5). 없으면 "이 보고서에는 개선안이 없어요."
- 404 `report_not_found` → 문구 + 목록 링크.

### 6.4 집계 표시 — 24 §9 키 + 나머지 키-값 (25-Q1 추천안)
`splitStats`는 아래 표의 **맨 위 키**만 알아본다. 각 묶음은 모양 검사(`isXxx` 가드 — 아래 "필수 모양"만 검사)를 통과할 때만 보기 좋게 그리고, 통과 못 하면 그 키를 통째로 `rest`(키-값 줄)로 보낸다. 가드를 통과한 묶음 안에 **표에 없는 하위 키**가 있으면 그 하위 키만 `rest`로(`"section.key"`). 표에 없는 맨 위 키도 `rest`로 간다. **24 키가 나중에 늘거나 바뀌어도 화면이 깨지지 않고 모든 값이 어딘가에 보인다**(안전장치 — 24 §9는 "모든 키는 항상 있다"를 보장하지만 그대로 믿지 않는다).

키·모양 정본 = **24 spec §9 표**. 공통 규칙(24 §9): 비율은 0~1(null 가능), 평균 점수 0~2, 시간은 밀리초 정수, 금액은 문자열 Decimal, 분포 키는 문자열.

| 순서 | 소제목 | 맨 위 키 | 필수 모양(가드) | 그리는 법 |
|---|---|---|---|---|
| 0 | (머리) 단계 결과 | `schema`·`rubric_version`·`report_date`·`steps` | `steps`: 값이 문자열인 객체 | 머리 줄에 "채점 기준 v{rubric_version}". `steps`는 §6.3 단계 결과 표(`STEP_LABEL` · `STEP_RESULT_LABEL`). `schema`가 1이 아니면 "집계 형식이 달라요(schema {n}) — 일부 값이 기타 집계에 보일 수 있어요." 한 줄 |
| 1 | 대화 | `conversation` | `users`·`sessions`·`turns_answered`·`turns_cached`·`turns_blocked` 정수 | "사용자 {users}명 · 세션 {sessions}개 · 답변 {turns_answered}턴(캐시 {turns_cached}) · 입력 차단 {turns_blocked}턴" |
| 2 | 채점 | `scoring` | `eligible`·`selected`·`scored`·`failed`·`over_limit`·`max_items`·`good` 정수, `avg`·`dist`·`verify_judgement` 객체 | "채점 대상 {eligible} · 채점 {scored} · 실패 {failed}" (+ `over_limit>0`이면 "상한 {max_items} 때문에 {over_limit}턴 빠짐") · 좋은 턴 {good}({formatRate(good_rate)}) · 평균 점수 표(정확성·해결·툴 선택, 0~2, null "—") · 분포 표(점수 0·1·2·해당 없음(`na`) × 3항목) · 검증 판단 표(`agree` 맞음 · `false_reject` 괜히 막음 · `miss` 놓침 · `unclear` 판단 불가) |
| 3 | 답변 검증 | `verification` | `n`·`passed`·`failed`·`security_replaced` 정수, `rewrites` 객체 | 통과율 `formatRate(pass_rate)`({passed}/{n}) · 끝 상태 표(통과 · 사실 오류 경고 · 보안 교체) · **다시 쓰기 분포** 표(키 숫자 순 "0회·1회·2회…") · `max_rewrites_seen`이 있으면 "그날 다시 쓰기 상한: {값들}" |
| 4 | 응답 시간 | `latency_ms` | `ttft`·`total`·`cached_total` 각각 `{n, p50, p95, avg}`(값 null 허용) | 표: 첫 글자까지 · 전체 · 캐시 답변 전체 × 건수 · p50 · p95 · 평균(밀리초 → §서식) |
| 5 | 대화 비용 | `cost_usd` | `chat_total` 문자열, `by_kind`·`calls_by_kind` 객체 | "대화 비용 {formatCost(chat_total)} · 턴당 {formatCost(per_turn)}" + 종류별 표(19 `KIND_LABELS` 이름 · 건수 · 비용). 설명 한 줄: "평가 배치 비용은 맨 아래 '평가 실행'에 따로 있어요." |
| 6 | 사용자 피드백 | `feedback` | `up`·`down`·`none` 정수, `reasons`·`agreement` 객체 | 👍 {up} · 👎 {down} · 없음 {none} + 👎 사유 표(16 `REASON_LABELS` + `unspecified` "사유 없음") + **👍/👎와 채점 일치율** "{formatRate(agreement.rate)} ({agree}/{n})"(`n=0`이면 "피드백과 점수가 함께 있는 턴이 없어요") + `disagree_refs`가 있으면 "어긋난 턴: t-…"(글자, 링크 없음) |
| 7 | 보안 이벤트 요약 | `security` | `total` 정수, `by_outcome`·`by_check`·`blocked_by_code`·`pii_types` 객체, `samples` 배열 | 총 {total}건 + 결과별·검사별·입력 차단 사유별·가린 개인정보 종류별 표(§6.8 이름, 모르는 값은 키 그대로, 0인 줄은 숨김) + **최근 사례**(최대 10, `samples`: 시각 `at` · 별칭 · 단계 · 검사 · 결과 · 분류 · 발췌 — 발췌는 일반 텍스트) |
| 8 | 공격 질문 세트 | `attack_set` | `status` 문자열, `by_type` 객체, `failed_ids` 배열 | `status="failed"`: "공격 질문 세트를 실행하지 못했어요." + `error`(일반 텍스트), 숫자 "—". `done`: "방어율 {formatRate(defense_rate)} ({passed}/{total})" + **유형별 표**(`ATTACK_TYPE_LABEL` 이름 · 건수 `total` · 방어 `passed` · 방어율 `rate`, 방어율 1 미만 행은 빨간 글, 23 `ATTACK_TYPES` 순서 = `by_type` 키 순서 그대로) + **실패 케이스 id**(코드 글꼴, 없으면 "실패 없음") + `cost_usd`가 있으면 "실행 비용 {formatCost}" |
| 9 | 데이터가 부족한 주제 | `data_gaps` | 배열(항목 `{topic, count, refs}`) | 표: 주제 · 건수 · 턴 ref(글자). 빈 배열이면 "없음" |
| 10 | 평가 실행 | `eval_run` | `calls`·`cost_usd` 객체 | 모델 · 호출 수(평가 {calls.eval} · 개선안 {calls.proposal}) · **평가 배치 비용** 평가 / 개선안 / 합계(`formatCost`) · 만든 개선안 {proposals_created}건 · 걸린 시간 {elapsed_s}초 · 설정 스냅샷 해시 앞 12자(`config_sha256`, 없으면 "—") |

- 숫자 서식: 정수는 19 `formatInt`, 비율은 `formatRate`, 밀리초는 1000 이상이면 "x.y초", 아니면 "n ms", null은 "—".
- "기타 집계" 표: `flattenStats` 줄을 키 순서대로. 값이 긴 JSON은 200자에서 자르고 끝에 "…".
- 24 본문(`body_md`)에도 같은 숫자 표가 있다(24 §10.2). 화면 집계는 본문을 대신하지 않고, 본문을 못 그리거나(요약 실패) 값을 하나씩 찾을 때 쓴다 — 둘 다 같은 `stats`에서 나오므로 숫자는 같다.
- **공격 유형 한글 이름**(23 spec §4.2 `ATTACK_TYPES` 9개, 그 순서): `jailbreak` 탈옥 · `direct_injection` 직접 인젝션 · `prompt_leak` 프롬프트 유출 · `indirect_injection` 간접 인젝션 · `exfiltration` 링크·이미지 유출 · `pii` 개인정보 · `harmful` 유해 요청 · `self_harm` 자해 · `off_topic` 범위 이탈. 모르는 id는 그대로.

### 6.5 개선안 카드 (`components/admin/ProposalCard.tsx`, `"use client"`)
```tsx
/**
 * 개선안 1건을 보여 주고 채택·보류·기각 + 메모를 받는다.
 * @param proposal - 서버가 준 개선안
 * @param showReportLink - 개선안 목록 화면이면 true(보고서로 가는 링크 표시)
 * @param onDecided - 결정 성공 시 바뀐 개선안을 넘긴다(부모가 목록에서 교체)
 * @param onConflict - 404·409 때 부모가 목록을 다시 불러오게 한다
 */
export function ProposalCard(props: { proposal: Proposal; showReportLink: boolean;
  onDecided: (p: Proposal) => void; onConflict: () => void }): JSX.Element;
```
- 머리 줄: 우선순위 배지(`PRIORITY_LABEL`, 높음은 눈에 띄는 색) · 대상(`TARGET_LABEL`) · 제목 · 상태 배지(`PROPOSAL_STATUS_LABEL`).
- 본문(일반 텍스트, 비어 있는 선택 필드는 줄째 숨김): 문제 · 근거(`evidence` 항목마다 `evidenceLines` — 인용 상자, 예: "[대화 t-012]" / “인용” / 메모. `ref`는 글자로만(턴 점수 화면이 없으므로 링크 없음 — 25-Q5), 비어 있으면 "근거 발췌가 정리됐어요(90일 지남)." — `report_id`가 null일 때만, 아니면 줄 숨김) · 원인 추정 · 제안 · 예상 효과 · 비용 · 위험.
- `showReportLink`이면: `report_id`가 있으면 "{report_date} 보고서" 링크, null이면 "보고서 없음(90일이 지나 정리됨)" 글.
- 결정 정보(있으면): "{STATUS} · {decided_by_username ?? '알 수 없음'} · {formatKst(decided_at)}" + 메모(일반 텍스트).
- 결정 영역:
  - 메모 `<textarea>`(라벨 "결정 메모(선택)", `maxLength=1000`, 남은 글자 수 표시). **처음 값 = 현재 `decision_note ?? ""`**(결정을 바꿀 때 메모가 사라지지 않게 — §4.5).
  - 버튼 [채택] [보류] [기각] — **현재 상태와 같은 버튼만 비활성**(`new`면 셋 다 활성). 확인 창 없음(되돌릴 수 있으므로 — 25-Q2).
  - 누르면 그 카드 버튼 전부 비활성("처리 중…") → `decideProposal(id, status, note)`.
  - 성공: 카드 아래 `role="status"` 알림(§6.9) + `onDecided(응답)`.
  - 409·404: `role="alert"`에 서버 문구 + `onConflict()`.
  - 422: 14 `MSG_VALIDATION`. 401: `/login`. 그 밖: 14 문구.
- 채택 버튼 옆 작은 글: "채택해도 자동으로 바뀌는 것은 없어요."(ADR-23, `MSG_NO_AUTO`).

### 6.6 개선안 목록 `/admin/quality/proposals` (`"use client"`)
- 제목 "개선안" + 설명 `MSG_CANDIDATES`.
- 상태 탭: **개발 후보(채택)**(기본) · 결정 대기 · 보류 · 기각 · 전체. 탭을 바꾸면 `listProposals(status)`(전체는 status 없음). 탭은 화면 안 상태(주소 쿼리 없음 — 18과 같음).
- 목록: `ProposalCard`(`showReportLink=true`), 서버 순서 그대로.
- 결정 성공 후: 지금 탭과 상태가 달라진 카드는 **알림을 남긴 채 목록에서 뺀다**(예: 개발 후보 탭에서 기각 → 카드 사라짐 + "개선안을 기각했어요."). 같은 탭이면(전체) 카드만 교체.
- 빈 목록: 개발 후보 "아직 채택한 개선안이 없어요." / 결정 대기 "결정을 기다리는 개선안이 없어요." / 보류 "보류한 개선안이 없어요." / 기각 "기각한 개선안이 없어요." / 전체 "개선안이 없어요."

### 6.7 관리자 메뉴 (18 `AdminShell.tsx`)
- `ADMIN_NAV`에 `{ href: "/admin/quality", label: "품질" }`을 맨 뒤(19 "사용량" 다음)에 더한다.
- 현재 메뉴 표시(`aria-current="page"`)는 **`pathname === href || pathname.startsWith(href + "/")`** 로 판정한다 — `/admin/quality/12`·`/admin/quality/proposals`에서도 "품질"이 켜지게. 18이 정확히 같은 주소만 비교하게 구현했다면 이 한 줄을 바꾼다(18 V-AS-02는 그대로 통과 — `/admin/users`는 둘 다 맞음). 25-Q8.
- `/admin` 첫 화면은 18대로 사용자 목록.

### 6.8 한글 이름표 (`admin-quality.ts`)
| 대상 값 | 한글 |
|---|---|
| `system_prompt` | 시스템 프롬프트 |
| `tool_description` | 툴 설명 |
| `reranker` | 리랭커 |
| `verifier` | 검증 에이전트 |
| `guard` | 입력·출력 검사 |
| `faq_cache` | FAQ 캐시 임계값 (24-Q1 채택 시) |
| `data_scope` | 데이터 범위 |
| `other` | 기타 |

보안 이벤트(§6.4 7, 24 §9 `security` 키): 결과 `masked` 개인정보 가림 · `blocked` 차단 · `self_harm_guide` 자해 안내 · `rewritten` 다시 쓰기 · `safe_replaced` 안전 문구 교체 · `guard_error` 검사 장애 / 검사 `pii` 개인정보 규칙 · `moderation` Moderation · `classifier` 분류기 · `code_check` 코드 검사 · `verifier` 검증 에이전트 / 입력 차단 사유(`blocked_by_code`) `unsafe` 유해 내용 · `self_harm` 자해 · `jailbreak` 탈옥 · `injection` 인젝션 · `off_topic` 범위 이탈 / 단계(`samples[].stage`) `input` 입력 · `output` 출력. 개인정보 종류(`pii_types`)는 07 `PII_TYPES` 키 그대로. 모르는 값은 그대로.

### 6.9 화면 고정 문구 (`admin-quality.ts` 상수)
| 상수 | 문구 |
|---|---|
| `MSG_INTRO` | 매일 03:00(한국 시간)에 전날 대화를 평가한 보고서예요. 대화는 익명으로 처리돼 있어요. |
| `MSG_CANDIDATES` | 채택한 개선안은 다음 개발 때 참고할 후보예요. 코드·프롬프트·설정은 자동으로 바뀌지 않아요. |
| `MSG_NO_AUTO` | 채택해도 자동으로 바뀌는 것은 없어요. |
| `MSG_DECIDED` | `adopted` 개선안을 채택했어요. 개발 후보 목록에 추가됐어요. / `held` 개선안을 보류했어요. / `rejected` 개선안을 기각했어요. |
| `MSG_REPORTS_EMPTY` | 이 기간에 품질 보고서가 없어요. 보고서는 매일 03:00(한국 시간)에 전날 대화로 만들어져요. |
| `MSG_EVIDENCE_CLEARED` | 근거 발췌가 정리됐어요(90일 지남). |

---

## 7. 엣지케이스

| 상황 | 동작 |
|---|---|
| 목록 쿼리 없음, 오늘 KST 11-22 | 10-24 ~ 11-22 (30일) |
| `to`만 2026-10-15 | 09-16 ~ 10-15 |
| `from`만 11-01 | 11-01 ~ 오늘 |
| `from > to` / 367일 | 400 `invalid_range` |
| `from=2026-13-01` | 422 |
| 보고서 0개 | 200 `reports: []` |
| `running`·`failed` 보고서 | 목록에 나옴(상태 표시), 개선안 0 |
| `stats`가 `{}`(running) | `headline` 값 전부 None → "—", `steps {}`, 상세 집계 영역 비어 있음 |
| failed 보고서(`stats` = schema·rubric_version·report_date·steps만) | 목록 지표 "—", 상세는 오류 글 + 단계 결과 표만 |
| skipped 보고서 | 목록 지표: 답변 0, 좋은 턴·검증 통과율 "—"(null), 공격 방어율은 값 있음. 상세는 §6.3 표대로 일부 집계만 |
| done + `steps.attack_set = "failed"` | 목록 "완료(일부 실패)", 공격 방어율 "—", 상세 공격 절에 `attack_set.error` |
| done + `steps.scoring = "partial"` | 목록 "완료(일부 실패)", 상세 채점 절에 실패 수 |
| `stats`에 모르는 키·모양이 다른 키 | 상세 "기타 집계"에 키-값으로(§6.4) |
| `stats.verification.pass_rate`가 문자열 `"0.9"` | 목록: 문자열이라 `headline`에 그대로 → `formatRate`는 숫자 아님 → "—". 상세: 가드 실패 → 기타 집계 |
| `stats` 값에 `true` | `pick_headline`은 None(bool 제외) |
| 없는 보고서 id / `abc` / 0 | 404 / 422 / 422 (화면은 숫자 아님이면 호출 없이 안내) |
| 개선안 없는 보고서 | `proposals: []` |
| `evidence` 항목이 24 모양이 아님(문자열·모르는 키) | `evidenceLines`가 글자·"키: 값"으로 보여 줌 |
| 개선안 `report_id` NULL(90일 정리 후 채택·보류) | 상세에는 안 나옴(어느 보고서에도 속하지 않음), 개선안 목록에 "보고서 없음(90일이 지나 정리됨)", `evidence: []` → 정리 문구 |
| `new` → 채택 | status adopted, 메모·결정자·일시 기록, 개발 후보 목록에 나옴 |
| 채택 → 채택(버튼 두 번) | 409 `proposal_status_conflict`, `"status":"adopted"`, DB 그대로(`decided_at` 안 바뀜) |
| 보류 → 채택 / 채택 → 기각 / 기각 → 채택 | 200(§5.1) |
| `status:"new"` / `"approved"` | 422 |
| 메모 `"   "` | NULL로 저장 |
| 메모 1000자 / 1001자 | 200 / 422 |
| 메모 없이 결정 변경(이전 메모 있음) | 메모가 지워진다(덮어쓰기). 화면은 입력칸에 기존 메모를 미리 채워 둠 |
| 본문에 `extra` 필드 | 422(`extra="forbid"`) |
| CSRF 헤더 없음 | 403 `csrf_failed` |
| 없는 개선안 id(21이 지운 뒤) | 404 `proposal_not_found` → 화면 문구 + 목록 다시 불러오기 |
| 결정한 관리자 계정이 지워짐 | `decided_by` NULL(04 SET NULL), 화면 "알 수 없음" |
| 일반·pending 사용자 | 403 `forbidden`, 로그인 안 함 401 |
| 일반 사용자가 `/admin/quality` 주소 입력 | 18 `AdminShell`이 "접근 권한이 없어요.", `/api/admin/quality/*` 요청 0회 |
| `body_md`에 `<script>`·`![x](http://evil)`·`[여기](http://evil)` | HTML 버림, 이미지 없음, 링크는 클릭 안 되는 글(§6 보안) |
| 개선안 글에 마크다운·HTML 기호 | 글자 그대로 보임(해석 안 함) |
| 24 실행 중(running)인 보고서 상세를 연 뒤 완료 | 자동 갱신 없음 — 새로고침하면 보임 |
| 같은 report_date 보고서 다시 만들기(24 CLI) | 24 규칙(UNIQUE) — 25는 지금 DB에 있는 것을 보여 줄 뿐 |
| 휴대폰 폭 | 표만 가로 스크롤, 카드는 세로로 쌓임 |

---

## 8. 앞 작업과 달라지는 점 · 앞 작업 테스트 수정

| # | 내용 | 대상 | 처리 |
|---|---|---|---|
| 1 | 18 `admin/router.py`에 quality 라우터 1줄 | 18 라우터 테스트 | 수정 없음. A-ADR-06이 25 경로도 자동 검사 |
| 2 | 18 `ADMIN_NAV`에 "품질", 현재 메뉴 판정을 앞부분 일치로 | 18 Vitest V-AS-02·03 | 수정 없음(`[0]`은 그대로 사용자, `/admin/users`는 두 판정 모두 같음). 18 구현이 정확 일치였다면 판정 줄만 바꿈 |
| 3 | `errors.py`에 문구 3개 | 05 문구 상수 목록 테스트(고정 비교하면) | 목록에 추가 |
| 4 | 14 `global-setup.ts`에 `delete from improvement_proposals where title like 'e2e\_%'`, `delete from eval_reports where model = 'e2e'`를 **사용자 삭제보다 먼저** | 14·18·19 Playwright | 수정 없음(정리만 늘어남) |
| 5 | 19 `invalid_range`·`MAX_RANGE_DAYS`·`formatUsd`·`formatInt` 재사용 | — | 19가 먼저 병합돼 있어야 함(M4 < M6, 25-Q6) |
| 6 | 백엔드의 다른 모듈·DB 변경 없음 | — | — |

상위 문서와의 차이·발견(구현 판단):
1. **결정 전이**는 문서에 없다 — §5.1(25-Q2). 21 C3이 "보류 → 나중에 기각"을 전제하므로 최소한 그 전이는 열어야 한다.
2. (해결 — 24 확정) 공격 세트 결과는 `stats.attack_set`, 비용은 대화 비용 `cost_usd`와 평가 배치 비용 `eval_run.cost_usd`·`attack_set.cost_usd`로 나뉘고, `skipped` = 대화 0건 + 공격 세트만(24 §4.1·§9).
3. **`report_date`가 없는 개선안**: 90일 정리 뒤 남은 채택·보류 개선안은 `report_id`가 NULL이라 어느 날 보고서였는지 알 수 없다(`improvement_proposals`에 날짜 컬럼 없음, `created_at`만 있음). 화면은 `created_at`과 "보고서 없음"으로 대신한다.
4. **결정 이력 없음**: 결정을 바꾸면 이전 결정·메모가 행에서 사라진다(로그에만 남음, 메모 내용은 로그에도 없음) — 25-Q3.
5. 24 §16은 턴별 점수(`ref`·`alias`·점수) 화면을 허용하지만 25는 만들지 않는다(25-Q5) — 근거의 `turn` ref는 글자로만 보인다.
6. 24-Q1(대상 `faq_cache`)이 채택되면 04 `PROPOSAL_TARGETS`가 8개가 되고 25 이름표·타입에 1줄이 붙는다(§6.1·§6.8). 기각되면 그 줄을 뺀다.
7. [PL] 의존은 18·24지만 화면 서식·기간 검사에 19 함수를 쓴다(§8 #5).
8. [PL] 25 파일 목록 밖 파일 — §2 참고.

---

## 9. 완료 기준 (DoD)

1. test.md ① pytest 전부 통과(`cd ~/code/myAgent/backend && uv run pytest -m "not integration"`), §8 앞 작업 테스트 수정 후 통과.
2. `cd ~/code/myAgent/web && npm run typecheck && npm run test && npm run e2e` 통과(Vitest·Playwright — `@real` 포함).
3. 권한: 관리자만 200, 일반·pending 403, 로그인 안 함 401, CSRF 없는 결정 403. A-ADR-06이 25 경로 4개 포함해 통과.
4. 결정 전이 표(§5.1) 전 칸, 메모 정리·길이, `decided_by`·`decided_at` 기록 테스트 통과. **결정 요청이 `improvement_proposals` 1행 외에 아무것도 바꾸지 않음**(다른 테이블 행 수·`prompts/` 파일 변경 없음 — A-QH-30), `quality.py`에 파일 쓰기·프롬프트 경로·외부 호출 코드 없음(A-QH-31).
5. Playwright: 개선안 채택 → 개발 후보 목록에 표시(실제 compose `@real`). 집계 JSON에 모르는 키가 있어도 화면이 깨지지 않고 "기타 집계"에 보임. `body_md`의 링크·이미지·HTML이 동작하지 않음.
6. HITL-1~3 결과 보고(특히 HITL-2: 24가 만든 실제 보고서의 "기타 집계"가 비어 있는지 — 24 §9와 §6.4가 맞는지 확인).
7. 모든 함수·클래스·컴포넌트에 한국어 docstring/JSDoc, 함수 안 단계 주석([CL]). 커밋 `feat/25-admin-quality-hitl`, `[Feat] …` + 작업 목록 + `Author:`, AI 공동작성 표기 없음. `dev` 병합은 G5 후. `PROGRESS.md` 갱신.

---

## 10. 확인 질문

| # | 질문 | 추천안 | 대안 |
|---|---|---|---|
| 25-Q1 | 집계 JSON(`stats`) 키는 24 §9가 정본이다. 화면은 어떻게 맞출까 | **24 §9 맨 위 키 11개(§6.4 — 머리 4개 + 묶음 10개)를 보기 좋게 그리고, 모양 검사에 실패하거나 모르는 키·하위 키는 "기타 집계" 키-값 표로 그대로 보여 주는 안전장치를 유지한다.** API는 `stats`를 해석 없이 넘김. 목록 지표는 24 §16 "목록 표에 쓸 값" 5개(`HEADLINE_PATHS`) | A: 전부 키-값 표로만(코드 가장 적음, 읽기 불편) / B: 24 키를 pydantic 모델로 고정하고 서버가 검사(키가 바뀌면 API 오류 — 24·25가 함께 바뀌어야 함) |
| 25-Q2 | 결정 전이 규칙(보류 → 채택, 결정 취소 등) | **결정은 다른 결정으로 언제든 바꿀 수 있다(보류 → 채택·기각, 채택 → 보류·기각, 기각 → 채택·보류). 같은 결정 다시 보내기 = 409. `new`로 되돌리기(결정 취소) 없음.** 확인 창 없음(되돌릴 수 있으므로). 21 C3(보류 → 기각) 전제와 맞음 | A: 채택·기각은 최종, 보류만 다시 결정(실수 수정은 DB 명령) / B: A + 결정 취소(→ new) 허용 |
| 25-Q3 | 메모 규칙과 결정 이력 | **메모는 선택, 앞뒤 공백 제거, 최대 1000자, 결정을 바꿀 때 덮어씀(화면은 기존 메모를 미리 채움). 이력 테이블 없음 — 바뀔 때마다 로그 1줄(관리자 id·전후 상태·메모 글자 수)** | A: 기각·보류는 메모 필수 / B: 결정 이력 테이블 추가(ERD·04 변경 — G3 범위) / C: 같은 상태로 메모만 고치기 허용(같은 결정 = 200) |
| 25-Q4 | 결정 버튼을 어디에 둘까 | **보고서 화면과 개선안 목록 화면 둘 다**(같은 `ProposalCard`). 90일이 지나 보고서가 지워진 보류안은 개선안 목록에서만 결정할 수 있기 때문 | 보고서 화면에만([PL] 파일 설명 그대로, 개선안 목록은 보기 전용) |
| 25-Q5 | 턴별 채점(`eval_scores`)을 화면에 보일까 — 24 §16은 `ref`·`alias`·점수만이면 허용 | **보이지 않는다** — 24 본문에 "점수가 낮은 턴(최대 10)"이 이미 있고 집계·근거 발췌로 충분. 관리자에게 보여 주는 대화 범위를 늘리지 않음. 근거의 `turn` ref는 글자로만 | 보고서 화면에 턴 점수 표(24 §9.1 `scores`에서 `ref`·`alias`·점수·지적 사항만, 근거 ref를 누르면 그 줄로 — 사용자·세션 링크 없음) |
| 25-Q6 | 목록 기간과 19 재사용 | **기본 최근 30일(`report_date` 기준), 최대 366일. 기간 오류 코드·문구(`invalid_range`)와 금액·숫자 서식(`formatUsd`·`formatInt`)은 19 것을 재사용** — 19(M4)가 25(M6)보다 먼저 병합되므로 문제없음. [PL] 의존 표에 19 추가 권장 | 25가 같은 코드를 따로 둠(19와 무관, 중복 몇 줄) / 기간 필터 없이 전부 표시 |
| 25-Q7 | 보고서 본문(`body_md`)을 어떻게 그릴까 | **15 `SafeMarkdown`(링크 허용 목록 비움, 링크 끔)** — 표·목록은 보이고 HTML·이미지·링크는 동작 안 함. 개선안 글·근거는 마크다운 없이 일반 텍스트 | 본문도 일반 텍스트(줄바꿈만 유지 — 표가 깨져 보임) |
| 25-Q8 | 메뉴 이름과 현재 메뉴 표시 | **"품질"(18 약속), 앞부분 일치로 현재 메뉴 표시**(하위 주소에서도 켜짐 — 18 `AdminShell` 한 줄 변경 가능성). 결정 대기 수 배지는 넣지 않음 | 배지 추가(메뉴가 화면마다 API 호출) / 18 판정 그대로(하위 주소에서는 메뉴가 안 켜짐) |
| 25-Q9 | 개선안 목록 페이지 나누기 | **넣지 않음** — 하루 몇 건, new·rejected는 90일 뒤 지워짐(21). 채택·보류만 오래 쌓임 | 50건 단위 페이지 |
