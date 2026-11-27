# 21-ingest-daily-sync — 매일 01:00 현행화·90일 정리 (spec)

> 하네스 Phase 4 산출물 (spec-writer, 작성 2026-11-22). 상태: **확정(2026-11-22)** — 확인 질문은 모두 추천안대로 결정(마지막 절 표). 브랜치 `feat/21-ingest-daily-sync`, 의존 작업 12-faq-cache·20-ingest-hubs-lint(→ 03·04·05·06·08·09·11·13).
> 근거: [PL]=program_list.md(G4 승인본) §2 표·§3 "21-ingest-daily-sync"·§1.2·§5 X-d·Q6 · [A]=architecture.md(G3 재승인본) §2.1 `ingest`·§3.3 1)~10)·§3.7(03:00 배치)·§5.1(90일 기준·`improvement_proposals` 비고)·§6.2·ADR-09·13·14·§12 A12·A16 · [R]=requirements.md FR-45·46·47·48, NFR-31, FR-103·104 · [E]=ERD 18개(`docs/images/src/erd.py`) · [S]=stack-options.md S15(APScheduler 3.11) · [PG]=PROGRESS.md 결정 로그(G4 Q6 카운터 공유 800+200, 03-Q1·Q2·Q10, 2026-11-22 `quota_requests` 삭제).
> **이어받는 확정 spec**: [01](`TourApiClient`·`TourApiError`·`KST`·`AREAS`·`CONTENT_TYPES`·`save_raw`·`upsert_tour_item`·`render_entity`·`entity_path`·`content_hash`·`write_page`·`LightRagClient`·`PageToIndex`·`index_pages`·`apply_outcomes`·`ingest_runs`/`ingest_state`/`wiki_pages`/`tour_items` 컬럼·compose `ingest` 정의·종료 코드 0~3) · [03](`Budget`·`BudgetExhausted`·`kst_today`·`INGEST_WRITE_LOCK_KEY=1`·`LockBusy`·`parse_list_item`·`build_stub_record`·`insert_stub_stmt`·`soft_delete_stmt`·`detail_loop`·`make_process_item`·`index_pending`·`INDEX_BATCH`·`MAX_ATTEMPTS`·`bootstrap:failures`·`bootstrap:completed_at`·`run_bootstrap`·`cap_errors`·종료 코드 4) · [04](테이블 정의·FK 삭제 동작 §4.5·테스트 DB 픽스처 §7) · [05](`IDLE_TIMEOUT`·`is_valid` 규칙, `rate_limits` 규칙·윈도) · [06](재설정 코드 10분·5회) · [08](`security_events`) · [09](`chat_sessions.updated_at` 갱신 규칙) · [10](`nadri_tools` 카운터 함수 — ingest 몫은 그대로 [03] `Budget`) · [11](`daily_quota`·`usage_events`) · [12](`invalidate_by_contentids`) · [13](`message_feedback` 연쇄).
> **20(2026-11-22 확정)**: 허브·lint·위키 git·잠금 함수는 20 spec(`tasks/20-ingest-hubs-lint/spec.md` §5.2·§7·§8·§9, 같은 날 작성, 확인 질문 대기)의 이름을 그대로 쓴다(`write_hubs`·`affected_hubs`·`missing_hubs`·`build_hub_model`·`run_lint`·`save_lint`·`summary_line`·`commit_wiki`·`ingest_write_lock`·`LockBusy`). 20 확정 때 이름이 바뀌면 §9 표와 `HubsPort` 어댑터만 맞춘다(병합 시 맞춤 — 21-Q11).
> **미확인** = 문서·공식 자료로 확인하지 못한 사실. 특히 `areaBasedSyncList2`의 요청 파라미터·응답 필드·정렬·삭제 표시는 전부 **미확인(A12)** 이다. 구현 첫 단계에서 실제 호출 1~2건(raw 파일)으로 확인하고 §14 표에 결과를 적는다.
> 용어: "테이블 생성 스크립트" = Alembic 리비전 파일([01] §3.3). 이 작업은 **테이블을 새로 만들거나 바꾸지 않는다**(`ingest_state` 키·`ingest_runs.kind` 값만 추가).

---

## 1. 작업 목표

`ingest` 컨테이너를 **상주 스케줄러**로 바꾸고, 매일 01:00(KST)에 [A] §3.3의 1)~10)을 한 작업(`daily_sync`)으로 실행한다 [R FR-45, NFR-31], [A ADR-09].

1. `areaBasedSyncList2`로 서울·제주에서 마지막 성공 이후 바뀐·삭제된 contentid를 찾는다.
2. 바뀐 항목은 상세 3종을 다시 받아(예산 안에서) raw → upsert → 엔티티 재렌더 → 해시가 바뀐 페이지만 LightRAG delete→insert.
3. 삭제된 항목은 `deleted_at`을 채우고 위키 파일·LightRAG 문서·`wiki_pages` 행을 지운다.
4. 영향 받은 시군구 허브만 다시 쓴다(20 함수).
5. 바뀐·삭제된 contentid를 근거로 쓴 FAQ 캐시를 지운다(12 함수).
6. lint 결과를 `ingest_runs.lint`에 저장하고 위키 볼륨을 git 커밋한다(20 함수).
7. **90일 정리**: 오래된 대화 세션(메시지·피드백·FAQ 캐시·턴별 채점 연쇄)·보안 이벤트·품질 보고서(미결정 개선안 삭제, 채택·보류는 근거만 비움)와 만료된 로그인 세션·재설정 코드·오래된 요청 제한 카운터를 지운다.
8. 실행마다 `ingest_runs`(`kind='daily_sync'`)에 단계별 결과를 남긴다.

수동 실행: `nadri ingest sync --now`. 같은 수집 쓰기 잠금(advisory lock 키 1, 03-Q10)을 잡지 못하면 건너뛴다.

### 1.1 넣지 않는 것
| 빠지는 것 | 들어오는 작업 / 이유 |
|---|---|
| 허브 작성 프롬프트·LLM 호출·허브 인덱싱, lint 규칙, git 명령 | 20 (21은 호출만) |
| 03:00 품질 평가 작업과 그 등록 | 24 (21은 등록할 자리 `JobSpec` 목록만 만든다) |
| 품질 보고서·개선안 화면에서 `report_id`가 비어 있는 채택·보류 개선안 표시 | 25 (§13 "뒤 작업에 전달") |
| 이미지(`detailImage2`) | 범위 밖([PG] O 결정) |
| 새 테이블·컬럼, 테이블 생성 스크립트 | 없음 |
| 확장 데이터 원천(FR-49) | v1.1 이후 |
| `usage_events`·`daily_quota`·`ingest_runs`·raw 스냅샷 정리 | 하지 않음(§8.2, 21-Q10) |

---

## 2. 생성·수정 파일

경로의 `nadri/`는 `backend/src/nadri/`.

| 파일 | 신규/수정 | 역할 |
|---|---|---|
| `nadri/ingest/scheduler.py` | 신규 | APScheduler(`Asia/Seoul`) 구성, `JobSpec` 목록, 시작 시 놓친 실행 따라잡기, 준비 완료 파일, 종료 신호 처리 (§5) |
| `nadri/ingest/jobs/__init__.py` | 신규 | 빈 파일 |
| `nadri/ingest/jobs/daily_sync.py` | 신규 | 1)~10) 순서·잠금·단계별 실패 격리·`ingest_runs` 기록, (21-Q1) 초기 적재 이어하기 연결 (§6) |
| `nadri/ingest/sync.py` | 신규 | SyncList 탐색·분류·"현행화 대기" 목록·상세 재수집 연결·바뀐 페이지 재인덱싱·삭제 반영·영향 허브 키 계산 (§7) |
| `nadri/ingest/cleanup.py` | 신규 | 90일·만료 정리 규칙과 실행 (§8) |
| `nadri/core/tourapi.py` | 수정(01·03) | `area_based_sync_list()` 메서드, `parse_sync_item()` (§7.1) |
| `nadri/ingest/indexer.py` | 수정(01) | `delete_document_wait()` 추가(삭제 반영용, `index_pages`는 그대로) (§7.5) |
| `nadri/ingest/bootstrap.py` | 수정(03) | `make_process_item`이 내용이 같아도 `detail_synced_at`을 채우게 한 줄 추가 (§11-1) |
| `nadri/cli.py` | 수정 | `ingest scheduler`(상주), `ingest sync --now` (§10) |
| `compose.yaml` | 수정 | `ingest` 상주·재시작 정책·healthcheck, `tour-tools`·`api`의 `depends_on` 조건 변경 (§5.4) |
| `backend/tests/**` | 신규·수정 | test.md, 앞 작업 테스트 수정(§11) |
| `CLAUDE.md` | 수정 | "명령어" 절에 `ingest sync --now`·스케줄러 로그 보는 법 |
| `docs/harness/tasks/21-ingest-daily-sync/spec.md` §14 | 수정 | 구현 중 A12 판정 결과 기록 |

> [PL] 파일 목록 밖: `core/tourapi.py`(SyncList 메서드가 클라이언트에 있어야 함 — [01] 구조), `indexer.py`(삭제 대기 함수), `bootstrap.py` 한 줄(§11-1, 현행화에서 생기는 무한 재수집 방지), `jobs/__init__.py`.

---

## 3. 설정·상수

새 환경변수 없음. [01] `TOURAPI_DAILY_INGEST_BUDGET`(800)·`INDEX_TIMEOUT_S`·`WIKI_DIR`·`RAW_DIR`, [20]이 추가하는 OpenAI 설정을 그대로 쓴다.

| 상수 | 위치 | 값 | 이유 |
|---|---|---|---|
| `SYNC_AT` | scheduler.py | `time(1, 0)` (KST) | [R FR-45] |
| `MISFIRE_GRACE_S` | scheduler.py | `3600` | 01:00에 잠깐 늦게 깨어나도(이벤트 루프 지연·절전 해제 직후) 1시간 안이면 실행 |
| `READY_FILE` | scheduler.py | `/tmp/nadri-ingest-ready` | compose healthcheck가 보는 파일 (§5.4) |
| 수집 쓰기 잠금 | — | 20 `nadri/ingest/lock.py`의 `ingest_write_lock(engine)`·`LockBusy`(키 `INGEST_WRITE_LOCK_KEY=1`, 20-Q11 — 03 코드를 옮긴 것) | [A] §3.3 "키 1", 03-Q10 같은 키. 20-Q11이 "옮기지 않음"이면 03 `bootstrap`에서 import |
| `SYNC_PAGE_SIZE` | sync.py | `= LIST_PAGE_SIZE`(03, `100`) | `numOfRows` 상한 **미확인**(03 §14와 같음) |
| `SYNC_OVERLAP` | sync.py | `timedelta(days=1)` | 커서보다 하루 앞부터 다시 훑는다 — 원천 수정 시각과 반영 시각 차이·시계 차이 여유. 겹친 항목은 "이미 최신"으로 걸러져 상세 호출이 생기지 않음(§7.3) |
| `RETENTION` | cleanup.py | `timedelta(days=90)` | [R NFR-31], [A] §3.3 9) |
| `RATE_LIMIT_KEEP` | cleanup.py | `timedelta(days=1)` | 가장 긴 윈도(가입·재설정 1시간 — 05·06)보다 충분히 김 (21-Q9) |
| `IDLE_TIMEOUT` | — | [05] `nadri.api.auth.sessions.IDLE_TIMEOUT`(2시간) import | 만료 판정을 05 `is_valid`와 같게 |

---

## 4. `ingest_state` 키·`ingest_runs` 값 (테이블 변경 없음)

| 키 | 값 | 쓰는 곳 |
|---|---|---|
| `sync:cursor` | `{"since": ISO(KST tz-aware), "updated_at": ISO}` | 목록 단계가 **두 지역 모두 끝까지** 훑었을 때만 갱신(§7.2). 값 = 그 실행의 목록 단계 시작 시각 |
| `sync:pending` | `{"<contentid>": {"area": "서울", "added_at": ISO, "reason": "new"\|"changed"}}` | "현행화 대기" 목록 — 상세를 다시 받아야 하는 항목. 처리·제외되면 지움(§7.4). 예산이 모자라 오늘 못 받은 항목이 내일로 넘어간다 |
| `tourapi_calls:YYYY-MM-DD` | [03] 형식 그대로(`ingest`·`live`·`ops`·`quota_hit`) | `Budget(kind="ingest")`. ops에 `areaBasedSyncList2`가 추가됨 |
| `bootstrap:failures` | [03] 형식 그대로 | 현행화 상세 실패도 같은 키에 센다(같은 `MAX_ATTEMPTS=3` 규칙) |

`ingest_runs`: `kind='daily_sync'`(01 표에 CHECK 없음 — 값만 추가), `status`는 `running`/`done`/`failed`(01 CHECK 그대로 — "건너뜀"은 행을 만들지 않고 로그로만 남김), `stats` = §6.4 `SyncResult`, `lint` = 20 lint 결과(이 컬럼을 처음 쓰는 곳).

---

## 5. `ingest/scheduler.py` — 상주 스케줄러

### 5.1 시그니처
```python
@dataclass(frozen=True)
class JobSpec:
    """매일 정해진 KST 시각에 돌릴 작업 하나."""
    id: str                                   # "daily_sync" (24가 "daily_quality" 추가)
    at: time                                  # KST 시각
    run: Callable[[], Awaitable[None]]        # 예외를 밖으로 던지지 않는 래퍼(§5.2-4)
    catch_up: Callable[[datetime], Awaitable[bool]] | None = None   # 시작 시 따라잡기 필요 여부(없으면 안 함)

def build_scheduler(jobs: Sequence[JobSpec]) -> AsyncIOScheduler:
    """작업마다 CronTrigger(hour, minute, timezone=Asia/Seoul)로 등록한 스케줄러를 만든다(시작은 안 함).
    옵션: coalesce=True, max_instances=1, misfire_grace_time=MISFIRE_GRACE_S."""

def default_jobs(settings: Settings, sf: async_sessionmaker[AsyncSession]) -> list[JobSpec]:
    """21이 등록하는 작업 목록 — 지금은 daily_sync 하나. 24는 이 목록에 한 줄을 더한다."""

def needs_catch_up(last_started_at: datetime | None, now: datetime, at: time) -> bool:
    """오늘 KST `at` 시각이 이미 지났는데 그 이후에 시작한 실행이 없으면 True(순수 함수).
    now가 오늘 at 이전이면 False(어제 실행 여부와 무관 — 곧 정시 실행이 온다)."""

async def serve(settings: Settings, *, stop: asyncio.Event | None = None,
                clock: Callable[[], datetime] = lambda: datetime.now(KST)) -> None:
    """상주 진입점. 스케줄러 시작 → 따라잡기 확인 → 준비 완료 파일 쓰기 → stop(또는 SIGTERM/SIGINT)까지 대기 →
    스케줄러 종료(shutdown(wait=False)) → 엔진 정리."""
```

### 5.2 `serve` 처리 순서
1. DB 엔진·세션 팩토리를 만든다([01] `create_engine`). 비밀값 점검(`require`)은 **여기서 하지 않는다** — 키가 빠져도 컨테이너는 떠 있고, 작업 실행 때 실패로 기록한다(api·tour-tools가 ingest 준비를 기다리므로 키 하나 때문에 전체가 못 뜨는 것을 막음, §5.4).
2. `build_scheduler(default_jobs(...))` → `start()`.
3. **따라잡기**(21-Q2): 작업마다 `catch_up(now)`가 True면 즉시 1회 실행을 스케줄러에 추가(`add_job(run, "date", run_date=now)`). daily_sync의 `catch_up` = `ingest_runs`에서 `kind='daily_sync'`의 가장 최근 `started_at`을 읽어 `needs_catch_up(…, SYNC_AT)`.
4. 작업 래퍼는 예외를 잡아 `logging.getLogger("nadri.ingest")`에 ERROR 1줄(메시지만, 비밀값 없음)로 남기고 삼킨다 — 스케줄러가 죽지 않게. `LockBusy`는 INFO `daily_sync skipped: lock busy`.
5. `READY_FILE`을 쓴다(내용 = 시작 시각). 종료 신호 처리기(`loop.add_signal_handler`)로 `stop`을 set.
6. 종료 시 실행 중이던 작업은 끊긴다 → 다음 실행이 잠금을 얻은 뒤 `running` 행을 `failed`로 정리하고(§6.2-2), 대기 목록·커서가 DB에 있어 이어서 진행한다.

### 5.3 로그 (표준 출력, `docker compose logs ingest`로 봄)
- 스케줄러 시작: `scheduler started jobs=[daily_sync@01:00 KST] next=2026-11-23T01:00:00+09:00`
- 작업 시작·끝: `daily_sync start run_id=12` / `daily_sync done run_id=12 status=done elapsed_s=842.1 summary={...}`(summary = `SyncResult`에서 숫자만 — §6.4 `summary_line`). 사용자 질문·답변 글은 로그에 없다(정리 단계는 건수만).

### 5.4 compose 변경 (21-Q4)
| 서비스 | 01·05 정의 | 21 |
|---|---|---|
| `ingest` | 기본 명령 `alembic upgrade head` 후 종료, `restart: "no"` | `command: ["sh", "-c", "alembic upgrade head && exec nadri ingest scheduler"]`, `restart: unless-stopped`, `healthcheck: {test: ["CMD", "python", "-c", "import os,sys; sys.exit(0 if os.path.exists('/tmp/nadri-ingest-ready') else 1)"], interval: 5s, timeout: 3s, retries: 60, start_period: 10s}` |
| `tour-tools` | `depends_on: ingest(service_completed_successfully)` | `ingest(service_healthy)` — 테이블 생성 스크립트가 끝나야 스케줄러가 뜨고, 그때 healthy |
| `api` | `depends_on: ingest(service_completed_successfully)`(05) | `ingest(service_healthy)` |
- 그 밖의 `ingest` 설정(비루트·`cap_drop`·볼륨·환경변수)은 그대로. 20이 넣는 `OPENAI_API_KEY`도 그대로 쓴다.
- `docker compose run --rm ingest nadri …`(초기 적재·수동 실행)는 `command`를 덮어쓰므로 지금과 같이 동작한다.
- `/tmp`은 컨테이너 쓰기 층이다. 컨테이너가 재시작되면 이전 준비 파일이 남아 있을 수 있지만, 그때는 의존 서비스가 이미 떠 있어 영향이 없다.
- 시간대: `CronTrigger(timezone=ZoneInfo("Asia/Seoul"))`. 이미지에 시간대 자료가 없으면 `ZoneInfo`가 실패한다 — 01이 이미 `ZoneInfo("Asia/Seoul")`를 쓰므로 01에서 해결됐을 것으로 본다(**미확인** — 안 되어 있으면 `tzdata` 패키지를 의존에 추가).
- 의존 추가: `apscheduler==3.11.*`([S] S15 "3.11", 정확한 패치 버전은 구현 시점 `uv.lock`에 고정). 4.x는 API가 달라 쓰지 않는다.

---

## 6. `ingest/jobs/daily_sync.py` — 작업 묶음

### 6.1 시그니처
```python
@dataclass
class SyncDeps:
    """daily_sync가 쓰는 외부 자원(테스트에서 가짜로 바꿔 끼움)."""
    settings: Settings
    sf: async_sessionmaker[AsyncSession]
    tourapi: TourApiClient            # on_call = budget.reserve
    budget: Budget                    # [03] kind="ingest", limit=TOURAPI_DAILY_INGEST_BUDGET
    lightrag: LightRagClient
    hubs: HubsPort                    # §9 — 20 함수 묶음(가짜 주입 가능)
    engine: AsyncEngine               # 잠금 전용 연결용(20 ingest_write_lock)
    clock: Callable[[], datetime] = lambda: datetime.now(KST)
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep

async def run_daily_sync(deps: SyncDeps) -> SyncResult:
    """[A] §3.3 1)~10)을 한 번 실행한다. 잠금을 못 얻으면 LockBusy(행을 만들지 않음).
    단계 하나가 실패해도 다음 단계를 계속하고, 정리 단계(9)는 항상 시도한다."""

async def run_scheduled_daily(settings: Settings, sf) -> None:
    """스케줄러용 래퍼: SyncDeps를 만들고 run_daily_sync → (21-Q1·26-Q1) 초기 적재를 시작했고 안 끝났으면 run_bootstrap 이어하기(빈 DB면 안 함).
    클라이언트 정리(aclose)까지 한다. 예외는 serve의 래퍼가 로그로 남긴다."""

def final_status(steps: dict[str, StepOutcome], index_failed: int, removal_failed: int) -> Literal["done", "failed"]:
    """단계 하나라도 failed이거나 인덱싱·삭제 반영 실패가 1건 이상이면 failed(순수 함수)."""
```

### 6.2 처리 순서 (`run_daily_sync`)
| 순서 | 단계 이름(`steps` 키) | [A] §3.3 | 내용 | 이 단계가 실패하면 |
|---|---|---|---|---|
| 0 | — | 잠금 | `async with ingest_write_lock(engine)`(20 — 전용 연결에서 `pg_try_advisory_lock(1)`). 실패 → `LockBusy`(아무것도 안 함, 21-Q3) | — |
| 0-1 | — | — | 멈춘 기록 정리: `kind='daily_sync' AND status='running'` 행을 `failed`, `error='중단됨 — 다음 실행에서 정리'`, `finished_at=now`([03] §9.1-2와 같은 방식) | 예외 → 잠금 해제 후 다시 던짐 |
| 0-2 | — | — | `ingest_runs(kind='daily_sync', status='running')` 행 생성 → `run_id` | 〃 |
| 1 | `list` | 1)·2) | §7.2 SyncList 탐색 → 분류 → 껍데기 추가·`detail_synced_at=NULL`·소프트 삭제·대기 목록 추가 | 기록 후 2로 진행(이미 있던 대기 목록은 처리) |
| 2 | `detail` | 3) | §7.4 대기 목록 상세 재수집 + 배치마다 바뀐 페이지 재인덱싱·인덱싱 대기분 처리 | 기록 후 3으로 |
| 3 | `remove` | 4) | §7.5 삭제된 항목의 LightRAG 문서·위키 파일·`wiki_pages` 행 삭제 | 항목별 실패는 다음 날 재시도, 단계 예외는 기록 후 4로 |
| 4 | `hubs` | 5) | §7.6 영향 허브(+ 빠진 허브)만 20 `write_hubs`로 재작성 | 기록 후 5로 |
| 5 | `faq` | 6) | [12] `invalidate_by_contentids(바뀐 ∪ 삭제된 contentid)` → 커밋 | 기록 후 6으로 |
| 6 | `lint` | 7) | 20 `run_lint` → `save_lint(sf, run_id, report)`(= `ingest_runs.lint`) → `summary_line` | 기록 후 7로 |
| 7 | `git` | 8) | 20 `commit_wiki(wiki_dir, message)` → `CommitResult(sha, files)` | 기록 후 8로 |
| 8 | `cleanup` | 9) | §8 정리(트랜잭션 1개) | 기록(롤백됨 — 다음 날 다시 시도) |
| 9 | — | 10) | `ingest_runs` 갱신: `finished_at`, `stats=asdict(SyncResult)`, `status=final_status(...)`, `error`(실패 단계 이름을 `; `로 이은 한 줄) → 잠금 해제 | — |

- 단계마다 `try/except Exception` → `steps[이름] = StepOutcome("failed", 메시지)`, `errors`에 한 줄. 단계 사이에 넘기는 값(바뀐·삭제된 contentid 집합, 영향 허브 키)은 실패한 단계까지 모인 만큼만 넘긴다(21-Q12).
- **TourAPI 한도 처리**는 [03]과 같다: 1·2단계에서 22를 받으면 `budget.mark_quota_hit()` 후 두 단계 모두 그날 중단(`stop_reason="quota"`), 23이면 이번 실행의 TourAPI 단계만 중단(`"rate"`), 예산 소진이면 `"budget"`. 이 경우에도 3~8단계는 진행한다. `stop_reason`이 `quota`·`rate`면 단계 결과는 `failed`, `budget`이면 `ok`(내일 이어짐 — [03] 표와 같은 판단).
- 스케줄러 실행 때 키가 빠져 있으면: `TOURAPI_SERVICE_KEY` 없음 → 1·2단계 `failed("설정 누락: TOURAPI_SERVICE_KEY")`, `LIGHTRAG_API_KEY` 없음 → 2·3단계 같은 방식(2단계는 인덱싱에 필요). 나머지 단계는 진행한다(정리는 키와 무관). CLI는 [01] 규칙대로 시작 전에 `require`로 종료 코드 2.

### 6.3 초기 적재와의 관계 (21-Q1)
문제: 03의 `--follow`는 매일 00:10에 이어하기를 시작해 **잠금 키 1을 몇 시간 잡고** 그날 ingest 예산 800을 거의 다 쓴다. 그러면 01:00 `daily_sync`는 잠금 실패로 매일 건너뛰고(현행화·90일 정리 모두 멈춤), 잡더라도 예산이 남지 않는다.

추천안(21-Q1): **스케줄러 작업이 두 일을 차례로 한다** — `run_scheduled_daily`가
1. `run_daily_sync`(잠금 획득 → 1~9 → 잠금 해제)를 먼저 돌려 현행화가 예산을 먼저 쓰고(하루 수십~수백 건 예상, **미확인**),
2. **초기 적재를 한 번이라도 시작했고(`ingest_runs`에 `kind='bootstrap'` 행이 있음) 아직 안 끝났으면**(`ingest_state`에 `bootstrap:completed_at` 없음) 이어서 [03] `run_bootstrap(BootstrapOptions())`(자체적으로 잠금을 다시 잡음 — 실패하면 `LockBusy` 로그만)을 실행해 남은 예산을 쓴다. 결과는 03 형식으로 `kind='bootstrap'` 행이 따로 남는다.
- (26-Q1, 2026-11-28) 한 번도 시작하지 않은 빈 DB에서는 이어하기를 하지 않는다. 그러지 않으면 새로 설치하자마자 따라잡기(21-Q2)가 전체 초기 적재(TourAPI 800건·인덱싱 비용)를 스스로 시작한다. 초기 적재의 첫 시작은 [A] §3.3대로 CLI(`ingest bootstrap`)만 한다.
- 21 병합 뒤에는 `--follow` 컨테이너를 멈춘다(HITL H-0). `--follow` 코드는 지우지 않는다(수동 실행용으로 남김 — 수술적 변경).
- `nadri ingest sync --now`는 1만 한다(초기 적재는 [03] `ingest bootstrap` 명령이 따로 있음).

### 6.4 실행 결과 `SyncResult`
```python
@dataclass(frozen=True)
class StepOutcome:
    status: Literal["ok", "failed", "skipped"]
    note: str | None = None                  # 실패·건너뜀 이유 한 줄

@dataclass
class SyncResult:
    """daily_sync 한 번의 요약(ingest_runs.stats에 그대로 저장, CLI 마지막 줄 JSON)."""
    run_id: int
    since: str | None                        # 이번 탐색 기준 시각(ISO, overlap 적용 전), 없으면 None
    stop_reason: Literal["complete", "budget", "quota", "rate", "error", "no_bootstrap"]
    calls: int; calls_by_op: dict[str, int]
    listed: dict[str, dict[str, int | bool]]   # {"서울": {"pages", "items", "new", "changed", "fresh", "deleted", "ignored", "complete"}, "제주": {...}}
    pending_left: int
    detailed: int; soft_deleted: int; detail_failed: int
    indexed: int; index_skipped: int; index_failed: int
    removed_pages: int; removal_failed: int
    hubs: dict                               # {"keys": ["서울:23", ...]} + 20 asdict(HubRunResult)의 숫자 필드(written·skipped·failed·indexed·cost_usd …), 건너뛰면 {"skipped_reason": …}
    faq_invalidated: int
    lint_summary: str | None                 # 20 summary_line(report) 한 줄(본문은 ingest_runs.lint)
    git_commit: str | None; git_files: int
    cleanup: dict[str, int]                  # §8.3 CleanupResult
    steps: dict[str, StepOutcome]
    errors: list[str]                        # [03] cap_errors(50)
    elapsed_s: float

def summary_line(r: SyncResult) -> dict:
    """로그·CLI 표준 출력용으로 숫자 필드와 steps 상태만 뽑는다(순수 함수)."""
```

---

## 7. `ingest/sync.py` — 현행화

### 7.1 `core/tourapi.py` 추가
```python
async def area_based_sync_list(self, area: str, *, num_of_rows: int, page_no: int = 1) -> TourApiResponse:
    """areaBasedSyncList2 한 페이지. 파라미터 = 공통 + AREAS[area] + numOfRows + pageNo + arrange=C.
    contentTypeId는 보내지 않는다(8종을 한 번에 받고 코드에서 거름). on_call은 [03]처럼 보내기 직전."""

@dataclass(frozen=True)
class SyncItem:
    """SyncList item 한 건에서 쓰는 값."""
    contentid: str; content_type_id: int
    modifiedtime: datetime | None            # 'YYYYMMDDHHMMSS' KST → tz-aware, 형식 오류면 None
    showflag: str | None                     # "1" 표시 / "0" 숨김·삭제로 추정(미확인)
    raw: dict                                # 새 항목 껍데기를 만들 때 [03] parse_list_item에 그대로 넘김

def parse_sync_item(item: dict) -> SyncItem:
    """SyncList item dict를 SyncItem으로 바꾼다. contentid·contenttypeid가 없으면 ValueError."""
```
- **미확인(A12)**: ① `arrange=C`가 "수정일 최신순"인지 ② 요청 파라미터 `modifiedtime`(날짜 필터)·`showflag`·`listYN`이 v2에 있는지 ③ 응답에 `showflag`·`modifiedtime`이 오는지 ④ 새로 생긴 콘텐츠·삭제된 콘텐츠가 이 목록에 나오는지 ⑤ item 필드가 `areaBasedList2`와 같아 `parse_list_item`을 그대로 쓸 수 있는지. KorService1 시절 공개 명세 기준의 추정이다. 구현 첫 단계(test.md I-1)에서 지역별 1페이지를 실제로 받아 §14에 적고, 다르면 §7.2 탐색 방식을 21-Q5 대안으로 바꾼다.

### 7.2 목록 단계 — 탐색 (`scan_area`)
```python
def sync_since(cursor: dict | None, first_bootstrap_at: datetime | None) -> datetime | None:
    """탐색 기준 시각(overlap 적용 전). 커서가 있으면 cursor.since, 없으면 첫 초기 적재 시작 시각
    (ingest_runs kind='bootstrap'의 최소 started_at), 그것도 없으면 None(= 초기 적재 전 → 목록 단계 건너뜀). 순수 함수."""

def scan_page(items: list[SyncItem], threshold: datetime) -> tuple[list[SyncItem], bool]:
    """한 페이지에서 threshold(= since − SYNC_OVERLAP) 이후 수정된 항목만 고르고, 더 오래된 항목이 하나라도 있으면
    두 번째 값 True(= 이 페이지 다음은 안 봐도 됨). modifiedtime 없는 항목은 고르고(보수적) 멈춤 판단에는 안 씀. 순수 함수."""

async def scan_area(deps: SyncDeps, area: str, threshold: datetime, acc: ListAccumulator) -> bool:
    """1페이지부터 scan_page가 멈춤을 알리거나, 마지막 페이지(page × size ≥ totalCount)거나, 빈 페이지일 때까지 읽는다.
    페이지마다 raw 저장 → 분류(§7.3) → DB 반영(한 트랜잭션, 커밋). 끝까지 읽었으면 True."""
```
처리:
1. `since = sync_since(...)`. None이면 `steps.list = skipped("초기 적재 전")`, `stop_reason="no_bootstrap"`, 2단계도 대기 목록이 비어 있으므로 사실상 건너뜀.
2. `threshold = since − SYNC_OVERLAP`. `list_started_at = clock()`.
3. 지역 순서 서울 → 제주. 페이지마다 `save_raw(key="sync_{area}_p{page}")`([01] 규칙, 날짜 폴더 아래 `areaBasedSyncList2/`).
4. 두 지역 모두 True면 `sync:cursor = {"since": list_started_at}`로 갱신. 하나라도 끝까지 못 읽었으면(예산·한도·오류) 커서를 **그대로** 둔다 — 다음 실행이 같은 기준으로 다시 훑고, 이미 처리한 항목은 §7.3 규칙으로 "이미 최신"이 되어 상세 호출이 생기지 않는다(목록 호출만 다시 씀).
5. 페이지 수 상한은 두지 않는다 — 예산([03] `reserve`)이 상한이다. 첫 실행(커서 없음)은 초기 적재 시작 이후의 모든 변경을 훑으므로 페이지가 많을 수 있다(예상 호출 수는 HITL H-2에서 확인).

### 7.3 분류 규칙 (`classify`, 순수 함수)
```python
@dataclass(frozen=True)
class Existing:
    """tour_items에 이미 있는 행의 필요한 값."""
    detail_synced_at: datetime | None; deleted_at: datetime | None
    area: str; sigungu_code: str | None

Action = Literal["ignore", "new", "changed", "fresh", "delete"]

def classify(item: SyncItem, existing: Existing | None) -> Action: ...
```
| 순서 | 조건 | 결과 | DB 반영 (`apply_actions`, 페이지당 한 트랜잭션) |
|---|---|---|---|
| 1 | `content_type_id ∉ CONTENT_TYPES` | `ignore` | 없음 |
| 2 | `showflag == "0"` 이고 행이 있고 `deleted_at IS NULL` | `delete` | [03] `soft_delete_stmt` → `deleted` 집합에 추가 (21-Q6) |
| 3 | `showflag == "0"` (행이 없거나 이미 삭제됨) | `ignore` | 없음 |
| 4 | 행 없음 | `new` | [03] `parse_list_item(item.raw)` → `build_stub_record` → `insert_stub_stmt` → 대기 목록 추가(`reason="new"`) |
| 5 | 행 있음, `deleted_at` 있음(다시 나타남) | `changed` | `detail_synced_at=NULL` → 대기 목록 추가. `deleted_at`은 상세 upsert가 NULL로 되돌린다([01] upsert 규칙) |
| 6 | `detail_synced_at`·`modifiedtime` 둘 다 있고 `detail_synced_at >= modifiedtime` | `fresh` | 없음(우리가 원천 수정 뒤에 이미 받음 — 겹쳐 훑은 항목·초기 적재가 방금 받은 항목) |
| 7 | 그 밖(상세 미수집 껍데기 포함) | `changed` | `UPDATE tour_items SET detail_synced_at = NULL WHERE contentid = :id` → 대기 목록 추가(`reason="changed"`) |

- 7의 `detail_synced_at=NULL`은 [A] §3.3 2) "상세 미수집 큐"를 그대로 따른다. 부수 효과: 다시 받기 전까지 [12] 캐시 저장 조건 8에서 빠져, 낡은 내용으로 새 캐시가 생기지 않는다.
- `parse_list_item` 실패(필드 없음)는 `errors`에 `"sync <area> p<page>: 사유"`로 남기고 그 항목만 건너뛴다.
- `ListAccumulator`는 지역별 `pages`·`items`와 결과별 개수를 센다(`SyncResult.listed`).

### 7.4 상세 단계 — 대기 목록 처리
```python
def build_pending_batch_stmt(pending: list[str], excluded: set[str], limit: int) -> Select:
    """SELECT contentid, content_type_id, area FROM tour_items
       WHERE contentid = ANY(:pending) AND detail_synced_at IS NULL AND NOT (contentid = ANY(:excluded))
       ORDER BY contentid LIMIT :limit   — deleted_at은 보지 않는다(다시 나타난 항목 포함)."""

def prune_pending(pending: dict[str, dict], rows: dict[str, tuple[datetime | None, datetime | None]],
                  failures: dict[str, dict]) -> tuple[dict[str, dict], list[str]]:
    """대기 목록에서 (상세 완료 | 행 없음 | 실패 횟수 ≥ MAX_ATTEMPTS)인 항목을 뺀 새 목록과, 실패로 빠진 contentid 목록을
    돌려준다(순수 함수). rows = {contentid: (detail_synced_at, deleted_at)}."""

async def index_changed(deps: SyncDeps, contentids: Collection[str]) -> IndexStats:
    """방금 다시 받은 항목(삭제 안 됨)의 엔티티 페이지를 다시 렌더해 [01] PageToIndex(새 해시, wiki_pages의 이전 해시·doc_id)로
    만들고 index_pages → apply_outcomes. 해시가 같으면 skipped(호출 없음)."""
```
처리:
1. 대기 목록을 읽어 [03] `detail_loop`에 넘긴다: `next_batch` = `build_pending_batch_stmt`, `process_item` = [03] `make_process_item`(§11-1 수정 반영), `remaining` = `budget.remaining`, `on_quota` = `budget.mark_quota_hit`, `record_failure` = [03]과 같은 `bootstrap:failures` 기록, `max_items=None`, `batch_size=INDEX_BATCH`.
2. `after_batch`: 이 배치에서 `stored`된 contentid로 `index_changed` → 이어서 [03] `index_pending()`(인덱싱이 실패해 해시가 NULL이 된 페이지·새 항목 페이지).
   - 바뀐 항목은 `wiki_pages`에 이전 해시가 있어 [03] `index_pending`의 대기 조건(해시 NULL)에 걸리지 않는다 — 그래서 `index_changed`가 따로 필요하다.
3. 처리 결과: `stored` → `changed` 집합, `deleted`(`detailCommon2`가 빈 응답 — [03] 소프트 삭제) → `deleted` 집합.
4. 반복이 끝나면 `prune_pending` → 저장. 실패로 빠진 항목은 `errors`에 `"sync detail <contentid>: 3회 실패로 제외"`.
5. 영향 허브 계산을 위해 1 이전에 대기 목록 contentid로 20 `affected_hubs`를 불러 옛 시군구 허브 키를 담아 둔다(§7.6 3 `before`).
- `as_of`가 날마다 바뀌므로([01] §6.4) 다른 날 다시 받은 항목은 내용이 같아도 대부분 `updated` → 페이지 해시가 바뀌어 재인덱싱된다. [01]이 받아들인 동작이며 현행화 대상(바뀐 항목)만이라 비용이 작다.

### 7.5 삭제 반영 (`remove_deleted_pages`)
```python
def build_removal_queue_stmt() -> Select:
    """SELECT w.path, w.lightrag_doc_id, t.contentid FROM wiki_pages w JOIN tour_items t ON t.contentid = w.contentid
       WHERE w.kind = 'entity' AND t.deleted_at IS NOT NULL ORDER BY w.path"""

async def remove_deleted_pages(deps: SyncDeps) -> RemovalStats:
    """삭제된 항목의 페이지마다: LightRAG 문서 삭제(있으면, 사라질 때까지 대기) → 위키 파일 삭제(없어도 됨) →
    wiki_pages 행 삭제·커밋. LightRAG 삭제가 실패하면 그 페이지는 그대로 두고(다음 실행에서 재시도) 다음 페이지로."""

# indexer.py 추가 ([01] index_pages 2) 단계와 같은 동작을 따로 부를 수 있게)
async def delete_document_wait(client: LightRagClient, doc_id: str, *, timeout_s: float, poll_interval_s: float = 5.0,
                               sleep=asyncio.sleep, clock=time.monotonic) -> None:
    """delete_documents([doc_id]) 후 document_exists가 False가 될 때까지 기다린다. 실패·시간 초과면 LightRagError."""
```
- 대기 목록이 따로 없다 — "삭제됐는데 `wiki_pages` 행이 남은 항목"이 곧 재시도 대상이다(크래시·LightRAG 장애에도 안전).
- 순서가 "LightRAG 먼저, `wiki_pages` 마지막"인 이유: `wiki_pages`를 먼저 지우면 재시도 근거가 사라진다. 대신 LightRAG 삭제가 실패해 행이 남은 동안에는 `rag_query`가 그 문서를 후보로 돌려줄 수 있다([01] §6.8: `wiki_pages` 메타가 **없는** 후보만 버림). 다음 실행에서 다시 지우므로 받아들인다.
- 이번 실행에서 삭제 반영된 contentid도 `deleted` 집합에 넣는다(예전 실행에서 실패해 남았던 것 포함 → FAQ·허브도 그때 반영).
- [A] 엔드포인트(A16)는 01에서 확정된 경로를 쓴다.

### 7.6 영향 허브 (20 `affected_hubs`·`missing_hubs`·`write_hubs`)
처리:
1. 초기 적재가 안 끝났으면(`ingest_state`에 `bootstrap:completed_at` 없음) **단계 `skipped("초기 적재 중")`** — 허브 27개는 20이 적재 완료 때 만든다(20 §6 8a). (21-Q8)
2. `OPENAI_API_KEY`가 없으면 `skipped("no_openai_key")`(20 bootstrap 8a와 같은 처리 — 실패로 만들지 않음).
3. 키 = `before ∪ after ∪ missing`:
   - `before` = 2단계(상세) **시작 전** 대기 목록 contentid로 `affected_hubs(sf, pending)` — 시군구가 바뀐 항목의 옛 허브(20 §9 안내).
   - `after` = 이번 실행의 `changed ∪ deleted`로 `affected_hubs(sf, …)`(20: 소프트 삭제 행 포함, 허브 정의가 없는 시군구는 버림).
   - `missing` = `missing_hubs(sf)` — 예전 실행에서 허브 작성·인덱싱이 실패해 빠진 허브를 다시 시도(초기 적재 완료 뒤에는 bootstrap이 더 돌지 않으므로 21이 맡는다).
4. 키가 비면 `skipped("영향 없음")`. 아니면 `write_hubs(keys, settings=…, sf=…, lightrag=…, model=build_hub_model(settings))`. 입력 해시가 같은 허브는 20이 LLM 없이 `skipped`(20 Q5) — 전화·운영시간만 바뀐 날은 비용 0.
5. `HubRunResult.failed ≥ 1` 또는 `index_failed ≥ 1`이면 단계 `failed`(다음 날 `missing_hubs`로 재시도). 허브 비용은 20이 `usage_events(kind=hub)`로 기록한다.

### 7.7 FAQ 무효화
- `ids = changed ∪ deleted`(이번 실행에서 모인 것). 비면 0(쿼리 안 함 — 12 규칙). 한 세션에서 [12] `invalidate_by_contentids(db, ids)` → 커밋.
- 12의 함수는 `nadri/api/faq_cache.py`에 있다. ingest가 같은 패키지(`app` 이미지)라 import할 수 있다(새로 만들지 않음).

---

## 8. `ingest/cleanup.py` — 90일·만료 정리

### 8.1 규칙 표 (ERD 18개 테이블 기준)
`now` = 주입된 시각(tz-aware), `ts_cut = now − RETENTION`, `date_cut = kst_today(now) − 90일`. 실행 순서 = 표 순서, **한 트랜잭션**(하나라도 실패하면 모두 롤백 → 다음 날 다시 시도).

| # | 대상 | 조건 | 동작 | 연쇄(04 FK) |
|---|---|---|---|---|
| C1 | `chat_sessions` | `updated_at < :ts_cut` | DELETE | `chat_messages` → `message_feedback`·`faq_cache`(원본)·`eval_scores` 삭제 / `security_events.session_id·message_id`·`usage_events.message_id`·다른 메시지의 `faq_cache_id` → NULL |
| C2 | `security_events` | `created_at < :ts_cut` | DELETE | 없음 |
| C3 | `improvement_proposals` | 대상 = `report_id IN (SELECT id FROM eval_reports WHERE report_date < :date_cut)` **또는** `(report_id IS NULL AND created_at < :ts_cut)`, 그리고 `status IN ('new','rejected')` | DELETE | 없음 |
| C4 | `improvement_proposals` | C3과 같은 대상, `status IN ('adopted','held') AND evidence <> '[]'::jsonb` | `UPDATE SET evidence = '[]'::jsonb` | 없음 |
| C5 | `eval_reports` | `report_date < :date_cut` | DELETE | `eval_scores` 삭제 / 남은 개선안(채택·보류) `report_id` → NULL([PL] X-d, 04 SET NULL) |
| C6 | `auth_sessions` | `expires_at <= :now OR last_seen_at + :idle <= :now` | DELETE | 없음 |
| C7 | `password_reset_codes` | `expires_at <= :now OR consumed_at IS NOT NULL` | DELETE | 없음 |
| C8 | `rate_limits` | `window_start < :now − :rate_keep AND (locked_until IS NULL OR locked_until <= :now)` | DELETE | 없음 |

- C3·C4는 C5 **전에** 해야 한다(C5 뒤에는 `report_id`가 NULL이 되어 어느 보고서 소속이었는지 알 수 없음).
- C3의 "`report_id IS NULL AND created_at` 90일 지남" 조건: 보류(held)로 남았다가 나중에 기각(rejected)으로 바뀐 개선안이 다음 정리 때 지워지게 하는 조건(21-Q7). 채택·보류로 남아 있는 한 지우지 않는다.
- C1 기준은 `updated_at`(마지막 질문 시각 — 09가 턴 저장 때만 갱신, 제목·요약 갱신은 안 바꿈)이다 [A] §5.1. "세션 단위 삭제"라 오래된 세션 안의 최근 메시지는 없다.
- C5 기준을 `started_at`이 아니라 `report_date`(대상 날짜)로 둔다: 03:00 배치(24)가 D+1에 D의 보고서를 만드므로, 그 보고서가 다룬 대화(D)와 같은 날 기준으로 지워진다.
- 개선안의 `problem`·`proposal` 등 다른 글은 남긴다([A] §5.1 "evidence만 비움").
- C6은 05 `is_valid`의 반대 조건(절대 만료 또는 유휴 만료)이다. 05는 접근할 때 만료 세션을 지우고, 21은 다시 접근하지 않는 세션을 지운다.
- C7: 만료됐거나 이미 쓴 코드는 06 흐름에서 다시 쓰이지 않는다(06 재설정 요청 처리 4단계가 새 코드를 만들 때 그 사용자의 이전 코드를 모두 지움). 5회 실패 코드는 만료 시각이 지나면 C7에 걸린다.

### 8.2 정리하지 않는 테이블 (21-Q10)
| 테이블 | 이유 |
|---|---|
| `users` | 계정 — 비활성화는 18 |
| `chat_messages`·`message_feedback`·`eval_scores` | C1·C5 연쇄로만 지움 |
| `faq_cache` | C1 연쇄(원본 메시지) + 7.7 무효화 + 13 👎. 따로 기간 정리 없음([12] "TTL 없음") |
| `daily_quota` | 사용자당 하루 1행, 글 없음 — 사용량 통계(19) 근거 |
| `usage_events` | 비용·월 누적(19, NFR-43) 근거. 대화 내용 없음(`message_id`는 C1 때 NULL) |
| `tour_items` | 소프트 삭제 행은 남긴다([01] `wiki_pages` FK NO ACTION, 다시 나타날 수 있음) |
| `wiki_pages` | 삭제 반영(7.5)만 |
| `ingest_runs` | 하루 1~2행, 운영 이력 |
| `ingest_state` | 날짜 카운터 키 하루 1행([03] §4 "지우지 않음") |
| raw 스냅샷(`raw-data` 볼륨) | 불변 스냅샷 [R FR-40] |

### 8.3 시그니처
```python
@dataclass(frozen=True)
class Cutoffs:
    ts_cut: datetime; date_cut: date; rate_cut: datetime; now: datetime

def cutoffs(now: datetime) -> Cutoffs:
    """정리 기준 시각들을 계산한다(순수 함수). now가 naive면 ValueError."""

def build_cleanup_stmts(c: Cutoffs) -> list[tuple[str, Executable]]:
    """C1~C8을 (결과 키, 문) 목록으로 순서대로 돌려준다(순수 함수 — 값은 모두 바인드 파라미터).
    결과 키: chat_sessions, security_events, proposals_deleted, proposals_evidence_cleared, eval_reports,
             auth_sessions, reset_codes, rate_limits."""

async def run_cleanup(sf: async_sessionmaker[AsyncSession], *, now: datetime) -> dict[str, int]:
    """한 트랜잭션에서 build_cleanup_stmts를 차례로 실행하고 키별 영향 행 수(rowcount)를 돌려준다. 커밋까지."""
```
- `rowcount`는 직접 지운 행 수다(연쇄로 지워진 메시지 수는 세지 않음 — 로그·`stats`에는 세션 수로 충분).

---

## 9. 20에서 가져다 쓰는 함수 (20 spec 초안 기준 — 병합 시 맞춤, 21-Q11)

| 함수 (20 모듈) | 21에서 쓰는 자리 | 잠금 |
|---|---|---|
| `ingest_write_lock(engine)` · `LockBusy` (`ingest/lock.py`) | §6.2 0 | — |
| `affected_hubs(sf, contentids) -> set[HubKey]` (`wiki/hubs.py`) | §7.6 3 | 필요 없음 |
| `missing_hubs(sf) -> set[HubKey]` | §7.6 3 | 필요 없음 |
| `build_hub_model(settings) -> Runnable` | §7.6 4 | — |
| `write_hubs(keys, *, settings, sf, lightrag, model, force=False, clock) -> HubRunResult` | §7.6 4 | **호출자(21)가 키 1 보유** |
| `run_lint(*, settings, sf, lightrag, clock) -> LintReport` · `save_lint(sf, run_id, report)` · `summary_line(report)` (`wiki/lint.py`) | §6.2 6 | 필요 없음 |
| `commit_wiki(wiki_dir, message) -> CommitResult` (`wiki/git.py`, async) | §6.2 7 | **호출자(21)가 키 1 보유** |

```python
# 21 jobs/daily_sync.py — 20 함수를 한 곳에서 감싸 테스트에서 가짜로 바꿈(이름이 바뀌면 여기만 고침)
class HubsPort(Protocol):
    async def affected(self, contentids: Collection[str]) -> set[tuple[str, str]]: ...
    async def missing(self) -> set[tuple[str, str]]: ...
    async def write(self, keys: Collection[tuple[str, str]]) -> dict: ...          # asdict(HubRunResult)
    async def lint(self, run_id: int) -> str: ...                                   # run_lint → save_lint → summary_line
    async def commit(self, message: str) -> tuple[str | None, int]: ...             # (sha, files)
```
- 21이 20에 기대하는 성질(20 초안에 이미 적혀 있음 — 확정 때 유지 확인): ① `write_hubs`·`commit_wiki`·`run_lint`는 **advisory lock을 스스로 잡지 않는다**(21이 키 1을 잡은 채 부름 — 다른 연결로 같은 키를 잡으면 실패). ② `commit_wiki`는 `add -A`로 삭제까지 커밋(§7.5에서 지운 엔티티 파일). ③ `affected_hubs`는 소프트 삭제 행도 포함. ④ `write_hubs`가 `usage_events(kind=hub)`를 직접 기록.
- git 커밋 메시지: 첫 줄 `[daily_sync] {KST 날짜} 변경 {detailed} · 삭제 {removed_pages} · 허브 {written}`(20 CLI의 `[hubs] run …` 형식에 맞춤), 개인 정보 없음.

---

## 10. CLI (`nadri/cli.py`)
| 명령 | 동작 | 종료 코드 |
|---|---|---|
| `nadri ingest scheduler` | §5 `serve` (compose `ingest` 기본 명령). 끝나지 않음 | 0(정상 종료 신호) |
| `nadri ingest sync --now` | `require(TOURAPI_SERVICE_KEY)`·`require(LIGHTRAG_API_KEY)` → `run_daily_sync` 1회(초기 적재 이어하기 없음) → 진행 줄 + 마지막 줄 `summary_line` JSON | 0 = `done`, 1 = `failed`, 2 = 설정·인자 오류, 4 = 잠금 실패(다른 수집 작업 실행 중) |
- `--now` 없이 `nadri ingest sync`만 주면 인자 오류(2) — 실수로 큰 작업을 돌리지 않게 명시적으로([PL] 표기 그대로).
- 실행 위치: 스케줄러가 떠 있으면 `docker compose exec ingest nadri ingest sync --now`, 아니면 `docker compose run --rm ingest nadri ingest sync --now`. 01:00 작업이 도는 중이면 4.
- 진행 줄(표준 출력): `[sync 서울 p1] new 2 changed 14 fresh 80 deleted 1`, `[상세 12] 126508 경복궁 updated`([03] 형식), `[삭제] entity/12/999.md`, `[허브] 서울:23 서울:24`, `[정리] chat_sessions 3 security_events 10 …`. 서비스 키·URL 쿼리 없음.
- `nadri ingest status`([03])는 수정하지 않는다. 마지막 실행 3개에 `daily_sync`도 보인다(같은 표).

---

## 11. 앞 작업과 달라지는 점 · 앞 작업 테스트 수정

| # | 대상 | 앞 작업 | 21 | 이유 |
|---|---|---|---|---|
| 1 | [03] `make_process_item` 3단계 | upsert 결과가 `unchanged`면 `detail_synced_at`이 바뀌지 않음([01] §6.4 — 비교 대상 아님) | upsert 뒤 `UPDATE tour_items SET detail_synced_at = :fetched_at WHERE contentid = :id AND detail_synced_at IS NULL` 한 줄 | 현행화가 `detail_synced_at=NULL`로 만든 항목을 **같은 날** 다시 받아 내용이 같으면(`as_of`도 같음) NULL로 남아 매일 다시 받게 된다. 초기 적재에서는 껍데기 → 상세가 항상 `updated`라 영향 없음 |
| 2 | [01] compose `ingest` | one-shot, `restart: "no"` | 상주, `restart: unless-stopped`, healthcheck | [A] §2.1 "APScheduler 상주", 01-Q1 "21에서 바꾼다" |
| 3 | [01] `tour-tools`·[05] `api` `depends_on` | `ingest(service_completed_successfully)` | `ingest(service_healthy)` | ingest가 끝나지 않으므로 완료 조건이 영원히 안 옴 |
| 4 | [01] `core/tourapi.py` | 오퍼레이션 4개(+10의 실시간 2개) | `area_based_sync_list`·`parse_sync_item` 추가 | SyncList |
| 5 | [01] `indexer.py` | 삭제는 `index_pages` 안에서만 | `delete_document_wait` 추가(기존 함수는 그대로) | 삭제만 하는 경로 |
| 6 | [03] `--follow` 운영 | 매일 00:10 이어하기 | 스케줄러 01:00 작업이 현행화 뒤 이어하기(21-Q1). `--follow` 코드는 그대로 둠 | 잠금·예산 충돌 |

앞 작업 테스트 수정:
| 테스트 | 수정 |
|---|---|
| [03] `make_process_item` 관련(U-RUN·통합 I-4 등 `unchanged` 결과를 보는 것이 있으면) | `unchanged`일 때 `detail_synced_at`이 채워지는 기대 추가. 없으면 21 test.md D-SY-9가 새로 확인 |
| [01]·[05] compose를 파싱해 `depends_on` 조건을 고정 비교하는 테스트가 있으면 | `service_healthy`로 바꿈(26의 `test_compose_hardening.py`는 아직 없음) |
| [01] HITL "ingest가 `exited (0)`" 확인 문구 | 21 이후 `Up (healthy)`. 01 test.md는 고치지 않고 21 HITL에 적는다(이미 지나간 HITL) |

상위 문서와의 차이(구현 판단, 아키텍처 범위 안):
1. **현행화 대기 목록(`sync:pending`)**: [A] §3.3 2)는 "`detail_synced_at=NULL` → 상세 미수집 큐"만 적었다. 초기 적재가 안 끝난 동안 그 큐에는 껍데기 수천 건이 섞여 있어, 바뀐 항목을 먼저 받으려면 따로 표시가 필요하다 → `ingest_state` 키 하나(테이블 추가 없음). NULL 표시도 [A]대로 한다.
2. **"이미 최신" 걸러내기**(§7.3-6): SyncList를 하루 겹쳐 훑어도 상세 호출이 늘지 않게.
3. **삭제 반영 순서·재시도 근거**(§7.5): 별도 큐 없이 "삭제됐는데 `wiki_pages`가 남은 항목"을 재시도 대상으로.
4. **단계 실패 격리**(§6.2): [A] §3.3은 순서만 적었다. 정리(9)는 개인정보 보관 기한(NFR-31)이라 앞 단계 실패와 무관하게 시도한다(21-Q12).
5. **초기 적재 이어하기를 01:00 작업 뒤에**(§6.3, 21-Q1): [A] §3.3 "초기 적재: CLI"와 03 `--follow`를 바꾼다.
6. **놓친 실행 따라잡기**(§5.2-3, 21-Q2): [A]에 없음. 개인 PC(WSL)는 01:00에 꺼져 있거나 절전일 수 있다.

---

## 12. 엣지케이스
| 상황 | 동작 |
|---|---|
| 01:00에 다른 수집 작업(수동 `bootstrap`·`reindex`·`hubs`·`sync --now`)이 잠금 보유 | `LockBusy` → INFO 로그 `daily_sync skipped: lock busy`, `ingest_runs` 행 없음. 정리도 안 함(21-Q3 결정에 따라 정리만 따로 할 수 있음) |
| 같은 날 두 번 실행(01:00 자동 + `sync --now`) | 둘째 실행은 커서 이후만 훑고(대부분 `fresh`), 대기 목록이 비어 있으면 상세 0, 정리는 지울 것이 없어 0 — 멱등 |
| 두 실행이 동시에 | 잠금으로 하나만. 다른 하나는 4(CLI) / 건너뜀(스케줄러) |
| 실행 중 컨테이너 종료(`docker compose down`·PC 종료) | 다음 실행이 `running` 행을 `failed`로 정리. 대기 목록·커서·실패 횟수가 DB에 있어 이어서. 정리 트랜잭션 도중이면 롤백(다음 날 다시) |
| 01:00에 PC가 꺼져 있었음 | 다음 기동 때 `needs_catch_up` → 바로 1회 실행(21-Q2). 같은 날 이미 돌았으면 안 함 |
| 01:00 직전에 컨테이너가 뜸 | `needs_catch_up` False(오늘 01:00 전) → 정시 실행만 |
| 실행 중 자정 통과(긴 실행) | 예산은 [03]처럼 새 날짜 키로 넘어감. 정리 `now`는 정리 단계 시작 시각 |
| 초기 적재 전(`tour_items` 비어 있고 bootstrap 이력 없음) | `since=None` → 1·2단계 `skipped`, 정리는 진행, `stop_reason="no_bootstrap"`, `status=done` |
| 커서 없음(21 첫 실행) | 첫 bootstrap 시작 시각부터 훑음 — 페이지가 많을 수 있음. 예산이 모자라면 커서 그대로 → 다음 날 다시(이미 처리한 항목은 `fresh`) |
| SyncList가 `modifiedtime`을 안 줌 | 모든 항목을 고르고(`fresh` 판정 불가 → `changed`) 멈춤 판단 불가 → 끝까지 읽음. 호출이 크게 늘면 A12 판정으로 21-Q5 대안 |
| `arrange=C`가 최신순이 아님 | 오래된 항목이 첫 페이지에 나와 일찍 멈춤 → 변경을 놓침. **I-1에서 반드시 확인**(§14), 아니면 21-Q5 대안 |
| `showflag` 필드 없음 | 2·3번 규칙이 안 걸림 → 삭제는 상세 재수집 때 `detailCommon2` 빈 응답으로만 감지([03] 규칙) |
| 22(일일 한도) | `quota_hit` → 1·2단계 중단, 3~8 진행, 실행 `failed`. 실시간 툴(10)도 그날 멈춤([03] 규칙) |
| 23(초당 한도) | 1·2단계 이번 실행만 중단, 3~8 진행, `failed`. 대기 목록은 다음 실행에 |
| 예산 소진 | 1·2단계 `budget`(ok), 커서 그대로·대기 목록 남김, `done` |
| 같은 항목이 계속 실패 | [03] `bootstrap:failures`로 3회 → 대기 목록에서 제외, `errors`에 보고 |
| 다시 받은 항목이 다른 유형으로 바뀜(경로 변경) | 새 경로 페이지가 생기고 이전 경로 `wiki_pages` 행·파일이 남는다. 드문 일로 보고 처리하지 않는다 — 20 lint가 "깨진 링크·고아 페이지"로 보고하면 수동 정리(**미확인**: 20 lint 범위) |
| LightRAG 다운 | 2단계 인덱싱 실패 → 해시 NULL → 다음 실행 `index_pending`. 3단계 항목별 실패 → 행 남김 → 다음 실행. 실행 `failed` |
| OpenAI 장애(허브) | 4단계 `failed`, 다음 단계 진행. 다음 날 20 `missing_hubs`(인덱싱 안 된 허브)로 다시 시도. 작성 자체가 실패해 이전 허브 파일이 그대로 남은 경우는 그 시군구가 다시 바뀔 때 다시 쓰인다(**미확인**: 20 `missing_hubs`가 "작성 실패·이전 내용 유지"도 잡는지 — 20 확정 때 확인) |
| git 저장소가 아직 없음 | 20 `commit_wiki`가 `ensure_repo`로 만든다 |
| 정리 대상 0건 | 모두 0, 오류 아님 |
| 90일 정확히 경계(`updated_at == ts_cut`) | 지우지 않음(`<`) |
| 보고서가 지워진 채택 개선안 | `report_id` NULL, `evidence` `[]`, 나머지 글 유지 → 25 화면이 보고서 링크 없이 표시해야 함(§13) |
| `report_date`가 오늘 기준 90일 전 날짜 | `date_cut`과 같으면 남김(`<`) |
| 03:00 품질 배치(24)와 겹침 | 다른 잠금 키(2). 01:00 작업이 03:00을 넘겨도 24는 전날 대화(90일 정리 대상 아님)만 읽어 충돌 없음. 단, 초기 적재 이어하기(§6.3)가 길면 OpenAI 호출이 겹칠 수 있음 — 기능 문제 없음 |
| `ingest_runs.kind`에 새 값 | CHECK 없음([01] 표) — 그대로 저장 |
| 시계 | 모든 함수가 `clock`/`now`를 주입받는다. naive 시각이면 `ValueError`([03] `kst_today`와 같음) |

---

## 13. 뒤 작업에 전달
- **24**: `scheduler.default_jobs()`에 `JobSpec("daily_quality", time(3, 0), run=…, catch_up=…)` 한 줄을 더한다. 잠금 키 2. 90일이 지난 `eval_reports`는 01:00에 `report_date` 기준으로 지워지므로, `eval quality --date`로 90일 이전 날짜를 다시 만들면 다음 01:00에 지워진다.
- **25**: 90일 뒤 채택·보류 개선안은 `report_id` NULL·`evidence` `[]`로 남는다. 목록·개발 후보 화면이 보고서 없는 개선안을 오류 없이 보여야 한다.
- **26**: compose 점검 테스트에서 `ingest`가 `restart: unless-stopped`·healthcheck를 가진 것을 기준으로 한다.

---

## 14. 가정·확인 항목 판정 (구현 중 결과 기록)
| ID | 확인 방법 | 통과 기준 | 실패 시 대안 | 사용자 확인 | 결과 |
|---|---|---|---|---|---|
| **A12** SyncList 요청 파라미터 | test.md I-1: 서울·제주 각 1페이지(2호출) raw 확인 | `areaCode`·`arrange=C`로 정상 응답 | 파라미터 이름·코드 체계 수정(03 `AREAS`와 같이) | 아니오 | |
| **A12** 정렬 | I-1 raw의 `modifiedtime`이 내림차순인지 | 내림차순 | 21-Q5 대안 B(날짜 필터 파라미터) 또는 C(끝까지 읽기) | 호출 수가 크게 늘면 예 | |
| **A12** 응답 필드 | I-1 raw: `showflag`·`modifiedtime`·`contentid`·`contenttypeid`·목록 필드 | 있음 | `showflag` 없음 → 삭제는 상세 빈 응답으로만(코드 그대로). `modifiedtime` 없음 → 21-Q5 대안 | 아니오 | |
| **A12** 새·삭제 콘텐츠 포함 여부 | 며칠 운영 뒤 `listed.new`·`listed.deleted`·상세 빈 응답 건수 | 새 콘텐츠가 `new`로 잡힘 | 안 잡히면 03 `--relist` 주기 실행 여부를 사용자에게 묻는다 | 예(그때) | |
| **A12** 하루 호출 수 | H-2·H-5: `calls_by_op` | 목록 + 상세가 예산 안 | 초과가 잦으면 예산 배분(현행화 몫) 논의 | 예(그때) | |
| A16 삭제 | H-4(삭제가 생겼을 때) LightRAG 문서 수 감소 | 삭제 후 `document_exists` False | 01 A16 대안 | 아니오 | |

---

## 15. 완료 기준 (DoD)
1. test.md ① 전부 통과(`cd ~/code/myAgent/backend && uv run pytest -m "not integration"`), §11 앞 작업 테스트 수정 후 통과.
2. **잠금 중복 실행 건너뜀**: 다른 연결이 키 1을 잡고 있으면 `LockBusy`, `ingest_runs` 행 없음(DB 테스트).
3. **변경·삭제 처리**: 분류 표(§7.3) 7줄, 대기 목록 처리·재시도·제외, 바뀐 페이지만 재인덱싱, 삭제 반영(LightRAG → 파일 → 행), FAQ 무효화 호출, 영향 허브 키 계산이 테스트로 확인된다.
4. **정리 규칙 표**(§8.1 C1~C8): 시계 주입으로 경계(89일·90일·91일) 테스트 통과, 연쇄(메시지·피드백·캐시·채점) 확인, 채택·보류 개선안 근거만 비움.
5. compose: `docker compose up -d` 뒤 `ingest`가 `Up (healthy)`, `api`·`tour-tools`가 정상 기동(H-1).
6. HITL H-2(`sync --now` 결과 — 변경 건수·호출 수)와 H-5(다음 날 01:00 자동 실행 로그) 보고. §14 A12 판정 기록, 실패 대안 중 사용자 확인 항목은 **멈추고 묻는다**.
7. 한국어 docstring·단계 주석([CL]), `CLAUDE.md` "명령어" 갱신. 커밋 `feat/21-ingest-daily-sync`, `[Feat] …` + 작업 목록 + `Author:` 줄, AI 공동작성 표기 없음 [R NFR-73]. `dev` 병합은 G5 후. `PROGRESS.md` 갱신.

---

## 16. 확인 질문
| # | 질문 | 선택지 | 추천안 |
|---|---|---|---|
| 21-Q1 | 03 `--follow`가 매일 00:10부터 잠금 키 1과 예산 800을 잡아 01:00 현행화가 매일 건너뛰어질 수 있다. 초기 적재가 끝나기 전 둘을 어떻게 나눌까 | A: 01:00 스케줄러 작업이 **현행화 → (적재 미완료면) 초기 적재 이어하기**를 차례로 실행, `--follow`는 멈춤 / B: `--follow` 유지하고 시작 시각을 현행화 뒤(예: 02:00)로 옮김(현행화가 늦게 끝나면 또 겹침) / C: 현행화가 잠금이 풀릴 때까지 기다림([A] "건너뜀"과 다름, 몇 시간 대기) | **결정(2026-11-22): 추천안대로** — **A** — 현행화가 예산을 먼저 쓰고 남은 예산을 적재가 씀. 컨테이너 하나로 끝나 운영이 단순 |
| 21-Q2 | 01:00에 PC가 꺼져 있거나 절전이면 그날 실행이 빠진다(APScheduler 메모리 저장소는 놓친 실행을 기억하지 못함) | A: ingest 기동 때 "오늘 01:00 이후 실행 기록 없음"이면 바로 1회 실행 / B: 놓치면 다음 날까지 기다림 | **결정(2026-11-22): 추천안대로** — **A** — 개인 PC 운영에서 90일 정리·현행화가 며칠씩 밀리는 것을 막음 |
| 21-Q3 | 잠금을 못 얻어 건너뛸 때 90일 정리도 같이 건너뛸까 | A: 같이 건너뜀([A] 그대로, 다음 날 다시) / B: 정리만은 잠금과 무관하게 실행(정리는 수집 테이블을 건드리지 않음) | **결정(2026-11-22): 추천안대로** — **A** — Q1을 A로 하면 01:00에 잠금이 잡혀 있는 경우는 사용자가 수동 작업을 돌릴 때뿐이고, 다음 날(또는 따라잡기) 바로 지워진다. 단순함 우선 |
| 21-Q4 | ingest가 상주하면 `tour-tools`·`api`의 "ingest 완료 후 기동" 조건이 영원히 안 온다 | A: ingest가 테이블 생성 스크립트 뒤 스케줄러를 띄우고 준비 파일을 써서 **healthcheck → `service_healthy`** / B: 테이블 생성만 하는 1회용 `migrate` 서비스 추가(컨테이너 정의 9개 — ADR-01 "8개"와 다름) | **결정(2026-11-22): 추천안대로** — **A** |
| 21-Q5 | SyncList에서 "마지막 성공 이후" 변경을 어떻게 찾을까(파라미터 **미확인** A12) | A: `arrange=C`(수정일 최신순) 페이지를 넘기다 기준 시각(−1일 여유)보다 오래된 항목이 나오면 멈춤 + "이미 최신" 걸러내기 / B: 요청 파라미터 `modifiedtime`으로 날짜별 조회(있을 때만) / C: 지역 전체를 끝까지 읽음(서울만 수십~150페이지 추정, 매일 예산의 상당 부분) | **결정(2026-11-22): 추천안대로** — **A로 구현하고 I-1 결과로 확정** — A가 안 되면(정렬이 다름) B, B도 안 되면 C(사용자에게 호출 수 보고 후) |
| 21-Q6 | 삭제 신호 | A: `showflag=0`이면 상세 호출 없이 바로 삭제 처리 + 상세 재수집 때 `detailCommon2` 빈 응답도 삭제(03 규칙) / B: `showflag=0`이어도 `detailCommon2` 1회로 확인 후 삭제(호출 1건 추가) | **결정(2026-11-22): 추천안대로** — **A** — `showflag` 의미는 I-1·운영 며칠로 확인(§14), 잘못 지워도 다음에 다시 나타나면 `changed`로 되살아남 |
| 21-Q7 | 보고서가 이미 지워져 `report_id`가 NULL인 개선안(보류 → 나중에 기각 등)을 언제 지울까 | A: `created_at` 90일 지남 + `new`·`rejected`면 삭제(§8.1 C3) / B: 지우지 않음(채택·보류 결정 뒤 바뀐 것은 그대로 남김) | **결정(2026-11-22): 추천안대로** — **A** — [A] §5.1 "new·rejected는 삭제" 규칙을 보고서 삭제 뒤에도 같게 적용 |
| 21-Q8 | 허브 단계 범위 | A: 초기 적재 완료 전에는 건너뜀(20이 완료 때 27개 생성), 완료 뒤에는 **영향 허브 + 빠진 허브(`missing_hubs`)** 를 다시 씀 / B: 영향 허브만(실패한 허브는 사용자가 `ingest hubs`로 수동 재실행) / C: 적재 중에도 영향 시군구 허브를 만듦(반쪽 허브가 생김) | **결정(2026-11-22): 추천안대로** — **A** — 완료 뒤에는 bootstrap이 더 돌지 않으므로 실패 허브 재시도를 21이 맡는 게 자연스럽다. 입력이 같으면 20이 LLM을 부르지 않아 비용 거의 없음 |
| 21-Q9 | "만료·오래된" 기준 | 로그인 세션 = 05 `is_valid` 반대(절대 7일·유휴 2시간), 재설정 코드 = 만료 또는 사용됨, `rate_limits` = 윈도 시작 1일 지남 + 잠금 아님 / 대안: 로그인 세션도 만료 뒤 7일 더 보관(감사용) | **결정(2026-11-22): 추천안대로** — **추천 기준 그대로** — 감사 요구 없음(NFR에 없음) |
| 21-Q10 | 정리하지 않는 것: `usage_events`·`daily_quota`(사용량·비용 통계), `ingest_runs`, raw 스냅샷, 소프트 삭제된 `tour_items` | A: 그대로 보관(글·개인 대화 내용 없음) / B: `usage_events`도 90일(월 누적·대시보드 기간이 짧아짐) | **결정(2026-11-22): 추천안대로** — **A** |
| 21-Q11 | 20 함수 이름(§9)은 같은 날 작성된 20 spec **초안**을 따랐다 | A: 20 확정 후 21 §9 표·`HubsPort`만 맞춘다(병합 순서 20 → 21) / B: 21이 이름을 따로 정해 20에 요구 | **결정(2026-11-22): 추천안대로** — **A** — §9의 성질 ①~④(잠금을 스스로 잡지 않음·삭제 포함 커밋·소프트 삭제 포함·허브 비용 직접 기록)는 20 확정본에서도 유지되어야 함. 20-Q11(잠금 `lock.py`로 옮김)이 "옮기지 않음"이면 21은 03 `bootstrap`에서 import |
| 21-Q12 | 한 단계가 실패하면 | A: 기록하고 다음 단계 계속, 정리는 항상 시도, 실행 결과 `failed` / B: 첫 실패에서 멈춤([03] bootstrap 방식) | **결정(2026-11-22): 추천안대로** — **A** — TourAPI·LightRAG·OpenAI 장애가 90일 정리(NFR-31)를 막지 않게 |
