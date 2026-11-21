# 10-tool-tour-live — `tour_live` 툴 (spec)

> 하네스 Phase 4 산출물 (spec-writer, 작성 2026-11-21). 상태: **초안 — 사용자 검토 대기**. 브랜치 `feat/10-tool-tour-live`, 의존 작업 01·02 (+ 03의 `budget.py`·`on_call` 직전 호출, 04의 테스트 DB 픽스처를 이어받음).
> 근거: [PL]=program_list.md(G4 승인본) §2 표·§3 "10-tool-tour-live"·§5 Q6 · [A]=architecture.md(G3 재승인본) §2.1 tour-tools 표·§3.1 실패 처리·§4 외부 연동·§5.1 DB 롤·§9 비밀값 표·ADR-05·08·13·14·24 · [R]=requirements.md FR-11·52·55, NFR-07·08·33 · [01]·[02]·[03]·[04]=같은 폴더의 확정 spec · [PG]=PROGRESS.md 결정 로그(G4 Q6, 01-Q6, 03-Q1·Q2·Q3).
> 이 문서는 [01]~[04]의 이름·시그니처를 그대로 쓴다. 바꾸는 부분은 §10 "앞 작업과 달라지는 점"에 모두 적었다.
> **미확인** = 문서·공식 자료로 확인하지 못해 구현 중 실제 호출로 확인해야 하는 사실(§12 표).

---

## 1. 작업 목표

tour-tools MCP 서버에 네 번째 툴 `tour_live`를 붙여, 에이전트가 **TourAPI를 지금 바로 불러** 두 가지를 볼 수 있게 한다 [A §2.1], [R FR-52].

| op | TourAPI 오퍼레이션 | 용도 |
|---|---|---|
| `festival` | `searchFestival2` | 서울·제주에서 지정한 날짜 범위에 열리는(진행 중·예정) 축제·행사 |
| `nearby` | `locationBasedList2` | 좌표 주변 관광 정보(위치 동의로 받은 현재 좌표 또는 툴 결과의 장소 좌표 기준, FR-55) |

- 결과는 01과 같은 구조화 JSON: 항목마다 `contentid`·`source`·`as_of`, `source = "실시간 조회"` [A §2.1], ADR-05.
- **TourAPI 일일 한도를 ingest와 같은 카운터로 나눠 쓴다**(G4 Q6): ingest 800 + 실시간 200. 호출 **전에** 카운터에서 1건을 예약하고, 예약이 안 되면 TourAPI를 부르지 않는다(03-Q1). 오류 22를 받으면 그날 실시간·적재 모두 멈춘다(03-Q2).
- tour-tools DB 롤 `nadri_tools`에 카운터 쓰기 권한을 **최소로** 준다(01-Q6): `ingest_state` 테이블 권한은 주지 않고, 실시간 카운터만 +1 하는 **SECURITY DEFINER 함수 2개의 실행 권한만** 준다(§5, 확인 질문 Q1).
- TourAPI·네트워크 오류는 툴 오류 결과로 LLM에 돌려 답변을 계속하게 한다 [A §3.1 실패 처리], [02 §4.5].
- api 쪽: 툴 허용 목록·순서에 `tour_live` 추가, 화면 라벨 "실시간 정보 확인 중" [PL §3].
- 추적: FR-11(툴 선택)·FR-52·FR-55(좌표 사용), NFR-07(읽기 전용 툴·최소 권한)·NFR-33(좌표 저장·로그 안 함), ADR-05·08·14.

### 1.1 넣지 않는 것
| 하지 않는 것 | 담당 |
|---|---|
| 위치 동의 UI·좌표를 질문에 붙이는 일(`현재 위치: 위도·경도` 줄) | 09(백엔드)·16(화면) |
| 대화 저장 시 툴 인자·결과에서 좌표를 빼는 일(NFR-33) | 09 — §11-4에 요청 사항으로 적음 |
| FAQ 캐시에서 `tour_live` 결과가 있는 답변 제외 | 12 (ADR-13에 이미 정해짐) |
| 실시간 결과 raw 저장·`tour_items` 반영 | 없음 — 실시간 결과는 그 답변에만 쓴다(raw는 ingest만, FR-40) |
| 실시간 결과 캐시(같은 질문 재사용) | 없음(하루 200건, 사용자 1명 규모 — 단순함 우선) |
| `nadri tools smoke`에서 `tour_live` 호출 | 없음 — 예산을 쓰므로 통합 테스트·HITL에서만 부른다 |
| 확장 원천(서울 실시간 도시데이터 등, FR-49) | v1.1 이후 |

---

## 2. 생성·수정 파일

경로의 `nadri/`는 `backend/src/nadri/`([01] §2).

| 파일 | 신규/수정 | 역할 |
|---|---|---|
| `nadri/tools/tour_live.py` | 신규 | 입력 검증(`TourLiveParams`), 실시간 카운터 예약(`LiveBudget`), TourAPI 응답 → 툴 결과 변환, 오류 → 짧은 한국어 툴 오류 (§6·§7) |
| `nadri/tools/server.py` | 수정 | `ToolDeps`에 `tourapi`·`live_budget` 추가, `tour_live` 등록(4번째), `build_app`이 TourAPI 키 필수 확인·클라이언트 생성 (§6.4) |
| `nadri/core/tourapi.py` | 수정 | `search_festival()`·`location_based_list()` 추가 (§6.1) |
| `nadri/core/config.py` | 수정 | `TOURAPI_DAILY_LIVE_BUDGET`(기본 200) 추가 (§4) |
| `backend/alembic/versions/0003_tourapi_live_counter.py` | 신규 | 카운터 함수 2개 생성 + `nadri_tools`에 EXECUTE만 부여 (§5). 번호는 구현 시점 head 다음 번호, `down_revision` = 그 시점 head |
| `nadri/agent/tools.py` | 수정 | `TOUR_TOOL_ORDER`·`TOOL_LABELS`·`MATERIAL_SOURCES`에 `tour_live` 추가 (§8) |
| `nadri/prompts/answer.md` | 수정 | 툴 선택 규칙 4번에 `tour_live` 사용 기준 2줄 (§8.2, 확인 질문 Q3) |
| `compose.yaml` | 수정 | `tour-tools`에 `TOURAPI_SERVICE_KEY` 주입 (§4) |
| `backend/tests/**` | 신규·수정 | test.md. 01·02 테스트 일부 수정(§10) |
| `docs/harness/tasks/10-tool-tour-live/spec.md` §12 | 수정 | 구현 중 미확인 사실 확인 결과 기록 |

> [PL] 파일 목록에 없는 수정: `core/config.py`(설정 1개), `compose.yaml`(키 주입 — [01] §5.2가 "tour-tools 주입은 10"으로 넘김), 테이블 생성 스크립트 `0003`(권한 함수 — 01-Q6), `prompts/answer.md`(툴 선택 규칙 — Q3). 모두 이 작업을 동작시키려면 필요하다.

---

## 3. 설정 (`core/config.py`)

| 필드 (환경변수) | 타입 | 기본값 | 쓰는 곳 |
|---|---|---|---|
| `TOURAPI_DAILY_LIVE_BUDGET` | int (≥ 0) | `200` | tour-tools — G4 Q6 실시간 몫. `0`이면 실시간 조회를 하지 않음(모든 호출이 예산 소진 오류) |

- 기존 [01] §4.2 `TOURAPI_SERVICE_KEY`·`TOURAPI_BASE_URL`·`TOURAPI_TIMEOUT_S`(15초)를 tour-tools에서도 쓴다. 새 타임아웃 설정은 만들지 않는다(채팅 전체 180초 안에 충분).
- 합계 보장: ingest ≤ 800([03] `Budget(kind="ingest")`) + live ≤ 200(이 작업) → 하루 1,000 이하(개발계정 한도, F7).

## 4. Compose

| 서비스 | 바뀌는 것 |
|---|---|
| `tour-tools` | `environment`에 `TOURAPI_SERVICE_KEY: ${TOURAPI_SERVICE_KEY}` 추가. 나머지([01] §5.2) 그대로 |

- [A] §9 비밀값 표가 이미 "`TOURAPI_SERVICE_KEY` → ingest, tour-tools"다. `.env.example`은 바뀌지 않는다(키 이름이 이미 있음).
- `TOURAPI_DAILY_LIVE_BUDGET`은 compose에 넣지 않는다(기본값 사용, 단순함 우선).

---

## 5. 카운터 쓰기 권한 — SECURITY DEFINER 함수 (01-Q6 결정 사항)

### 5.1 왜 함수인가
- `nadri_tools`는 지금 `tour_items`·`wiki_pages` SELECT만 가진다([01] §3.3). 카운터는 `ingest_state` 행(`tourapi_calls:YYYY-MM-DD`)에 있고, 같은 테이블에 적재 커서(`bootstrap:list:*`)·실패 기록(`bootstrap:failures`)도 있다([03] §4).
- `GRANT UPDATE ON ingest_state`를 주면 tour-tools가 커서·실패 기록·ingest 카운터까지 바꿀 수 있다. 행 단위 보안(RLS)은 설정이 늘어난다.
- 그래서 **"오늘 live 카운터 +1"과 "quota_hit 표시" 두 동작만 하는 함수**를 테이블 소유자(`nadri_app`) 권한으로 실행되게(SECURITY DEFINER) 만들고, `nadri_tools`에는 그 함수 실행 권한만 준다. `ingest_state` 테이블 권한은 여전히 없다.

### 5.2 함수 정의 (`0003` `upgrade()`, `op.execute`로 실행. 롤 `nadri_app` = 함수 소유자)
```sql
-- 실시간 툴 1건 예약: 조건을 만족하면 live 합계와 ops[p_op]를 +1 하고 새 live 합계를 돌려준다. 못 하면 NULL.
CREATE FUNCTION tourapi_live_reserve(p_day date, p_op text, p_limit int)
RETURNS int
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp
AS $$
DECLARE
  k text := 'tourapi_calls:' || to_char(p_day, 'YYYY-MM-DD');
  n int;
BEGIN
  -- 1) 그날 행이 없으면 03과 같은 초기값으로 만든다
  INSERT INTO ingest_state(key, value)
  VALUES (k, '{"ingest":0,"live":0,"ops":{},"quota_hit":false}'::jsonb)
  ON CONFLICT (key) DO NOTHING;
  -- 2) live < p_limit 이고 quota_hit 아님일 때만 +1 (행 잠금으로 ingest 예약과 직렬화)
  UPDATE ingest_state
  SET value = jsonb_set(
        jsonb_set(value, '{live}', to_jsonb(COALESCE((value->>'live')::int, 0) + 1)),
        '{ops}',
        COALESCE(value->'ops', '{}'::jsonb)
          || jsonb_build_object(p_op, COALESCE((value->'ops'->>p_op)::int, 0) + 1))
  WHERE key = k
    AND COALESCE((value->>'live')::int, 0) < p_limit
    AND NOT COALESCE((value->>'quota_hit')::boolean, false)
  RETURNING (value->>'live')::int INTO n;
  RETURN n;
END;
$$;

-- 오류 22를 받았을 때: 그날 quota_hit = true (ingest·live 모두 예약 거부, 03-Q2)
CREATE FUNCTION tourapi_live_mark_quota_hit(p_day date)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp
AS $$
DECLARE
  k text := 'tourapi_calls:' || to_char(p_day, 'YYYY-MM-DD');
BEGIN
  INSERT INTO ingest_state(key, value)
  VALUES (k, '{"ingest":0,"live":0,"ops":{},"quota_hit":false}'::jsonb)
  ON CONFLICT (key) DO NOTHING;
  UPDATE ingest_state SET value = jsonb_set(value, '{quota_hit}', 'true'::jsonb) WHERE key = k;
END;
$$;

REVOKE ALL ON FUNCTION tourapi_live_reserve(date, text, int) FROM PUBLIC;
REVOKE ALL ON FUNCTION tourapi_live_mark_quota_hit(date) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION tourapi_live_reserve(date, text, int) TO nadri_tools;
GRANT EXECUTE ON FUNCTION tourapi_live_mark_quota_hit(date) TO nadri_tools;
```
- `downgrade()`: `DROP FUNCTION` 두 개(권한도 함께 사라짐).
- UPDATE 식은 [03] §5.2 예약 문에서 `kind`를 `'live'`로 고정한 것이다. 키 형식·초기값·`ops` 형식이 [03]과 같아야 한다 — DB 테스트로 [03] `DayUsage.from_value`가 이 함수가 쓴 값을 그대로 읽는지 확인한다(test.md D-LB-8).
- `SET search_path = pg_catalog, public, pg_temp`: SECURITY DEFINER 함수가 호출자가 만든 같은 이름의 임시 테이블 등을 잘못 쓰지 않게 하는 PostgreSQL 권장 설정(`pg_temp`를 명시해 맨 뒤로 보낸다 — 적지 않으면 맨 앞에서 찾는다).
- PostgreSQL은 새 함수의 EXECUTE를 기본으로 PUBLIC에 준다 → 위 `REVOKE … FROM PUBLIC`이 필수다.
- 함수는 오늘 날짜가 아닌 `p_day`도 받는다(날짜는 호출 쪽 시계 — [03] §5.1-4와 같은 방식, 테스트에서 날짜를 고정하기 위해). tour-tools는 이미 TourAPI 키를 가지고 있어 날짜·limit을 막아도 보안 이득이 없으므로 추가 검사는 하지 않는다.
- [03] Q3: A12에서 한도가 **오퍼레이션별**로 확정되면 [03]의 예약 문과 함께 이 함수의 조건도 `ops[p_op] < p_limit`으로 바꾼다(그 시점 테이블 생성 스크립트 1개 추가). 미확인·서비스 전체면 위 정의 그대로.

---

## 6. 모듈별 입출력 · 시그니처

주석 규칙([CL]): 모든 함수·클래스에 한국어 docstring(요약 → Args → Returns → Raises/부수효과), 함수 안 단계 주석 `# 1) …`. 아래 docstring은 요약 한 줄만 적었다.

### 6.1 `core/tourapi.py` 확장
```python
async def search_festival(self, area: str, event_start_date: date, *, num_of_rows: int,
                          sigungu_code: str | None = None, page_no: int = 1) -> TourApiResponse:
    """searchFestival2로 area의 행사 목록을 받는다(eventStartDate = YYYYMMDD)."""
async def location_based_list(self, lat: float, lng: float, radius_m: int, *, num_of_rows: int,
                              content_type_id: int | None = None, page_no: int = 1) -> TourApiResponse:
    """locationBasedList2로 좌표 반경 안 관광 정보 목록을 받는다(mapX=경도, mapY=위도, radius=미터)."""
```
- 공통 파라미터·`parse_response`·오류 처리·`on_call`(요청 **직전**, 예외면 요청 안 보냄 — [03] §6.1)은 기존 그대로.
- `search_festival`: `areaCode`(=`AREAS[area]`, 모르는 지역이면 `ValueError`·HTTP 없음 — [01] U-TA-15와 같은 규칙), `eventStartDate`, `sigunguCode`(있을 때만), `numOfRows`, `pageNo`, `arrange=A`(제목순 — 정렬은 코드에서 다시 하므로 무엇이든 상관없음, **미확인**: v2 정렬 코드).
- `location_based_list`: `mapX`(경도), `mapY`(위도), `radius`(미터 정수), `contentTypeId`(있을 때만), `numOfRows`, `pageNo`, `arrange=E`(거리순 — **미확인**, §12 L3).
- `AREAS`의 값이 01 A12 확인으로 법정동 코드 체계로 바뀌었으면 그 결과를 그대로 쓴다(이 작업에서 코드 체계를 새로 정하지 않음).
- 파라미터 이름(`eventStartDate`·`mapX`·`mapY`·`radius`·`sigunguCode`)은 KorService1 문서 관례에 따른 것이다(**미확인** — §12 L1~L3).

### 6.2 `tools/tour_live.py` — 상수·입력
```python
SOURCE_LIVE = "실시간 조회"                  # [A] §2.1 그대로 (확인 질문 Q4)
FESTIVAL_ROWS = 100                         # festival 1회 요청 건수 (TourAPI 1건으로 끝냄)
NEARBY_ROWS = 50                            # nearby 1회 요청 건수
MAX_SPAN_DAYS = 31                          # festival 날짜 범위 상한(양 끝 포함)
SERVICE_BOXES: dict[str, tuple[float, float, float, float]] = {
    "서울": (37.41, 37.72, 126.73, 127.27),  # (min_lat, max_lat, min_lng, max_lng) — 행정 경계를 덮는 대략값
    "제주": (33.10, 34.00, 126.10, 127.00),  # 마라도~추자도 포함
}
MSG_BUDGET = "실시간 조회 불가: 오늘 실시간 조회 가능 횟수를 모두 썼습니다."
MSG_RATE = "실시간 조회 불가: 관광공사 서버가 잠시 요청을 받지 않습니다."
MSG_FAIL = "실시간 조회 불가: 관광공사 서버 응답 오류입니다."

class TourLiveParams(BaseModel):
    """tour_live 입력. LLM이 채우는 값이라 엄격히 검증한다."""
    op: Literal["festival", "nearby"]
    area: Literal["서울", "제주"] | None = None                     # festival 필수
    sigungu_code: str | None = Field(default=None, pattern=r"^\d{1,5}$")   # festival 선택
    start_date: date | None = None                                 # festival, 없으면 오늘(KST)
    end_date: date | None = None                                   # festival, 없으면 start_date
    near: NearPoint | None = None                                  # nearby 필수 ([01] data_query의 NearPoint 재사용, radius_km ≤ 20)
    content_type: Literal[12, 14, 15, 25, 28, 32, 38, 39] | None = None   # nearby 선택
    limit: int = Field(default=10, ge=1)                           # 20 초과는 20으로 낮춤

def resolve_dates(p: TourLiveParams, today: date) -> tuple[date, date]:
    """festival 날짜 범위를 정한다(기본 오늘~오늘). end < start 또는 31일 초과면 ValueError."""
def in_service_area(lat: float, lng: float) -> bool:
    """좌표가 서울·제주 대략 상자 안인지 본다(확인 질문 Q2)."""
```
검증 규칙(`model_validator(mode="after")`, 어긋나면 `ValueError` — FastMCP가 `isError` 결과로 바꿈, [01] §6.8 공통 규칙):
1. `op="festival"`: `area` 필수. `near`·`content_type`이 있으면 오류.
2. `op="nearby"`: `near` 필수. `area`·`sigungu_code`·`start_date`·`end_date`가 있으면 오류. `in_service_area(near.lat, near.lng)`가 False면 오류 "서울·제주 밖 좌표는 조회하지 않습니다."
3. `limit` > 20 → 20 ([01] data_query와 같음).
4. **검증은 예약보다 먼저** 한다 — 잘못된 입력은 카운터를 쓰지 않는다.

### 6.3 `tools/tour_live.py` — 카운터·변환·툴 본체
```python
class LiveBudget:
    """실시간 툴의 TourAPI 일일 예산. DB 함수 tourapi_live_reserve로 예약한다(nadri_tools 롤)."""
    def __init__(self, sf: async_sessionmaker[AsyncSession], *, limit: int,
                 clock: Callable[[], datetime] = lambda: datetime.now(KST)) -> None: ...
    async def reserve(self, op: str) -> None:
        """1건 예약. 함수가 NULL을 돌려주면 BudgetExhausted. TourApiClient의 on_call로 넘긴다."""
    async def mark_quota_hit(self) -> None:
        """오늘 quota_hit를 true로 표시한다(오류 22 수신 시)."""

def build_live_reserve_stmt(day: date, op: str, limit: int) -> TextClause:
    """SELECT tourapi_live_reserve(:day, :op, :limit) — 값은 전부 바인드 파라미터."""
def build_live_quota_hit_stmt(day: date) -> TextClause:
    """SELECT tourapi_live_mark_quota_hit(:day)."""

class LiveUnavailable(Exception):
    """실시간 조회를 하지 못함. 메시지(MSG_*)가 그대로 LLM에 툴 오류로 간다."""

def parse_yyyymmdd(value: str | None) -> date | None:
    """'20261121' → date. 빈 값·형식 오류 → None."""
def festival_items(raw_items: list[dict], start: date, end: date, area: str, as_of: date) -> list[dict]:
    """행사 item을 툴 결과 항목으로 바꾸고, [start, end]와 기간이 겹치는 것만 행사 시작일 순으로 돌려준다(순수 함수)."""
def nearby_items(raw_items: list[dict], near: NearPoint, as_of: date) -> list[dict]:
    """주변 item을 툴 결과 항목으로 바꾸고, 반경 안의 것만 거리순으로 돌려준다(순수 함수)."""
async def tour_live(p: TourLiveParams, deps: ToolDeps) -> dict:
    """op에 따라 TourAPI를 1번 부르고 결과를 구조화 JSON으로 돌려준다. 실패는 LiveUnavailable."""
```
- `BudgetExhausted`·`KST`·`kst_today`는 [03] `nadri.ingest.budget`·[01] `nadri.core.tourapi`의 것을 import한다(같은 패키지, 새로 만들지 않음).
- `LiveBudget.reserve` 처리: 1) `day = kst_today(clock())` 2) 세션 1개·트랜잭션 1개로 `build_live_reserve_stmt` 실행·커밋 3) 결과가 `None`이면 `BudgetExhausted`.
- `LiveBudget.mark_quota_hit`도 `day`를 그때 시계로 계산한다.

**항목 변환 공통** (`festival_items`·`nearby_items`):
1. item마다 [03] `parse_list_item(item)` → `ListItem`. `ValueError`(contentid·contenttypeid·title 없음)면 그 item은 버린다.
2. 문자열 값은 [01] `clean_text` 적용. 주소 = `addr1` + " " + `addr2`(둘 다 없으면 None), 좌표 = `mapy`→lat, `mapx`→lng(빈 값·0 → None) — [01] §6.4 매핑과 같다.
3. **이미지 필드(`firstimage`·`firstimage2`)와 그 밖의 URL 필드는 넣지 않는다** — 답변 이미지 표시 안 함([PG] G1 전 O-결정)·허용 링크 목록([02] §8)에 이미지 주소가 섞이지 않게.
4. 항목 키(순서 고정):
   - festival: `contentid, title, content_type_id, area, sigungu_code, addr, tel, lat, lng, event_start, event_end, source, as_of`
   - nearby: `contentid, title, content_type_id, addr, tel, lat, lng, distance_km, source, as_of`
   - `source = SOURCE_LIVE`, `as_of` = 조회한 KST 날짜(`TourApiResponse.fetched_at`의 날짜, ISO 문자열), 날짜는 ISO 문자열.
5. festival: `eventstartdate`·`eventenddate`(필드명 **미확인**, §12 L2)를 `parse_yyyymmdd`로 읽는다. 둘 중 하나라도 None이면 버린다. 기간이 `[start, end]`와 겹치는 것(`event_start ≤ end AND event_end ≥ start`)만 남기고 `(event_start, event_end, contentid)` 순으로 정렬.
6. nearby: 좌표가 None이면 버린다. `distance_km = round(haversine_km(near.lat, near.lng, lat, lng), 2)`([01] `haversine_km` 재사용 — 응답의 `dist` 필드에 기대지 않음), `distance_km ≤ near.radius_km`만 남기고 `(distance_km, contentid)` 순.

**`tour_live` 처리 순서**:
1. (입력은 래퍼에서 이미 `TourLiveParams`로 검증됨)
2. festival이면 `resolve_dates(p, kst_today(now))` → `deps.tourapi.search_festival(p.area, start, num_of_rows=FESTIVAL_ROWS, sigungu_code=p.sigungu_code)`.
   nearby면 `deps.tourapi.location_based_list(near.lat, near.lng, round(near.radius_km * 1000), num_of_rows=NEARBY_ROWS, content_type_id=p.content_type)`.
   → `TourApiClient`의 `on_call`이 `deps.live_budget.reserve(op)`라서 **예약이 먼저**, 실패하면 요청이 나가지 않는다.
3. 오류 변환 (§7 표): `BudgetExhausted` → `LiveUnavailable(MSG_BUDGET)` / `TourApiError.quota_exceeded`(22) → `mark_quota_hit()` 후 `LiveUnavailable(MSG_BUDGET)` / `rate_limited`(23) → `LiveUnavailable(MSG_RATE)` / 그 밖의 `TourApiError`·DB 오류·예상 못 한 예외 → `LiveUnavailable(MSG_FAIL)`. **재시도 없음**([01] §6.2).
4. 항목 변환 → 상위 `limit`개.
5. 결과:
```json
{"op": "festival", "items": [...], "count": 3, "total_count": 41, "truncated": false,
 "source": "실시간 조회", "as_of": "2026-11-21", "fetched_at": "2026-11-21T14:03:12+09:00",
 "range": {"start": "2026-11-21", "end": "2026-11-21"}}
```
   - `total_count` = 응답 `totalCount`, `truncated` = `total_count > 받은 item 수`(1페이지만 받았음을 LLM이 알 수 있게).
   - `range`는 festival만. nearby 결과에는 **요청 좌표·반경을 다시 넣지 않는다**(NFR-33 — 좌표가 툴 결과 원문에 남지 않게).
6. 로그 한 줄(INFO): `tool=tour_live op=<op> outcome=<ok|empty|budget|quota|rate|error> count=<n> tourapi_code=<코드|-> total_ms=<ms>`. **인자(좌표·날짜·지역)는 남기지 않는다**(NFR-33, [01] §6.8 로그 규칙). `quota`는 WARNING.

### 6.4 `tools/server.py` 수정
```python
@dataclass
class ToolDeps:
    """툴 함수가 쓰는 공유 자원(서버 기동 시 1회 생성)."""
    settings: Settings
    sf: async_sessionmaker[AsyncSession]
    lightrag_http: httpx.AsyncClient
    reranker: CrossEncoderReranker
    tourapi: TourApiClient          # 10 추가: on_call = live_budget.reserve
    live_budget: LiveBudget         # 10 추가
```
- `build_app`: 1) 기존 토큰 검사([01] — 빈 토큰이면 기동 거부) 2) `require(settings.tourapi_service_key, "TOURAPI_SERVICE_KEY")`(없으면 기동 거부, 종료 코드 2 — [01] §4.2 `require`). **키 검사 둘은 DB 엔진·리랭커 등 자원을 만들기 전에** 한다(테스트가 리랭커 없이 돌게) 3) 기존 자원 생성 4) `LiveBudget(sf, limit=settings.TOURAPI_DAILY_LIVE_BUDGET)` 5) `TourApiClient(key, settings.TOURAPI_BASE_URL, timeout=settings.TOURAPI_TIMEOUT_S, on_call=live_budget.reserve)`.
- `build_mcp`: 툴 4개를 **`rag_query, data_query, tour_live, get_datetime`** 순서로 등록([A] §2.1 표 순서). 래퍼 인자는 `TourLiveParams`의 필드를 최상위 인자로 받고(01의 `data_query` 래퍼와 같은 방식) 안에서 `TourLiveParams(...)`로 검증한다.
- 툴 설명(LLM이 보는 고정 문자열 — NFR-40 고정 프리픽스, 바꾸면 프롬프트 캐시가 한 번 깨짐):
  > 한국관광공사 TourAPI를 지금 바로 조회한다(하루 호출 수 제한 있음). op="festival": area(서울/제주)에서 start_date~end_date(기본 오늘, 최대 31일)에 열리는 축제·행사. op="nearby": near{lat,lng,radius_km(≤20)} 주변 관광 정보(content_type 선택, 서울·제주 안 좌표만). 저장된 정보로 충분하면 data_query를 먼저 쓴다. 결과 항목마다 contentid·source("실시간 조회")·as_of가 있다.
- 서버 종료 시 `tourapi.aclose()`(lightrag_http와 같은 위치에서 정리).

---

## 7. 엣지케이스 · 오류 처리

| 상황 | TourAPI 요청 | 카운터 | 툴 결과(LLM이 받는 것) | 로그 outcome |
|---|---|---|---|---|
| 정상, 항목 있음 | 1건 | live +1 | `items` n개 | `ok` |
| 정상, 빈 결과(`items: ""`, totalCount 0) | 1건 | live +1 | `{"items": [], "count": 0, …}` — 오류 아님 | `empty` |
| 받은 item이 모두 기간 밖·반경 밖·필수값 없음 | 1건 | live +1 | 빈 `items`, `total_count`는 응답 값 | `empty` |
| 입력 오류(festival에 area 없음, 31일 초과, end<start, 서울·제주 밖 좌표, 잘못된 content_type 등) | 0건 | 변화 없음 | 입력 오류 메시지(`ValueError`) | (FastMCP 검증 단계 — 로그 없음) |
| **오늘 live 200건 소진** | 0건 | 변화 없음 | `MSG_BUDGET` | `budget` |
| **`quota_hit` 이미 true**(ingest나 다른 호출이 22를 받음) | 0건 | 변화 없음 | `MSG_BUDGET` | `budget` |
| **TourAPI 오류 22**(우리 셈과 포털 셈이 어긋남) | 1건 | live +1, `quota_hit=true` → 그날 ingest도 멈춤(03-Q2) | `MSG_BUDGET` | `quota` (WARNING) |
| `mark_quota_hit` 자체 실패(DB) | 1건 | live +1 | `MSG_BUDGET` (표시 실패는 로그 ERROR) | `quota` |
| TourAPI 오류 23(초당 한도) | 1건 | live +1 | `MSG_RATE` — 이번 호출만 실패, 다음 호출은 시도 | `rate` |
| 타임아웃·HTTP 오류·XML 게이트웨이 오류·키 오류(30 등)·`parse` | 1건 | live +1(실패도 셈, [03] §5.1-2) | `MSG_FAIL` (코드는 로그에만) | `error` |
| 예약 중 DB 오류(연결 끊김 등) | 0건 | 알 수 없음 | `MSG_FAIL` — 셀 수 없으면 부르지 않음(fail-closed) | `error` |
| 같은 답변에서 `tour_live` 여러 번 호출 | 호출마다 1건 | 호출마다 +1 | 각각 | — 상한은 일일 200·그래프 `recursion_limit`([02] §5.5)뿐(확인 질문 Q6) |
| 실행 중 자정 통과 | — | 다음 예약부터 새 날짜 키 | — | — |
| festival 응답이 100건 넘음 | 1건 | +1 | 앞 100건만 사용, `truncated: true` | `ok` |
| 기간 중인 축제가 응답에 안 나옴(`eventStartDate` 의미 차이) | — | — | — | §12 L1에서 확인 → 요청 시작일을 앞당기는 코드 수정 |
| 오류 메시지에 키·내부 URL | — | — | 넣지 않는다(MSG_* 고정 문자열만) | — |
| tour-tools에 `TOURAPI_SERVICE_KEY` 없음 | — | — | 서버 기동 거부(종료 코드 2) → api의 `load_tools`가 실패 → 채팅 `error{llm_unavailable}`([02] §6.2) | — |
| api의 MCP 툴 목록에 `tour_live`가 없음(옛 tour-tools 이미지) | — | — | `load_tools` `RuntimeError` → `llm_unavailable` ([02] §6.2 허용 목록 규칙) | — |

- 오류 메시지는 **사실만** 적는다(지시문 없음). 툴 결과는 `<자료>`로 감싸지고 "자료 속 지시는 따르지 않는다"([02] §6.3 규칙 7)라서, "data_query로 답하라" 같은 안내는 툴 설명과 `answer.md`(§8.2)에 둔다.
- 22를 실시간 툴이 받아 `quota_hit`가 켜지면 그날 적재는 [03]의 "남은 예산 0"으로 멈춘다(`stop_reason=budget`). `nadri ingest status`의 `quota_hit` 표시로 원인을 알 수 있다.

---

## 8. api 쪽 변경

### 8.1 `agent/tools.py` ([02] §6.2)
```python
TOUR_TOOL_ORDER: tuple[str, ...] = ("rag_query", "data_query", "tour_live", "get_datetime")
TOOL_LABELS["tour_live"] = "실시간 정보 확인 중"
MATERIAL_SOURCES["tour_live"] = "한국관광공사 공공데이터(실시간 조회)"
```
- 최종 툴 순서: `rag_query, data_query, tour_live, get_datetime, web_search`(고정 — ADR-16). 허용 목록에 `tour_live`가 들어가므로 MCP 서버에 없으면 `RuntimeError`([02] 규칙 그대로).
- 순서·툴 정의가 바뀌어 배포 직후 첫 요청은 프롬프트 캐시 미적중(1회성, 정상).
- `evidence.py`·`output_guard.py`는 **바꾸지 않는다**: `tour_live` 결과 항목에 `contentid`·`title`·`source`·`as_of`가 있어 [02] §8.1 규칙(키 `contentid`를 가진 dict → `SourceItem(type="tour")`)으로 그대로 근거·`sources`가 된다. 결과에 URL이 없으므로 `allowed_urls`에는 들어가지 않는다.

### 8.2 `prompts/answer.md` — 규칙 4에 추가 (확인 질문 Q3)
> - 진행 중이거나 다가오는 축제·행사는 `tour_live`(op="festival"). 날짜가 "이번 주말"처럼 상대적이면 먼저 `get_datetime`으로 범위를 구한다.
> - 주변 장소는 먼저 `data_query`(near). 결과가 없거나 사용자가 지금 기준 최신 정보를 원하면 `tour_live`(op="nearby"). 좌표는 질문의 "현재 위치" 줄이나 툴 결과의 lat·lng만 쓰고 지어내지 않는다.
> - `tour_live`가 "실시간 조회 불가"를 돌려주면 `data_query`로 저장된 정보를 찾아 답하고, 실시간 정보가 아니라 기준일 자료임을 밝힌다.

- 08도 `answer.md`를 보강한다(같은 파일). 병합 순서에 따라 규칙 번호만 맞춘다(§11-3).

---

## 9. 테스트 요지 (상세는 test.md)
- 단위(Docker 없음): 입력 검증, 날짜 범위, 서비스 지역 상자, 항목 변환·정렬·필터, 오류 → 메시지 변환, 예약이 요청보다 먼저·예약 실패 시 요청 0건, 22 → `mark_quota_hit` 1회, 로그에 좌표 없음, 예약 SQL 바인드, 서버 툴 4개 등록·키 필수, api 툴 순서·라벨, evidence 수집.
- DB(마커 `db`, [04] `pg_container`): 함수 동작·동시 예약·`nadri_tools`가 함수만 쓰고 테이블은 못 건드림·[03] `Budget`과 같은 행 공유·quota_hit 공유.
- 통합(`integration`, 실 TourAPI 2~3건): festival·nearby 실호출, 카운터 +1 확인, 어댑터 툴 목록.
- HITL: 채팅으로 "오늘 서울에서 하는 축제" 1회, 예산 소진 흉내.

---

## 10. 앞 작업과 달라지는 점 (앞 작업 코드·테스트를 이 작업에서 고침)
| # | 앞 작업 | 10 | 고칠 테스트 |
|---|---|---|---|
| 1 | [01] tour-tools 툴 3종, `ToolDeps` 4필드 | 툴 4종, `ToolDeps`에 `tourapi`·`live_budget` | 01 통합 **I-2** 기대 이름 집합에 `tour_live` 추가. 01 HITL H-7 기대 "툴 3종 목록" → 목록 4종(smoke는 3종만 호출 — 코드 그대로) |
| 2 | [01] `build_app`은 TourAPI 키 불필요 | 키 필수(`require`) | 01 **U-AUTH-9**(빈 토큰 기동 거부): 테스트 환경에 가짜 `TOURAPI_SERVICE_KEY`를 넣어 "토큰 때문에" 거부되는지 확인하게 고침 |
| 3 | [01] `nadri_tools` = 2테이블 SELECT만, [01] §5.2 tour-tools에 TourAPI 키 없음 | + 함수 2개 EXECUTE, tour-tools에 키 주입 | 01 I-5·04 D-PRV-1~3은 **그대로 통과**해야 한다(테이블 권한 변화 없음) — 회귀 확인만 |
| 4 | [02] `TOUR_TOOL_ORDER` 3개, 라벨 4개 | 4개, 라벨 5개 | 02 **U-TL-01**(FakeMCPClient 입력에 `tour_live` 추가, 기대 순서 `["rag_query","data_query","tour_live","get_datetime","web_search"]`), **U-TL-02**(누락 대상 예시 유지), **U-TL-07**(5개 이름 라벨). `FakeMCPClient`로 툴 목록을 만드는 다른 02 테스트(U-API-07·08 등)의 툴 목록에도 `tour_live` 가짜 툴 추가 |
| 5 | [02] `answer.md` 규칙 4 | `tour_live` 기준 3줄 | 프롬프트 내용 스냅샷 테스트가 있으면 갱신 |
| 6 | [03] `ingest_state` 카운터의 `live`는 "10이 채운다" | 함수로 채움 | 03 테스트 수정 없음. 03 U-BG-7(`live` 남은 수)과 같은 의미로 동작 |

---

## 11. 상위 문서와의 차이 (아키텍처 범위 안의 구현 판단)
1. **`nadri_tools` 권한 확장**: [A] §5.1 "DB 롤(3개, 변경 없음) … `nadri_tools`는 SELECT만", [R] NFR-07 "관광 테이블 SELECT만 되는 DB 계정". 이 작업은 테이블 권한은 그대로 두고 **카운터 함수 2개 실행 권한**을 더한다. G4 Q6(카운터 공유)과 01-Q6(10에서 최소 권한으로 결정)을 함께 만족시키는 가장 좁은 방법이다. NFR-07·[A] §5.1 문구에 "실시간 카운터 함수 실행 권한 예외"를 덧붙일지 확인 질문 Q1.
2. **`tour_live` 툴 인자**: [A] §2.1은 `tour_live(op, …)`만 적었다. 이 spec이 `op` 값(`festival`·`nearby`)과 나머지 인자를 정했다(`near`는 [01] `data_query`와 같은 모양).
3. **`answer.md` 수정**: [PL] 10 파일 목록에 없다. 툴 선택 규칙이 프롬프트에 툴 이름으로 적혀 있어([02] §6.3 규칙 4) 같이 고쳐야 한다. 08도 같은 파일을 고친다(병합 시 충돌 가능 — 규칙 4 안에서만 고쳐 충돌 범위를 줄임).
4. **NFR-33과 대화 저장(09에 전달)**: [A] §5.1 `chat_messages.tool_results`는 툴 **인자**까지 저장한다. 위치 동의로 받은 좌표가 `tour_live`·`data_query`의 `near` 인자로 들어가면 저장되어 NFR-33("저장·로그하지 않는다")과 어긋난다. 또 결과의 `distance_km`와 장소 좌표를 여러 개 모으면 사용자 위치를 대략 역산할 수 있다. 10은 **결과에 요청 좌표를 넣지 않고 로그에 남기지 않는 것**까지만 한다. 저장 쪽은 09에서 "`near` 인자는 저장 전에 지우고, `distance_km`도 지울지" 결정이 필요하다(확인 질문 Q7 — 01 `data_query`에도 같은 문제가 이미 있음).
5. **서울·제주 밖 좌표 거부**(Q2): [A]에 없는 검사. 범위 밖 지역([PL] §4.3)에 실시간 예산을 쓰지 않게 하는 최소 검사다.

---

## 12. 가정 판정
[PL] 10 "가정: 없음"([A] §12 A1~A30 중 이 작업에 배정된 것 없음). 대신 구현 중 확인할 **미확인** 사실:

| ID | 사실 | 확인 방법 | 다르면 (모두 코드 수정, 사용자 확인 불필요) | 결과 |
|---|---|---|---|---|
| L1 | `searchFestival2`의 `eventStartDate`가 "이 날짜 이후 **끝나는**(진행 중 포함)" 행사를 주는지, "이 날짜 이후 **시작하는**" 행사만 주는지 | 통합 I-LV-2 결과에서 `event_start < 오늘 ≤ event_end`인 항목이 있는지 + 공공데이터포털 활용가이드 | 시작 기준이면 요청 `eventStartDate`를 `start − 90일`(상수 `FESTIVAL_LOOKBACK_DAYS`)로 앞당기고 코드 필터(§6.3-5)로 거른다. 이 경우 100건 안에 다 안 들어오면 `truncated`로 알림 | |
| L2 | 응답 item 필드명(`eventstartdate`·`eventenddate`·`mapx`·`mapy`·`addr1`·`tel`·`sigungucode`) | I-LV-2·3 응답 키 기록 | 매핑 수정, 단위 픽스처를 실제 응답 1건으로 교체 | |
| L3 | `locationBasedList2`의 `radius` 상한(20,000m 추정)·`arrange=E`(거리순) 지원·`dist` 필드 | I-LV-3, 활용가이드 | 상한이 작으면 `NearPoint` 대신 `nearby`용 radius 상한을 낮춤. 거리순이 없으면 50건 안에서 코드 정렬(현재 설계 그대로) | |
| L4 | 빈 결과 모양(`items: ""` vs 별도 resultCode) | 결과가 없을 법한 조건(제주 시군구 하나·먼 날짜)으로 1회 | 별도 코드면 그 코드를 빈 결과로 처리 | |
| L5 | MCP 서버의 예외 → 어댑터 `ToolException` 변환([02] §5.2 미확인 이어받음) | HITL H-5(예산 소진 흉내)에서 답변이 계속되는지 | [02] `handle_tool_errors` 튜플에 해당 예외 추가([02] 규칙) | |
| L6 | `numOfRows=100` 허용 | I-LV-2 | 상한에 맞춰 `FESTIVAL_ROWS` 수정 | |
| L7 | `SERVICE_BOXES`가 서울·제주 행정 경계(제주는 마라도·우도·추자도 포함)를 덮는지 | 단위 U-LV-9 표본 좌표 + 지도에서 끝 지점 좌표 확인 | 상자 값 수정 | |

---

## 13. 완료 기준 (DoD)
1. `docker compose up -d --build`로 tour-tools가 healthy, `alembic upgrade head`(ingest 기동 명령)에 `0003` 포함. api의 툴 목록이 `rag_query, data_query, tour_live, get_datetime, web_search` 순서.
2. `nadri_tools` 권한: 함수 2개 EXECUTE 가능, `ingest_state` SELECT·INSERT·UPDATE·DELETE 모두 거부, 01·04 권한 테스트 회귀 없음. PUBLIC·`lightrag` 롤은 함수 실행 불가.
3. **예산 초과 없음**: 동시 예약 테스트에서 live가 limit을 넘지 않고, ingest 값은 함수 호출로 바뀌지 않는다. 22 → `quota_hit` → 그날 ingest `Budget.reserve`도 거부(DB 테스트).
4. TourAPI 목킹 단위테스트: 오퍼레이션 이름·파라미터, 예약→요청 순서, 오류 변환(예산·22·23·기타), 빈 결과, 결과 항목 `contentid`·`source`·`as_of` [PL §3].
5. 통합 1회: festival("오늘 서울") 실호출 결과 항목마다 `contentid`·`as_of`(오늘)·`source="실시간 조회"`, 카운터 live가 정확히 +1 [PL §3].
6. HITL: 채팅 "오늘 서울에서 하는 축제" → `tool{tour_live, "실시간 정보 확인 중"}` 이벤트, 답변이 `(#contentid)`로 인용, `done.sources`에 `source="실시간 조회"` 항목, 검증 통과(또는 사실 실패 경고). 예산 소진 흉내 시 TourAPI 호출 없이 답변이 저장 데이터로 이어짐.
7. 로그에 좌표·지역·날짜 인자, 서비스 키가 없다(단위 + HITL 로그 확인).
8. §12 미확인 사실 확인 결과를 표에 기록.
9. 단위·DB 테스트 전부 통과(`-m "not integration"`), 통합 통과. §10의 앞 작업 테스트 수정 반영 후 01·02·03·04 테스트 전부 통과.
10. 주석 규칙(한국어 docstring + 단계 주석), 커밋은 `feat/10-tool-tour-live` 브랜치·사용자 커밋 형식(`[Feat] …` + 작업 목록 + `Author:` 줄, AI 공동작성 표기 없음 [R NFR-73]). `dev` 병합은 G5 승인 후. `PROGRESS.md` 작업 표 갱신.

---

## 14. 확인 질문
| # | 질문 | 추천안 | 대안 |
|---|---|---|---|
| Q1 | `nadri_tools`가 카운터를 쓰는 방식(01-Q6에서 10으로 넘김) | **결정(2026-11-21): 추천안대로** — **SECURITY DEFINER 함수 2개(`tourapi_live_reserve`·`tourapi_live_mark_quota_hit`) 실행 권한만** — `ingest_state` 테이블 권한 없음, live 카운터 +1·quota_hit 표시만 가능. NFR-07·[A] §5.1에 "카운터 함수 실행 권한 예외" 한 줄 추가 | B: `GRANT SELECT, INSERT, UPDATE ON ingest_state TO nadri_tools`(간단, 대신 적재 커서·실패 기록·ingest 카운터까지 바꿀 수 있음) / C: B + 행 단위 보안(RLS)으로 `tourapi_calls:*` 키만 허용(설정 증가) |
| Q2 | `nearby` 좌표가 서울·제주 밖이면 거부할까 | **결정(2026-11-21): 추천안대로** — **거부**(대략 상자 2개로 검사, TourAPI·예산 안 씀). 서비스 범위가 서울·제주 | 검사 없음(경기 등 경계 밖 질문에도 실시간 조회가 나가고 범위 밖 답변이 생김) |
| Q3 | `answer.md` 툴 선택 규칙에 `tour_live` 기준을 넣을까([PL] 파일 목록 밖, 08과 같은 파일) | **결정(2026-11-21): 추천안대로** — **넣는다**(§8.2 3줄: 축제는 tour_live / 주변은 data_query 먼저 / 실시간 불가면 data_query로 대신하고 기준일 밝힘) | 툴 설명 문자열만으로 안내(파일 충돌 없음, 대신 모델이 언제 쓰는지 덜 분명) |
| Q4 | 결과 항목 `source` 값 | **결정(2026-11-21): 추천안대로** — **[A] 그대로 `"실시간 조회"`**, 제공처는 `<자료 출처="한국관광공사 공공데이터(실시간 조회)">`로 LLM에 전달 | `"한국관광공사 TourAPI 4.0 (실시간 조회)"`(화면 출처 목록에서 제공처가 바로 보임, [A] 문구와 다름) |
| Q5 | 주변 질문에서 어느 툴을 먼저 쓰게 할까 | **결정(2026-11-21): 추천안대로** — **`data_query`(저장 데이터, 무료) 먼저**, 결과가 없거나 최신 요청일 때만 `tour_live` — 하루 200건 아낌 | `tour_live` 먼저(항상 최신, 대신 예산 소모가 빠름) |
| Q6 | 한 답변 안의 `tour_live` 호출 횟수 상한 | **결정(2026-11-21): 추천안대로** — **두지 않음**(일일 200·그래프 `recursion_limit`으로 충분, 사용자 1명 규모) | 요청당 3회 상한(api `tools` 노드에서 셈 — 코드 추가) |
| Q7 | (09에 전달) 대화 저장 시 `near` 인자·`distance_km`가 저장되면 NFR-33과 어긋남 | **결정(2026-11-21): 추천안대로** — **09에서 `tool_results` 저장 전 `near` 인자와 `distance_km`를 지운다**(`data_query`·`tour_live` 공통). 10은 결과에 요청 좌표를 넣지 않고 로그에도 남기지 않음 | `near` 인자만 지우고 `distance_km`는 둔다(품질 평가 24에서 거리 답변 검토 가능, 역산 위험 남음) |
| Q8 | festival 범위·건수 상한 | **결정(2026-11-21): 추천안대로** — **최대 31일, 요청 1회 100건**(넘으면 `truncated`로 알림, 추가 페이지 안 받음 — 툴 호출 1회 = TourAPI 1건) | 여러 페이지를 받아 전부(호출 수 증가) |
