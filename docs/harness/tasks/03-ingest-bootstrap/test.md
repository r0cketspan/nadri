# 03-ingest-bootstrap — 테스트 설계

> 하네스 Phase 4 산출물 (spec-writer, 2026-11-21). 대상 스펙: `spec.md`(같은 폴더). 상태: 초안 — 사용자 검토 대기.
> 두 방향을 나눈다: ① 단위테스트(pytest, 실DB·실 TourAPI·실 LightRAG 없이 결정적) ② HITL(사용자가 직접 실행·확인). 그 사이에 실 compose로 도는 **통합 테스트**(`@pytest.mark.integration`)를 둔다.
> 실행 환경·대역 원칙은 01 test.md §0과 같다(WSL2 Ubuntu, `backend/.venv`, `uv run pytest`).

---

## 0. 실행 방법

```bash
cd ~/code/myAgent/backend
uv run pytest -m "not integration" -q                      # 단위
DB_HOST=127.0.0.1 LIGHTRAG_URL=http://127.0.0.1:9621 \
  uv run pytest -m integration -q tests/integration/test_bootstrap_db.py   # 통합(DB만)
```

- 프레임워크: `pytest` + `pytest-asyncio`(`asyncio_mode=auto`), `pyyaml`(frontmatter 확인) — 01 dev 그룹 그대로, 새 의존 없음.
- 대역(test double)
  | 외부 | 대역 |
  |---|---|
  | TourAPI | `httpx.MockTransport`(01과 같음). 유형별 상세 픽스처 `tests/fixtures/tourapi/detail_{유형}_{common,intro,info}.json` 8벌 |
  | 예산 | 테스트 안의 `FakeBudget`(남은 수를 리스트로 스크립트, `reserve`가 0이면 `BudgetExhausted`) |
  | DB | 단위에서는 쓰지 않는다. SQL은 `stmt.compile(dialect=postgresql.dialect())`로 문자열·바인드 확인. `detail_loop`·`run_follow`는 콜백 주입 |
  | 시계·대기 | 고정 tz-aware 시각, 가짜 `sleep`(호출 인자 기록) |
- 픽스처는 처음엔 spec §6.3 표의 필드 이름으로 손으로 만들고, 첫 실호출(I-5·H-3) 뒤 **실제 raw에서 유형별 1건씩 골라 교체**한다(비밀값 없음 확인). 교체 여부를 커밋 메시지에 적는다. 스냅샷(`tests/fixtures/wiki/entity_{유형}.md`)도 함께 다시 만든다.
- 테스트 함수마다 한국어 docstring(무엇을 검증하는지 한 줄).

---

## ① 단위테스트

### U-BG `tests/ingest/test_budget.py` — 공유 카운터·예산
| ID | 대상 | 입력 | 기대 |
|---|---|---|---|
| U-BG-1 | `kst_today` | UTC `2026-11-20T15:30Z` | `date(2026,11,21)` |
| U-BG-2 | 〃 | naive `datetime(2026,11,21)` | `ValueError` |
| U-BG-3 | `calls_key` | `date(2026,11,21)` | `"tourapi_calls:2026-11-21"` |
| U-BG-4 | `DayUsage.from_value` | `None` / 01 형식 `{"ingest": 168, "live": 0}` / 03 형식 전체 | `(0,0,{},False)` / `(168,0,{},False)` / 그대로 |
| U-BG-5 | `remaining` | ingest 798, limit 800 / 800 / 805 | 2 / 0 / 0 |
| U-BG-6 | 〃 | ingest 10, `quota_hit=True` | 0 |
| U-BG-7 | 〃 | kind `live`, live 150, limit 200 | 50 (ingest 값과 무관) |
| U-BG-8 | `build_reserve_stmt(key, "ingest", "detailIntro2", 800)` | 컴파일 | SQL에 `UPDATE ingest_state`, `quota_hit`, `RETURNING` 포함. `800`·`detailIntro2`·키 문자열은 **SQL 문자열에 없고 바인드에만** 있음 |
| U-BG-9 | `build_ensure_stmt` | 컴파일 | `ON CONFLICT` `DO NOTHING`, 초기값 JSON에 `ingest`·`live`·`ops`·`quota_hit` |
| U-BG-10 | `build_quota_hit_stmt` | 컴파일 | `quota_hit`를 true로 설정하는 `jsonb_set`(또는 `||`) 포함, 키는 바인드 |
| U-BG-11 | `estimate_completion` | list 0, detail 0, used 0, budget 800 | `(0, today)` |
| U-BG-12 | 〃 | list 0, detail 200(=600건), used 100 | `T=700 ≥ 600` → `(0, today)` |
| U-BG-13 | 〃 | list 50, detail 1000(=3,050건), used 800 | `T=0` → `ceil(3050/800)=4` → `(4, today+4)` |
| U-BG-14 | 〃 | list 0, detail 20000, used 0 (spec §5.3 예시) | `(74, today+74)` |
| U-BG-15 | `Budget.reserve` 날짜 | 가짜 clock이 23:59:59 → 00:00:01(KST)로 넘어감, 세션은 실행된 문을 기록하는 가짜 | 두 번의 예약 문 바인드 키가 `…-21`, `…-22`로 다름 |

### U-TA2 `tests/core/test_tourapi_types.py` — 클라이언트 변경·유형별 해석
| ID | 대상 | 입력 | 기대 |
|---|---|---|---|
| U-TA2-1 | `on_call` 시점 | MockTransport가 요청 도착 순서를 기록, `on_call`도 같은 목록에 기록 | 목록 순서가 `on_call` → 요청 |
| U-TA2-2 | `on_call` 예외 | `on_call`이 `BudgetExhausted` 던짐 | 같은 예외가 올라오고 **HTTP 요청 0건** |
| U-TA2-3 | 오류 호출도 셈 | 응답 resultCode `22` | `on_call` 1회, `TourApiError.quota_exceeded` (01 U-TA-12를 이 동작으로 고침) |
| U-TA2-4 | `parse_list_item` | 정상 item | `ListItem` 필드 채움, `content_type_id`는 int |
| U-TA2-5 | 〃 | `title` 없음 | `ValueError` |
| U-TA2-6 | `INTRO_SPECS` | 키 집합 | `{12,14,15,25,28,32,38,39}` == `CONTENT_TYPES` 키 |
| U-TA2-7 | 〃 | 8종 각각 | `labels` 키와 핵심 필드(tel·usetime·restdate·fee·event) 사이 중복 없음, `ignore`와도 중복 없음 |
| U-TA2-8 | `split_intro(12, …)` | `usetime`, `restdate`, `infocenter`, `parking`, `heritage1="1"`, `chkpet=""`, `contentid` | 핵심 `{usetime, restdate, tel}`, 나머지 `{"parking": …}`(heritage·빈 값·contentid 없음), 규칙 밖 `[]` |
| U-TA2-9 | 〃 | 12에 모르는 필드 `newfield="x"` | 나머지에 `newfield` 있음, 규칙 밖 `["newfield"]` |
| U-TA2-10 | `split_intro(32, …)` | `checkintime="15:00"`, `checkouttime="11:00"` | 핵심 usetime `"입실 15:00\n퇴실 11:00"` |
| U-TA2-11 | 〃 | `checkintime`만 | `"입실 15:00"` |
| U-TA2-12 | `split_intro(15, …)` | `eventstartdate="20261120"`, `eventenddate="20261130"`, `playtime`, `usetimefestival="무료"`, `sponsor1tel` | 핵심 `event_start/end` 원문, usetime=playtime, fee `"무료"`, tel=sponsor1tel |
| U-TA2-13 | 〃 | 유형 13 | `ValueError` |
| U-TA2-14 | `intro_lines(14, {"zz": "c", "scale": "b", "aa": "d", "discountinfo": "a"})` | — | `[("할인 정보","a"), ("규모","b"), ("aa","d"), ("zz","c")]` — labels 순서(§6.3 표: spendtime → discountinfo → scale …) 다음에 규칙 밖 필드 이름순 |

### U-UP2 `tests/ingest/test_upsert_types.py` — 유형별 레코드·껍데기 행
| ID | 대상 | 입력 | 기대 |
|---|---|---|---|
| U-UP2-1 | `build_record` 8종 | 유형별 픽스처, `fetched_at=2026-11-21T10:00+09:00` | 유형별 기대 표(테스트 안 상수): `content_type_id`, `tel`, `usetime`, `restdate`, `fee`, `event_*`가 spec §6.3·§7.1 규칙대로 |
| U-UP2-2 | 〃 tel 우선순위 | common `tel` 있음 + intro `infocenterfood` 있음(39) | common 값 |
| U-UP2-3 | 〃 fee 공백 무시 | 12, info `{"infoname":"입 장 료","infotext":"3,000원"}` | `fee == "3,000원"` (01 U-UP-8을 이 동작 포함으로 고침) |
| U-UP2-4 | 〃 fee 우선순위 | 14, intro `usefee="무료"` + info "이용요금 5,000원" | `"무료"`(intro 우선) |
| U-UP2-5 | 〃 행사 기간 | 15, `20261120`·`20261130` | `date(2026,11,20)`, `date(2026,11,30)` |
| U-UP2-6 | 〃 | 15, `20261301`·`""` | 둘 다 None, 예외 없음 |
| U-UP2-7 | 〃 코스 | 25, info `subnum` "2","1","가" | `extra["course"]` 순서 1, 2, 가 / 각 항목 `order·contentid·name·overview` |
| U-UP2-8 | 〃 객실 | 32, `roomoffseasonminfee1="0"`, `roompeakseasonminfee1="150000"`, `roomimg1="http…"` | `fee_off is None`, `fee_peak=="150000"`, 이미지 키 없음 |
| U-UP2-9 | 〃 모양 판별 | 32인데 info item에 `infoname` 있음 | `extra["info"]`로 들어감(rooms 아님) |
| U-UP2-10 | 〃 extra 형식 | 12 픽스처 | `extra["intro"]`가 **dict**(01 형식), 핵심 컬럼으로 간 필드 없음 |
| U-UP2-11 | 〃 결정성 | 같은 입력 2회 | 결과 `==` |
| U-UP2-12 | `build_stub_record` | 목록 item(서울, 39) | `detail_synced_at is None`, `extra == {}`, `as_of == 2026-11-21`, 좌표 float, `title` clean_text |
| U-UP2-13 | `insert_stub_stmt` | 컴파일 | `ON CONFLICT (contentid) DO NOTHING`, `RETURNING contentid`, 값은 바인드 |
| U-UP2-14 | `soft_delete_stmt` | 컴파일 | `SET deleted_at`, `WHERE contentid = … AND deleted_at IS NULL` |

### U-REN2 `tests/ingest/test_render_types.py` — 유형별 템플릿
| ID | 입력 | 기대 |
|---|---|---|
| U-REN2-1 | 8종 고정 `TourItem`(U-UP2-1 결과 + `updated_at` 고정) | 출력 == `tests/fixtures/wiki/entity_{유형}.md` 스냅샷(바이트 단위) — 8개 |
| U-REN2-2 | 8종 각각 `yaml.safe_load(frontmatter)` | `contentid`(문자열)·`source`·`as_of`·`updated_at` 존재(FR-42) |
| U-REN2-3 | 8종 각각 | 머리줄 `관광지 ID: <contentid>`가 본문에 **정확히 1번**, 출처 줄에 기준일, `None`·`\u` 이스케이프 없음 |
| U-REN2-4 | 15, `event_start`만 있음 | `행사 기간: 2026-11-20` 줄 |
| U-REN2-5 | 15, 둘 다 None | "행사 기간" 줄 없음 |
| U-REN2-6 | 25, course 2개 | `## 코스` 아래 `1. 경복궁 (ID 126508)` 형식, `관광지 ID:`로 시작하는 줄이 머리줄 하나뿐 |
| U-REN2-7 | 32, 객실 1개(요금 일부 None) | `## 객실` 불릿 괄호 안에 None 항목 없음, `150000` → `150,000원` |
| U-REN2-8 | 32, usetime `"입실 15:00\n퇴실 11:00"` | 기본 정보에 `입실·퇴실: 입실 15:00, 퇴실 11:00` 한 줄 |
| U-REN2-9 | 39, `extra.intro={"firstmenu":"고기국수","zz":"x"}` | 추가 정보에 `대표 메뉴: 고기국수` 다음 `zz: x` |
| U-REN2-10 | 01 형식 행(12, 01 픽스처 그대로) | 렌더 성공, 라벨 적용(예: `parking` → `주차:`) |
| U-REN2-11 | content_type_id 13 | `ValueError` |
| U-REN2-12 | 값에 줄바꿈 있는 추가 정보 | 둘째 줄부터 두 칸 들여쓰기 |
| U-REN2-13 | 같은 항목 2회 렌더 | 같은 문자열·같은 `content_hash` |
| U-REN2-14 | 템플릿 파일 | `templates/`에 `entity.md.j2` + `entity_{8종}.md.j2` 모두 존재하고 각자 `{% extends "entity.md.j2" %}` |

### U-CUR `tests/ingest/test_bootstrap_cursor.py` — 목록 커서
| ID | 대상 | 입력 | 기대 |
|---|---|---|---|
| U-CUR-1 | `cursor_key` | (`서울`, 12) | `"bootstrap:list:서울:12"` |
| U-CUR-2 | `cursor_from_value` | `None` | `next_page=1, total_count=None, done=False` |
| U-CUR-3 | `advance_cursor` | total 250, page 1, items 100 | `next_page=2`, `done=False`, `total_count=250` |
| U-CUR-4 | 〃 | total 250, page 3, items 50 | `done=True` |
| U-CUR-5 | 〃 | total 200, page 2, items 100 | `done=True`(경계) |
| U-CUR-6 | 〃 | total 0, page 1, items 0 | `done=True` |
| U-CUR-7 | 〃 | total 500, page 2, items 0 (빈 페이지) | `done=True` |
| U-CUR-8 | `pending_cells` | 16칸 중 `서울:12`·`제주:14` done | 14칸, 첫 칸 `서울:14`, 마지막 `제주:39`, 순서 고정 |
| U-CUR-9 | 〃 필터 | 옵션 areas=(`제주`,), types=(39, 12) | `제주:12` → `제주:39` (입력 순서와 무관하게 고정 순서) |
| U-CUR-10 | `relist_cursor` | done 커서 | `next_page=1, done=False`, `total_count` 유지 |

### U-Q `tests/ingest/test_bootstrap_queue.py` — 큐 조회 문
| ID | 대상 | 기대 |
|---|---|---|
| U-Q-1 | `build_queue_stmt(("서울","제주"), (12,39), {"x1"}, 20)` 컴파일 | `detail_synced_at IS NULL`, `deleted_at IS NULL`, `row_number() OVER (PARTITION BY area, content_type_id ORDER BY contentid)`, `ORDER BY rn, area, content_type_id`, `LIMIT`. 지역·유형·제외·20은 바인드 |
| U-Q-2 | 제외 집합 비어 있음 | 문 생성 성공(빈 배열 바인드), 조건이 모든 행을 거르지 않음(`NOT (contentid = ANY('{}'))`는 참) — 컴파일 문자열로 확인 |
| U-Q-3 | `build_index_queue_stmt(100, {"entity/12/1.md"})` 컴파일 | `LEFT OUTER JOIN wiki_pages`, `kind = 'entity'`(바인드), `detail_synced_at IS NOT NULL`, `deleted_at IS NULL`, `path IS NULL OR … content_hash IS NULL`, 제외 path 바인드 |

### U-LOOP `tests/ingest/test_detail_loop.py` — 예산·오류 판단 (콜백 가짜)
가짜 큐는 리스트에서 `batch_size`개씩, 제외 집합을 반영해 돌려준다. `process_item` 가짜는 항목별 결과/예외를 표로 받는다. 호출 기록으로 검증.

| ID | 상황 | 기대 |
|---|---|---|
| U-LOOP-1 | 큐 5건, 예산 넉넉, 모두 stored | `complete`, stored 5, `after_batch` 1회 이상, 마지막에 큐 조회가 빈 결과 |
| U-LOOP-2 | 큐 10건, `remaining`이 7 → 4 → 1 (항목 처리마다 3 감소) | 2건 처리 후 3번째 **시작 안 함**, `budget`, `process_item` 호출 2회 |
| U-LOOP-3 | 시작부터 `remaining` 0 | `budget`, `process_item` 0회, `after_batch` 1회 |
| U-LOOP-4 | 2번째 항목이 `BudgetExhausted`(경합) | `budget`, stored 1, `failed` 비어 있음, `record_failure` 0회 |
| U-LOOP-5 | 2번째 항목이 `TourApiError("22")` | `on_quota` 1회, `quota`, 3번째 미처리, stored 1, `after_batch` 호출됨 |
| U-LOOP-6 | 2번째 항목이 `TourApiError("23")` | `rate`, `on_quota` 0회 |
| U-LOOP-7 | 2번째 항목이 `TourApiError("timeout")`, 나머지 성공 | `complete`, stored 2, `failed == {id2: "timeout"}`, `record_failure(id2, …)` 1회, 다음 배치 조회의 제외 집합에 id2 |
| U-LOOP-8 | 큐 3건 모두 `timeout` 실패(가짜 큐는 제외 집합을 반영) | `complete`, `failed` 3건, `process_item` 항목당 정확히 1회 |
| U-LOOP-9 | `process_item`이 `ValueError`(변환 오류) | 실패 기록 후 계속 |
| U-LOOP-10 | `deleted` 반환 | deleted 카운트 +1, stored 그대로 |
| U-LOOP-11 | `max_items=3`, 큐 10건 | `max_items`, stored 3 |
| U-LOOP-12 | batch_size 2, 큐 5건 | `after_batch` 3회(2·2·1) |

### U-RUN `tests/ingest/test_bootstrap_run.py` — 결과 판정·반복·인자
| ID | 대상 | 입력 | 기대 |
|---|---|---|---|
| U-RUN-1 | `run_status(stop_reason, index_failed)` 표 | complete/budget/max_items × 실패 0 → `done`, quota/rate/error → `failed`, budget + 인덱싱 실패 1 → `failed`, index_retry → `failed` | 표대로 |
| U-RUN-2 | `exit_code(stop_reason, started_with_zero_budget=…)` | complete 0 / budget 0 / budget + 시작부터 0건 → 3 / max_items 0 / quota 1 / rate 1 / index_retry 1 / error 1. CLI가 `LockBusy`를 받으면 4 | 표대로 |
| U-RUN-3 | `next_resume_at` | 2026-11-21 14:00 KST | 2026-11-22 00:10 KST |
| U-RUN-4 | 〃 | 2026-11-21 00:05 KST | 2026-11-22 00:10 KST (같은 날 아님) |
| U-RUN-5 | 〃 | 2026-12-31 23:59 KST | 2027-01-01 00:10 KST |
| U-RUN-6 | `run_follow` | `run_once` 결과 순서 budget → budget → complete | 가짜 `sleep` 2회(각각 다음 00:10까지 초), 반환 0 |
| U-RUN-7 | 〃 | rate → rate → rate | `sleep(60)` 2회 후 3번째에서 반환 1 |
| U-RUN-8 | 〃 | rate → budget → rate → complete | 연속 횟수 초기화되어 반환 0 |
| U-RUN-9 | 〃 | quota → complete | 다음 날 대기 1회, 반환 0 |
| U-RUN-10 | 〃 | `run_once`가 예외 | 반환 1, 대기 없음 |
| U-RUN-10a | 〃 | index_retry → complete | 다음 날 대기 1회, 반환 0 |
| U-RUN-11 | 〃 | 인덱싱 실패가 있는 budget 결과 | 계속 반복(종료 안 함) |
| U-RUN-12 | `cap_errors` | 오류 60개 | `errors` 51줄(50 + `"외 10건"`) |
| U-RUN-13 | CLI 인자 | `--area 부산` / `--type 13` / `--max-items 0` / `--max-items 5 --follow` | 각각 종료 코드 2, TourAPI·DB 접근 없음 |
| U-RUN-14 | CLI 인자 | `--area 제주 --type 39 --type 12` | `BootstrapOptions(areas=("제주",), types=(12, 39))`(고정 순서로 정렬) |
| U-RUN-15 | `BootstrapResult` 직렬화 | 모든 필드 채움 | `json.dumps(asdict(r), ensure_ascii=False)` 성공, 서비스 키 문자열 없음 |

### 01 테스트 수정 (spec §10)
| 01 ID | 처리 |
|---|---|
| U-TA-12 | U-TA2-1~3으로 대체(호출 시점이 "직전") |
| U-BS-1~3 (`estimate_calls`·`budget_allows`·`validate_args`) | 함수 삭제와 함께 삭제. 인자 검증은 U-RUN-13 |
| U-UP-8 | "입 장 료" 공백 표기도 매칭되도록 기대값 갱신(U-UP2-3) |
| U-REN-1 | 01 스냅샷 `entity_126508.md`는 `entity_12.md.j2` 기준으로 다시 만든다(라벨 적용으로 "추가 정보" 줄이 바뀜) |

### 단위테스트 통과 기준
- 위 케이스 전부 + 01 테스트(수정분 포함) 전부 통과. 네트워크·DB 없이 통과.

---

## 통합 테스트 (`@pytest.mark.integration`) — `tests/integration/test_bootstrap_db.py`
전제: `compose.dev.yaml`로 postgres 기동(01 테이블 존재). 테스트 데이터는 `test-03-<uuid>` contentid, 카운터는 **미래 날짜 키**(`tourapi_calls:2099-01-01` 등 — 실제 오늘 카운터를 건드리지 않음). 끝나면 지운다.

| ID | 내용 | 기대 |
|---|---|---|
| I-1 | 동시 예약: `Budget(limit=10)`을 고정 시계(2099-01-01)로, `asyncio.gather`로 `reserve` 50회 동시 | 성공 정확히 10, `BudgetExhausted` 40, DB 값 `ingest == 10`, `ops` 합 10 |
| I-2 | `quota_hit`: 사용 3에서 `mark_quota_hit` → `reserve` | `BudgetExhausted`, 값 그대로 3 |
| I-3 | 01 형식 값(`{"ingest": 5, "live": 0}`)이 있는 키에 `reserve` | 성공, `ingest 6`, `ops == {"areaBasedList2": 1}` |
| I-4 | 껍데기 → 상세: `insert_stub_stmt` 2회(같은 contentid) | 1회째 RETURNING 1행, 2회째 0행. 이어서 `upsert_tour_item`(상세) → `updated`, `detail_synced_at` 채워짐 |
| I-5 | **(실 TourAPI, 선택 — 24호출)** `TOURAPI_LIVE=1`일 때만: DB 껍데기에서 유형별 1건씩 골라 상세 3종 호출 → `split_intro` 규칙 밖 필드·빈 핵심 컬럼 출력, raw를 픽스처 후보로 저장 | 8종 모두 호출 성공. 결과는 spec §14 "필드 이름"에 기록(실패해도 테스트는 기록만 — 판정은 사람) |
| I-6 | 큐 순서: 16칸 중 3칸에 껍데기 각 3건 | `build_queue_stmt(limit=5)` 결과가 칸을 돌아가며(rn=1 세 칸 → rn=2 두 칸) |
| I-7 | 인덱싱 대기 큐: 상세 받은 행 3개(wiki_pages 없음 1, 해시 NULL 1, 해시 있음 1) | 대기 큐에 앞의 2개만 |
| I-8 | 잠금: 연결 A가 `pg_try_advisory_lock(1)` 보유 중 `run_bootstrap` | `LockBusy`, `ingest_runs` 행 생성 안 됨 |
| I-9 | 멈춘 기록 정리: `ingest_runs`에 `bootstrap`·`running` 행 하나 넣고 실행(예산 0 고정 → 바로 종료) | 그 행 `failed`·error 문구, 새 행 `done`·`budget` |

---

## ② HITL — 사용자가 직접 실행·확인

모든 명령은 레포 루트(`~/code/myAgent`, WSL2)에서. `docker compose run --rm ingest nadri …`는 `R`로 줄여 적는다. 개발계정 한도가 하루 1,000건이라 **H-3(첫날 본 실행) 전에 쓰는 호출을 최소화**한다.

### H-0 준비
1. 01이 `dev`에 병합됐고 01 spec §10에 A12(한도 단위·`totalCount` 16칸·적재 일수)가 기록돼 있는지 확인. 한도 단위가 정해졌으면 spec Q3 결정에 반영.
2. 공공데이터포털 마이페이지 → KorService2 개발계정 트래픽 화면을 열어 둔다(오늘 사용량 기록).
3. `docker compose up -d` 후 `docker compose build ingest`(03 코드 반영).

### H-1 테스트
```bash
cd backend && uv run pytest -m "not integration" -q && \
DB_HOST=127.0.0.1 uv run pytest -m integration -q tests/integration/test_bootstrap_db.py
```
- 기대: 전부 통과. (I-5는 `TOURAPI_LIVE=1`을 줄 때만 — 24호출, 하고 싶으면 H-3 전에.)

### H-2 01 적재분 다시 렌더 (템플릿 교체)
```bash
R nadri ingest reindex
```
- 기대: 01의 50페이지가 `indexed` 50(템플릿이 바뀌어 해시가 다름), `failed` 0, LightRAG 문서 수 전후 동일. 비용은 인덱싱 50페이지분(01 측정 페이지당 비용 × 50).
- 확인: 아무 페이지 하나를 열어 "추가 정보"가 한글 라벨(예: `주차:`)로 나오는지.
```bash
docker compose run --rm ingest sh -c 'cat "$(ls -d /data/wiki/entity/12/*.md | head -1)"'
```

### H-3 첫날 본 실행 (단발)
```bash
R nadri ingest status                 # 실행 전 상태 (호출 없음)
R nadri ingest bootstrap              # 오늘 예산(800 − 오늘 이미 쓴 양)을 다 쓸 때까지
R nadri ingest status
```
- 기대
  - 진행 줄: 목록 16칸 페이지 진행 → 상세 진행 → 20건마다 인덱싱 줄.
  - 마지막 요약 JSON: `stop_reason` = `budget`(또는 데이터가 아주 적으면 `complete`), `calls ≤ 800 − 실행 전 사용량`, `calls_by_op` 합 = `calls`, `detail_failed`·`failed`(인덱싱) 0에 가까움, `estimate.days`·`estimate.date` 있음.
  - `status`: 16칸 모두 `total_count` 표시, 목록 진행 `done`(첫날에 끝나는 것이 보통 — 아니면 보고), 칸마다 상세 완료가 고르게 늘어남(돌아가며 수집), 오늘 카운터 `ingest ≤ 800`, `quota_hit false`.
- 포털 화면 사용량과 `ingest_state`의 오늘 `ingest`(+01 이후 같은 날 쓴 양)를 비교 → 같으면 셈 정확. 오퍼레이션별로 보이면 `ops`와도 비교(A12).
- 확인 SQL:
```bash
docker compose exec postgres psql -U postgres -d nadri -c "select value from ingest_state where key = 'tourapi_calls:' || to_char(now() at time zone 'Asia/Seoul','YYYY-MM-DD');"
docker compose exec postgres psql -U postgres -d nadri -c "select id, status, stats->>'stop_reason', stats->>'calls', stats->'estimate' from ingest_runs order by id desc limit 3;"
```

### H-4 끊김 후 이어하기 (DoD 2) — 다음 날 예산으로, 호출 약 30건
```bash
# 터미널 1
R nadri ingest bootstrap --max-items 30
# 터미널 2 — 터미널 1에 상세 진행 줄이 10개쯤 나오면 강제 종료
docker kill $(docker ps -q --filter "label=com.docker.compose.service=ingest")
# 터미널 1
R nadri ingest bootstrap --max-items 10
```
- 기대: 두 번째 실행 처음에 이전 실행 행이 `failed`(`중단됨 — 다음 실행에서 정리`)로 바뀜, 인덱싱 대기분(끊기기 전 저장했지만 인덱싱 못 한 페이지)부터 처리, 이어서 **새 항목**부터 상세 수집.
- 확인: 끊긴 시점의 그 1건을 빼면 raw에 같은 contentid의 `.2.json`이 없다.
```bash
docker compose run --rm ingest sh -c 'find /data/raw -name "*.2.json" | head'
```

### H-5 유형별 페이지 읽어 보기 (DoD 4)
```bash
for t in 12 14 15 25 28 32 38 39; do
  docker compose run --rm ingest sh -c "f=\$(ls /data/wiki/entity/$t/*.md 2>/dev/null | head -1); echo \"=== $t \$f\"; cat \"\$f\""
done
```
- 확인 포인트: 빈 줄·`None`·`0`/`1` 값·영어 필드명이 남았는지, 라벨이 자연스러운지, 15 행사 기간·25 코스 순서·32 객실 줄이 맞는지. 필드명이 그대로 보이는 줄이 있으면 그 이름을 알려 준다(라벨 추가 대상, `stats.unknown_intro_fields`와 같아야 함).
- 판단: 사용자 "자연스러움 / 고칠 곳 있음".

### H-6 넓은 표본 엔티티 추출 (A8)
H-5에서 본 장소 이름으로(음식점·숙박·축제·여행코스 각 1개):
```bash
R nadri lightrag sample --query "<음식점 이름>" --limit 20
R nadri lightrag sample --query "<숙박 이름>" --limit 20
R nadri lightrag sample --query "<축제 이름>" --limit 20
R nadri lightrag sample --query "<여행코스 이름>" --limit 20
```
- 확인 포인트: 01 H-6과 같음(한국어 이름, 번역·깨짐, frontmatter 키가 엔티티로 잡힘, 관계 의미). 추가로 메뉴·객실·행사 프로그램 같은 유형별 정보가 엔티티·관계로 잡히는지.
- 판단: "쓸 만함 / 미달". 미달이면 01 spec §9 A8 대안 중 선택(④ 상위 모델은 비용 확인 후).

### H-7 `usetime` 자유 텍스트 확인 ([A] §2.1 "추정")
```bash
docker compose exec postgres psql -U postgres -d nadri -c \
  "select content_type_id, left(usetime, 80) from tour_items where usetime is not null and detail_synced_at is not null order by random() limit 40;"
```
- 확인: 대부분 사람이 쓴 자유 텍스트(예: "09:00~18:00 (입장마감 17:00) / 동절기 …")인지. 결과를 spec §14에 "자유 텍스트 — 아키텍처 그대로" 또는 "정형 비율 N%"로 기록. 어느 쪽이어도 설계 변경 없음.

### H-8 첫날 보고와 운영계정 증설 여부 (DoD 7, 확인 질문 Q9)
구현자가 아래 표를 채워 사용자에게 보고한다.

| 항목 | 값 |
|---|---|
| 오늘 호출 수(합계 / 오퍼레이션별) · 포털 표시 | |
| 목록 페이지 수 · 껍데기 행 수(칸별 total_count 합) | |
| 상세 완료 · 소프트 삭제 · 실패(제외 포함) | |
| 인덱싱 indexed / failed · 인덱싱 총 시간 · 페이지당 시간 | |
| 남은 상세 큐 · 예상 남은 일수 · **예상 완료일** | |
| 전체 인덱싱 비용 추정(01 페이지당 비용 × 전체 페이지) | |
| raw·위키 볼륨 크기(`docker system df -v`에서 `raw-data`·`wiki-data`) | |
| 규칙에 없는 intro 필드(유형별) | |

- 예상 남은 일수가 **14일 초과**(Q9 추천 기준)면 사용자에게 묻는다: "운영계정 트래픽 증설을 신청할까요?" 함께 알릴 것 — 신청 조건(활용사례 등록 등)·처리 기간은 **미확인**이라 포털에서 직접 확인 필요, 신청하지 않으면 `--follow`로 계속 누적, 다른 선택지(Q9 대안: `detailInfo2`를 일부 유형만).
- 답을 `PROGRESS.md` 결정 로그에 남긴다.

### H-9 다음 날 이어짐·카운터 초기화 (A12)
```bash
R nadri ingest status        # 다음 날 00:10 이후
R nadri ingest bootstrap
```
- 기대: 새 날짜 키로 예산 800이 다시 생김, 22 없이 진행, 전날 큐에서 이어서 수집. 22가 나오면(포털 초기화 시각이 다름) 오류 메시지·시각을 기록하고 보고.

### H-10 백그라운드 누적 시작 (`--follow`, Q4)
```bash
docker compose run -d --name nadri-bootstrap ingest nadri ingest bootstrap --follow
docker logs -f nadri-bootstrap      # "다음 시작 2026-11-23 00:10" 같은 줄 확인 후 Ctrl+C (컨테이너는 계속 돎)
```
- 기대: 예산 소진 뒤 다음 시작 시각 줄을 찍고 대기. 다음 날 00:10 이후 로그에 새 실행이 이어짐.
- 동시 실행 방지 확인: 대기 중이 아닐 때(수집 중) `R nadri ingest bootstrap` → 종료 코드 4("다른 수집 작업 실행 중").
- Docker·WSL 재시작 후에는 멈춰 있다: `docker rm nadri-bootstrap` 후 같은 명령으로 다시 시작(이어서 진행).

### H-11 완료 확인 (여러 날 뒤 — G5 이후여도 됨)
```bash
R nadri ingest status
```
- 기대: 목록 16칸 `done`, 상세 큐 0, 인덱싱 대기 0, `bootstrap:completed_at` 기록, 칸별 상세 완료 수 ≈ `total_count`(차이 = 소프트 삭제 + 제외). 제외 항목이 있으면 목록과 사유를 보고. `--follow` 컨테이너는 `complete`로 종료(0).
- 이 결과를 `PROGRESS.md`에 기록하고 20(허브) 작업이 시작 가능함을 알린다.
