# 25-admin-quality-hitl — 테스트 설계 (test)

> spec.md와 짝. 절 번호 §n은 spec.md 기준. 작성 2026-11-22. 상태: **초안 — 확인 질문 대기**(spec §10).
> ① 자동 — A: pytest(결정적, 외부 호출 없음, DB는 04 테스트 컨테이너 — 마커 `db`) / B: Vitest(나누기·서식·API 함수·카드) / C: Playwright(가짜 응답을 `page.route`로 주입 + 실제 compose `@real`) ② HITL(24가 만든 실제 보고서로 화면 확인·결정).
> 집계 JSON 픽스처는 **24 spec §9 정본 표**, 공격 유형은 23 §4.2 `ATTACK_TYPES` 9개 기준(2026-11-22 확정본 반영).
> 전이 표 테스트(A-QH-1x)는 25-Q2 추천안 기준이다. 대안이 정해지면 그 표에 맞춰 기대값만 바꾼다.

---

## ① 자동 테스트

### 0. 공통
```bash
cd ~/code/myAgent/backend && uv run pytest -m "not integration"            # Docker 필요(db 마커)
cd ~/code/myAgent/web && npm run typecheck && npm run test
npm run e2e -- --grep-invert @real     # 가짜 응답 — compose의 web만 필요
npm run e2e -- --grep @real            # 실제 compose(외부 API 비용 없음 — 보고서·개선안은 psql로 넣음)
```
- 재사용: 05 헬퍼(`app`·`client`·`client2`·`make_user`·`login`·`post`·`clock`), 04 `db_sf`.
- 추가 헬퍼(`tests/helpers/quality.py`):

| 이름 | 역할 |
|---|---|
| `add_report(db_sf, *, report_date, status="done", stats=None, body_md=None, error=None, model="gpt-6-luna")` | `eval_reports` 1행 INSERT, id 반환 |
| `add_proposal(db_sf, *, report_id, seq=1, priority="medium", status="new", target="system_prompt", title="t", evidence=None, created_at=None, decision_note=None)` | `improvement_proposals` 1행 INSERT(필수 글 필드는 기본값 채움), id 반환 |
| `decide(client, pid, **body)` | CSRF 포함 `POST /api/admin/quality/proposals/{pid}/decision` |
| `SAMPLE_STATS` | 24 §9 표의 모든 키를 채운 done 보고서 dict(`schema`·`rubric_version`·`report_date`·`steps` + `conversation`·`scoring`·`verification`·`latency_ms`·`cost_usd`·`feedback`·`security`·`attack_set`(9개 유형 `by_type`, `failed_ids` 2개)·`data_gaps`·`eval_run`). JSON 파일 `tests/fixtures/quality/sample_stats.json` 하나를 pytest·Vitest·Playwright가 함께 씀 |
| `FAILED_STATS` | `{"schema":1,"rubric_version":1,"report_date":"2026-11-20","steps":{"collect":"done","scoring":"failed"}}`(24 §9 failed 예외 모양) |
| `SKIPPED_STATS` | `SAMPLE_STATS`를 대화 0건 모양으로(24 §9: conversation·scoring 수 0, 비율 null, `steps.scoring/summary/proposals="skipped"`, `attack_set` 실제 값) |

- 시계: `clock.now` 기본 `2026-11-22T03:00:00+00:00` = KST 2026-11-22 12:00.

---

### A. pytest

#### A1. 순수 함수 — `tests/api/admin/test_quality_pure.py` (DB 없음)

| ID | 입력 | 기대 |
|---|---|---|
| U-QH-01 | `resolve_report_range(None, None, now)` | `(2026-10-24, 2026-11-22)` (30일) |
| U-QH-02 | `resolve_report_range(None, 2026-10-15, now)` | `(2026-09-16, 2026-10-15)` |
| U-QH-03 | `resolve_report_range(2026-11-01, None, now)` | `(2026-11-01, 2026-11-22)` |
| U-QH-04 | `(2026-11-10, 2026-11-09)` | `ApiError(400, "invalid_range")`, 문구 = 19 `MSG_INVALID_RANGE` |
| U-QH-05 | 366일 / 367일 | 통과 / 400 |
| U-QH-06 | `now = 2026-11-30T15:00Z`(KST 12-01 00:00), 쿼리 없음 | `to = 2026-12-01` |
| U-QH-07 | `pick_headline(SAMPLE_STATS)` | 5개 키 모두 값: `turns_answered`·`proposals_created` int, `good_rate`·`verify_pass_rate`·`attack_defense_rate` float(픽스처 값 그대로) |
| U-QH-08 | `pick_headline({})` / `pick_headline(FAILED_STATS)` | 둘 다 5개 키 전부 None |
| U-QH-09 | `pick_headline({"verification": 3})` / `{"verification": {"pass_rate": True}}` / `{"verification": {"pass_rate": [1]}}` | 모두 `verify_pass_rate None`, 예외 없음 |
| U-QH-09b | `pick_headline(SKIPPED_STATS)` | `turns_answered 0`, `good_rate None`, `verify_pass_rate None`, `attack_defense_rate` 값 있음 |
| U-QH-09c | `pick_steps(SAMPLE_STATS)` / `pick_steps({"steps": {"scoring": "partial", "zzz": "done", "summary": 1}})` / `pick_steps({"steps": "x"})` | 5개 단계 / `{"scoring": "partial"}`(모르는 키·문자열 아닌 값 제외) / `{}` |
| U-QH-10 | `decision_allowed` 전체 표(현재 4 × 요청 3 = 12칸) | spec §5.1과 같음: 같은 상태 3칸만 False, 나머지 9칸 True |
| U-QH-11 | `DecisionIn(status="adopted", note="  메모  ")` / `note="   "` / `note=None` | `"메모"` / `None` / `None` |
| U-QH-12 | `note` 1000자 / 1001자(공백 제거 후) | 통과 / `ValidationError` |
| U-QH-13 | `DecisionIn(status="new")` / `"approved"` / `{"status":"held","x":1}` | 모두 `ValidationError` |
| U-QH-14 | `DECISION_STATUSES` ⊂ 04 `PROPOSAL_STATUSES`, `PROPOSAL_STATUSES − DECISION_STATUSES == {"new"}` | 참 |
| U-QH-15 | `web/lib/admin-quality.ts`의 `ProposalStatus`·`ProposalTarget`·`ProposalPriority`·`ReportStatus` 문자열 집합 vs 04 상수 4개 | 같음(TS 파일을 정규식으로 읽어 대조 — 19 U-UG-18 방식) |
| U-QH-16 | `ReportListOut` 직렬화(`by_alias=True`) | 키 `"from"` 있고 `"from_"` 없음 |

#### A2. 조회 — `tests/api/admin/test_quality_read.py` (마커 `db`)

준비: `admin`(관리자), `alice`(일반), `pend`(pending).
- r1 `2026-11-21` done, `SAMPLE_STATS`, body_md 있음 — 개선안 p1(high, new, seq 2), p2(low, adopted, seq 1), p3(medium, held, seq 3)
- r2 `2026-11-20` failed, stats `FAILED_STATS`, error `"boom"` — 개선안 없음
- r4 `2026-11-19` skipped, stats `SKIPPED_STATS` — 개선안 없음
- r3 `2026-09-01` done — 개선안 p4(medium, rejected)
- p5: `report_id NULL`, adopted, `evidence []`, created_at 2026-08-01

| ID | 요청 | 기대 |
|---|---|---|
| A-QH-01 | admin, `GET /reports` | 200, `from "2026-10-24"`, `to "2026-11-22"`, `reports` = [r1, r2, r4] 순(r3 기간 밖) |
| A-QH-02 | 〃 r1 줄 | `proposal_counts {new 1, adopted 1, held 1, rejected 0}`, `headline`이 U-QH-07과 같음, `steps` 5개, 응답에 `stats` 키 없음 |
| A-QH-03 | 〃 r2 줄 | `status "failed"`, `headline` 값 전부 null, `steps {collect done, scoring failed}`, counts 전부 0 |
| A-QH-03b | 〃 r4 줄 | `status "skipped"`, headline은 U-QH-09b와 같음 |
| A-QH-04 | `?from=2026-09-01&to=2026-09-30` | r3만 |
| A-QH-05 | `?from=2026-11-10&to=2026-11-09` / `?from=2026-13-01` | 400 `invalid_range` / 422 |
| A-QH-06 | `GET /reports/{r1}` | 200, `stats`가 `SAMPLE_STATS`와 똑같음(해석 없이 그대로), `body_md` 그대로, `proposals` = [p1(high), p3(medium), p2(low)] 순, 각 항목 `report_date "2026-11-21"` |
| A-QH-07 | `GET /reports/{r2}` | `error "boom"`, `proposals []`, `stats` = `FAILED_STATS` 그대로 |
| A-QH-08 | 없는 id / `abc` / `0` / `9223372036854775808` | 404 `report_not_found` / 422 / 422 / 422 |
| A-QH-09 | `GET /proposals` | 5건 전부, p5는 `report_id null`·`report_date null`·`evidence []`. p1의 `evidence`(24 §12.4 모양 `[{type:"turn",ref:"t-012",quote:"…",note:"…"},{type:"stat",ref:"latency_ms.total.p95",quote:null,note:"14.2초"}]`)가 그대로 |
| A-QH-10 | `GET /proposals?status=adopted` | p2, p5만(우선순위 같으면 `created_at` 최신 먼저) |
| A-QH-11 | `?status=deleted` | 422 |
| A-QH-12 | stats에 모르는 키 `{"zzz": {"a": [1,2]}}`를 넣은 보고서 상세 | 200, 그 키가 `stats`에 그대로 있음 |
| A-QH-13 | 쿼리 수(`before_cursor_execute`, `eval_reports`·`improvement_proposals` 포함 문만) | 목록 1개, 상세 2개, 개선안 1개 — 행마다 추가 조회 없음 |

#### A3. 결정 — `tests/api/admin/test_quality_decide.py` (마커 `db`)

| ID | 요청 | 기대 |
|---|---|---|
| A-QH-14 | p1(new) → `{status:"adopted", note:"다음 스프린트"}` | 200, 응답 `status "adopted"`, `decision_note`, `decided_by = admin.id`, `decided_by_username "admin"`, `decided_at = clock.now`. DB 같음 |
| A-QH-15 | 전이 표 12칸을 실제 API로(칸마다 새 개선안) | 허용 9칸 200, 같은 상태 3칸 409 `proposal_status_conflict` + 본문 `"status"` = 현재 상태, 409 때 DB 그대로(`decided_at`·메모 안 바뀜) |
| A-QH-16 | held → rejected, 그 뒤 21 `cleanup`의 C3 조건(`report_id NULL AND created_at < 90일 전`)으로 정리 실행(p5를 rejected로 바꾼 뒤) | p5 삭제됨 — 21 C3 전제와 25 전이가 맞물림 확인 |
| A-QH-17 | 메모 `"a"`로 채택 → 기각(note 없음) | `decision_note null`(덮어쓰기) |
| A-QH-18 | note 1001자 / `status:"new"` / extra 필드 | 422, DB 그대로 |
| A-QH-19 | 없는 id | 404 `proposal_not_found` |
| A-QH-20 | CSRF 헤더 없이 | 403 `csrf_failed`, DB 그대로 |
| A-QH-21 | alice(일반) / pend / 로그인 안 함 | 403 `forbidden` / 403 / 401 — 4개 엔드포인트 모두(파라미터화) |
| A-QH-22 | 동시 2건(같은 개선안, 둘 다 adopted, `asyncio.gather` + 세션 2개) | 하나 200, 하나 409 |
| A-QH-23 | 결정한 관리자 행 삭제(psql) 뒤 `GET /proposals` | `decided_by null`, `decided_by_username null`, 상태는 그대로 |
| A-QH-24 | 로그(caplog) | `admin_proposal_decision` 1줄, `admin_id`·`proposal_id`·`from`·`to`·`note_len`, **메모 내용 없음** |
| A-QH-25 | `GET` 엔드포인트에 POST / 결정 경로에 GET | 405 |

#### A4. 자동 적용 없음 (ADR-23) — `tests/api/admin/test_quality_no_auto.py`

| ID | 내용 | 기대 |
|---|---|---|
| A-QH-30 `db` | 결정 1건 전후로 앱 테이블 18개의 행 수와 `improvement_proposals` 외 테이블 전체 내용 해시, `backend/src/nadri/prompts/` 파일 해시 비교 | `improvement_proposals` 그 1행만 다름, 나머지 같음 |
| A-QH-31 | `quality.py` 소스(AST)에 `open(`·`Path(...).write_*`·`subprocess`·`httpx`·`openai`·`langchain` import·`"prompts"` 문자열 없음 | 없음 |

#### A5. 앞 작업 회귀
- 18·19·05 테스트 전체 재실행(spec §8). 18 A-ADR-06이 `/api/admin/quality/*` 4개도 통과. 05 문구 상수 목록 테스트가 있으면 3개 추가. 21 cleanup 테스트 그대로 통과.

---

### B. Vitest

#### B1. `web/tests/unit/admin-quality.test.ts`

| ID | 입력 | 기대 |
|---|---|---|
| V-QH-01 | `formatRate(0.9333)` / `1` / `0` / `null` / `"0.9"` / `1.2` | `"93.3%"` / `"100.0%"` / `"0.0%"` / `"—"` / `"—"` / `"120.0%"` |
| V-QH-02 | `formatCost("0.00190000")` / `0.5` / `undefined` | `"$0.0019"` / `"$0.50"` / `"—"` (19 `formatUsd` 규칙) |
| V-QH-03 | `splitStats(SAMPLE_STATS)` (24 §9 모든 키, 공유 픽스처) | `known`에 머리 4개 + 묶음 10개 모두, `rest` 빈 배열 — **24 §9와 25 §6.4가 맞는지 지키는 테스트** |
| V-QH-04 | `splitStats({...SAMPLE_STATS, zzz: {a: 1, b: [1,2]}})` | `rest` = `[{key:"zzz.a", value:"1"}, {key:"zzz.b", value:"[1,2]"}]` |
| V-QH-04b | `SAMPLE_STATS`의 `attack_set`에 하위 키 `extra: 3` 추가 | `known.attack_set` 그대로, `rest` = `[{key:"attack_set.extra", value:"3"}]` |
| V-QH-05 | `splitStats({verification: "oops", attack_set: {total: "x"}})` | 둘 다 가드 실패 → `known`에 없음, `rest`에 `verification`·`attack_set.total` 줄 |
| V-QH-05b | `splitStats(FAILED_STATS)` | `known`에 머리 4개만, `rest []` |
| V-QH-05c | `ATTACK_TYPE_LABEL` 키 | 23 `ATTACK_TYPES` 9개와 같음(jailbreak, direct_injection, prompt_leak, indirect_injection, exfiltration, pii, harmful, self_harm, off_topic) |
| V-QH-06 | `splitStats({})` | `known {}`, `rest []` |
| V-QH-07 | `flattenStats` 깊이 5 객체 | 깊이 4 아래는 JSON 문자열 한 줄 |
| V-QH-08 | `flattenStats({long: "x".repeat(300)})` | 값 200자 + "…" |
| V-QH-09 | `evidenceLines({type:"turn",ref:"t-012",quote:"q",note:"n"})` / `{type:"stat",ref:"latency_ms.total.p95",quote:null,note:"14.2초"}` | `["[대화 t-012]", "“q”", "n"]` / `["[집계 latency_ms.total.p95]", "14.2초"]` |
| V-QH-09b | `evidenceLines("발췌")` / `{foo:"q", user:"사용자 A"}` / `42` | `["발췌"]` / `["foo: q", "user: 사용자 A"]` / `["42"]` |
| V-QH-10 | 이름표(`PROPOSAL_STATUS_LABEL`·`REPORT_STATUS_LABEL`·`TARGET_LABEL`·`PRIORITY_LABEL`·`EVIDENCE_TYPE_LABEL`·`STEP_LABEL`·`STEP_RESULT_LABEL`) 키 집합 | 타입의 모든 값 포함(빠짐 없음), 값은 spec §6.1·§6.8과 같음 |
| V-QH-11 | `listReports()` / `listReports("", "2026-11-22")` | URL `/api/admin/quality/reports` / `…?to=2026-11-22`, GET, CSRF 헤더 없음 |
| V-QH-12 | `listProposals("adopted")` / `listProposals()` | `…/proposals?status=adopted` / `…/proposals`, 응답의 `proposals` 배열 반환 |
| V-QH-13 | `decideProposal(7, "held", "")` | POST `/api/admin/quality/proposals/7/decision`, 본문 `{"status":"held","note":null}`, `X-CSRF-Token` 있음 |
| V-QH-14 | 서버 409 `{"code":"proposal_status_conflict",…}` | `ApiError` code 그대로 |

#### B2. `web/tests/unit/proposal-card.test.tsx` (Testing Library, fetch 가짜)

| ID | 시나리오 | 기대 |
|---|---|---|
| V-PC-01 | status `new` 카드 | [채택][보류][기각] 모두 활성, "채택해도 자동으로 바뀌는 것은 없어요." 보임 |
| V-PC-02 | status `adopted`, 메모 "m" | [채택]만 비활성, 메모 칸 처음 값 "m", 결정 정보 줄에 관리자 이름·KST 일시 |
| V-PC-03 | [기각] 클릭 → 200 | 처리 중 버튼 3개 비활성, 끝나면 `role="status"` "개선안을 기각했어요.", `onDecided` 1회(응답 객체) |
| V-PC-04 | 409 | `role="alert"`에 서버 문구, `onConflict` 1회 |
| V-PC-05 | 텍스트 필드에 `<b>x</b>`·`**y**`·`[a](http://evil)` | 글자 그대로 보임, `<b>`·`<a>` 요소 없음 |
| V-PC-06 | `report_id null`, `evidence []`, `showReportLink` | "보고서 없음(90일이 지나 정리됨)", "근거 발췌가 정리됐어요(90일 지남)." |
| V-PC-07 | 선택 필드 `cause`·`risk` null | 해당 줄 없음 |
| V-PC-08 | 메모 칸 | `maxLength=1000`, 남은 글자 수 표시 |

---

### C. Playwright — `web/e2e/admin-quality.spec.ts`

가짜 응답: `page.route("**/api/auth/me")`로 관리자, `page.route("**/api/admin/quality/**")`로 `web/e2e/fixtures/quality/*.json`.

| 파일 | 내용 |
|---|---|
| `list.json` | 보고서 5개(done·done+`steps.attack_set=failed`·skipped·failed·running), done에 headline 값, 결정 대기 2 |
| `detail.json` | `SAMPLE_STATS` + 모르는 키 `zzz` + 개선안 3개(24 §12.4 evidence 모양) + `body_md`에 표·`<script>alert(1)</script>`·`![x](http://127.0.0.1:9/x.png)`·`[클릭](https://evil.example)` |
| `detail-broken.json` | `stats: {verification: "oops", attack_set: 5}` |
| `detail-failed.json` | status failed, `FAILED_STATS`, error 글 |
| `detail-skipped.json` | status skipped, `SKIPPED_STATS` |
| `detail-partial.json` | status done, `steps.attack_set "failed"`, `attack_set {status:"failed", error:"TimeoutError: …", total:null, …}` |
| `proposals-adopted.json` | 채택 2건(하나는 `report_id null`) |

| ID | 시나리오 | 기대 |
|---|---|---|
| P-QH-01 | `list.json`, `/admin/quality` | 표 5줄(최신 위), 실패 줄 "실패", 일부 실패 줄 "완료(일부 실패)", 건너뜀 줄 "건너뜀"·공격 방어율만 값, headline 없는 줄은 "—", "결정 대기 2" 굵게, "개발 후보 보기" 링크 |
| P-QH-02 | 날짜 2026-11-01~11-10 → [조회] | 두 번째 요청 URL에 `from=2026-11-01&to=2026-11-10`, 첫 요청은 쿼리 없음 |
| P-QH-03 | `detail.json` | 소제목 10개(대화 … 평가 실행), "채점 기준 v1", 공격 유형 표 9줄(한글 이름, 23 순서), 실패 id 2개, "기타 집계"에는 `zzz` 줄만, 개선안 카드 3개(높음 먼저), 근거 "[대화 t-012]" 글자(링크 아님) |
| P-QH-04 | 〃 보안 | `body_md` 표는 보임, `<script>` 실행 안 됨(`page.on("dialog")` 0회), `img` 요소 0개 + `127.0.0.1:9` 요청 0회, "클릭"은 `a` 아님 |
| P-QH-05 | `detail-broken.json` | 페이지 오류 없음(`pageerror` 0회), "기타 집계"에 `verification`·`attack_set` 줄 |
| P-QH-06 | `detail-failed.json` | "보고서를 만들지 못했어요." + error 글 + `nadri eval quality --date` 안내 + 단계 결과 표(채점 "실패"), 집계 소제목·개선안 영역 없음, "기타 집계" 없음 |
| P-QH-06b | `detail-skipped.json` | "어제는 대화가 없어…" 안내, 집계는 대화 비용·보안·공격 질문 세트·평가 실행만, 대화·채점 절 없음 |
| P-QH-06c | `detail-partial.json` | "일부 단계가 실패했어요." + 단계 표(공격 질문 세트 "실패" 빨간 글), 공격 절에 "실행하지 못했어요" + error, 다른 절은 정상 |
| P-QH-07 | `/admin/quality/abc` | API 요청 0회, "품질 보고서를 찾을 수 없어요." |
| P-QH-08 | 상세에서 카드 [채택] → 가짜 200 | 요청 본문 `{"status":"adopted","note":…}`, 성공 문구, 카드 상태 "채택(개발 후보)" |
| P-QH-09 | `proposals-adopted.json`, `/admin/quality/proposals` | 기본 탭 "개발 후보(채택)", 2건, `report_id null` 카드에 "보고서 없음(90일이 지나 정리됨)", 설명에 "자동으로 바뀌지 않아요" |
| P-QH-10 | 개발 후보 탭에서 [기각] → 가짜 200(status rejected) | 카드 사라지고 "개선안을 기각했어요." 남음 |
| P-QH-11 | 메뉴 | `/admin/quality/12`·`/admin/quality/proposals`에서 "품질" 링크 `aria-current="page"`, 클릭 시 `/admin/quality` |
| P-QH-12 | `mobile-chrome`, `detail.json` | 페이지 가로 넘침 없음(19 P-UG-06 방식) |
| P-QH-13 `@real` | `makeAdmin` → `makeQualityReport()`(psql: `eval_reports` `report_date '2000-01-0N'`·`model 'e2e'`·stats 일부 + `improvement_proposals` 1건 title `e2e_<시각>` status new) → 로그인 → `/admin/quality/{id}` → 메모 "e2e 메모" 입력 → [채택] → `/admin/quality/proposals` | 개발 후보 탭에 그 제목 카드, 메모 "e2e 메모", 결정자 = 그 관리자. psql로 `status='adopted'`, `decided_by` = 관리자 id 확인 |
| P-QH-14 `@real` | 같은 개선안 [채택] 다시(API 직접, `page.request`) | 409 `proposal_status_conflict` |
| P-QH-15 `@real` | e2e 일반 사용자로 `page.request.get("/api/admin/quality/reports")`·결정 POST | 403 `forbidden` |

- `@real` 정리: `global-setup.ts`(spec §8 #4)가 다음 실행 때 e2e 개선안 → 보고서 → 사용자 순으로 지운다.

### 통과 기준
- A·B·C 전부 통과(`@real` 포함), 실패 0.

---

## ② HITL

전제: 24 병합 후 compose, `nadri create-admin`으로 만든 관리자, 전날 실제 대화가 있고 03:00 배치(또는 `docker compose run --rm ingest nadri eval quality --date <어제>`)로 보고서가 만들어진 상태. 브라우저는 Windows에서 `http://localhost:8080`(또는 터널 주소).

### HITL-1 화면 흐름
1. 관리자 로그인 → 메뉴 "품질" → 목록에 어제 날짜 보고서, 상태 "완료", 핵심 지표 5개가 "—"가 아닌지(대화가 있던 날).
2. 보고서를 열어 요약·집계·개선안을 읽는다. 공격 질문 세트 방어율과 실패 id가 보이는지.
3. 개선안 3건에 각각 채택·보류·기각(메모 1개 이상) → "개발 후보 보기"에서 채택 1건이 보이는지.
4. 보류한 것을 채택으로 바꾸기 → 메모 칸에 이전 메모가 미리 채워져 있었는지, 개발 후보에 2건.
5. psql로 확인:
   ```bash
   docker compose exec postgres psql -U postgres -d nadri -c "
   select id, status, decision_note, decided_by, decided_at from improvement_proposals order by decided_at desc nulls last limit 5"
   ```
6. 채택 후 `git status`·`backend/src/nadri/prompts/` 변경 없음, 다음 날 답변 동작도 그대로인지(자동 적용 없음 — ADR-23).
7. 휴대폰(터널 주소)으로 같은 화면 — 표만 옆으로 밀리고 카드 버튼이 눌리는지.
8. 일반 사용자로 `/admin/quality` 주소 직접 열기 → "접근 권한이 없어요.", 네트워크 탭에 `/api/admin/quality` 요청 없음.

### HITL-2 24 집계 키 맞춤 (중요)
1. 실제 보고서의 `stats`를 뽑는다:
   ```bash
   docker compose exec postgres psql -U postgres -d nadri -At -c "select jsonb_pretty(stats) from eval_reports order by report_date desc limit 1"
   ```
2. 상세 화면 "기타 집계"가 **비어 있어야** 한다(24 §9 = 25 §6.4). 줄이 있으면 24 구현이 §9와 다르거나 25 가드가 틀린 것 → 그 키 이름을 기록해 보고.
3. 목록 핵심 지표 5개가 상세 값과 같은지, 상세 집계 숫자가 본문(`body_md`) 표의 숫자와 같은지.

### HITL-3 실패·건너뜀 보고서
1. 일부러 실패를 만들 수 없다면 psql로 가짜 보고서를 넣는다:
   ```bash
   docker compose exec postgres psql -U postgres -d nadri -At -c "insert into eval_reports(report_date, status, error, model) values ('2000-02-01','failed','테스트 오류','e2e') returning id"
   ```
2. 목록 기간을 2000-02-01로 조회 → "실패", 상세에 오류 글과 다시 실행 명령 안내.
3. 지우기: `docker compose exec postgres psql -U postgres -d nadri -c "delete from eval_reports where model='e2e'"`.

### HITL 결과 보고
| 항목 | 결과 |
|---|---|
| HITL-1 목록·상세·결정·개발 후보·결정 변경·자동 적용 없음·휴대폰·일반 사용자 차단 | |
| HITL-2 24 실제 stats 키 vs §6.4 표(안 맞는 키 목록) | |
| HITL-3 실패 보고서 표시 | |
