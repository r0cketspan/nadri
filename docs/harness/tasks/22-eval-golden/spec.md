# 22-eval-golden — 골든 Q&A 평가 (spec)

> 하네스 Phase 4 산출물 (spec-writer, 작성 2026-11-22). 상태: **초안 — 확인 질문 대기**(마지막 절 표). 브랜치 `feat/22-eval-golden`, 의존 작업 03-ingest-bootstrap · 08-guard-pipeline · 10-tool-tour-live · 11-quota-usage (→ 12·09·05·04·02·01).
> 근거: [PL]=program_list.md(G4 승인본) §2 표·§3 "22-eval-golden"·§4 추적표·§5 Q3·Q5 · [A]=architecture.md(G3 재승인본) §2.1 tour-tools `rag_query`·ingest CLI·§3.1·§7 디렉터리(`eval/golden/`)·§10 비용·ADR-06·13·18·§12.2 A10·A22·A24·A25·A27 · [R]=requirements.md FR-70, 목표 6("측정·기록만, 목표 수치는 결과를 보고 정함"), NFR-60 · [PG]=PROGRESS.md 결정 로그(G4 Q3 "bge-m3 비교는 v1.1 이후", G4 Q5 "에이전트 초안 40~60 → 사용자 검수", 08-Q4 "Moderation 임계값은 22·23에서", 12-Q4).
> **이어받는 확정 spec**: [01](`Settings`·`get_settings`·`RAG_CANDIDATES`·`RAG_TOP_K`·`fetch_candidates`·`rag_query`·`rerank`·`ToolDeps`·`BearerAuthMiddleware`·`cli.py` argparse·종료 코드 0/1/2) · [02](`AgentDeps.max_rewrites`·`VERIFY_MAX_REWRITES`·`build_graph`·`load_tools`·`ChatRuntime`·`get_chat_runtime`·`chat_event_stream`·SSE 이벤트·`ToolRecord`·`UsageRecord`·`VerifyAttempt`·`Evidence`·`collect_evidence`·`build_sources`·`SAFE_REPLACEMENT`·timings 정의) · [03](적재 상태 — `detail_synced_at`·`deleted_at`·`wiki_pages` 인덱싱) · [08](`check_input`·`InputVerdict`·`TurnInput`·`TurnStore`·`CompletedTurn`·`SecurityEventDraft`·`security_fail` 판정식·`fixed_messages()`) · [09](`TurnPair`·`SessionContext`·`history_messages`·`prev_turn`·`Location`·`TurnInput.history/location/turn_count`) · [10](`tour_live` 툴·실시간 몫 200) · [11](`pricing.cost_usd`·`usage_row`·`record_usage`·`USAGE_KINDS`의 `eval`) · [12](`ChatRuntime.embed=None`이면 캐시 끔·`FAQ_CACHE_THRESHOLD`·`build_embeddings`·`embed_question`).
> 이름·시그니처는 위 spec을 그대로 쓰고, 바꾸는 부분은 §12 "앞 작업과 달라지는 점"에 모두 적었다. **미확인** = 문서·공식 자료로 확인하지 못한 사실.

---

## 1. 작업 목표

FR-70의 **골든 Q&A 평가**를 만든다. 질문·정답·근거 contentid를 담은 평가셋(`eval/golden/golden.jsonl`)을 채팅과 **같은 코드**(PII 가리기 → 입력 검사 → LangGraph 답변⇄검증 → 출력 검사)로 프로세스 안에서 돌리고, 결과를 코드로 채점해 아래를 측정·기록한다([R] 목표 6 — 목표 수치는 정하지 않음).

| 지표 | 무엇을 보나 | 연결 가정 |
|---|---|---|
| 정답률 | 최종 답변이 정답 사실을 담았나 (+ 초안·다시 쓰기 단계별) | A25 |
| 근거 일치율 · 검색 적중률 | 답변이 인용한 contentid / 툴이 찾아온 contentid 안에 정답 근거가 있나 | A10, 리랭커 |
| 첫 토큰 지연 · 전체 시간 | `timings.ttft_ms`·`total_ms` (p50·p95) | A25, NFR-60 |
| 토큰 · 비용 | 호출 종류별 토큰, 11 단가표로 계산한 비용 | A25 |
| 입력 검사 오탐률 | 정상 질문인데 Moderation·분류기가 막은 비율 | A22, A24 |
| 검증 오판 · 놓침 | 맞는 초안을 불합격시킨 비율 / 틀린 초안을 합격시킨 비율 | A25 |

비교할 설정([PL] CLI): **리랭커 on/off**, **LightRAG 질의 모드 mix/hybrid**, **검증 다시 쓰기 0/1/2회**. 결과표를 사용자에게 보여 주고 `VERIFY_MAX_REWRITES`·`RAG_QUERY_MODE`·`RAG_RERANK_ENABLED`·`FAQ_CACHE_THRESHOLD`를 **설정값으로만** 정한다(HITL).

- FAQ 캐시는 **우회**한다(`ChatRuntime.embed=None`) — 캐시 적중이 답변 품질·지연 측정을 가리지 않게.
- 한도·분당 제한·세션 저장·제목·요약은 거치지 않는다(라우터·`DbTurnStore`를 쓰지 않음, §7.3).
- 평가셋은 **에이전트(구현자)가 적재 데이터에서 초안 40~60문항**을 만들고 **사용자가 검수·수정**한다(G4 Q5, §5).

### 1.1 넣지 않는 것
| 빠지는 것 | 들어오는 작업 / 이유 |
|---|---|
| 임베딩 모델 비교(bge-m3) | v1.1 이후 (G4 Q3) |
| 공격 질문 세트·방어율 | 23 |
| 매일 03:00 자동 실행·보고서 저장(`eval_reports`) | 24 — 골든은 **수동 CLI**만([A] §2.1 ingest CLI) |
| LLM 채점(판정 모델) | 넣지 않음 — 코드 채점만(§9 Q3) |
| 목표 수치·합격선 | 정하지 않음([R] 목표 6). 결과를 보고 사용자가 정함 |
| Moderation 범주별 임계값 설정 추가 | 22는 오탐 사례를 **보고만** 한다. 바꿀지는 23 결과와 함께 결정(08-Q4 이월, §15 Q10) |
| 분류기 `off_topic` 완화(안내형 답변) | 오탐이 나오면 사례를 보고하고 **사용자 확인**(A24). 22에서 코드 변경 없음 |
| 관리자 화면에 골든 결과 표시 | 범위 밖 — 결과는 CLI 출력·결과 파일 |

---

## 2. 생성·수정 파일

경로의 `nadri/`는 `backend/src/nadri/`.

| 파일 | 신규/수정 | 역할 |
|---|---|---|
| `eval/golden/golden.jsonl` | 신규 | 평가셋 40~60문항 (§4·§5). **구현 단계에서** 에이전트 초안 → 사용자 검수 후 커밋 |
| `eval/README.md` | 신규 | 골든 파일 형식, 채점 규칙, 실행·비교 방법, 검수 체크리스트(§5.3). 23·24가 자기 절을 덧붙임 |
| `nadri/eval/__init__.py` | 신규 | 패키지 |
| `nadri/eval/golden.py` | 신규 | 평가셋 읽기·검사, 채점, 단계별 잘라 계산, 집계, 실행기, 결과 파일·비교표 (§6~§10) |
| `nadri/cli.py` | 수정(01·03) | `nadri eval golden …` 하위 명령 (§10) |
| `nadri/core/config.py` | 수정(01·02) | `RAG_RERANK_ENABLED`·`RAG_QUERY_MODE` (§3) |
| `nadri/tools/rag_query.py` | 수정(01) | 질의 모드 인자, 리랭커 끄기 경로, 요청 헤더로 받은 평가용 덮어쓰기 (§8) |
| `nadri/tools/server.py` | 수정(01·10) | `rag_query` 래퍼가 요청 헤더를 읽어 넘김 (§8.2) |
| `nadri/agent/tools.py` | 수정(02·10) | `load_tools(..., extra_headers=None)` (§8.3) |
| `nadri/api/main.py` | 수정(02·08·09·12) | `get_chat_runtime`에서 런타임 조립부를 `build_chat_runtime()`로 떼어 냄(평가가 재사용, §7.2) |
| `compose.yaml` | 수정 | ingest에 `OPENAI_API_KEY`·`TAVILY_API_KEY` 환경변수, `./eval:/app/eval:ro`·`./eval/results:/app/eval/results` 마운트 (§3.3) |
| `.gitignore` | 수정 | `eval/results/` |
| `backend/tests/...` | 신규·수정 | test.md, 앞 작업 테스트 수정(§12) |
| `docs/harness/tasks/22-eval-golden/spec.md` §13 | 수정 | 가정 판정·결정 결과 기록 |

> [PL] 파일 목록 밖: `tools/server.py`·`agent/tools.py`·`api/main.py`·`compose.yaml`·`.gitignore` — 평가 프로세스(ingest)가 다른 컨테이너(tour-tools)의 리랭커·모드를 바꿔 부를 통로(§8, Q1)와, api 런타임을 앱 밖에서 조립할 자리(§7.2)가 필요해서다.

---

## 3. 설정 · 상수

### 3.1 새 환경변수 (`core/config.py`)
| 이름 | 타입·기본값 | 쓰는 곳 | 용도 |
|---|---|---|---|
| `RAG_RERANK_ENABLED` | `bool = True` | tour-tools | `False`면 CrossEncoder를 부르지 않고 LightRAG 순서 그대로 상위 `RAG_TOP_K`(ADR-06 대안 비교용) |
| `RAG_QUERY_MODE` | `Literal["mix", "hybrid"] = "mix"` | tour-tools | LightRAG `/query/data`의 `mode`. 그 밖 값이면 설정 오류로 기동 실패 |

- 기본값은 지금 아키텍처(ADR-06: mix + 리랭커)와 같다 — 22를 병합해도 동작은 바뀌지 않는다.
- 이미 있는 값(바꾸지 않음, HITL 결정 대상): `VERIFY_MAX_REWRITES`(02, 기본 2), `FAQ_CACHE_THRESHOLD`(12, 기본 0.95).

### 3.2 상수 (`eval/golden.py`)
| 상수 | 값 | 용도 |
|---|---|---|
| `GOLDEN_PATH` | `Path("/app/eval/golden/golden.jsonl")` (CLI `--file`로 바꿀 수 있음) | 평가셋 |
| `RESULTS_DIR` | `Path("/app/eval/results")` (`--out-dir`) | 결과 파일 |
| `CATEGORIES` | §4.2 표의 9개 | 분류 검사 |
| `RERANK_HEADER` / `RAG_MODE_HEADER` | `"X-Nadri-Rerank"` / `"X-Nadri-Rag-Mode"` | §8 (Q1) |
| `EVAL_USER_ID` | `0` | `TurnInput.user_id` 자리 채움(DB에 쓰지 않음) |
| `TIE_MARGIN` | `2` (문항 수) | 비교표에서 "차이 없음" 표시 기준(§9.4). 판정이 아니라 읽기 도움 |

### 3.3 compose (ingest 서비스)
- 환경변수 추가: `OPENAI_API_KEY`(20이 먼저 넣었으면 그대로), `TAVILY_API_KEY`, `TOOLS_URL`·`TOOLS_API_KEY`(01에 있음). 그래프가 답변·검증·분류기·Moderation·웹 검색을 실제로 부르기 때문이다.
- 마운트: `./eval:/app/eval:ro`(24도 같은 줄 — 먼저 병합되는 쪽이 넣는다), `./eval/results:/app/eval/results`(쓰기 가능, 결과 파일만 — Q8). `eval/results/`는 `.gitignore`.
- **미확인**: 읽기 전용 바인드 안에 쓰기 가능한 하위 바인드를 겹쳐 거는 것이 Docker Desktop 없이 WSL2 Docker Engine에서 문제없는지 — 구현 시 `touch /app/eval/results/x`로 확인. 안 되면 결과 경로를 `/data/eval-results`(새 바인드 `./eval-results`)로 바꾸고 README에 적는다.

---

## 4. `golden.jsonl` 형식

### 4.1 한 줄 = 한 문항 (UTF-8 JSON, 빈 줄·`#` 시작 줄은 건너뜀)
```json
{"id":"g-fact-001","category":"fact","area":"서울","question":"경복궁 화요일에도 열어?",
 "facts":[["화요일","휴무","쉬"]],"must_not":[["화요일에도 운영","화요일 정상 운영"]],
 "evidence":{"contentids":["126508"],"rule":"all"},"tools_any":[],
 "group":null,"turn":null,"location":null,"paraphrase_group":"pg-gbg-rest",
 "as_of":"2026-12-03","note":"휴무일 = restdate"}
```
| 필드 | 타입 | 필수 | 뜻 |
|---|---|---|---|
| `id` | str `^g-[a-z_]+-\d{3}$` | ✓ | 파일 안에서 유일 |
| `category` | §4.2 9개 중 하나 | ✓ | 집계 단위 |
| `area` | `"서울"`\|`"제주"`\|`null` | ✓ | 관광 문항은 지역, 그 밖은 null |
| `question` | str (1~500자) | ✓ | 사용자 질문 원문. **개인정보 없음**(§5.2) |
| `facts` | `list[list[str]]` | | 정답 사실 목록. 바깥 = 모두 만족(AND), 안쪽 = 그중 하나(OR) — §6.1 |
| `must_not` | `list[list[str]]` | | 나오면 오답인 표현. 안쪽 하나라도 나오면 실패 |
| `evidence` | `{"contentids": [str], "rule": "all"\|"any"}` \| null | | 정답 근거 contentid. `rule` 기본 `"all"` |
| `tools_any` | `list[str]` | | 이 중 하나 이상의 툴이 호출돼야 함(예: 웹 필요 → `["web_search"]`). 툴 이름은 02·10 허용 목록 5개 |
| `group` / `turn` | str / int ≥1 | 둘 다 있거나 둘 다 null | **후속 질문 묶음** — 같은 `group`은 한 세션에서 `turn` 순서로 실행(§7.4) |
| `location` | `{"lat","lng"}` \| null | | 위치 동의를 흉내 냄(09 `Location`). 주변 질문만 |
| `paraphrase_group` | str \| null | | 같은 뜻의 다른 표현끼리 같은 값 — FAQ 임계값 측정용(§10.3, Q6) |
| `as_of` | `YYYY-MM-DD` | 관광 문항 ✓ | 정답을 확인한 데이터 기준일(`tour_items.as_of`) |
| `note` | str | | 검수 메모(채점에 안 씀) |

- **채점 항목이 하나도 없는 문항은 오류**: `facts`·`must_not`·`evidence`·`tools_any` 중 최소 하나, 또는 category가 `smalltalk`·`common`·`out_of_area`(이 셋은 §6.1 기본 규칙으로 채점).
- 모르는 키가 있으면 오류(오타 방지).

### 4.2 분류와 목표 분포 (총 50문항 목표, 허용 40~60 — Q5)
| category | 뜻 | 목표 수 | 채점에 주로 쓰는 것 |
|---|---|---|---|
| `fact` | 관광 사실(운영시간·휴무·요금·주차·주소·전화) | 14 (서울 8·제주 6) | `facts`, `evidence(all)` |
| `condition` | 조건 검색(지역·종류·시군구·키워드) | 6 | `evidence(any)`, `tools_any:["data_query"]` |
| `nearby` | 주변(위치 동의 좌표 또는 장소 기준) | 4 | `tools_any:["data_query","tour_live"]`, `evidence(any)`(저장 데이터 기준일 때) |
| `festival` | 축제·행사(기간) | 4 | `tools_any:["data_query","tour_live"]` (+ 날짜가 고정된 질문은 `facts`) |
| `web` | 공공데이터에 없는 최신 정보(웹 필요) | 4 | `tools_any:["web_search"]` |
| `no_data` | 자료에 없는 것을 묻기(지어내면 안 됨) | 2 | `facts:[["자료에 없","정보가 없","확인되지 않","찾을 수 없","알 수 없"]]`, `must_not` |
| `smalltalk` | 인사·감사·잡담 | 5 | 기본 규칙(§6.1) — 분류기 오탐(A24) |
| `common` | 일반 상식(여행 관련 상식 포함) | 4 | 기본 규칙 + 필요 시 `facts` — 분류기 오탐(A24) |
| `out_of_area` | 서울·제주 밖 여행 질문(08-Q2: `normal`) | 3 | 기본 규칙 — 분류기 오탐(A24) |
| (후속 묶음) | 위 분류 중 아무거나에 `group`·`turn`을 붙임 | 3묶음 × 2~3턴 | 2턴째부터는 "거기", "그럼 주차는?"처럼 앞 대화에 기대는 질문 |

- 합계 46 + 후속 묶음의 2턴째 이후(약 6~7) ≈ 50~53. 서울:제주 ≈ 3:2(적재 비율).
- **Moderation 오탐 함정 문항**(A22)을 관광 문항 안에 3개 이상 섞는다: 예) "전쟁기념관 관람 시간", "총각김치 맛집", "제주 4·3 평화공원 위치" — 정상이지만 단어가 거칠게 들릴 수 있는 질문.
- **FAQ 짝**(Q6): `paraphrase_group`을 5묶음 이상(각 2~3개 표현) 둔다. 그리고 "비슷하지만 다른 질문" 짝(예: 경복궁 휴무 vs 창덕궁 휴무, 경복궁 요금 vs 경복궁 휴무)이 자연스럽게 생기도록 같은 장소·같은 질문 유형을 일부러 겹친다.

---

## 5. 평가셋 작성 방식 (G4 Q5 — 에이전트 초안 → 사용자 검수)

### 5.1 언제
03 초기 적재로 서울·제주 데이터가 **상세 수집·인덱싱까지 끝난 항목이 유형별로 최소 몇 개씩 생긴 뒤**(`nadri ingest status`로 확인). 적재가 덜 끝났으면 끝난 항목에서만 고른다. 근거 contentid는 반드시 `detail_synced_at IS NOT NULL AND deleted_at IS NULL`이고 `wiki_pages`에 인덱싱된 항목(LightRAG에 들어간 것)이어야 한다.

### 5.2 에이전트(구현자)가 하는 일
1. **후보 뽑기**: `docker compose exec postgres psql …`로 지역 × 유형별 항목을 고르고 `extra`(intro·info)에서 **짧고 분명한 값**(예: 휴무 "매주 화요일", 주차 "가능", 요금 "3,000원")이 있는 항목만 쓴다. 긴 자유 텍스트(`usetime` 여러 줄 등)는 정답 문자열로 쓰지 않거나 핵심 토큰만(예: "09:00", "18:00") 쓴다.
2. **질문 쓰기**: 실제 사용자 말투로(존댓말·반말·짧은 질문·오타 1~2개 섞기). 장소 이름을 정식 명칭과 다르게(예: "성산 일출봉") 쓴 문항도 몇 개.
3. **정답 쓰기**: `facts`는 표기 변형을 OR로 나열(예: `["09:00","9:00","오전 9시","9시"]`). `must_not`은 데이터와 반대되는 흔한 오답(예: 휴무가 화요일이면 "월요일 휴무").
4. **근거·기준일**: `evidence.contentids`, `as_of = tour_items.as_of`.
5. **비관광 문항**: smalltalk·common·out_of_area는 데이터와 무관하게 쓴다. 개인정보(전화번호·이메일 등)는 **어떤 문항에도 넣지 않는다**(골든 질문은 가림이 일어나지 않아야 함 — A27 확인 지표 §9.1).
6. `nadri eval golden --check`(§10.1)로 형식·근거 검사를 통과시킨다.
7. 검수표를 만든다: `--check`가 출력하는 표(id·분류·질문·정답·근거 제목·기준일)를 사용자에게 보여 준다.

### 5.3 사용자가 하는 일 (HITL-1)
- 검수 체크리스트(README에 같은 내용): ① 질문이 실제로 물어볼 만한가 ② 정답이 데이터와 맞고 표기 변형이 충분한가 ③ 답이 여러 개일 수 있는데 하나만 정답으로 둔 문항은 없는가 ④ 분포(§4.2)가 괜찮은가 ⑤ 빼거나 더할 문항.
- 사용자 수정은 에이전트가 반영 → `--check` 재통과 → 커밋. 이후 문항을 바꾸면 결과 파일의 `golden_sha256`이 달라져 비교표에 경고가 뜬다(§10.2).

### 5.4 데이터가 바뀌면
매일 현행화(21)로 근거 항목이 바뀌거나 지워질 수 있다. `--check`(그리고 실행 시작 시 같은 검사)가 근거 contentid마다 확인한다:
- 지워짐(`deleted_at` 있음)·없음 → **오류**(그 문항 고치기 전엔 실행 거부, `--skip-stale`로 그 문항만 빼고 실행 가능).
- `tour_items.as_of > 문항 as_of` → **경고**("재검수 필요") — 실행은 하고 결과에 `stale: true` 표시, 집계에서는 따로 셈.

---

## 6. 채점 규칙 (코드만 — Q3)

### 6.1 문항 1개 채점 (`grade_text`)
글자 맞추기용 정규화 `norm(s)`: NFKC → 소문자 → 모든 공백 제거. 답변과 정답 문자열에 똑같이 적용하고 "부분 문자열 포함"으로 본다.

| 검사 | 통과 조건 |
|---|---|
| `facts` | 바깥 목록의 **모든** 항목에 대해, 안쪽 문자열 중 하나 이상이 `norm(답변)`에 들어 있음 |
| `must_not` | 안쪽 문자열 중 **하나도** `norm(답변)`에 없음 |
| `evidence` (정답률이 아닌 근거 일치율에만) | §6.2 |
| `tools_any` | 이번 턴 `tool_records` 이름(오류 기록 포함 — 툴 선택 자체를 봄) 중 하나 이상이 목록에 있음 |
| 기본 규칙(모든 문항) | 입력 검사에서 차단되지 않음 && 최종 상태가 `security_replaced`가 아님 && 답변이 비어 있지 않음 |

- **정답(correct)** = 기본 규칙 && `facts` && `must_not` && `tools_any`(있는 것만). 하나라도 실패하면 **오답(wrong)** 이고 어느 검사가 실패했는지 `failed_checks`에 남긴다.
- **차단(blocked)** = 입력 검사 차단 → 오답으로 세고 `failed_checks=["blocked:<code>"]`, 입력 검사 오탐에도 셈.
- **장애(error)** = `error` 이벤트로 끝남(`llm_unavailable`·`guard_unavailable`·`timeout`) → 정답률 분모에서 **빼고** 따로 센다(Q9). 자동 재시도 없음 — `--ids`로 다시 돌린다.
- 위 검사는 **최종 답변**뿐 아니라 §6.3의 단계별 텍스트(초안·다시 쓰기 k회)에도 똑같이 적용한다.

### 6.2 근거 (`grade_evidence`)
- **인용 근거** = `build_sources(text, collect_evidence(tool_records))`(02)의 `type == "tour"` contentid 집합.
- **검색 근거** = `collect_evidence(tool_records).contentids`(툴이 찾아온 전체 — 답변이 인용했는지와 무관). 리랭커·모드 비교의 핵심 지표다.
- `rule == "all"`: 기대 contentid가 모두 들어 있으면 일치 / `"any"`: 하나라도 있으면 일치.
- 문항별로 `evidence_cited`(일치 여부)·`evidence_retrieved`(일치 여부)·`evidence_recall`(인용 근거 ∩ 기대 / 기대 수)을 남긴다.
- `evidence`가 없는 문항은 근거 지표 분모에서 빠진다.

### 6.3 검증 단계별 잘라 계산 (`cut_at`) — Q2
한 번의 실행(`--verify-max N`)에서 **다시 쓰기 상한이 k(0 ≤ k ≤ N)였다면 어떻게 끝났을지**를 그 실행 기록만으로 계산한다. 그래프는 상한 k에 닿기 전까지 상한 N일 때와 똑같이 움직이므로(02 §5.3 판정이 상한과 무관), 상한만 다른 실행을 따로 돌리는 것과 같은 결과를 **같은 답변 위에서**(LLM 무작위성 없이 짝지어) 비교할 수 있다.

입력: `CompletedTurn.answer_texts`(시도별 답변), `verify_log`(시도별 판정), 시도별 시각(§7.5), 시도별 사용량(§6.4).

| 경우 (상한 k) | 끝 상태 | 채점할 텍스트 | 시간 | 비용 |
|---|---|---|---|---|
| 시도 j ≤ k에서 합격 | `passed` | `answer_texts[j]` | 실제 끝 시각 | 시도 0~j |
| 시도 k까지 합격 못 함 + `verify_log[k]`가 보안 실패 | `security_replaced` | `fixed_messages().safe_replacement` | 검증 k 결과 시각 | 시도 0~k |
| 시도 k까지 합격 못 함 + 사실 실패만 | `failed` | `answer_texts[k]` | 검증 k 결과 시각 | 시도 0~k |
| **검증 끔**(k = "off") | `unverified` | `answer_texts[0]`(초안) | `timings.draft_ms` | 입력 검사 + 시도 0의 답변·툴 몫(검증·출력 Moderation 제외) |

- 보안 실패 판정 `security_failed(v: VerifyAttempt) -> bool`은 08 §9 식과 **같아야** 한다: `v.moderation_flagged or v.canary_leak or v.security_ok is False or any(issue.kind ∈ SECURITY_KINDS)`. 실제 그래프 결과와 일치하는지 테스트로 묶는다(test.md U-CUT-07).
- `cut_at(N)`은 실제 결과와 같아야 한다(같은 테스트).
- 상한 k의 근거 일치는 `build_sources(그 텍스트, collect_evidence(전체 tool_records))`로 계산한다 — 다시 쓰기 중 새로 부른 툴 결과까지 근거에 들어가는 근사(인용은 그 텍스트에 있는 것만 세므로 영향은 작음).
- 검증 끔 행은 FR-70의 "검증 에이전트 끔"이다 — 초안을 그대로 내보냈다면의 정답률·지연·비용. 실제로 끈 채 운영하는 설정은 만들지 않는다(보안 검사까지 꺼지므로, ADR-18).

### 6.4 사용량 시도별로 나누기 (`split_usage`)
`CompletedTurn`과 함께 `TurnStore.finish_done`이 받는 `usage`는 **입력 검사 몫 → 그래프 실행 순서**로 쌓인다(08 §10.2 4)·6), 02 `operator.add`). 그래서:
1. 첫 `answer` 기록 앞까지 = **입력 검사 몫**(moderation·classify).
2. 그 뒤로 시도 번호 0에서 시작, `verify` 기록을 본 뒤에 `answer` 기록이 나오면 시도 번호 +1.
3. 시도 안에서 `verify`와 그 뒤 같은 검증 노드의 `moderation`은 **검증 몫**, 나머지(`answer`·`web_search`)는 **생성 몫**.
- 이 순서 가정은 **실제 그래프 + 가짜 모델**로 고정한다(test.md U-CUT-06). 순서가 다르면 `UsageRecord`에 `attempt` 키를 더하는 쪽으로 바꾼다(02·08 노드 수정 — 구현 중 발견 시 보고).

---

## 7. 실행기

### 7.1 흐름 (`run_golden`)
```
1) 평가셋 읽기·검사(§4·§5.4) — 오류면 종료 코드 2
2) 설정 만들기: settings.model_copy(update={VERIFY_MAX_REWRITES: --verify-max})
3) 런타임 만들기: build_chat_runtime(settings, store=EvalTurnStore(), embed=None,
                                    tool_headers={X-Nadri-Rerank: on|off, X-Nadri-Rag-Mode: mix|hybrid})
4) 문항을 파일 순서대로 하나씩(동시 실행 없음 — 지연 측정 정확도, TourAPI·Tavily 사용량).
   후속 묶음은 첫 문항이 나온 자리에서 묶음 전체를 turn 순서로 실행
5) 문항마다: TurnInput 조립 → chat_event_stream(...) 을 끝까지 소비하며 이벤트·시각 기록
   → EvalTurnStore가 받은 CompletedTurn·usage·보안 이벤트 초안 → 채점(§6) → ItemResult
   → 진행 한 줄 출력 "[12/50] g-fact-012 정답 (3.4s)"
6) 집계(§9) → 결과 JSON 저장(§10.2) → 요약 Markdown 표 출력 → 사용량 DB 기록(§7.6)
```

### 7.2 런타임 조립 (`api/main.py`)
```python
async def build_chat_runtime(settings: Settings, *, store: TurnStore,
                             embed: Callable[[str], Awaitable[tuple[list[float], UsageRecord]]] | None,
                             tool_headers: Mapping[str, str] | None = None) -> ChatRuntime:
    """
    채팅 런타임(툴 로딩·그래프 컴파일·Moderation·분류기)을 앱 밖에서도 만들 수 있게 조립한다.

    Args:
        settings: 설정(평가는 VERIFY_MAX_REWRITES를 바꾼 복사본을 넘김)
        store: 턴 종료 기록 자리(앱 = DbTurnStore, 평가 = EvalTurnStore)
        embed: FAQ 임베딩 함수. None이면 FAQ 캐시 끔(평가)
        tool_headers: MCP 연결에 덧붙일 헤더(평가용 리랭커·모드 덮어쓰기, §8)
    Returns: ChatRuntime
    Raises: 02 get_chat_runtime과 같은 RuntimeUnavailable(툴 로딩 실패 등)
    """
```
- `get_chat_runtime`(02·08·09·12)은 이 함수를 `store=DbTurnStore(...)`, `embed=…`, `tool_headers=None`으로 부르도록 바꾼다(동작 같음, 지연 생성·락·캐시는 `get_chat_runtime`에 남김).
- 카나리 확인·`fixed_messages()` 로딩(08 §8.1)도 이 함수 안으로 옮겨 평가에서도 같은 검사를 거친다.

### 7.3 `EvalTurnStore` (메모리, DB 쓰기 없음)
```python
@dataclass
class EvalTurnStore:
    """TurnStore 구현. 턴 결과를 메모리에만 담아 두고 DB·한도·제목·요약·캐시 저장을 하지 않는다."""
    last: "TurnCapture | None" = None
    async def finish_done(self, ref, turn, events, usage) -> DoneIds: ...      # last 갱신, DoneIds(None, None, None)
    async def finish_blocked(self, ref, events, usage) -> int | None: ...       # last 갱신, None
    async def finish_error(self, ref, events, usage) -> None: ...               # last 갱신
    async def faq_lookup(self, vec) -> None: ...                                # 12 프로토콜 — 호출되면 AssertionError(embed=None이라 오면 안 됨)
    def take(self) -> "TurnCapture": ...                                        # last를 꺼내고 비움. 없으면 RuntimeError

@dataclass(frozen=True)
class TurnCapture:
    """한 턴에서 TurnStore가 받은 것."""
    outcome: Literal["done", "blocked", "error"]
    turn: CompletedTurn | None
    events: tuple[SecurityEventDraft, ...]
    usage: tuple[UsageRecord, ...]
```
- 구현 시점의 `TurnStore` 프로토콜에 메서드가 더 있으면 모두 "기록만" 하는 방식으로 채운다.
- 보안 이벤트를 DB에 쓰지 않으므로 골든 질문이 `security_events`·24 보고서를 오염시키지 않는다.

### 7.4 턴 입력 조립 (후속 묶음)
- 단일 문항: `TurnInput(raw_text=question, user_id=EVAL_USER_ID, session_id=str(uuid4()), prev_turn=None, history=(), location=item.location, turn_count=0)`.
- 묶음: 묶음마다 `session_id` 1개. 앞 턴이 **done으로 끝났을 때만** `TurnPair(turn_no, user_text=masked_text, assistant_text=final_text)`를 메모리 목록에 쌓는다(차단·장애 턴은 운영에서도 저장되지 않으므로 빼고 — 08 ADR-27·02 ADR-03). 다음 턴은 `SessionContext(user_id=0, session_id, turn_count=len(쌓인 것), summary_upto=0, summary_body=None, recent=쌓인 것[-10:])`로 09 `history_messages`·`prev_turn`을 불러 `history`·`prev_turn`을 채운다(요약은 쓰지 않음 — 묶음은 3턴 이하).
- `turn_count=0`이어도 `embed=None`이라 FAQ 조회는 일어나지 않는다.

### 7.5 이벤트 소비·시각 (`consume_stream`)
```python
@dataclass(frozen=True)
class StreamRecord:
    """SSE 한 턴을 소비한 기록."""
    events: list[tuple[float, str, dict]]   # (received_at 기준 ms, 이벤트 이름, data)
    end: Literal["done", "error"]
    block_code: str | None
    error_code: str | None
    attempt_end_ms: dict[int, float]        # 시도 k의 검증 결과가 나온 시각(아래)

def parse_sse(chunk: str) -> list[tuple[str, dict]]:
    """chat_event_stream이 내는 문자열 조각을 (이벤트, data)로 나눈다. ': ping' 주석은 버린다."""
async def consume_stream(stream: AsyncIterator[str], *, received_at: float, clock=time.monotonic) -> StreamRecord: ...
```
- `received_at`은 `chat_event_stream` 호출 직전 `time.monotonic()` — 운영과 같은 정의라 `CompletedTurn.timings`(`ttft_ms`·`draft_ms`·`total_ms`)를 그대로 쓴다.
- `attempt_end_ms[k]`: `status{revising, attempt=k+1}`를 받은 시각(시도 k 불합격), 마지막 시도는 `verified`·`replaced`·`warning` 중 첫 이벤트 시각. §6.3 잘라 계산의 시간 열에 쓴다.
- 이벤트 data는 결과 파일에 넣지 않는다(크기). `delta` 개수만 센다.

### 7.6 사용량 기록 (Q7)
실행이 끝나면 모든 문항의 `usage`를 **`usage_events`에 `kind="eval"`, `user_id=NULL`, `message_id=NULL`** 로 기록한다(FR-61 "모든 LLM 호출 비용 기록", [A] §10 "평가 토큰도 기록").
- 비용은 **원래 kind로** `pricing.cost_usd(record)`를 계산한 뒤 행의 `kind`만 `eval`로 바꾼다(그래야 moderation·web_search 0원, answer·verify LLM 단가가 맞게 들어감). `usage_row(record, user_id=None, message_id=None)` 결과에서 `kind`를 덮어쓴다.
- 실행 중간에 멈춰도(Ctrl+C·예외) 그때까지 돈 문항의 사용량은 `finally`에서 기록한다.
- `--no-record`로 끌 수 있다(테스트·짧은 시험 실행용 — 근거 확인(§5.4)은 여전히 DB를 쓴다).
- LightRAG 내부 키워드 추출 비용은 앱이 셀 수 없다(A14) — 결과 표에 "LightRAG 내부 호출 제외" 주석.

### 7.7 리랭커·모드 확인
실행 시작 직후 같은 헤더로 `load_tools(settings, extra_headers=…)`를 불러 얻은 `rag_query` 툴을 1회 직접 호출해(질문 "경복궁") 결과 맨 위 `meta`(§8.1)의 `rerank`·`mode`가 요청한 값과 같은지 확인한다. 다르면(헤더가 전달되지 않음) 종료 코드 1 — 잘못된 설정으로 50문항을 돌리고 엉뚱한 비교표를 만드는 것을 막는다.

---

## 8. tour-tools: 리랭커 on/off · 질의 모드 (Q1)

### 8.1 `rag_query` (01 §6.x 확장)
```python
@dataclass(frozen=True)
class RagOptions:
    """rag_query 1회의 검색 방식."""
    rerank: bool
    mode: Literal["mix", "hybrid"]

def rag_options_from(settings: Settings, headers: Mapping[str, str] | None) -> RagOptions:
    """설정 기본값에 평가용 헤더(X-Nadri-Rerank: on|off, X-Nadri-Rag-Mode: mix|hybrid) 덮어쓰기를 적용한다.
    헤더 값이 허용값 밖이면 ValueError(툴 오류 결과). 헤더 이름은 대소문자 무시."""

async def fetch_candidates(http, question: str, *, top_k: int, mode: Literal["mix", "hybrid"] = "mix") -> tuple[list[Candidate], dict]:
    """01 그대로 + 요청 본문 mode를 인자로."""

async def rag_query(question: str, deps: ToolDeps, lookup_pages=None, *, options: RagOptions | None = None) -> dict:
    """01 처리 순서 그대로, options(없으면 설정 기본값)에 따라 모드·리랭커를 고른다."""
```
- 리랭커 끔: 01 처리 순서 4)에서 `rerank` 대신 **LightRAG가 준 순서 그대로 앞 `RAG_TOP_K`개**. 후보 수(`RAG_CANDIDATES`)는 같게 받아 와 비교 조건을 맞춘다. 항목의 `score`는 `null`.
- 결과 dict 맨 위에 `"meta": {"rerank": bool, "mode": str}`를 더한다(LLM에도 보이지만 짧고 고정 형식 — §7.7 확인용). 02 `collect_evidence`는 `contentid` 키만 훑으므로 영향 없음.
- 로그 한 줄에 `rerank=on|off mode=…` 추가.
- **미확인**: LightRAG `/query/data`에 `mode:"hybrid"`를 주면 청크(`data.chunks`)를 돌려주는지(hybrid는 지식 그래프 기반이라 청크가 엔티티·관계에 딸린 것만 올 수 있음). 구현 시 1회 호출로 확인하고 §13에 기록. 청크가 0개로 오면 그 사실 자체가 A10 결과("hybrid는 이 구조에서 못 씀")다.

### 8.2 헤더 읽기 (`tools/server.py`)
- `rag_query` 래퍼에 FastMCP `Context` 인자를 더해 HTTP 요청 헤더를 읽는다: `ctx.request_context.request.headers`(**미확인**: mcp 1.30.x stateless Streamable HTTP에서 `request_context.request`가 Starlette `Request`로 채워지는지). 안 되면 대안: `BearerAuthMiddleware`가 두 헤더를 `contextvars.ContextVar`에 넣고 래퍼가 읽는다(인증 통과한 요청만).
- `Context` 인자는 툴 입력 스키마에 나오지 않아야 한다(LLM이 보는 툴 정의 = 프롬프트 캐시 프리픽스, ADR-16). 툴 스키마 스냅샷 테스트로 확인(test.md U-RQ22-06).
- 헤더는 인증(Bearer) 통과 뒤에만 읽힌다. api는 이 헤더를 보내지 않으므로 운영 동작은 설정값 그대로다.

### 8.3 `load_tools` (02·10)
```python
async def load_tools(settings: Settings, client_factory=MultiServerMCPClient,
                     extra_headers: Mapping[str, str] | None = None) -> list[BaseTool]:
    """02·10 그대로 + MCP 연결 headers에 extra_headers를 합친다(Authorization은 덮어쓰지 못함)."""
```

---

## 9. 집계 지표 (`summarize`)

### 9.1 한 실행의 요약 (`RunSummary`)
| 항목 | 계산 | 분모 |
|---|---|---|
| `n_items` / `n_error` / `n_stale` | 문항 수 / 장애 수 / 근거 기준일 지남 | — |
| `accuracy` | 정답 수 / (전체 − 장애) | 장애 제외 |
| `accuracy_by_category` | 분류별 같은 계산 | 〃 |
| `evidence_cited_rate` · `evidence_retrieved_rate` · `evidence_recall_mean` | §6.2 | `evidence` 있는 문항 − 장애 |
| `ttft_ms` · `total_ms` | p50 · p95 · 평균 (p는 **가장 가까운 순위 방식**: 정렬 후 `ceil(p/100 × n)`번째) | done으로 끝난 문항(차단 제외 — 답변 생성 안 함) |
| `tokens` | kind별 `input`·`cached`·`cache_write`·`output` 합 (None은 0으로 더하고 None 개수 따로) | 전체 |
| `cost_usd_total` · `cost_usd_per_item` | 11 `cost_usd` 합(Decimal) / 장애 제외 문항 수 | 〃 |
| `guard_false_positive` | 차단 수 / (전체 − 장애) + 단계별(`moderation`: unsafe·self_harm / `classifier`: jailbreak·injection·off_topic) + 분류별 + **차단 문항 목록**(id·코드·분류기 reason) | 모든 골든 문항은 정상 질문이므로 차단 = 오탐 |
| `pii_masked_items` | `masked_types`가 비어 있지 않은 문항 id 목록(기대 0 — A27) | — |
| `verify_status_counts` | `passed`·`failed`·`security_replaced` 수, `rewrite_count` 분포(0/1/2) | done 문항 |
| `verify_false_reject` | **초안이 정답**(§6.1)인데 시도 0 검증이 불합격시킨 수 / 초안 정답 수. 보안 불합격(`security_failed`)은 따로 셈 | done·채점 가능 |
| `verify_miss` | **초안이 오답**인데 시도 0 검증이 합격시킨 수 / 초안 오답 수 | 〃 |
| `by_cut` | §6.3의 k = off, 0, …, N 행마다 `accuracy`·`evidence_cited_rate`·`total_ms` p50/p95·`cost_usd_per_item`·끝 상태 분포 | done 문항(차단·장애는 모든 행에서 같음) |

- "채점 가능" = `facts`·`must_not`·`tools_any` 중 하나 이상이 있거나 기본 규칙 문항. 사실상 전 문항.
- 묶음의 2턴째 이후는 `accuracy_by_category`에 자기 분류로 들어가고, 따로 `followup` 줄(묶음 2턴째 이후만)도 낸다.

### 9.2 결과 표 (stdout Markdown) — 한 실행
```
## 골든 평가 — rerank=on mode=mix verify-max=2 (50문항, 2026-12-05 14:03 KST)
| 항목 | 값 |
| 정답률 | 41/48 (85.4%) — 장애 2 제외 |
| 근거 일치(인용) / 검색 적중 | 30/34 / 33/34 |
| 첫 토큰 p50/p95 | 2.1s / 4.8s |
| 전체 p50/p95 | 6.3s / 14.2s |
| 비용 합계 / 문항당 | $0.0951 / $0.00198 (LightRAG 내부 호출 제외) |
| 입력 검사 오탐 | 1/48 — g-small-003 classifier off_topic "…reason…" |
| 검증 오판 / 놓침 | 2/38 / 1/10 |
### 검증 상한별 (같은 답변에서 잘라 계산)
| 상한 | 정답률 | 근거 일치 | 전체 p50/p95 | 문항당 비용 | passed/failed/보안교체 |
| 끔(초안) | … |
| 0 | … |
| 1 | … |
| 2 | … |
### 분류별 정답률 · 오답 목록(id · 실패 검사)
```

### 9.3 비교표 (`--compare`)
결과 파일 여러 개를 받아 실행마다 한 열로 `accuracy`·`evidence_cited_rate`·`evidence_retrieved_rate`·`ttft p50/p95`·`total p50/p95`·`cost_usd_per_item`·`guard_false_positive`·`verify_false_reject`를 나란히 놓는다. 그리고 **문항별 차이**(한 실행에서는 정답, 다른 실행에서는 오답인 id 목록)를 붙인다.
- 결과 파일의 `golden_sha256`이 서로 다르면 표 맨 위에 경고("평가셋이 달라 직접 비교 불가").

### 9.4 읽는 법 (README에 같은 문단)
- 50문항 규모에서 1~2문항 차이는 LLM 무작위성 범위일 수 있다 — 비교표는 정답 수 차이가 `TIE_MARGIN`(2) 이하이면 "차이 작음"으로 표시한다. **판정·자동 선택은 하지 않는다**(사용자 결정).
- 리랭커·모드는 **검색 적중률**이 정답률보다 덜 흔들리는 지표다(답변 생성 무작위성을 덜 탐).
- 검증 상한은 §6.3 짝 비교라 실행 간 무작위성이 없다.

---

## 10. CLI (`nadri eval golden`)

| 옵션 | 기본 | 뜻 |
|---|---|---|
| `--rerank on\|off` | 설정값(`RAG_RERANK_ENABLED`) | tour-tools 리랭커(헤더로 이번 실행만, §8) |
| `--rag-mode mix\|hybrid` | 설정값(`RAG_QUERY_MODE`) | LightRAG 질의 모드(〃) |
| `--verify-max 0\|1\|2` | 설정값(`VERIFY_MAX_REWRITES`) | 이번 실행의 다시 쓰기 상한. 요약에는 0~이 값까지 잘라 계산한 행이 같이 나옴 |
| `--ids ID [ID …]` | 전체 | 이 문항만(묶음 문항을 하나라도 고르면 그 묶음 전체) |
| `--category C [C …]` | 전체 | 이 분류만 |
| `--file PATH` | `GOLDEN_PATH` | 평가셋 |
| `--out-dir PATH` | `RESULTS_DIR` | 결과 파일 위치 |
| `--label TEXT` | `rerank-<on/off>_<mode>_v<N>` | 결과 파일 이름·표 머리 |
| `--skip-stale` | 끔 | 근거가 지워진 문항을 빼고 실행(§5.4) |
| `--no-record` | 끔 | `usage_events` 기록 안 함 |
| `--check` | — | **LLM 호출 없음.** 형식·근거 검사 + 검수표 출력 후 종료(§10.1) |
| `--compare FILE [FILE …]` | — | **LLM 호출 없음.** 결과 파일 비교표 출력 후 종료(§9.3) |
| `--faq-pairs` | — | 임베딩만 호출. FAQ 임계값 표 출력 후 종료(§10.3) |

- `--check`·`--compare`·`--faq-pairs`는 서로, 그리고 실행 옵션과 함께 쓸 수 없다(인자 오류 2).
- 종료 코드: 0 성공(장애 문항이 있어도 0, 요약에 표시) · 1 실행 실패(툴 로딩 실패, §7.7 확인 실패, DB 연결 실패) · 2 인자·평가셋 형식 오류.
- 실행: `docker compose run --rm ingest nadri eval golden --rerank on --rag-mode mix --verify-max 2`.

### 10.1 `--check`
1. 모든 줄을 읽어 §4.1 규칙 검사(오류는 `줄 번호: id: 이유`로 모두 모아 출력).
2. 묶음 검사: 같은 `group`의 `turn`이 1부터 빈틈없이 이어지는지.
3. DB에서 근거 contentid 확인(§5.4) — 지워짐·없음은 오류, 기준일 지남은 경고. `wiki_pages`에 인덱싱 안 된 contentid도 경고("검색으로 찾을 수 없음").
4. 분포표(분류 × 지역 수) + 검수표(id · 분류 · 질문 · 정답 요약 · 근거 제목 · 기준일) 출력.
5. 오류가 하나라도 있으면 종료 코드 2.

### 10.2 결과 파일 `RESULTS_DIR/golden-<YYYYMMDD-HHMM>-<label>.json`
```json
{"run": {"label":"rerank-on_mix_v2","started_at":"…+09:00","finished_at":"…",
         "settings":{"rerank":true,"rag_mode":"mix","verify_max":2,"model":"gpt-6-luna","faq_cache":"bypass"},
         "golden_sha256":"…","n_items":50},
 "summary": { … §9.1 … },
 "items": [{"id":"g-fact-001","category":"fact","group":null,"turn":null,
            "end":"done","block_code":null,"error_code":null,"stale":false,
            "grade":"correct","failed_checks":[],
            "verify_status":"passed","rewrite_count":0,
            "cuts":{"off":{"grade":"correct","status":"unverified","total_ms":2100,"cost_usd":"0.0011"},
                    "0":{…},"1":{…},"2":{…}},
            "evidence_cited":true,"evidence_retrieved":true,"evidence_recall":1.0,
            "tools":["rag_query"],"masked_types":[],
            "timings":{…},"cost_usd":"0.00187","tokens":{…},
            "draft_text":"…","final_text":"…","guard_reason":null}]}
```
- 답변 원문을 넣는다(오답 원인을 사람이 보기 위해). 골든 질문은 개인정보가 없으므로 문제 없음. 파일은 커밋하지 않는다(`.gitignore`).
- 같은 이름이 있으면 `-2`, `-3`을 붙인다(덮어쓰지 않음).

### 10.3 `--faq-pairs` (FAQ 임계값 — Q6)
1. `paraphrase_group`이 있는 문항을 모두 모아 **가린 질문**(`mask_pii`)을 12 `embed_question`으로 임베딩.
2. 그 문항들 사이 모든 짝의 코사인 유사도를 계산 → "같은 묶음 짝"(적중해야 함)과 "다른 묶음 짝"(적중하면 안 됨)으로 나눔.
3. 임계값 0.85·0.88·0.90·0.92·0.93·0.94·0.95·0.96·0.97마다: 같은 묶음 짝 중 적중 비율(재사용률), 다른 묶음 짝 중 적중 수(**오적중** — 다른 질문에 남의 답을 줌), 오적중 짝 목록(상위 5개, 질문 두 개와 유사도).
4. 임베딩 사용량도 §7.6처럼 `kind="eval"`로 기록(약 $0.00002).
- 운영 캐시 조회는 `faq_cache` 행 중 **가장 가까운 1개**만 보지만, 이 표는 짝 단위로 본다 — 임계값의 위험(오적중)을 보수적으로 보여 준다.

---

## 11. 비용 추정 ([A] §10 단가)

| 실행 | 계산 | 금액 |
|---|---|---|
| 한 번 실행(50문항, 상한 2) | 문항당 ≈ $0.0019(분류기·답변·검증·다시 쓰기 평균) | ≈ **$0.10** |
| 비교 기본 세트(§13 HITL: 기준 + 리랭커 끔 + hybrid = 3회) | 3 × $0.10 | ≈ **$0.30** |
| LightRAG 내부 키워드 추출(앱 집계 불가) | 50 × ≈$0.0002 × 3 | ≈ $0.03 |
| `--faq-pairs` | 약 20문항 임베딩 | < $0.001 |
| Tavily | web 4문항 × 3회 ≈ 12~20크레딧(월 1,000 무료 안, A28) | $0 |
| TourAPI 실시간 몫 | nearby·festival 8문항 × 1~2호출 × 3회 ≈ 24~48건(하루 200 몫 안) | $0 |

- 시간: 문항당 약 5~20초 순차 → 한 번 실행 약 5~15분.
- 다시 쓰기가 잦으면 문항당 비용이 $0.0038까지 오른다 — 그래도 한 번 실행 $0.2 이하.

---

## 12. 앞 작업과 달라지는 점 · 앞 작업 테스트 수정

| # | 내용 | 대상 | 처리 |
|---|---|---|---|
| 1 | `fetch_candidates`가 `mode` 인자를 받음(기본 `"mix"`) | 01 U-RQ(요청 본문 검사) | 기본값이 같아 수정 없음. hybrid 테스트 추가 |
| 2 | `rag_query` 결과 맨 위에 `meta{rerank, mode}` | 01 U-RQ 결과 dict 통째 비교 테스트 | 기대값에 `"meta":{"rerank":true,"mode":"mix"}` 추가. 항목 비교면 수정 없음 |
| 3 | 리랭커 끔이면 항목 `score: null` | 01·02 | 기본(켬)에서는 그대로 — 수정 없음 |
| 4 | `rag_query` 래퍼에 `Context` 인자 | 01 툴 스키마 테스트(U-SV 등) | 스키마 불변이어야 함 — 기존 테스트가 그대로 통과하는지가 검사 |
| 5 | `load_tools(..., extra_headers=None)` | 02·10 U-TL | 기본값 None이라 수정 없음 |
| 6 | `get_chat_runtime` → `build_chat_runtime` 호출로 바뀜 | 02·08·09·12 런타임 테스트 | 동작 같음. `get_chat_runtime` 내부를 몽키패치하는 테스트가 있으면 `build_chat_runtime`을 대상으로 바꿈 |
| 7 | `Settings`에 `RAG_RERANK_ENABLED`·`RAG_QUERY_MODE` | 01 U-CFG(필드 목록 고정 비교라면) | 목록에 추가 |
| 8 | compose ingest 환경변수·마운트 | 01·03 compose 검사 테스트(있으면) | 기대값 추가 |
| 9 | `usage_events`에 `kind="eval"` 행이 생김(user_id NULL) | 19 사용량 집계(아직 작성 전) | 19 spec에 "평가(eval) — 시스템" 줄로 보이게 알림 |

상위 문서와의 차이(구현 판단):
1. **평가 프로세스가 tour-tools 설정을 바꾸는 통로**: [PL]은 `--rerank`·`--rag-mode` 옵션과 설정값만 적었는데, 리랭커·모드는 다른 컨테이너(tour-tools) 안에 있다. 요청 헤더 덮어쓰기로 이번 실행만 바꾼다(Q1).
2. **"검증 끔"의 뜻**: FR-70 "검증 에이전트 끔/1회/2회"와 [PL] `--verify-max 0|1|2`가 다르다(상한 0 = 검증은 1번 하고 다시 쓰기만 안 함). 둘 다 보여 준다 — "끔"은 초안 기준 계산, 0/1/2는 다시 쓰기 상한(§6.3, Q2).
3. **FAQ 임계값 결정 재료**: [PL] HITL은 FAQ 임계값 결정을 요구하지만 골든은 캐시를 우회하므로 그 재료가 없다. `--faq-pairs`를 더한다(Q6).
4. **ingest 컨테이너 키**: [A] §2.1은 `eval golden`을 ingest CLI로 두지만 ingest에는 `TAVILY_API_KEY`(와 20 전이면 `OPENAI_API_KEY`)가 없다. compose에 추가한다(§3.3).
5. **`./eval` 읽기 전용 vs 결과 파일 쓰기**: [A] §7은 `./eval:/app/eval:ro`. 결과 하위 폴더만 쓰기 가능으로 겹쳐 건다(Q8).
6. **런타임 조립 분리**(§7.2): "같은 코드로 프로세스 안 실행"([PL])을 위해 `get_chat_runtime`(요청·앱 상태에 묶임)에서 조립부를 떼어 낸다.

---

## 13. 가정 판정·결정 (구현 중 결과 기록)

판정 결과는 이 표 결과 열과 `PROGRESS.md` 결정 로그에 남긴다. 아래 "결정"은 모두 **사용자**가 비교표를 보고 한다(설정값만 변경, compose `environment`에 값 + 주석으로 근거 결과 파일 이름).

| ID | 확인 방법 | 기록할 것 | 실패·결과에 따른 선택지 | 사용자 확인 | 결과 |
|---|---|---|---|---|---|
| **A10** mix ≥ hybrid | HITL-3·4: 기준 실행 vs `--rag-mode hybrid` | 정답률·검색 적중률·근거 일치·지연, 문항별 차이 | hybrid가 뚜렷이 나음 → `RAG_QUERY_MODE=hybrid` / 비슷하거나 mix가 나음 → mix 유지 | 필수 | |
| 리랭커 on/off (ADR-06) | HITL-3·4: 기준 vs `--rerank off` | 위와 같음 + `rerank_ms`(tour-tools 로그) | 끔이 비슷하면 지연·CPU를 아끼려 끌 수 있음 → `RAG_RERANK_ENABLED=false` / 켬 유지 | 필수 | |
| **A25** 검증 0/1/2 | HITL-3 기준 실행의 "검증 상한별" 표(+ 선택 HITL-7 실제 상한 0 실행) | 상한별 정답률·지연 p50/p95·비용, 오판·놓침 | `VERIFY_MAX_REWRITES` 2 유지 / 1 / 0 ([A] A25 대안 범위) | 필수 | |
| **A22** Moderation 정상 질문 오탐 | 모든 실행의 `guard_false_positive.moderation` | 걸린 문항·범주 | 0건 → 그대로 / 1건 이상 → 사례 보고, 범주 임계값은 23 결과와 함께 결정(Q10) | 오탐 시 | |
| **A24** 분류기 오탐 | `guard_false_positive.classifier`(smalltalk·common·out_of_area·후속 묶음 중심) | 걸린 문항·라벨·reason | 0건 → 그대로 / 있으면 classify.md 예시 보강(프롬프트 — 사용자 확인) 또는 off_topic 안내형 완화(**사용자 확인**, [A] A24) | 오탐 시 필수 | |
| A27 PII 가림 오탐 (참고) | `pii_masked_items` | 가려진 골든 문항 | 있으면 07 규칙 사례로 보고 | 발생 시 | |
| FAQ 임계값 (ADR-13) | HITL-5 `--faq-pairs` | 임계값별 재사용률·오적중 | 오적중 0인 가장 낮은 값 근처에서 사용자가 선택 / 0.95 유지 | 필수 | |
| hybrid 청크 반환 (§8.1 미확인) | 구현 중 1회 호출 | `data.chunks` 개수 | 0이면 hybrid 비교는 "사용 불가"로 기록 | 아니오 | |

---

## 14. 엣지케이스

| 상황 | 동작 |
|---|---|
| `golden.jsonl` 없음 | 종료 코드 2, "평가셋 파일이 없어요: <경로>" |
| 줄 JSON 깨짐·모르는 키·중복 id·묶음 turn 빈틈 | 모든 오류를 모아 출력, 종료 코드 2 |
| 근거 contentid 삭제됨 | 오류(실행 거부). `--skip-stale`면 그 문항만 빼고 경고 |
| 근거 기준일이 문항보다 새로움 | 경고, `stale:true`, 집계에 `n_stale` |
| tour-tools 꺼짐·토큰 틀림 | 런타임 조립 실패 → 종료 코드 1 |
| 헤더가 안 먹음(§7.7 meta 불일치) | 종료 코드 1, "리랭커·모드 설정이 tour-tools에 전달되지 않았어요" |
| 문항 실행 중 `error{llm_unavailable/guard_unavailable/timeout}` | 그 문항 `end:error`, 정답률 분모 제외, 다음 문항 계속 |
| 문항 실행 중 예상 못 한 예외(코드 버그) | 그 문항 `end:error`, `error_code:"exception:<클래스명>"`, 계속 |
| 입력 검사 차단 | `grade:wrong`, `failed_checks:["blocked:<code>"]`, 오탐 목록에 reason과 함께 |
| 묶음 1턴째가 차단·장애 | 2턴째는 그 턴 없이(history 비고) 실행 — 운영과 같음. 결과에 `group_broken:true` |
| `tools_any`인데 툴 오류(예: Tavily 장애로 web_search가 오류 기록) | 툴은 "호출됨"으로 셈(선택을 봄). 답변 품질은 `facts`가 따로 봄 |
| 리랭커 끔 + 후보 0개 | 01과 같음(`items: []`) |
| `--verify-max 0` | 잘라 계산 행은 off·0 두 줄 |
| `--ids`에 없는 id | 인자 오류 2 |
| Ctrl+C | 그때까지의 결과로 집계·결과 파일 저장(`run.interrupted:true`), 사용량 기록 |
| TourAPI 실시간 몫 소진 | `tour_live`가 툴 오류 결과 → 답변은 계속(10), nearby·festival 정답률이 떨어질 수 있음 — 요약에 tour_live 오류 수 표시 |
| 결과 폴더가 쓰기 불가 | 종료 코드 1(실행 전에 쓰기 확인 — 다 돌리고 저장 실패하지 않게) |
| DB 연결 실패 | `--check`·근거 확인·사용량 기록에 DB 필요 → 종료 코드 1. `--no-record --skip-db-check`는 만들지 않음(근거 확인은 필수) |

---

## 15. 완료 기준 (DoD)

1. test.md ① 전부 통과(`cd ~/code/myAgent/backend && uv run pytest -m "not integration"`), §12 앞 작업 테스트 수정 후 통과.
2. `eval/golden/golden.jsonl` 40~60문항, §4.2 분포(사용자 조정 반영), `--check` 오류 0, **사용자 검수 완료**(HITL-1).
3. `eval/README.md`: 형식·채점 규칙·실행·비교·검수 체크리스트·읽는 법(§9.4).
4. HITL-3·4·5 결과표를 사용자에게 보고하고, 사용자가 `VERIFY_MAX_REWRITES`·`RAG_QUERY_MODE`·`RAG_RERANK_ENABLED`·`FAQ_CACHE_THRESHOLD` 값을 결정. 값은 compose `environment`에만 반영(코드 기본값은 바꾸지 않음 — Q11), §13 결과 열·`PROGRESS.md` 결정 로그 갱신.
5. 분류기·Moderation 오탐 사례가 있으면 보고하고 사용자 결정을 기록(코드 변경은 이 작업 밖).
6. 운영 동작 불변: 헤더 없는 `rag_query`가 22 전과 같은 결과(meta 제외), 기본 설정으로 채팅 E2E 통과.
7. 한국어 docstring·단계 주석([CL]). 커밋 `feat/22-eval-golden`, `[Feat] …` + 작업 목록 + `Author:`, AI 공동작성 표기 없음. `dev` 병합은 G5 후. `PROGRESS.md` 갱신.

---

## 16. 확인 질문

| # | 질문 | 선택지 | 추천안 |
|---|---|---|---|
| 22-Q1 | 평가(ingest 컨테이너)가 tour-tools의 리랭커 on/off·질의 모드를 어떻게 바꿀까 | A: **요청 헤더로 이번 실행만 덮어쓰기**(`X-Nadri-Rerank`·`X-Nadri-Rag-Mode`, 인증 통과 요청만, api는 안 보냄) / B: 환경변수를 바꿔 tour-tools를 재기동한 뒤 실행(CLI 옵션은 확인용 — `meta`로 대조) | **A** — 명령 한 줄로 비교 실행, 운영 설정·컨테이너를 건드리지 않음. 위험은 "토큰을 가진 api가 검색 방식을 바꿀 수 있음"뿐(데이터 접근 범위는 같음) |
| 22-Q2 | FR-70 "검증 끔/1회/2회"를 어떻게 측정할까 | A: **상한 2 실행 1번에서 끔(초안)·0·1·2를 잘라 계산**(같은 답변 위 짝 비교, 비용 1배) + `--verify-max`로 실제 실행도 가능 / B: 상한마다 따로 실행(비용 3배, 실행 간 무작위성 섞임) | **A** |
| 22-Q3 | 정답 채점 방식 | A: **코드만**(정답 표현 OR 목록·금지 표현·근거 contentid·툴 호출 — 결정적, 무료) / B: 코드 + 애매한 문항만 LLM 판정(23과 같은 방식, 비용·무작위성 추가) | **A** — 문항을 사용자가 검수하며 표현 목록을 넉넉히 넣음. 오답 목록에 답변 원문이 있어 사람이 확인 가능 |
| 22-Q4 | 비교 실행 범위 | A: **기준(on·mix·2) + 리랭커 끔 + hybrid = 3회**(한 번에 한 가지만 바꿈, 검증 상한은 잘라 계산) / B: 2×2×3 전부 12회 | **A** (약 $0.3, 30~45분) |
| 22-Q5 | 분류·분포(§4.2) — `no_data`(자료 없음 2)·`out_of_area`(서울·제주 밖 3)를 [PL] 목록에 더해도 될까, 총 50 목표 | A: **§4.2 표대로** / B: [PL] 목록만(관광 사실·조건·주변·축제·웹 + 스몰토크·상식·후속) / C: 사용자가 수 조정 | **A** — no_data는 "지어내지 않음"(FR-12), out_of_area는 08-Q2 분류 경계 오탐 측정 |
| 22-Q6 | FAQ 임계값 결정 재료 | A: **`paraphrase_group` + `--faq-pairs`로 임계값별 재사용률·오적중 표**(임베딩만, 거의 무료) / B: 측정 없이 0.95 유지(ADR-13 "보수적 시작") | **A** — [PL] HITL이 임계값 결정을 요구하는데 골든 본 실행은 캐시를 우회해 재료가 없음 |
| 22-Q7 | 평가 실행의 AI 사용량을 DB에 남길까 | A: **`usage_events`에 `kind="eval"`, 사용자 없음으로 기록**(월 비용·$10 경고에 포함, 24 매일 평가와 같은 kind) / B: 결과 파일에만(대시보드 월 비용에서 빠짐) | **A** — FR-61 "모든 호출 비용 기록". `--no-record`로 끌 수 있음 |
| 22-Q8 | 결과 파일 위치 | A: **`eval/results/`(git 제외), 그 폴더만 쓰기 가능으로 마운트** / B: 결과를 화면에만(파일 없음 — `--compare` 불가) / C: 결과 요약 파일을 커밋 | **A** (요약 숫자는 §13·PROGRESS에 옮겨 적음) |
| 22-Q9 | 장애로 끝난 문항(`llm_unavailable`·`timeout` 등) | A: **정답률 분모에서 빼고 따로 표시, 재시도 없음**(`--ids`로 재실행) / B: 오답으로 셈 / C: 1회 자동 재시도 | **A** — 장애는 품질이 아니라 가용성 문제. 수가 많으면 요약에 바로 보임 |
| 22-Q10 | Moderation 정상 질문 오탐이 나오면 22에서 범주별 임계값 설정을 추가할까(08-Q4 이월) | A: **22는 보고만, 결정은 23 결과(유해 탐지율)와 같이** / B: 22에서 범주별 임계값 설정 추가 | **A** — 오탐을 줄이려 임계값을 올리면 탐지율이 떨어져 23 결과 없이 정할 수 없음 |
| 22-Q11 | 결정된 설정값을 어디에 반영할까 | A: **compose `environment`에 값 + 근거 결과 파일 이름 주석**(코드 기본값은 그대로) / B: `Settings` 기본값을 바꿈 | **A** — "설정값만 변경"([PL]), 되돌리기 쉬움 |
| 22-Q12 | 골든 문항이 데이터 변경(매일 현행화)으로 낡으면 | A: **실행 전 근거 검사 — 삭제는 실행 거부(`--skip-stale`로 제외 가능), 기준일 지남은 경고·따로 집계** / B: 검사 없음 | **A** |
