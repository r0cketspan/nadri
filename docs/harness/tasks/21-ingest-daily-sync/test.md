# 21-ingest-daily-sync — 테스트 설계 (test)

> spec.md와 짝. 절 번호 §n은 spec.md 기준. 작성 2026-11-22. 상태: **확정(2026-11-22)**.
> ① pytest — 단위(DB·네트워크 없음, 결정적) + DB(04 테스트 컨테이너, 마커 `db`) + 통합(실 TourAPI, 마커 `integration`, 선택) ② HITL(사용자가 직접).
> 확인 질문(21-Q1·Q2·Q5·Q8 등)이 추천안과 다르게 정해지면 해당 표의 기대값을 그 결정에 맞춰 고친다.

---

## ① pytest

### 0. 공통
- 실행(WSL2 Ubuntu, `backend/.venv`):
  ```bash
  cd ~/code/myAgent/backend
  uv run pytest -m "not integration" -q                       # 단위 + DB (Docker 필요)
  uv run pytest -m "not integration and not db" -q            # DB 없이 빠르게
  TOURAPI_LIVE=1 uv run pytest -m integration -q tests/integration/test_sync_live.py   # 실 TourAPI 2호출(선택)
  ```
- 프레임워크: `pytest` + `pytest-asyncio`(`asyncio_mode=auto`) — 새 dev 의존 없음. 새 런타임 의존 `apscheduler==3.11.*`.
- 대역(test double)
  | 외부 | 대역 |
  |---|---|
  | TourAPI | `httpx.MockTransport`([01] 방식). SyncList 픽스처 `tests/fixtures/tourapi/sync_{서울,제주}_p{n}.json`(처음엔 spec §7.1 추정 필드로 손으로 만들고, I-1 뒤 실제 raw로 교체 — 키 없음 확인) |
  | 예산 | [03] `FakeBudget`(남은 수 스크립트) 또는 DB 테스트에서는 실제 `Budget`(미래 날짜 키 `tourapi_calls:2099-…`) |
  | LightRAG | `FakeLightRag`: `insert_text`·`track_status`·`delete_documents`·`document_exists` 호출 기록, 문서 집합을 메모리로 유지, 실패·지연을 스크립트로 |
  | 20 함수 | `FakeHubs`(`HubsPort` 구현, spec §9): `affected(ids)`·`missing()` → 스크립트한 키 집합, `write(keys)` 인자 기록·결과(`{"written":…,"failed":…,"index_failed":…}`)/예외, `lint(run_id)` → `"lint: error 0 · warning 2"`, `commit(msg)` → `("abc123", 3)` 또는 `(None, 0)`. DB 테스트에서 20 실제 함수를 쓰는 경우는 20 병합 뒤 D-SY-16b |
  | 12 무효화 | 실제 함수(DB 테스트) / 단위에서는 콜백 기록 |
  | 시계·대기 | 고정 tz-aware 시각(`datetime(2026,11,22,1,0,tzinfo=KST)`), 가짜 `sleep` |
- DB 픽스처: [04] §7 `pg_container`·`db_sf`·`super_engine`. [04] `db_engine`은 앱 테이블 14개만 비우므로 이 작업 테스트 파일에 `ingest_tables_clean` 픽스처를 둔다 — 테스트 시작 전 `super_engine`으로 `TRUNCATE tour_items, wiki_pages, ingest_runs, ingest_state RESTART IDENTITY CASCADE`.
- 헬퍼(`tests/helpers/ingest.py`):
  | 이름 | 역할 |
  |---|---|
  | `make_item(db_sf, contentid, *, type=12, area="서울", sigungu="23", detail_at=…, deleted_at=None)` | `tour_items` 행 |
  | `make_page(db_sf, contentid, *, kind="entity", hash="h1", doc_id="doc-1", area=…, sigungu=…)` | `wiki_pages` 행(경로는 [01] `entity_path`) |
  | `sync_item(contentid, *, type=12, modified="20261121100000", showflag="1")` | SyncList item dict |
  | `at(days_ago, *, base=NOW)` | `NOW - timedelta(days=days_ago)` |
  | 04·05·09·12·13 헬퍼 | `make_user`·`make_session(db_sf, user_id, turns=…)`·`make_faq`·피드백 행 직접 삽입 |
- 테스트 함수마다 한국어 docstring 한 줄.

### 1. 스케줄러 (DB 없음) — `tests/ingest/test_scheduler.py`
| ID | 대상 | 입력 | 기대 |
|---|---|---|---|
| U-SC-1 | `build_scheduler([JobSpec("daily_sync", time(1,0), run)])` | — | 작업 1개, 트리거 `CronTrigger` hour=1 minute=0, 시간대 `Asia/Seoul`, `coalesce=True`, `max_instances=1`, `misfire_grace_time=3600`. 시작하지 않은 상태 |
| U-SC-2 | 〃 다음 실행 시각 | 트리거에 `now=2026-11-22 00:30 KST` | `2026-11-22 01:00 KST` |
| U-SC-3 | 〃 | `now=2026-11-22 01:00:01 KST` | `2026-11-23 01:00 KST` |
| U-SC-4 | 〃 UTC 기준 시계 | `now=2026-11-21T16:30Z`(= 11-22 01:30 KST) | `2026-11-23 01:00 KST`(= `2026-11-22T16:00Z`) |
| U-SC-5 | `needs_catch_up` | 마지막 시작 `11-21 01:00`, now `11-22 09:00` KST | True |
| U-SC-6 | 〃 | 마지막 `11-22 01:00:03`, now `11-22 09:00` | False |
| U-SC-7 | 〃 | 마지막 `11-21 01:00`, now `11-22 00:59` | False(곧 정시 실행) |
| U-SC-8 | 〃 | 마지막 None, now `11-22 09:00` | True |
| U-SC-9 | 〃 | 마지막 None, now `11-22 00:30` | False |
| U-SC-10 | 〃 naive 시각 | — | `ValueError` |
| U-SC-11 | `default_jobs` | 가짜 settings·sf | id 목록 `["daily_sync"]`, 시각 01:00, `catch_up` 있음 |
| U-SC-12 | `serve` | `stop` 이벤트를 0.1초 뒤 set, 가짜 `catch_up`=True, 가짜 `run`(호출 기록), 임시 `READY_FILE` 경로(monkeypatch) | 준비 파일 생김, 따라잡기 `run` 1회 호출, 종료 후 스케줄러 종료 |
| U-SC-13 | 작업 래퍼 | `run`이 `RuntimeError("x")` / `LockBusy` | 예외 밖으로 안 나감. ERROR 로그 1줄 `x` / INFO `daily_sync skipped: lock busy`(caplog) |
| U-SC-14 | `serve` 키 없음 | settings에 `TOURAPI_SERVICE_KEY` None | `serve`는 정상 시작(준비 파일 생김) — 키 점검은 작업 실행 때 |

### 2. TourAPI SyncList (DB 없음) — `tests/core/test_tourapi_sync.py`
| ID | 대상 | 입력 | 기대 |
|---|---|---|---|
| U-TS-1 | `area_based_sync_list("서울", num_of_rows=100, page_no=2)` | MockTransport가 요청 기록 | 경로 끝 `areaBasedSyncList2`, 쿼리에 `areaCode=1`(01 `AREAS`), `numOfRows=100`, `pageNo=2`, `arrange=C`, `_type=json`, `contentTypeId` **없음**. `resp.params`에 `serviceKey` 없음 |
| U-TS-2 | `on_call` 순서 | `on_call`이 `BudgetExhausted` | 요청이 나가지 않음(MockTransport 호출 0), 예외 전파, `on_call` 인자 `"areaBasedSyncList2"` |
| U-TS-3 | 오류 22 응답 | resultCode `22` | `TourApiError.quota_exceeded` True |
| U-TS-4 | `parse_sync_item` | `sync_item("126508", modified="20261121103000", showflag="0")` | `content_type_id=12`, `modifiedtime=2026-11-21 10:30 KST`(tz-aware), `showflag="0"`, `raw`가 원본 dict |
| U-TS-5 | 〃 | `modifiedtime` 없음 / `"2026-11-21"`(형식 다름) | `modifiedtime is None`(예외 없음) |
| U-TS-6 | 〃 | `contentid` 없음 / `contenttypeid` 없음 | `ValueError` |

### 3. 현행화 순수 함수 (DB 없음) — `tests/ingest/test_sync_pure.py`
`T = 2026-11-20 01:00 KST`(기준 시각), `TH = T − 1일`.

| ID | 대상 | 입력 | 기대 |
|---|---|---|---|
| U-SY-1 | `sync_since` | 커서 `{"since": T}`, 첫 적재 시각 있음 | `T`(커서 우선) |
| U-SY-2 | 〃 | 커서 None, 첫 적재 `2026-11-01 00:10` | `2026-11-01 00:10` |
| U-SY-3 | 〃 | 둘 다 None | None |
| U-SY-4 | `scan_page` | 수정 시각 [T+5h, T, TH](최신순) , threshold TH | 고른 것 3개(TH와 **같으면 고름**), 멈춤 False |
| U-SY-5 | 〃 | [T, TH−1초, TH−2h] | 고른 것 1개, 멈춤 True |
| U-SY-6 | 〃 | [None, TH−1h] | 고른 것 1개(None 항목), 멈춤 True |
| U-SY-7 | 〃 | [None, None] | 2개, 멈춤 False |
| U-SY-8 | 〃 | 빈 목록 | ([], False) |
| U-SY-9 | `classify` 규칙 표 (파라미터화, spec §7.3) | ① 유형 76 ② showflag 0 + 행(삭제 안 됨) ③ showflag 0 + 행 없음 ④ showflag 0 + 이미 삭제 ⑤ 행 없음 ⑥ 행 삭제됨 + showflag 1 ⑦ `detail_synced_at=T+1h`, 수정 `T` ⑧ `detail_synced_at=T`, 수정 `T`(같음) ⑨ `detail_synced_at=T−1h`, 수정 `T` ⑩ `detail_synced_at=None`(껍데기) ⑪ `detail_synced_at=T`, 수정 None | ① ignore ② delete ③ ignore ④ ignore ⑤ new ⑥ changed ⑦ fresh ⑧ fresh ⑨ changed ⑩ changed ⑪ changed |
| U-SY-10 | `prune_pending` | 대기 {A,B,C,D,E}, rows: A 상세 완료, B NULL, C 행 없음, D NULL, E NULL / failures: D attempts 3, E attempts 2 | 남은 목록 {B, E}, 실패 제외 [D] |
| U-SY-13 | `final_status` | steps 모두 ok, 실패 0 / `hubs` failed / ok인데 `index_failed=1` / ok인데 `removal_failed=1` / `list` skipped만 | done / failed / failed / failed / done |
| U-SY-14 | `summary_line` | `SyncResult` 예시 | 숫자 필드·`steps` 상태만, `errors`·`lint` 본문 없음 |
| U-SY-15 | 문 컴파일 `build_pending_batch_stmt(["1","2"], {"2"}, 20)` | postgresql 방언 | `ANY`·`NOT (… ANY)`·`LIMIT`, `deleted_at` 조건 **없음**, 값은 바인드 |
| U-SY-16 | 문 컴파일 `build_removal_queue_stmt()` | — | `kind = 'entity'`, `deleted_at IS NOT NULL`, `ORDER BY w.path` |

### 4. 정리 규칙 순수 부분 (DB 없음) — `tests/ingest/test_cleanup_pure.py`
| ID | 대상 | 입력 | 기대 |
|---|---|---|---|
| U-CL-1 | `cutoffs` | now `2026-11-22 01:00 KST` | `ts_cut = 2026-08-24 01:00 KST`, `date_cut = 2026-08-24`, `rate_cut = 2026-11-21 01:00 KST` |
| U-CL-2 | 〃 | now `2026-11-21T16:30Z`(KST 11-22 01:30) | `date_cut = 2026-08-24`(KST 날짜 기준) |
| U-CL-3 | 〃 | naive | `ValueError` |
| U-CL-4 | `build_cleanup_stmts` | Cutoffs | 키 순서 `[chat_sessions, security_events, proposals_deleted, proposals_evidence_cleared, eval_reports, auth_sessions, reset_codes, rate_limits]`(C3·C4가 C5보다 앞) |
| U-CL-5 | 〃 컴파일 | — | 모든 기준값이 바인드 파라미터(문자열에 날짜 리터럴 없음), C3에 `status IN ('new', 'rejected')`, C4에 `'adopted', 'held'` |

### 5. 작업 묶음 순서·실패 격리 (DB 없음) — `tests/ingest/test_daily_sync_flow.py`
단계 함수를 가짜로 바꿔 끼운 `run_daily_sync`(잠금·`ingest_runs`도 가짜 — 호출 기록). 단계 순서 기록 리스트로 검증.

| ID | 상황 | 기대 |
|---|---|---|
| U-DS-1 | 모두 성공 | 순서 `lock → stale → run_row → list → detail → remove → hubs → faq → lint → git → cleanup → finalize → unlock`, `status=done` |
| U-DS-2 | 잠금 실패 | `LockBusy`, 다른 단계 0회, 행 생성 0 |
| U-DS-3 | `list`가 예외 | `steps.list=failed`, 나머지 전부 실행, `status=failed`, `error`에 `list` |
| U-DS-4 | `hubs`가 예외 | `faq`·`lint`·`git`·`cleanup` 실행, `failed` |
| U-DS-5 | `cleanup`이 예외 | `finalize`는 실행, `steps.cleanup=failed` |
| U-DS-6 | `detail` 중 22 | `budget.mark_quota_hit` 1회, `stop_reason=quota`, `steps.detail=failed`, `remove`~`cleanup` 실행 |
| U-DS-7 | `list` 중 23 | `detail` 단계는 TourAPI 호출 없이 끝남(`rate` — 이번 실행 TourAPI 중단), `remove`~`cleanup` 실행, `failed` |
| U-DS-8 | 예산 소진(`budget`) | `steps.detail=ok`, `stop_reason=budget`, `done` |
| U-DS-9 | ① `TOURAPI_SERVICE_KEY` 없음 ② `LIGHTRAG_API_KEY` 없음 | ① `list`·`detail` failed("설정 누락: TOURAPI_SERVICE_KEY"), `remove`~`cleanup` 실행 ② `detail`·`remove` failed("설정 누락: LIGHTRAG_API_KEY"), `list`·`hubs`~`cleanup` 실행 (spec §6.2) |
| U-DS-10 | 단계 간 값 전달 | 대기 {A, P}, 가짜 `detail`이 changed {A}, `remove`가 deleted {B}. `FakeHubs.affected`: {P,A} 호출 → {(서울,"23")}, {A,B} 호출 → {(서울,"24")}, `missing` → {(제주,"2")}. `bootstrap:completed_at` 있음, OpenAI 키 있음 | `faq`가 받은 ids == {A, B}. `affected`가 상세 **전**에 대기 목록으로 1회, 뒤에 {A,B}로 1회. `write` 인자 == {(서울,"23"),(서울,"24"),(제주,"2")} |
| U-DS-10b | 허브 건너뜀 | ① `bootstrap:completed_at` 없음 ② OpenAI 키 없음 ③ 키 합집합이 빔 | `write` 0회. `steps.hubs` = skipped(① "초기 적재 중" ② "no_openai_key" ③ "영향 없음"), 실행 결과에 영향 없음(done) |
| U-DS-10c | 허브 일부 실패 | `write` → `{"failed":1,…}` | `steps.hubs=failed`, 다음 단계 계속, `status=failed` |
| U-DS-11 | `lint` 결과 | `FakeHubs.lint(run_id)` → `"lint: error 0 · warning 2"` | `lint`가 이 실행의 `run_id`로 1회 호출(저장은 20 `save_lint` 몫), `SyncResult.lint_summary`가 그 문자열 |
| U-DS-12 | git 메시지·결과 | detailed 3, removed 1, 허브 written 2, now 11-22, `commit` → ("abc123", 3) | 메시지 첫 줄 `[daily_sync] 2026-11-22 변경 3 · 삭제 1 · 허브 2`, `git_commit="abc123"`, `git_files=3`. `commit`이 `(None, 0)`이면 `git_commit=None`, 단계 ok |
| U-DS-13 | `run_scheduled_daily` (21-Q1 A) | `bootstrap:completed_at` 없음 | `run_daily_sync` → `run_bootstrap` 순서. 있음 → `run_bootstrap` 호출 0 |
| U-DS-14 | 〃 | `run_bootstrap`이 `LockBusy` | 예외 삼킴, INFO 로그 |
| U-DS-15 | 〃 | `run_daily_sync`가 `LockBusy` | `run_bootstrap`도 호출하지 않음(수동 작업이 잠금 보유 중) |

### 6. DB 테스트 (마커 `db`) — `tests/ingest/test_sync_db.py`
`ingest_tables_clean` 사용. TourAPI는 MockTransport, 예산은 실제 `Budget`(시계 2099-01-01 고정 — 실제 날짜 키를 건드리지 않음, 끝나면 키 삭제).

| ID | 준비 | 동작 | 기대 |
|---|---|---|---|
| D-SY-1 분류 반영 | 행: A(상세 `T−1h`), B(상세 `T+1h`), C(삭제 안 됨), D(이미 삭제). SyncList 1페이지: A(수정 T), B(수정 T), C(showflag 0), D(showflag 1), E(새 항목, 서울 39), F(유형 76) | `scan_area("서울", TH, acc)` | A `detail_synced_at` NULL·대기 목록에, B 그대로, C `deleted_at` 채워짐, D `detail_synced_at` NULL·대기 목록에(`deleted_at`은 아직 있음), E 껍데기 행 생성(`detail_synced_at` NULL)·대기 목록 `reason=new`, F 무시. `acc` 개수 = changed 2, fresh 1, deleted 1, new 1, ignored 1. raw 파일 `areaBasedSyncList2/sync_서울_p1.json` 생성 |
| D-SY-2 페이지 멈춤 | 1페이지 끝 항목이 TH보다 오래됨, 2페이지 픽스처도 있음 | `scan_area` | 1페이지만 요청(MockTransport 1회), True |
| D-SY-3 끝 페이지 | totalCount 150, 2페이지 모두 최신 | 〃 | 2회 요청, True |
| D-SY-4 커서 갱신 | 두 지역 모두 True | `run_list_step`(spec §7.2 4) | `sync:cursor.since == list_started_at` |
| D-SY-5 커서 유지 | 제주 1페이지에서 `BudgetExhausted` | 〃 | 커서 이전 값 그대로, 서울 반영분은 커밋됨, `stop_reason=budget` |
| D-SY-6 커서 없음·적재 이력 없음 | `ingest_runs` 비어 있음 | 목록 단계 | 요청 0, `steps.list=skipped`, `stop_reason=no_bootstrap` |
| D-SY-7 대기 목록 처리 | 대기 {A, D, E}(D-SY-1 뒤), 상세 픽스처(A·D·E), FakeLightRag | 상세 단계 | 세 행 `detail_synced_at` 채워짐, D `deleted_at` NULL(되살아남), 대기 목록 비움, `changed` 집합 {A, D, E} |
| D-SY-8 바뀐 페이지 재인덱싱 | A의 `wiki_pages` 해시 `old`, doc `doc-A` | D-SY-7의 `after_batch` | FakeLightRag 기록: `delete_documents(["doc-A"])` → `insert_text(…, file_source="entity/12/A.md")`, `wiki_pages.content_hash` = 새 해시. E(새 항목)는 `index_pending` 경로로 인덱싱 |
| D-SY-9 내용 같음(§11-1) | A를 `detail_synced_at=NULL`로 만든 뒤, 같은 날 같은 상세로 처리(`upsert` 결과 `unchanged`) | 상세 단계 | A `detail_synced_at` = `fetched_at`(NULL 아님), 대기 목록에서 빠짐, LightRAG 호출 0(해시 같음) |
| D-SY-10 빈 상세 = 삭제 | A의 `detailCommon2` item 0개 | 상세 단계 | A 소프트 삭제, `deleted` 집합에 A, 호출 1건 |
| D-SY-11 실패 제외 | A 상세가 매번 timeout, `bootstrap:failures` A attempts 2 | 상세 단계 1회 | attempts 3, 대기 목록에서 A 빠짐, `errors`에 "3회 실패로 제외" |
| D-SY-12 삭제 반영 | C(삭제됨) `wiki_pages` doc `doc-C`, 위키 파일 있음(tmp_path) | `remove_deleted_pages` | LightRAG `delete_documents(["doc-C"])` → `document_exists` False, 파일 없음, `wiki_pages` 행 없음, `removed_pages=1` |
| D-SY-13 삭제 실패 재시도 | FakeLightRag 삭제가 시간 초과 | 〃 1회 → 2회(정상) | 1회: 행·파일 그대로, `removal_failed=1`. 2회: 정리됨 |
| D-SY-14 doc_id 없음 | C `lightrag_doc_id` NULL(인덱싱 전 삭제) | 〃 | LightRAG 호출 0, 파일·행 삭제 |
| D-SY-15 FAQ 무효화 | `faq_cache` 3행: contentids [A], [C,X], [Y] | 단계 5(ids {A, C}) | 앞 두 행 삭제, [Y] 남음, `faq_invalidated=2`, 그 캐시를 가리키던 메시지 `faq_cache_id` NULL |
| D-SY-16 허브 연결 | `bootstrap:completed_at` 있음, `FakeHubs` | D-SY-7 흐름(A·D·E 처리) | `FakeHubs.affected`가 대기 목록 {A,D,E}로(상세 전) 1회, `changed ∪ deleted`로 1회 호출. `write`는 두 결과·`missing` 합집합으로 1회 |
| D-SY-16b (20 병합 뒤) | 20 실제 `affected_hubs`·`missing_hubs`, 가짜 모델 | A(서울 23 → 다시 받은 뒤 24로 바뀜) | `write_hubs` 키에 (서울,23)·(서울,24) 둘 다 |
| D-SY-17 잠금 | 다른 연결이 `pg_try_advisory_lock(1)` 보유 | `run_daily_sync` | `LockBusy`, `ingest_runs` 0행 |
| D-SY-18 멈춘 기록 정리 | `ingest_runs`에 `daily_sync`·`running` 1행, `bootstrap`·`running` 1행 | `run_daily_sync`(나머지 가짜) | `daily_sync` 행 `failed`·문구, `bootstrap` 행은 그대로(03 몫), 새 행 1개 |
| D-SY-19 중복 실행 멱등 | D-SY-1~15 흐름 한 번 실행 뒤 같은 SyncList로 다시 실행 | 두 번째 | 상세 호출 0(모두 `fresh`), LightRAG 호출 0, FAQ 무효화 0, 정리 0, `status=done` |
| D-SY-20 결과 기록 | 정상 1회 | — | `ingest_runs` 행 `kind=daily_sync`, `status=done`, `stats`에 spec §6.4 필드 전부, `lint` = FakeHubs lint 값, `finished_at` 채워짐 |

### 7. 정리 DB 테스트 (마커 `db`) — `tests/ingest/test_cleanup_db.py`
`NOW = 2026-11-22 01:00 KST` 주입. 행은 super 엔진으로 시각을 직접 넣는다.

| ID | 준비 | 기대 (`run_cleanup(now=NOW)` 뒤) |
|---|---|---|
| D-CL-1 세션 경계 | 세션 S89(`updated_at = at(89)`), S90(정확히 `at(90)`), S91(`at(91)`) | S91만 삭제, `chat_sessions=1` |
| D-CL-2 세션 연쇄 | S91에 메시지 4(2턴), 👎 피드백 1, 원본 FAQ 캐시 1, `eval_scores` 1, `security_events`(session_id=S91, `created_at=at(10)`) 1, `usage_events`(message_id=S91 메시지) 1. 다른 세션 S10의 메시지가 그 캐시를 가리킴(`faq_cache_id`) | 메시지·피드백·캐시·채점 0행, 보안 이벤트는 남고 `session_id`·`message_id` NULL, `usage_events` 남고 `message_id` NULL, S10 메시지 남고 `faq_cache_id` NULL |
| D-CL-3 보안 이벤트 | `created_at` 89·90·91일 | 91일만 삭제 |
| D-CL-4 보고서·개선안 | 보고서 R_old(`report_date=2026-08-23`), R_edge(`2026-08-24`), R_new(`2026-11-20`). R_old 개선안: new·rejected·adopted(evidence `[{"q":"…"}]`)·held(evidence 있음). R_new 개선안 new 1. R_old에 `eval_scores` 1 | R_old 삭제·R_edge·R_new 남음. R_old의 new·rejected 삭제, adopted·held 남고 `report_id` NULL·`evidence=[]`·`problem`·`proposal` 그대로. R_new 개선안 그대로. R_old 채점 0. 결과 `proposals_deleted=2`, `proposals_evidence_cleared=2`, `eval_reports=1` |
| D-CL-5 고아 개선안 | `report_id` NULL: rejected(`created_at=at(120)`), held(`at(120)`, evidence `[]`), new(`at(30)`) | rejected만 삭제. held 그대로(이미 빈 근거 → `proposals_evidence_cleared`에 안 셈), new(30일) 그대로 |
| D-CL-6 로그인 세션 | ① `expires_at = NOW−1초` ② `expires_at=NOW+1일`, `last_seen_at = NOW−2시간`(정확히 유휴 경계) ③ `expires_at=NOW+1일`, `last_seen_at=NOW−1시간` ④ `expires_at == NOW` | ①②④ 삭제, ③ 남음 (05 `is_valid`와 같은 경계 — `is_valid(row, NOW)`가 False인 행만 지워짐을 같은 데이터로 대조) |
| D-CL-7 재설정 코드 | ① 만료 지남 ② 유효·사용됨(`consumed_at` 있음) ③ 유효·미사용 ④ 유효·attempts 5 | ①② 삭제, ③④ 남음 |
| D-CL-8 rate_limits | ① `window_start=NOW−2일`, 잠금 없음 ② `NOW−2일`, `locked_until=NOW+5분` ③ `NOW−1시간` ④ `NOW−2일`, `locked_until=NOW−1분` | ①④ 삭제, ②③ 남음 |
| D-CL-9 한 트랜잭션 | C5 문을 일부러 실패시키는 가짜(monkeypatch로 잘못된 문 삽입) | 예외, **C1~C4 결과도 롤백**(행 수 그대로) |
| D-CL-10 손대지 않는 테이블 | `users`, `daily_quota`(`day=2026-01-01`), `usage_events`(`created_at=at(200)`), 소프트 삭제 `tour_items`, `ingest_runs` 오래된 행 | 모두 그대로 |
| D-CL-11 0건 | 모두 최신 | 결과 dict 모든 값 0, 오류 없음 |

### 8. CLI (DB 없음, `run_daily_sync` 가짜) — `tests/test_cli_sync.py`
| ID | 명령 | 기대 |
|---|---|---|
| U-CLI-1 | `nadri ingest sync --now`, 결과 done | 종료 0, 마지막 줄 JSON = `summary_line` |
| U-CLI-2 | 결과 failed | 1 |
| U-CLI-3 | `LockBusy` | 4, 한국어 안내 "다른 수집 작업이 실행 중이에요" 류 한 줄 |
| U-CLI-4 | `nadri ingest sync`(`--now` 없음) | 2 |
| U-CLI-5 | `TOURAPI_SERVICE_KEY` 없음 | 2([01] `require`) |
| U-CLI-6 | `nadri ingest scheduler` | `serve` 호출(가짜) |
| U-CLI-7 | 출력에 서비스 키 문자열 없음 | settings 키 `"SECRET-KEY-123"`, 진행 줄 전체에 미포함 |

### 9. 통합 (선택, `@pytest.mark.integration`) — `tests/integration/test_sync_live.py`
| ID | 내용 | 기대 |
|---|---|---|
| I-1 | **(실 TourAPI 2호출)** `TOURAPI_LIVE=1`일 때만. 실제 `Budget`(오늘 키 — 2건 소비)로 서울·제주 `area_based_sync_list(num_of_rows=100, page_no=1)` → raw 저장 → 출력: `totalCount`, item 필드 이름 목록, `modifiedtime` 처음 5개(정렬 확인), `showflag` 값 분포 | 두 호출 성공. 결과를 spec §14 A12 줄에 기록(판정은 사람 — 테스트는 기록만) |

### 10. 앞 작업 회귀
- 01·03 ingest 테스트 전체, 12(무효화)·13 테스트 재실행. spec §11 표대로 수정한 테스트 통과.

### 통과 기준
- 위 전부 통과(I-1 제외), `-m "not integration"` 실패 0.

---

## ② HITL

전제: 20이 `dev`에 병합됨(허브·lint·git), 21 브랜치로 이미지 다시 빌드. 명령은 레포 루트(`~/code/myAgent`, WSL2)에서.

### H-0 준비 (21-Q1 A일 때)
1. 03 `--follow` 컨테이너가 떠 있으면 멈춘다: `docker ps --filter name=nadri-bootstrap` → `docker stop nadri-bootstrap && docker rm nadri-bootstrap`.
2. 초기 적재 상태 확인: `docker compose run --rm ingest nadri ingest status` → `bootstrap:completed_at` 유무와 오늘 카운터(`ingest`·`live`)를 적어 둔다.

### H-1 상주 기동
```bash
docker compose -f compose.yaml -f compose.dev.yaml up -d --build
docker compose ps
docker compose logs ingest --since 5m
```
- [ ] `ingest`가 `Up (healthy)`(이전처럼 `exited (0)`이 아님), `api`·`tour-tools`도 `Up`
- [ ] 로그에 `scheduler started jobs=[daily_sync@01:00 KST] next=<다음 01:00>` 한 줄
- [ ] (오늘 01:00 이후이고 오늘 실행 기록이 없으면 — 21-Q2 A) 바로 `daily_sync start run_id=…` 따라잡기 실행이 보임. 이 경우 H-2는 그 실행이 끝난 뒤에 한다

### H-2 수동 실행 `ingest sync --now`
```bash
docker compose exec ingest nadri ingest sync --now
```
- [ ] 진행 줄: `[sync 서울 p1] new … changed … fresh … deleted …`, `[상세 …]`, `[정리] …`
- [ ] 마지막 줄 JSON에서 아래를 결과 표에 옮긴다: `calls`, `calls_by_op.areaBasedSyncList2`, 지역별 `listed`, `detailed`, `soft_deleted`, `removed_pages`, `indexed`, `hubs`(keys·written·skipped·cost_usd), `faq_invalidated`, `lint_summary`, `git_commit`, `cleanup`, `steps`
- [ ] 종료 코드 `echo $?` → 0(또는 1이면 `steps`의 failed 이유 기록)
- [ ] 첫 실행이면(커서 없음) 목록 페이지 수가 많을 수 있다 — `calls_by_op.areaBasedSyncList2`가 수십을 넘으면 그대로 보고(21-Q5)
```bash
docker compose exec postgres psql -U postgres -d nadri -c "select id, kind, status, started_at, finished_at, stats->'steps' as steps from ingest_runs order by id desc limit 3"
docker compose exec postgres psql -U postgres -d nadri -c "select key, value from ingest_state where key in ('sync:cursor') or key like 'tourapi_calls:%' order by key desc limit 3"
docker compose exec postgres psql -U postgres -d nadri -c "select jsonb_object_length(value) as pending from ingest_state where key = 'sync:pending'"
```
- [ ] `daily_sync` 행 `done`, `sync:cursor.since`가 방금 시각, 오늘 카운터 `ingest`가 H-0보다 `calls`만큼 늘었음

### H-3 SyncList 실제 모양 (A12)
```bash
docker compose exec ingest sh -c 'ls /data/raw/$(TZ=Asia/Seoul date +%F)/areaBasedSyncList2/ | head; f=$(ls /data/raw/$(TZ=Asia/Seoul date +%F)/areaBasedSyncList2/*서울_p1*.json | head -1); python -c "import json,sys; d=json.load(open(sys.argv[1])); it=d[\"response\"][\"body\"][\"items\"][\"item\"]; print(sorted(it[0].keys())); print([i.get(\"modifiedtime\") for i in it[:5]]); print({i.get(\"showflag\") for i in it})" "$f"'
```
(raw 저장 구조가 01 구현과 다르면 경로·키만 맞춰 같은 내용을 확인)
- [ ] 필드 이름 목록에 `contentid`·`contenttypeid`·`modifiedtime`(·`showflag`)이 있음
- [ ] `modifiedtime` 처음 5개가 **최신순**(내림차순) — 아니면 멈추고 보고(21-Q5)
- [ ] `showflag` 값 종류 기록

### H-4 정리 확인 (테스트 데이터로)
테스트용 사용자 1명(05 `create-admin`이 아닌 일반 사용자, 활성)으로 대화 1개를 만든 뒤 시각만 과거로 돌린다.
```bash
# 1) 대화 하나 만들기(09 HITL 셸 함수 사용) 후 세션 id를 S에 적는다
# 2) 91일 전으로 바꾸기 + 오래된 보안 이벤트·만료 세션 흉내
docker compose exec postgres psql -U postgres -d nadri -c "update chat_sessions set updated_at = now() - interval '91 days' where id = '$S'"
docker compose exec postgres psql -U postgres -d nadri -c "update security_events set created_at = now() - interval '91 days' where session_id = '$S'"
docker compose exec postgres psql -U postgres -d nadri -c "select count(*) from chat_messages where session_id = '$S'"
docker compose exec ingest nadri ingest sync --now
docker compose exec postgres psql -U postgres -d nadri -c "select count(*) from chat_sessions where id = '$S'; select count(*) from chat_messages where session_id = '$S'"
```
- [ ] 정리 전 메시지 수 > 0, 정리 뒤 세션·메시지 0, 출력 `cleanup.chat_sessions ≥ 1`
- [ ] 다른(최근) 세션은 그대로(사이드바 목록 정상)
- [ ] 로그(`docker compose logs ingest --since 5m`)·출력에 질문·답변 글이 없음(건수만)

### H-5 다음 날 01:00 자동 실행
PC·Docker를 01:00에 켜 둔 다음 날 아침(또는 꺼져 있었다면 기동 직후 따라잡기 확인):
```bash
docker compose logs ingest --since 12h | grep -E "daily_sync|scheduler"
docker compose exec postgres psql -U postgres -d nadri -c "select id, kind, status, started_at, finished_at, stats->'calls' as calls, stats->'detailed' as detailed, stats->'cleanup' as cleanup from ingest_runs where started_at > now() - interval '1 day' order by id"
```
- [ ] `daily_sync start` 시각이 01:00 KST 직후(따라잡기였다면 기동 시각 직후)
- [ ] `daily_sync done … status=done`, 이어서(초기 적재 미완료면, 21-Q1 A) `bootstrap` 행이 하나 더 있음
- [ ] `scheduler started … next=`가 다음 날 01:00을 가리킴
- [ ] 오늘 카운터 `ingest` ≤ 800(`ingest status`)

### H-6 중복 실행 건너뜀
터미널 두 개에서 거의 동시에:
```bash
docker compose exec ingest nadri ingest sync --now     # 터미널 1
docker compose exec ingest nadri ingest sync --now; echo "exit=$?"     # 터미널 2 (1이 도는 중에)
```
- [ ] 터미널 2가 `exit=4`와 "다른 수집 작업 실행 중" 안내, `ingest_runs`에 행이 하나만 늘어남

### H-7 (삭제가 생겼을 때만) 삭제 반영
`soft_deleted` 또는 `removed_pages`가 1 이상인 날:
```bash
docker compose exec postgres psql -U postgres -d nadri -c "select t.contentid, t.deleted_at, w.path from tour_items t left join wiki_pages w on w.contentid = t.contentid where t.deleted_at > now() - interval '2 days'"
```
- [ ] 삭제된 항목의 `wiki_pages` 행 없음(path NULL), 위키 파일 없음(`docker compose exec ingest ls /data/wiki/entity/<유형>/<id>.md` → 없음), `nadri lightrag sample --query "<그 이름>"`에 나오지 않음(A16)

### HITL 결과 보고
| 항목 | 결과 |
|---|---|
| H-1 상태(`healthy`)·스케줄러 다음 실행 시각·따라잡기 여부 | |
| H-2 `calls`(SyncList·상세)·지역별 listed·detailed·indexed·hubs·faq·cleanup·steps | |
| H-3 필드 이름·정렬(최신순?)·`showflag` 값 → spec §14 A12 | |
| H-4 정리 전/후 행 수 | |
| H-5 01:00 자동 실행 로그 시각·결과, 이어진 bootstrap 행 | |
| H-6 두 번째 실행 종료 코드 | |
| H-7 (있으면) 삭제 반영 | |
