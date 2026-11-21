# 10-tool-tour-live — 테스트 설계 (test)

> spec.md와 짝. 절 번호 §n은 spec.md 기준. 작성 2026-11-21. 상태: 초안 — 사용자 검토 대기.
> 두 방향을 나눈다: ① pytest — 단위(결정적, 실 TourAPI·실DB 없음) + DB(마커 `db`, [04] 테스트 DB 컨테이너) + 통합(`@pytest.mark.integration`, 실 compose·실 TourAPI) ② HITL(사용자가 직접 실행).

---

## 0. 실행 방법

WSL2 Ubuntu의 uv 가상환경(`backend/.venv`)에서 ([01] §5.3a, [04] §7).
```bash
cd backend
uv run pytest -m "not integration and not db" -q      # 단위만 (Docker 불필요)
uv run pytest -m "not integration" -q                 # 단위 + DB (Docker 필요 — 테스트 DB 컨테이너)
# 통합: compose.dev.yaml로 전체 기동 + .env 실 키, 오늘 실시간 예산이 3건 이상 남아 있을 때
DB_HOST=127.0.0.1 TOOLS_URL=http://127.0.0.1:8001/mcp uv run pytest -m integration -q tests/integration/test_tour_live_live.py
```

### 대역(가짜)
| 외부 | 대역 |
|---|---|
| TourAPI | `httpx.MockTransport` — 요청 URL·쿼리를 기록하고 `tests/fixtures/tourapi/festival_*.json`·`nearby_*.json`·오류 응답을 돌려줌([01] 방식). 픽스처는 처음엔 손으로 만들고 §12 L2 확인 뒤 실제 응답 1건씩으로 교체(키 없음 확인) |
| 카운터 | `FakeLiveBudget` — `reserve(op)`는 공유 기록 목록에 `("reserve", op)`를 남기고, 스크립트에 따라 통과·`BudgetExhausted`·`OSError`. `mark_quota_hit()` 호출 수 기록, 옵션으로 예외 |
| 시계 | `clock`에 고정 KST 시각 |
| DB(단위) | 쓰지 않음. SQL은 `stmt.compile(dialect=postgresql.dialect())`로 문자열·바인드 검사([01] 방식) |
| 리랭커·LightRAG | 서버 등록 테스트에서 가짜 `ToolDeps`(필드만 채운 더미) |

순서 확인: `FakeLiveBudget`과 MockTransport 핸들러가 **같은 목록**에 기록 → 목록 순서로 "예약 → 요청"을 확인.

---

## ① 단위테스트 (pytest, 마커 없음)

### U-TP `tests/core/test_tourapi_live.py` — TourAPI 클라이언트 확장 (§6.1)
| ID | 입력 | 기대 |
|---|---|---|
| U-TP-1 | `search_festival("서울", date(2026,11,21), num_of_rows=100)` | 경로 `/searchFestival2`, 쿼리 `areaCode=1`(= `AREAS["서울"]`), `eventStartDate=20261121`, `numOfRows=100`, `pageNo=1`, `_type=json`, `MobileOS=ETC`, `MobileApp=nadri`, `serviceKey` 있음, `sigunguCode` **없음** |
| U-TP-2 | 같은 호출 + `sigungu_code="23"` | `sigunguCode=23` |
| U-TP-3 | `location_based_list(37.5796, 126.9770, 1000, num_of_rows=50)` | 경로 `/locationBasedList2`, `mapX=126.977`, `mapY=37.5796`(경도·위도가 뒤바뀌지 않음), `radius=1000`, `arrange=E`, `numOfRows=50`, `contentTypeId` 없음 |
| U-TP-4 | 같은 호출 + `content_type_id=39` | `contentTypeId=39` |
| U-TP-5 | `search_festival("부산", …)` | `ValueError`, HTTP 요청 0건 |
| U-TP-6 | `on_call` 순서 | 기록 목록이 `on_call("searchFestival2")` → 요청 순 ([03] U-TA2-1과 같은 방식) |
| U-TP-7 | 반환 `TourApiResponse.params` | `serviceKey` 키 없음 |

### U-LV `tests/tools/test_tour_live.py` — 입력 검증·변환·오류 (§6.2·§6.3·§7)

**입력 검증** (`TourLiveParams`, `resolve_dates`, `in_service_area`)
| ID | 입력 | 기대 |
|---|---|---|
| U-LV-1 | `op="festival"`, area 없음 | 검증 오류 |
| U-LV-2 | `op="festival", area="서울", near={…}` | 검증 오류 |
| U-LV-3 | `op="nearby"`, near 없음 | 검증 오류 |
| U-LV-4 | `op="nearby", near={…}, area="서울"` / `start_date=…` | 둘 다 검증 오류 |
| U-LV-5 | `limit=100` / `limit=0` | `limit == 20` / 검증 오류 |
| U-LV-6 | `content_type=13` / `sigungu_code="1; DROP"` / `op="weather"` | 모두 검증 오류 |
| U-LV-7 | `resolve_dates`, today=2026-11-21: (없음,없음) / (11-28,없음) / (11-28,11-27) | (11-21,11-21) / (11-28,11-28) / `ValueError` |
| U-LV-8 | 〃 (11-01,12-01)=31일 / (11-01,12-02)=32일 | 통과 / `ValueError` |
| U-LV-9 | `in_service_area`: 서울시청(37.5663,126.9779)·제주시청(33.4996,126.5312)·마라도(33.1180,126.2669)·추자도(33.9620,126.2990) / 부산시청(35.1796,129.0756)·인천공항(37.4602,126.4407) | 앞 4개 True / 뒤 2개 False (좌표는 공개 지도 값 — §12 L7) |
| U-LV-10 | `op="nearby"`, near = 부산시청 좌표 | 검증 오류, 메시지 "서울·제주 밖 좌표는 조회하지 않습니다." |

**변환** (`parse_yyyymmdd`, `festival_items`, `nearby_items` — 순수 함수)
| ID | 입력 | 기대 |
|---|---|---|
| U-LV-11 | `parse_yyyymmdd`: `"20261121"` / `""` / `None` / `"20261301"` / `"2026-11-21"` | `date(2026,11,21)` / None ×4 |
| U-LV-12 | `festival_items` 픽스처 5건, 범위 11-21~11-21: A(11-01~11-30), B(11-21~11-21, 제목 `"서울 &amp; 빛 축제"`, `firstimage` 있음), C(12-01~12-05), D(`eventenddate` 없음), E(`title` 없음) | 결과 [A, B] 순서(시작일 순). B 제목 `"서울 & 빛 축제"`. C(기간 밖)·D(날짜 없음)·E(필수값 없음) 제외 |
| U-LV-13 | 〃 항목 키 | 정확히 `contentid, title, content_type_id, area, sigungu_code, addr, tel, lat, lng, event_start, event_end, source, as_of`. `source=="실시간 조회"`, `as_of=="2026-11-21"`, 날짜는 ISO 문자열, `firstimage`·URL 값 없음 |
| U-LV-14 | 범위 11-21~11-22, F(11-22~11-23) 추가 | F 포함 |
| U-LV-15 | `nearby_items`, 기준 (37.5700,126.9800) 반경 1.0km, 항목: 0.3km·0.9km·1.4km 지점, `mapx="0"` 항목 | 0.3·0.9 두 개, 거리 오름차순, `distance_km` 소수 2자리, 1.4km·좌표 0 제외. 키 = `contentid, title, content_type_id, addr, tel, lat, lng, distance_km, source, as_of` |

**툴 본체** (`tour_live(p, deps)` — 실제 `TourApiClient` + MockTransport + `FakeLiveBudget`, 시계 2026-11-21 14:00 KST)
| ID | 상황 | 기대 |
|---|---|---|
| U-LV-16 | festival 정상(응답 3건, totalCount 3) | 결과 키 `op, items, count, total_count, truncated, source, as_of, fetched_at, range`, `truncated is False`, `range == {"start":"2026-11-21","end":"2026-11-21"}`, `fetched_at`이 `+09:00` |
| U-LV-17 | 응답 100건, totalCount 150 | `truncated is True`, `limit` 10 → `count == 10` |
| U-LV-18 | 순서 | 공유 기록 = `[("reserve","searchFestival2"), ("request","/searchFestival2")]` |
| U-LV-19 | 예산 소진(`reserve`가 `BudgetExhausted`) | `LiveUnavailable`, 메시지 == `MSG_BUDGET`, **HTTP 요청 0건**, `mark_quota_hit` 0회 |
| U-LV-20 | 응답 resultCode `22` | `LiveUnavailable(MSG_BUDGET)`, `mark_quota_hit` **1회**, 로그 WARNING `outcome=quota` |
| U-LV-21 | 22 + `mark_quota_hit`가 예외 | 여전히 `MSG_BUDGET`, 로그 ERROR 1줄 |
| U-LV-22 | 응답 XML 코드 `23` | `MSG_RATE`, `mark_quota_hit` 0회, 요청 1회(재시도 없음) |
| U-LV-23 | `httpx.ReadTimeout` / HTTP 500 / XML 코드 `30` / 깨진 본문 | 모두 `MSG_FAIL`, 요청 각 1회, 메시지·로그에 서비스 키 값 없음, 로그에 `tourapi_code=timeout`/`http_500`/`30`/`parse` |
| U-LV-24 | `reserve`가 `OSError`(DB 끊김) | `MSG_FAIL`, HTTP 요청 0건 |
| U-LV-25 | 빈 응답(`items: ""`, totalCount 0) | 오류 아님, `items == []`, `count == 0`, 로그 `outcome=empty` |
| U-LV-26 | nearby 정상, 요청 좌표 (37.57961, 126.97701) — 어느 장소 좌표와도 다른 값 | `json.dumps(결과)`에 `"37.57961"`·`"126.97701"` 문자열 없음, `range`·`near` 키 없음 |
| U-LV-27 | 로그 (U-LV-26 실행 후 `caplog`) | `tool=tour_live op=nearby outcome=ok count=` 한 줄, `37.57961`·`126.97701`·날짜·서비스 키 없음 |
| U-LV-28 | 시계 2026-11-21 23:59:59 KST | `as_of == "2026-11-21"`(응답 `fetched_at` 기준) |

### U-LB `tests/tools/test_live_budget.py` — 카운터 래퍼 (§6.3)
| ID | 대상 | 기대 |
|---|---|---|
| U-LB-1 | `build_live_reserve_stmt(date(2026,11,21), "searchFestival2", 200)` 컴파일 | SQL에 `tourapi_live_reserve` 포함. `2026-11-21`·`searchFestival2`·`200`은 **SQL 문자열에 없고 바인드에만** |
| U-LB-2 | `build_live_quota_hit_stmt(date(2026,11,21))` | SQL에 `tourapi_live_mark_quota_hit`, 날짜는 바인드 |
| U-LB-3 | `LiveBudget.reserve` — 가짜 세션이 스칼라 `None` 반환 / `5` 반환 | `BudgetExhausted` / 정상 반환, 두 경우 모두 커밋 1회 |
| U-LB-4 | 시계가 23:59:59 → 00:00:01(KST)로 넘어감 | 두 예약 문의 날짜 바인드가 `2026-11-21`, `2026-11-22` ([03] U-BG-15와 같은 방식) |

### U-SV `tests/tools/test_server_live.py` — 서버 등록 (§6.4)
| ID | 대상 | 기대 |
|---|---|---|
| U-SV-1 | `build_mcp(가짜 deps)` → `await mcp.list_tools()` | 이름 순서 `["rag_query","data_query","tour_live","get_datetime"]` |
| U-SV-2 | `tour_live` 입력 스키마 | `op` enum = `festival`,`nearby`; `area` enum = `서울`,`제주`; `near`에 `lat`·`lng`·`radius_km` |
| U-SV-3 | `tour_live` 설명 | spec §6.4 고정 문자열과 같음(바뀌면 프롬프트 캐시가 깨진다는 것을 알리는 스냅샷) |
| U-SV-4 | FastMCP로 `tour_live` 호출, 인자 `{"op":"festival"}`(area 없음) | 결과 `isError`, `FakeLiveBudget.reserve` 0회 |
| U-SV-5 | FastMCP로 호출, `FakeLiveBudget`이 `BudgetExhausted` | 결과 `isError`, 텍스트에 `MSG_BUDGET` 포함 |
| U-SV-6 | `build_app` — `TOOLS_API_KEY` 있음, `TOURAPI_SERVICE_KEY` 없음 | `SystemExit(2)`, 메시지에 `TOURAPI_SERVICE_KEY`. 리랭커·DB 엔진 생성 전에 끝남(가짜 리랭커 생성자 호출 0회) |

### U-TL·U-EV — api 쪽 (`tests/agent/test_tools.py`, `tests/agent/test_evidence.py`)
| ID | 대상 | 기대 |
|---|---|---|
| U-TL-01 (수정) | FakeMCPClient가 `[get_datetime, evil_write, tour_live, rag_query, data_query]` | 이름 순서 `["rag_query","data_query","tour_live","get_datetime","web_search"]`, `evil_write` 없음 |
| U-TL-02 (그대로) | `rag_query` 누락 | `RuntimeError` |
| U-TL-02b (신규) | `tour_live` 누락 | `RuntimeError` |
| U-TL-07 (수정) | `tool_label` 5개 이름 | `tour_live` → `"실시간 정보 확인 중"`, 모르는 이름 → `"자료 찾는 중"` |
| U-TL-08 (신규) | `wrap_as_material("tour_live", "{}")` | `<자료 출처="한국관광공사 공공데이터(실시간 조회)" 도구="tour_live">`로 시작 |
| U-EV-10 (신규) | `collect_evidence`에 `tour_live` 결과 JSON 기록 1개(`tests/data/tour_live_ok.json`, 항목 2개) | `contentids` 2개, `by_contentid[...]`의 `title`·`source=="실시간 조회"`·`as_of` 채워짐, `urls` 비어 있음 |
| U-EV-11 (신규) | `build_sources("… (#2786391) …", ev)` | `sources == [{"type":"tour","contentid":"2786391","title":…,"source":"실시간 조회","as_of":…}]`, `allowed_urls == []` |
| U-EV-12 (신규) | `is_error=True`인 `tour_live` 기록(`MSG_BUDGET`) | 근거에서 제외(contentids 비어 있음) — [02] 규칙 회귀 |

- 02의 다른 테스트에서 `FakeMCPClient`로 툴 목록을 만드는 곳(U-API-07·08 등)은 `tour_live` 가짜 툴을 목록에 추가해야 통과한다(spec §10-4).

---

## ① DB 테스트 (마커 `db`) — `tests/db/test_live_counter.py`

[04] §7 픽스처(`pg_container`, `db_sf`, `super_engine`)를 쓴다. 추가 픽스처(이 파일 안):
- `tools_engine`: `postgresql+asyncpg://nadri_tools:test-tools@{pg_container.host}:{pg_container.port}/nadri` 엔진(테스트마다).
- `live_day`: 테스트마다 다른 먼 미래 날짜(2099-01-01부터 순서대로)를 주고, 끝나면 `super_engine`으로 `DELETE FROM ingest_state WHERE key LIKE 'tourapi_calls:2099-%'`([04] `db_engine`은 앱 테이블 14개만 비우므로 직접 정리).

| ID | 대상 | 기대 |
|---|---|---|
| D-LB-1 | `pg_proc` 조회: 두 함수 | `prosecdef = true`, `proconfig`에 `search_path=pg_catalog, public, pg_temp`, 소유자 `nadri_app` |
| D-LB-2 | `has_function_privilege(롤, 함수, 'EXECUTE')` | `nadri_tools` true ×2, `nadri_app` true(소유자), `lightrag` **false** ×2(PUBLIC 회수 확인) |
| D-LB-3 | `nadri_tools`로 `SELECT tourapi_live_reserve(:d, 'searchFestival2', 200)` | 반환 1. 값 == `{"ingest":0,"live":1,"ops":{"searchFestival2":1},"quota_hit":false}` |
| D-LB-4 | limit 3으로 4번 | 반환 1, 2, 3, **NULL**. 값 `live == 3` |
| D-LB-5 | 미리 `{"ingest":500,"live":0,"ops":{"detailIntro2":500},"quota_hit":false}`(super로 넣음) → live 예약 2번(`locationBasedList2`) | `ingest == 500` 그대로, `live == 2`, `ops == {"detailIntro2":500,"locationBasedList2":2}` |
| D-LB-6 | 미리 `quota_hit=true` → live 예약 | NULL, 값 변화 없음 |
| D-LB-7 | 동시 예약: limit 10, 연결 50개로 `asyncio.gather` | NULL 아닌 반환 정확히 10개, 값 `live == 10`, `ops` 합 10 ([03] I-1과 같은 방식) |
| D-LB-8 | [03] 공존: 같은 날짜에 [03] `Budget(db_sf, kind="ingest", limit=800, clock=고정)`.`reserve("areaBasedList2")` 1번 + live 함수 1번 | [03] `DayUsage.from_value(값)` == `(ingest=1, live=1, ops={"areaBasedList2":1,"searchFestival2":1}, quota_hit=False)`, 키 == [03] `calls_key(날짜)` |
| D-LB-9 | `nadri_tools`로 `tourapi_live_mark_quota_hit(:d)` → 같은 날 [03] ingest `Budget.reserve` / live 예약 | `quota_hit == true` / `BudgetExhausted` / NULL (03-Q2 "22면 그날 둘 다 중단") |
| D-LB-10 | 행이 없는 날짜에 `mark_quota_hit` | 행 생성, 초기값 + `quota_hit == true` |
| D-LB-11 | `nadri_tools`로 `SELECT/INSERT/UPDATE/DELETE` on `ingest_state` | 4개 모두 권한 오류(`InsufficientPrivilegeError`). `has_table_privilege` 4개 false |
| D-LB-12 | 회귀(01 I-5·04 D-PRV) | `nadri_tools`: `tour_items`·`wiki_pages` SELECT true, `ingest_runs` SELECT false, 앱 테이블 14개 권한 없음 그대로 |
| D-LB-13 | `LiveBudget`(실제 클래스, `tools_engine` 세션, 고정 시계 = `live_day`) limit 1 | 첫 `reserve` 정상, 두 번째 `BudgetExhausted`, `mark_quota_hit()` 후 값 `quota_hit == true` |
| D-LB-14 | 되돌리기·재적용: `alembic downgrade -1` → 함수 없음(`to_regprocedure` NULL) → `upgrade head` → 함수·권한 다시 있음 | 이 테스트는 공유 컨테이너를 head로 되돌려 놓고 끝낸다(실패해도 `finally`에서 `upgrade head`) |

### 통과 기준
- 위 단위·DB 테스트 전부 통과, `-m "not integration and not db"` 실행 시 단위만 돌고 Docker 없이 통과.
- §10의 앞 작업 테스트 수정 후 01·02·03·04 테스트 전부 통과.

---

## ① 통합 테스트 (`@pytest.mark.integration`) — `tests/integration/test_tour_live_live.py`

전제: `docker compose -f compose.yaml -f compose.dev.yaml up -d --build`(0003 적용), `.env`에 실 `TOURAPI_SERVICE_KEY`, 오늘 실시간 예산이 3건 이상 남음. 카운터 읽기는 `.env`의 `APP_DB_PASSWORD`로 `nadri_app` 접속(01 통합과 같은 방식). **실 TourAPI 2건 사용**.

| ID | 내용 | 기대 |
|---|---|---|
| I-LV-1 | `MultiServerMCPClient`(headers 포함) `get_tools()` | 이름 집합 == {`rag_query`,`data_query`,`tour_live`,`get_datetime`} (01 I-2 수정판과 같음), `tour_live` 스키마의 `op` enum |
| I-LV-2 | 어댑터로 `tour_live(op="festival", area="서울")` (오늘) | 오류 아님. 항목마다 `contentid` 비어 있지 않음, `as_of ==` 오늘 KST, `source == "실시간 조회"`, `event_start ≤ 오늘 ≤ event_end`. 오늘 `live`가 호출 전보다 **정확히 +1**. 기록: 응답 키 목록(L2), `total_count`·`truncated`(L6), `event_start < 오늘`인 항목 수(L1 — 0이면 L1 대안 적용 검토) |
| I-LV-3 | `tour_live(op="nearby", near={"lat":37.5796,"lng":126.9770,"radius_km":1})` (경복궁) | 항목 `distance_km ≤ 1.0`, 거리 오름차순, `source`·`as_of` 채워짐. `live` +1. 기록: `dist` 필드 유무·응답 정렬(L3) |
| I-LV-4 | `tour_live(op="nearby", near=부산시청)` | 툴 오류(입력 검증), `live` 변화 없음(비용 0) |
| I-LV-5 | tour-tools 로그(`docker compose logs tour-tools --since 5m`)를 테스트가 읽지 않음 — HITL H-6에서 사람이 확인 | — |

- 결과 기록: 실행 시각, 항목 수, L1·L2·L3·L6 관찰값을 spec §12 표에 적는다.

---

## ② HITL — 사용자가 직접 실행·확인

모든 명령은 WSL2 Ubuntu `~/code/myAgent`에서. 오늘 날짜는 `D=$(TZ=Asia/Seoul date +%F)`로 둔다.

### H-0 준비
1. `feat/10-tool-tour-live` 브랜치, `.env`에 `TOURAPI_SERVICE_KEY` 있음(01에서 넣은 값).
2. 지금 카운터를 적어 둔다:
   `docker compose exec postgres psql -U postgres -d nadri -c "select value from ingest_state where key='tourapi_calls:$D'"`
3. 03 초기 적재를 `--follow`로 돌리고 있으면 그대로 둔다(H-5는 실시간 몫만 건드림). H-7(선택)은 적재가 돌고 있지 않을 때만.

### H-1 기동·키 주입·함수 확인
```bash
docker compose -f compose.yaml -f compose.dev.yaml up -d --build
docker compose ps                                   # tour-tools healthy, ingest Exited (0)
docker compose exec tour-tools python -c "import os;print(bool(os.environ.get('TOURAPI_SERVICE_KEY')))"   # True (값은 출력하지 않음)
docker compose exec postgres psql -U postgres -d nadri -c "\df+ tourapi_live_*"
```
- 확인: 함수 2개, "보안" 열이 definer, 소유자 `nadri_app`, 접근 권한에 `nadri_tools=X`만(PUBLIC 없음).

### H-2 권한 눈으로 확인
```bash
docker compose exec postgres psql "postgresql://nadri_tools:$(grep ^TOOLS_DB_PASSWORD .env | cut -d= -f2)@localhost/nadri" \
  -c "select * from ingest_state limit 1"                                   # permission denied
docker compose exec postgres psql "postgresql://nadri_tools:$(grep ^TOOLS_DB_PASSWORD .env | cut -d= -f2)@localhost/nadri" \
  -c "select tourapi_live_reserve('2099-12-31','test',1)"                   # 1
docker compose exec postgres psql -U postgres -d nadri -c "delete from ingest_state where key='tourapi_calls:2099-12-31'"
```
- 확인: 첫 명령은 권한 오류, 두 번째는 `1`. 정리 명령 후 그 행이 없음.

### H-3 테스트 실행
`cd backend && uv run pytest -m "not integration" -q` → 전부 통과. 이어서 §0의 통합 명령 → I-LV-1~4 통과, 출력된 관찰값을 spec §12에 적는다.

### H-4 채팅으로 "오늘 서울에서 하는 축제" (FR-52, 핵심)
그 시점의 채팅 호출 방법을 쓴다: 05 병합 전이면 02 test HITL-2의 `curl`, 05 병합 후면 05 test H-3의 `login`·`$CK`·`$TK` 헤더, 09 병합 후면 세션을 만든 뒤 그 ID.
```bash
curl -sN -X POST http://127.0.0.1:8080/api/chat/sessions/<세션>/messages \
  -H 'Content-Type: application/json' [-H "$CK" -H "X-CSRF-Token: $TK"] \
  -d '{"text":"오늘 서울에서 하는 축제 알려줘"}'
```
- 확인:
  1. `event: tool` 데이터에 `"name":"tour_live","label":"실시간 정보 확인 중"`(앞에 `get_datetime`이 올 수 있음).
  2. 답변의 축제마다 `(#contentid)` 인용, 끝에 기준일(오늘) 줄.
  3. `done.sources`의 항목이 `"source":"실시간 조회"`, `as_of`가 오늘. `verify_status`가 `passed`(또는 `failed`+경고 — 그 경우 이유를 기록).
  4. 축제 2개를 골라 "대한민국 구석구석"(visitkorea.or.kr) 등 공식 화면에서 이름·기간이 맞는지 본다.
  5. 카운터: H-0의 값보다 `live`가 툴 호출 횟수만큼 늘었다(보통 1).
- 질문 "이번 주말 제주 축제"도 1회: `get_datetime` → `tour_live`(범위 토~일) 순서인지 본다.

### H-5 예산 소진 흉내 (엣지, TourAPI 호출 없음 확인)
```bash
# 오늘 live를 200으로 맞춘다 (원래 값을 H-0에서 적어 둠)
docker compose exec postgres psql -U postgres -d nadri -c \
 "update ingest_state set value = jsonb_set(value,'{live}','200') where key='tourapi_calls:$D'"
```
- H-4의 질문을 다시 보낸다. 확인:
  1. `tool` 이벤트에 `tour_live`가 있어도 답변이 계속되고(오류 이벤트 없음), 저장 데이터(`data_query`)로 답하거나 실시간 조회를 못 했다고 밝힌다(spec §8.2 규칙 — L5 확인).
  2. 카운터 `live`가 200 그대로(TourAPI를 부르지 않음).
  3. `docker compose logs tour-tools --since 5m | grep tool=tour_live` → `outcome=budget`.
- 되돌리기: 같은 명령으로 `live`를 H-0 값(+H-4 사용분)으로 돌려놓는다.

### H-6 로그에 위치·비밀값이 없는지 (NFR-33)
1. 주변 질문 1회: "경복궁 근처에 지금 가볼 만한 곳 있어?" — 툴 순서를 적는다(`data_query` 먼저인지, Q5).
2. `docker compose logs tour-tools api --since 10m | grep -E "tool=tour_live|tool=data_query"` → 이 줄들에 좌표(위도·경도 숫자)·날짜·지역 인자가 **없다**.
3. `docker compose logs tour-tools --since 10m | grep -c serviceKey` → `0`(요청 URL·키가 로그에 없음).

### H-7 (선택) quota_hit 공유 확인 — 적재가 돌고 있지 않을 때만
```bash
docker compose exec postgres psql -U postgres -d nadri -c \
 "update ingest_state set value = jsonb_set(value,'{quota_hit}','true') where key='tourapi_calls:$D'"
```
- 축제 질문 → 실시간 조회 불가로 답변 계속. `docker compose run --rm ingest nadri ingest status`에 `quota_hit: true`.
- **반드시 되돌린다**: 같은 명령에서 `'true'` → `'false'`. (켜 둔 채면 그날 적재가 멈춘다.)

### H-8 포털 대조 (A12 이어서)
다음 날, 공공데이터포털 마이페이지 KorService2 트래픽 화면의 전날 사용량과 `ingest_state`의 전날 `ingest + live`를 비교해 적는다(오퍼레이션별 표시가 있으면 `ops`와도).

### 기록 표
| 항목 | 결과 | 비고 |
|---|---|---|
| H-1 함수·키 주입 | | |
| H-2 권한 | | |
| H-3 테스트·L1/L2/L3/L6 관찰 | | |
| H-4 축제 답변·공식 화면 대조 | | |
| H-5 예산 소진 시 답변 계속(L5) | | |
| H-6 로그 좌표·키 없음, 주변 질문 툴 순서 | | |
| H-7 quota_hit 공유(선택) | | |
| H-8 포털 대조 | | |
