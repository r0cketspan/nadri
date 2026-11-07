# 기술스택 후보 — nadri (Phase 2a, **G2 승인 2026-11-07**)

> **G2 결과**: 각 S 항목은 `PROGRESS.md` 결정 로그대로 확정. 아래 "PoC" 항목은 **별도 PoC 없이 첫 구현 작업(최소 end-to-end)에서 검증**하는 것으로 바뀌었다 — 검증 목록은 `architecture.md` §12(A1~A17).

> 입력: `docs/harness/requirements.md`(G1 승인본), `TECH_STACK.md`(초안), `docs/analysis/00·01`, `docs/harness/PROGRESS.md` 결정 로그.
> 외부 사실은 **2026-11-07 공식 문서·레지스트리를 직접 조회해 확인**했고, 항목마다 [확인] 또는 **미확인**으로 표시했다.
> 작성: solution-architect 에이전트 (Phase 2a). G2에서 사용자가 각 S 항목을 선택한다.

## 결정 항목 요약 (G2에서 답할 것)

| # | 결정 항목 | 추천안 (한 줄) |
|---|---|---|
| S1 | 보조 모델 (`gpt-5-nano` 대체) | **`gpt-6-luna` 하나로 통일**. `gpt-5-nano`는 2026-12-11에 종료된다 |
| S2 | STT 모델 | **`gpt-transcribe`**. `gpt-4o-mini-transcribe`는 2027-02-26에 종료된다 |
| S3 | 임베딩 모델 | **OpenAI `text-embedding-3-small`**. bge-m3는 평가셋 비교용으로만 둔다 |
| S4 | LightRAG 인덱싱 LLM·질의 모드 | **`gpt-6-luna` + 처음엔 `mix`**, PoC에서 `hybrid`와 비교해 확정 |
| S5 | 리랭커 서빙 | **B: tour-tools 안 CrossEncoder** + LightRAG `/query/data` 사용, LightRAG 자체 리랭크는 끈다 |
| S6 | 개발 중 HTTPS 접속 경로 | **도메인을 지금 사서 Named Tunnel 사용**. 임시 주소(Quick Tunnel)는 SSE를 지원하지 않는다 |
| S7 | 인증코드 메일 발송 | **Gmail SMTP + 앱 비밀번호** |
| S8 | TourAPI 초기 적재 | **개발계정(1,000건/일)으로 나눠 적재** + PoC에서 건수를 세 보고 운영계정 신청 여부 결정 |
| S9 | Hermes 배포·버전·보안 설정 | **공식 이미지 + 버전 태그 고정**, config.yaml 마운트, toolset 화이트리스트와 memory 끄기 |
| S10 | MCP 서버 구현 | **공식 `mcp` Python SDK(FastMCP) + Streamable HTTP** |
| S11 | 백엔드 기본 스택 | **Python 3.12 + uv + FastAPI + SQLAlchemy 2.x(async) + asyncpg + Alembic + argon2-cffi** |
| S12 | FastAPI가 Hermes 스트림을 받는 방법 | **httpx로 SSE를 직접 파싱** |
| S13 | rate limit·잠금·일일 한도 저장소 | **PostgreSQL만 사용(Redis 없음)** + 실제 IP는 `CF-Connecting-IP`에서 |
| S14 | FAQ 응답 캐시 | **pgvector 유사도 캐시**, 대상을 좁힘(세션 첫 질문, 위치·상대날짜 없는 질문) |
| S15 | 스케줄러 (C5) | **`ingest` 컨테이너 안 APScheduler** (01:00 현행화 + 90일 삭제) |
| S16 | 프론트 UI·스트리밍 | **Next.js 16 + Tailwind 4 + shadcn/ui + react-markdown(raw HTML 끔) + 직접 만든 fetch 스트림 파서** |
| S17 | PWA 구현 | **Next.js 기본 `app/manifest.ts` + 최소 서비스워커**, 플러그인 없음 |
| S18 | 백오피스 구현 | **같은 Next.js 앱의 `/admin`** |
| S19 | 프론트·E2E 테스트 도구 | **Vitest + React Testing Library + Playwright** |
| S20 | ElevenLabs 모델·음성·한도 | **`eleven_flash_v2_5`**, 음성은 사용자가 듣고 고름, 한도는 기록 + 요청당 글자 수 상한 |
| S21 | 지표·사용량 저장 | **PostgreSQL 테이블 + 백오피스 대시보드**, 외부 관측 도구 없음 |

> 답변 형식 예: "S1 추천, S6 B, 나머지 추천대로".
> 이번 조사에서 새로 확인한 것 중 **요구사항(D-05, NFR-22, TS §8.1)을 바꿔야 하는 항목이 3개**: S1, S2, S6.

### G2 답변 기록 (G2 승인 2026-11-07)
| # | 사용자 답변 (2026-11-07) |
|---|---|
| S2 | **`gpt-transcribe` 채택** (G2 승인 시 requirements·TECH_STACK에 반영) |
| S3 | `text-embedding-3-small` 동의, bge-m3는 비교용 |
| S4 | 인덱싱 `gpt-6-luna` 동의. 비용 추정·mix/hybrid 설명 요청 |
| S5 | 동의 |
| S6 | 도메인 **`.dev`** 구입 방향 (Cloudflare Registrar, Named Tunnel) |
| S7 | Gmail SMTP 동의. 계정·앱 비밀번호는 메일 작업 구현 시 사용자가 `.env`에 직접 입력 |
| S8 | 동의 (실제 건수는 첫 적재 작업에서 조회) |
| S9~S19 | 추천안 동의 (S16 Tailwind 확정) |
| S20 | `eleven_flash_v2_5` + **기본 보이스 1개 고정**, 사용자 음성 선택 기능 없음 |
| S21 | 동의 |
| 사용량 | 실사용자는 사실상 1명 (5명은 상한 가정) |
| PoC | 별도 PoC 대신 "단계별 구현하며 실행·수정" 방식 제안 → 검토 중 |

---

## 0. 이번 조사에서 나온 중요한 사실 (요구사항에 영향)

| # | 사실 | 출처 (2026-11-07 조회) | 영향 |
|---|---|---|---|
| F1 | `gpt-5-nano`(`gpt-5-nano-2025-08-07`)는 **2026-12-11 종료**. 권장 대체 모델은 `gpt-5.6-luna` | OpenAI Deprecations 페이지 | D-05·NFR-41의 보조 모델을 바꿔야 함 → **S1** |
| F2 | `gpt-4o-mini-transcribe`(`-2025-12-15` 포함)는 **2027-02-26 종료**. 대체 모델은 `gpt-transcribe`($0.0045/분) 또는 `gpt-live-transcribe` | OpenAI Deprecations, `gpt-transcribe` 모델 페이지 | TS §1·§8.1 STT 모델 변경 → **S2** |
| F3 | `gpt-6-luna`: 입력 $0.10, 캐시 입력 $0.01, **캐시 쓰기 $0.125**(입력가의 1.25배), 출력 $0.50 /1M. 스냅샷은 별칭 `gpt-6-luna` 하나뿐(날짜 스냅샷 없음). **Chat Completions에서는 `reasoning_effort=none`일 때만 function calling 가능** | `gpt-6-luna` 모델 페이지 | 버전 고정 불가 → 응답의 모델명을 기록하는 것으로 대체. Hermes가 OpenAI를 어떤 API로 부르는지 PoC 확인 필수 → **S9** |
| F4 | `gpt-5.6-luna`: $0.20 / $0.02 / $1.20 — `gpt-6-luna`보다 비쌈 | 모델 페이지 | S1 근거 |
| F5 | `text-embedding-3-small` $0.02/1M, 종료 공지 없음 | 모델 페이지, Deprecations | S3 |
| F6 | **Cloudflare Quick Tunnel(임시 주소)은 SSE를 지원하지 않음**. 동시 요청 200개 제한, 가동 보장 없음 | Cloudflare Docs "Quick Tunnels › Limitations" | 개발 중 임시 주소로는 FR-10·NFR-23(스트리밍)을 검증할 수 없음 → **S6** |
| F7 | TourAPI 국문 관광정보 서비스: **개발계정 1,000건/일**, 운영계정은 "활용사례 등록 시 신청하면 증가". 일일 한도(22)·초당 한도(23) 초과 에러코드가 따로 있음 | data.go.kr 15101578 페이지 | 한도가 오퍼레이션별인지 서비스 전체인지는 **미확인** → **S8** |
| F8 | Hermes API Server: `/v1/chat/completions` 스트림에 표준 chunk 외에 **`event: hermes.tool.progress`** 커스텀 이벤트와 10초 keepalive 주석(`:`)이 섞임. 끄는 설정은 `gateway.platforms.api_server.tool_progress_events`. 클라이언트가 보낸 system 메시지는 **Hermes 기본 시스템 프롬프트 위에 덧붙음**. 기본 동시 실행 상한 `max_concurrent_runs: 10`. 기본 플랫폼 toolset `hermes-api-server`는 **터미널을 포함한 거의 모든 툴을 유지** | Hermes docs: API Server, Toolsets Reference | 화이트리스트를 반드시 직접 구성(NFR-07) → **S9·S12** |
| F9 | Hermes 웹 검색 백엔드는 `web.backend: tavily`로 지정(`TAVILY_API_KEY`). MCP 서버별 툴 필터는 `mcp_servers.<name>.tools.include` | Hermes docs: Web Search, MCP | requirements §6의 "Tavily 연결 설정 키"가 해소됨 |
| F10 | Hermes 이미지 `nousresearch/hermes-agent`는 릴리스가 잦음(v0.22.7 2026-11-03 → v0.23.0 2026-11-05) | Docker Hub 태그 | `latest`를 쓰면 안 되고 태그 고정 필요 → **S9** |
| F11 | LightRAG 최신 v1.5.7(2026-09-02). `PGTableGraphStorage`는 **AGE 없이 PostgreSQL 14+ 일반 테이블**에서 동작하고 `pgvector/pgvector:pg18` 이미지로 충분하다고 명시. 리랭크 바인딩은 `null/cohere/jina/aliyun`. 서버에 `/query/data`(답변 생성 없이 검색 결과를 구조화된 데이터로 반환) 엔드포인트가 있음. 질의 모드는 `local/global/hybrid/naive/mix/bypass` | LightRAG `env.example`, `query_routes.py`, Releases | S4·S5 근거 |
| F12 | LightRAG README: PostgreSQL 저장소는 **처음 테이블을 만들 때 벡터 차원이 고정**되고, 재임베딩 도구가 없음 → 임베딩을 바꾸면 벡터 테이블을 지우고 다시 인덱싱해야 함 | LightRAG README | NFR-32 재확인, S3 |

---

## 1. 이미 확정된 항목 (다시 묻지 않음)

| 영역 | 확정 내용 | 근거 |
|---|---|---|
| 데이터 원천 | TourAPI 4.0 `KorService2`, 서울+제주 × 콘텐츠 8종 | D-01, D-22 |
| 채널 | 챗봇 반응형 웹 + PWA, 관리자 백오피스 웹 | D-02, 결정로그 11-07 |
| 프론트 / BFF | Next.js(App Router, TS) / FastAPI, 브라우저는 FastAPI만 호출 | D-03 |
| 에이전트 | Hermes Agent만 사용, stateless `/v1/chat/completions` | D-04, C2, 결정로그 |
| 메인 LLM | OpenAI `gpt-6-luna`, fallback 없음 | D-05, NFR-42 (보조 모델은 S1에서 다시 정함) |
| Graph RAG | LightRAG가 LLM Wiki 페이지를 인덱싱, 리랭커 사용 | D-06 |
| LightRAG 실행 형태 | 내부망 전용 서버 컨테이너 + `LIGHTRAG_API_KEY` | NFR-08, TS §9 |
| DB | PostgreSQL + pgvector 단일 DB, 그래프는 `PGTableGraphStorage`, 이미지 `pgvector/pgvector:pg18` (F11) | D-07, TS §5.1 |
| 툴 연결 | 자체 MCP 서버 `tour-tools`(rag_query·data_query·tour_live·get_datetime) | D-08 |
| 웹 검색 | Hermes 내장 `web_search`/`web_extract`, 백엔드 Tavily (`web.backend: tavily` — F9) | D-08, 결정로그 |
| 인증 | 아이디+비밀번호(Argon2id), 서버 세션 쿠키, 가입 신청 후 관리자 승인 | D-11 |
| STT 방식 | 비실시간 Push-to-talk, OpenAI 전사 API, `SttProvider` | D-12 (모델은 S2) |
| TTS | ElevenLabs 단독, `TtsProvider`, Edge TTS 제외 | D-13, C12, 결정로그 |
| 실행 환경 | WSL2 Ubuntu-22.04 + Docker Compose, named volume | D-14, NFR-20·21 |
| 프록시·외부 접속 | Nginx 단일 진입점(SSE 버퍼링 off) + Cloudflare Tunnel | D-15, 결정로그 (개발 중 주소 방식은 S6) |
| 비용 정책 | 캐싱·모델 분리·FAQ 캐시·대시보드·1일 50회(+50 추가 승인)·월 $10 경고 | D-16, FR-62·63 |
| 평가 | 골든 Q&A + E2E, 단위테스트 pytest | D-18, NFR-70 |
| 현행화 | 매일 01:00 KST, `areaBasedSyncList2` 변경분만 반영 | FR-45 |
| 범위 밖 | 소셜 로그인, 네이티브 앱, 로컬 LLM, 클라우드 배포, 답변 이미지, 별도 DB(DuckDB·AGE·Neo4j·Qdrant) 등 | requirements §5 |

---

## 2. TECH_STACK.md 초안과 requirements의 차이 (G2/G3 후 TECH_STACK 갱신 대상)

| TECH_STACK 위치 | 초안 내용 | 바뀐 내용 (requirements 기준) |
|---|---|---|
| §1, §8.2 | TTS: Edge(개발) → ElevenLabs(데모) | ElevenLabs만 사용 (D-13, C12) |
| §4.1·§4.2 | `web_fetch`, 백엔드 DuckDuckGo/Brave/SearXNG 중 선택 | `web_extract` + Tavily (FR-54) |
| §3.1 | "MVP는 지역 1곳으로 축소" | 서울+제주 (D-22), 여러 날에 나눠 적재 (FR-48) |
| §9 | Nginx가 443 노출, 인증서 직접 준비 | Cloudflare Tunnel이 HTTPS 처리 → `cloudflared` 컨테이너 → `nginx:80` 내부 연결, 호스트 인바운드 포트 불필요, 인증서 직접 준비 불필요 (G3에서 명시) |
| §7 미정 | 가입 범위·비밀번호 재설정 | 관리자 승인 가입 + 이메일 인증코드 (FR-04·05) |
| §1, §10 | 보조 모델 `gpt-5-nano`, STT `gpt-4o-mini-transcribe` | 둘 다 종료 예정 (F1·F2) → S1·S2 |
| §10 단가 | "캐시 입력은 1/10 가격" | 맞지만 **캐시 쓰기는 1.25배**가 추가됨 (F3) |
| §1, §2, §9 | 백오피스·메일·Tavily·터널 없음 | FR-07·FR-80~84·D-15 반영 필요 |
| §4.4 | 최소 에이전트 루프 "선택" | MVP 이후 작업 (FR-71) |

---

## 3. 열린 결정 항목

### S1. 보조 모델 (제목·요약·키워드) — `gpt-5-nano` 대체 [F1]
`gpt-5-nano`는 2026-12-11 종료 예정이라 구현 중이나 데모 전에 사라진다.

| 안 | 내용 | 비용 ($/1M 입력/캐시/출력) | 운영 | 1인 적합 | 요구사항 |
|---|---|---|---|---|---|
| **A (추천)** | **`gpt-6-luna`로 통일**, 제목·요약은 `reasoning_effort`를 낮게 | 0.10 / 0.01 / 0.50 | 모델 1개만 관리 | 높음 | NFR-41의 "모델 분리" 의미가 약해짐 → 문구를 "같은 모델, 낮은 reasoning effort·짧은 출력"으로 수정 필요 |
| B | 공식 대체 모델 `gpt-5.6-luna` | 0.20 / 0.02 / 1.20 | 모델 2개 | 중간 | 모델 분리는 유지되지만 메인보다 **2배 비쌈** |
| C | 다른 소형 모델 | **미확인** (`gpt-5.4-nano`는 2027-04-01 종료 예정) | — | — | 또 종료될 위험 |

근거: 현재 가격표에서 `gpt-6-luna`가 가장 싼 범용 텍스트 모델로 보임(전체 목록 전수 확인은 **미확인**). → **D-05·NFR-41 수정 필요(사용자 승인)**.

### S2. STT 모델 [F2]
| 안 | 내용 | 비용 | 비고 |
|---|---|---|---|
| **A (추천)** | **`gpt-transcribe`** | $0.0045/분 | 파일 전사 지원. **키워드 힌트·문맥 입력 지원** → 관광지명 인식에 유리. 스냅샷은 별칭 하나뿐 |
| B | `gpt-4o-mini-transcribe-2025-12-15` | **미확인** (TS 기재 $0.003/분) | 2027-02-26 종료 |
| C | `gpt-live-transcribe` | **미확인** | 실시간용. PTT에는 과함 |

60초 상한이면 1회 최대 약 $0.0045. webm/opus·mp4/aac 입력 지원 여부는 **미확인** → PoC에서 두 포맷 확인(NFR-51).

### S3. 임베딩 모델 (requirements §6)
| 안 | 모델 | 차원 | 비용 | 운영 | 1인 적합 | 비고 |
|---|---|---|---|---|---|---|
| **A (추천)** | **`text-embedding-3-small`** | 1536 | $0.02/1M | 컨테이너 추가 없음 | 높음 | 종료 공지 없음(F5). 한국어 품질은 평가셋으로 측정 |
| B | 로컬 `BAAI/bge-m3` | 1024 | API 비용 0 | 전용 컨테이너 필요. GPU면 **NVIDIA Container Toolkit 설치가 필요해 D-14와 충돌**, CPU면 초기 인덱싱이 느림(속도 **미확인**) | 낮음 | 한국어 품질 **미확인** |
| C | `text-embedding-3-large` | 3072 | $0.13/1M | pgvector HNSW `vector` 2,000차원 제한 → `halfvec` 등 우회 필요(LightRAG 처리 여부 **미확인**) | 중간 | — |

임베딩 변경 = 전체 재인덱싱(F12). **A로 시작, PoC 소량 샘플에서만 B 비교** 권장(FR-70 충족).

### S4. LightRAG 인덱싱 LLM·질의 모드 (requirements §6, C11)
**인덱싱 LLM**

| 안 | 비용 | 비고 |
|---|---|---|
| **A (추천)** | `gpt-6-luna` | 싸다. 한국어 추출 품질 **미확인** |
| B | `gpt-6.1-terra` ($1.00/$5.00) | 10배 비쌈. A 품질 부족 시에만 |
| C | 허브 페이지만 상위 모델, 엔티티는 A | 복잡도 증가 |

인덱싱 총비용 **미확인** → PoC에서 50페이지 비용 측정 후 추정.

**질의 모드**

| 안 | 비고 |
|---|---|
| **A (추천, 시작값)** | `mix` (LightRAG 기본값, 그래프+벡터 청크) → FR-50 "벡터+그래프 후보 30개"와 가장 잘 맞음 |
| B | `hybrid` (local+global 그래프 중심, AN §5 안) |
| C | `local` 고정 — 빠를 수 있으나 넓은 질문에 약함 |

→ PoC P2에서 A/B 정답률·지연 비교 후 G3 전에 확정. 질의용 키워드 추출 LLM을 따로 둘 수 있는지 **미확인**.

### S5. 리랭커 서빙 (requirements §6, TS §5.3)
| 안 | 내용 | 운영 | 1인 적합 | 요구사항 |
|---|---|---|---|---|
| A | 전용 `reranker` 컨테이너(Cohere 호환 `/rerank`, 예: vLLM + `cohere` 바인딩) → LightRAG 리랭크 on | 컨테이너 1개 추가. vLLM CPU 서빙 적합성 **미확인** | 중간 | 충족 |
| **B (추천)** | **`tour-tools` 안 `sentence-transformers` CrossEncoder(`bge-reranker-v2-m3`)**. LightRAG는 `/query/data`로 후보만 받고(F11) 리랭크는 끔 | 컨테이너 추가 없음. tour-tools 이미지에 torch 포함으로 커짐 | 높음 | 충족. "30→5"(FR-50)를 직접 통제, 리랭커 on/off 평가(FR-70) 쉬움 |
| C | 호스팅 리랭크 API(Cohere·Jina) | 외부 키·비용(가격 **미확인**) | 중간 | D-05 취지와 어긋남 |

CPU 30쌍 재채점 지연 **미확인** → PoC P2 측정. 너무 느리면 A(GPU)로 가야 하고 D-14 충돌이 생김.

### S6. 개발 중 HTTPS 접속 경로 [F6] — O1 재확인
O1은 "개발 중에는 Cloudflare 임시 주소"였지만 **Quick Tunnel은 SSE 미지원**이 확인됨 → 개발 중 모바일 스트리밍 검증 불가.

| 안 | 내용 | 비용 | 요구사항 |
|---|---|---|---|
| **A (추천)** | **도메인을 지금 사서 Cloudflare에 연결, 처음부터 Named Tunnel** (O1의 "데모 전 구입"을 앞당김) | 도메인 연 비용 **미확인**, Named Tunnel 무료 여부 **미확인** | NFR-22·23 개발 중 검증 가능, 운영과 같은 경로 |
| B | 개발 중에는 PC `http://localhost`로 Nginx 직접 접속(브라우저별 보안 컨텍스트 동작 **미확인**). 모바일·PWA 검증은 도메인 구입 후 | 0원 | 모바일 검증 지연 |
| C | 임시 주소 유지 | 0원 | **스트리밍 검증 불가** — 비추천 |

S7에서 트랜잭션 메일 서비스를 쓰려면 도메인이 필요하므로 A는 S7과도 연결됨.

### S7. 인증코드 메일 발송 (FR-07)
| 안 | 비용 | 운영 | 1인 적합 | 비고 |
|---|---|---|---|---|
| **A (추천)** | **Gmail SMTP + 앱 비밀번호**(2단계 인증 필요) | 무료. 일일 발송 한도 **미확인** | 높음 | 데모 규모에 충분. 발신자가 개인 Gmail로 보임 |
| B | 트랜잭션 메일 서비스(Resend·Brevo·Mailgun 등) | 무료 등급·한도 **미확인** | 중간 | 도메인 DNS 인증(SPF·DKIM) 필요 → S6-A일 때만 현실적 |
| C | 메일 없이 관리자 수동 재설정 | 0 | 높음 | **FR-05 위반** — 불가 |

공통: 발송은 SMTP 함수 하나, 테스트는 목킹(NFR-70). Mailpit 컨테이너는 선택.

### S8. TourAPI 초기 적재 전략 [F7]
개발계정 1,000건/일. 1건에 상세 오퍼레이션 3개(`detailCommon2`·`detailIntro2`·`detailInfo2`)를 부른다고 가정하면 하루 약 300건(한도 단위 **미확인**). 서울·제주 총 항목 수 **미확인**.

| 안 | 내용 | 비고 |
|---|---|---|
| **A (추천)** | **FR-48대로 개발계정으로 나눠 적재 + 이어하기**. PoC P3에서 `totalCount`를 먼저 조회해 일수 계산 | 1만 건이면 한 달 이상 가능(가정) |
| B | A + 운영계정 트래픽 증설 신청 | "활용사례 등록" 필요 → 사전 신청 가능 여부 **미확인** |
| C | 상세 정보 일부 빼고 적재 | 운영시간·요금(FR-41) 누락 — 비추천 |

PoC 결과가 "수십 일"이면 B를 다시 묻는다.

### S9. Hermes 배포·버전·보안 설정 [F3·F8·F9·F10]
| 안 | 내용 | 비고 |
|---|---|---|
| **A (추천)** | **공식 이미지 `nousresearch/hermes-agent:<버전 태그>`**(PoC 시점 고정) + `infra/hermes/config.yaml` 읽기 전용 마운트 | `latest` 금지 |
| B | 소스에서 직접 빌드 | 관리 부담 큼 |

A에서 반드시 정할 것 (PoC P1):
1. 플랫폼 toolset을 기본 `hermes-api-server`(터미널 포함) 대신 **web 툴 + tour-tools MCP만**으로 + `mcp_servers.tour-tools.tools.include`에 4개만. 정확한 설정 키 **미확인**.
2. **memory·session_search 끄기** — 여러 사용자가 Hermes 하나를 공유하므로 정보 섞임 위험(NFR-30).
3. Hermes→OpenAI 호출이 Chat Completions인지 Responses인지 — 전자면 툴 호출에 `reasoning_effort=none` 필요(F3) → **미확인**.
4. `/v1/chat/completions` 스트림 끝 `usage`에 캐시 토큰 포함 여부 **미확인**(FR-61·NFR-40).
5. `prompt_cache_key` 전달 여부 **미확인**. 안 되면 NFR-40을 "고정 프리픽스 자동 캐싱 + `cached_tokens` 측정"으로 완화.
6. Hermes 기본 시스템 프롬프트 토큰 수 → 질의 1건 비용 추정의 핵심.

### S10. MCP 서버 구현 (`tour-tools`)
| 안 | 비고 |
|---|---|
| **A (추천)** | **공식 `mcp` Python SDK(v2.3.0, FastMCP 포함) + Streamable HTTP** — Compose 내부망에서 Hermes가 URL로 연결 |
| B | 별도 `fastmcp` 패키지 — 의존성 하나 더 |
| C | stdio 전송(Hermes 컨테이너 안 실행) — 분리가 깨짐 |

Hermes의 HTTP 연결 지원은 문서 예시로 확인, 전송 방식 세부는 **미확인** → P1.

### S11. 백엔드 기본 스택 (api·tour-tools·ingest 공통)
| 안 | 구성 | 비고 |
|---|---|---|
| **A (추천)** | **Python 3.12, uv, FastAPI(0.162), SQLAlchemy 2.1(async) + asyncpg, Alembic, argon2-cffi(25.1), pytest** | 3.12에서 torch·sentence-transformers 포함 호환 **미확인** |
| B | SQLModel | SQLAlchemy 위 한 겹 더 |
| C | asyncpg 직접 SQL + 수동 마이그레이션 | 테이블 10개 이상이라 부담 |

LightRAG 테이블은 LightRAG가 관리, Alembic은 **우리 테이블만**(스키마 분리는 G3). 흔한 비밀번호 목록(NFR-01) 출처는 G3/spec.

### S12. FastAPI가 Hermes 스트림을 받는 방법 [F8]
| 안 | 비고 |
|---|---|
| **A (추천)** | **`httpx` 스트리밍 + SSE 직접 파싱** — `hermes.tool.progress`(툴 진행 표시·`tool_trace`)와 keepalive 주석을 명시적으로 처리 |
| B | `openai` Python SDK에 `base_url`로 Hermes 지정 — 커스텀 이벤트 처리 **미확인** |

### S13. rate limit·로그인 잠금·일일 한도 저장소
| 안 | 비고 |
|---|---|
| **A (추천)** | **PostgreSQL만** — 실패 횟수·잠금·일일 50회·추가 승인·분당 채팅 횟수를 테이블로. 동시 사용자 1~5명(NFR-61) |
| B | A + Nginx `limit_req` IP 1차 방어 (선택) |
| C | Redis 추가 — D-07 취지와 맞지 않음 |

공통: 터널을 거치면 Nginx가 보는 IP는 `cloudflared` IP → **`CF-Connecting-IP`를 신뢰된 프록시에서만 읽도록**(NFR-02, G3에서 명시).

### S14. FAQ 응답 캐시 (FR-60)
| 안 | 비고 |
|---|---|
| A | 정규화 후 완전 일치만 재사용 — "비슷한 질문" 미충족 |
| **B (추천)** | **질문 임베딩 pgvector 유사도, 임계값 이상이면 재사용**. 대상: **세션 첫 질문 + 위치·상대 날짜·웹 검색을 쓰지 않은 답변**. 답변의 contentid를 저장해 ingest 갱신 시 무효화. 임계값 **미확인** → 평가셋으로 |
| C | MVP에서 생략 — FR-60 위반 |

### S15. 스케줄러 (C5 해소)
| 안 | 비고 |
|---|---|
| **A (추천)** | **`ingest` 컨테이너 상주 + APScheduler(3.11)**: 01:00 KST 현행화 + 90일 대화 삭제(NFR-31), 중복 실행 방지. 초기 적재(FR-48)는 같은 이미지 CLI로 수동 |
| B | `supercronic` cron 컨테이너에서 CLI 실행 |
| C | Hermes 내장 cron — 쓰기 권한 필요, NFR-07 충돌 — 비추천 |
| D | 호스트 cron/systemd — D-14 위반 |

### S16. 프론트 UI·스트리밍 클라이언트
| 안 | 구성 | 비고 |
|---|---|---|
| **A (추천)** | **Next.js 16(16.4.5) + React 19 + Tailwind CSS 4 + shadcn/ui**, `react-markdown` + `remark-gfm`(**raw HTML 끔**, XSS 방지), **`fetch` + `ReadableStream` 직접 파싱**(POST·CSRF 헤더 가능) | 의존성 최소 |
| B | A + Vercel AI SDK `useChat` | FastAPI가 전용 스트림 프로토콜 구현 필요 |
| C | `EventSource` | GET만 가능 → NFR-05와 맞지 않음 |

버전은 2026-11-07 npm 기준, 최종 고정은 G4 이후 첫 작업.

### S17. PWA 구현 (NFR-52)
| 안 | 비고 |
|---|---|
| **A (추천)** | **Next.js 기본 `app/manifest.ts` + 아이콘 + 최소 서비스워커(오프라인 캐시 없음)**, `display: standalone` |
| B | Serwist 등 플러그인 — 오프라인 불필요, Next 16 호환 **미확인** |
| C | manifest만 — Android 설치 조건 충족 여부 **미확인** |

### S18. 백오피스 구현 (FR-80)
| 안 | 비고 |
|---|---|
| **A (추천)** | **같은 Next.js 앱 `/admin` 라우트 그룹**, 권한 검사는 FastAPI `/api/admin/*` 서버측. 같은 출처(NFR-10)·같은 세션 쿠키 |
| B | 별도 Next.js 앱 — 빌드·컨테이너 2배 |
| C | FastAPI 서버 렌더링(SQLAdmin 등) — 대시보드·승인 흐름 커스터마이징 번거로움 |

### S19. 프론트·E2E 테스트 도구 (NFR-70·71)
| 안 | 비고 |
|---|---|
| **A (추천)** | **Vitest + React Testing Library**(단위), **Playwright(1.65)**(E2E). 음성 E2E는 Chromium 가짜 마이크 플래그로 파일 주입(동작은 PoC/E2E 설계 때 확인) |
| B | Jest + RTL + Playwright — ESM/TS 설정 번거로움 |
| C | Playwright만 — 컴포넌트 회귀 잡기 어려움 |

### S20. ElevenLabs 모델·음성·한도 (FR-32, NFR-43)
한국어 지원 현행 모델: `eleven_v4`, `eleven_v4_turbo`, `eleven_v3`, `eleven_multilingual_v2`, `eleven_flash_v2_5`. `eleven_turbo_v2_5`는 deprecated.

| 안 | 비고 |
|---|---|
| **A (추천)** | **`eleven_flash_v2_5`** — 지연 짧음(~100ms), 최대 40,000자. 크레딧 단가 우위 **미확인** |
| B | `eleven_v4_turbo` — 최신·표현력. 단가 **미확인** |
| C | `eleven_multilingual_v2` / `eleven_v4` — 품질 우선, 지연·비용 **미확인** |

- voice_id: 사용자가 한국어 샘플 2~3개를 듣고 선택 → `.env`의 `ELEVENLABS_VOICE_ID`.
- 한도: 플랜 월 크레딧 **미확인** → **사용량 기록(NFR-43) + 1회 요청 글자 수 상한**만. 플랜이 작으면 다시 묻는다.

### S21. 지표·사용량 저장 (NFR-60, FR-61·83)
| 안 | 비고 |
|---|---|
| **A (추천)** | **PostgreSQL 테이블**(첫 토큰 지연·전체 시간·툴 시간·토큰·캐시 토큰·외부 API 사용량) + 백오피스 대시보드 |
| B | Langfuse 등 관측 도구 — 데모 규모에 과함 |
| C | 로그 파일만 — 대시보드(FR-83) 어려움 |

---

## 4. G3 전에 필요한 PoC (진행 방식 승인 필요)

CLAUDE.md는 "G4 전 소스 수정 금지". 아래 PoC는 **레포 밖 임시 디렉터리에서 버리는 코드로** 하거나 별도 허락이 필요하다.

| PoC | 확인할 것 | 영향 받는 결정 |
|---|---|---|
| P1 Hermes | 고정 태그 실행, API Server 응답, toolset 화이트리스트 키, memory 끄기, tour-tools MCP(HTTP) 연결, `web.backend: tavily`, OpenAI 호출 방식·`gpt-6-luna` 툴 호출, 스트림 `usage`·캐시 토큰, `prompt_cache_key` 전달, 기본 시스템 프롬프트 토큰 수 | S9, S12, NFR-40 |
| P2 LightRAG | pg18 + `PGTableGraphStorage`로 위키 50페이지 인덱싱 → 한국어 엔티티 품질, 인덱싱 비용, `mix` vs `hybrid`, `/query/data` 응답의 청크·출처, CPU CrossEncoder 30쌍 지연, (선택) bge-m3 비교 | S3, S4, S5 |
| P3 TourAPI | 실제 키로 명세, 서울·제주 × 8종 `totalCount`, 한도 계산 단위, `areaBasedSyncList2` 응답 | S8, FR-48 |
| P4 음성 | `gpt-transcribe`로 webm/opus·mp4/aac 전사, ElevenLabs 한국어 음성 샘플 | S2, S20 |

## 5. 비용 감각 (참고용 추정)
- AN §3.5 추정(질의 1건 입력 약 8k / 출력 약 500 토큰) × `gpt-6-luna` 단가 → **1건 약 $0.001**. 캐시 쓰기 1.25배·Hermes 기본 프롬프트 크기는 미반영(**미확인**, P1 측정).
- 최대치 가정: 5명 × 50회 × 30일 = 7,500건 → 약 $7.5/월 + 인덱싱·허브 페이지 비용(**미확인**). **월 $10 경고선(FR-63)에 가까울 수 있다.**

## 6. G2 승인 후 갱신할 문서
- `requirements.md`: D-05·NFR-41(S1), STT 모델 표기(S2), NFR-22·O1(S6)
- `TECH_STACK.md`: §2 표 전부 + S1~S21 결과
- `PROGRESS.md`: G2 결정 로그
