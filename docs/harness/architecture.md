# 아키텍처 — nadri (관광 챗봇 PWA + 관리자 백오피스)

> 하네스 Phase 2b 산출물. **G3 최초 승인 (2026-11-07)** → **G3 재검토 재승인 (2026-11-21)**. solution-architect.
> 재작성 사유: 2026-11-20~21 사용자 결정 — Hermes 제거 → LangGraph(답변+검증 에이전트)·LangChain, 매일 품질 평가·개선안·HITL, AI 보안 5겹, 👍/👎 피드백. 요구사항은 `requirements.md` §8 개정 이력(2026-11-21) 기준.
> 입력: `docs/harness/requirements.md`(2026-11-21 개정본), `docs/harness/stack-options.md`(G2 승인본), `docs/harness/PROGRESS.md`, `TECH_STACK.md`, `docs/analysis/00·01`.
> 출처 표기: [R]=requirements.md, [S]=stack-options.md (S1~S21 결정, F1~F12 사실), [TS]=TECH_STACK.md, [AN]=00-initial-analysis.md, [DS]=01-data-sources.md, [PG]=PROGRESS.md, [CL]=CLAUDE.md, [V]=이번 재작성에서 직접 조회한 사실(§12.1, 조회일 2026-11-21).
> **이 문서는 G1·G2·사용자 결정을 바꾸지 않는다.** 문서 간 상충은 §11, 확인하지 못한 외부 동작은 **미확인**으로 표시하고 §12 검증 계획에 넣는다.
> 규모 전제: 실사용자 사실상 1명, 상한 5명 [R D-21, NFR-61]. 수평 확장·고가용성은 설계하지 않는다. **보안이 응답 속도보다 우선**(D-24) — 지연 최적화는 v1.1 이후.

---

## 1. 확정 기술스택

| 영역 | 확정 | 근거 |
|---|---|---|
| 실행 | WSL2 Ubuntu-22.04 + Docker Compose, named volume | [R D-14, NFR-20·21] |
| 프론트 | Next.js 16(App Router, TS) + Tailwind 4 + shadcn/ui, react-markdown+remark-gfm(**raw HTML 끔, 이미지 렌더 끔, 링크 허용 목록**), fetch+ReadableStream SSE 파서 | [S S16], [R NFR-14] |
| PWA | `app/manifest.ts` + 최소 서비스워커(오프라인 캐시 없음) | [S S17] |
| 백오피스 | 같은 Next.js 앱의 `/admin`(가입·사용량·**품질 리포트**), 권한 검사는 FastAPI `/api/admin/*` | [S S18], [R FR-102] |
| BFF | Python 3.12, uv, FastAPI, SQLAlchemy 2.x(async)+asyncpg, Alembic, argon2-cffi | [S S11] |
| **에이전트** | **LangGraph** `StateGraph`(답변 노드 ⇄ 툴 노드 → 검증 노드 → 다시 쓰기 루프), api 프로세스 안에서 요청마다 stateless 실행, **체크포인터 미사용** | [R D-04, NFR-30, FR-90] |
| **LLM 호출** | **LangChain** `ChatOpenAI`(답변·검증·입력 분류·제목·요약·평가·개선안·허브 페이지), `OpenAIEmbeddings`(FAQ 캐시). 모든 `ChatOpenAI`는 `use_responses_api=True`, `store=False` | [R D-04, NFR-41], ADR-11·17 |
| OpenAI SDK 직접 | STT(`gpt-transcribe`), **Moderation API**(`omni-moderation-latest`) — LLM 생성 호출이 아님(ADR-11) | [R D-04, NFR-12] |
| 모델 | OpenAI `gpt-6-luna` 하나. fallback 없음. 임베딩 `text-embedding-3-small`(1536) | [R D-05, NFR-41·42], [S S1·S3] |
| MCP 연결 | api(·ingest) → tour-tools: `langchain-mcp-adapters` Streamable HTTP + 내부 토큰 헤더 | [R D-08], ADR-24 |
| 툴 서버 | 공식 `mcp` Python SDK **1.30.x**(FastMCP, Streamable HTTP, stateless). 2.x 아님 — 어댑터가 `mcp<2` 요구 [V] | [S S10], ADR-24 |
| 웹 검색 | `langchain-tavily` `TavilySearch`를 답변 에이전트에 직접 바인딩(`search_depth="basic"`, `max_results=5`) | [R FR-54], ADR-25 |
| 입력·출력 검사 | 자체 `guard` 모듈: 규칙 기반 개인정보 가리기 → Moderation → LLM 분류기(입력) / Moderation + 코드 검사 + 검증 에이전트 보안 항목(출력) | [R NFR-12·13·35] |
| Graph RAG | LightRAG 서버 v1.5.7, `PGTableGraphStorage`, 질의 `mix`(→ `hybrid` 비교), 자체 리랭크 끔, **자체 OpenAI 연동 유지** | [S S4·S5], [S F11] |
| 리랭커 | `BAAI/bge-reranker-v2-m3` CrossEncoder, **tour-tools 내장**(CPU) | [S S5] |
| DB | PostgreSQL + pgvector 단일 인스턴스(`pgvector/pgvector:pg18`), Redis 없음 | [R D-07], [S S13] |
| STT / TTS | OpenAI `gpt-transcribe` (`SttProvider`) / ElevenLabs `eleven_flash_v2_5` (`TtsProvider`) | [S S2·S20], [R NFR-50] |
| 프록시·외부 접속 | Nginx(SSE 버퍼링 off) + Cloudflare Named Tunnel, `.dev` 도메인 | [R D-15, NFR-22], [S S6] |
| 메일 | Gmail SMTP + 앱 비밀번호 | [S S7] |
| 스케줄러 | `ingest` 컨테이너 상주 APScheduler: **01:00 KST** 현행화·90일 삭제, **03:00 KST** 품질 평가·개선안·공격 세트 | [S S15], [R FR-45·100] |
| FAQ 캐시 | pgvector 유사도 캐시, **검증 통과** 답변만, 👎 받으면 제외 | [S S14], [R FR-92·103] |
| 관측 | PostgreSQL 테이블 + 백오피스. **LangSmith 등 외부 추적 미사용**(환경변수로 명시적 끔) | [S S21], [R NFR-36] |
| 테스트 | pytest · Vitest + RTL · Playwright | [S S19] |
| 진행 방식 | 별도 PoC 없음 — 위험 연동은 **첫 구현 작업(최소 end-to-end)** 에서 실행 검증 | [PG G2] |

**고정 후보 버전** (PyPI 조회 2026-11-21, §12.1): `langgraph` 1.2.24 · `langgraph-prebuilt` 1.1.3 · `langchain` 1.5.2(`langchain-tavily` 의존) · `langchain-core` 1.8.4 · `langchain-openai` 1.8.5 · `langchain-mcp-adapters` 0.3.2 · `langchain-tavily` 0.2.18 · `mcp` **1.30.0** · `openai` 3.57.0 · `lightrag-hku` 1.5.7. 모두 Python ≥3.11 지원. `uv.lock`으로 고정한다.

---

## 2. 모듈 구성 (컨테이너 8개)

Hermes 컨테이너를 없앴고 그 역할(에이전트 루프)은 api 프로세스 안 LangGraph로 옮겼다. 새 컨테이너는 없다. 품질 평가 배치는 `ingest`에 넣는다(이름 유지) [R FR-100].

| # | 서비스 | 이미지 | 존재 이유 (한 줄) | 외부 노출 |
|---|---|---|---|---|
| 1 | `cloudflared` | `cloudflare/cloudflared` (`tunnel run --token`) | 호스트 인바운드 포트 없이 HTTPS를 제공하는 유일한 외부 진입점 | 아웃바운드만 |
| 2 | `nginx` | `nginx` | `/`·`/admin`→web, `/api/*`→api를 한 출처로 묶고 SSE 버퍼링·업로드 크기 설정 | ✗ (`cloudflared`→`nginx:80`) |
| 3 | `web` | Next.js standalone 빌드 | 챗봇 UI·PWA·백오피스 화면 | ✗ |
| 4 | `api` | 자체(Python `app` 타깃) | 브라우저가 부르는 유일한 API: 인증·한도·대화 정본·**입력/출력 검사·LangGraph 에이전트 실행**·STT/TTS·피드백·관리자 API | ✗ |
| 5 | `tour-tools` | 자체(Python `tools` 타깃, torch 포함) | 읽기 전용 관광 툴 4종을 MCP로 제공하고 RAG 후보를 리랭크(읽기 전용 DB 롤·torch 분리) | ✗ |
| 6 | `lightrag` | LightRAG 서버 이미지(v1.5.7 고정) | 위키 페이지의 그래프+벡터 인덱스 관리·후보 검색 | ✗ |
| 7 | `postgres` | `pgvector/pgvector:pg18` | 모든 영속 데이터의 단일 저장소 | ✗ |
| 8 | `ingest` | 자체(Python `app` 타깃) | 01:00 수집·위키·인덱싱·현행화·90일 삭제 / **03:00 평가 에이전트·개선안 에이전트·공격 세트** | ✗ |

v1.1 이후: `stt-gpu`(faster-whisper) [TS §9], FR-49 확장 원천은 `ingest`·`tour-tools` 안의 모듈로 추가 [DS §4].

### 2.1 컨테이너별 책임 상세

**web (Next.js)**
- 화면: 로그인·가입 신청·비밀번호 재설정·승인 대기 / 채팅(사이드바 세션 목록·삭제, 초안 스트리밍 → "✓ 확인됨"·교체·경고 표시, 👍/👎 + 👎 사유, PTT 녹음, TTS 재생, 위치 동의 토글, 한도 초과 안내) / `/admin`(가입 신청, 사용량 대시보드, 사용자 비활성화, **품질 리포트·개선안 결정**).
- 데이터는 **브라우저에서만** `/api/*` 호출(ADR-12). 권한 판단은 api.
- 마크다운 렌더: raw HTML 끔, `img` 요소 렌더 안 함, 링크는 `done` 이벤트의 `allowed_urls`에 있는 것만 클릭 가능(그 외는 일반 텍스트), 초안 단계에서는 모든 링크 비활성(ADR-22).
- 서비스워커는 `/api/*`를 가로채지 않는다(SSE 보호).

**api (FastAPI BFF + 에이전트 실행)** — 내부 모듈

| 모듈 | 책임 | 요구사항 |
|---|---|---|
| `auth` | 가입 신청, 로그인/로그아웃, 세션 쿠키, 비밀번호 변경·재설정, 잠금·지연 | FR-01~07, NFR-01~05 |
| `ratelimit` | `rate_limits` 테이블 고정 윈도 카운터(로그인·재설정·STT·채팅 분당 10회) | NFR-02·06 |
| `quota` | 일일 50회 한도(추가 요청 없음 — 2026-11-22) | FR-62 |
| `guard` | **입력 검사**(PII 가리기 → Moderation → LLM 분류기), **출력 검사**(Moderation, 코드 검사: 인용 contentid·링크 허용 목록·카나리 문자열), 자해 신호 109 안내, `security_events` 기록 | NFR-11~16·35 |
| `agent` | LangGraph 그래프(답변·툴·검증·다시 쓰기), MCP 툴 로딩, Tavily 툴, 툴 결과 수집(출처·contentid·URL) | FR-11~13·19·50~55·90 |
| `chat` | 세션 CRUD, 컨텍스트 조립(요약 1 + 최근 10턴), 그래프 스트림 → 브라우저 SSE 이벤트 변환, 턴 저장, 제목·요약(그래프 밖 단발 호출) | FR-10~22, FR-91, D-10 |
| `faq_cache` | 첫 질문(가린 텍스트) 임베딩 → 유사도 조회/저장, 👎 시 제외 | FR-60·92·103, S14 |
| `feedback` | 👍/👎 + 사유 저장, 👎 시 연결 FAQ 캐시 삭제 | FR-103 |
| `voice` | `SttProvider`(openai) · `TtsProvider`(elevenlabs) | FR-30~32, NFR-50·51 |
| `mail` | Gmail SMTP 인증코드 발송(백그라운드) | FR-05·07 |
| `admin` | 가입 승인, 사용량 집계, 비활성화, **품질 리포트 조회·개선안 결정** | FR-80~84, FR-102 |
| `usage` | `usage_events` 기록, 단가표로 비용 계산, 월 $10 경고 | FR-61·63, NFR-43·60 |
| `cli` | `create-admin` | FR-80 |

**tour-tools (MCP 서버)** — 런타임 **읽기 전용** 툴만 노출(ADR-08). 변경 없음, 인증 헤더만 추가(ADR-24).

| 툴 | 동작 | 데이터 |
|---|---|---|
| `rag_query(question)` | LightRAG `/query/data`(mode `mix`)로 후보 약 30개 → CrossEncoder 재채점 → 상위 5개 + `wiki_pages`의 contentid·출처·기준일 | FR-50 |
| `data_query(area, sigungu?, content_type?, keyword?, near?{lat,lng,radius_km}, on_date?, sort, limit≤20)` | `tour_items` 파라미터화 조회(SQL 생성 없음), 하버사인, 행사 기간 필터 | FR-51 |
| `tour_live(op, …)` | TourAPI 실시간: 진행 중 축제(`searchFestival2`), 좌표 주변(`locationBasedList2`) | FR-52 |
| `get_datetime()` | 현재 KST 일시·요일·이번 주말/다음 주 범위 | FR-19·53 |

- 모든 툴 결과는 **구조화된 JSON**(항목마다 `contentid`·`source`·`as_of`, 실시간이면 `source=실시간 조회`). api가 이 결과에서 출처·contentid를 직접 뽑는다(ADR-05).
- TourAPI `usetime`은 자유 텍스트라 운영 여부는 원문을 돌려주고 해석은 LLM에 맡긴다(추정, 첫 적재 작업에서 확인).

**lightrag** — 서버 모드, `LIGHTRAG_API_KEY`, PostgreSQL 저장소 + `PGTableGraphStorage`, `SUMMARY_LANGUAGE=Korean`, `RERANK_BINDING=null`, LLM `gpt-6-luna`, 임베딩 `text-embedding-3-small`. 자체 OpenAI 연동(LangChain 미경유). insert/delete는 `ingest`만.

**ingest** — APScheduler 상주 + CLI

| 모듈 | 책임 |
|---|---|
| `tourapi` · `budget` · `raw` · `upsert` · `wiki` · `indexer` | (변경 없음) KorService2 수집, 일일 호출 예산, raw 스냅샷, `tour_items` upsert, 엔티티 템플릿·허브 LLM 작성(LangChain `ChatOpenAI`)·lint·위키 git, 해시 기반 LightRAG delete→insert |
| `jobs.daily_sync` | 01:00 KST 현행화 → 허브 → FAQ 무효화 → lint → 위키 커밋 → 90일 삭제·만료 정리 (§3.3) |
| `jobs.daily_quality` | **03:00 KST** 평가 에이전트 → 공격 세트 → 개선안 에이전트 → 보고서·개선안 저장 (§3.7). 코드는 `nadri.eval` |
| CLI | `ingest bootstrap`, `ingest sync --now`, **`eval quality --date YYYY-MM-DD`**(수동 재실행), **`eval golden`**(FR-70 골든 평가, 수동) |

**postgres** — 인스턴스 1개 안에 DB 2개(ADR-07): `nadri`(Alembic), `lightrag`(LightRAG 자체 관리). 둘 다 `vector` 확장.

### 2.2 요구사항 → 모듈 추적 (요약)

| 요구사항 | 모듈 |
|---|---|
| FR-01~07, NFR-01~06 | api `auth`·`ratelimit`·`mail` |
| FR-10~22, D-09·10, NFR-30 | api `chat`·`agent`, tour-tools |
| FR-30~32, NFR-50·51 | web 녹음/재생, api `voice` |
| FR-40~48 | ingest |
| FR-50~55 | tour-tools, api `agent`(Tavily 툴), web(위치 동의) |
| FR-60~63, NFR-40~43, NFR-60 | api `faq_cache`·`quota`·`usage` |
| FR-70 | `eval/`(데이터) + `nadri.eval`(CLI·배치) |
| FR-80~84, FR-102 | web `/admin`, api `admin`·`cli` |
| FR-90~92 | api `agent`(검증 노드)·`chat`(SSE)·`faq_cache` |
| FR-100~105 | ingest `jobs.daily_quality` + `nadri.eval`, api `feedback`·`admin` |
| NFR-07~17 | api `guard`·`agent`, compose, nginx, web 렌더러, 프롬프트 |
| NFR-35·36 | api `guard.pii`, `nadri.eval.anonymize`, compose 환경변수 |
| NFR-20~24 | compose, cloudflared, nginx, volume |

---

## 3. 데이터 흐름

### 3.1 채팅: 입력 검사 → 그래프 → 출력 검사 → SSE → 저장 (FR-10~22, FR-50~55, FR-60~62, FR-90~92, NFR-12~15)

```
브라우저 ─POST /api/chat/sessions/{id}/messages {text, location?}─▶ cloudflared ─▶ nginx ─▶ api
api:
 1) 세션 쿠키·CSRF·status=active (NFR-04·05, FR-06)
 2) 분당 10회 (NFR-06) → 초과 429
 3) 오늘(KST) 사용량 < 50 (FR-62, 관리자는 건너뜀) → 초과 429 {code:"quota_exceeded"}
 4) 세션 turn_count < 50 (FR-15) → 초과 409 {code:"session_full"}
 ── SSE 시작 ──  event: meta {session_id, user_text_masked, masked_types[]}
                 event: status {stage:"checking"}
 5) 입력 검사 (순서대로, 앞 단계 통과해야 다음 단계 — §3.8, ADR-20)
    ① PII 가리기(규칙, 메모리 안에서) → 이후 모든 단계는 가린 텍스트만 사용
    ② Moderation API (가린 텍스트) — 실패·타임아웃 → 차단(error guard_unavailable, 미차감)
       자해 계열 → blocked{code:"self_harm"} + 109 안내 / 그 외 flagged → blocked{code:"unsafe"}
    ③ LLM 분류기 (가린 이번 질문 + 직전 1턴 발췌) → jailbreak | injection | off_topic → blocked{code}
    차단 시: security_events 기록 → (Q2 추천안) 대화 미저장·한도 1회 차감 → event: done{blocked:true} → 끝
 6) FAQ 캐시: (세션 첫 질문 && location 없음)이면 가린 질문 임베딩 → 유사도 ≥ 임계값 →
    캐시 답변(이미 검증 통과본)을 delta로 흘림 → event: verified → 10)으로
 7) 메시지 조립 (고정부 앞, NFR-40, ADR-16):
      [system] 고정 답변 프롬프트(규칙·출처 형식·자료 속 지시 무시·한국어·카나리 문자열) + 툴 정의(순서 고정)
      [system] <이전 대화 요약> … </이전 대화 요약>   (있을 때, "자료"로 표시)
      최근 10턴 원문 (user=가린 텍스트 / assistant=최종 답변)
      [user] 이번 질문(가린 텍스트) (+ 위치 동의 시 "현재 위치: 위도·경도" — 저장 안 함, NFR-33)
 8) LangGraph 실행: graph.astream(state, stream_mode=["messages","updates","custom"])   (ADR-17~19)
      event: status {stage:"answering"}
      [answer] ChatOpenAI(gpt-6-luna, tools=5) ──tool_calls──▶ [tools] ─┬ MCP ▶ tour-tools ─ rag_query ▶ lightrag ▶ postgres(lightrag)
            ▲                                                          │                  │            └ CrossEncoder + wiki_pages 메타
            └─────────────── ToolMessage(<자료 …> 구분자) ◀────────────┤                  ├ data_query ▶ postgres(nadri.tour_items, 읽기 전용 롤)
                                                                       │                  ├ tour_live ▶ TourAPI
                                                                       │                  └ get_datetime
                                                                       └ TavilySearch ▶ Tavily
         툴 호출 시: event: tool {name, label}   (예: "관광 정보 찾는 중")  ※ UI는 tool 이벤트를 받으면 그때까지 받은 delta를 지운다
         최종 답변 토큰(시도 0만): event: delta {text}     → 끝나면 event: draft_done {}
      [verify] event: status {stage:"verifying"} — 아래 셋을 병렬 실행, 하나라도 실패면 불합격
         a. 코드 검사: 인용 contentid ⊆ 이번 요청 툴 결과 contentid, 링크 URL ⊆ 툴 결과 URL, 카나리 문자열 없음
         b. 출력 Moderation (실패·타임아웃 → 요청 실패로 처리, 아래 실패 처리)
         c. 검증 에이전트(ChatOpenAI, 툴 없음, 구조화 출력): 초안 vs 툴 결과 원문(메모리, 잘리지 않음) —
            사실 일치(운영시간·요금·주소…), 툴 결과에 없는 관광 사실 지어냄, 보안 항목(프롬프트 유출·개인정보·범위 이탈·허용 안 된 링크)
         합격 → 시도 0이면 event: verified {} / 시도 ≥1이면 event: replaced {text, attempt} + event: verified {}
         불합격 && attempt < VERIFY_MAX_REWRITES(기본 2) → event: status {stage:"revising", attempt}
                → [revise] 문제 목록을 피드백 메시지로 추가 → [answer] (툴 재호출 허용, 토큰은 흘리지 않고 모음) → [verify]
         불합격 && 횟수 소진 →
                · 보안 실패(b 또는 c의 보안 항목, a의 카나리) → event: replaced {text: 고정 안전 문구} + security_events
                · 사실 실패만 → (마지막 본이 화면과 다르면 replaced) + event: warning {code:"unverified", message}
 9) event: done {assistant_message_id, user_message_id, sources[], allowed_urls[], verify_status, rewrite_count, cached, quota_remaining}
    ": ping" 주석 15초마다 (A11)
10) 성공 시 한 트랜잭션: user 메시지(가린 텍스트, pii_types)·assistant 메시지(최종본 — 허용 안 된 링크는 텍스트로 강등,
    tool_results(길이 제한)·verification·rewrite_count·verify_status·timings) 저장, turn_count+1, daily_quota.used+1,
    usage_events(호출별: classify·answer·verify·embed·web_search, 토큰·캐시 토큰·응답 모델명) 기록
11) 응답 후 백그라운드(그래프 밖 단발 ChatOpenAI): 첫 턴이면 제목(FR-16) / turn_count > 10이면 누적 요약(FR-14)
    / verify_status=passed && FAQ 조건 충족이면 캐시 저장(ADR-13)
```

**SSE 이벤트 정의** (브라우저용, ADR-04)

| 이벤트 | 데이터 | 언제 |
|---|---|---|
| `meta` | `session_id`, `user_text_masked`, `masked_types[]` | 시작 직후. UI는 사용자 말풍선을 가린 텍스트로 바꿔 표시(NFR-35) |
| `status` | `stage`: `checking`/`answering`/`verifying`/`revising`, `attempt?` | 단계 전환 |
| `tool` | `name`, `label` | 툴 호출 직전. 받으면 UI는 표시 중인 delta를 지움 |
| `delta` | `text` | 시도 0 최종 답변 토큰 |
| `draft_done` | — | 초안 끝(링크는 아직 비활성) |
| `verified` | — | 검증 통과 → "✓ 확인됨" |
| `replaced` | `text`, `attempt` | 수정본 또는 고정 안전 문구로 화면 교체 |
| `warning` | `code:"unverified"`, `message` | 다시 쓰기 소진, 사실 검증 실패 |
| `blocked` | `code`: `unsafe`/`self_harm`/`jailbreak`/`injection`/`off_topic`, `message` | 입력 검사 차단(고정 안내 문구) |
| `done` | 위 9) | 정상 종료(차단 포함). 이 뒤에만 링크 활성 |
| `error` | `code`: `llm_unavailable`/`guard_unavailable`/`timeout`, `message` | 장애 — 재시도 버튼(FR-18) |

- **실패 처리**: OpenAI(답변·검증·분류)·Moderation·MCP 연결 실패, 비정상 종료, 전체 타임아웃(기본 180초 — 검증 루프 반영, 설정값)이면 `error`, **턴을 저장하지 않고 차감하지 않는다**(ADR-03). 초안이 이미 보였어도 검증을 못 했으면 저장하지 않는다(보안 우선). 개별 툴 오류(TourAPI·Tavily)는 툴 결과로 LLM에 돌려 답변을 계속한다.
- **브라우저 연결 끊김**: 그래프 실행 태스크를 취소하고 저장·차감하지 않는다.
- **출처**: 툴 결과에서 얻는다(ADR-05). 답변 본문의 `(#contentid)` 인용과 URL을 코드가 툴 결과 집합과 대조한다. `sources` = 답변이 인용한 툴 결과 항목(contentid·제목·기준일·출처, 웹이면 URL·제목).
- **지연 기록**(NFR-60): `timings` = `guard_ms`(입력 검사), `ttft_ms`(요청 수신 → 첫 delta), `draft_ms`, `tool_ms`, `verify_ms`(검증 합계), `total_ms`.

### 3.2 STT / TTS (FR-30~32)
```
STT: MediaRecorder(webm/opus 또는 mp4/aac, 60초 자동 종료) → POST /api/stt (multipart, 10m, MIME·크기 재검사, 분당 제한)
     → SttProvider(openai SDK: gpt-transcribe, language=ko) → {text} → 입력창 → 사용자가 수정 후 전송(전송 시 §3.1 입력 검사)
     → usage_events(kind=stt). 음성 자체는 Moderation하지 않음(오디오 미지원 [V]) — 전사 텍스트가 전송 시 검사됨
TTS: POST /api/tts {message_id} → 그 사용자의 assistant 메시지(저장된 최종본)만 → 마크다운·링크 제거, 1,500자 상한(가정)
     → TtsProvider(elevenlabs) → audio/mpeg 중계 → usage_events(kind=tts)
```

### 3.3 매일 01:00 KST 현행화·인덱싱 (FR-40~48, NFR-31) — 기존과 같음, 9) 정리 대상만 추가
```
APScheduler(Asia/Seoul) 01:00 daily_sync — advisory lock(키 1) 실패 시 건너뜀
 1) areaBasedSyncList2(서울·제주, 마지막 성공 이후) → 변경/삭제 contentid  [A12]
 2) 변경분 detail_synced_at=NULL → "상세 미수집" 큐
 3) 예산 안에서 detailCommon2·detailIntro2·detailInfo2 → raw → upsert → 엔티티 재렌더 → 해시 바뀐 페이지만 LightRAG delete→insert → wiki_pages
 4) 삭제분: deleted_at, 위키 파일·LightRAG 문서·wiki_pages 삭제
 5) 영향 허브(시군구)만 ChatOpenAI로 재작성 → LightRAG delete→insert
 6) FAQ 무효화: faq_cache.contentids ∩ 변경·삭제 contentid ≠ ∅ 인 행 삭제
 7) lint → ingest_runs.lint   8) 위키 git 커밋
 9) 정리(90일, NFR-31): updated_at 90일 지난 chat_sessions 삭제(메시지·피드백·FAQ 캐시·eval_scores 연쇄),
    90일 지난 security_events·eval_reports(→ 미결정 개선안 연쇄) 삭제, 채택·보류된 개선안은 evidence만 비움,
    만료 auth_sessions·인증코드·오래된 rate_limits 삭제
10) ingest_runs 기록
초기 적재: docker compose run --rm ingest ingest bootstrap (이어하기)
```

### 3.4 가입 신청 → 관리자 승인 (FR-04, FR-80·81·84) — 변경 없음
```
POST /api/auth/signup → 정책 검사 → users(status=pending) / pending 로그인 → "승인 대기" 표시, 채팅 403
/admin → approve|reject|disable (disable 시 auth_sessions 전부 삭제) / rejected·disabled 로그인 → 일반 실패 문구
첫 관리자: docker compose run --rm api nadri create-admin --username … --email …
```

### 3.5 이메일 인증코드 비밀번호 재설정 (FR-05, NFR-03) — 변경 없음
```
request {email} → rate limit → 항상 같은 응답 → 활성 사용자면 6자리 코드(해시 저장, 10분, 5회) 백그라운드 발송
confirm {email, code, new_password} → 검증 → Argon2id 갱신 → 전 세션 폐기 → 코드 소모, 실패 문구 통일
```

### 3.6 일일 50회 한도 (FR-62)
```
성공 답변(캐시 적중 포함) 1회 = daily_quota.used +1. 입력 검사 차단 = +1 (Q2 추천안). 장애·중단·Moderation 장애 차단 = 미차감
한도 = 50 / 초과 → 429 quota_exceeded → 그날 채팅 차단·"내일 다시" 안내 (추가 요청·관리자 승인 없음 — 2026-11-22 FR-62 변경)
관리자(role=admin)는 한도 검사 없음. 차감(used +1)은 똑같이 기록(사용량 통계용)
```

### 3.7 매일 03:00 KST 품질 평가 → 개선안 → HITL (FR-100~105, FR-70, NFR-16·36) — 신규
```
APScheduler 03:00 daily_quality — advisory lock(키 2), 같은 report_date 완료본 있으면 건너뜀
 1) eval_reports(report_date=전날 KST, status=running) 생성
 2) 수집: 전날 assistant 메시지 + 짝 user 메시지(이미 가린 텍스트) + tool_results + verification + timings
          + usage_events 비용 + message_feedback + security_events
 3) 익명화(nadri.eval.anonymize): user_id → 보고서 안 별칭("사용자 A") — 대응표 저장 안 함, session_id 제거,
    user 텍스트에 PII 가리기 한 번 더(멱등). 외부 추적 서비스로 보내지 않음(NFR-36)
 4) 대화가 있으면 평가 에이전트(ChatOpenAI, 툴 없음, 구조화 출력) — 턴 단위 채점
      👎 받은 턴을 먼저, 상한 EVAL_MAX_ITEMS(기본 200)까지
      항목(기준·척도는 spec): 정확성(툴 결과 대비)·해결 여부·툴 선택 적절성·검증 결과 타당성·데이터 부족 주제
      → eval_scores. 대화 0건이면 채점·개선안 건너뜀(FR-100)
 5) 공격 질문 세트 실행(nadri.eval.attack, eval/attack_set/*.jsonl, 매일 — NFR-16)
      실제 guard + 그래프를 같은 코드로 실행. 웹 툴은 세트에 적힌 "오염된 결과"를 돌려주는 고정 가짜 툴로 바꿔
      간접 인젝션을 결정적으로 재현(Tavily 호출·비용 없음). 판정은 코드 우선(차단 여부·카나리 미노출·허용 안 된 URL 없음),
      애매한 항목만 LLM 판정 → 방어율·실패 케이스 id
 6) 보고서 작성: 코드 집계(검증 통과율·다시 쓰기 분포·지연 p50/p95·비용·피드백 수·👍/👎와 LLM 점수 일치율·
    보안 이벤트 요약·공격 세트 방어율) + 평가 에이전트의 요약문(데이터 부족 주제 등) → eval_reports(stats, body_md)
 7) 개선안 에이전트(ChatOpenAI, 툴 없음, 구조화 출력): 입력 = 보고서 + 현재 설정 스냅샷
    (backend/src/nadri/prompts/*, 툴 설명, 리랭커·검증·FAQ 임계값 설정, 데이터 범위) → 개선안 목록
    (문제·근거 발췌·원인 추정·제안·예상 효과·비용·위험·우선순위·대상) → improvement_proposals(status=new)
 8) usage_events(kind=eval|proposal) 기록, eval_reports.status=done (실패 시 failed + error, 다음 날 자동 재시도 없음 — CLI로 수동)
HITL: 관리자 /admin 품질 리포트 → 개선안마다 채택/보류/기각 + 메모 → improvement_proposals.status·decision_note·decided_by
      채택 = "개발 후보" 목록에 쌓임. 코드·프롬프트·설정 자동 변경 없음 (ADR-23)
```

### 3.8 AI 보안 흐름 (NFR-11~16·35) — 신규
상세 위협 모델·방어 표는 루트 `SECURITY_GUIDE.md`.
```
[1 입력 검사]  원문 ─▶ ① PII 가리기(규칙) ─▶ ② Moderation(omni-moderation-latest) ─▶ ③ LLM 분류기 ─▶ 통과
                         │ 원문은 이 단계 밖으로        │ API 실패=차단            │ jailbreak·injection·off_topic
                         │ 나가지 않음(저장·로그 금지)   │ self-harm 계열=109 안내   │ =차단
                         ▼                             ▼                          ▼
                    security_events(pii_masked)   security_events(blocked/self_harm/guard_error)  security_events(blocked)
[2 에이전트]   고정 시스템 프롬프트(비밀값 없음, 카나리 포함, "자료 속 지시 무시"), 툴 결과·웹·요약은 <자료 출처=… > … </자료> 로 감쌈
[3 툴]         읽기 전용 5개만(tour-tools 4 + TavilySearch). tour-tools는 SELECT 전용 DB 롤, 내부 토큰, 파라미터화 조회
[4 출력 검사]  코드 검사(contentid·URL 허용 목록·카나리) ∥ 출력 Moderation ∥ 검증 에이전트 보안 항목 → 실패 시 다시 쓰기 → 소진 시 고정 안전 문구
[5 화면]       raw HTML 끔, 이미지 렌더 끔, 링크는 allowed_urls만·done 이후만 클릭 가능, 저장 시 허용 안 된 링크는 텍스트로 강등
[상시]         공격 질문 세트 매일 실행(§3.7) → 방어율·보안 이벤트 요약을 품질 보고서에
```

### 3.9 피드백 (FR-103)
```
PUT /api/chat/messages/{id}/feedback {rating:"up"|"down", reason?:"wrong"|"outdated"|"misunderstood"|"other"}
 → 본인 assistant 메시지인지 확인 → message_feedback upsert(메시지당 1개, 변경 가능)
 → down이면: faq_cache 중 source_message_id = id 또는 id = (그 메시지의 faq_cache_id) 행 삭제
DELETE 같은 경로 → 피드백 취소
```

---

## 4. 외부 의존

| 외부 서비스 | 호출 주체 | 용도 | 비밀값 | 실패 시 |
|---|---|---|---|---|
| OpenAI API — LLM(Responses) | api(분류·답변·검증·제목·요약), ingest(허브·평가·개선안·공격 세트), lightrag(인덱싱·키워드 추출) | `gpt-6-luna` | `OPENAI_API_KEY` | 채팅: `error` + 재시도(FR-18), 미저장·미차감 |
| OpenAI API — Embeddings | api(FAQ), lightrag | `text-embedding-3-small` | 〃 | FAQ 조회 실패 → 캐시 건너뛰고 정상 진행 |
| OpenAI API — Moderation | api(입력·출력), ingest(공격 세트) | `omni-moderation-latest`, 무료 [V] | 〃 | **차단**(`guard_unavailable`, 미차감) — NFR-12 |
| OpenAI API — Audio | api | `gpt-transcribe` | 〃 | STT 오류 표시 |
| TourAPI 4.0 KorService2 | ingest, tour-tools(`tour_live`) | 원천 데이터 | `TOURAPI_SERVICE_KEY` | ingest: 다음 실행 / tour_live: 툴 오류를 LLM에 |
| Tavily | **api**(`TavilySearch`) | 웹 검색 | `TAVILY_API_KEY` | 툴 오류 → 공공데이터만으로 답 |
| ElevenLabs | api | TTS | `ELEVENLABS_API_KEY`, `ELEVENLABS_VOICE_ID` | 재생 오류 표시 |
| Gmail SMTP | api | 인증코드 | `SMTP_USER`, `SMTP_APP_PASSWORD` | 로그, 응답 동일 |
| Cloudflare | cloudflared | HTTPS | `CLOUDFLARE_TUNNEL_TOKEN` | 외부 접속 불가 |
| Hugging Face (빌드 1회) | tour-tools 빌드 | 리랭커 가중치 | 없음 | 빌드 실패 |

- **보내지 않는 곳**: LangSmith·Langfuse 등 관측 서비스(NFR-36). compose에 `LANGSMITH_TRACING=false`, `LANGCHAIN_TRACING_V2=false`를 명시하고 `LANGSMITH_*` 키는 주입하지 않는다.
- OpenAI Responses 호출은 `store=False`(OpenAI 측 응답 저장 끔) + `include=["reasoning.encrypted_content"]`(툴 루프에서 추론 항목 전달) [V 코드 확인, 실호출 미확인 A18].
- v1.1 이후 확장 원천(FR-49): `ingest/sources/*` 또는 tour-tools 실시간 툴. 구성도에 점선만.

---

## 5. DB 스키마 개요

### 5.1 `nadri` DB (Alembic 관리)
모든 시각은 `timestamptz`, "하루"는 KST 날짜. 테이블·컬럼 한글 명칭은 ERD와 같게 DDL `COMMENT`로 넣는다(SQLAlchemy `comment=`). 한글 명칭의 **정본은 ERD**(`docs/images/erd.svg`, 생성 스크립트 `docs/images/src/erd.py`)이고, 아래 표의 명칭이 ERD와 다르면 ERD를 따른다. 18개 테이블(기존 14 + 신규 5 − `quota_requests` 삭제 2026-11-22).

**기존 테이블 (변경 없는 것)**

| 테이블 (한글 명칭) | 핵심 컬럼 (한글 명칭) | 비고 |
|---|---|---|
| `users` (사용자) | id(사용자 ID), username(아이디), email(이메일), password_hash(비밀번호 해시), role(역할), status(상태), created_at(가입 신청 시각), approved_at(승인 시각), approved_by(승인 관리자) | NFR-34 |
| `auth_sessions` (로그인 세션) | id_hash(세션 ID 해시), user_id(사용자 ID), created_at(생성 시각), last_seen_at(마지막 활동 시각), expires_at(만료 시각) | NFR-04 |
| `rate_limits` (요청 제한 카운터) | key(제한 키), window_start(윈도 시작), count(횟수), locked_until(잠금 해제 시각) | |
| `password_reset_codes` (비밀번호 재설정 코드) | id(코드 ID), user_id(사용자 ID), code_hash(코드 해시), expires_at(만료 시각), attempts(시도 횟수), consumed_at(사용 시각) | |
| `chat_sessions` (대화 세션) | id(세션 ID), user_id(사용자 ID), title(제목), summary(누적 요약), turn_count(턴 수), created_at(생성 시각), updated_at(갱신 시각) | 90일 기준 = updated_at |
| `daily_quota` (일일 사용 한도) | user_id(사용자 ID), day(날짜), used(사용 횟수) | `extra` 컬럼 삭제(2026-11-22) |
| `tour_items` (관광 항목) | contentid(콘텐츠 ID) … (기존과 같음) | FR-41 |
| `wiki_pages` (위키 페이지) | path(경로) … (기존과 같음) | |
| `ingest_runs` (수집 실행 기록) | id … (기존과 같음) | |
| `ingest_state` (수집 상태) | key(키), value(값) | |

**변경 테이블**

| 테이블 (한글 명칭) | 컬럼 (한글 명칭) | 변경 내용 |
|---|---|---|
| `chat_messages` (대화 메시지) | id(메시지 ID), session_id(세션 ID, fk cascade), turn_no(턴 번호), role(역할: user/assistant), content(내용 — user는 **가린 텍스트**), pii_types text[](가린 개인정보 종류, user만), **tool_results** jsonb(툴 결과: 이름·인자·소요 ms·내용(툴당 2,000자, 합계 10,000자 상한 — 가정)·contentids·urls), sources jsonb(출처), from_cache(캐시 응답 여부), **faq_cache_id**(FAQ 캐시 ID, fk set null), **verify_status**(검증 상태: `passed`/`failed`/`security_replaced`/`cached`), **rewrite_count** smallint(다시 쓰기 횟수), **verification** jsonb(검증 기록: 시도별 판정·문제 목록·Moderation 결과·소요 ms·이전 초안(2,000자 상한)), **timings** jsonb(지연 기록), created_at(생성 시각) | `tool_trace` → `tool_results`로 대체(상위 집합). 위치 좌표·원문 저장 안 함(NFR-33·35). 90일 연쇄 삭제(FR-104) |
| `usage_events` (사용량 기록) | id, user_id(null=시스템), message_id(fk set null), kind(종류), model(응답 모델명), input_tokens(입력 토큰), cached_tokens(캐시 읽기 토큰), **cache_write_tokens**(캐시 쓰기 토큰), output_tokens(출력 토큰), units(초·글자·크레딧·건), cost_usd(비용), ttft_ms(첫 토큰 지연), total_ms(전체 시간), tool_ms(툴 시간), created_at | kind 값: `answer`(기존 `chat`)·`verify`·`classify`·`moderation`(무료, 건수만)·`title`·`summary`·`embed`·`stt`·`tts`·`web_search`·`hub`·`eval`·`proposal`. 캐시 쓰기 단가 1.25배(F3) 반영 |
| `faq_cache` (FAQ 응답 캐시) | id, source_message_id(원 메시지, fk cascade), question(질문 — 가린 텍스트), embedding vector(1536), answer(답변), sources(출처), contentids text[](근거 contentid), created_at, hit_count(적중 수) | 저장 조건에 "검증 통과·👎 없음" 추가(ADR-13) |

**신규 테이블**

| 테이블 (한글 명칭) | 컬럼 (한글 명칭) | 비고 |
|---|---|---|
| `message_feedback` (답변 피드백) | message_id(메시지 ID, pk·fk cascade), user_id(사용자 ID), rating(평가: `up`/`down`), reason(👎 사유: `wrong`/`outdated`/`misunderstood`/`other`/null), created_at(생성 시각), updated_at(수정 시각) | 메시지당 1개. 대화와 함께 90일 삭제(FR-103) |
| `security_events` (보안 이벤트) | id(이벤트 ID), user_id(사용자 ID, fk set null), session_id(세션 ID, fk set null), message_id(메시지 ID, fk set null), stage(단계: `input`/`output`), check_name(검사: `pii`/`moderation`/`classifier`/`code_check`/`verifier`), outcome(결과: `masked`/`blocked`/`self_harm_guide`/`rewritten`/`safe_replaced`/`guard_error`), categories text[](분류 — PII 종류·Moderation 범주·분류기 라벨), excerpt(발췌 — 가린 텍스트 300자 이하), detail jsonb(세부 — 점수 등, 원문 없음), created_at(발생 시각) | NFR-12·13. 90일 삭제. 원문은 절대 넣지 않음 |
| `eval_reports` (품질 보고서) | id(보고서 ID), report_date(대상 날짜, unique), status(상태: `running`/`done`/`skipped`/`failed`), stats jsonb(집계 — 검증·지연·비용·피드백·보안·공격 세트 방어율), body_md(보고서 본문), model(응답 모델명), started_at(시작 시각), finished_at(종료 시각), error(오류) | FR-100·105. 90일 삭제 |
| `eval_scores` (턴별 채점) | id(채점 ID), report_id(보고서 ID, fk cascade), message_id(메시지 ID, fk cascade), scores jsonb(항목별 점수), issues text(지적 사항), created_at | FR-100. 메시지·보고서 삭제 시 함께 삭제 |
| `improvement_proposals` (개선안) | id(개선안 ID), report_id(보고서 ID, fk cascade — 미결정분만, 아래 비고), seq(순번), target(대상: `system_prompt`/`tool_description`/`reranker`/`verifier`/`guard`/`faq_cache`/`data_scope`/`other` — faq_cache는 24-Q1 2026-11-28 추가), title(제목), problem(문제), evidence jsonb(근거 발췌 — 익명·가린 텍스트), cause(원인 추정), proposal(제안), expected_effect(예상 효과), cost_note(비용), risk(위험), priority(우선순위: `high`/`medium`/`low`), status(결정: `new`/`adopted`/`held`/`rejected`), decision_note(결정 메모), decided_by(결정 관리자), decided_at(결정 시각), created_at | FR-101·102. report_id는 fk **set null**로 두고, 90일 정리 때 `new`·`rejected`는 삭제, `adopted`·`held`는 evidence만 비우고 남김(개발 후보 보존) |

DB 롤(3개, 변경 없음): `nadri_app`(api·ingest) · `nadri_tools`(tour-tools, `tour_items`·`wiki_pages` SELECT만 + TourAPI 실시간 호출 수 세기 함수 2개 실행 권한 — 2026-11-21 10-Q1) · `lightrag`. 초기화 `infra/postgres/init/*.sql`.

### 5.2 `lightrag` DB
변경 없음. LightRAG가 생성·관리, HTTP API로만 접근. 벡터 차원 1536 고정, 임베딩 변경 시 전체 재인덱싱 [S F12], [R NFR-32].

---

## 6. API 개요

### 6.1 브라우저용 (`/api/*`, 같은 출처)
상태 변경 요청은 `X-CSRF-Token` 필요(NFR-05). 관리자 API는 role=admin 서버 검사.

| 메서드 · 경로 | 설명 | 요구사항 |
|---|---|---|
| POST `/api/auth/signup` · `/login` · `/logout` · `/password` · `/password-reset/request` · `/password-reset/confirm`, GET `/api/auth/me` | (변경 없음) | FR-01~05, NFR-02~05 |
| GET `/api/chat/sessions` · POST `/api/chat/sessions` · GET/DELETE `/api/chat/sessions/{id}` | (변경 없음, 메시지는 가린 텍스트로 반환 + verify_status·내 피드백 포함) | FR-10·16·17·20 |
| POST `/api/chat/sessions/{id}/messages` | 질문 → **SSE** (§3.1 이벤트) | FR-10~19·55·90·91, NFR-12~15 |
| **PUT · DELETE `/api/chat/messages/{id}/feedback`** | 👍/👎 + 사유(선택) / 취소 | FR-103 |
| POST `/api/stt` · `/api/tts` | (변경 없음) | FR-30~32 |
| GET `/api/admin/users?status=` · POST `/api/admin/users/{id}/approve`·`/reject`·`/disable` | (변경 없음) | FR-81·84 |
| GET `/api/admin/usage?from=&to=` | 사용량·비용(kind별 분리 표시), $10 경고 | FR-63·83, NFR-43 |
| **GET `/api/admin/quality/reports?from=&to=`** | 보고서 목록(날짜·상태·핵심 지표) | FR-102 |
| **GET `/api/admin/quality/reports/{id}`** | 보고서 본문·집계·공격 세트 결과·개선안 목록 | FR-102·105 |
| **GET `/api/admin/quality/proposals?status=`** | 개선안 목록(예: `adopted` = 개발 후보) | FR-102 |
| **POST `/api/admin/quality/proposals/{id}/decision`** | `{status: adopted|held|rejected, note}` | FR-102 |
| GET `/api/health` | 헬스체크 | — |

### 6.2 내부 전용 (Compose 네트워크, nginx 미경유)

| 호출 | 대상 | 인증 |
|---|---|---|
| api·ingest → `http://tour-tools:8000/mcp` (Streamable HTTP, `langchain-mcp-adapters`) | MCP 툴 4종 | `Authorization: Bearer TOOLS_API_KEY` (어댑터의 `headers` 지원 [V], 서버는 ASGI 미들웨어로 검사) |
| tour-tools → `POST http://lightrag:9621/query/data` | 후보 검색 | `LIGHTRAG_API_KEY` |
| ingest → LightRAG 문서 insert·delete·상태 API | 인덱싱 | `LIGHTRAG_API_KEY` (경로 **미확인** A16) |
| ~~api → hermes~~ | 삭제 | ~~`API_SERVER_KEY`~~ 삭제 |

---

## 7. 디렉터리 구조

```
myAgent/
├── compose.yaml                 # 8개 서비스, named volume
├── compose.dev.yaml             # 개발 덮어쓰기: 소스 마운트·핫리로드·nginx 127.0.0.1 포트
├── .env.example                 # 키 이름만
├── SECURITY_GUIDE.md            # AI 보안 가이드 (NFR-17)
├── web/
│   ├── app/                     #   (chat)/, (auth)/, admin/(users, usage, quality/), manifest.ts
│   ├── components/  lib/        #   SSE 파서(이벤트 §3.1), 안전 마크다운 렌더러(링크 허용 목록), 녹음기, api 클라이언트
│   ├── public/  e2e/            #   아이콘·sw.js / Playwright (NFR-71)
│   └── Dockerfile
├── backend/                     # Python 3.12 단일 프로젝트 (uv), 이미지 타깃 2개
│   ├── pyproject.toml           #   그룹 `reranker`(torch·sentence-transformers)는 tools 타깃만
│   ├── alembic/
│   ├── src/nadri/
│   │   ├── core/                #   설정, DB 엔진, ORM 모델, TourAPI 클라이언트, llm.py(ChatOpenAI·임베딩 생성 함수), 단가표
│   │   ├── prompts/             #   answer.md, verify.md, classify.md, title.md, summary.md, hub.md, evaluate.md, propose.md (+ 고정 안내 문구)
│   │   ├── guard/               #   pii.py(규칙·검증번호·Luhn), moderation.py(openai SDK), classifier.py, input_guard.py, output_guard.py(코드 검사·링크 강등), events.py
│   │   ├── agent/               #   state.py, graph.py(StateGraph), nodes.py(answer·verify·revise), tools.py(MCP 로딩 + TavilySearch), evidence.py(툴 결과 → contentid·URL·sources)
│   │   ├── api/                 #   FastAPI: auth, chat(router·sse·context), feedback, admin(…, quality), quota, usage, faq_cache, voice(stt/, tts/), mail
│   │   ├── tools/               #   MCP 서버(FastMCP): rag_query, data_query, tour_live, get_datetime, reranker, auth 미들웨어
│   │   ├── ingest/              #   scheduler, bootstrap, sync, raw, wiki(templates/, hubs, lint), indexer, budget, sources/
│   │   ├── eval/                #   quality.py(평가 에이전트·보고서), proposals.py(개선안 에이전트), attack.py(공격 세트), golden.py(FR-70), anonymize.py
│   │   └── cli.py               #   create-admin, ingest bootstrap/sync, eval quality/golden
│   ├── tests/                   #   pytest (LLM·MCP·Moderation·Tavily 목킹, PII 규칙 표 테스트)
│   └── Dockerfile               #   target app(api·ingest) / target tools(tour-tools)
├── infra/
│   ├── nginx/nginx.conf
│   ├── lightrag/lightrag.env
│   └── postgres/init/01-init.sh
├── eval/                        # 평가 데이터 (ingest에 읽기 전용 바인드 마운트)
│   ├── golden/                  #   골든 Q&A (질문·정답·근거 contentid)
│   ├── attack_set/              #   attacks.jsonl — 탈옥·직접/간접 인젝션·프롬프트 유출·링크 유출·PII·유해·자해·범위 이탈, 한국어 포함
│   └── README.md                #   형식·판정 규칙
└── docs/ (analysis/, harness/, images/)
```
named volume: `pg-data`, `wiki-data`(ingest만 rw), `raw-data`(ingest만). ~~`hermes-home`~~ 삭제. 바인드: `./eval:/app/eval:ro`(ingest만).

---

## 8. 주요 설계 결정 (ADR)

| ID | 결정 | 근거 | 버린 대안 |
|---|---|---|---|
| ADR-01 | **컨테이너 8개**, 네트워크 1개, 호스트 포트 없음(개발 덮어쓰기에서만 nginx 127.0.0.1) | NFR-61·08. Hermes 제거 | 네트워크 분리 |
| ADR-02 | `backend/` 단일 프로젝트, 이미지 타깃 2개(app / tools) — G3 Q1 유지 | 모델·클라이언트·설정·프롬프트·guard 공유 | 3개 프로젝트 |
| ADR-03 | 대화 정본은 `nadri` DB, LangGraph는 요청마다 stateless(**체크포인터 없음**), 컨텍스트 조립은 api. **실패·검증 불가 턴은 저장·차감 안 함** | NFR-30, D-10, FR-18. 재시도 단순 | LangGraph 체크포인터에 대화 저장(정본 이중화) |
| ADR-04 | 그래프 스트림을 그대로 넘기지 않고 api가 자체 SSE 이벤트(§3.1 표)로 변환 | 툴 인자·내부 메시지 비노출, 프론트 파서 단순, 캐시 적중도 같은 형식 | LangGraph 스트림 패스스루 |
| ADR-05 | **출처·contentid는 툴 결과에서 얻는다**(G3 Q3 "출처 블록 파싱" 대체). 답변 속 `(#contentid)`·URL은 툴 결과 집합과 코드로 대조 | api가 툴 결과를 직접 봄. 파싱 실패로 퇴화하던 경로가 사라짐 | 출처 블록 파싱 |
| ADR-06 | `rag_query` = LightRAG `/query/data`(mix, ~30) → CrossEncoder → 상위 5 + `wiki_pages` 메타 | S5 | LightRAG 내장 리랭크 |
| ADR-07 | 같은 인스턴스에 DB 2개 + 롤 3개 — G3 Q2 유지 | D-07 | 스키마 분리 |
| ADR-08 | 에이전트 툴은 **읽기 전용 5개**(tour-tools 4 + `TavilySearch`). `web_extract`·쓰기·실행·파일 툴 없음. LightRAG 쓰기·위키 쓰기는 ingest만 | NFR-07, C4 | Tavily extract 추가 |
| ADR-09 | 스케줄은 ingest APScheduler + advisory lock(키 분리): **01:00 현행화**, **03:00 품질 평가**. 초기 적재·평가 재실행은 CLI | S15, FR-100. 03:00은 01:00 정리 후 | 별도 평가 컨테이너, 호스트 cron |
| ADR-10 | 잠금·분당 제한·한도는 PostgreSQL, 실제 IP는 nginx가 `CF-Connecting-IP`→`X-Real-IP` | S13 | Redis |
| ADR-11 | **그래프 밖 단발 호출**(제목·요약·입력 분류·평가·개선안·허브)은 LangChain `ChatOpenAI` 직접. **OpenAI SDK 직접은 STT와 Moderation**만 — Moderation은 생성 호출이 아니고 `langchain-openai`의 `OpenAIModerationMiddleware`는 `create_agent` 전용 훅이라 순서 고정 검사·109 안내·이벤트 기록에 맞지 않음 [V] | 사용자 결정 3·8 | Moderation 미들웨어 사용 |
| ADR-12 | Next.js는 화면만, 데이터는 브라우저→`/api` | D-03, NFR-10 | RSC에서 api 호출 |
| ADR-13 | FAQ 캐시 저장 조건: 세션 첫 질문 && 위치 없음 && **verify_status=passed** && 툴 결과에 `web_search`·`get_datetime`·`tour_live` 없음 && 근거 contentid ≥1. 👎 받으면 즉시 삭제. 질문은 가린 텍스트로 임베딩. 임계값 보수적(코사인 0.95 시작) | S14, FR-60·92·103, NFR-31 | 완전 일치 캐시 |
| ADR-14 | TourAPI 일일 호출 예산(기본 800/일) | F7 | 실패 코드로 중단 |
| ADR-15 | CSRF = 서명된 double-submit | NFR-05 | synchronizer 토큰 |
| ADR-16 | 고정 프리픽스: 답변 프롬프트 + 툴 정의(바인딩 순서 고정) → 요약(`<이전 대화 요약>` 자료 블록) → 최근 턴 → 질문. 날짜·위치는 마지막 user 메시지/툴로만. `prompt_cache_key`는 역할별 고정값(`nadri-answer-v1`, `nadri-verify-v1`, `nadri-classify-v1`)을 `.bind()`로 전달 | NFR-40. 요약을 자료로 감싸 인젝션이 요약을 통해 지시로 승격되는 것을 막음 | 시스템 프롬프트에 날짜 삽입 |
| ADR-17 | **LangGraph `StateGraph`를 직접 구성**: 노드 `answer`·`tools`(`langgraph-prebuilt` `ToolNode`)·`verify`·`revise`, 조건 간선으로 루프. `recursion_limit` 설정(툴 폭주 방지) | 검증 루프·초안 스트리밍 제어가 필요해 간선을 직접 다루는 편이 단순 | `langchain.agents.create_agent` + 미들웨어(루프가 숨겨져 검증 분기 제어가 어려움), 감독자형 멀티 에이전트(범위 밖) |
| ADR-18 | **검증 = 코드 검사 ∥ 출력 Moderation ∥ 검증 에이전트**(툴 없음, 구조화 출력, 툴 결과 원문을 메모리에서 대조). 다시 쓰기 최대 `VERIFY_MAX_REWRITES=2`(설정값, FR-70 끔/1회/2회 비교로 조정). 보안 실패 소진 시 고정 안전 문구, 사실 실패 소진 시 경고 | FR-90·91, NFR-13. 결정적으로 판정 가능한 것(contentid·URL·카나리)은 LLM에 맡기지 않음 | LLM 단독 검증 |
| ADR-19 | **초안 선스트리밍**: 시도 0 답변만 delta로 흘리고 다시 쓰기는 모아서 `replaced`로 교체. 초안 단계에선 링크 비활성 | 사용자 결정 6. 잔여 위험은 §15 Q1 | 최종본만 표시 |
| ADR-20 | **입력 검사 순차·실패 시 차단**: PII → Moderation → LLM 분류기, 각 단계 통과 후 다음 단계, 통과 후에만 생성. Moderation 오류·타임아웃(5초, 설정값) = 차단(fail-closed) | NFR-12, D-24 | 병렬 검사(빠르지만 PII 전 원문이 외부로 나감), fail-open |
| ADR-21 | **PII 가리기는 사용자 입력에만, 규칙 기반**(정규식 + 검증번호·Luhn + 문맥 단어). 답변(출력)에는 정규식 가리기를 하지 않는다 — 관광지 대표 전화(`tel`)가 공공데이터 정답이기 때문. 출력의 개인정보는 검증 에이전트 보안 항목이 본다 | NFR-35. 결정적·빠름·오프라인 | 로컬 NER(v1.1 후보), 출력 정규식 가리기 |
| ADR-22 | **링크 허용 목록 = 그 요청 툴 결과의 URL**. 3중: 검증 코드 검사(불합격→다시 쓰기) · 저장 시 강등 · 프론트 렌더러(`allowed_urls`, done 이후만) | NFR-14. 데이터 유출 경로 차단 | 도메인 허용 목록 |
| ADR-23 | **평가·개선안은 ingest 배치, 툴 없는 LLM 호출**. 결과는 DB에만, 사람(관리자)이 채택/보류/기각. 자동 적용 경로를 코드에 두지 않음 | FR-100~102, 범위 밖 "자동 적용" | 개선안 자동 PR·프롬프트 자동 교체 |
| ADR-24 | tour-tools는 별도 MCP 컨테이너 유지, api·ingest는 `langchain-mcp-adapters`(Streamable HTTP, 툴 호출마다 세션)로 연결, 내부 토큰 헤더. **`mcp` 1.30.x 고정**(어댑터 0.3.2가 `mcp<2` 요구, 서버·클라이언트가 같은 uv 프로젝트) | 사용자 결정 4, [V] | api 프로세스 안 툴(torch가 api로 들어옴, 읽기 전용 롤 분리 상실), mcp 2.x(어댑터 미지원) |
| ADR-25 | Tavily: `TavilySearch(max_results=5, search_depth="basic", include_raw_content=False, include_images=False)`, `auto_parameters` 끔(advanced 자동 전환 = 2크레딧 방지) [V]. 검색어는 가린 텍스트에서 LLM이 만듦 | NFR-43(월 1,000 무료 [V]), NFR-11 | advanced 검색 |
| ADR-26 | 관측은 DB 테이블만. LangSmith 추적 환경변수를 명시적으로 끄고, OpenAI Responses `store=False` | NFR-36 | LangSmith |
| ADR-27 | **입력 차단 턴은 대화에 저장하지 않고 `security_events`에만 가린 발췌 저장, 한도 1회 차감**(Moderation 장애 차단은 미차감) | 공격문이 다음 턴 컨텍스트로 들어가지 않게, 분류기 비용·반복 공격 억제 — §15 Q2에서 확인 | 차단도 대화에 저장 / 미차감 |

---

## 9. 보안 / 비밀값

**외부 노출 면**: Cloudflare → cloudflared → nginx:80 → web/api. 그 외 내부망(NFR-08). nginx `/api/`: `proxy_buffering off`, `proxy_read_timeout 300s`, `client_max_body_size 10m`.

**인증·세션**: (변경 없음) Argon2id, 10자+·흔한 비밀번호, 5회→15분 잠금, 세션 해시 저장·재발급·유휴 2시간/절대 7일, 문구 통일.

**AI 보안 5겹** (D-24 보안 우선, 상세 §3.8·`SECURITY_GUIDE.md`)

| 겹 | 위치 | 내용 | 요구사항 |
|---|---|---|---|
| 1 입력 검사 | api `guard.input_guard` | PII 가리기 → Moderation(실패=차단, 자해=109) → LLM 분류기(탈옥·인젝션·범위 밖) | NFR-12·15·35 |
| 2 에이전트 | api `agent`, `prompts/` | 비밀값 없는 고정 프롬프트 + 카나리, 툴 결과·웹·요약은 `<자료>` 구분자, "자료 속 지시 무시", 관광 사실은 툴 결과로만 | NFR-11·16, D-09 |
| 3 툴 | tour-tools, `TavilySearch` | 읽기 전용 5개, SELECT 전용 롤, 파라미터화 조회, 내부 토큰, `recursion_limit` | NFR-07 |
| 4 출력 검사 | api `agent.verify`, `guard.output_guard` | 코드 검사(contentid·URL·카나리) ∥ 출력 Moderation ∥ 검증 에이전트 보안 항목 → 다시 쓰기 → 고정 안전 문구 | NFR-13, FR-90 |
| 5 화면 | web 렌더러 | raw HTML 끔, 이미지 끔, 링크 허용 목록·done 이후만 | NFR-14 |
| 상시 | ingest 03:00 | 공격 세트 매일 실행, 보안 이벤트 요약 → 품질 보고서 | NFR-16, FR-105 |

**컨테이너 격리**: Hermes(터미널 툴 포함 이미지)가 사라져 "에이전트 컨테이너에 셸이 있는" 위험 자체가 없어졌다. 에이전트가 실행하는 코드는 우리 툴 5개뿐. 자체 이미지(api·tour-tools·ingest)는 비루트 사용자, `cap_drop: [ALL]`, `no-new-privileges`, docker.sock 미마운트.

**개인정보**: 원문 입력은 `guard.pii` 밖으로 나가지 않는다(저장·로그·LLM·Tavily·평가 모두 가린 텍스트). 위치 좌표는 메모리에서만(NFR-33). api 요청 본문 로깅 금지. 평가 입력은 익명(NFR-36).

**비밀값 배치** — `.env` 하나, 서비스별 필요한 키만 주입(NFR-09). 시스템 프롬프트에 비밀값 없음(NFR-16).

| 키 | 받는 서비스 | 변경 |
|---|---|---|
| `OPENAI_API_KEY` | api, lightrag, ingest | hermes 삭제 |
| `TOURAPI_SERVICE_KEY` | ingest, tour-tools | — |
| `TAVILY_API_KEY` | **api** | hermes → api |
| `ELEVENLABS_API_KEY`, `ELEVENLABS_VOICE_ID` | api | — |
| `SMTP_USER`, `SMTP_APP_PASSWORD`, `MAIL_FROM` | api | — |
| `LIGHTRAG_API_KEY` | lightrag, tour-tools, ingest | — |
| `TOOLS_API_KEY` | tour-tools, api, ingest | **신규**(MCP 내부 토큰) |
| `POSTGRES_PASSWORD`, `APP_DB_PASSWORD`, `TOOLS_DB_PASSWORD`, `LIGHTRAG_DB_PASSWORD` | postgres / api·ingest / tour-tools / lightrag | — |
| `SESSION_SECRET` | api | — |
| `CLOUDFLARE_TUNNEL_TOKEN` | cloudflared | — |
| ~~`API_SERVER_KEY`~~ | — | **삭제** |
| (비밀 아님) `LANGSMITH_TRACING=false`, `LANGCHAIN_TRACING_V2=false` | api, ingest | 신규 |

선택: 서비스별 OpenAI 키 분리(A14 보완).

---

## 10. 비용·지표 기록 범위

**질문 1건당 LLM 호출 수** (FAQ 캐시 미적중, `gpt-6-luna` 단가 입력 $0.10·캐시 $0.01·출력 $0.50 /1M [S F3], 토큰 수는 추정)

| 호출 | 횟수 | 1회 추정(입력/캐시/출력 토큰) | 1회 비용 |
|---|---|---|---|
| Moderation(입력·출력) | 2 (+다시 쓰기마다 1) | — | $0 (무료 [V]) |
| 입력 분류기 | 1 | 1.0k / 0.7k / 50 | ≈ $0.00006 |
| 답변(툴 호출 단계) | 평균 1 | 3.5k / 3.0k / 100 | ≈ $0.00013 |
| 답변(최종 작성) | 1 | 7k / 3.5k / 500 | ≈ $0.00064 |
| 검증 | 1~3 | 6k / 1.5k / 300 | ≈ $0.0006 |
| 다시 쓰기(답변) | 0~2 | 9k / 7k / 500 | ≈ $0.0005 |
| LightRAG 키워드 추출(`mix`, rag_query 시) | 0~1 | — | ≈ $0.0002 (앱 집계 불가, A14) |

- 합격 1회(가장 흔함): **≈ $0.0016**. 다시 쓰기 1회: ≈ $0.0027, 2회: ≈ $0.0038. 다시 쓰기 비율 20% 가정 평균 **≈ $0.0019** — G2 추정($0.001)의 약 2배. 제목·요약은 기존과 같음.
- 월 영향: 1명×하루 20문항 → 월 600건 ≈ **$1.2**(+제목·요약·STT). 상한 5명×50회 매일(최악) → 월 7,500건 ≈ $14 → FR-63 $10 경고 발생 가능(차단 없음).
- 매일 평가 배치: 채점 20턴 × ≈$0.0006 + 보고서·개선안 ≈ $0.004 + 공격 세트(약 60건, 대부분 입력 단계 차단 ≈ $0.0001/건, 통과분은 전체 파이프라인) ≈ $0.03 → **하루 ≈ $0.05, 월 ≈ $1.5**. 대화가 없는 날은 공격 세트만(≈ $0.03).
- **합계 예상**: 1인 실사용 월 약 $3~4 (G2 추정 $1.5에서 증가 — 검증·분류·평가 배치). 최초 인덱싱 $15~30은 같음.
- 기록되는 것: 그래프·단발 호출 토큰(`usage_metadata`, 캐시 읽기 `input_token_details.cache_read`, 캐시 쓰기 `cache_creation` [V 코드 확인]), Moderation 건수, Tavily 호출 수(1회=1크레딧, basic), ElevenLabs 글자 수, 허브·평가·개선안 토큰.
- 기록되지 않는 것: LightRAG 내부 OpenAI 호출 → 대시보드 월 비용은 "앱 기록 기준 추정"(A14).

---

## 11. 문서 간 상충

### 11.1 G3 최초 승인 때 정리 완료 (X1~X9)
2026-11-07 처리 완료(TECH_STACK §2·§3.1·§11·§12, requirements D-16, README, stack-options 머리말, 구성도). X4(에이전트 범위)는 이번 재작성으로 의미가 바뀌어 X13으로 대체.

### 11.2 이번 재작성에서 생긴 상충

| ID | 내용 | 출처 A | 출처 B | 처리 |
|---|---|---|---|---|
| X10 | Hermes 서술 잔존 | [TS] §1·§2·§4.3·§6·§9·§12, [README] 스택·구성, [S] S9·S12·F8~F10·P1, `erd.md`(usage_events kind), `architecture.svg` | [R D-04·D-08] 개정본, 이 문서 | B 기준. TS·README·stack-options 머리말(대체 표시)·ERD·구성도 갱신 필요(§14) |
| X11 | 초안 선스트리밍 vs 보안 우선 | [R FR-91] 초안 먼저 표시 | [R D-24, NFR-13] 보안 우선·출력 검사 | 초안은 출력 검사 전에 보인다. ADR-19·22의 완화책으로 설계, **§15 Q1** |
| X12 | 주민번호 "검증번호 확인" | [R NFR-35] | 2020-10 주민등록번호 부여체계 개편 이후 발급분은 검증번호 규칙이 적용되지 않을 수 있음(**미확인**, A29) | **§15 Q3** |
| X13 | "STT만 OpenAI SDK 직접" | [R D-04], 사용자 결정 3 | Moderation API 호출 수단 필요(NFR-12) | Moderation은 생성 호출이 아니므로 SDK 직접으로 해석(ADR-11). 요약 보고에 명시 |
| X14 | 대화 없는 날 | [R FR-100] "대화가 없으면 건너뜀" | [R NFR-16] 공격 세트 "매일" | 채점·개선안만 건너뛰고 공격 세트는 매일 실행(§3.7) |
| X15 | 보안 문서 이름 | [PG] 2026-11-20 메모 `docs/ai-security.md` | [R NFR-17] 루트 `SECURITY_GUIDE.md` | B |
| X16 | 단가 추정 | [TS §10] 질의 1건 약 $0.001 | 이 문서 §10 ≈ $0.0019 | TS §10 갱신 필요 |
| X17 | 웹 툴 | [R FR-11] `web_search`(Tavily) | 기존 문서의 `web_extract` | B — extract 없음(ADR-08) |

---

## 12. 미검증 가정과 실패 시 대안

G2 결정대로 별도 PoC 없이 **첫 구현 작업(최소 end-to-end: postgres + lightrag + tour-tools + api 채팅 1경로 [입력 검사 → 그래프 → 검증 → SSE], 위키 수십 페이지)** 에서 A7·A9·A16·A18~A26·A30을 실행 확인한다. 나머지는 표시한 작업에서. 실패해 사용자 결정을 바꿔야 하면 **멈추고 사용자에게 묻는다**.

### 12.1 이번에 직접 확인한 사실 [V] (조회일 2026-11-21)

| 항목 | 확인 내용 | 근거 |
|---|---|---|
| 최신 버전 | langgraph 1.2.24(11-20), langgraph-prebuilt 1.1.3, langchain 1.5.2, langchain-core 1.8.4, langchain-openai 1.8.5(11-19), langchain-mcp-adapters 0.3.2(08-06), langchain-tavily 0.2.18(04-16), mcp 2.3.0 / 1.x 최신 1.30.0(09-07), openai 3.57.0, lightrag-hku 1.5.7 | `https://pypi.org/pypi/<pkg>/json` |
| 의존 제약 | langchain-mcp-adapters 0.3.2 → `mcp<2.0.0,>=1.24.0`, `langchain-core<2,>=1.3.3` / langchain-openai 1.8.5 → `openai>=2.45.0`, `langchain-core>=1.8.4` / langchain-tavily → `langchain>=1,<2` | 각 wheel `METADATA` |
| gpt-6 + 툴 | `ChatOpenAI._use_responses_api()`가 모델명이 `gpt-6`으로 시작하고 tools가 있으면 **자동으로 Responses API** 사용 → F3의 Chat Completions `reasoning_effort=none` 제약을 피함. `reasoning_effort`·`reasoning`·`use_responses_api`·`store`·`include`(`reasoning.encrypted_content`) 필드 존재 | langchain-openai 1.8.5 `chat_models/base.py` |
| 스트리밍 사용량 | 기본 base URL이면 `stream_usage=True` 기본 켜짐. Responses 사용량 → `usage_metadata.input_token_details.cache_read`(cached_tokens), `cache_creation`(cache_write_tokens) | 같은 파일 |
| prompt_cache_key | 호출 kwargs로 전달(`invoke(..., prompt_cache_key=…)`, 즉 `.bind()` 가능), `prompt_cache_retention`도 지원 | 같은 파일 docstring |
| MCP 어댑터 | `StreamableHttpConnection{transport:"streamable_http", url, headers…}` 지원 | `langchain_mcp_adapters/sessions.py` |
| mcp 1.30 서버 | `FastMCP.streamable_http_app()`, `stateless_http` 옵션 존재 | mcp 1.30.0 wheel |
| LangGraph 스트림 | `stream_mode` = `values/updates/checkpoints/tasks/debug/messages/custom`, 커스텀 이벤트는 `get_stream_writer()` | langgraph 1.2.24 `types.py`, `config.py` |
| Moderation | `omni-moderation-latest` 무료, 텍스트·이미지(오디오 불가). 범주: sexual, sexual/minors, harassment(/threatening), hate(/threatening), illicit(/violent), self-harm, self-harm/intent, self-harm/instructions, violence(/graphic) | platform.openai.com/docs/guides/moderation |
| Moderation 미들웨어 | `langchain_openai.middleware.OpenAIModerationMiddleware`는 `create_agent`용 before/after_model 훅 | langchain-openai 1.8.5 |
| Tavily | 무료 월 1,000크레딧(카드 불필요), basic 검색 1크레딧·advanced 2크레딧, `auto_parameters`가 advanced로 바꿀 수 있음 → `search_depth="basic"` 명시 권장 | docs.tavily.com/documentation/api-credits, langchain-tavily 0.2.18 소스 |

### 12.2 가정 표

| ID | 가정 | 검증 방법 (통과 기준) | 실패 시 대안 | 확인 시점 |
|---|---|---|---|---|
| ~~A1·A2~~ | Hermes toolset·memory | — | **해당 없음**(Hermes 제거) | — |
| ~~A3~~ | Hermes `gpt-6-luna` 툴 호출 | — | A18로 대체 | — |
| ~~A4·A5·A6~~ | Hermes usage·진행 이벤트·내부 저장 | — | **해당 없음**(A19·A20으로 대체) | — |
| A7 | LightRAG `/query/data`가 청크·문서 식별자 반환, 후보 ~30 조절 | 응답 확인 | 엔티티 페이지 헤더에 contentid / 라이브러리 직접 사용 | 첫 작업 |
| A8 | 한국어 엔티티 추출 품질 | 샘플 검토 | 프롬프트 조정 / `naive` / 인덱싱만 상위 모델(**사용자 확인**) | 첫 작업 |
| A9 | CPU CrossEncoder 30쌍 지연 허용 | 측정 기록 | max_length 축소·후보 20·ONNX·off·GPU(**사용자 확인**) | 첫 작업 |
| A10 | `mix` ≥ `hybrid` | 평가셋 | `hybrid` | 평가 작업 |
| A11 | Named Tunnel SSE 무버퍼링, 15초 ping | 모바일 토큰 단위 표시 | ping 축소 | 인프라 작업 |
| A12 | TourAPI 한도 단위·SyncList 파라미터 | 실제 호출 | 예산 조정·운영계정(**사용자 확인**) | 첫 적재 |
| A13 | `gpt-transcribe` webm/mp4, iOS PWA 마이크 | 두 포맷 전사 | ffmpeg 변환 | 음성 작업 |
| A14 | LightRAG 내부 사용량 집계 불가 | 기능 확인 | "추정" 표기 + 서비스별 키 | 사용량 작업 |
| ~~A15~~ | 출처 블록 형식 준수 | — | **해당 없음**(ADR-05 툴 결과 기반) | — |
| A16 | LightRAG 문서 delete→insert, 상태 조회 | 갱신 후 중복 없음 | 해시 문서 ID·file_path 삭제 | 첫 작업 |
| A17 | localhost에서 `__Host-` 쿠키 | Chrome 로그인 | 터널 주소로만 | 인증 작업 |
| **A18** | `ChatOpenAI(gpt-6-luna, use_responses_api=True, store=False, include=[encrypted reasoning])`로 툴 루프·구조화 출력이 동작 [V 코드] | rag_query·data_query 실제 호출 + 결과 기반 답변, 검증 노드 구조화 출력 파싱 | ① `store=True`(OpenAI 30일 보관 — NFR-36 영향 **사용자 확인**) ② Chat Completions + `reasoning_effort="none"`(F3) ③ 모델 변경(D-05, **사용자 확인**) | 첫 작업 |
| **A19** | 스트리밍에서 `usage_metadata`·`cache_read` 수신, 역할별 `prompt_cache_key`로 2번째 요청부터 cache_read > 0 [V 코드] | 실호출 2회 비교 | usage 없으면 `updates` 모드의 완성 메시지에서 수집 / OpenAI 대시보드 대조, NFR-40은 "측정 가능한 범위" | 첫 작업 |
| **A20** | `astream(stream_mode=["messages","updates","custom"])`에서 `metadata["langgraph_node"]`로 답변 노드 토큰만 골라 delta로, 툴 호출은 `updates`로, 검증 판정은 `custom`으로 받을 수 있음. Responses 청크 텍스트는 `chunk.text`로 추출 | 시나리오별 이벤트 순서 스냅샷 테스트 | 답변 노드 안에서 `get_stream_writer()`로 직접 delta 발행 | 첫 작업 |
| **A21** | 어댑터 0.3.2 ↔ mcp 1.30 FastMCP(stateless HTTP) 연동, `headers`로 토큰 전달 [V 코드] | 툴 4종 호출, 토큰 없으면 401 | 서버를 앞단 ASGI 미들웨어로 감싸기 / 내부망 신뢰로 퇴화(토큰 생략) | 첫 작업 |
| **A22** | Moderation이 한국어 유해 입력을 쓸 만큼 잡고, 정상 관광 질문("전쟁기념관", "총각김치 맛집" 등)을 덜 막음 | 공격 세트 탐지율 + 골든 세트 오탐률 기록 | 범주별 `category_scores` 임계값 조정(spec), 분류기 보완 | 첫 작업·평가 |
| **A23** | Moderation 가용성·지연·한도가 1~5명에 충분(무료, 한도 수치 **미확인**) | 실패율·p95 지연 기록 | 짧은 재시도 1회 후 차단(정책 유지) | 첫 작업 |
| **A24** | LLM 분류기 오탐(스몰토크·상식·후속 질문을 off_topic으로)이 낮음 | 골든 세트·일상 질문 세트로 오탐률 측정 | 직전 1턴 맥락 확대, off_topic은 차단 대신 안내형 답변으로 완화(**사용자 확인**) | 평가 작업 |
| **A25** | 검증 루프 지연(최악 다시 쓰기 2회 ≈ 3~4배)과 검증 오판(정답을 불합격)이 허용 범위 | FR-70 끔/1회/2회 비교: 정확도·지연·비용 | `VERIFY_MAX_REWRITES` 1 또는 0(설정값, 사용자 결정 범위 안) | 평가 작업 |
| **A26** | 검증 에이전트가 툴 결과 원문(최대 수천~1만 토큰)을 한 번에 보고 판정 가능 | 긴 결과 케이스 판정 정확도 | 인용 항목만 골라 검증 입력 축소 | 첫 작업 |
| **A27** | PII 규칙 오탐이 관광 질문에서 드묾(날짜·contentid·요금 숫자) | 규칙 표 단위 테스트 + 골든 질문 무변화 | 문맥 단어 필수화, 패턴 축소 | guard 작업 |
| **A28** | Tavily 월 1,000크레딧 안 (basic 1크레딧 [V]) | 사용량 대시보드 | 웹 툴 설명에 "공공데이터에 없을 때만" 강화 | 사용량 작업 |
| **A29** | 2020-10 이후 발급 주민번호의 검증번호 규칙 적용 여부 | 행정안전부 공식 자료 확인 | §15 Q3 | guard 작업 |
| **A30** | 툴 호출 전 머리말 텍스트가 delta로 새어도 `tool` 이벤트로 지워져 화면 일관 | 이벤트 스냅샷 | 프롬프트로 머리말 금지 + 답변 노드 메시지 단위 버퍼링 | 첫 작업 |

---

## 13. 범위 밖 / 넣지 않은 것 (과설계 방지)
- 승인 결과 메일, 관리자 실시간 알림, lint 리포트 화면, 사용자 재활성화 버튼, **보안 이벤트 전용 화면**(품질 보고서 요약으로 대신), 개선안 자동 적용·자동 PR.
- LangGraph 체크포인터·장기 메모리, 감독자형 멀티 에이전트, 로컬 NER 이름 탐지(v1.1 후보), LangSmith 등 외부 관측, 출력 정규식 PII 가리기.
- 수평 확장, 고가용성, 백업 자동화, Redis, 별도 리랭커·스케줄러·평가 컨테이너.
- 서비스워커 오프라인 캐시, 답변 이미지, 다국어, Tavily extract.
- FR-49 확장 원천, `stt-gpu`(v1.1 이후). 지연 최적화(D-24, v1.1 이후).

---

## 14. 구성도 갱신 사양 (`docs/images/architecture.svg`)

> 2026-11-07 판 기준으로 아래만 바꾼다. 갱신 후 `architecture.png` 재내보내기, README 구성 설명 갱신.

**삭제**: Hermes Agent 박스, 화살표 6(FastAPI→Hermes)·7(Hermes→OpenAI)·8(Hermes→Tavily)·9(Hermes→tour-tools), "에이전트" 그룹의 Hermes 부제(툴 화이트리스트, memory off), 볼륨 `hermes-home`.

**박스 변경·추가**

| 그룹 | 박스 (제목 / 부제) |
|---|---|
| 애플리케이션 | FastAPI 박스를 키워 내부에 하위 칩 3열: **입력 검사**(PII 가리기 → Moderation → 분류기) / **LangGraph**(답변 에이전트 ⇄ 툴 → 검증 에이전트, 다시 쓰기 ≤2) / **출력 검사**(링크·contentid·카나리). 부제: BFF · 인증 · 한도 · 대화 · 피드백 · STT/TTS |
| 애플리케이션 | Next.js 부제: 채팅 UI · PWA · `/admin`(가입·사용량·**품질 리포트**) |
| 에이전트 → "툴" 그룹으로 이름 변경 | tour-tools / MCP 서버 + 리랭커, 칩 rag_query · data_query · tour_live · get_datetime (변경 없음) |
| 데이터 | ingest 부제: APScheduler **01:00** 수집·위키·인덱싱 · **03:00 평가 에이전트 → 개선안 에이전트 · 공격 세트** |
| 외부 서비스 | OpenAI API 부제: gpt-6-luna · 임베딩 · gpt-transcribe · **Moderation** |
| 데이터 볼륨 | `eval/` (골든·공격 세트, 읽기 전용) 작은 박스 추가 |

**화살표** (번호는 새로 매김. 실선=내부, 점선=외부, 굵은 선=사용자 요청)

| # | 출발 → 도착 | 라벨 |
|---|---|---|
| 1~5 | (기존과 같음) 사용자→Cloudflare→cloudflared→Nginx→Next.js / FastAPI | HTTPS · 터널 · :80 · `/`,`/admin` · `/api/*`(SSE) |
| 6 | FastAPI(LangGraph) → tour-tools | MCP (HTTP, 토큰) |
| 7 | FastAPI → OpenAI | 분류 · 답변 · 검증 · 제목 · 요약 · 임베딩 · STT (점선) |
| 8 | FastAPI(입력·출력 검사) → OpenAI | Moderation (점선) |
| 9 | FastAPI(LangGraph) → Tavily | 웹 검색 (점선) |
| 10~14 | (기존 10~14) tour-tools→LightRAG·PostgreSQL·TourAPI, LightRAG→PostgreSQL·OpenAI | 그대로 |
| 15 | FastAPI → PostgreSQL | 사용자 · 대화 · 한도 · 사용량 · 피드백 · 보안 이벤트 |
| 16·17 | FastAPI → ElevenLabs / Gmail SMTP | TTS / 인증코드 (점선) |
| 18~22 | (기존 19~23) ingest → TourAPI·raw·PostgreSQL·LLM Wiki·LightRAG | 그대로 |
| 23 | ingest → OpenAI | 허브 · 평가 · 개선안 · 공격 세트 (점선) |
| 24 | ingest → PostgreSQL | 품질 보고서 · 개선안 (21과 합쳐도 됨) |
| 25 | eval/ → ingest | 공격 세트 (읽기 전용) |
| 26 | 추후 연동 4개 → ingest | 회색 점선 |

**범례**: 기존 + "보안 검사(입력·출력)" 칩 색 1개. 하단 주석: "호스트 인바운드 포트 없음 — 외부 접속은 Cloudflare Tunnel만 · 에이전트는 api 안 LangGraph(stateless)".
**ERD**(`docs/images/erd.svg`, `erd.md`): §5.1대로 `chat_messages` 컬럼 변경, `usage_events.cache_write_tokens`·kind 값, `faq_cache` 연결, 신규 5개 테이블(묶음 "품질·보안": message_feedback, security_events, eval_reports, eval_scores, improvement_proposals) 추가. 테이블 수 14 → 19.

---

## 15. G3 확인 질문

**G3 최초 답변 (2026-11-07)** — 유지: Q1 `backend/` 단일 프로젝트 + 이미지 2종, `ingest` 이름 유지 · Q2 같은 인스턴스 별도 DB `lightrag` · Q4 허브 시군구 27개 · Q5 성공·캐시 적중 차감, 장애 미차감 · ERD 한글 명칭 = DDL COMMENT. **대체**: Q3(출처 블록 파싱) → ADR-05 툴 결과 기반, Q6(Hermes 유지) → D-04 LangGraph.

**G3 재검토 답변 (2026-11-21, 사용자)**: Q1 추천안(초안 선스트리밍 + 완화책) · Q2 추천안(대화 미저장, 보안 이벤트에 가린 발췌, 한도 1회 차감, Moderation 장애는 미차감) · Q3 추천안(생년월일·성별 자리 패턴, 검증번호 미사용) · **Q4 가린 모양 = 형식 유지 + `*`**(전화 `010-****-****`, 주민 `******-*******`, 이메일 `****@gmail.com`, 이름 `***` — 종류는 `pii_types`에 기록). 이에 따라 NFR-35 "검증번호 확인"은 X12대로 정리.

**G3 재검토 질문 (2026-11-21)**

| # | 질문 | 추천안 | 대안 |
|---|---|---|---|
| Q1 | 초안 선스트리밍은 출력 검사 **전에** 초안을 보여 준다(D-24 보안 우선과 긴장). 잔여 위험을 받아들일까? | **받아들임 + 완화책**: 입력 검사 통과 후에만 생성, 초안 동안 링크 비활성·이미지/HTML 없음, 출력 검사 실패 시 즉시 고정 안전 문구로 교체, 시스템 프롬프트엔 비밀값 없음 → 남는 위험은 "수 초간 부적절 초안 노출"뿐 | B: 출력 Moderation + 코드 검사(빠른 보안 검사)를 통과한 뒤 초안을 한 번에 표시, 사실 검증은 그 뒤(토큰 스트리밍 사라짐) / C: 검증 끝난 최종본만 표시 |
| Q2 | 입력 검사에 걸린 질문의 처리 | **대화에 저장 안 함**(다음 턴 컨텍스트 오염 방지), `security_events`에 가린 발췌만, **한도 1회 차감**(분류기 비용·반복 공격 억제). Moderation 장애로 인한 차단은 미차감. 자해 109 안내도 같은 규칙 | B: 차단도 미차감 / C: "차단됨" 표시로 대화에 저장(새로고침해도 보임, 컨텍스트에서는 제외) |
| Q3 | 주민·외국인등록번호 판정 — 2020-10 개편 후 발급분은 검증번호 규칙이 없을 수 있음(미확인) | **생년월일 유효 + 성별 자리(1~8) 패턴이면 가림, 검증번호는 쓰지 않음**(관광 질문에 13자리 숫자는 드물어 오탐 위험 낮음) | B: NFR-35 그대로 검증번호 일치 시만(오탐 적지만 신규 번호 누락 가능) / C: 패턴이면 가리고 검증번호 일치 여부는 이벤트 detail에만 기록 |

