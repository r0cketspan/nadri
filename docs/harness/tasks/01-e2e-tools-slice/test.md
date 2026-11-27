# 01-e2e-tools-slice — 테스트 설계

> 하네스 Phase 4 산출물 (spec-writer, 2026-11-21). 대상 스펙: `spec.md`(같은 폴더). 상태: 초안 — 사용자 검토 대기.
> 두 방향을 나눈다: ① 단위테스트(pytest, 실모델·실DB·실 API 없이 결정적) ② HITL(사용자가 직접 실행·확인). 그 사이에 실 compose·실 키로 도는 **통합 테스트**(`@pytest.mark.integration`)를 둔다.

---

## 0. 실행 방법

테스트는 **WSL2 Ubuntu의 uv 가상환경**(`backend/.venv`)에서 돈다(spec §5.3a, Q4 결정).

```bash
# 최초 1회: uv 설치 후 의존 설치 (리랭커 그룹 제외)
cd backend && uv sync --no-group reranker

# 단위테스트 (외부 서비스 불필요)
uv run pytest -m "not integration" -q

# 통합 테스트 (compose.dev.yaml로 4서비스 기동·적재 완료 후, .env 실 키 필요)
DB_HOST=127.0.0.1 LIGHTRAG_URL=http://127.0.0.1:9621 TOOLS_URL=http://127.0.0.1:8001/mcp \
  uv run pytest -m integration -q
```

- 프레임워크: `pytest` + `pytest-asyncio`(`asyncio_mode=auto`), YAML 파싱 확인용 `pyyaml`(dev 그룹).
- 대역(test double) 원칙
  | 외부 | 대역 방법 |
  |---|---|
  | TourAPI | `httpx.MockTransport` — 요청(URL·쿼리)을 기록하고 `tests/fixtures/tourapi/*.json|xml` 고정 응답을 돌려줌 |
  | LightRAG HTTP | `httpx.MockTransport` — 경로별 핸들러(상태 전이를 리스트로 스크립트) |
  | CrossEncoder | `score()`만 가진 가짜 클래스(입력 순서대로 정해진 점수) |
  | DB | 단위테스트에서는 쓰지 않는다. SQL은 `stmt.compile(dialect=postgresql.dialect())`로 문자열·바인드 파라미터를 검사. DB 조회가 필요한 함수는 조회 콜백을 주입(`lookup_pages`) |
  | 시계·대기 | `datetime_info(now)`에 고정 시각, `index_pages(sleep=가짜, clock=가짜)` |
  | MCP 하위 앱 | 200 `ok`를 돌려주는 더미 ASGI 앱을 `BearerAuthMiddleware`로 감싸 `httpx.ASGITransport`로 호출 |
- 픽스처 응답은 **처음엔 TourAPI 문서 형식을 따라 손으로 만들고**(필드명 미확인), 첫 실호출 뒤 실제 raw 파일에서 1건씩 골라 **교체**한다(키 등 비밀값 없음 확인). 교체 여부를 커밋 메시지에 적는다.
- 테스트 파일은 모두 한국어 docstring(무엇을 검증하는지 한 줄).

---

## ① 단위테스트

### U-CFG `tests/core/test_config.py` — 설정
| ID | 대상 | 입력 | 기대 |
|---|---|---|---|
| U-CFG-1 | `Settings.database_url` | `DB_USER=nadri_app`, `DB_PASSWORD=p@ss:w/rd`, 기본 호스트 | `postgresql+asyncpg://nadri_app:p%40ss%3Aw%2Frd@postgres:5432/nadri` |
| U-CFG-2 | `repr(Settings)` | `TOOLS_API_KEY=secret-xyz` | 출력에 `secret-xyz` 없음 |
| U-CFG-3 | ORM COMMENT ↔ ERD | `Base.metadata`의 4테이블 | 테이블·컬럼 comment가 spec §3.2 표와 정확히 같음(기대값 표를 테스트 안에 상수로 둠 — `erd.py` AST 대조는 04) |
| U-CFG-4 | `require()` | 값 None, 이름 `TOURAPI_SERVICE_KEY` | `SystemExit(2)`, 메시지에 키 이름 포함 |

### U-TA `tests/core/test_tourapi.py` — TourAPI 클라이언트
| ID | 대상 | 입력 | 기대 |
|---|---|---|---|
| U-TA-1 | `parse_response` | 정상 JSON, `items.item` 리스트 3개, `totalCount` 120 | `(body, [3개], 120)` |
| U-TA-2 | 〃 | `items.item`이 dict 하나 | 원소 1개 리스트 |
| U-TA-3 | 〃 | `items: ""`, `totalCount: 0` | `[]`, 0 |
| U-TA-4 | 〃 | header `resultCode: "22"` | `TourApiError`, `code=="22"`, `quota_exceeded is True` |
| U-TA-5 | 〃 | XML `<OpenAPI_ServiceResponse>…<returnReasonCode>30</returnReasonCode>` | `TourApiError(code="30")` |
| U-TA-6 | 〃 | XML 코드 `23` | `rate_limited is True` |
| U-TA-7 | 〃 | HTTP 500 | `code=="http_500"` |
| U-TA-8 | 〃 | 깨진 본문 `"<html>오류"` | `code=="parse"` |
| U-TA-9 | `area_based_list("서울", 12, num_of_rows=30)` | MockTransport | 요청 쿼리에 `areaCode=1`, `contentTypeId=12`, `numOfRows=30`, `pageNo=1`, `_type=json`, `MobileOS=ETC`, `MobileApp=nadri`, `serviceKey` 존재. 경로 `/areaBasedList2` |
| U-TA-10 | `detail_intro("126508", 12)` | MockTransport | 경로 `/detailIntro2`, `contentId=126508`, `contentTypeId=12` |
| U-TA-11 | 반환값 `params` | 위 호출 | `serviceKey` 키가 없음 |
| U-TA-12 | `on_call` | 성공 1회 + 오류(22) 1회 | 콜백 2회 호출(오류도 셈), 인자는 오퍼레이션 이름 |
| U-TA-13 | 타임아웃 | MockTransport가 `httpx.ReadTimeout` 발생 | `TourApiError(code="timeout")`, 재시도 없음(요청 1회) |
| U-TA-14 | 예외 메시지 | 오류 30 | `str(err)`에 서비스 키 값이 없음 |
| U-TA-15 | 알 수 없는 지역 | `area_based_list("부산", 12, …)` | `ValueError` (HTTP 호출 없음) |

### U-RAW `tests/ingest/test_raw.py` — raw 스냅샷 (tmp_path)
| ID | 입력 | 기대 |
|---|---|---|
| U-RAW-1 | `fetched_at=2026-11-21T00:30+09:00`, op `detailCommon2`, key `126508` | 경로 `{tmp}/2026-11-21/detailCommon2/126508.json`, JSON에 `operation·params·fetched_at·body`, 한글 그대로(`ensure_ascii=False`) |
| U-RAW-2 | UTC `2026-11-20T15:30Z`(= KST 11-21 00:30) | 날짜 폴더 `2026-11-21`(KST 기준) |
| U-RAW-3 | 같은 키 두 번 저장 | 두 번째는 `126508.2.json`, 첫 파일 내용·mtime 불변 |
| U-RAW-4 | 세 번째 저장 | `126508.3.json` |
| U-RAW-5 | key `서울/12 p1` | 파일명 `서울_12_p1.json`(경로 구분자 치환, 상위 폴더 탈출 없음) |

### U-UP `tests/ingest/test_upsert.py` — 변환·upsert 문
| ID | 대상 | 입력 | 기대 |
|---|---|---|---|
| U-UP-1 | `clean_text` | `"09:00~18:00<br>입장마감 17:00"` | `"09:00~18:00\n입장마감 17:00"` |
| U-UP-2 | 〃 | `"<a href=\"http://x\">http://x</a>"` | `"http://x"` |
| U-UP-3 | 〃 | `"A &amp; B"` / `"  "` / `None` | `"A & B"` / `None` / `None` |
| U-UP-4 | `build_record` | 픽스처 common·intro·info(타입 12), `fetched_at=2026-11-21T10:00+09:00` | contentid·title·area=`서울`·`content_type_id=12`, `lat=float(mapy)`, `lng=float(mapx)`, `as_of=date(2026,11,21)`, `detail_synced_at=fetched_at`, `modifiedtime` KST 파싱 |
| U-UP-5 | 〃 | `addr2` 빈 값 | `addr == addr1`(끝 공백 없음) |
| U-UP-6 | 〃 | `mapx="0"`, `mapy=""` | `lat is None and lng is None` |
| U-UP-7 | 〃 | common `tel` 없음, intro `infocenter="02-3700-3900"` | `tel == "02-3700-3900"` |
| U-UP-8 | 〃 | info에 `{"infoname":"입 장 료"…}` 없음, `{"infoname":"이용요금","infotext":"3,000원"}` 있음 | `fee == "3,000원"` |
| U-UP-9 | 〃 | `modifiedtime="2026-11-21"`(형식 다름) | `modifiedtime is None`(예외 없음) |
| U-UP-10 | 〃 | intro에 매핑 안 된 `parking`, 빈 값 `chkpet=""` | `extra["intro"] == {"parking": …}`(빈 값 키 없음) |
| U-UP-11 | 〃 | 같은 입력 두 번 | 두 결과 `==`(결정적) |
| U-UP-12 | `build_upsert_stmt` | 레코드 1개 | 컴파일 SQL에 `ON CONFLICT (contentid) DO UPDATE`, `IS DISTINCT FROM`, `RETURNING`, `xmax` 포함. `WHERE` 비교 목록에 `detail_synced_at` **없음**, `as_of` **있음** |
| U-UP-13 | 〃 | title `"경복궁'; DROP TABLE x;--"` | 컴파일 SQL 문자열에 그 값이 없고 바인드 파라미터에 있음 |

### U-REN `tests/ingest/test_render.py` — 엔티티 렌더
| ID | 입력 | 기대 |
|---|---|---|
| U-REN-1 | 고정 `TourItem`(경복궁, 모든 필드 채움, `updated_at=2026-11-21T10:00+09:00`) | 출력 == `tests/fixtures/wiki/entity_126508.md`(스냅샷, 바이트 단위) |
| U-REN-2 | 같은 항목 2회 렌더 | 동일 문자열, `content_hash` 동일(64자 16진) |
| U-REN-3 | 출력 frontmatter를 `yaml.safe_load` | `contentid=="126508"`(문자열), `source`, `as_of`, `updated_at` 키 존재(FR-42) |
| U-REN-4 | title `경복궁: "정궁"` | frontmatter 파싱 성공, title 값 원문 그대로 |
| U-REN-5 | 한글 값 | 출력에 `\u` 이스케이프 없음 |
| U-REN-6 | tel·fee·restdate None, overview 없음 | "전화:"·"이용요금:"·"## 개요" 줄 없음, `None` 문자열 없음 |
| U-REN-7 | `sigungu_code=None` | frontmatter에 `sigungu_code` 키 없음 |
| U-REN-8 | 본문 | `관광지 ID: 126508` 줄 포함(A7 대안 근거), 마지막 출처 줄에 기준일 포함 |
| U-REN-9 | `entity_path(12, "126508")` | `"entity/12/126508.md"` |
| U-REN-10 | `write_page(tmp, "entity/12/1.md", "x")` 두 번(내용 다름) | 최종 내용 = 두 번째, 임시 파일 남지 않음, 중간 폴더 자동 생성 |
| U-REN-11 | `updated_at`만 1초 다른 항목 | 해시가 달라짐(재인덱싱 트리거 확인) — 렌더 결정성은 현재 시각과 무관 |

### U-IDX `tests/ingest/test_indexer.py` — 인덱서 (LightRAG MockTransport)
| ID | 상황 | 기대 |
|---|---|---|
| U-IDX-1 | `needs_indexing` 표: (h, h, "doc-1")→False / (h2, h, "doc-1")→True / (h, None, None)→True / (h, h, None)→True | 표대로 |
| U-IDX-2 | 해시 같은 페이지 3개 | 모두 `skipped`, **HTTP 요청 0건** |
| U-IDX-3 | 새 페이지(old 없음) 1개, track 상태 `processing`→`processed`(doc_id `doc-new`) | 요청 순서 insert → track_status ×2, 결과 `indexed`, `doc_id=="doc-new"`, `content_hash` = 새 해시, 가짜 `sleep`이 `poll_interval_s`로 호출됨 |
| U-IDX-4 | 바뀐 페이지(old_doc_id `doc-old`) | 요청 순서 **delete(doc-old) → exists 확인(False) → insert → track** (delete가 insert보다 먼저) |
| U-IDX-5 | delete 응답 500 | `failed`, reason에 "삭제", **insert 요청 없음** |
| U-IDX-6 | 삭제 후 exists가 계속 True → 타임아웃 | `failed("delete_timeout")`, insert 없음 |
| U-IDX-7 | track 상태 `failed`, error "llm error" | `failed`, reason 포함 |
| U-IDX-8 | track이 끝나지 않음, 가짜 clock이 `timeout_s` 넘김 | 남은 페이지 전부 `failed("timeout")` |
| U-IDX-9 | 모든 요청 | 헤더 `X-API-Key`(값 = 주입한 키) 존재(v1.5.7 `utils_api.py`에서 이름 확인) |
| U-IDX-10 | insert 본문 | `file_source == to_file_source(page.path)`(`/`→`__`, LightRAG가 basename만 남기기 때문 — spec §6.6), `text == page.text` |
| U-IDX-12 | insert 409 "already contains"(이전 실패 잔여 문서) | 같은 file_source 문서 찾기 → delete → 사라짐 확인 → insert 재시도 → `indexed` |
| U-IDX-11 | `outcome_to_values(o, now)` | indexed → `{content_hash, lightrag_doc_id, indexed_at}` 채움 / failed → 셋 다 None / skipped → 변경 없음(None 반환) |

### U-BS `tests/ingest/test_bootstrap.py` — 적재 보조 함수
| ID | 대상 | 입력 | 기대 |
|---|---|---|---|
| U-BS-1 | `estimate_calls` | 30 / 20 / 1 | 91 / 61 / 4 |
| U-BS-2 | `budget_allows` | (0, 91, 800) / (710, 91, 800) / (709, 91, 800) | True / False / True |
| U-BS-3 | `validate_args` | area `부산` / type 14 / limit 0 / limit 51 | 각각 `ValueError`, TourAPI 호출 0건 |
| U-BS-4 | `count_totals` | MockTransport가 지역·유형별 totalCount 반환 | 16칸 dict, 요청 16회, 모두 `numOfRows=1` |
| U-BS-5 | `estimate_days` | 16칸 중 한 칸 3,000·나머지 0, 예산 800, 목록 100건/호출 | 서비스 전체 한도 `ceil((30 + 9000)/800)=12`, 오퍼레이션별 `ceil(3000/800)=4` |
> `run_bootstrap` 전체 흐름(DB·파일·LightRAG 연결)은 통합 테스트 I-4로 확인한다 — 단위에서 DB를 흉내 내는 큰 가짜를 만들지 않는다(단순함 우선).

### U-AUTH `tests/tools/test_auth.py` — MCP 인증 미들웨어
더미 앱(200 `ok`)을 `BearerAuthMiddleware(app, token="t0k")`로 감싸 `httpx.AsyncClient(transport=ASGITransport(...))`로 호출.
| ID | 요청 | 기대 |
|---|---|---|
| U-AUTH-1 | `POST /mcp` 헤더 없음 | 401, 본문 `{"error":"unauthorized"}`, 더미 앱 호출 안 됨 |
| U-AUTH-2 | `Authorization: Bearer wrong` | 401, 본문 U-AUTH-1과 동일 |
| U-AUTH-3 | `Authorization: t0k`(접두어 없음) | 401 |
| U-AUTH-4 | `Authorization: bearer t0k`(소문자) | 401 (정확히 `Bearer `만 허용 — 단순 규칙) |
| U-AUTH-5 | `Authorization: Bearer t0k` | 200 `ok` |
| U-AUTH-6 | `GET /health` 헤더 없음 | 200 `ok`, 더미 앱 호출 안 됨 |
| U-AUTH-7 | `POST /health` 헤더 없음 | 401 (예외는 GET만) |
| U-AUTH-8 | `lifespan` 스코프 | 더미 앱으로 그대로 전달 |
| U-AUTH-9 | `build_app`에 빈 토큰 | 기동 거부(예외) |

### U-DQ `tests/tools/test_data_query.py` — 정형 조회
| ID | 대상 | 입력 | 기대 |
|---|---|---|---|
| U-DQ-1 | `DataQueryParams` | `area="부산"` | 검증 오류 |
| U-DQ-2 | 〃 | `limit=0` | 검증 오류 |
| U-DQ-3 | 〃 | `limit=100` | `limit == 20` |
| U-DQ-4 | 〃 | `sort="distance"`, near 없음 | 검증 오류 |
| U-DQ-5 | 〃 | `near.radius_km=25` / `0` | 검증 오류 |
| U-DQ-6 | 〃 | `keyword="   "` | `keyword is None` |
| U-DQ-7 | 〃 | `content_type=13` | 검증 오류 |
| U-DQ-8 | 〃 | `sigungu_code="1; DROP"` | 검증 오류 |
| U-DQ-9 | `escape_like` | `"50%_할인\\"` | `"50\\%\\_할인\\\\"` |
| U-DQ-10 | `build_select` | `{area:"서울"}` | SQL에 `deleted_at IS NULL`, `area = %(…)s`, `ORDER BY title, contentid`, `LIMIT`; 바인드 `서울`, 10 |
| U-DQ-11 | 〃 | keyword `"궁' OR 1=1 --"` | 컴파일 SQL 문자열에 `OR 1=1` 없음, 바인드 값에 `%궁' OR 1=1 --%`, `ILIKE`·`ESCAPE` 포함 |
| U-DQ-12 | 〃 | `content_type=12, sigungu_code="23"` | 두 조건 모두 바인드로 포함 |
| U-DQ-13 | 〃 | `on_date=2026-11-21` | `event_start <=`·`event_end >=` 조건 |
| U-DQ-14 | 〃 | `sort="modified"` | `ORDER BY modifiedtime DESC NULLS LAST, contentid` |
| U-DQ-15 | 〃 | near 있음 | `lat IS NOT NULL`, bounding box 4조건, `LIMIT 500` |
| U-DQ-16 | `haversine_km` | 서울시청(37.5663,126.9779) ↔ 경복궁(37.5796,126.9770) | 1.48 ± 0.02 km |
| U-DQ-17 | 〃 | 서울(37.5665,126.9780) ↔ 제주시(33.4996,126.5312) | 454.0 ± 1.0 km |
| U-DQ-18 | 〃 | 같은 점 | 0.0 |
| U-DQ-19 | `bounding_box(37.5663,126.9779,3)` | — | U-DQ-16의 경복궁 좌표가 상자 안, (37.62,126.98)은 상자 밖 |
| U-DQ-20 | `apply_near` | 행 4개(0.5·2.9·3.1km·좌표 None 제외 상태), radius 3, 거리순, limit 10 | 0.5·2.9 두 개, 거리 오름차순, `distance_km` 소수 2자리 |
| U-DQ-21 | 〃 | 같은 입력, `sort_by_distance=False`, limit 1 | 입력 순서 유지 1개 |
| U-DQ-22 | 결과 항목 변환(`row_to_item`) | DB 행 dict | 키 집합 = spec §6.8 목록 + `source`, `extra` 없음, 날짜는 ISO 문자열 |

### U-DT `tests/tools/test_get_datetime.py` — 날짜 해석 (고정 시각)
| ID | now (KST) | 기대 |
|---|---|---|
| U-DT-1 | 2026-11-18 14:00 (수) | weekday `수요일`, 이번 주말 11-21~11-22, 다음 주 11-23~11-29 |
| U-DT-2 | 2026-11-21 09:00 (토) | 이번 주말 11-21~11-22, 다음 주 11-23~11-29 |
| U-DT-3 | 2026-11-22 23:59 (일) | 이번 주말 **11-21~11-22**, 다음 주 11-23~11-29 |
| U-DT-4 | 2026-11-23 00:00 (월) | 이번 주말 11-28~11-29, 다음 주 11-30~12-06 |
| U-DT-5 | 2026-12-31 12:00 (목) | 이번 주말 2027-01-02~01-03, 다음 주 2027-01-04~01-10 |
| U-DT-6 | UTC 2026-11-20T15:30Z | KST 변환 → date 2026-11-21, `토요일` |
| U-DT-7 | naive `datetime(2026,11,21)` | `ValueError` |
| U-DT-8 | 출력 형식 | `now`가 `+09:00`으로 끝남, `timezone=="Asia/Seoul"`, `source`·`as_of` 존재 |

### U-RAG `tests/tools/test_rag_query.py` — rag_query (LightRAG MockTransport + 가짜 리랭커 + 가짜 lookup)
| ID | 대상·상황 | 기대 |
|---|---|---|
| U-RAG-1 | `parse_query_data` — 픽스처(청크 3개, `file_path`·`content`·`chunk_id`) | `Candidate` 3개, 순서 유지 (픽스처 형식은 A7 확인 후 실제 응답으로 교체) |
| U-RAG-2 | 〃 — `data`에 청크 키 없음 | `LightRagError` |
| U-RAG-3 | `top_k_indices([0.1,0.9,0.5,0.9], 2)` | `[1, 3]`(동점은 원래 순서) |
| U-RAG-4 | `top_k_indices([0.3], 5)` | `[0]` |
| U-RAG-5 | `rag_query` 정상 — 후보 7개, 가짜 점수, lookup이 7개 모두 메타 반환 | items 5개, 점수 내림차순, 각 항목 `contentid`·`source`·`as_of`·`path`·`score`·`text` 비어 있지 않음, `count==5` |
| U-RAG-6 | 요청 본문 | `mode=="mix"`, 후보 수 = 설정값 30, 헤더 `X-API-Key` |
| U-RAG-7 | 후보 0개 | `{"items": [], "count": 0}`, 가짜 리랭커 `score` 호출 0회 |
| U-RAG-8 | 상위 5개 중 1개의 path가 lookup 결과에 없음 | 항목 4개(다시 채우지 않음) |
| U-RAG-9 | LightRAG 500 / 타임아웃 | 예외, 메시지 "지식 검색을 할 수 없습니다", 메시지에 내부 URL·키 없음 |
| U-RAG-10 | question `""` / 공백 / 501자 | `ValueError`, HTTP 호출 0건 |
| U-RAG-11 | `rerank`가 이벤트 루프를 막지 않음 | 가짜 `score`가 `asyncio.to_thread` 경유로 호출됨(monkeypatch로 확인) |
| U-RAG-12 | 로그 | `caplog`에 `tool=rag_query`, `candidates=7`, `rerank_ms=` 포함, 질문 원문 없음 |

### 단위테스트 통과 기준
- 위 케이스 전부 통과, 네트워크 차단 상태(테스트 서비스에 외부 접속 불필요)에서도 통과.
- `sentence_transformers`·`torch` 없이 수집·실행 가능(리랭커는 지연 import — `--no-group reranker` 환경).

---

## 통합 테스트 (`@pytest.mark.integration`, 실 compose + 실 키)
전제: `docker compose up -d` 완료, 서울 30 + 제주 20 적재 완료(HITL H-5). 비용: LightRAG 질의 몇 번 + 테스트 페이지 1개 인덱싱(수 센트 이하 추정, **미확인**).

| ID | 내용 | 기대 |
|---|---|---|
| I-1 | 버전 | `importlib.metadata.version("mcp") == "1.30.0"`, `langchain-mcp-adapters == "0.3.2"` (A21) |
| I-2 | 어댑터 툴 목록 | `MultiServerMCPClient`(headers 포함) `get_tools()` 이름 집합 == {`rag_query`,`data_query`,`get_datetime`}, 각 입력 스키마 존재 |
| I-3 | 어댑터 호출 | `rag_query("경복궁 관람 시간")` → items 1~5개, 각 `contentid`가 `tour_items`에 존재, `source`·`as_of` 비어 있지 않음 / `data_query({"area":"제주","limit":30})` → 20개 이하·전부 area 제주 / `get_datetime()` → 오늘 KST 날짜 |
| I-4 | 인증 | `httpx.post(TOOLS_URL)` 헤더 없음 401, 틀린 토큰 401, `GET /health` 200 |
| I-5 | 롤 권한 | `nadri_tools`로 접속: `SELECT count(*) FROM tour_items` 성공, `SELECT * FROM ingest_runs` → 권한 오류, `INSERT INTO tour_items …` → 권한 오류, `lightrag` DB 접속 실패 |
| I-6 | COMMENT | `nadri_app`으로 `obj_description`·`col_description` 조회 → spec §3.2 표와 일치 |
| I-7 | upsert 멱등(실DB) | 테스트용 contentid `test-01-<uuid>`: 첫 upsert `inserted` → 같은 레코드 `unchanged`(updated_at 불변) → usetime 변경 `updated`. 종료 시 삭제 |
| I-8 | 인덱서 왕복(실 LightRAG) | 테스트 페이지 `entity/test/<uuid>.md`: 인덱싱 `indexed`·doc_id A → 같은 내용 `skipped`(요청 0) → 내용 변경 `indexed`·doc_id B≠A, `document_exists(A)` False, 문서 수 전후 동일(A16). 종료 시 B 삭제 |
| I-9 | 테이블 생성 스크립트 되돌리기·재적용 | 별도 임시 DB가 없으므로 **수동 HITL H-3로 대체**(downgrade가 실데이터를 지우므로 자동화하지 않음) |

---

## ② HITL — 사용자가 직접 실행·확인

모든 명령은 레포 루트(`~/code/myAgent`, WSL2)에서. `docker compose run --rm ingest nadri …`는 `R`로 줄여 적는다.

### H-0 준비
0. WSL2 Ubuntu에 uv 설치(`curl -LsSf https://astral.sh/uv/install.sh | sh`) → `uv --version` 확인.
1. `cp .env.example .env` → `OPENAI_API_KEY`, `TOURAPI_SERVICE_KEY`(Decoding 키) 입력. 나머지 6개는 `openssl rand -hex 32`로 채움.
2. OpenAI 대시보드 Usage에서 오늘 사용액을 적어 둔다(인덱싱 비용 측정 기준점).
3. 공공데이터포털 마이페이지에서 KorService2 개발계정 트래픽 화면을 열어 현재 사용량을 적어 둔다(A12).

### H-1 빌드
```bash
docker compose build
docker image ls | grep nadri
```
- 확인: 빌드 성공, tools 이미지 크기 기록(가중치 포함 수 GB 예상), app 이미지 크기 기록.
- 기대: tools 빌드 로그에 리랭커 가중치 내려받기 1회, CUDA 관련 휠 없음.

### H-2 기동·포트
```bash
docker compose up -d
docker compose ps -a
docker compose logs ingest
```
- 기대: postgres `healthy`, lightrag `running`, tour-tools `healthy`, ingest `Exited (0)`. `PORTS` 열이 모두 비어 있음. ingest 로그에 `Running upgrade -> 0001_tour_ingest`.

### H-3 DB 확인
```bash
docker compose exec postgres psql -U postgres -d nadri -c "\dt+"
docker compose exec postgres psql -U postgres -d nadri -c "\d+ tour_items"
docker compose exec -e PGPASSWORD="$(grep ^TOOLS_DB_PASSWORD .env | cut -d= -f2)" postgres \
  psql -h localhost -U nadri_tools -d nadri -c "select count(*) from ingest_runs"
```
- 기대: 테이블 4개와 설명(관광 정보·위키 페이지·수집 실행 이력·수집 상태), 컬럼 설명 열이 spec §3.2와 같음. 마지막 명령은 `permission denied for table ingest_runs`.
- (선택) 테이블 생성 스크립트 되돌리기·재적용: `R alembic downgrade base` → `\dt` 비어 있음 → `R alembic upgrade head` → 복원. **적재 전에만** 한다.

### H-4 totalCount (A12)
```bash
R nadri ingest count
```
- 기대: 서울·제주 × 8종 16칸 표, 합계, 적재 일수 두 가지(서비스 전체 한도 / 오퍼레이션별 한도). 16호출 사용.
- 확인 포인트: 숫자가 0인 칸이 있으면 지역 코드 체계 문제(미확인 항목) — 보고.

### H-5 실적재 (G4 Q9)
```bash
R nadri ingest bootstrap --area 서울 --type 12 --limit 30
R nadri ingest bootstrap --area 제주 --type 12 --limit 20
```
- 기대: 진행 줄 50개, 마지막 요약 JSON에 `calls` 91·61, `upserted.inserted` 30·20, `indexed` 30·20, `failed` 0, `index_elapsed_s` 기록.
- 확인:
  ```bash
  docker compose run --rm ingest sh -c 'find /data/raw -type f | wc -l; ls /data/wiki/entity/12 | wc -l; cat "$(ls -d /data/wiki/entity/12/*.md | head -1)"'
  docker compose exec postgres psql -U postgres -d nadri -c \
    "select count(*), count(content_hash), count(lightrag_doc_id) from wiki_pages; select kind,status,stats->>'calls' from ingest_runs; select * from ingest_state;"
  ```
  기대: raw 파일 152개, 위키 50개, 페이지 내용이 사람이 읽기에 자연스러움(빈 줄·`None` 없음, 출처 줄 있음), `wiki_pages` 50/50/50, `ingest_runs` 2행 `done`, `tourapi_calls:<오늘>`의 `ingest` = 152(+H-4의 16 = 168).
- 포털 트래픽 화면 사용량 증가분이 168과 같은지, 오퍼레이션별로 따로 세는지 확인(A12 한도 단위).
- 다음 날 OpenAI Usage 증가분 기록 → 페이지당 비용 → 전체 추정(spec §9 식).

### H-6 한국어 엔티티 추출 (A8)
```bash
R nadri lightrag sample --query "경복궁" --limit 20
R nadri lightrag sample --query "성산일출봉" --limit 20
R nadri lightrag sample --query "한라산" --limit 20
```
(표본에 해당 장소가 없으면 H-5 출력에 나온 이름으로 바꾼다 — 확인 질문 Q8.)
- 확인 포인트: 엔티티 이름이 한국어로 올바른지, 영어로 번역되거나 깨진 이름이 있는지, `source`·`as_of`·`contentid` 같은 frontmatter 키가 엔티티로 잡혔는지, 관계 설명이 맞는지.
- 판단: 사용자가 "쓸 만함 / 미달" 결정. 미달이면 spec §9 A8 대안 중 선택(④ 상위 모델은 비용 확인).

### H-7 MCP 툴 호출 (A21·A7)
```bash
R nadri tools smoke
R nadri tools smoke --question "제주에서 바다 보이는 산책 코스"
```
- 기대: 툴 3종 목록, 각 호출 성공·소요 ms. `rag_query` 항목 ≤ 5개, 각 항목에 `contentid`·`source`·`as_of`·`path`. `data_query` 결과 area 일치. `get_datetime` 오늘 날짜·이번 주말 범위가 달력과 맞음.
- 확인 포인트: rag_query 상위 결과가 질문과 관련 있어 보이는지(리랭커 동작 감각), 같은 장소 청크가 중복으로 여러 번 나오는지(A7 기록).

### H-8 인증 401 (A21)
```bash
docker compose run --rm ingest python -c "import httpx;print(httpx.post('http://tour-tools:8000/mcp').status_code, httpx.post('http://tour-tools:8000/mcp', headers={'Authorization':'Bearer wrong'}).status_code)"
```
- 기대: `401 401`.

### H-9 리랭커 지연 (A9)
```bash
R nadri tools smoke --repeat 10
docker compose logs tour-tools | grep "tool=rag_query" | tail -10
docker compose exec tour-tools sh -c 'nproc; grep -m1 "model name" /proc/cpuinfo'
```
- 기대: 10줄의 `candidates`·`lightrag_ms`·`rerank_ms`·`total_ms`. 첫 줄 제외 p50·p95 계산(구현자가 smoke 출력에 요약 표시).
- 판단: p95 ≤ 2.0초 통과(Q3). 2~5초면 `RERANKER_MAX_LENGTH=256`, `RAG_CANDIDATES=20`으로 compose 환경변수만 바꿔 `docker compose up -d tour-tools` 후 재측정. 그래도 넘으면 사용자 결정(ONNX·끔·GPU).
- 후보가 30보다 적으면(위키 50페이지라 가능) 구현자가 30쌍 직접 측정값을 따로 보고.

### H-10 재인덱싱 멱등·갱신 (A16)
```bash
R nadri ingest reindex                                  # 1) 전부 skipped, LightRAG 문서 수 전후 동일
docker compose exec postgres psql -U postgres -d nadri -c \
  "update tour_items set usetime = usetime || ' (테스트 변경)' where contentid = '<H-5에서 고른 ID>'"
R nadri ingest reindex --contentid <ID>                 # 2) 1개 indexed, 이전 doc 삭제 확인, 문서 수 동일
R nadri tools smoke --question "<그 장소 이름> 이용시간"   # 3) 결과 text에 '(테스트 변경)' 포함
docker compose exec postgres psql -U postgres -d nadri -c \
  "update tour_items set usetime = replace(usetime, ' (테스트 변경)', '') where contentid = '<ID>'"
R nadri ingest reindex --contentid <ID>                 # 4) 원복
```
- 기대: 1) `skipped=50`, `indexed=0`, 문서 수 before == after. 2) `indexed=1`, 출력에 이전 doc_id 삭제 확인, 문서 수 동일. 3) 변경 문구가 검색 결과에 보임. 4) 원복.
- 주의: 2)~4)는 LightRAG 인덱싱 비용이 페이지 2개분 든다.

### H-11 개발 덮어쓰기
```bash
docker compose -f compose.yaml -f compose.dev.yaml up -d tour-tools
# backend/src/nadri/tools/get_datetime.py 툴 설명 한 글자 수정 후
docker compose logs -f tour-tools   # 재시작 로그 확인 후 되돌림
```
- 기대: 파일 저장 후 uvicorn 재시작 로그. 호스트 포트는 여전히 없음.

### H-12 테스트 실행
```bash
cd backend
uv run pytest -m "not integration" -q
DB_HOST=127.0.0.1 LIGHTRAG_URL=http://127.0.0.1:9621 TOOLS_URL=http://127.0.0.1:8001/mcp uv run pytest -m integration -q
```
- 기대: 둘 다 전부 통과. `git status`에 `.venv`·`__pycache__`·`.pytest_cache`가 보이지 않음(`.gitignore` 대상).

### HITL 보고 양식 (구현자가 사용자에게)
| 항목 | 값 |
|---|---|
| 이미지 크기 app / tools | |
| totalCount 16칸 합계, 적재 일수(두 가지) | |
| 실적재 호출 수 / 포털 표시 / 한도 단위 | |
| 인덱싱 시간(페이지당·전체 추정) | |
| 인덱싱 비용(페이지당·전체 추정, 기존 $15~30 대비) | |
| A8 엔티티·관계 샘플(질의 3개) + 사용자 판단 | |
| rerank_ms p50 / p95, 후보 수, CPU | |
| A7 응답 필드·file_path 매핑률·후보 수 조절 | |
| A16 절차 결과 | |
| A21 버전·401 결과 | |
