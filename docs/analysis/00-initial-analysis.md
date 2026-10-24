# 공공데이터 챗봇 — 사전 분석 (2026-10-24)

> 하네스(`debugs-choi-harnes`) **Phase 1 진입 전** 사전 조사 문서. 확정 사항 아님 — G1~G3에서 확정한다.
> 코드는 건드리지 않았음. 확인 못 한 것은 **[미확인]** 표시.

---

## 0. 한 줄 결론

- **Hermes Agent → WSL2(Ubuntu-22.04)에 설치 가능, 공식 권장 경로이기도 함.** 현재 PC 조건(WSL 2.x, systemd 켜짐, GPU 패스스루 동작, WSLg 오디오)이 이미 다 갖춰져 있음.
- **Graph RAG는 LightRAG 추천** (MS GraphRAG보다 인덱싱 저렴, 문서 삭제/증분 갱신 지원 → "현행화"에 유리).
- **⚠️ Drama 3 로컬 구동은 불가** — 35B MoE(가중치 ~40GB), RTX 4060 8GB로는 안 됨. 쓰려면 API(OpenRouter/Fish Audio)로.
- **⚠️ 공공데이터는 대부분 표(수치) 데이터** → Graph RAG만으로는 "합계/최댓값/특정 날짜 값" 질문에 약함. **표 데이터는 DuckDB/SQLite 조회 툴, 설명·관계형 지식은 Wiki+GraphRAG**로 나누는 하이브리드를 권장.

---

## 1. 현재 환경 점검 (실측)

| 항목 | 값 | 판단 |
|---|---|---|
| OS | Windows 11 Pro 10.0.26200 | OK |
| WSL | 2.x (WSL 3.0.3.0, kernel 6.18.54), WSLg 1.0.79 | OK |
| 배포판 | Ubuntu-22.04, **VERSION 2** | Hermes 공식 테스트 대상(Ubuntu LTS) |
| systemd | `/etc/wsl.conf`에 `systemd=true` | Hermes gateway 서비스 상시 구동 가능 |
| WSL 자원 | 12 vCPU, RAM 15GiB(호스트 32GB), 디스크 944GB 여유 | 충분. 필요시 `.wslconfig`로 RAM 상향 |
| GPU | RTX 4060 **8GB**, WSL 내부 `nvidia-smi` 인식됨 | faster-whisper/임베딩/리랭커 로컬 가능, 로컬 LLM·Drama3는 무리 |
| Python | 3.11.9, git, docker 있음 | OK (uv는 없음 → 설치 권장) |
| 오디오 | `PULSE_SERVER=unix:/mnt/wslg/PulseServer`, RDPSource 존재 | WSL 안에서 마이크 접근 이론상 가능 [미확인: 실제 녹음 품질/지연] |
| `/mnt/d` | 9p(drvfs) 마운트 | **느림** — Hermes·모델·venv·인덱스는 WSL 홈(`~`)에 둬야 함 |
| Hermes | 미설치(`~/.hermes` 없음) | — |

기존 자산(재사용 후보): `D:\workspaces\faster_whisper_lab`, `smart_ai_chatbot`(vector 폴더 있음), `llm_lab`, `ai_lab`.

---

## 2. 하네스 플러그인 확인 — `debugs-choi-harnes`

- 위치: **https://github.com/r0cketspan/debugs-choi-harnes** (README 기재 주소 `LegSmith/debugs-choi-harnes`는 301 리다이렉트됨 → 계정명 변경된 듯)
- v0.1.0, 마지막 커밋 2026-07-30. 공식 마켓(`anthropics/claude-plugins-official`) 최신 `marketplace.json`에는 **아직 미등재** (검토 대기 상태와 일치).
- 현재 이 PC의 Claude Code에는 **미설치**.
- 구조: 9 Phase · 5 Gate, 에이전트 6종(requirements-analyst → solution-architect → task-planner → spec-writer → implementer → integration-designer), 산출물 `docs/harness/`.

### 이 프로젝트에 적용 시 메모
1. 설치: `/plugin marketplace add r0cketspan/debugs-choi-harnes` → `/plugin install debugs-choi-harnes@debugs-choi-harnes-marketplace` (LegSmith 주소도 리다이렉트로 될 가능성 높음 [미확인])
2. 시작: `/new 공공데이터 기반 Graph RAG 챗봇 (Hermes Agent)` → 이 문서를 Phase 1 입력 자료로 사용.
3. **현재 브랜치가 `master`, 커밋 0개** → 하네스 커밋 컨벤션은 git log 학습 불가 → Conventional Commits 폴백됨. (gitStatus상 main 브랜치는 `main`으로 표시됨 — G5 병합 대상 브랜치를 master/main 중 하나로 정리 필요)
4. 하네스 개선 아이디어(플러그인 쪽, 선택): `plugin.json`/README의 `LegSmith` URL을 실제 주소로 정리 / RAG·챗봇류는 `test.md`에 단위테스트 외에 **골든 Q&A 평가셋(정답률·근거 일치율)** 항목이 있으면 좋음.

---

## 3. 구성요소별 분석

### 3.1 Hermes Agent (Nous Research)
- 설치(WSL 안): `curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash && source ~/.bashrc && hermes`
- 설치 경로: 코드 `~/.hermes/hermes-agent/`, 데이터·설정 `~/.hermes/` (`config.yaml`, `.env`)
- **OpenAI 연결**: `.env`에 `OPENAI_API_KEY=...`, `config.yaml`
  ```yaml
  model:
    provider: "openai-api"
    default: "<model-id>"
  ```
- **챗봇 백엔드로 쓰는 법 = API Server**: `hermes gateway` 실행 시 OpenAI 호환 엔드포인트 제공 (기본 `127.0.0.1:8642`)
  - `/v1/chat/completions`(stateless), `/v1/responses`(서버측 대화 상태), `/v1/runs`(비동기+이벤트), SSE 스트리밍, 툴 호출 진행 이벤트 노출
  - `API_SERVER_KEY` 필수. Windows 브라우저에서 접근하려면 `.wslconfig`에 `networkingMode=mirrored` 권장
  - Open WebUI / LibreChat / LobeChat 등 기성 프론트를 그대로 붙일 수 있음 → **MVP 프론트 개발 생략 가능**
- **메신저 게이트웨이**: Telegram/Discord/Slack 등 20+ 지원 → 웹 대신 텔레그램 봇으로 MVP를 내는 것도 가장 빠른 길
- **MCP 지원**: `config.yaml`의 `mcp_servers`에 stdio/HTTP 서버 등록, `tools.include/exclude`로 툴 필터링
- **음성**: STT `local`(=faster-whisper 내장!), TTS `edge`(무료)/`elevenlabs`/`openai`/`neutts`/`piper` 등. **Fish Audio(Drama3)는 기본 목록에 없음** → 플러그인 또는 별도 서비스 필요
- **Cron 내장** → 데이터 현행화 작업을 Hermes 스케줄로 돌릴 수도 있음
- 보조 모델(`auxiliary.compression.model`)로 요약/압축은 더 싼 모델 지정 가능

#### ⚠️ Hermes 보안 주의 (중요)
Hermes는 **터미널·파일·브라우저 등 60+ 툴을 가진 범용 자율 에이전트**다. 불특정 다수에게 챗봇으로 노출하면 프롬프트 인젝션으로 쉘 실행이 가능해진다.
→ 공개 챗봇이면 API Server 플랫폼의 툴셋을 **RAG 조회 툴 + 데이터 조회 툴만 허용(whitelist)** 하도록 G3에서 반드시 설계. 터미널 백엔드는 docker 샌드박스로. [미확인: 플랫폼별 toolset 제한 정확한 설정 키 — Phase 2에서 문서 확인]

### 3.2 Graph RAG — LightRAG 추천
| | LightRAG (HKUDS) | Microsoft GraphRAG |
|---|---|---|
| 인덱싱 비용 | 낮음 | 높음 (커뮤니티 요약 다수) |
| 증분 갱신 | 지원, **문서 삭제 시 영향 엔티티 재구성** | 3.3.0(2026-10)부터 `update` 지원, 삭제는 사실상 재인덱싱 |
| 서버 | `lightrag-server` (REST + Web UI + Ollama 호환 API) | 라이브러리 중심 |
| 저장소 | 기본 파일(개발용) / PostgreSQL(운영 권장), Neo4j, Qdrant 등 | Parquet 등 |
| 질의 모드 | local / global / hybrid / naive / **mix(기본)** | local / global / drift |
| 리랭커 | `bge-reranker-v2-m3` 지원(+1~2초) | — |

- 설치: `uv tool install "lightrag-hku[api]"` → `lightrag-server`
- **기본 바인딩이 0.0.0.0** → 인증 설정 필수
- `SUMMARY_LANGUAGE`로 엔티티/요약 언어 지정(→ Korean) [미확인: 한국어 엔티티 추출 품질 — 샘플 데이터로 PoC 필요]
- 임베딩 모델은 인덱싱·질의 동일해야 함 → **처음에 확정**(바꾸면 재인덱싱)
- Hermes 연결: LightRAG MCP 서버(커뮤니티) 또는 **얇은 MCP 래퍼 직접 작성**(query/insert/delete 3개 툴) — 후자 권장(툴 노출 범위 통제)

### 3.3 LLM Wiki (Karpathy 패턴) — 데이터 현행화/관리 레이어
- 구조: `raw/`(원본, 불변) → `wiki/`(LLM이 작성·유지하는 상호 링크된 마크다운) → 스키마 파일(규칙)
- 연산: **ingest**(새 데이터 반영) / **query** / **lint**(깨진 링크·오래된 페이지·모순 점검)
- 이 프로젝트에서의 역할 분담 제안:
  - **Wiki = 사람이 읽을 수 있는 정본(Source of Truth) + 변경 이력(git)**
  - **LightRAG = Wiki 페이지를 인덱싱한 검색 엔진** (raw가 아니라 wiki를 넣음 → 노이즈↓, 일관성↑)
  - 갱신 흐름: 데이터 변경 감지 → 영향 wiki 페이지만 갱신(frontmatter에 `source`, `기준일`, `updated_at`) → LightRAG에서 해당 문서 delete+insert
- 알려진 한계: wiki가 커지면 LLM 컨텍스트로 전체를 못 봄 → 그래서 Graph RAG가 필요한 것이고, 이 조합 자체는 합리적

### 3.4 공공데이터 소스
- 공식 data.go.kr MCP는 확인 안 됨. 커뮤니티 MCP 있음: `opendata-mcp`(API 검색/문서/호출, `ODP_SERVICE_KEY`), `data-go-mcp-servers`(기관별 모음, Apache-2.0), 서울 열린데이터광장 예제 등
- **권장**: 런타임에 범용 MCP로 아무 API나 부르게 하지 말고, **쓸 데이터셋을 정해서 수집 파이프라인으로 적재** (응답 속도·비용·정확성 모두 유리). 실시간성이 필요한 소수 API만 툴로.
- **표 데이터 → DuckDB(또는 SQLite) + 조회 툴**, 설명/규정/기관 관계 → Wiki+LightRAG

### 3.5 LLM — OpenAI 모델/비용 (공식 가격표, 2026-10-24 조회, $/1M tokens)
| 모델 | 입력 | 캐시입력 | 출력 | 용도 제안 |
|---|---|---|---|---|
| **gpt-6-luna** | 0.10 | 0.01 | 0.50 | **메인 챗 + LightRAG 질의** (가성비 최상) |
| gpt-5-nano | 0.05 | 0.005 | 0.40 | 키워드 추출/분류 등 보조 |
| gpt-5.6-luna | 0.20 | 0.02 | 1.20 | 대안 |
| gpt-6.1-sol | 2.00 | 0.10 | 10.00 | 품질 부족할 때만 (Wiki 작성/ingest 품질용) |
| text-embedding-3-small | 0.02 | — | — | 임베딩(클라우드) |

- 임베딩 대안: **로컬 `BAAI/bge-m3`**(한국어 강함, GPU 2GB 내외) — 비용 0, 대신 WSL GPU 의존
- 대략 추정: 질의 1건 = 입력 ~8k(시스템+툴+컨텍스트) / 출력 ~500 → gpt-6-luna 기준 **약 $0.001 (≈1.4원)**. Hermes 시스템 프롬프트·툴 정의가 커서 **프롬프트 캐싱 효과가 큼**. [미확인: Hermes 기본 시스템 프롬프트 실제 토큰 수 — 설치 후 측정]

### 3.6 STT / TTS (서브)
- **STT — faster-whisper**: Hermes `stt.provider: local`로 바로 연동됨. RTX 4060에서 `large-v3-turbo` + `int8_float16` 정도면 한국어 품질·속도 균형 좋음(VRAM ~2–3GB). WSL CUDA에선 cuBLAS 12 / cuDNN 9 라이브러리 필요. 기존 `faster_whisper_lab` 재사용 가능.
- **TTS**
  - **Drama 3 (Fish Audio)**: 35B MoE(활성 3B), 83개 언어, 2026-10-13 가중치 공개, **라이선스: Fish Audio Community License(제한적 상업 이용)**. 가중치 ~40GB → **로컬 불가**. OpenRouter(`fish-audio/drama-3`) 등 API로만 현실적. Hermes 기본 TTS 목록에 없음 → 커스텀 연동 필요. 한국어 품질 [미확인].
  - **ElevenLabs**: Hermes 기본 지원(`ELEVENLABS_API_KEY`), 한국어 품질 검증된 편 → **데모용 1순위**
  - **Edge TTS**: 무료, 키 불필요, `ko-KR` 음성 있음 → **개발 중 기본값**
- **마이크 처리 방식 권장**: WSL 오디오(WSLg Pulse) 의존보다 **브라우저에서 녹음(getUserMedia) → 서버로 업로드 → STT** 구조가 안정적이고, 나중에 원격 사용자도 그대로 지원됨. Hermes CLI 음성 모드는 로컬 테스트 용도로만.

GPU 8GB 예산(동시 상주 기준): whisper turbo ~2.5GB + bge-m3 ~2GB + reranker ~1GB ≈ 5.5GB → 가능.

---

## 4. 제안 아키텍처 (초안, G3에서 확정)

```
                ┌─────────────── 데이터 현행화 (배치 / Hermes cron) ───────────────┐
 data.go.kr API │  collector ──▶ raw/ (날짜별 스냅샷, 불변)                          │
 파일 데이터셋   │                   │                                               │
                │      ┌────────────┴─────────────┐                                 │
                │      ▼                          ▼                                 │
                │  표 데이터 → DuckDB        설명/관계 → wiki/*.md (LLM Wiki, git)   │
                │                                 │  ingest / lint                  │
                │                                 ▼                                 │
                │                         LightRAG (graph+vector, 변경분만 delete/insert)
                └───────────────────────────────────────────────────────────────────┘
                                     │ (MCP: rag_query / data_query)
 [브라우저 UI] ──▶ Hermes API Server (:8642, /v1/responses, SSE) ──▶ OpenAI gpt-6-luna
   마이크 녹음 ─▶ STT(faster-whisper) ─┘          └─ 툴 whitelist: rag_query, data_query 만
   TTS 재생 ◀── Edge / ElevenLabs / (Drama3 API)
```

모두 WSL2(Ubuntu-22.04) 안에서 구동, Windows 브라우저는 mirrored 네트워킹으로 `localhost` 접근.

---

## 5. 리스크 & 대응

| 리스크 | 영향 | 대응 |
|---|---|---|
| Hermes가 공개 챗봇 용도로 툴 권한 과다 | 보안 사고 | 툴 whitelist, docker 터미널 백엔드, API 키 |
| 표 데이터를 RAG로만 처리 | 수치 오답 | DuckDB 조회 툴 병행 |
| 한국어 엔티티 추출 품질 | 그래프 품질 저하 | 소량 PoC 후 모델/프롬프트 조정, 임베딩은 bge-m3 검토 |
| 응답 속도 (Hermes 루프 + LightRAG 키워드 추출 + 검색) | "빨리 답하기" 목표 미달 | mix 모드 대신 local/hybrid 고정, 리랭커 선택적, 스트리밍, 자주 묻는 질문 캐시 |
| 프로젝트 파일이 `/mnt/d`에 있으면 느림 | 개발 경험 저하 | 레포를 WSL `~/code/`로 이전 검토 |
| Drama3 라이선스/한국어 품질 | 상업 사용 제약 | ElevenLabs/Edge 우선, Drama3는 실험 |
| WSL 재시작 시 IP 변경, 포트 노출 | 접근 불가 | `networkingMode=mirrored` |

---

## 6. 돌아오면 정할 것 (Phase 1 / G1 입력)

1. **어떤 공공데이터?** 도메인과 구체 데이터셋(예: 부동산 실거래가, 관광지, 복지 서비스, 기상, 대중교통 …). 표 데이터 위주인지 문서(규정·안내문) 위주인지.
2. **사용 채널**: 웹 UI(Open WebUI 같은 기성품 vs 직접 제작) / 텔레그램·디스코드 봇 / 둘 다
3. **누가 씀?** 본인 데모·포트폴리오 vs 불특정 공개 서비스 → 보안·비용 설계 수준이 달라짐
4. **레포 위치**: 지금처럼 `D:\workspaces\myAgent` 유지 vs WSL `~/code/myAgent`로 이전(권장)하고 Claude Code도 WSL에서 실행
5. **현행화 주기**: 일/주/월, 그리고 "기준일" 표기 필요 여부
6. **예산 상한**: 월 OpenAI 비용 상한, ElevenLabs 유료 플랜 여부
7. 브랜치 정리: master vs main 중 기준 브랜치

## 7. 다음 단계 제안
1. 하네스 설치 → `/new`로 Phase 1 시작 (이 문서 = 입력 자료)
2. G2 전 **PoC 2개만 먼저** 해보면 스택 결정이 확실해짐 (승인 시):
   - WSL에 Hermes 설치 + OpenAI 연결 + API Server 응답 확인
   - 데이터셋 샘플 1개로 LightRAG 한국어 인덱싱·질의 품질 확인

---

## 8. 추가 요구 역량 매핑 (2026-10-24 추가)

| 항목 | 가능 여부 | 이 프로젝트에서 구현되는 지점 |
|---|---|---|
| Tool calling · 에이전트 루프 | ✅ | Hermes가 루프 담당. 직접 구현 부분 = MCP 툴(`rag_query`/`data_query`/`wiki_ingest`) 설계·스키마. 루프 이해를 보여주려면 OpenAI SDK로 최소 에이전트 루프를 별도 모듈로 만들어 Hermes와 비교 (선택) |
| 벡터DB · 임베딩 | ✅ | LightRAG 벡터 저장소를 **Qdrant 또는 PostgreSQL(pgvector)** 로 명시 선택. 임베딩 = bge-m3(로컬 GPU) vs text-embedding-3-small 비교 |
| 추론 파이프라인 | ✅ | 질의 → (키워드 추출) → 그래프/벡터 검색 → 리랭크(bge-reranker-v2-m3) → 생성 → 근거 표기. 음성은 STT → 파이프라인 → TTS |
| 컨테이너 배포 | ✅ | 공식 이미지 `nousresearch/hermes-agent` (`gateway run`, 8642), LightRAG Docker Compose, Qdrant/Postgres, STT 서비스 → docker compose 한 벌. WSL2 docker 이미 설치됨 |
| LLM 서빙 | ⚠️ 제한적 | RTX 4060 8GB → vLLM/Ollama로 **소형 모델(4B~8B 양자화)** 정도만. 메인은 OpenAI, 로컬 모델은 fallback·보조 작업용 `custom` provider로 연결 |
| 프롬프트 캐싱 | ✅ | OpenAI 자동 캐싱(1,024토큰 이상 프리픽스). Hermes 시스템 프롬프트·툴 정의가 길어 효과 큼. `prompt_cache_key`, 고정 프리픽스 설계, 캐시 적중률(`cached_tokens`) 측정 |
| 멀티클라우드 운영 | ⚠️ 범위 조정 | 현실적 범위 = **멀티 프로바이더**(Hermes `fallback_providers`: OpenAI → Gemini/OpenRouter → 로컬 vLLM). 진짜 멀티클라우드(AWS+GCP 동시 배포)는 개인 프로젝트엔 과함 → 컨테이너 이식성 + 1개 클라우드 배포로 대체 권장. 주의: 프로바이더 전환 시 캐시 무효화로 비용 증가 |

---

## 9. 사용자 결정 사항 (2026-10-24)
- **LLM 서빙(로컬 모델) 제외.** LLM은 OpenAI API만 사용.
- **채널 = 웹 브라우저 + 모바일 브라우저** (반응형 웹/PWA). Discord·Telegram 등 메신저 게이트웨이 사용 안 함.
- **STT = 비실시간 Push-to-talk**: 시작 버튼 → 녹음 → 종료 버튼 → 녹음 파일 1개를 STT → 텍스트. faster-whisper 불필요 → OpenAI 전사 API(`gpt-4o-mini-transcribe` $0.003/분 등) 사용.
  - 결과 텍스트를 입력창에 채워 사용자가 확인·수정 후 전송 (오인식 보정)
  - 모바일 마이크(getUserMedia)는 **HTTPS 필수** → 개발 중에도 터널(cloudflared 등) 또는 로컬 인증서 필요
  - iOS Safari는 MediaRecorder 출력이 mp4/aac, 크롬은 webm → 둘 다 OpenAI 전사 API 지원 포맷
- 위 결정으로 §3.6의 faster-whisper / WSL 오디오 / GPU 예산 논의는 당장은 불필요해짐.

## 10. 사용자 결정 사항 (2차, 2026-10-24)
- **STT 확장성**: 현재는 OpenAI 전사 API, 추후 WSL/Linux GPU의 faster-whisper/Whisper로 교체 가능하게 `SttProvider` 인터페이스 + 설정값 전환(`STT_PROVIDER=openai|faster_whisper`). 로컬 STT는 별도 GPU 컨테이너로 분리 가능하게.
- **스택**: 프론트 **Next.js**(반응형 채팅 UI), 백엔드 **FastAPI**(중계 서버, 브라우저는 FastAPI만 호출).
- **RAG**: LLM Wiki 페이지를 벡터 임베딩 → RAG 검색 대상.
- **DB**: **PostgreSQL** 단일화 제안 — pgvector(벡터) + 표 데이터 + 대화 세션/메시지. (DuckDB 제거)
- **리랭커 사용**.
- **실행 환경**: 전부 WSL2 Ubuntu-22.04 안에서(Docker). Windows 11에는 브라우저만.
- **배포**: Docker Compose(Rocky Linux·Windows Docker Desktop 이식 가능), 클라우드 배포 안 함. 리버스 프록시는 HTTPS + 단일 진입점 용도.
- **비용 최적화**: 프롬프트 캐싱, 모델 분리(메인/보조), FAQ 응답 캐시, 사용량 대시보드. **LLM 장애 시 다른 프로바이더로 fallback 하지 않음** → 시스템 장애로 사용자에게 안내(에러 메시지 + 재시도 버튼). 멀티 프로바이더 제외.
- **평가·테스트**: 골든 Q&A 평가셋(정답률·근거 일치율) + E2E 통합테스트 채택.
- **미확정(추가 논의)**: Tool 목록 확정, 대화 유지 정책(컨텍스트 턴 수/요약/세션 최대 길이/보관 기간), 사용자 식별(로그인 vs 익명).

## 11. 사용자 결정 사항 (3차, 2026-10-24)
- **도메인 = 관광 챗봇**, 데이터 = 한국관광공사 TourAPI 4.0(KorService2).
- 대화 정책: 최근 10턴 원문 + 누적 요약 / 세션 최대 50턴 / 90일 보관 — **확정**.
- **로그인 필수 — 일반 로그인(아이디+비밀번호, Argon2id) + 서버 세션 쿠키**로 결정 (소셜 로그인 제외). 상세 TECH_STACK.md §7.
- TourAPI 인증키는 사용자가 공공데이터포털에서 직접 발급.
- "LLM검색" = 툴 없이 LLM이 직접 답변(스몰토크·일반 상식). 관광 사실(운영시간·요금 등)은 툴 결과로만 답변.
- 코드 주석 규칙: 함수 위 설명 주석 + 함수 내 단계 주석 (CLAUDE.md).
- 레포를 WSL `~/code/myAgent`로 이전.
- 문서: `CLAUDE.md`(Karpathy-inspired 원칙 + 프로젝트 규칙), `TECH_STACK.md`(개발자용 기술 문서) 작성.

---

### 참고 출처
- Hermes 설치: https://hermes-agent.nousresearch.com/docs/getting-started/installation/
- Hermes WSL2 가이드: https://hermes-agent.nousresearch.com/docs/user-guide/windows-wsl-quickstart
- Hermes API Server: https://hermes-agent.nousresearch.com/docs/user-guide/features/api-server
- Hermes Voice: https://hermes-agent.nousresearch.com/docs/user-guide/features/voice-mode
- Hermes MCP: https://hermes-agent.nousresearch.com/docs/user-guide/features/mcp
- Hermes Providers: https://hermes-agent.nousresearch.com/docs/integrations/providers
- LightRAG: https://github.com/HKUDS/LightRAG
- LightRAG vs GraphRAG: https://particula.tech/blog/lightrag-vs-graphrag , https://tianpan.co/blog/2026/04/09/graphrag-production-when-vector-search-hits-ceiling
- LLM Wiki: https://blog.starmorph.com/blog/karpathy-llm-wiki-knowledge-base-guide , https://noqta.tn/en/blog/karpathy-llm-wiki-knowledge-base-beyond-rag-2026
- OpenAI 가격: https://developers.openai.com/api/docs/pricing
- Drama 3: https://www.llmreference.com/model/drama-3 , https://comfyui-wiki.com/ko/news/2026-10-13-fish-audio-drama-3
- 공공데이터 MCP: https://glama.ai/mcp/servers/@ceami/opendata-mcp , https://tomevault.io/tome/Koomook/data-go-mcp-servers
- 하네스: https://github.com/r0cketspan/debugs-choi-harnes
