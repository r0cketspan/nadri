# 24-eval-daily-quality — 테스트 설계 (test)

> spec.md와 짝. 절 번호 §n은 spec.md 기준. 작성 2026-11-22. 상태: **확정(2026-11-28, 확인 질문 전부 추천안대로)**(spec §22).
> ① pytest(결정적 — 실제 OpenAI·tour-tools·LightRAG 호출 없음. 평가·요약·개선안 모델은 가짜 러너, 공격 세트는 가짜 `run_attack`. DB가 필요한 것은 04 테스트 컨테이너, 마커 `db`) ② HITL(사용자가 실제 하루치 보고서·개선안을 읽고 채점 기준을 판단).

---

## ① pytest

### 0. 공통
- 실행: `cd ~/code/myAgent/backend && uv run pytest -m "not integration"` (Docker 필요). DB 없는 것만: `-m "not integration and not db"`.
- 재사용: 04 `db_sf`·`make_user`, 09 `make_session`, 02 `usage_from_message` 대역 AIMessage, 21 `JobSpec`·`build_scheduler`·고정 시계, 20 잠금 테스트 방식.
- 추가 헬퍼(`tests/eval/quality_helpers.py`):

| 이름 | 역할 |
|---|---|
| `raw_turn(**kw)` | `RawTurn` 기본값(`message_id=1`, `user_id=10`, `session_id=UUID(int=1)`, `turn_no=1`, `created_at=2026-12-04 10:00 KST`, `question="경복궁 휴무일?"`, `answer="매주 화요일 휴무예요 (#126508)"`, `from_cache=False`, `verify_status="passed"`, `rewrite_count=0`, `tool_results=[{name:"rag_query",…}]`, `verification={"max_rewrites":2,"attempts":[…]}`, `timings={ttft_ms:2000,total_ms:6000,…}`) + 덮어쓰기 |
| `raw_event(**kw)` | `RawSecurityEvent` 기본값 |
| `day(turns, events=(), cost=None, date="2026-12-04")` | `DayData` |
| `score(acc=2, res=2, tool=2, vj="agree", gap=None, issues=())` | `TurnScore` |
| `FakeRunner(outputs)` | `ainvoke`가 차례로 `{"raw": AIMessage(usage_metadata=…), "parsed": …, "parsing_error": None}`를 돌려줌. 항목이 예외면 raise, `"sleep"`이면 오래 대기(타임아웃 시험). 받은 메시지를 `calls`에 기록 |
| `attack_ok(total=60, passed=57)` / `attack_fail(exc)` | 가짜 `run_attack` |
| `seed_day(db_sf, date)` | DB에 사용자 2명·세션 3개·턴(답변 5, 캐시 1)·피드백(👍1·👎2)·보안 이벤트(masked 1·classifier blocked 1·output rewritten 1)·usage_events(answer·verify·classify·moderation·embed·hub·eval) 넣기. 날짜 경계 밖(전날 23:59:59, 다음 날 00:00:00) 행도 1개씩 |

### 1. 날짜 창 (DB 없음) — `tests/eval/test_quality_window.py`

| ID | 입력 | 기대 |
|---|---|---|
| U-QW-01 | `day_window(2026-12-04)` | start `2026-12-04T00:00+09:00`, end `2026-12-05T00:00+09:00` |
| U-QW-02 | `previous_kst_date(2026-12-05T03:00+09:00)` | `2026-12-04` |
| U-QW-03 | `previous_kst_date(2026-12-04T18:30Z)` (= KST 12-05 03:30) | `2026-12-04` |
| U-QW-04 | naive datetime | `ValueError` |

### 2. 수집 (마커 `db`) — `tests/eval/test_quality_collect.py`

| ID | 준비 | 기대 |
|---|---|---|
| A-QC-01 | `seed_day` | 답변 턴 = 창 안 assistant 행만(경계 00:00:00 다음 날 행 제외, 전날 23:59:59 제외), created_at 순 |
| A-QC-02 | 턴 2의 직전 턴 존재 | `prev_question`·`prev_answer` 채움, 첫 턴은 None |
| A-QC-03 | 피드백 👎 wrong | `feedback_rating="down"`, `feedback_reason="wrong"` |
| A-QC-04 | user 행 없는 assistant 행 | 건너뜀 + 경고 로그(메시지 id만, 글 없음 — caplog) |
| A-QC-05 | 보안 이벤트 | 창 안 것만, 모든 단계 |
| A-QC-06 | 사용량 | `cost_by_kind`에 `hub`·`eval`·`proposal` 없음, 나머지 kind별 Decimal 합·건수 |
| A-QC-07 | 수집 중 대화 테이블 쓰기 없음 | 실행 전후 `chat_messages`·`message_feedback`·`faq_cache` 행 수·내용 동일 |

### 3. 채점 대상 고르기 (DB 없음) — `tests/eval/test_quality_select.py`

| ID | 준비 | 기대 |
|---|---|---|
| U-QS-01 | 캐시 턴 1 + 보통 2 | 캐시 제외, 2개 |
| U-QS-02 | 보통(10:00)·rewrite 1(11:00)·failed(12:00)·👎(13:00), 상한 2 | 고른 것 = 👎·failed, `over_limit=2` |
| U-QS-03 | 같은 순위 3개, 상한 2 | created_at 앞선 2개 |
| U-QS-04 | 고른 턴 | created_at 순으로 다시 정렬 |
| U-QS-05 | `security_replaced` | failed와 같은 순위 |
| U-QS-06 | 빈 목록 | `([], 0)` |

### 4. 익명화 (DB 없음) — `tests/eval/test_anonymize.py`

| ID | 입력 | 기대 |
|---|---|---|
| U-AN-01 | 턴 3개(user_id 10·20·10, 세션 다름), 이벤트 1개 → `anonymize_day` 결과를 **JSON 직렬화**(ref_to_message 제외) + `evaluate_messages` 모든 글 | 문자열 `"10"`·`"20"`(user_id), 세션 UUID, message_id, 테스트 사용자 이메일·아이디가 **어디에도 없음** |
| U-AN-02 | `alias_label` 0·25·26·27·701 | A·Z·AA·AB·ZZ |
| U-AN-03 | 처음 본 순서: 이벤트(user 20, 09:00) → 턴(user 10, 10:00) | user 20 = 사용자 A, user 10 = 사용자 B |
| U-AN-04 | 이벤트 user_id None | "알 수 없음" |
| U-AN-05 | 질문에 `010-1234-5678`(옛 규칙으로 안 가려진 경우를 흉내) | `EvalItem.question`에서 가려짐 |
| U-AN-06 | 이미 가린 질문 `010-****-****` | 그대로(멱등) |
| U-AN-07 | 답변에 관광지 전화 `02-3700-3900` | `EvalItem.answer`는 **그대로**(가리지 않음 — 24-Q15) |
| U-AN-08 | 툴 결과 | `ms`·`contentids`·`urls` 빠짐, `name`·`args`·`content`·`truncated`·`is_error` 유지 |
| U-AN-09 | 직전 턴 질문·답변 500자 | 300자로 잘림, 직전 질문도 가림 적용 |
| U-AN-10 | `mask_excerpt("a"*400)` / None / 이메일 포함 | 300자 + "…" / None / 가려짐 |
| U-AN-11 | 보안 이벤트 `at` | "HH:MM" KST, 날짜·초 없음 |
| U-AN-12 | `verify_attempts` | `quote` 없음, `kind`·`detail`만 |
| U-AN-13 | `AliasBook`을 두 번 만들기 | 서로 독립(전역 상태 없음) — 대응표 저장 안 함 |

### 5. 평가 에이전트 호출 (DB 없음) — `tests/eval/test_quality_score.py`

| ID | 준비 | 기대 |
|---|---|---|
| U-SC-01 | `evaluate_messages(item)` | [SystemMessage(evaluate.md 내용), HumanMessage 1개], 순서 §8.2(이전 턴 → 질문 → 답변 → 자료 → 검증) |
| U-SC-02 | 👎 받은 턴 | HumanMessage에 피드백 흔적 없음("👎", "down", "wrong", "피드백" 미포함 — 24-Q3) |
| U-SC-03 | 툴 결과 내용에 `</자료>` 포함 | 02 `wrap_as_material` 규칙으로 바뀜(구분자 깨지지 않음) |
| U-SC-04 | 툴 결과 없음 | `<자료 없음/>` |
| U-SC-05 | 오류 툴 결과 | `도구="… (오류)"` |
| U-SC-06 | 지연·비용·별칭 | HumanMessage에 없음 |
| U-SC-07 | `FakeRunner([parsed ok])` | `(TurnScore, UsageRecord(kind="eval", model=…))` |
| U-SC-08 | `parsing_error` 있음 / `parsed=None` | `EvalParseError` |
| U-SC-09 | `"sleep"` + `EVAL_CALL_TIMEOUT_S` 몽키패치 0.01 | `asyncio.TimeoutError` |
| U-SC-10 | `score_items` 3턴 중 2번째 실패 | `scores` 2개, `failed=["t-002"]`, 순서대로 1회씩 호출(동시 없음 — 러너 호출 기록 시각 겹침 없음) |
| U-SC-11 | `TurnScore` 스키마: `accuracy=3` / `issues` 4개 / `data_gap` 81자 | 검증 오류 |
| U-SC-12 | `build_evaluator` | 구조화 출력이 `json_schema`·`include_raw=True`, 캐시 키 `nadri-eval-v1`(가짜 llm 기록) |
| U-SC-13 | `is_good` | (2,2)=True, (None,2)=True, (1,2)=False, (2,1)=False, (0,2)=False |

### 6. 집계 (DB 없음) — `tests/eval/test_quality_stats.py`

| ID | 입력 | 기대 |
|---|---|---|
| U-ST-01 | **스키마**: 아무 입력으로 `build_stats` | 키 집합·값 타입이 spec §9 표와 같음(표를 테스트 안 상수로 옮겨 재귀 비교) |
| U-ST-02 | 대화 0건 | 같은 키 집합, 수 0, 비율·평균 null, steps scoring/summary/proposals = skipped |
| U-ST-03 | `percentile([100..1000],50/95)`, `[]` | 500·1000, None |
| U-ST-04 | 점수 accuracy [2,2,0,None], resolution [2,1,2,2] | avg accuracy 1.33(None 제외), dist accuracy `{"0":1,"1":0,"2":2,"na":1}`, good 2(턴1·턴4), good_rate 0.5 |
| U-ST-05 | verify_judgement 집계 | 네 키 모두 있음 |
| U-ST-06 | verification: passed 3·failed 1·security_replaced 1·cached 1, rewrite [0,0,1,2,2] | n 5(캐시 제외), pass_rate 0.6, rewrites `{"0":2,"1":1,"2":2}` |
| U-ST-07 | `max_rewrites_seen` 값 2·2·1 | `[1,2]` |
| U-ST-08 | latency: 캐시 턴·`ttft_ms` null 섞임 | ttft·total은 캐시·null 제외, `cached_total` 따로 |
| U-ST-09 | cost: answer 0.01·verify 0.005 Decimal, 답변 4 + 차단 1 | `chat_total="0.01500000"`, `per_turn="0.00300000"`, 문자열 |
| U-ST-10 | 분모 0(답변·차단 0) | `per_turn` null |
| U-ST-11 | feedback: 👍1·👎2(wrong·사유 없음)·없음 2 | up 1, down 2, none 2, reasons wrong 1·unspecified 1 |
| U-ST-12 | agreement: 👍&좋음, 👎&나쁨, 👎&좋음, 👍&채점 실패 | n 3, agree 2, rate 0.6667, `disagree_refs`=[👎&좋음 ref] |
| U-ST-13 | security mapping: moderation blocked / moderation self_harm_guide / classifier blocked [jailbreak] / output rewritten | blocked_by_code unsafe 1·self_harm 1·jailbreak 1, by_outcome·by_check 모든 키 존재 |
| U-ST-14 | `turns_blocked` | stage=input && outcome ∈ blocked·self_harm_guide 수(guard_error 제외) |
| U-ST-15 | pii_types: masked 이벤트 categories [phone,email],[phone] | phone 2·email 1, 07 PII_TYPES 전부 키 |
| U-ST-16 | samples: 이벤트 15개(masked 5 포함) | masked 제외, 최근 순 최대 10, excerpt 가려짐 |
| U-ST-17 | attack ok(60/57, by_type) | defense_rate 0.95, by_type rate 계산 |
| U-ST-18 | attack failed | status failed, total·passed·defense_rate null, error 채움 |
| U-ST-19 | 비율 반올림 | 2/3 → 0.6667, avg 4/3 → 1.33 |
| U-ST-20 | `stats` 직렬화 | `json.dumps` 성공(Decimal 없음 — 문자열), user_id·세션 없음 |
| U-ST-21 | failed용 부분 stats | `schema`·`rubric_version`·`report_date`·`steps`만 |

### 7. 요약·본문 (DB 없음) — `tests/eval/test_quality_report.py`

| ID | 입력 | 기대 |
|---|---|---|
| U-RP-01 | `summarize_report` 입력 | briefs에 질문·답변 글 없음, stats에서 steps·eval_run 빠짐 |
| U-RP-02 | 요약이 모르는 ref `t-999` 포함 | data_gaps에서 버려짐, count = 남은 refs 수 |
| U-RP-03 | topic에 전화번호 | 가려짐 |
| U-RP-04 | 요약 실패 시 data_gaps | 채점 `data_gap` 글이 같은 것끼리 묶임(대소문자·공백만 정리) |
| U-RP-05 | `render_body` 스냅샷(보통 날) | §10.2 절 순서, 수치가 stats와 같음 |
| U-RP-06 | 공격 세트 실패·개선안 실패 | 맨 위 경고 줄 2개 |
| U-RP-07 | 대화 0건 | 제목 + 건너뜀 문구 + 공격 세트 절만 |
| U-RP-08 | 점수 낮은 턴 12개 | 10개, 정렬 규칙(정확성 → 해결 → 👎), 질문 120자·가림 |
| U-RP-09 | 본문 | `<`로 시작하는 HTML 태그·이미지 문법 `![` 없음(코드가 넣지 않음) |
| U-RP-10 | 설정과 관측 다름(`VERIFY_MAX_REWRITES=2`, 관측 [1]) | 본문에 경고 한 줄 |

### 8. 공격 세트 연결 (DB 없음) — `tests/eval/test_quality_attack.py`

| ID | 준비 | 기대 |
|---|---|---|
| U-AT-01 | 23 `AttackReport` 대역(`by_type` 9유형 — jailbreak total 8·passed 8, 한 유형 total 0, `total=58`, `passed=54`, `defense_rate=0.931034`, `failed_ids=[2개]`, `cost_usd=Decimal("0.0412")`, `items`·`moderation_detection`에 원문 넣어 둠) → `to_attack_summary` | status done, by_type 9키·rate 1.0·0건 유형 rate None, defense_rate 0.931, failed_ids 그대로, cost_usd Decimal, 결과 직렬화에 `items` 원문 없음 |
| U-AT-04 | `run_attack` 호출 인자(가짜 `run_attack_set` 기록) | `run_attack_set(settings)` 한 번, 키워드 인자 없음 |
| U-AT-05 | 가짜 `run_attack_set`이 `asyncio.CancelledError` | 그대로 올라감(failed로 바꾸지 않음) |
| U-AT-02 | `run_attack`에서 23 함수가 `AttackSetError` / `RuntimeUnavailable` / `ValueError` | 각각 `status="failed"`, error `"<클래스>: …"`(300자), 예외 다시 안 올림 |
| U-AT-03 | `total=0`(모두 미시험) | `defense_rate` None, by_type rate 모두 None |

### 9. 개선안 (DB 없음 + `db`) — `tests/eval/test_proposals.py`

| ID | 준비 | 기대 |
|---|---|---|
| U-PR-01 | 스냅샷: 가짜 프롬프트에 `CANARY` 포함 | `[카나리 문자열]`로 바뀜, `contains_canary(snapshot_text)` False |
| U-PR-02 | `tools_loader` 예외 | `tools=[]`, `tools_unavailable: true`, 예외 없음 |
| U-PR-03 | `snapshot_sha256` | 같은 입력 같은 값, 프롬프트 1글자 바꾸면 다름 |
| U-PR-04 | `propose_messages` | 4개 구획(보고서·턴 요약·현재 설정·기존 개선안), 별칭 없음 |
| U-PR-05 | `clean_proposals`: turn ref 모름 1·알 1 | 아는 것만 남음 |
| U-PR-06 | 근거 전부 모르는 ref | 그 개선안 버림 + 로그 `no_evidence` |
| U-PR-07 | stat ref `latency_ms.total.p95`(있음) / `latency_ms.foo`(없음) / `security.samples[2]`(범위 밖) | 있음만 남음 |
| U-PR-08 | attack ref = failed_ids 안 / 밖 | 안만 남음 |
| U-PR-09 | quote·problem에 이메일 | 가려짐 |
| U-PR-10 | title 공백 | 버림 / cause 공백 → NULL |
| U-PR-11 | priority low·high·medium 순 입력 | seq 1=high, 2=medium, 3=low |
| U-PR-12 | `ProposalSet` 6건 | 스키마 오류 |
| U-PR-13 | `ProposalDraft.target` Literal | 04 `PROPOSAL_TARGETS`와 정확히 같음(상수 대조, `faq_cache` 포함 8개) |
| U-PR-14 | 행 dict | `status="new"`, decision 3칸 None, 키 = `improvement_proposals` 컬럼 부분집합 |
| A-PR-15 (`db`) | `load_open_proposals`: new(10일 전)·held·adopted·rejected·new(40일 전)·31건 | rejected·40일 전 제외, 최신 30건, 본문 필드 없음 |
| A-PR-16 (`db`) | `data_scope` | 지역×유형별 active·detailed 수, 소프트 삭제 제외 |

### 10. 작업 흐름·저장 (마커 `db`) — `tests/ingest/test_daily_quality.py`
가짜 러너 3개(평가·요약·개선안), 가짜 `run_attack`, 고정 시계로 `run_daily_quality` 실행.

| ID | 준비 | 기대 |
|---|---|---|
| A-JOB-01 | `seed_day` + 모두 성공 | `eval_reports` 1행 `done`, `eval_scores` = 채점 턴 수(캐시 제외), 개선안 `new` n행, `model` 채움, `finished_at` 채움, `stats.steps` 모두 done |
| A-JOB-02 | 실행 중간(채점 단계)에서 DB 조회 | 행 `running` 이 먼저 커밋되어 보임 |
| A-JOB-03 | 대화 0건 | `skipped`, 평가·요약·개선안 러너 호출 0, 공격 세트 1회, `stats.attack_set` 채움 |
| A-JOB-04 | 차단만 있는 날 | `done`, 채점 skipped, 개선안 러너 호출 1 |
| A-JOB-05 | 같은 날 `done` 있음 | `ReportExists`, 러너 호출 0 |
| A-JOB-06 | `failed` 행 있음 | 같은 id 재사용, error NULL로 → done |
| A-JOB-07 | `running` 행 있음(죽은 실행) | 같은 id 재사용 |
| A-JOB-08 | `--force` + 개선안 전부 new | 옛 행·점수·개선안 삭제 후 새 id |
| A-JOB-09 | `--force` + 개선안 하나 adopted | `ReportHasDecisions`, 아무것도 안 바뀜 |
| A-JOB-10 | 채점 전부 실패 | `failed`, error "평가 에이전트 호출이 모두 실패…", 점수·개선안 0행, 사용량 기록됨 |
| A-JOB-11 | 채점 1개 실패 | `done`, steps.scoring partial, 점수 행 = 성공 수 |
| A-JOB-12 | 공격 세트 실패 | `done`, steps.attack_set failed |
| A-JOB-13 | 요약 실패 | `done`, steps.summary failed, 본문 "요약을 만들지 못했어요" |
| A-JOB-14 | 개선안 실패 | `done`, 개선안 0행, steps.proposals failed |
| A-JOB-15 | 저장 단계 예외(가짜로 점수 INSERT 실패) | 점수·개선안 0행(롤백), 행 `failed`, error에 "save" |
| A-JOB-16 | 사용량 | `usage_events`에 kind eval(채점 n + 요약 1)·proposal 1행, user_id·message_id NULL, cost = 11 `cost_usd` |
| A-JOB-17 | 실패해도 사용량 | A-JOB-10에서 실패 호출 중 raw가 있던 것 기록 |
| A-JOB-18 | `eval_scores.scores` | §9.1 키, ref가 개선안 evidence turn ref와 대응, issues 가림 |
| A-JOB-19 | 익명성 전수 | `body_md`·`stats`·`evidence` 전체 글에 user_id·세션 UUID·사용자 이메일·아이디 없음 |
| A-JOB-20 | 대화 테이블 불변 | 실행 전후 `chat_messages`·`message_feedback`·`faq_cache`·`security_events` 동일(24는 읽기만) |
| A-JOB-21 | 잠금: 다른 연결이 키 2 보유 | `LockBusy`, 행 없음 |
| A-JOB-22 | 잠금: 다른 연결이 키 1 보유 | 정상 실행(서로 안 막음) |
| A-JOB-23 | `stats.eval_run` | calls·cost(문자열)·proposals_created·config_sha256 채움 |
| A-JOB-24 | 90일 연결: 결과 행을 21 `run_cleanup`(now = report_date+91일) | 보고서·점수 삭제, new 개선안 삭제, adopted는 evidence `[]`·report_id NULL (21·04 규칙과 맞물림 확인) |

### 11. 자동 변경 경로 없음 — `tests/eval/test_no_auto_apply.py`

| ID | 검사 | 기대 |
|---|---|---|
| U-NOAUTO-01 | `nadri/eval/{anonymize,quality,proposals}.py`·`nadri/ingest/jobs/daily_quality.py` 소스를 AST로 훑기 | `open(…, "w"/"a"/"x")`, `write_text`, `write_bytes`, `subprocess`, `os.system`, `shutil`, `git` 호출, `nadri.ingest.wiki.git` import 없음 |
| U-NOAUTO-02 | 같은 파일들이 `prompts` 패키지에서 쓰는 함수 | `load_prompt`·`fixed_messages`(읽기)만 |
| U-NOAUTO-03 | A-JOB-01 실행 전후 `nadri/prompts/` 파일 해시 | 같음 |

### 12. 스케줄러·따라잡기 (DB 없음 + `db`) — `tests/ingest/test_scheduler_quality.py`

| ID | 준비 | 기대 |
|---|---|---|
| U-SCH-01 | `default_jobs` | `daily_sync@01:00`, `daily_quality@03:00` 두 개 |
| U-SCH-02 | `build_scheduler` 등록 | daily_quality CronTrigger hour 3·minute 0·Asia/Seoul, coalesce·max_instances 1 |
| A-SCH-03 | `quality_catch_up(now=12-05 09:00)`, 12-04 행 없음 | True |
| A-SCH-04 | 같은 now, 12-04 `failed` 행 | False |
| U-SCH-05 | now=12-05 02:00 | False(곧 정시 실행) |
| A-SCH-06 | 12-03 행 없음·12-04 행 있음 | False(이틀 전은 따라잡지 않음) |
| U-SCH-07 | 래퍼: `LockBusy` / `ReportExists` / 기타 예외 | INFO / INFO / ERROR 1줄, 예외 안 올림, 로그에 대화 글 없음 |
| U-SCH-08 | 시작 로그 | `jobs=[daily_sync@01:00 KST, daily_quality@03:00 KST]` |

### 13. CLI (DB 없음, 실행 함수 몽키패치) — `tests/test_cli_eval_quality.py`

| ID | 인자 | 기대 |
|---|---|---|
| U-CLI-01 | `--date` 없음 / `2026-13-01` | 2 |
| U-CLI-02 | 오늘·미래 날짜(고정 시계) | 2 |
| U-CLI-03 | 91일 전 | 2, 안내 문구 |
| U-CLI-04 | 결과 done / skipped / failed | 0 / 0 / 1 |
| U-CLI-05 | `ReportExists` | 0 + "--force" 안내 |
| U-CLI-06 | `--force` + `ReportHasDecisions` | 2 |
| U-CLI-07 | `LockBusy` | 4 |
| U-CLI-08 | `OPENAI_API_KEY` 없음 | 2 |
| U-CLI-09 | 진행 줄 | ref·점수·수만, 질문·답변 글 없음(capsys) |

### 14. 앞 작업 회귀
- 20·21 잠금·스케줄러 테스트, 11 `UsageRecord` Literal ⊆ `USAGE_KINDS`, 04 스키마 테스트(`PROPOSAL_TARGETS`에 `faq_cache` — 04 기대값 갱신), 22 compose 기대값(`x-tuning` 블록이 api·tour-tools·ingest에), 23 `UsageRecord` Literal(`eval`은 23, `proposal`은 24).

### 통과 기준
- 위 전부 통과, `-m "not integration"`에서 실패 0.

---

## ② HITL

전제: 24 적용 compose, 23 병합(공격 세트), 전날 실제 대화가 몇 턴 이상(없으면 그날 직접 질문 10~20개 — 👍/👎 몇 개, 일부러 데이터에 없는 질문·후속 질문 섞기).

### HITL-1 수동 실행
`docker compose exec ingest nadri eval quality --date <어제>`
- 확인: 진행 줄, 종료 코드 0, 마지막 줄 비용. `docker compose logs ingest`에 대화 글 없음.
- `psql`로 `SELECT status, stats->'steps', stats->'eval_run' FROM eval_reports WHERE report_date='<어제>';`, `SELECT count(*) FROM eval_scores …`, `SELECT seq, target, priority, title FROM improvement_proposals WHERE report_id=…`.
- 비용: `stats.eval_run.cost_usd.total` + `attack_set.cost_usd`를 spec §17 추정과 비교 → §19 기록.

### HITL-2 채점 기준 판단 (사용자 — 핵심)
에이전트가 `body_md`와 점수가 낮은 턴·👎 턴·무작위 5턴의 (가린 질문·답변·점수·지적)을 표로 보여 준다(사용자 본인 대화이므로 확인 가능).
- 사용자가 판단: ① 정확성 0/1/2가 사람 판단과 맞나 ② 엄격함이 적당한가(너무 깐깐/너그러움) ③ 툴 선택·검증 판단 점수가 납득되나 ④ 데이터 부족 주제가 쓸모 있나 ⑤ 👍/👎 불일치(`disagree_refs`) 사례에서 누가 맞나.
- 고칠 점이 있으면 `evaluate.md` 수정 + `RUBRIC_VERSION` 올림 → `--force`로 같은 날 다시 → 다시 판단. 결과를 PROGRESS 결정 로그에.

### HITL-3 개선안·익명성 확인
- 개선안마다: 근거가 실제 문제를 가리키나, 제안이 구체적인가, 자동으로 무엇이 바뀐 흔적이 없나(`git status` 깨끗, 프롬프트 파일 그대로).
- 익명성: `body_md`·`stats`·`evidence` 전체에서 내 아이디·이메일·user_id 숫자 검색 → 없음.

### HITL-4 스케줄·따라잡기
1. ingest를 03:00 전 상태로 두고 03:00 실행 로그 확인(또는 시계를 못 바꾸면 2번으로 대신).
2. 오늘 보고서가 아직 없는 상태에서 `docker compose restart ingest`(03:00 이후) → 로그 `daily_quality start` 1회, 이후 재시작하면 "보고서 있음"으로 안 돎.
3. 대화 없는 날(다음 날 대화 안 하고 확인) → `skipped`, 공격 세트 결과만.

### HITL 결과 보고
| 항목 | 결과 |
|---|---|
| 1 상태·채점 수·개선안 수·실행 시간 | |
| 1 실제 비용 vs §17 | |
| 2 채점 기준 판단(맞음/고침, RUBRIC_VERSION) | |
| 2 👍/👎 일치율·불일치 사례 판단 | |
| 3 개선안 품질 의견, 자동 변경 없음 확인 | |
| 3 익명성 확인 | |
| 4 03:00 실행 / 따라잡기 / skipped | |
| spec §19 미확인 항목(캐시 적중·파싱 실패율·오류 메시지·툴 로딩) | |
