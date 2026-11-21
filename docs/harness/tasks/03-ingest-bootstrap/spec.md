# 03-ingest-bootstrap — 초기 적재 (서울·제주 × 8종, 이어하기) (spec)

> 하네스 Phase 4 산출물 (spec-writer, 작성 2026-11-21). 상태: **초안 — 사용자 검토 대기**. 브랜치 `feat/03-ingest-bootstrap`, 의존 작업 01-e2e-tools-slice(01이 `dev`에 병합된 뒤 시작).
> 근거: [PL]=program_list.md(G4 승인본) §2 표·§3 "03-ingest-bootstrap"·§1.2·§5 Q6·Q9 · [A]=architecture.md(G3 재승인본) §2.1·§3.3·§4·§5.1·ADR-09·ADR-14·§12 A8·A12 · [R]=requirements.md FR-40·41·42·44·48, NFR-24 · [E]=ERD(`docs/images/src/erd.py`) · [S]=stack-options.md S8·F7 · [TS]=TECH_STACK.md §3 · [01]=`tasks/01-e2e-tools-slice/spec.md` · [PG]=PROGRESS.md 결정 로그(G4 Q6, 01-Q1·Q6).
> **이 작업은 01이 만든 파일·함수·테이블을 넓힌다.** 이름·시그니처는 [01]을 그대로 쓰고, 바꾸는 부분은 §10 "01과 달라지는 점"에 모두 적었다.
> **미확인** = 문서·공식 자료로 확인하지 못한 사실. 구현 중 실제 호출(raw 파일)로 확인하고 §14 표에 결과를 적는다.
> 용어: "테이블 생성 스크립트" = Alembic 리비전 파일([01] §3.3). 이 작업은 **테이블을 새로 만들거나 바꾸지 않는다**(`ingest_state`·`ingest_runs`의 값 형식만 정한다).

---

## 1. 작업 목표

개발계정 일일 한도(1,000건/일 [S F7]) 안에서 **서울·제주 × 콘텐츠 8종 전체**를 여러 날에 나눠, 끊겨도 **멈춘 곳부터 이어서** 적재한다 [R FR-48]. 흐름은 01과 같다(목록 → 상세 3종 → raw → `tour_items` upsert → 엔티티 위키 렌더 → 내용 해시가 바뀐 페이지만 LightRAG 인덱싱) [R FR-40·41·42·44]. 슬라이스 직후 시작해 다른 작업과 병행하며 백그라운드로 누적한다 [PL §1.2].

이 작업으로 되는 것:
- TourAPI 호출 **전에** 공유 카운터에서 1건을 예약하고, 오늘 ingest 예산(기본 800)을 넘는 호출은 **아예 보내지 않는다**(G4 Q6: ingest 800 + 실시간 툴 200, 카운터 공유).
- 일일 한도 오류(22)를 받으면 그날은 더 부르지 않는다. 초당 한도 오류(23)는 이번 실행만 끝낸다(확인 질문 Q2).
- 목록 페이지 커서·"상세 미수집" 큐·"인덱싱 대기" 큐가 모두 DB 상태로 남아, 다시 실행하면 이어서 진행한다.
- 콘텐츠 유형 8종마다 `detailIntro2` 필드를 컬럼·한글 라벨로 매핑하고, 유형별 엔티티 템플릿 8개로 렌더한다.
- 실행마다 `ingest_runs`에 건수·호출 수(오퍼레이션별)·멈춘 이유·남은 양·예상 완료일을 남긴다.
- `nadri ingest status`로 진행률과 예상 완료일을 볼 수 있다. `--follow`로 켜 두면 예산이 다 떨어진 날은 다음 날 00:10(KST)까지 기다렸다가 이어간다.

### 1.1 넣지 않는 것 (이후 작업 범위)
| 빠지는 것 | 들어오는 작업 |
|---|---|
| 실시간 툴 `tour_live`와 그 예산(200) 소비, `nadri_tools` 롤에 카운터 쓰기 권한 부여 | 10 (01-Q6 결정: 10 spec에서 최소 권한 방식 결정) |
| 허브 페이지 27개, lint, 위키 git 커밋, "적재 완료 시 허브 생성" 호출 | 20 (03은 완료 시각만 `ingest_state`에 남김) |
| 매일 01:00 현행화(`areaBasedSyncList2`)·삭제 반영(위키·LightRAG 삭제)·APScheduler 상주 | 21 |
| 골든 평가·리랭커 비교 | 22 |
| 테이블 추가·변경, compose 서비스 추가 | 없음 (01의 4테이블·4서비스 그대로) |
| 이미지(`detailImage2`, 객실 이미지 필드) | 범위 밖 ([PG] O 결정: 답변 이미지 표시 안 함) |

---

## 2. 생성·수정 파일

경로의 `nadri/`는 `backend/src/nadri/`([01] §2).

| 파일 | 신규/수정 | 역할 |
|---|---|---|
| `nadri/ingest/budget.py` | 신규 | 날짜별 공유 카운터(`ingest_state`) 읽기·**예약**·한도 도달 표시, 남은 예산, 예상 완료일 계산 (§5) |
| `nadri/core/tourapi.py` | 수정 | `on_call` 호출 시점을 "보내기 직전"으로 바꿈(예외로 요청 막기 가능), 유형별 `detailIntro2` 해석 규칙 `INTRO_SPECS`, 목록 item 해석 (§6) |
| `nadri/ingest/upsert.py` | 수정 | `build_record`를 유형별 규칙으로 확장, 목록 item → 껍데기 행(`build_stub_record`·`insert_stub_stmt`), 소프트 삭제 문 (§7) |
| `nadri/ingest/wiki/render.py` | 수정 | 유형별 템플릿 선택·렌더 컨텍스트 조립(`build_context`) (§8) |
| `nadri/ingest/wiki/templates/entity.md.j2` | 수정 | 공통 뼈대(frontmatter·머리줄·개요·추가 정보·출처)를 `{% block %}`으로 나눔 |
| `nadri/ingest/wiki/templates/entity_{12,14,15,25,28,32,38,39}.md.j2` | 신규 8개 | 유형별 "기본 정보" 블록과 특수 절(행사 기간·코스·객실) |
| `nadri/ingest/bootstrap.py` | 수정 | 목록 커서 → 상세 큐 → 배치 인덱싱, 이어하기, 실패 횟수, 수집 쓰기 잠금, `--follow` 반복, `ingest_runs` 기록, 진행 현황 (§9) |
| `nadri/cli.py` | 수정 | `ingest bootstrap` 옵션 교체, `ingest status` 추가 (§9.7) |
| `backend/tests/**` | 신규·수정 | test.md. 01의 U-TA-12·U-BS-1~3·U-UP-8 수정(§10) |
| `CLAUDE.md` | 수정 | "명령어" 절에 `ingest bootstrap [--follow]`·`ingest status` 추가 |
| `docs/harness/tasks/03-ingest-bootstrap/spec.md` §14 | 수정 | 구현 중 가정 판정 결과 기록 |

> [PL] 파일 목록에 없는 수정: `upsert.py`·`render.py`(유형별 매핑·템플릿 선택이 여기 있어야 함 — [01] 구조상 필연), `ingest status` 명령(확인 질문 Q8).

---

## 3. 설정

새 환경변수는 만들지 않는다. [01] §4.2의 `TOURAPI_DAILY_INGEST_BUDGET`(기본 `800`)을 **강제 예산**으로 쓴다(01은 실행 전 점검만 했음).

모듈 상수(설정값으로 빼지 않음 — 단순함 우선 [CL]):
| 상수 | 위치 | 값 | 이유 |
|---|---|---|---|
| `LIST_PAGE_SIZE` | bootstrap.py | `100` | 목록 1회 100건([01] §9 적재 일수 식과 같음). `numOfRows` 상한은 **미확인** |
| `DETAIL_CALLS_PER_ITEM` | bootstrap.py | `3` | 상세 3종 |
| `INDEX_BATCH` | bootstrap.py | `20` | 상세 20건마다 인덱싱(중단돼도 잃는 양이 작게) |
| `MAX_ATTEMPTS` | bootstrap.py | `3` | 같은 항목 상세 실패 3회면 큐에서 뺌(확인 질문 Q7) |
| `RESUME_AT` | bootstrap.py | `time(0, 10)` KST | `--follow`가 다음 날 다시 시작하는 시각(자정 직후 카운터 초기화 시각 차이 여유 — 포털 초기화 시각 **미확인**) |
| `RATE_RETRY_WAIT_S` / `RATE_RETRY_MAX` | bootstrap.py | `60` / `3` | `--follow`에서 23 오류 뒤 대기·연속 허용 횟수 |
| `INGEST_WRITE_LOCK_KEY` | bootstrap.py | `1` | 수집 쓰기 잠금(21 `daily_sync`와 같은 키 — 확인 질문 Q10) |

---

## 4. `ingest_state` 키와 값 형식 (테이블 변경 없음)

[01] §3.2의 `ingest_state(key text PK, value jsonb)`에 아래 키를 쓴다. 날짜는 모두 **KST**.

| 키 | 값 | 쓰는 곳 |
|---|---|---|
| `tourapi_calls:YYYY-MM-DD` | `{"ingest": int, "live": int, "ops": {"<오퍼레이션>": int}, "quota_hit": bool}` | budget.py (01 형식 `{"ingest","live"}`의 **상위 집합** — 없는 키는 0/`{}`/`false`로 읽음). `live`는 10이 채운다 |
| `bootstrap:list:<지역>:<유형>` (예: `bootstrap:list:서울:12`) | `{"next_page": int, "total_count": int \| null, "done": bool, "updated_at": ISO}` | 목록 커서 (§9.2) |
| `bootstrap:failures` | `{"<contentid>": {"attempts": int, "last_error": str, "last_at": ISO}}` | 상세 실패 횟수 (§9.3) |
| `bootstrap:completed_at` | `{"at": ISO}` | 목록 16칸 완료 + 상세 큐 0 + 인덱싱 대기 0이 처음 된 시각. 20이 허브 생성 시점 판단에 쓴다 |

- `ops`는 포털 마이페이지(오퍼레이션별 표시로 추정, **미확인**)와 대조하기 위한 분해 값이다. `ingest`·`live`는 합계.
- 오래된 날짜 키는 지우지 않는다(하루 1행, 정리 필요 없음).

---

## 5. `ingest/budget.py` — 공유 카운터와 예산

### 5.1 규칙
1. **예약 후 호출**: TourAPI 요청을 보내기 직전에 `reserve(op)`가 카운터를 +1 한다. 오늘 `kind` 사용량이 `limit` 이상이거나 `quota_hit`이면 +1 하지 않고 `BudgetExhausted`를 던진다 → 요청을 보내지 않는다. 그래서 **"예산 초과 없음"이 코드로 보장**된다(동시 실행·실시간 툴과 경합해도 행 잠금으로 직렬화).
2. 예약한 호출은 실패(타임아웃·HTTP 오류·22 등)해도 되돌리지 않는다 — 포털도 실패 호출을 셀 수 있어 보수적으로 센다([01] §6.2와 같은 판단, **미확인**).
3. 22(일일 한도 초과)를 받으면 `mark_quota_hit()` → 그날 남은 예약이 모두 거부된다(ingest·live 모두). 우리 셈과 포털 셈이 어긋났다는 신호이므로 `ingest_runs.stats.stop_reason="quota"`로 남겨 보고한다.
4. 날짜는 `reserve` 때마다 시계로 다시 계산한다 — 실행 중 자정을 넘기면 새 날짜 키로 자연스럽게 넘어간다.
5. **예산 단위**(서비스 전체 vs 오퍼레이션별): 01의 A12 판정 결과를 따른다(확인 질문 Q3). 판정이 "미확인"이면 **서비스 전체 합계 ≤ 800**(보수적)으로 구현한다. 아래 SQL은 서비스 전체 기준이다.

### 5.2 시그니처
```python
class BudgetExhausted(Exception):
    """오늘 예산을 다 썼거나 일일 한도(22)에 도달해 TourAPI 요청을 보내지 않았음을 알린다."""

def calls_key(day: date) -> str:
    """'tourapi_calls:YYYY-MM-DD' 키를 만든다."""
def kst_today(now: datetime) -> date:
    """tz-aware 시각을 KST 날짜로 바꾼다. naive면 ValueError."""

@dataclass(frozen=True)
class DayUsage:
    """하루치 카운터 값."""
    ingest: int
    live: int
    ops: dict[str, int]
    quota_hit: bool
    @classmethod
    def from_value(cls, value: dict | None) -> "DayUsage":
        """jsonb 값을 읽는다. 01 형식(ops·quota_hit 없음)·None도 받는다(없는 값은 0/{}/False)."""

def remaining(usage: DayUsage, kind: Literal["ingest", "live"], limit: int) -> int:
    """오늘 kind가 더 쓸 수 있는 호출 수. quota_hit면 0, 음수는 0."""

def build_ensure_stmt(key: str) -> Insert:
    """INSERT INTO ingest_state(key, value) VALUES (:key, '{"ingest":0,"live":0,"ops":{},"quota_hit":false}') ON CONFLICT DO NOTHING."""
def build_reserve_stmt(key: str, kind: str, op: str, limit: int) -> TextClause:
    """조건(사용량 < limit, quota_hit 아님)을 만족할 때만 kind 합계와 ops[op]를 +1 하고 새 합계를 RETURNING 하는 UPDATE 문."""
def build_quota_hit_stmt(key: str) -> TextClause:
    """value의 quota_hit를 true로 바꾸는 UPDATE 문(행이 없으면 ensure 후 실행)."""

class Budget:
    """한 종류(kind)의 TourAPI 일일 예산. TourApiClient의 on_call로 reserve를 넘긴다."""
    def __init__(self, sf: async_sessionmaker[AsyncSession], *, kind: Literal["ingest", "live"],
                 limit: int, clock: Callable[[], datetime] = lambda: datetime.now(KST)) -> None: ...
    async def reserve(self, op: str) -> None:
        """1건 예약. 실패하면 BudgetExhausted. 한 트랜잭션에서 ensure → reserve UPDATE → 커밋."""
    async def usage(self, day: date | None = None) -> DayUsage: ...
    async def remaining(self) -> int: ...
    async def mark_quota_hit(self) -> None: ...

def estimate_completion(*, list_pages_left: int, detail_queue: int, used_today: int,
                        budget: int, today: date) -> tuple[int, date]:
    """남은 호출 수로 (추가로 필요한 날 수, 예상 완료일)을 계산한다(순수 함수, §5.3)."""
```

reserve UPDATE 요지(서비스 전체 기준, 구현자가 문법만 다듬는다 — 값은 전부 바인드 파라미터):
```sql
UPDATE ingest_state
SET value = jsonb_set(
      jsonb_set(value, ARRAY[:kind], to_jsonb(COALESCE((value->>:kind)::int, 0) + 1)),
      '{ops}',
      COALESCE(value->'ops', '{}'::jsonb)
        || jsonb_build_object(:op, COALESCE((value->'ops'->>:op)::int, 0) + 1))
WHERE key = :key
  AND COALESCE((value->>:kind)::int, 0) < :limit
  AND NOT COALESCE((value->>'quota_hit')::boolean, false)
RETURNING (value->>:kind)::int
```
- 반환 행이 없으면 `BudgetExhausted`. 10이 tour-tools(`nadri_tools` 롤)에서 같은 문을 쓰려면 권한이 필요하다 — 10 spec에서 결정(01-Q6). 이 문은 한 문장이라 SECURITY DEFINER 함수로 감싸기도 쉽다.
- 01의 `record_call(sf, day, kind)`·`calls_today(sf, day)`는 `Budget.reserve`·`Budget.usage`로 대체하고 bootstrap.py에서 지운다(§10).

### 5.3 예상 완료일 식
- 남은 호출 `R = list_pages_left + DETAIL_CALLS_PER_ITEM × detail_queue`.
- 오늘 남은 예산 `T = max(0, budget − used_today)`.
- `R ≤ T`면 `(0, today)`. 아니면 `days = ceil((R − T) / budget)`, 완료일 = `today + days`.
- 전제: 매일 한 번 이상 실행(`--follow` 또는 수동). 인덱싱 시간은 넣지 않는다(01 측정에서 하루 처리량 안에 끝난다고 확인되면 무시, 아니면 §14에 기록).
- `list_pages_left`: 커서의 `total_count`가 있으면 `ceil(total_count / LIST_PAGE_SIZE) − (next_page − 1)`, `total_count`가 아직 없으면(첫 페이지 전) 1로 센다.
- 예시(가상의 수치 — 실제 값은 01 `ingest count`·03 첫날 결과로 바꾼다): 상세 큐 20,000건, 오늘 사용 0 → `R = 60,000`, `T = 800` → 추가 74일.

---

## 6. `core/tourapi.py` 확장

### 6.1 `on_call` 시점 변경
- [01] §6.2: "HTTP 요청을 보낸 **직후** 호출". → 03: **보내기 직전** 호출하고, 콜백이 예외를 던지면 요청을 보내지 않고 그 예외를 그대로 올린다. 시그니처는 같다(`on_call: Callable[[str], Awaitable[None]] | None`, 인자 = 오퍼레이션 이름).
- 셈 결과는 01과 같다(보낸 요청은 성공·실패 무관하게 1건). 달라지는 것은 "예산이 없으면 안 보냄"뿐이다(확인 질문 Q1).

### 6.2 목록 item 해석
```python
@dataclass(frozen=True)
class ListItem:
    """areaBasedList2 item 한 건에서 쓰는 값(정리 전 원문)."""
    contentid: str; content_type_id: int; title: str
    addr1: str | None; addr2: str | None; sigungucode: str | None
    mapx: str | None; mapy: str | None; tel: str | None; modifiedtime: str | None

def parse_list_item(item: dict) -> ListItem:
    """목록 item dict를 ListItem으로 바꾼다. contentid·contenttypeid·title이 없으면 ValueError."""
```
- 필드 이름은 [01] §6.4 매핑과 같은 가정(**미확인** — 01 첫 실호출에서 확인된 이름을 따른다).

### 6.3 유형별 `detailIntro2` 해석 규칙 `INTRO_SPECS`
```python
@dataclass(frozen=True)
class IntroSpec:
    """유형 하나의 detailIntro2 필드 해석 규칙."""
    tel: tuple[str, ...]             # common.tel이 비었을 때 볼 intro 필드(앞에서부터 첫 값)
    usetime: tuple[str, ...]         # 이용·영업 시간. 2개 이상이면 "라벨 값" 줄을 \n으로 합침
    restdate: str | None             # 휴무일
    fee: str | None                  # intro 안 요금 필드. None이거나 값이 비면 detailInfo2에서 찾음(§7.1)
    event_start: str | None          # YYYYMMDD
    event_end: str | None
    labels: dict[str, str]           # 위에서 쓰지 않은 필드의 한글 표시 이름(표시 순서 = dict 순서)
    ignore: frozenset[str] = frozenset()   # 버리는 필드(코드성·0/1 표시 값)

COMMON_IGNORE = frozenset({"contentid", "contenttypeid"})   # 모든 유형 공통
INTRO_SPECS: dict[int, IntroSpec]                           # 8종, 아래 표

def split_intro(content_type_id: int, intro: dict) -> tuple[dict[str, str | None], dict[str, str], list[str]]:
    """intro를 (핵심 컬럼 값 dict, 나머지 {필드명: 값}, 규칙(labels)에 없는 필드 이름 목록)으로 나눈다(순수 함수).
    값은 clean_text 적용, 빈 값·ignore 필드는 버림. 규칙에 없는 필드도 나머지에 남긴다(정보 유실 없음).
    알 수 없는 유형이면 ValueError."""

def intro_lines(content_type_id: int, rest: dict[str, str]) -> list[tuple[str, str]]:
    """나머지 필드를 표시용 [(한글 라벨, 값)]으로 바꾼다(순수 함수). 순서 = labels 순서, 규칙에 없는 필드는
    필드명을 라벨로 써서 이름순으로 끝에 붙인다."""
```
- 핵심 컬럼 값 dict 키: `tel`, `usetime`, `restdate`, `fee`, `event_start`, `event_end`(날짜 문자열 원문).

**유형별 규칙 표** — 필드 이름은 KorService1 시절 공개 명세를 기준으로 한 **추정이다(미확인)**. 구현 첫 단계에서 8종 각 1건의 실제 `detailIntro2` raw와 대조해 이 표와 `INTRO_SPECS`를 함께 고친다(test.md I-5, §14 "필드 이름").

| 유형 | tel | usetime | restdate | fee | event | labels (필드 → 한글) | ignore |
|---|---|---|---|---|---|---|---|
| 12 관광지 | `infocenter` | `usetime` | `restdate` | — (info에서) | — | useseason 이용 시기, opendate 개장일, expguide 체험 안내, expagerange 체험 가능 연령, accomcount 수용 인원, parking 주차, chkbabycarriage 유모차 대여, chkpet 반려동물 동반, chkcreditcard 신용카드 | heritage1·2·3 |
| 14 문화시설 | `infocenterculture` | `usetimeculture` | `restdateculture` | `usefee` | — | spendtime 관람 소요시간, discountinfo 할인 정보, scale 규모, accomcountculture 수용 인원, parkingculture 주차, parkingfee 주차 요금, chkbabycarriageculture 유모차 대여, chkpetculture 반려동물 동반, chkcreditcardculture 신용카드 | |
| 15 축제공연행사 | `sponsor1tel` | `playtime` | — | `usetimefestival` (명세상 "이용요금", **미확인**) | `eventstartdate`·`eventenddate` | eventplace 행사 장소, placeinfo 행사장 위치 안내, sponsor1 주최, sponsor2 주관, sponsor2tel 주관 연락처, agelimit 관람 가능 연령, spendtimefestival 관람 소요시간, bookingplace 예매처, program 행사 프로그램, subevent 부대 행사, discountinfofestival 할인 정보, festivalgrade 축제 등급, eventhomepage 행사 홈페이지 | |
| 25 여행코스 | `infocentertourcourse` | — | — | — | — | distance 코스 총거리, taketime 소요 시간, schedule 일정, theme 테마 | |
| 28 레포츠 | `infocenterleports` | `usetimeleports` | `restdateleports` | `usefeeleports` | — | openperiod 개장 기간, reservation 예약 안내, expagerangeleports 체험 가능 연령, scaleleports 규모, accomcountleports 수용 인원, parkingleports 주차, parkingfeeleports 주차 요금, chkbabycarriageleports 유모차 대여, chkpetleports 반려동물 동반, chkcreditcardleports 신용카드 | |
| 32 숙박 | `infocenterlodging` | `checkintime`(입실), `checkouttime`(퇴실) | — | — (info에서) | — | roomcount 객실 수, roomtype 객실 유형, reservationlodging 예약 안내, reservationurl 예약 페이지, refundregulation 환불 규정, chkcooking 객실 내 취사, subfacility 부대시설, foodplace 식음료장, pickup 픽업 서비스, scalelodging 규모, accomcountlodging 수용 인원, parkinglodging 주차 | benikia, goodstay, hanok |
| 38 쇼핑 | `infocentershopping` | `opentime` | `restdateshopping` | — | — | saleitem 판매 품목, saleitemcost 품목별 가격, fairday 장 서는 날, shopguide 매장 안내, opendateshopping 개장일, scaleshopping 규모, restroom 화장실, culturecenter 문화센터, parkingshopping 주차, chkbabycarriageshopping 유모차 대여, chkpetshopping 반려동물 동반, chkcreditcardshopping 신용카드 | |
| 39 음식점 | `infocenterfood` | `opentimefood` | `restdatefood` | — | — | firstmenu 대표 메뉴, treatmenu 취급 메뉴, reservationfood 예약 안내, packing 포장, seat 좌석 수, smoking 금연·흡연, kidsfacility 어린이 놀이방, discountinfofood 할인 정보, opendatefood 개업일, scalefood 규모, parkingfood 주차, chkcreditcardfood 신용카드 | lcnsno |

- 32의 usetime 합치기 예: `"입실 15:00\n퇴실 11:00"`(한쪽만 있으면 그 줄만). 라벨은 위 괄호 안 글자.
- `ignore` 근거: heritage·benikia·goodstay·hanok는 0/1 표시 값이라 페이지에 "1"로 찍혀 의미가 없다(**미확인** — 실제 값이 글이면 labels로 옮긴다). `lcnsno`(인허가번호)는 관광 정보가 아님.

---

## 7. `ingest/upsert.py` 확장

### 7.1 `build_record` (시그니처는 [01] 그대로)
`build_record(area, common, intro, info, fetched_at) -> TourItemRecord` — `content_type_id = int(common["contenttypeid"])`로 유형을 정하고 아래 규칙을 쓴다. [01] §6.4 매핑 표 중 유형과 무관한 줄(contentid·title·area·sigungu_code·addr·lat/lng·modifiedtime·detail_synced_at·as_of, `clean_text` 적용)은 그대로다.

| 컬럼 | 03 규칙 |
|---|---|
| tel | common `tel` → 비면 `INTRO_SPECS[유형].tel` 순서대로 첫 값 |
| usetime / restdate | `split_intro` 핵심 값 |
| fee | `split_intro`의 fee → 비면 detailInfo2 일반형 항목 중 `infoname`의 **공백을 모두 지운 값**에 "입장료" 또는 "이용요금"이 들어간 첫 `infotext`(예: "입 장 료" 매칭) → 없으면 None |
| event_start / event_end | 15만: `YYYYMMDD` → `date`. 형식이 다르거나 비면 None(예외 없음). 시작 > 종료면 둘 다 그대로 두고 `errors`에 경고 한 줄 |
| extra | [01] 형식 그대로 `{"overview", "homepage", "intro": {필드명: 값}, "info": [{"name","text"}]}` + 03 추가 `"course": [...]`(25), `"rooms": [...]`(32) — 빈 키는 넣지 않음. `intro`는 `split_intro`의 나머지 dict(핵심 컬럼으로 간 필드·ignore 필드 제외) |

- **extra 형식은 [01]과 같다**(`intro`는 필드명 dict). 한글 라벨·표시 순서는 저장하지 않고 렌더 때 `intro_lines`로 붙인다 → 01 적재 50행도 같은 방식으로 렌더되고, 라벨을 고쳐도 데이터를 다시 받을 필요가 없다(확인 질문 Q11).
- detailInfo2 모양(**미확인**, 유형별로 다름):
  - 일반형(12·14·15·28·38·39 추정): `infoname`·`infotext` → `info`.
  - 25 여행코스: `subnum`, `subcontentid`, `subname`, `subdetailoverview` → `course = [{"order": int(subnum), "contentid", "name", "overview"}]`, `order` 오름차순(숫자 아님 → 맨 뒤, 원래 순서).
  - 32 숙박: `roomtitle`, `roomsize1`, `roomcount`, `roombasecount`, `roommaxcount`, `roomoffseasonminfee1`, `roompeakseasonminfee1`, `roomintro` → `rooms = [{"name","size","count","base","max","fee_off","fee_peak","intro"}]`. 값 `"0"`·빈 값은 None(요금 0원 표시 방지). 이미지 필드(`roomimg*`)는 버린다.
  - 판별은 유형으로 하되, item에 `infoname`이 있으면 유형과 무관하게 일반형으로 처리한다(명세와 실제가 다를 때 유실 방지).
- 매핑 규칙에 없는 intro 필드 이름은 `build_record`가 반환하지 않으므로, bootstrap이 `split_intro`의 세 번째 값을 모아 `stats.unknown_intro_fields`에 유형별로 남긴다(§9.6) — 표를 고칠 근거.

### 7.2 껍데기 행(목록 단계)
```python
def build_stub_record(area: str, li: ListItem, fetched_at: datetime) -> dict:
    """목록 item으로 tour_items 껍데기 행 값을 만든다(순수 함수). detail_synced_at=None, extra={}, as_of=KST 날짜.
    title·addr·tel은 clean_text, 좌표·modifiedtime은 [01] §6.4 규칙."""
def insert_stub_stmt(values: dict) -> Insert:
    """INSERT … ON CONFLICT (contentid) DO NOTHING RETURNING contentid — 이미 있는 행(01 적재분 포함)은 건드리지 않는다."""
def soft_delete_stmt(contentid: str, now: datetime) -> Update:
    """UPDATE tour_items SET deleted_at=:now, updated_at=:now WHERE contentid=:id AND deleted_at IS NULL."""
```
- 껍데기 행 = [A] §3.3의 "상세 미수집" 큐(`detail_synced_at IS NULL`)를 초기 적재에도 쓰는 것. 상세를 받으면 [01] `upsert_tour_item`이 같은 행을 `updated`로 채운다.
- 껍데기 행도 `data_query`에 보인다(제목·주소·좌표·전화는 실제 목록 값). 확인 질문 Q6.

---

## 8. 위키 렌더 — 유형별 템플릿 8종

### 8.1 구조
- `entity.md.j2`(공통 뼈대, [01] 형태 유지): frontmatter → `# 제목` → 머리줄 `관광지 ID: N · 유형: X · 지역: Y` → `{% block basic %}` → `{% block special %}{% endblock %}` → `## 개요` → `## 추가 정보` → 출처 줄.
- `entity_<유형>.md.j2` 8개: `{% extends "entity.md.j2" %}` 후 `basic`(필요하면 `special`)만 채운다. 템플릿 밖 로직 없음.
- frontmatter 키·순서·`yq` 필터·결정성 규칙·"값 없는 줄/빈 절 출력 안 함"은 [01] §6.5 그대로. FR-42 필수 키(contentid·source·as_of·updated_at) 유지.
- 머리줄의 `관광지 ID: N`은 유형과 무관하게 같은 글자로 둔다(A7 대안 정규식 근거, [01] §9). 코스 항목 등 다른 ID는 `ID 126508` 형태로만 쓴다(정규식이 첫 머리줄만 잡도록).

### 8.2 유형별 "기본 정보" 블록 (줄 순서 고정, 값 없으면 줄 생략)
| 유형 | 템플릿 | 기본 정보 줄 | 특수 절 (`special`) |
|---|---|---|---|
| 12 | `entity_12.md.j2` | 주소, 전화, 이용시간, 휴무일, 이용요금 | — |
| 14 | `entity_14.md.j2` | 주소, 전화, 이용시간, 휴무일, 이용요금 | — |
| 15 | `entity_15.md.j2` | **행사 기간**(`YYYY-MM-DD ~ YYYY-MM-DD`, 한쪽만 있으면 그쪽만), 주소, 문의 전화, 공연 시간, 이용요금 | — |
| 25 | `entity_25.md.j2` | 전화 | `## 코스` 번호 목록: `1. 이름 (ID 126508)` + 다음 줄 들여쓴 개요 |
| 28 | `entity_28.md.j2` | 주소, 전화, 이용시간, 휴무일, 이용요금 | — |
| 32 | `entity_32.md.j2` | 주소, 전화, 입실·퇴실(usetime 여러 줄은 `, `로 이어 한 줄), 이용요금 | `## 객실` 불릿: `- 이름 (크기 N, 기준 N명·최대 N명, 비수기 최저 N원, 성수기 최저 N원)` — 괄호 안도 값 있는 것만 |
| 38 | `entity_38.md.j2` | 주소, 전화, 영업시간, 휴무일 | — |
| 39 | `entity_39.md.j2` | 주소, 전화, 영업시간, 휴무일 | — |

- `## 추가 정보`: `intro_lines(유형, extra.intro)`의 `라벨: 값` 줄 → `extra.info`의 `이름: 값` 줄. 값에 줄바꿈이 있으면 다음 줄부터 두 칸 들여쓰기.
- 요금 숫자 형식(천 단위 쉼표 등)은 바꾸지 않는다(원문 그대로) — 객실 요금만 숫자 문자열이면 `100,000원`으로 표시.

### 8.3 시그니처
```python
TEMPLATE_BY_TYPE: dict[int, str] = {t: f"entity_{t}.md.j2" for t in CONTENT_TYPES}

def build_context(item: TourItem) -> dict:
    """렌더 컨텍스트를 만든다(순수 함수): item 필드, type_name, intro_lines(한글 라벨 적용), info_lines, course, rooms, event_period."""
def render_entity(item: TourItem) -> str:
    """[01]과 같은 이름·의미. content_type_id로 템플릿을 골라 렌더한다. 모르는 유형이면 ValueError."""
```
- `entity_path`·`content_hash`·`write_page`는 [01] 그대로.
- **01로 적재된 50페이지**: 템플릿이 바뀌므로 내용 해시가 달라진다. 03 병합 직후 `nadri ingest reindex` 1회로 50페이지를 다시 인덱싱한다(인덱싱 비용 50페이지분, test.md H-2). 이후 bootstrap의 인덱싱 대기 큐는 "해시 없음"만 보므로 자동으로 하지 않는다.

---

## 9. `ingest/bootstrap.py` — 이어하기 적재

### 9.1 한 번의 실행 순서 (`run_bootstrap`)
1. **수집 쓰기 잠금**: 전용 연결에서 `pg_try_advisory_lock(INGEST_WRITE_LOCK_KEY)`. 실패하면 아무것도 하지 않고 `LockBusy` → CLI 종료 코드 4. 실행이 끝나면 해제(`--follow`의 대기 중에는 잡고 있지 않음).
2. **멈춘 기록 정리**: `ingest_runs`에서 `kind='bootstrap' AND status='running'`인 행(잠금을 얻었으니 모두 비정상 종료분)을 `status='failed'`, `error='중단됨 — 다음 실행에서 정리'`, `finished_at=now()`로 바꾼다.
3. `ingest_runs`에 `kind=bootstrap, status=running` 행 생성.
4. **인덱싱 대기분 먼저 처리**: §9.4 `index_pending()` — TourAPI를 쓰지 않으므로 예산과 무관.
5. **목록 단계** §9.2: 대상 16칸(필터 적용) 중 `done=false`인 칸을 고정 순서로 페이지 단위 진행. 예산이 1건도 없으면 멈춤.
6. **상세 단계** §9.3: 큐에서 `INDEX_BATCH`건씩 꺼내 상세 3종 → raw → upsert → 렌더 → 파일 → `wiki_pages`, 배치마다 `index_pending()`.
7. 멈춘 이유(`stop_reason`) 결정 후 마지막 `index_pending()`.
8. 남은 양 계산(목록 남은 페이지·상세 큐·인덱싱 대기) → `estimate_completion` → `stats`. 셋 다 0이고 목록 16칸이 모두 `done`이면 `bootstrap:completed_at`을 (없을 때만) 기록.
9. `ingest_runs` 갱신(`finished_at`, `stats`, `status`, `error`), 잠금 해제. 예외는 `error`에 메시지(비밀값 없음) 저장 후 다시 던진다([01] §6.7과 같음).

멈춘 이유와 결과(`status`)·종료 코드:
| stop_reason | 뜻 | status | 단발 실행 종료 코드 | `--follow` |
|---|---|---|---|---|
| `complete` | 목록 done·상세 큐 0·마지막 인덱싱 뒤 대기 큐 0 | done | 0 | 종료(0) |
| `index_retry` | 목록·상세는 끝났지만 이번 실행에서 인덱싱 실패한 페이지가 남음 | failed | 1 | 다음 날 대기 후 반복(실패 페이지 재시도) |
| `budget` | 오늘 ingest 예산 소진(다음 항목에 3건이 안 남음 포함) | done | 0 (시작부터 0건이면 3) | 다음 날 `RESUME_AT`까지 대기 후 반복 |
| `max_items` | `--max-items` 도달 | done | 0 | (조합 금지, 인자 오류) |
| `quota` | 22 받음 → `mark_quota_hit` | failed | 1 | 다음 날 대기 후 반복 |
| `rate` | 23 받음 | failed | 1 | `RATE_RETRY_WAIT_S` 대기 후 반복, 연속 `RATE_RETRY_MAX`회면 종료(1) |
| `error` | 그 밖의 예외 | failed | 1 | 종료(1) |
```python
class LockBusy(Exception):
    """수집 쓰기 잠금을 다른 실행이 잡고 있음."""
def run_status(stop_reason: str, index_failed: int) -> Literal["done", "failed"]:
    """위 표대로 ingest_runs.status를 정한다(순수 함수)."""
def exit_code(stop_reason: str, *, started_with_zero_budget: bool) -> int:
    """단발 실행 종료 코드를 정한다(순수 함수). 잠금 실패(4)는 CLI가 LockBusy를 잡아 직접 돌려준다."""
def cap_errors(errors: list[str], limit: int = 50) -> list[str]:
    """오류 줄을 limit개로 자르고 넘친 수를 '외 N건' 한 줄로 붙인다."""
```
- 인덱싱 실패가 1건 이상이면 stop_reason과 무관하게 `status=failed`([01] 규칙 유지). 종료 코드는 위 표를 따르고(`complete`·`budget`이면 0) 실패 건수는 요약에 표시한다 — 다음 실행에서 자동 재시도되므로 반복을 멈추지 않는다.
- `budget`·`quota`일 때 `--follow`가 다음 날 다시 시작하는 시각: **다음 KST 날짜의 `RESUME_AT`**(같은 날 00:10 이전이어도 다음 날).

### 9.2 목록 단계 — 커서
```python
@dataclass
class ListCursor:
    """지역×유형 한 칸의 목록 진행 상태(ingest_state 'bootstrap:list:<지역>:<유형>')."""
    area: str; content_type_id: int
    next_page: int = 1; total_count: int | None = None; done: bool = False

def cursor_key(area: str, content_type_id: int) -> str: ...
def cursor_from_value(area: str, content_type_id: int, value: dict | None) -> ListCursor: ...
def advance_cursor(c: ListCursor, *, page_no: int, total_count: int, items_on_page: int,
                   page_size: int = LIST_PAGE_SIZE) -> ListCursor:
    """한 페이지를 받은 뒤의 커서. page_no × page_size ≥ total_count 이거나 items_on_page == 0 이면 done."""
def pending_cells(cursors: list[ListCursor]) -> list[ListCursor]:
    """done 아닌 칸을 고정 순서(지역: 서울→제주, 유형: 12·14·15·25·28·32·38·39)로 돌려준다."""
def relist_cursor(c: ListCursor) -> ListCursor:
    """--relist용: next_page=1, done=False로 되돌린다(total_count는 유지)."""
```
처리:
1. 칸 순서대로, 칸 하나를 `done`까지 페이지를 이어 받는다(칸 사이를 섞지 않음 — 커서 단순).
2. 페이지마다: `area_based_list(area, type, num_of_rows=LIST_PAGE_SIZE, page_no=next_page)` → `save_raw(key="{area}_{type}_p{page}")` → item마다 `parse_list_item` → `insert_stub_stmt`(새로 들어간 수 = `stubs_inserted`) → 같은 트랜잭션에서 커서 저장 → 커밋. **커서는 페이지가 DB에 들어간 뒤에만 전진**한다(중간에 끊기면 그 페이지를 다시 받음 — 중복은 `DO NOTHING`).
3. `parse_list_item` 실패 item은 `errors`에 `"list <area>:<type> p<page>: 사유"`로 남기고 건너뛴다.
4. 정렬 파라미터는 [01]과 같은 `arrange=C`. 목록 단계는 보통 첫날 안에 끝나므로(전체 페이지 수 = Σ ceil(totalCount/100), 01 측정치로 확인) 날을 넘겨 페이지가 밀리는 일은 드물다. 밀려서 빠진 항목은 21 현행화가 메운다고 가정한다(**미확인** A12 — SyncList가 신규 항목도 주는지). `--relist`로 커서를 1페이지로 되돌려 목록만 다시 훑을 수 있다(껍데기는 `DO NOTHING`이라 안전).
5. 목록 단계가 끝난 칸은 `stats.list_check`에 `{칸: {"total_count", "rows"}}`(DB의 그 칸 행 수)를 남긴다 — 차이가 크면 보고.

### 9.3 상세 단계 — "상세 미수집" 큐
큐 조회 문(`build_queue_stmt(areas, types, excluded, limit)`, 값은 모두 바인드):
```sql
SELECT contentid, content_type_id, area FROM (
  SELECT contentid, content_type_id, area,
         row_number() OVER (PARTITION BY area, content_type_id ORDER BY contentid) AS rn
  FROM tour_items
  WHERE detail_synced_at IS NULL AND deleted_at IS NULL
    AND area = ANY(:areas) AND content_type_id = ANY(:types)
    AND NOT (contentid = ANY(:excluded))
) q
ORDER BY rn, area, content_type_id
LIMIT :limit
```
- **16칸을 돌아가며 1건씩**(라운드로빈) 꺼낸다 → 첫날부터 8종 모두 표본이 생겨 A8 넓은 표본 확인이 가능하다(확인 질문 Q5).
- `excluded` = `bootstrap:failures`에서 `attempts ≥ MAX_ATTEMPTS`인 contentid ∪ **이번 실행에서 이미 실패한** contentid(같은 실행 안 무한 반복 방지).

`detail_loop` — 예산·오류 판단만 담당하는 반복(테스트에서 가짜를 꽂을 수 있게 DB·HTTP를 콜백으로 받음):
```python
@dataclass(frozen=True)
class QueueItem:
    contentid: str; content_type_id: int; area: str

ItemResult = Literal["stored", "deleted"]

@dataclass
class DetailLoopResult:
    """상세 반복 결과."""
    stop_reason: Literal["complete", "budget", "quota", "rate", "max_items"]
    stored: int; deleted: int
    failed: dict[str, str]                 # contentid → 사유(이번 실행)

async def detail_loop(*, next_batch: Callable[[int, set[str]], Awaitable[list[QueueItem]]],
                      process_item: Callable[[QueueItem], Awaitable[ItemResult]],
                      after_batch: Callable[[], Awaitable[None]],
                      remaining: Callable[[], Awaitable[int]],
                      on_quota: Callable[[], Awaitable[None]],
                      record_failure: Callable[[str, str], Awaitable[None]],
                      max_items: int | None, batch_size: int = INDEX_BATCH) -> DetailLoopResult:
    """큐가 빌 때까지(또는 예산·한도·개수 제한까지) 항목을 처리하고 배치마다 after_batch(인덱싱)를 부른다."""
```
반복 규칙:
1. 배치 조회 `next_batch(batch_size, 이번 실행 실패 집합)` → 비면 `complete`.
2. 항목마다, 처리 **전에** `remaining() < DETAIL_CALLS_PER_ITEM`이면 `budget`(그 항목은 시작하지 않음 — 반쪽 호출 방지). `max_items`에 도달했으면 `max_items`.
3. `process_item(item)`:
   - `stored`/`deleted` → 카운트.
   - `BudgetExhausted`(다른 프로세스와 경합해 중간에 소진) → 그 항목은 미완료로 큐에 남김, 실패로 세지 않음, `budget`.
   - `TourApiError.quota_exceeded`(22) → `on_quota()` → `quota`.
   - `TourApiError.rate_limited`(23) → `rate`.
   - 그 밖의 `TourApiError`·변환 오류(`ValueError`) → `failed[contentid]=사유`, `record_failure(contentid, 사유)`(DB에 attempts+1), 다음 항목.
4. 멈추거나 배치가 끝나면 `after_batch()`(멈출 때도 이미 저장한 페이지를 인덱싱하기 위해 반드시 1회).

`process_item` 실제 구현(`make_process_item(...)`):
1. `detail_common` → raw 저장(key=contentid). **item이 0개면**(콘텐츠가 사라진 것으로 추정, **미확인**) `soft_delete_stmt` → `deleted` 반환(나머지 2건 호출 안 함).
2. `detail_intro`·`detail_info` → raw 저장.
3. `build_record` → [01] `upsert_tour_item` → `render_entity` → `write_page` → `wiki_pages` upsert(path·kind=entity·contentid·title·area·sigungu_code·as_of, 해시·doc_id는 건드리지 않음 — [01] §6.7과 같음) → 커밋(항목마다).
4. `split_intro` 세 번째 값(규칙에 없는 필드)을 실행 통계에 모은다.
5. 성공하면 `bootstrap:failures`에서 그 contentid를 지운다(있으면).

### 9.4 인덱싱 대기 큐 (`index_pending`)
```python
def build_index_queue_stmt(limit: int, exclude_paths: set[str]) -> Select:
    """상세를 받았는데(detail_synced_at NOT NULL, deleted_at NULL) wiki_pages 행이 없거나 content_hash가 NULL인 항목."""
async def index_pending(*, sf, settings, lightrag, attempted: set[str], limit: int = INDEX_BATCH * 5) -> IndexStats:
    """대기 큐 항목을 tour_items에서 다시 렌더·파일 저장·wiki_pages upsert 후 [01] index_pages → apply_outcomes."""
```
- `tour_items t LEFT JOIN wiki_pages w ON w.contentid = t.contentid AND w.kind = 'entity'`, 조건 `w.path IS NULL OR w.content_hash IS NULL`.
- 같은 실행에서 이미 시도한 path(`attempted`)는 다시 넣지 않는다(실패 페이지는 다음 실행에서 재시도 — [01] §6.6 "failed면 해시 NULL"과 맞물림).
- 크래시가 어느 지점에서 나도(upsert 후·파일 쓰기 전·인덱싱 전) 다음 실행에서 이 큐가 이어받는다.

### 9.5 `--follow` 반복
```python
def next_resume_at(now: datetime) -> datetime:
    """다음 KST 날짜의 RESUME_AT(tz-aware)을 돌려준다(순수 함수)."""
async def run_follow(opts: BootstrapOptions, *, run_once: Callable[[], Awaitable[BootstrapResult]],
                     sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
                     clock: Callable[[], datetime] = lambda: datetime.now(KST)) -> int:
    """§9.1 표대로 run_once를 반복하고 종료 코드를 돌려준다. 대기 전 '다음 시작 시각'을 한 줄 출력."""
```
- 실행 방법(사용자): `docker compose run -d --name nadri-bootstrap ingest nadri ingest bootstrap --follow` → `docker logs -f nadri-bootstrap`. `docker compose run` 컨테이너는 재시작 정책이 없어 Docker·WSL이 다시 시작되면 멈춘다 → 같은 명령을 다시 실행하면 이어진다(이어하기가 DB 상태 기반이라 안전). 같은 이름 컨테이너가 남아 있으면 `docker rm nadri-bootstrap` 후 실행.
- 21에서 ingest가 상주 스케줄러가 되면 `--follow` 대신 스케줄러 작업으로 옮길지 21에서 정한다.

### 9.6 실행 결과 `BootstrapResult` ([01] 필드 + 추가)
```python
@dataclass(frozen=True)
class BootstrapOptions:
    """bootstrap 실행 옵션(CLI 인자)."""
    areas: tuple[str, ...] = ("서울", "제주")
    types: tuple[int, ...] = (12, 14, 15, 25, 28, 32, 38, 39)
    max_items: int | None = None
    relist: bool = False
    follow: bool = False

@dataclass
class BootstrapResult:
    """한 번의 실행 요약(ingest_runs.stats에 그대로 저장, 표준 출력 마지막 JSON)."""
    # [01]에서 이어받는 필드
    run_id: int; calls: int; listed: int
    upserted: dict[str, int]; pages_written: int
    indexed: int; skipped: int; failed: int
    index_elapsed_s: float; elapsed_s: float
    errors: list[str]                       # 최대 50줄, 넘으면 끝에 "외 N건"
    # 03 추가
    stop_reason: str
    calls_by_op: dict[str, int]             # 이번 실행 오퍼레이션별 호출 수
    list_pages: int; stubs_inserted: int
    detailed: int; soft_deleted: int; detail_failed: int
    queue_left: dict[str, int]              # {"list_pages", "detail", "index", "excluded"}
    estimate: dict                          # {"days": int, "date": "YYYY-MM-DD", "budget": 800, "used_today": int}
    unknown_intro_fields: dict[str, list[str]]   # 유형 → 규칙에 없는 필드 이름(정렬)
    list_check: dict[str, dict]
```
- `calls`·`calls_by_op`는 이번 실행에서 `reserve`에 성공한 수(= 보낸 요청 수). 오늘 합계는 `ingest_state`.
- 진행 줄(표준 출력): 목록 `[목록 서울:12 p3/12] +87`, 상세 `[상세 152] 126508 경복궁 updated`, 배치 인덱싱 `[인덱싱] indexed 20 skipped 0 failed 0 (318.2s)`. 로그에 서비스 키·URL 쿼리 없음.

### 9.7 CLI (`nadri/cli.py`)
| 명령 | 동작 |
|---|---|
| `nadri ingest bootstrap [--area 서울\|제주 ...] [--type 12 ...] [--max-items N] [--relist] [--follow]` | §9.1. `--area`·`--type`은 여러 번 줄 수 있고 없으면 전부. `--max-items`는 1 이상, `--follow`와 함께 쓰면 인자 오류(2). 잘못된 지역·유형 → 2 |
| `nadri ingest status` | TourAPI 호출 없음. 16칸 표(`total_count`·목록 진행 `next_page/전체 페이지`·DB 행 수·상세 완료 수·인덱싱 완료 수), 상세 큐·인덱싱 대기·제외(실패 ≥3) 수, 오늘 카운터(`ingest`·`live`·`ops`·`quota_hit`), 예상 완료일, 마지막 실행 3개(`ingest_runs`) |
| `nadri ingest count` / `reindex` | [01] 그대로. 단 TourAPI 호출은 `Budget.reserve` 경유(`count` 16건도 예산 안), `reindex`는 수집 쓰기 잠금을 잡는다 |
- 종료 코드: [01]의 0·1·2·3 + **4 = 다른 수집 작업 실행 중(잠금 실패)**.
- 01의 `--limit`(목록 1페이지 limit건)·"유형 12만" 제한은 없어진다(§10).

---

## 10. 01과 달라지는 점 (01 코드·테스트를 이 작업에서 고침)
| # | [01] | 03 | 이유 |
|---|---|---|---|
| 1 | `on_call`은 요청 **직후** 호출 (§6.2, U-TA-12) | **직전** 호출, 예외면 요청 안 보냄 | 예산 강제(예약 후 호출). 셈은 같음 — 확인 질문 Q1 |
| 2 | `record_call`·`calls_today`·`estimate_calls`·`budget_allows`·`validate_args`(bootstrap.py, U-BS-1~3) | 지움 → `budget.Budget`·`BootstrapOptions` 검증으로 대체 | 01 최소 점검을 강제 예산으로 교체([PL] §1.1-2) |
| 3 | `ingest_state` 값 `{"ingest","live"}` | `+ "ops", "quota_hit"` (상위 집합) | 포털 대조·22 처리 |
| 4 | `bootstrap --area --type --limit`(유형 12, ≤50) | `--area/--type` 필터(여러 개)·`--max-items`·`--relist`·`--follow` | 전체 적재·이어하기 |
| 5 | extra = `{overview, homepage, intro, info}` | 같은 형식 + `course`(25)·`rooms`(32). 한글 라벨은 렌더 때 붙임 | 확인 질문 Q11 |
| 6 | fee: infoname에 "입장료"/"이용요금" 포함 | 공백을 지운 infoname으로 비교 + intro 요금 필드 우선 | "입 장 료" 같은 표기 대응(**미확인**: 실제 표기) |
| 7 | 단일 템플릿 `entity.md.j2` | 공통 뼈대 + 유형별 8개 | [PL] 8종 템플릿 |
| 8 | 한도(22·23) → 남은 항목 중단, `failed` | 22 → 그날 중단(`quota_hit`), 23 → 이번 실행만 | 확인 질문 Q2 |

---

## 11. 상위 문서와의 차이 (아키텍처 범위 안의 구현 판단)
1. **23(초당 한도) 처리**: [PL] §3은 "22·23이면 그날 중단". 23은 초당 제한이라 하루를 통째로 쉬면 손해가 커서 "이번 실행만 중단"으로 둔다(확인 질문 Q2).
2. **수집 쓰기 잠금 키 1**: [A] ADR-09·§3.3은 01:00 현행화에 advisory lock 키 1을 쓴다. 초기 적재도 같은 테이블·LightRAG에 쓰므로 **같은 키**로 서로 겹치지 않게 한다(확인 질문 Q10). 21이 생기면 01:00 작업이 적재 실행 중일 때 "건너뜀"이 된다.
3. **껍데기 행**: [A] §3.3의 "상세 미수집" 큐(`detail_synced_at IS NULL`) 개념을 초기 적재에도 쓴다 — 별도 큐 테이블 없음(확인 질문 Q6).
4. **상세가 빈 항목 → 소프트 삭제**: [A] §3.3 4)의 삭제(위키·LightRAG까지)는 21 몫. 03은 껍데기만 있는 항목이라 `deleted_at`만 채운다(위키·문서가 없음).
5. **`--follow`·`ingest status`**: [A] §2.1 CLI 목록에 없는 옵션·명령. 여러 날 누적([PL] §1.2)과 HITL "예상 완료일 보고"를 위한 최소 추가(확인 질문 Q4·Q8).

---

## 12. 엣지케이스
| 상황 | 동작 |
|---|---|
| 실행 시작 때 오늘 예산 0 | 잠금·정리·인덱싱 대기 처리 후 목록·상세 0건, `stop_reason=budget`, 종료 코드 3 (`--follow`면 다음 날 대기) |
| 다음 항목에 3건이 안 남음(예: 798 사용) | 그 항목을 시작하지 않고 `budget`. 남은 2건은 다음 날로 넘어감(실시간 툴 200과는 별도 몫) |
| 상세 도중 다른 프로세스가 예산을 써서 `BudgetExhausted` | 그 항목은 미완료로 큐에 남음, 실패 횟수 증가 없음. 이미 보낸 1~2건은 소비된 채 남음(최대 2건 손실) |
| 22 | `quota_hit` 표시 → 그날 ingest·live 모두 예약 거부, 실행 `failed`·`quota`. 원인(포털 셈 차이·초기화 시각) 보고 |
| 23 | 이번 실행 `failed`·`rate`. `--follow`는 60초 뒤 재시도, 연속 3회면 종료 |
| 실행 중 자정 통과 | 다음 `reserve`부터 새 날짜 키 — 예산이 다시 생겨 계속 진행 |
| 목록 페이지 저장 후·커서 저장 전 끊김 | 같은 트랜잭션이라 둘 다 반영되거나 둘 다 안 됨. 안 됐으면 그 페이지를 다시 받음(호출 1건 손해) |
| 상세 upsert 후·파일/인덱싱 전 끊김 | 인덱싱 대기 큐(§9.4)가 다음 실행 처음에 이어받음 |
| `ingest_runs`에 `running`이 남음(강제 종료) | 다음 실행이 잠금을 얻은 뒤 `failed`로 정리 |
| 두 번 동시 실행(수동 + `--follow`) | 두 번째는 잠금 실패 → 종료 코드 4, 아무것도 안 함 |
| 같은 항목 상세가 계속 실패(타임아웃·`parse` 등) | 실행마다 1회 시도, 누적 3회면 큐에서 제외(`queue_left.excluded`로 보고). `--relist`와 무관 |
| `detailCommon2` item 0개 | 소프트 삭제, 호출 1건만 사용(**미확인**: 실제로 빈 응답인지 오류코드인지 — 오류코드면 위 "계속 실패" 규칙) |
| 01 적재 50건 | 목록 단계에서 `DO NOTHING`으로 그대로, 상세 큐에 안 들어감(이미 `detail_synced_at` 있음). 템플릿 변경분은 `reindex` 1회(§8.3) |
| 15 행사 기간 형식 이상(`20261301` 등) | `None`, 페이지에 행사 기간 줄 없음 |
| 32 객실 요금 `"0"` | 표시 안 함 |
| 25 코스 `subnum`이 숫자 아님 | 맨 뒤로, 원래 순서 유지 |
| 규칙에 없는 intro 필드 | 필드명을 라벨로 "추가 정보"에 표시 + `stats.unknown_intro_fields` |
| LightRAG 다운 | 상세 저장은 계속, 인덱싱 실패 → 해시 NULL → 다음 실행에서 재시도, 실행 `failed` |
| `--max-items`와 `--follow` 함께 | 인자 오류(2) |
| 서비스 키 없음 | [01] `require` → 종료 코드 2 |

---

## 13. 완료 기준 (DoD)
1. **예산 초과 없음**: 어떤 실행·동시 실행에서도 그날 `ingest_state.tourapi_calls:<날짜>.ingest ≤ TOURAPI_DAILY_INGEST_BUDGET`(통합 I-1 동시 예약 테스트 + 첫날 실측). 포털 트래픽 화면 값도 1,000 이하.
2. **이어하기**: 실행 도중 강제 종료(`docker kill`) 후 다시 실행하면 목록 커서·상세 큐·인덱싱 대기를 이어받는다. 같은 항목 상세를 두 번 받지 않고(raw 순번 파일 `.2.json` 없음 — 강제 종료로 끊긴 그 1건 제외), `ingest_runs`의 끊긴 행은 `failed`로 정리된다(HITL H-4).
3. 22·23·예산 소진·큐 소진·`--max-items` 각각의 `stop_reason`·`status`·종료 코드가 §9.1 표대로(단위테스트).
4. **8종 템플릿**: 유형별 스냅샷 테스트 8개 통과, 실제 적재 페이지를 유형별 1개씩 사용자가 읽어 보고 "자연스러움"(빈 줄·`None`·0/1 값 없음, 라벨 한국어) 확인.
5. **해시 같은 페이지는 재인덱싱 안 함**: 재실행 시 인덱싱 대기 0이면 LightRAG 호출 0([01] `index_pages`의 `skipped`).
6. 실행마다 `ingest_runs` 1행: `stats`에 §9.6 필드(호출 수·오퍼레이션별 호출 수·건수·오류·남은 양·예상 완료일).
7. 첫날 실행 결과(호출 수·건수·예상 완료일)를 사용자에게 보고하고, 예상 남은 일수가 길면 운영계정 트래픽 증설 신청 여부를 묻는다(확인 질문 Q9 기준). 답을 `PROGRESS.md` 결정 로그에 남긴다.
8. §14 가정·확인 항목 판정을 기록(실패 대안 중 사용자 확인 항목은 **멈추고 묻는다**).
9. 단위테스트 전부 통과(`-m "not integration"`), 통합 테스트 통과. 01 테스트 중 §10에서 바뀐 것은 새 동작에 맞게 고쳐 통과.
10. 주석 규칙(한국어 docstring + 단계 주석), `CLAUDE.md` "명령어" 절 갱신, 커밋은 `feat/03-ingest-bootstrap` 브랜치·사용자 커밋 형식(`[Feat] …` + 작업 목록 + `Author:` 줄, AI 공동작성 표기 없음 [R NFR-73]). `dev` 병합은 G5 승인 후. **초기 적재 완료 자체는 DoD가 아니다**(여러 날 걸림 — G5는 첫날 결과로 판단하고, 완료는 `ingest status`로 이후 확인).

---

## 14. 가정·확인 항목 판정 (구현 중 결과 기록)
판정 방법은 test.md 통합·HITL과 1:1. 결과는 이 표와 `PROGRESS.md` 결정 로그에 남긴다.

| ID | 확인 방법 | 통과 기준 | 실패 시 대안 | 사용자 확인 | 결과 |
|---|---|---|---|---|---|
| **A12** 한도 단위 | 01 §10 결과를 먼저 본다. 미확인이면 첫날 `ingest_state.ops`와 포털 마이페이지(오퍼레이션별 사용량 표시 여부)를 대조 | 한도가 서비스 전체인지 오퍼레이션별인지 확정 | 확정 못 하면 서비스 전체로 유지(보수). 오퍼레이션별로 확정되면 예산 단위 변경 여부를 묻는다(Q3) | Q3 | |
| **A12** 실제 일수 | 첫날 `stats.estimate` + `ingest status` | 예상 완료일 산출 | 길면 운영계정 증설·호출 줄이기 → **사용자 확인**(Q9) | Q9 | |
| **A12** 카운터 초기화 시각 | 첫날 예산 소진 후 다음 날 00:10 이후 실행에서 22 없이 진행되는지 | 22 없음 | 22가 나면 `RESUME_AT`을 늦춤(코드 상수) | 아니오 | |
| **A12** 22·23 실제 모양 | 발생하면 raw·오류 메시지 기록(일부러 일으키지 않음) | `TourApiError.code`가 `22`/`23`으로 해석됨 | 다른 코드·XML 형식이면 `QUOTA_CODES`·`RATE_CODES`·파서 수정 | 아니오 | |
| **A8** 넓은 표본 | 첫날 이후 8종 각 1~2개 장소로 `nadri lightrag sample --query` 4회(음식점·숙박·축제·여행코스 이름) → 엔티티·관계 각 10~20개 | 사용자 "쓸 만함"([01] §9 A8 참고 기준) | [01] §9 A8 대안 ①~④(④ 상위 모델은 **사용자 확인**) | 실패 시 | |
| 필드 이름 (8종 intro·info, 목록) | 통합 I-5: 유형별 1건씩 실제 상세 3종 → `split_intro`의 "규칙에 없는 필드"·비어 버린 핵심 컬럼 확인 | 8종 모두 핵심 컬럼(usetime·restdate·tel 등 해당 유형에 있는 것)이 채워지고 규칙에 없는 필드 0개(또는 표에 반영) | §6.3 표·`INTRO_SPECS` 수정(코드) | 아니오 | |
| detailInfo2 모양 (25·32) | I-5에서 25·32 raw 확인 | course·rooms 매핑 성공 | 매핑 수정(코드) | 아니오 | |
| `usetime` 자유 텍스트 여부 ([A] §2.1 "추정") | HITL H-7: 유형별 `usetime` 표본 40개 | 사람이 읽는 자유 텍스트임을 확인 → [A] 그대로(원문 전달, 해석은 LLM) | 정형(예: `HH:MM~HH:MM`)이 대부분이어도 아키텍처 변경 없음 — 기록만 | 아니오 | |
| 빈 상세 = 삭제? | 소프트 삭제 건이 생기면 그 contentid를 포털·목록 재조회로 확인 | 실제로 사라진 콘텐츠 | 일시 오류였다면 소프트 삭제 대신 실패 횟수 규칙으로(코드) | 아니오 | |
| `numOfRows` 100 | 첫 목록 호출 | 100건 반환 | 상한이 더 작으면 `LIST_PAGE_SIZE` 수정 | 아니오 | |

---

## 15. 확인 질문
| # | 질문 | 추천안 | 대안 |
|---|---|---|---|
| Q1 | 예산을 "호출 전 예약"으로 강제하려면 01의 `on_call`을 요청 **직전**에 부르고, 예산이 없으면 요청을 막아야 한다(01 spec 변경) | **직전 예약**(경합해도 800을 절대 넘지 않음) | 01처럼 직후 기록 + 항목 시작 전 남은 양만 점검(동시 실행 시 몇 건 넘을 수 있음) |
| Q2 | 한도 오류 처리. [PL]은 "22·23이면 그날 중단" | **22 → 그날 중단(카운터에 표시해 실시간 툴도 멈춤), 23 → 이번 실행만 중단**(`--follow`는 1분 뒤 재시도, 연속 3회면 종료) | [PL] 그대로 둘 다 그날 중단(단순하지만 23 한 번에 하루를 잃음) |
| Q3 | 예산 단위. 01의 A12 판정에서 한도가 **오퍼레이션별**로 확인되면 하루 처리량이 약 3배까지 늘 수 있다 | **01 결과를 따른다**: 서비스 전체면 합계 800, 오퍼레이션별이면 오퍼레이션마다 800(실시간 툴 몫 200도 오퍼레이션별), 미확인이면 합계 800 | 결과와 무관하게 합계 800 유지(가장 안전, 가장 느림) |
| Q4 | 여러 날 누적 실행 방식 | **`--follow` 옵션**: 켜 두면 예산 소진 시 다음 날 00:10까지 기다렸다 이어감(`docker compose run -d`) | B: 사용자가 매일 한 번 수동 실행 / C: 21 스케줄러가 생길 때까지 기다림(적재 시작이 늦어짐) |
| Q5 | 상세 수집 순서 | **16칸(지역×유형) 돌아가며 1건씩** — 첫날부터 8종 표본이 생겨 템플릿·A8을 바로 확인 | 칸 하나씩 끝까지(서울 관광지 → 서울 문화시설 …) |
| Q6 | 목록에서 만든 "껍데기 행"(상세 받기 전: 제목·주소·좌표·전화만)이 적재 기간 동안 `data_query`에 보인다 | **보이게 둔다**(실제 공공데이터 값, 주변 검색 범위가 빨리 넓어짐) | `data_query`에 `detail_synced_at IS NOT NULL` 조건 추가(01 툴 한 줄 수정, 상세 받은 것만 보임) |
| Q7 | 같은 항목 상세가 계속 실패할 때 | **실행마다 1회, 누적 3회 실패면 큐에서 제외**하고 `ingest status`에 표시. `detailCommon2`가 빈 응답이면 삭제된 것으로 보고 소프트 삭제 | 무한 재시도(적재가 끝나지 않을 수 있음) |
| Q8 | 진행 현황 명령 `nadri ingest status` 추가([PL]에 없음) | **추가**(TourAPI 호출 없이 칸별 진행·남은 양·예상 완료일) | 실행 요약 JSON과 SQL 조회로 대신 |
| Q9 | 운영계정 트래픽 증설 신청을 물어볼 기준 | **첫날 결과를 항상 보고하고, 예상 남은 일수가 14일을 넘으면 신청 여부를 묻는다**. 신청 조건("활용사례 등록")·처리 기간은 **미확인**이라 사용자가 포털에서 확인 | 30일 기준 / 기간과 무관하게 개발계정만 사용 / 호출 줄이기(예: `detailInfo2`를 요금·코스·객실이 필요한 유형만 — 하루 처리량 약 1.5배, 대신 일부 유형의 추가 정보 누락) |
| Q10 | 초기 적재와 21의 01:00 현행화가 같은 advisory lock 키 1을 쓴다 | **같은 키**(둘 다 `tour_items`·위키·LightRAG에 씀, 동시 실행 방지). 적재 중이면 01:00 작업은 건너뜀 | 다른 키(동시에 돌면 같은 항목을 두 번 받을 수 있음) |
| Q11 | `detailIntro2` 나머지 필드의 한글 라벨을 어디서 붙일까 | **DB(`extra.intro`)에는 01처럼 필드명 그대로 저장, 렌더 때 `INTRO_SPECS` 라벨·순서로 표시**(01 적재분과 형식이 같고, 라벨을 고쳐도 다시 받을 필요 없음) | 저장할 때 `[[한글 라벨, 값], …]`로 바꿔 저장(01 형식과 달라져 렌더가 두 형식을 읽어야 함) |
