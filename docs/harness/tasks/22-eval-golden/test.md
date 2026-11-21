# 22-eval-golden — 테스트 설계 (test)

> spec.md와 짝. 절 번호 §n은 spec.md 기준. 작성 2026-11-22. 상태: **확정(2026-11-22)**.
> ① pytest(결정적 — 실제 LLM·LightRAG·Tavily·TourAPI 호출 없음. 가짜 모델로 **실제 그래프**를 돌림. DB가 필요한 것은 04 테스트 컨테이너, 마커 `db`) ② HITL(사용자가 직접 — 평가셋 검수, 비교 결과표 보고 설정값 결정).

---

## ① pytest

### 0. 공통
- 실행: `cd ~/code/myAgent/backend && uv run pytest -m "not integration"` (Docker 필요). DB 없는 것만: `-m "not integration and not db"`.
- 재사용: 02 대역(`FakeChatModel`·가짜 verifier·`FakeMCPClient`·가짜 `moderate`), 08 `FakeClassifier`·`MemoryTurnStore`, 09 `TurnPair`·`SessionContext`, 01 tour-tools 테스트의 가짜 LightRAG 응답·가짜 reranker, 04 `db_sf`, 12 `make_tour(db_sf, contentid, *, detail, deleted)`.
- 추가 헬퍼(`tests/eval/helpers.py`):

| 이름 | 역할 |
|---|---|
| `gitem(**kw)` | 골든 문항 dict 기본값(`id="g-fact-001"`, `category="fact"`, `area="서울"`, `question="경복궁 휴무일?"`, `facts=[["화요일"]]`, `as_of="2026-12-01"`) + 덮어쓰기 |
| `write_golden(tmp_path, items, extra_lines=())` | jsonl 파일 생성(주석·빈 줄 끼워 넣기 가능) |
| `va(attempt, *, fact_ok=True, security_ok=True, flagged=False, canary=False, issues=())` | `VerifyAttempt` dict |
| `ur(kind, *, inp=100, cached=0, out=10, model="gpt-6-luna")` | `UsageRecord` dict |
| `capture(answer_texts, verify_log, *, tool_records=(), usage=(), timings=None, masked_types=(), verify_status="passed")` | `TurnCapture(outcome="done", turn=CompletedTurn(…))` |
| `fake_runtime(answers, verdicts, *, classify=None, moderate=None, tools=…)` | 02 `build_graph` + 가짜 모델로 만든 `ChatRuntime`(store=`EvalTurnStore()`, embed=None) |
| `sse(name, data)` | 02 `format_event` 결과 문자열 |

### 1. 평가셋 읽기·검사 (DB 없음) — `tests/eval/test_golden_load.py`

| ID | 입력 | 기대 |
|---|---|---|
| U-GL-01 | 정상 3줄 + 빈 줄 + `#` 주석 줄 | 문항 3개, 순서 유지 |
| U-GL-02 | 2번째 줄 JSON 깨짐 | `GoldenFormatError`, 메시지에 `2:` 줄 번호 |
| U-GL-03 | 같은 id 2개 | 오류 "중복 id" (두 줄 번호 모두) |
| U-GL-04 | 모르는 키 `fact`(오타) | 오류 |
| U-GL-05 | id 형식 `fact-1` / category `food` / area `부산` | 각각 오류 |
| U-GL-06 | `category="fact"`인데 `facts`·`must_not`·`evidence`·`tools_any` 모두 없음 | 오류 "채점 항목 없음" |
| U-GL-07 | `category="smalltalk"`, 채점 항목 없음 | 통과(기본 규칙) |
| U-GL-08 | `group="f1"`인데 `turn` 없음 / `turn=2`만 있고 1 없음 / 1·3 | 각각 오류 |
| U-GL-09 | `facts=[[]]`(빈 OR 목록) / `facts=[["  "]]` | 오류 |
| U-GL-10 | `tools_any=["search"]`(허용 5개 밖) | 오류 |
| U-GL-11 | `evidence.rule` 없음 | `"all"`로 채움 |
| U-GL-12 | 관광 분류(fact 등)인데 `as_of` 없음 / 형식 틀림 | 오류 |
| U-GL-13 | 오류 여러 개 | 한 번에 모두 모아 보고(첫 오류에서 멈추지 않음) |
| U-GL-14 | `golden_sha256` | 파일 바이트 SHA-256과 같음, 주석 한 줄 바꾸면 값 바뀜 |
| U-GL-15 | `select_items(items, ids=["g-f1-002"])` (묶음 f1의 2턴째) | 묶음 f1 전체(1·2턴) 선택 |
| U-GL-16 | `select_items(..., ids=["g-x-999"])` | `ValueError`(→ CLI 2) |
| U-GL-17 | `select_items(..., categories=["web"])` | web 문항만, 파일 순서 |
| U-GL-18 | **레포의 실제 `eval/golden/golden.jsonl`** | 읽기 오류 0, 문항 40~60, §4.2 분류 9개 중에서만, 개인정보 없음(07 `mask_pii(question).types == []`) — 파일이 커밋된 뒤부터 |

### 2. 채점 (DB 없음) — `tests/eval/test_golden_grade.py`

| ID | 문항 · 답변 | 기대 |
|---|---|---|
| U-GR-01 | `norm("오전 9 시 ～ 18：00")` | `"오전9시~18:00"` (NFKC·소문자·공백 제거) |
| U-GR-02 | facts `[["09:00","9시"],["화요일"]]`, 답변 "9시에 열고 화요일 휴무" | correct |
| U-GR-03 | 같은 facts, 답변 "9시에 열어요" | wrong, `failed_checks=["facts:2"]`(몇 번째 항목인지) |
| U-GR-04 | must_not `[["월요일 휴무"]]`, 답변 "월요일휴무입니다" | wrong(공백 무시), `["must_not:1"]` |
| U-GR-05 | tools_any `["web_search"]`, tool_records 이름 `["rag_query"]` | wrong `["tools_any"]` |
| U-GR-06 | tools_any `["web_search"]`, web_search 기록 `is_error=True` | 통과(선택을 봄) |
| U-GR-07 | 입력 차단 `off_topic` | wrong `["blocked:off_topic"]` |
| U-GR-08 | 끝 상태 `security_replaced` | wrong `["security_replaced"]` |
| U-GR-09 | 답변 공백뿐 | wrong `["empty"]` |
| U-GR-10 | `end="error"` | `grade="error"`(정답·오답 아님) |
| U-GR-11 | smalltalk, 채점 항목 없음, 정상 답변 | correct |
| U-GR-12 | 대소문자 "KTX" vs "ktx" | 일치 |
| U-GR-13 | `grade_evidence`: 기대 `["1","2"]` rule all, 인용 `{"1"}` | cited False, recall 0.5 |
| U-GR-14 | 같은 기대 rule any | cited True |
| U-GR-15 | 인용 `{}`, 툴 결과 contentid `{"1","2","9"}` | cited False, retrieved True |
| U-GR-16 | 답변이 `(#7)` 인용했지만 툴 결과에 7 없음 | 7은 인용 근거에서 빠짐(02 `build_sources` 규칙) |
| U-GR-17 | `evidence=None` | 근거 값 모두 None(분모 제외) |

### 3. 잘라 계산 · 사용량 나누기 (DB 없음) — `tests/eval/test_golden_cut.py`

| ID | 준비 | 기대 |
|---|---|---|
| U-CUT-01 | 시도 0 합격 (`answer_texts={0:"A"}`, `verify_log=[va(0)]`), N=2 | cut off/0/1/2 모두 텍스트 "A"; off=`unverified`, 0~2=`passed` |
| U-CUT-02 | 시도 0 사실 실패, 1 합격 | off "A0"·unverified / 0: "A0"·failed / 1·2: "A1"·passed |
| U-CUT-03 | 0 보안 실패(`security_ok=False`), 1 합격 | 0: `safe_replacement` 문구·security_replaced / 1: passed |
| U-CUT-04 | 0 사실, 1 사실, 2 사실 실패 | 0:"A0" failed / 1:"A1" failed / 2:"A2" failed |
| U-CUT-05 | 카나리(`canary=True`)·`moderation_flagged`·보안 issue(`prompt_leak`) 각각 | `security_failed` True. 사실 issue(`fabricated`)만은 False |
| U-CUT-06 | **실제 그래프 + 가짜 모델**(02 대역): 입력 검사(moderation·classify) → answer(tool_calls) → tools(web_search) → answer → verify(불합격) → revise → answer → verify(합격) | `split_usage` = 입력 검사 몫 [moderation, classify], 시도 0 생성 [answer, web_search, answer]·검증 [verify, moderation], 시도 1 생성 [answer]·검증 [verify, moderation] |
| U-CUT-07 | 실제 그래프 + 가짜 모델로 시나리오 4개(0 합격 / 0 사실→1 합격 / 사실 소진 / 보안 소진), `max_rewrites=2` 및 같은 시나리오를 `max_rewrites=0`·`1`로 각각 실제 실행 | `cut_at(k)`(N=2 실행 기록) 끝 상태·텍스트 == 상한 k 실제 실행의 `verify_status`·`final_text` (k=0,1,2) |
| U-CUT-08 | 시각: `attempt_end_ms={0:3000,1:6000}`, 실제 끝 6500, `draft_ms=1500` | off 1500 / 0: 3000 / 1·2: 6500(1에서 합격이면 실제 끝) |
| U-CUT-09 | 비용: 시도별 usage | off = 입력 검사 + 시도 0 생성 몫 / k = 입력 검사 + 시도 0~k 전체. 11 `cost_usd` 합과 같음(Decimal) |
| U-CUT-10 | N=0 실행 | cuts 키 `off`·`0`만 |

### 4. SSE 소비 (DB 없음) — `tests/eval/test_golden_stream.py`

| ID | 입력(가짜 스트림 + 가짜 시계) | 기대 |
|---|---|---|
| U-SS-01 | `parse_sse(sse("delta",{"text":"a"}) + ": ping\n\n" + sse("done",{…}))` | `[("delta",…),("done",…)]`, ping 버림 |
| U-SS-02 | 한 조각에 이벤트 2개 / 이벤트 하나가 두 조각에 걸침 | 둘 다 올바르게 분리(버퍼링) |
| U-SS-03 | meta→checking→answering→delta×3→draft_done→verifying→revising(1)→replaced→verified→done | `end="done"`, `attempt_end_ms[0]` = revising 받은 시각, `[1]` = replaced 시각 |
| U-SS-04 | …→blocked→done | `block_code` 채움 |
| U-SS-05 | …→error{timeout} | `end="error"`, `error_code="timeout"` |

### 5. 실행기 (DB 없음) — `tests/eval/test_golden_run.py`
모두 `fake_runtime`(실제 `chat_event_stream`·그래프·`check_input`, 가짜 LLM·Moderation·분류기·MCP 툴)으로 `run_items(items, runtime, …)`를 부른다(`--no-record`와 같은 경로, 근거 DB 확인은 가짜 함수 주입).

| ID | 준비 | 기대 |
|---|---|---|
| U-RUN-01 | 문항 3개(fact 정답, fact 오답, smalltalk) | 결과 3개, 순서 유지, grade correct/wrong/correct, 진행 줄 3개(capsys) |
| U-RUN-02 | 런타임 `embed=None` 확인 + `EvalTurnStore.faq_lookup` 호출 시 AssertionError | 실행 중 오류 없음(=FAQ 조회 안 함) |
| U-RUN-03 | 묶음 f1(2턴): 가짜 답변 모델이 받은 메시지 기록 | 2턴째 호출 메시지에 1턴의 가린 질문·최종 답변(HumanMessage·AIMessage)이 들어 있음, 분류기가 받은 `prev_turn`이 1턴 |
| U-RUN-04 | 묶음 1턴째를 분류기가 차단 | 2턴째 history 비어 있음, 결과에 `group_broken:true` |
| U-RUN-05 | 2번째 문항에서 가짜 모델이 예외(`LlmUnavailable` 성격) | 그 문항 `end:error`, 3번째 문항은 정상 실행 |
| U-RUN-06 | 2번째 문항에서 예상 못 한 예외(`ZeroDivisionError`)가 실행기 코드에서 | `error_code="exception:ZeroDivisionError"`, 계속 |
| U-RUN-07 | 질문에 PII 없음 | 가짜 Moderation·분류기가 받은 텍스트 == 질문 원문(가림 없음), `masked_types=[]` |
| U-RUN-08 | `location={lat,lng}` 문항 | 가짜 모델이 받은 마지막 HumanMessage에 09 `[현재 위치]` 줄 |
| U-RUN-09 | `settings.VERIFY_MAX_REWRITES=2`인데 `verify_max=0`으로 실행 | 그래프 `AgentDeps.max_rewrites == 0`(첫 불합격에서 끝남), 원래 settings 객체는 그대로 |
| U-RUN-10 | 실행 중 `KeyboardInterrupt`(3번째 문항에서) | 앞 2개로 요약·결과 파일 저장, `run.interrupted:true`, 사용량 기록 함수 호출됨(가짜) |
| U-RUN-11 | `EvalTurnStore.take()`를 턴 없이 호출 | RuntimeError |
| U-RUN-12 | 리랭커·모드 확인(§7.7): 가짜 rag_query가 `meta{rerank:true}` 돌려주는데 요청은 off | 실행 전 `RagOptionsMismatch` → CLI 종료 코드 1 |

### 6. 집계·출력 (DB 없음) — `tests/eval/test_golden_summary.py`

| ID | 입력(ItemResult 목록 직접 생성) | 기대 |
|---|---|---|
| U-SUM-01 | 10문항: 정답 6·오답 2·차단 1·장애 1 | accuracy = **6/9**(차단은 오답으로 분모에 포함, 장애 1건은 분모에서 제외), `n_error=1` |
| U-SUM-02 | percentile: [100,200,…,1000] | p50=500, p95=1000 (가장 가까운 순위), 빈 목록 → None |
| U-SUM-03 | ttft: 차단·장애 문항은 timings 없음 | ttft 분모에서 빠짐 |
| U-SUM-04 | 비용 Decimal 합 | `Decimal` 정확 합, 문항당 = 합 / (전체−장애), 문자열로 직렬화 |
| U-SUM-05 | 토큰에 None 섞임 | 합은 None 제외, `none_count` 따로 |
| U-SUM-06 | 차단 2건(moderation unsafe 1, classifier off_topic 1) | `guard_false_positive` 전체 2/9, 단계별 1·1, 목록에 id·코드·reason |
| U-SUM-07 | 오판: 초안 정답 5 중 시도 0 불합격 2(사실 1·보안 1) | `verify_false_reject` 2/5, 그중 보안 1 |
| U-SUM-08 | 놓침: 초안 오답 3 중 시도 0 합격 1 | `verify_miss` 1/3 |
| U-SUM-09 | 분류별·후속 줄 | 묶음 2턴째는 자기 분류 + `followup` 줄에 들어감, 1턴째는 followup에 안 들어감 |
| U-SUM-10 | `stale:true` 1건 | `n_stale=1` |
| U-SUM-11 | Markdown 요약 스냅샷 | §9.2 형식(머리 줄·표·검증 상한별 표·오답 목록) |
| U-SUM-12 | 결과 파일 저장: 같은 이름이 이미 있음 | `-2` 붙은 새 파일, 기존 파일 불변 |
| U-SUM-13 | 결과 파일 JSON 왕복(저장 → 읽기) | `--compare`가 읽는 모양과 같음 |
| U-CMP-01 | 결과 파일 2개(A 정답 40, B 정답 41) | 비교표 열 2개, 정답 수 차이 1 → "차이 작음" 표시 |
| U-CMP-02 | 문항별 차이 | A 정답·B 오답 id 목록과 반대 목록 |
| U-CMP-03 | `golden_sha256`이 다름 | 표 위 경고 줄 |

### 7. FAQ 짝 (DB 없음) — `tests/eval/test_golden_faq.py`

| ID | 준비 | 기대 |
|---|---|---|
| U-FP-01 | 가짜 임베딩: pg1 두 문항(코사인 0.97), pg2 한 문항(pg1과 0.93) | 같은 묶음 짝 1개, 다른 묶음 짝 2개 |
| U-FP-02 | 임계값 표 | 0.95: 재사용 1/1, 오적중 0 / 0.92: 재사용 1/1, 오적중 2 + 목록 |
| U-FP-03 | 임베딩에 넘긴 텍스트 | `mask_pii(question).text`(PII 없는 질문이면 원문과 같음) |
| U-FP-04 | `paraphrase_group` 문항 0개 | 안내 문구 출력, 종료 코드 2 |

### 8. CLI (DB 없음) — `tests/test_cli_eval.py`

| ID | 인자 | 기대 |
|---|---|---|
| U-CLI-01 | `eval golden --rerank maybe` / `--verify-max 3` / `--rag-mode naive` | 종료 코드 2 |
| U-CLI-02 | `--check --compare a.json` | 2 |
| U-CLI-03 | 옵션 없음 | 실행 함수가 설정 기본값(rerank True, mix, VERIFY_MAX_REWRITES)으로 호출됨(몽키패치) |
| U-CLI-04 | `--rerank off --rag-mode hybrid` | 런타임 조립에 `tool_headers={"X-Nadri-Rerank":"off","X-Nadri-Rag-Mode":"hybrid"}` |
| U-CLI-05 | 기본 `--label` | `rerank-off_hybrid_v2` 형식 |
| U-CLI-06 | `--compare` 파일 없음 | 2 |

### 9. tour-tools (DB 없음) — `tests/tools/test_rag_query_eval.py`

| ID | 준비 | 기대 |
|---|---|---|
| U-RQ22-01 | `rag_options_from(settings(기본), None)` | `RagOptions(rerank=True, mode="mix")` |
| U-RQ22-02 | 헤더 `{"x-nadri-rerank":"off","X-NADRI-RAG-MODE":"hybrid"}` | `(False, "hybrid")` (대소문자 무시) |
| U-RQ22-03 | 헤더 `rerank: maybe` | `ValueError` |
| U-RQ22-04 | `rag_query(options=RagOptions(False,"mix"))`, 가짜 LightRAG 후보 8개, 가짜 reranker(호출 기록) | reranker 호출 0회, 결과 = LightRAG 순서 앞 5개, `score` 모두 None, `meta={"rerank":false,"mode":"mix"}` |
| U-RQ22-05 | `options=RagOptions(True,"hybrid")` | LightRAG 요청 본문 `mode=="hybrid"`, reranker 호출 1회 |
| U-RQ22-06 | FastMCP에 등록된 `rag_query` 툴 입력 스키마 | 22 전과 같음(`question`만, `ctx` 없음) — 스냅샷 |
| U-RQ22-07 | 인증 통과 요청에 두 헤더 → 툴 호출(ASGI 테스트 클라이언트로 MCP 요청 1회) | 래퍼가 `RagOptions(False,"hybrid")`로 `rag_query` 호출(spy) — §8.2 헤더 읽기 경로 검증 |
| U-RQ22-08 | 헤더 없음 | 설정값으로 호출 |
| U-RQ22-09 | 설정 `RAG_QUERY_MODE="naive"` | 설정 검증 오류 |
| U-TL22-01 | `load_tools(settings, FakeMCPClient, extra_headers={"X-Nadri-Rerank":"off","Authorization":"x"})` | 연결 설정 headers에 `X-Nadri-Rerank` 있음, `Authorization`은 원래 Bearer 값 유지 |

### 10. 사용량 기록·근거 확인 (마커 `db`) — `tests/eval/test_golden_db.py`

| ID | 준비 | 기대 |
|---|---|---|
| A-GD22-01 | usage [answer(gpt-6-luna 1000/0/100), moderation(units 1), web_search(units 1), verify] → `record_eval_usage(db, usage)` | `usage_events` 4행, 모두 `kind="eval"`, `user_id`·`message_id` NULL, `cost_usd` = 원래 kind로 계산한 값(moderation·web_search 0, answer = 11 `llm_cost`) |
| A-GD22-02 | `--no-record` 경로 | 0행 |
| A-GD22-03 | 근거 확인: `make_tour("1")`(정상), `make_tour("2", deleted=True)`, contentid "3" 없음 | 1 통과, 2·3 오류 |
| A-GD22-04 | `tour_items.as_of`가 문항 `as_of`보다 새로움 | 경고, `stale` |
| A-GD22-05 | `wiki_pages`에 인덱싱 안 된 contentid | 경고 "검색으로 찾을 수 없음" |
| A-GD22-06 | `--check` 전체(`write_golden` + DB) | 분포표·검수표 출력, 오류 있으면 종료 코드 2 |
| A-GD22-07 | `KeyboardInterrupt` 뒤 `finally` 기록 | 그때까지의 사용량 행만 생김 |

### 11. 앞 작업 회귀
- 01·02·08·09·10·12 테스트 전체 재실행, spec §12 표 수정 반영(특히 01 `rag_query` 결과 dict 비교에 `meta`, 01 `Settings` 필드 목록).
- `get_chat_runtime` 경로 테스트(02·08·12)가 `build_chat_runtime` 분리 뒤에도 통과.

### 통과 기준
- 위 전부 통과, `-m "not integration"`에서 실패 0.

---

## ② HITL

전제: 22 적용 compose(ingest에 키·`./eval` 마운트), 03 적재로 서울·제주 항목이 상세·인덱싱까지 된 상태(`docker compose run --rm ingest nadri ingest status`), tour-tools·lightrag·postgres 기동.

### HITL-1 평가셋 검수 (G4 Q5)
1. 에이전트가 spec §5.2대로 초안 40~60문항을 만들고 `docker compose run --rm ingest nadri eval golden --check` 출력(분포표 + 검수표)을 사용자에게 보여 준다.
2. 사용자는 README 체크리스트(① 물어볼 만한 질문인가 ② 정답이 데이터와 맞고 표기 변형이 충분한가 ③ 답이 여러 개일 수 있는데 하나만 정답인 문항 ④ 분포 ⑤ 빼거나 더할 문항)로 검토하고 고칠 것을 말한다.
3. 에이전트가 반영 → `--check` 오류 0 → 사용자 "승인" → 커밋.

### HITL-2 짧은 시험 실행
`docker compose run --rm ingest nadri eval golden --ids g-fact-001 g-small-001 --no-record`
- 확인: 진행 줄 2개, 요약표, `eval/results/`에 결과 파일, 파일 안 `final_text`가 실제 답변. tour-tools 로그에 `rerank=on mode=mix`.

### HITL-3 기준 실행 (리랭커 켬 · mix · 다시 쓰기 상한 2)
`docker compose run --rm ingest nadri eval golden --rerank on --rag-mode mix --verify-max 2`
- 요약표 전체를 보고서에 붙인다(정답률·근거·지연·비용·오탐·오판, **검증 상한별 표**).
- 오답 목록 상위 10개를 사용자와 같이 본다 — 답변이 실제로 틀렸는지, 정답 표현이 부족한(채점 문제)지 구분. 채점 문제면 HITL-1처럼 문항을 고치고(사용자 승인) 다시 돈다.

### HITL-4 비교 실행
```bash
docker compose run --rm ingest nadri eval golden --rerank off
docker compose run --rm ingest nadri eval golden --rag-mode hybrid
docker compose run --rm ingest nadri eval golden --compare eval/results/golden-*-rerank-on_mix_v2.json \
    eval/results/golden-*-rerank-off_mix_v2.json eval/results/golden-*-rerank-on_hybrid_v2.json
```
(`--compare` 경로는 컨테이너 안 경로 `/app/eval/results/…` — README에 정확한 예시)
- tour-tools 로그 `rerank_ms`(켬일 때) p50·p95도 함께 적는다.

### HITL-5 FAQ 임계값
`docker compose run --rm ingest nadri eval golden --faq-pairs`
- 임계값별 재사용률·오적중 표와 오적중 짝 목록을 본다.

### HITL-6 결정 (사용자)
아래 표를 채워 사용자에게 보여 주고 값마다 결정을 받는다. 결정값은 compose `environment`에만 넣고(Q11) PROGRESS 결정 로그에 적는다.

| 설정 | 지금 값 | 비교 근거(결과 파일) | 에이전트 의견 | 사용자 결정 |
|---|---|---|---|---|
| `VERIFY_MAX_REWRITES` | 2 | 기준 실행 검증 상한별 표 | | |
| `RAG_QUERY_MODE` | mix | 기준 vs hybrid | | |
| `RAG_RERANK_ENABLED` | true | 기준 vs 리랭커 끔 | | |
| `FAQ_CACHE_THRESHOLD` | 0.95 | `--faq-pairs` 표 | | |
| 분류기 오탐(있으면) | — | 오탐 목록 | 프롬프트 예시 보강 / off_topic 안내형 완화 / 그대로 | |
| Moderation 오탐(있으면) | — | 오탐 목록 | 23 결과와 같이 결정(Q10) | |

결정 반영 뒤: `docker compose up -d api tour-tools` → 채팅 1건으로 동작 확인(새 설정에서 오류 없음).

### HITL-7 (선택) 잘라 계산 검증
`docker compose run --rm ingest nadri eval golden --verify-max 0`
- 이 실행의 정답률·끝 상태 분포가 HITL-3 "상한 0" 행과 크게 다르지 않은지(무작위성 범위) 본다. 크게 다르면 보고(§6.3 가정 재검토).

### HITL 결과 보고
| 항목 | 결과 |
|---|---|
| 1 문항 수·분포, 사용자 검수 완료일 | |
| 3 기준 실행 요약(정답률·근거·p50/p95·문항당 비용·오탐·오판/놓침) | |
| 3 검증 상한별 표 | |
| 4 비교표(정답률·검색 적중률·지연·비용) + 문항별 차이 | |
| 4 `rerank_ms` p50/p95 | |
| 5 임계값별 재사용률·오적중 | |
| 6 사용자 결정 4개 + 오탐 대응 | |
| hybrid 청크 반환 여부(spec §8.1 미확인) | |
| 실제 총비용(`usage_events` kind=eval 합) vs spec §11 추정 | |
