# 26-release-readiness — 릴리스 준비 점검 (spec)

> 하네스 Phase 4 산출물 (spec-writer, 작성 2026-11-22). 상태: **초안(2026-11-22)** — 확인 질문(§13)은 아직 결정 전. 브랜치 `feat/26-release-readiness`, 의존 작업 01~25 전부.
> 근거: [PL]=program_list.md(G4 승인본) §2 표·§3 "26-release-readiness"·§1.1-5·§4 추적표·§5 X-f · [A]=architecture.md(G3 재승인본) §2 컨테이너 표·§7 디렉터리·named volume·ADR-01·10·26·§9 "컨테이너 격리"·비밀값 표 · [R]=requirements.md NFR-08·09·17·20·21·36·71, D-23 · [TS]=TECH_STACK.md §9·§12 · [SG]=SECURITY_GUIDE.md · [PG]=PROGRESS.md 결정 로그(02-Q5·02-Q9·G4 Q1·Q8·14-Q1·20-Q12·21-Q1·21-Q2·21-Q4·22-Q8·22-Q11).
> **이어받는 확정 spec**(compose·`.env`·Dockerfile을 만들거나 고친 작업): [01](§4.1 `.env.example` 8키·§4.3 lightrag 비밀값·§5 compose 4서비스·`compose.dev.yaml`·§5.4 Dockerfile `app`/`tools`·`01-init.sh`) · [02](§10 api·nginx·cloudflared, `TUNNEL_TOKEN` 환경변수, nginx `127.0.0.1:8080`) · [05](§8 api DB·`SESSION_SECRET`, cloudflared 프로필 제거, `create-admin`) · [06](SMTP 3키) · [10](tour-tools에 `TOURAPI_SERVICE_KEY`) · [14](§9 web 서비스·`web/Dockerfile`·nginx `location /`) · [17](ElevenLabs 2키) · [20](ingest에 `OPENAI_API_KEY`, Dockerfile `app`에 git) · [21](§5.4 ingest 상주·healthcheck·`service_healthy`) · [22](§3.3 ingest에 `TAVILY_API_KEY`·`./eval` 마운트·결정 설정값 위치) · [24](§3.3 `x-tuning`). 03·04·07~09·11~13·15·16·18·19는 compose·`.env`를 바꾸지 않는다(각 spec "새 환경변수 없음" 확인).
> **23~25 확정본 대조(2026-11-22)**: [23](`nadri eval attack`, compose 변경 없음 — 22의 ingest 키·`./eval` 마운트 사용, 가짜 웹 툴이라 Tavily 키 안 씀) · [24](§3.3 `x-tuning` 공용 블록(24-Q2), 스케줄러 `daily_quality`@03:00·놓친 실행(24-Q10), `lock.py` 키 2(코드만, compose 무관), `nadri eval quality --date … [--force]`, `./eval` 마운트는 22 것 그대로) · [25](새 환경변수·compose·nginx 변경 없음). `.env.example`에 새 키를 넣는 작업은 없다.
> **미확인** = 문서·공식 자료로 확인하지 못한 사실.

---

## 1. 작업 목표

01~25가 조금씩 고쳐 온 `compose.yaml`·`compose.dev.yaml`·`.env.example`을 **최종 형태로 정리**하고, 그 형태가 보안 규칙을 지키는지 **자동 테스트로 고정**한 뒤, **빈 볼륨에서 문서대로 처음부터 띄워 채팅 1회까지 되는지** 사용자가 직접 확인한다. 그리고 README "시작하기"·상태 줄과 CLAUDE.md "명령어" 절을 최종으로 쓴다.

| 목표 | 무엇으로 확인 | 요구사항 |
|---|---|---|
| 자체 이미지 4개(api·tour-tools·ingest·web) 비루트·`cap_drop: [ALL]`·`no-new-privileges`, docker.sock 미마운트 | `test_compose_hardening.py` + HITL 실측(`id -u`, `CapEff`, `NoNewPrivs`) | [A] §9, ADR-01 |
| 호스트 포트: `compose.yaml`엔 없음, 개발 덮어쓰기는 `127.0.0.1`만 | 테스트 | NFR-08, ADR-01 |
| 서비스별 `.env` 키 주입이 최종 표(§4)와 정확히 같음 | 테스트 | NFR-09 |
| `LANGSMITH_*` 키 미주입·추적 끔 | 테스트 + HITL `env` 확인 | NFR-36, ADR-26 |
| 컨테이너 8개, 네트워크 1개, 데이터는 named volume | 테스트 | NFR-20·21, ADR-01 |
| 빈 볼륨 → `compose up` → 테이블 생성 → `create-admin` → 소량 적재 → 채팅 1회 | HITL-1~6 | NFR-20·21, [PL] 26 완료 기준 |
| README 시작하기·상태·"v1.1 이후" 표기·SECURITY_GUIDE 링크, CLAUDE.md 명령어 | 문서 + HITL-8 명령어 대조 | NFR-17, D-23, X-f |

### 1.1 넣지 않는 것
| 빠지는 것 | 이유 |
|---|---|
| 외부 이미지(postgres·lightrag·nginx·cloudflared)에 `cap_drop`·비루트 강제 | [A] §9는 자체 이미지만 정함. nginx·postgres 공식 이미지는 root로 시작해 권한을 내리는 구조라 `cap_drop: [ALL]`이면 못 뜬다(§13 Q3) |
| Rocky Linux·Windows Docker Desktop 실제 이식 시험 | NFR-21은 "이식 가능" 설계 요건. 이번엔 WSL2에서만 확인하고, 막을 수 있는 것(호스트 전용 경로·`network_mode: host` 없음, 볼륨 이름 고정 없음)만 테스트로 막는다. 실제 이식은 **미확인**으로 README에 적음 |
| E2E 시나리오(NFR-71 전체) | Phase 6 |
| `dev`→`prod` 병합·`v1.0` 태그 | Phase 6 뒤, 사용자 승인 후 |
| 컨테이너 이미지 취약점 스캔·SBOM | 요구사항 없음 |
| 새 서비스·새 기능 | 없음. 코드 변경은 §13 결정에 따른 한두 줄뿐 |

---

## 2. 생성·수정 파일

| 파일 | 신규/수정 | 역할 |
|---|---|---|
| `backend/tests/test_compose_hardening.py` | 신규 | compose·`.env.example`·Dockerfile을 읽어 §6 검사. 검사 함수 + 실제 파일 검사 + 일부러 틀린 예로 검사 함수 자체 확인 |
| `compose.yaml` | 수정(최종) | §3 표대로 정리 — 빠진 보안 설정·`restart`·주석 보강, §13 결정 반영(lightrag healthcheck, postgres healthcheck TCP, 설정값 공유 앵커 등). 동작을 바꾸는 변경은 §13 결정분만 |
| `compose.dev.yaml` | 수정(최종) | §3.3 — 포트가 모두 `127.0.0.1`인지, 보안 설정을 덮어쓰지 않는지 정리만 |
| `.env.example` | 수정(최종) | §5 — 16개 키, 사용처·생성 방법 주석을 최종 사용처에 맞게 고침 |
| `README.md` | 수정 | §8 — 상태 줄, "시작하기"(실제 명령), "레포 구조 (계획)" → 실제, 스택 표 버전 동기화, "MVP" 표기 없음 확인 |
| `CLAUDE.md` | 수정 | §9 — "명령어" 절을 묶음별로 최종 정리(01·03·14·18·20·21·22·23·24가 덧붙인 줄을 합치고 중복 제거) |
| `docs/harness/architecture.md` | 수정(문서 정리, §13 Q8) | §9 비밀값 표(Tavily → api·ingest, postgres 행 풀어 쓰기), §2 cloudflared 행(`--token` → `TUNNEL_TOKEN`), ADR-01 개발 포트 문구 |
| `docs/harness/PROGRESS.md` | 수정 | 26 완료·G5 기록, 결정 로그 |
| `.gitattributes` | 신규(§13 Q7 결정 시) | `*.sh text eol=lf` — Windows에서 받아도 `01-init.sh` 줄바꿈이 깨지지 않게 |

> [PL] 파일 목록 밖: `architecture.md`·`PROGRESS.md`(문서 불일치 정리), `.gitattributes`(Q7), 그리고 §13 결정에 따라 21 `scheduler`/`daily_sync`의 따라잡기 조건 한 줄(Q1). 결정 전에는 만들지 않는다.

---

## 3. compose 최종 형태

### 3.1 서비스 8개 (`compose.yaml`, `name: nadri`, 네트워크는 기본 1개)

| 서비스 | 이미지/빌드 | `user` | 보안 설정 | 볼륨 | `depends_on` | healthcheck | `restart` | 처음 넣은 작업 |
|---|---|---|---|---|---|---|---|---|
| `postgres` | `pgvector/pgvector:pg18` | (이미지 기본) | — | `pg-data`, `./infra/postgres/init:/docker-entrypoint-initdb.d:ro` | — | `pg_isready` (**Q4**: `-h 127.0.0.1` 추가 추천) | `unless-stopped` | 01 |
| `lightrag` | LightRAG `v1.5.7` 고정(주소 **미확인**, 01) | (이미지 기본) | — | `lightrag-data:<작업 디렉터리>`, `env_file: infra/lightrag/lightrag.env` | `postgres: service_healthy` | 없음 → **Q2**: 추가 추천 | `unless-stopped` | 01 |
| `ingest` | `build: {context: ./backend, target: app}` | `"10001:10001"` | `cap_drop: [ALL]`, `security_opt: ["no-new-privileges:true"]` | `wiki-data:/data/wiki`, `raw-data:/data/raw`, `./eval:/app/eval:ro`, `./eval/results:/app/eval/results` | `postgres: service_healthy` | 준비 파일 `/tmp/nadri-ingest-ready`(21) | `unless-stopped`(21) | 01·20·21·22·24 |
| `tour-tools` | `build: {context: ./backend, target: tools}` | `"10001:10001"` | 같음 | 없음 | `postgres: service_healthy`, `lightrag: service_started`(Q2 채택 시 `service_healthy`), `ingest: service_healthy`(21) | `GET /health` | `unless-stopped` | 01·10·24 |
| `api` | `build: {context: ./backend, target: app}`, `uvicorn nadri.api.main:app` | `"10001:10001"` | 같음 | 없음 | `postgres: service_healthy`, `ingest: service_healthy`(21), `tour-tools`(시작만, 02) | `GET /api/health` | `unless-stopped` | 02·05·06·17·24 |
| `web` | `build: {context: ./web, target: runner}` | `"1000:1000"` | 같음 | 없음 | — | `manifest.webmanifest` fetch(14) | `unless-stopped` | 14 |
| `nginx` | `nginx:<stable-alpine 태그 고정>` | (이미지 기본) | — | `./infra/nginx/nginx.conf:/etc/nginx/conf.d/default.conf:ro` | `api`, `web` | 없음 | `unless-stopped` | 02·14 |
| `cloudflared` | `cloudflare/cloudflared:<태그 고정>`, `command: tunnel --no-autoupdate run` | (이미지 기본) | — | 없음 | `nginx` | 없음 | `unless-stopped`(05) | 02·05 |

- 모든 서비스: 호스트 `ports` 없음, `privileged`·`cap_add`·`network_mode`·`pid`·`ipc` 없음, docker.sock 마운트 없음.
- 외부 이미지는 **태그 고정**(`latest`·태그 없음 금지 — 같은 compose로 다시 띄워도 같은 결과, NFR-21).
- `cloudflared`에 `profiles` 없음(05가 제거). 토큰은 `environment: TUNNEL_TOKEN: ${CLOUDFLARE_TUNNEL_TOKEN}`(02-Q5 — 명령 인자 아님).
- 자체 이미지의 `user` uid는 Dockerfile 사용자와 같다(backend `nadri` 10001, web `node` 1000). compose에도 명시해 이미지가 바뀌어도 root로 돌지 않게 한다(§6 C-03).
- `ingest` 기본 명령: `sh -c "alembic upgrade head && exec nadri ingest scheduler"`(21). `docker compose run --rm ingest nadri …`는 명령을 덮어써 1회 실행.

### 3.2 볼륨
- top-level `volumes:` = `pg-data`, `lightrag-data`, `wiki-data`, `raw-data` 4개. **`name:`·`external:` 없음** — 프로젝트 이름(`-p`)이 접두어로 붙어야 HITL의 클린 기동(`-p nadri-clean`)이 기존 데이터와 섞이지 않는다.
- 바인드 마운트는 아래만 허용(그 밖은 테스트 실패):

| 서비스 | 호스트 경로 | 읽기 전용 |
|---|---|---|
| postgres | `./infra/postgres/init` | ✓ |
| nginx | `./infra/nginx/nginx.conf` | ✓ |
| ingest | `./eval` | ✓ |
| ingest | `./eval/results` | ✗ (결과 파일만 — 22-Q8) |

- `wiki-data`·`raw-data`는 ingest만 마운트([A] §7).

### 3.3 `compose.dev.yaml` (개발 덮어쓰기)
| 서비스 | 바꾸는 것 | 처음 넣은 작업 |
|---|---|---|
| nginx | `ports: ["127.0.0.1:8080:80"]` | 02 (02-Q9) |
| postgres | `ports: ["127.0.0.1:5432:5432"]` | 01 (통합 테스트용) |
| lightrag | `ports: ["127.0.0.1:9621:9621"]` | 01 |
| tour-tools | `ports: ["127.0.0.1:8001:8000"]`, 소스 마운트, `--reload` | 01 |
| ingest | 소스·alembic 마운트 | 01 |
| api | 소스 마운트, `--reload` | 02 |
| web | `build.target: dev`, `next dev`, `./web:/app` | 14 (14-Q3) |

- 규칙: 포트는 **전부 `127.0.0.1` 바인드**. `user`·`cap_add`·`privileged`·`security_opt`를 덮어쓰지 않는다. 바인드는 `./backend/…`·`./web` 소스만 추가.
- [A] ADR-01은 "개발 덮어쓰기에서만 nginx 127.0.0.1"이라 적었지만 01이 통합 테스트용 포트 3개를 더 열었다 — §10 I-6, Q6.

### 3.4 조정 설정값 공용 블록 `x-tuning` (22-Q11 + 24-Q2)
22 HITL에서 사용자가 정한 조정값은 compose `environment`에 값 + 근거 결과 파일 이름 주석으로 둔다(22-Q11). 24-Q2는 이 값을 **한 곳(`x-tuning`)에 적고 api·tour-tools·ingest 세 서비스에 같은 값으로** 넣자고 정했다 — ingest의 개선안 에이전트가 "지금 설정" 스냅샷을 만들고(24 §3.3), 평가(22 골든·23 공격 세트·24 매일 평가)가 운영(api·tour-tools)과 같은 설정을 재야 하기 때문이다. 26은 24 이름·범위로 통일한다(Q5).

```yaml
x-tuning: &tuning          # 22 HITL 결정값 — 근거: eval/results/<결과 파일 이름>
  VERIFY_MAX_REWRITES: "2"
  FAQ_CACHE_THRESHOLD: "0.95"
  RAG_RERANK_ENABLED: "true"
  RAG_QUERY_MODE: "mix"
  RAG_CANDIDATES: "30"
  RAG_TOP_K: "5"
services:
  api:        { environment: { <<: *tuning, ... } }
  tour-tools: { environment: { <<: *tuning, ... } }
  ingest:     { environment: { <<: *tuning, ... } }
```
| 값 | 실제로 쓰는 곳 | 세 서비스 모두 받는 이유 |
|---|---|---|
| `VERIFY_MAX_REWRITES`·`FAQ_CACHE_THRESHOLD` | api(채팅), ingest(평가 그래프·스냅샷) | 평가 = 운영 설정, 개선안 스냅샷 |
| `RAG_RERANK_ENABLED`·`RAG_QUERY_MODE`·`RAG_CANDIDATES`·`RAG_TOP_K` | tour-tools(`rag_query`), ingest(스냅샷) | 개선안 스냅샷이 실제 검색 설정을 봄 |

- 비밀값이 아니므로 §4 `.env` 키 표(C-12) 대상이 아니다(24 §12-5). 대신 C-27이 "세 서비스가 같은 `x-tuning`을 쓰고 서로 다른 값으로 덮어쓰지 않음"을 검사한다.
- 22 HITL 결정 전이면 블록에 코드 기본값과 같은 값을 둔다(동작 같음) — 값 위치를 미리 고정해 두기 위해.

---

## 4. 서비스별 `.env` 키 주입 — 최종 표

판정 기준: 서비스 정의 안 문자열에 들어 있는 `${키}` 참조 중 `.env.example`에 있는 키. 컨테이너 안 이름이 달라도(예: `DB_PASSWORD=${APP_DB_PASSWORD}`, `LLM_BINDING_API_KEY=${OPENAI_API_KEY}`, `TUNNEL_TOKEN=${CLOUDFLARE_TUNNEL_TOKEN}`) **어느 `.env` 키를 받는지**로 본다.

| `.env` 키 | postgres | lightrag | ingest | tour-tools | api | web | nginx | cloudflared | 근거 작업 |
|---|---|---|---|---|---|---|---|---|---|
| `OPENAI_API_KEY` | | ✓ | ✓ | | ✓ | | | | 01(lightrag)·02(api)·20(ingest) |
| `TOURAPI_SERVICE_KEY` | | | ✓ | ✓ | | | | | 01·10 |
| `TAVILY_API_KEY` | | | ✓ | | ✓ | | | | 02·22(22-Q8) |
| `LIGHTRAG_API_KEY` | | ✓ | ✓ | ✓ | | | | | 01 |
| `TOOLS_API_KEY` | | | ✓ | ✓ | ✓ | | | | 01·02 |
| `POSTGRES_PASSWORD` | ✓ | | | | | | | | 01 |
| `APP_DB_PASSWORD` | ✓ | | ✓ | | ✓ | | | | 01·05 |
| `TOOLS_DB_PASSWORD` | ✓ | | | ✓ | | | | | 01 |
| `LIGHTRAG_DB_PASSWORD` | ✓ | ✓ | | | | | | | 01 |
| `SESSION_SECRET` | | | | | ✓ | | | | 05 |
| `SMTP_USER`·`SMTP_APP_PASSWORD`·`MAIL_FROM` | | | | | ✓ | | | | 06 |
| `ELEVENLABS_API_KEY`·`ELEVENLABS_VOICE_ID` | | | | | ✓ | | | | 17 |
| `CLOUDFLARE_TUNNEL_TOKEN` | | | | | | | | ✓ | 02·05 |

추적 끔(비밀 아님, 값 고정 문자열 `"false"`): `LANGSMITH_TRACING`, `LANGCHAIN_TRACING_V2` → **api·ingest**([A] §9). 그 밖의 `LANGSMITH_*`·`LANGCHAIN_*` 키(예: `LANGSMITH_API_KEY`, `LANGCHAIN_API_KEY`, `LANGSMITH_ENDPOINT`, `LANGSMITH_PROJECT`)는 **어느 서비스에도, `.env.example`에도 없다**.

[A] §9 표와 다른 점(§10에서 자세히):
1. `TAVILY_API_KEY` — [A] "api"만 → 최종 **api·ingest**(22-Q8 평가 실행).
2. DB 비밀번호 행 — [A] "postgres / api·ingest / tour-tools / lightrag"는 키마다 한 서비스처럼 읽히지만, postgres는 `01-init.sh`가 롤을 만들려고 **4개 모두** 받는다(G4 Q8).
3. ingest의 `OPENAI_API_KEY`는 [A]에 이미 있음 — 01은 일부러 빼고 20에서 넣음(최종은 [A]와 같음).

---

## 5. `.env.example` 최종 (키 16개, 값은 모두 비움)

```
# ── 필수 ──────────────────────────────────────────────
# OpenAI — 답변·검증·분류·요약(api), 허브·평가(ingest), LightRAG 인덱싱·질의(lightrag)
OPENAI_API_KEY=
# 공공데이터포털 TourAPI(KorService2) 인증키 — "Decoding" 키 (적재: ingest, 실시간 조회: tour-tools)
TOURAPI_SERVICE_KEY=
# Tavily 웹 검색 — 답변(api)·평가(ingest)
TAVILY_API_KEY=
# 내부 토큰 — 각각 openssl rand -hex 32 로 생성
LIGHTRAG_API_KEY=
TOOLS_API_KEY=
# 로그인 세션·CSRF 서명 키 — openssl rand -hex 32 (32자 이상)
SESSION_SECRET=
# PostgreSQL 비밀번호 — 각각 openssl rand -hex 24. 빈 볼륨 첫 기동 때만 적용된다(나중에 바꾸려면 README 참고)
POSTGRES_PASSWORD=
APP_DB_PASSWORD=
TOOLS_DB_PASSWORD=
LIGHTRAG_DB_PASSWORD=
# ── 외부 접속 (없으면 localhost 개발 모드로만 사용) ──────
# Cloudflare Named Tunnel 토큰
CLOUDFLARE_TUNNEL_TOKEN=
# ── 선택 (없으면 해당 기능만 꺼짐) ─────────────────────
# Gmail 발신 — "앱 비밀번호" 16자, 공백 없이. 없으면 비밀번호 재설정 메일이 안 감
SMTP_USER=
SMTP_APP_PASSWORD=
# 보낸 사람 표시(선택) — 예: nadri <me@gmail.com>
MAIL_FROM=
# ElevenLabs TTS — 없으면 음성 읽기가 꺼짐
ELEVENLABS_API_KEY=
ELEVENLABS_VOICE_ID=
```
- 주석 문구는 01·05·06·17이 쓴 것을 최종 사용처에 맞게 고친 것(01의 "OpenAI — LightRAG 인덱싱·질의"는 이제 api·ingest도 씀).
- 기본값이 있는 조정값(`SSE_PING_S`·`MODERATION_TIMEOUT_S` 등 02 HITL에서 셸 변수로 바꾸는 것, `STT_PROVIDER`·`TTS_PROVIDER`)은 `.env.example`에 넣지 않는다 — compose에 `${이름:-기본값}`으로만 있다(있는 경우).

---

## 6. `backend/tests/test_compose_hardening.py`

### 6.1 구조
- 실행: `cd ~/code/myAgent/backend && uv run pytest tests/test_compose_hardening.py`. Docker·네트워크·DB 없이 파일만 읽는다(결정적). 단 C-20(`docker compose config`)만 Docker CLI가 있을 때 실행, 없으면 skip.
- 읽는 파일: 레포 루트(`Path(__file__).resolve().parents[2]`)의 `compose.yaml`, `compose.dev.yaml`, `.env.example`, `.gitignore`, `infra/lightrag/lightrag.env`, `infra/postgres/init/*.sh`, `backend/Dockerfile`, `web/Dockerfile`.
- YAML은 `yaml.safe_load`(01 dev 그룹 `pyyaml`). `<<` 병합 키도 풀린다.
- 검사는 **함수**로 만들고(`check_*(…) -> list[str]`, 위반 메시지 목록, 빈 목록 = 통과), 테스트는 ① 실제 파일에 대해 `== []` ② 일부러 틀린 작은 dict에 대해 기대 메시지가 나오는지(test.md) 두 방향으로 부른다. 검사 함수는 이 테스트 파일 안에만 둔다(한 번만 쓰는 코드 — 별도 모듈 안 만듦).
- 위반 메시지는 한국어, `서비스명: 무엇이 틀렸나 (기대: …)` 형식. 실패 시 무엇을 고칠지 바로 보이게.

### 6.2 상수 (최종 표를 코드로 고정)
```python
SERVICES = {"postgres", "lightrag", "ingest", "tour-tools", "api", "web", "nginx", "cloudflared"}  # ADR-01
SELF_BUILT = {"ingest", "tour-tools", "api", "web"}            # build 키가 있는 서비스와 같아야 함
EXPECTED_ENV_KEYS: dict[str, set[str]] = { ... }               # §4 표 그대로
TRACING_OFF = {"api", "ingest"}                                # LANGSMITH_TRACING / LANGCHAIN_TRACING_V2 = "false"
TUNING_KEYS = {"VERIFY_MAX_REWRITES", "FAQ_CACHE_THRESHOLD", "RAG_RERANK_ENABLED",
               "RAG_QUERY_MODE", "RAG_CANDIDATES", "RAG_TOP_K"}   # 24 §3.3
TUNING_SERVICES = {"api", "tour-tools", "ingest"}                # 24-Q2
ALLOWED_BINDS: dict[str, dict[str, bool]] = {                  # 서비스 → {호스트 경로: 읽기전용 필수?}
    "postgres": {"./infra/postgres/init": True}, "nginx": {"./infra/nginx/nginx.conf": True},
    "ingest": {"./eval": True, "./eval/results": False}}
NAMED_VOLUMES = {"pg-data", "lightrag-data", "wiki-data", "raw-data"}
ALLOWED_ENV_FILES = {"infra/lightrag/lightrag.env"}
SECRET_NAME = re.compile(r"(KEY|SECRET|PASSWORD|TOKEN)$")
REF = re.compile(r"\$\{([A-Z0-9_]+)(:?[-?+][^}]*)?\}")      # ${X}, ${X:-기본}, ${X:?메시지}
```

### 6.3 도우미 함수
```python
def load_yaml(path: Path) -> dict:
    """compose 파일을 읽는다. 파일이 없으면 FileNotFoundError(테스트 실패로 보임)."""
def env_of(svc: dict) -> dict[str, str]:
    """environment를 {이름: 값 문자열}로 바꾼다. 목록형("K=V")·사전형 모두. 값이 bool이면 ValueError
    (compose는 bool을 거부함 — "false"처럼 따옴표 필요)."""
def refs_in(obj) -> list[tuple[str, str | None]]:
    """dict·list·str을 재귀로 훑어 ${이름…} 참조를 (이름, 기본값 표기 또는 None)으로 모은다."""
def env_example_keys(path: Path) -> dict[str, str]:
    """.env.example의 KEY=값 줄을 읽는다(주석·빈 줄 무시). 중복 키면 ValueError."""
def bind_mounts(svc: dict) -> list[tuple[str, str, bool]]:
    """volumes 중 호스트 경로(./ 또는 / 로 시작)인 것만 (호스트, 컨테이너, 읽기전용) 목록. 짧은·긴 문법 모두."""
def final_user(dockerfile: Path, target: str) -> str | None:
    """Dockerfile에서 target 단계의 마지막 USER를 찾는다. 그 단계에 없으면 FROM 부모 단계로 거슬러 올라간다.
    끝까지 없으면 None(= root)."""
```

### 6.4 검사 항목
| ID | 검사 | 대상 | 근거 |
|---|---|---|---|
| C-01 | 서비스 이름 집합 == `SERVICES`(8개), top-level `networks` 없음(또는 `default`만) | compose.yaml | ADR-01 |
| C-02 | `build` 있는 서비스 집합 == `SELF_BUILT` | compose.yaml | 새 자체 이미지가 생기면 이 테스트가 알려 줌 |
| C-03 | 자체 이미지: `user`가 있고 uid가 `0`·`root`가 아님 | compose.yaml | [A] §9 |
| C-04 | 자체 이미지: Dockerfile 해당 target의 최종 USER가 있고 root·0이 아님 (`backend/Dockerfile` app·tools, `web/Dockerfile` runner) | Dockerfile | [A] §9 |
| C-05 | 자체 이미지: `cap_drop == ["ALL"]` | compose.yaml | [A] §9 |
| C-06 | 자체 이미지: `security_opt`에 `no-new-privileges:true`(또는 `no-new-privileges`) | compose.yaml | [A] §9 |
| C-07 | **모든** 서비스: 어떤 볼륨에도 `docker.sock`·`/var/run/docker` 없음 | 두 파일 | [A] §9 |
| C-08 | 모든 서비스: `privileged`·`cap_add`·`network_mode`·`pid`·`ipc`·`devices` 없음 | 두 파일 | 최소 권한 |
| C-09 | compose.yaml: 어떤 서비스에도 `ports` 없음(nginx 포함 — 외부 진입은 cloudflared) | compose.yaml | NFR-08, ADR-01 |
| C-10 | compose.dev.yaml: 모든 `ports`가 `127.0.0.1:`로 시작(긴 문법이면 `host_ip == "127.0.0.1"`), nginx는 `127.0.0.1:8080:80` | dev | 02-Q9, Q6 |
| C-11 | compose.dev.yaml: `user`·`security_opt`·`cap_drop`을 덮어쓰지 않음 | dev | 보안 설정 유지 |
| C-12 | 서비스별 `.env` 키 참조 집합 == `EXPECTED_ENV_KEYS[서비스]`(§4) — 모자람·넘침 모두 메시지 | compose.yaml | NFR-09, [A] §9 |
| C-13 | 비밀값 이름(`SECRET_NAME`) 환경변수는 값이 정확히 `${키}` 하나(글자 그대로 값·기본값 `:-` 금지) | compose.yaml | NFR-09 |
| C-14 | `.env` 키 참조는 `environment` 안에만(명령·healthcheck·labels에 `${비밀키}` 금지 — `ps`에 보임) | compose.yaml | 02-Q5 |
| C-15 | `env_file`은 `ALLOWED_ENV_FILES`만(`.env` 직접 지정 금지), 그 파일에 `SECRET_NAME` 키가 없음 | compose.yaml, lightrag.env | NFR-09 |
| C-16 | `LANGSMITH_*`·`LANGCHAIN_*`: `TRACING_OFF` 서비스는 `LANGSMITH_TRACING == "false"`·`LANGCHAIN_TRACING_V2 == "false"`(대소문자 무시), 그 밖의 이름은 어느 서비스에도 없음, `${LANGSMITH_…}`·`${LANGCHAIN_…}` 참조 없음, `.env.example`에도 없음 | compose.yaml, .env.example | NFR-36, ADR-26 |
| C-17 | `.env.example`: 키 집합 == §4 표의 16개, 모든 값이 비어 있음, 모든 키가 어느 서비스에서든 참조됨, compose의 **기본값 없는** `${키}`는 모두 `.env.example`에 있음 | 두 파일 | NFR-09, 문서 최신 |
| C-18 | `.gitignore`에 `.env` 줄, `git ls-files .env` 결과 비어 있음(git 없으면 앞 절반만) | .gitignore | NFR-09 |
| C-19 | 볼륨: top-level이 `NAMED_VOLUMES`와 같고 `name`·`external` 없음 / 바인드는 `ALLOWED_BINDS`만, 읽기 전용 필수 항목은 `:ro` / `wiki-data`·`raw-data`는 ingest만 | compose.yaml | NFR-21, [A] §7 |
| C-20 | (Docker CLI 있을 때) `docker compose -f compose.yaml -f compose.dev.yaml --env-file .env.example config -q` 종료 코드 0, 그리고 `-f compose.yaml … config --format json` 결과(병합·앵커 반영)에서도 C-09·C-05가 통과 | 두 파일 | 문법·병합 결과 확인 |
| C-21 | 기동 순서: 어떤 `depends_on`에도 `service_completed_successfully` 없음, `api`·`tour-tools`는 `ingest: service_healthy`, `ingest`는 healthcheck 있음·명령에 `alembic upgrade head`와 `nadri ingest scheduler` | compose.yaml | 21-Q4 |
| C-22 | `restart: unless-stopped` — 8개 모두 | compose.yaml | 21, 05 |
| C-23 | healthcheck 있음: postgres·ingest·tour-tools·api·web (+Q2 채택 시 lightrag) | compose.yaml | 클린 기동 순서 |
| C-24 | 외부 이미지(`image`만 있는 서비스) 태그 고정: `:` 뒤 태그가 있고 `latest`가 아님 | compose.yaml | NFR-21 |
| C-25 | cloudflared: `environment.TUNNEL_TOKEN == "${CLOUDFLARE_TUNNEL_TOKEN}"`, `command`에 `--token` 없음, `profiles` 없음 | compose.yaml | 02-Q5, 05 |
| C-27 | `x-tuning`(24-Q2): compose.yaml 원문에 top-level `x-tuning` 앵커가 있고 `TUNING_SERVICES` 세 서비스의 `environment`가 모두 `<<: *tuning`으로 합침(원문 텍스트 확인), 병합 결과에서 `TUNING_KEYS` 6개 값이 세 서비스 모두 같음, 다른 서비스(web·nginx 등)에는 없음, 값은 따옴표 문자열 | compose.yaml | 22-Q11, 24-Q2 |
| C-26 | (Q7 채택 시) `infra/**/*.sh`에 `\r` 없음, `.gitattributes`에 `*.sh text eol=lf` | 파일 | NFR-21 |

- 01·05·21·22가 "compose 검사 테스트가 있으면 기대값 수정"이라 적은 대상은 이 파일이다. 26 전에는 compose를 고정 비교하는 테스트가 없다(각 spec 확인).

---

## 7. 클린 기동 절차 (README "시작하기"와 같은 순서 — HITL 정본은 test.md ②)

목적: 사용자의 개발 데이터(며칠 걸린 적재)를 **건드리지 않고**, 새 프로젝트 이름으로 빈 볼륨에서 처음부터 띄운다.

1. **기존 환경 멈춤**(삭제 아님): `docker compose stop`. 이유 — 같은 터널 토큰으로 커넥터가 둘 뜨면 Cloudflare가 요청을 둘에 나눠 보낸다(**미확인**: 공식 문서상 같은 터널의 복수 커넥터는 부하 분산으로 동작), 개발 포트 충돌, 스케줄러 2개가 같은 TourAPI 키를 씀.
2. **클린 프로젝트 기동**: `docker compose -p nadri-clean up -d --build` (운영 형태 `compose.yaml`만 — README 기본 경로). `-p`가 `name: nadri`보다 우선해 볼륨이 `nadri-clean_pg-data` 등으로 새로 생긴다.
3. **기동 확인**: `docker compose -p nadri-clean ps`에서 postgres·ingest·tour-tools·api·web `healthy`, 나머지 `running`. ingest 로그 `scheduler started`.
4. **테이블 생성 확인**: `nadri` DB 테이블 18개 + `alembic_version`, 롤 3개, DB 2개(`nadri`·`lightrag`), `vector` 확장.
5. **관리자 생성**: `docker compose -p nadri-clean run --rm api nadri create-admin --username admin --email <이메일>`.
6. **소량 적재**: `docker compose -p nadri-clean run --rm ingest nadri ingest bootstrap --area 서울 --type 12 --max-items 30` → `ingest status`.
   - [PL]은 `--limit`이라 적었지만 03이 `--max-items`로 바꿨다(§10 I-1).
   - 21의 따라잡기(21-Q2)가 먼저 돌고 있으면 잠금 키 1 때문에 종료 코드 4 → 로그에서 `daily_sync done`을 본 뒤 다시. 그리고 **Q1을 정하지 않으면** 빈 DB에서 따라잡기가 전체 초기 적재를 스스로 시작한다(§10 I-11).
   - 기동 시각이 03:00 KST 이후면 24 놓친 실행(24-Q10)도 바로 돈다 — 어제 보고서 행이 없으므로 `daily_quality`가 대화 0건으로 **공격 세트만 실행**하고 보고서를 `skipped`로 저장(24 §4 3)). 잠금 키 2라 적재·현행화(키 1)와 서로 막지 않는다. 적재 전이라 `rag_query` 항목은 빈 결과로 돈다(방어율 숫자는 참고만).
7. **채팅 1회**: 터널 주소에서 admin 로그인 → "경복궁 관람 시간 알려줘" → 토큰 단위 스트리밍 → `✓ 확인됨`(또는 경고) → 출처·기준일 → 사이드바 이력.
8. **정리**: `docker compose -p nadri-clean down -v`(반드시 `-p nadri-clean`) → 원래 환경 `docker compose up -d`.

- 비용(추정): TourAPI 약 90~150건(30건 × 목록+상세 3종, 01-Q9 기준 — **개발계정 하루 한도를 기존 환경과 같이 씀**), LightRAG 인덱싱 30페이지 약 $0.1~0.5(**미확인**, 01 실측으로 고침), 채팅 1회 약 $0.002, 03:00 이후 기동이면 24 놓친 실행의 공격 세트 약 $0.03~0.10(24 §17 ≈$0.03, 23 §11 ≈$0.06~0.10 — 두 추정이 다름, **미확인**).
- 터널이 없는 사용자 경로(README 대안): `docker compose -f compose.yaml -f compose.dev.yaml up -d --build --scale cloudflared=0` → `http://localhost:8080`. 토큰이 비면 cloudflared가 계속 재시작하므로 `--scale cloudflared=0`.

---

## 8. README 변경

| 위치 | 지금 | 바꿀 것 |
|---|---|---|
| 상태 줄(5~6행) | "설계 단계 (구현 전)…" | "**v1.0 구현 완료 — E2E 점검(Phase 6) 후 `v1.0` 태그 예정**" 한 줄 + PROGRESS 링크. 태그 후에는 Phase 6/릴리스 작업이 다시 고침 |
| "시작하기 (구현 후 채울 예정)" | 준비물 3개, "명령은 구현 후" | §8.1 |
| "레포 구조 (계획)" | 계획 | "(계획)" 삭제, 실제 디렉터리와 대조(`compose.dev.yaml`·`.env.example`·`eval/results/`(git 제외) 추가) |
| 기술 스택 표 | 버전 없음 | 실제 고정 버전(Node LTS 메이저·Next·Python·주요 라이브러리)과 다르면 맞춤 — 사용자 규칙 "스택 확정·변경 시 README도 갱신" |
| "MVP" 표기 | 2026-11-22 확인 시 README에 없음(이미 "v1.1 이후") | `grep -n MVP README.md TECH_STACK.md` 0건 확인만 (X-f 사실상 해결됨) |
| 보안 절 | `SECURITY_GUIDE.md` 링크 있음 | 링크 동작 확인만(NFR-17) |

### 8.1 "시작하기" 내용 (쉬운 말, 실제 명령)
1. **준비물**: WSL2 Ubuntu-22.04(또는 Linux) + Docker Engine·Compose v2 / 필수 키: TourAPI 인증키(Decoding), OpenAI 키, Tavily 키 / 외부 접속용: `.dev` 도메인 + Cloudflare Named Tunnel 토큰 / 선택: Gmail 앱 비밀번호, ElevenLabs 키·보이스 ID. 레포는 `~/` 아래(Windows `/mnt/c` 아래 금지).
2. **`.env` 만들기**: `cp .env.example .env` → 키 입력, 내부 토큰·DB 비밀번호는 `openssl rand -hex 32`. "DB 비밀번호는 처음 띄울 때만 적용" 경고.
3. **띄우기**: 터널 있음 `docker compose up -d --build` / 터널 없음 §7 대안 명령. 첫 빌드는 리랭커 모델(약 2.3GB, **미확인**) 때문에 오래 걸림.
4. **상태 확인**: `docker compose ps`(healthy 기다리기).
5. **첫 관리자**: `create-admin` 명령.
6. **관광 데이터 적재**: 소량 `--max-items 30`로 먼저 확인 → 전체 적재는 매일 01:00 작업이 이어서 함(서울·제주 전체 며칠~2주, 03-Q9) → 진행은 `ingest status`.
7. **접속**: 터널 주소 또는 `http://localhost:8080` → 로그인 → 질문.
8. **자동으로 도는 것**: 매일 01:00 현행화(+적재 이어하기)·90일 정리, 03:00 품질 평가.
9. **멈추기·지우기**: `docker compose down`(데이터 유지) / `down -v`는 **모든 데이터 삭제** 경고.
10. **문제 해결**: `docker compose logs -f <서비스>`, 다른 환경(Rocky·Docker Desktop)은 "같은 compose로 동작하도록 만들었지만 직접 확인하지 않음"(NFR-21 **미확인**).

---

## 9. CLAUDE.md "명령어" 절 최종

01·03·14·18·20·21·22·23·24가 덧붙인 줄을 아래 묶음으로 합치고, 같은 명령 중복을 지운다. 모든 명령은 HITL-8에서 실제로 한 번씩 돌려 확인한다(비용이 드는 것은 표시).

| 묶음 | 명령 (요지) |
|---|---|
| 개발 도구 준비 | `cd backend && uv sync --no-group reranker` · `cd web && npm ci && npx playwright install --with-deps chromium` |
| 백엔드 테스트 | `uv run pytest -m "not integration"` · DB 없이 `-m "not integration and not db"` · 통합 `DB_HOST=127.0.0.1 … uv run pytest -m integration` · 이 작업 `uv run pytest tests/test_compose_hardening.py` |
| 웹 테스트 | `npm run typecheck` · `npm run test` · `npm run e2e`(compose 기동 필요) · `--grep @real`(실제 API 비용) |
| 실행 | 개발 `docker compose -f compose.yaml -f compose.dev.yaml up -d --build` · 운영 `docker compose up -d --build` · 상태 `docker compose ps` · 로그 `docker compose logs -f <서비스>` |
| 계정 | `docker compose run --rm api nadri create-admin --username … --email …` · 로그인 잠금 해제 psql(05) |
| 적재·현행화 | `nadri ingest bootstrap …` · `nadri ingest status` · `docker compose exec ingest nadri ingest sync --now` · `nadri ingest hubs` · `nadri ingest lint` · 위키 git 로그(20) · `nadri tools smoke` |
| 평가 | 골든 `nadri eval golden [--rerank on|off] [--rag-mode mix|hybrid] [--verify-max 0|1|2] [--ids …] [--check|--compare FILE…|--faq-pairs]`(22) · 공격 세트 `docker compose run --rm ingest nadri eval attack [--ids …] [--type …] [--no-judge] [--no-record] [--check]`(23, 뚫려도 종료 코드 0) · 매일 평가 재실행 `docker compose exec ingest nadri eval quality --date YYYY-MM-DD [--force]`(24, 종료 코드 0/1/2/4) |
| DB 접속 | `docker compose exec postgres psql -U postgres -d nadri` |
| 클린 기동 확인 | §7 요지(`-p nadri-clean` … `down -v`) |

- "작업 환경" 절은 이미 최신(14-Q1). 바꾸지 않는다.

---

## 10. 앞 작업 spec 사이 불일치 (발견 목록)

| # | 내용 | 출처 A | 출처 B | 처리 제안 | 질문 |
|---|---|---|---|---|---|
| I-1 | 적재 옵션 이름 | [PL] 26 완료 기준 `ingest bootstrap --limit` | 03 §9.7 `--limit` 없앰 → `--max-items N` | 26 HITL·README는 `--max-items`. [PL] 문구는 그대로 두고 여기 기록 | — |
| I-2 | Tavily 키 받는 곳 | [A] §9 표 "api"만 | 22-Q8 ingest 추가 | 최종 표(§4) api·ingest, [A] §9 표 고침 | Q8 |
| I-3 | DB 비밀번호 행 | [A] §9 "postgres / api·ingest / tour-tools / lightrag" | 01 §5.2 postgres가 4개 모두 받음(`01-init.sh`) | 테스트는 01 기준, [A] 표를 풀어 씀 | Q8 |
| I-4 | 터널 토큰 전달 | [A] §2 표 `tunnel run --token` | 02-Q5 환경변수 `TUNNEL_TOKEN` | 02 기준(C-25), [A] §2 행 고침 | Q8 |
| I-5 | ingest 수명·기동 순서 | 01 `restart: "no"`·one-shot, 01·05 `service_completed_successfully` | 21-Q4 상주·`service_healthy` | 21 기준(C-21·C-22) — 이미 결정됨, 확인만 | — |
| I-6 | 개발 포트 | [A] ADR-01 "개발 덮어쓰기에서만 nginx 127.0.0.1" | 01 §5.3 postgres·lightrag·tour-tools도 `127.0.0.1` 포트(통합 테스트용) | "모두 127.0.0.1"로 허용, ADR-01 문구 고침 | Q6 |
| I-7 | 조정 설정값 위치 | 22-Q11 "compose `environment`에"(서비스 미지정), 26 초안 `x-agent-settings`(api·ingest, `VERIFY_MAX_REWRITES`만) | 24-Q2 `x-tuning`(6개 값, api·tour-tools·ingest) | 24 이름·범위로 통일(§3.4), C-27 | Q5 |
| I-8 | lightrag 준비 확인 | 01 lightrag healthcheck 없음, tour-tools `service_started` | 클린 기동 직후 `ingest bootstrap`이 LightRAG 준비 전에 인덱싱하면 실패 가능(**미확인**: 01 인덱서 재시도 여부) | healthcheck 추가 + tour-tools `service_healthy` | Q2 |
| I-9 | postgres healthcheck | 01 `pg_isready -U postgres`(소켓) | 빈 볼륨 첫 기동 때 공식 이미지는 init 스크립트를 임시 서버(TCP 안 엶)로 돌려, 소켓 검사는 init 도중에도 통과할 수 있음 → lightrag·ingest가 너무 일찍 붙음(**미확인**: pgvector pg18 이미지도 같은 entrypoint) | `pg_isready -h 127.0.0.1 -U postgres -d nadri` | Q4 |
| I-10 | 터널 없는 사용자 | 05 cloudflared 프로필 제거(항상 기동) | 토큰이 비면 cloudflared 재시작 반복 | README에 `--scale cloudflared=0` 안내(compose 변경 없음) | — |
| I-11 | 빈 DB에서 스케줄러가 기동 즉시 도는 일 | [A] §3.3 "초기 적재: CLI", 21 §6.3 "이어하기" | ① 21 조건 "`bootstrap:completed_at` 없으면 `run_bootstrap`" — 한 번도 안 시작한 빈 DB도 해당, 21-Q2 따라잡기로 **기동 즉시** 전체 적재(예산 800·인덱싱 비용) 시작 → §7 6단계와 잠금 충돌 ② 24-Q10 따라잡기 — 03:00 이후 기동이면 어제 보고서가 없어 공격 세트만 1회(약 $0.03~0.10, 키 2라 충돌 없음) | ①은 21 조건에 "`ingest_runs`에 kind='bootstrap' 행이 있을 때만" 추가, ②는 그대로(설치 직후 공격 세트 확인이 되어 오히려 유용, 비용 작음) | Q1 |
| I-12 | 23~25 확정본 대조(2026-11-22) | 26 초안 "23~25 미확인" | 23: compose 변경 없음·Tavily 안 씀 / 24: `x-tuning`(I-7)·스케줄러 작업·키 2(코드만)·`./eval`은 22 것 / 25: 변경 없음 | §3·§4 표 그대로(새 `.env` 키 없음), §3.4·§9·§7만 고침. ingest의 `TAVILY_API_KEY`는 22 골든 실행만을 위해 남음(23·24는 가짜 웹 툴) | — |
| I-13 | 02 HITL 문구 | 02 test.md "`config --services`에 cloudflared 없어야 함(프로필)" | 05 프로필 제거 | 지난 작업 기록이라 고치지 않음(참고만) | — |
| I-14 | `.env.example` 주석 | 01 "OpenAI — LightRAG 인덱싱·질의" | 02·20·22로 api·ingest도 사용 | §5로 고침 | — |
| I-15 | Windows 줄바꿈 | NFR-21 Docker Desktop 이식 | `01-init.sh`가 CRLF로 받아지면 postgres 초기화 실패(git `core.autocrlf=true` 기본인 Windows) | `.gitattributes` | Q7 |

---

## 11. 엣지케이스

| 상황 | 동작 |
|---|---|
| 테스트 실행 시 `compose.dev.yaml` 없음 | C-10·C-11 실패("파일이 없어요") — 01이 만들므로 있어야 정상 |
| environment 값이 YAML bool(`false`) | `env_of`가 ValueError → 테스트 실패 메시지 "따옴표로 감싸세요" |
| 비밀값 이름이 아닌데 `.env` 키를 참조(예: `MAIL_FROM`) | C-12 표대로 판정(C-13은 이름 패턴만) |
| `${X:?메시지}` 형식 | 참조로 인정, 기본값 없음으로 취급(C-17) |
| 앵커 `<<:`로 environment 합침 | safe_load가 풀어 줌. C-20이 compose 실제 병합 결과로 한 번 더 확인 |
| Docker CLI 없음(순수 CI 등) | C-20 skip(사유 표시), 나머지는 실행 |
| git 없음 | C-18의 `git ls-files` 부분 skip |
| 클린 기동 중 TourAPI 한도(22) | 적재가 그날 중단 — 다음 날 다시 또는 기존 환경 오늘 사용량이 적을 때 실행(HITL 전제) |
| `down -v`에서 `-p` 빠뜨림 | **기존 데이터 삭제** — HITL 절차에서 명령을 복사해 쓰도록 굵게 경고, 시작 전 `docker volume ls | grep nadri`로 두 이름을 확인 |
| 빌드 중 리랭커 가중치 내려받기 실패 | 01 Dockerfile 동작(빌드 실패) — 다시 빌드 |

---

## 12. 완료 기준 (DoD)

1. test.md ① 전부 통과(`uv run pytest tests/test_compose_hardening.py`, 전체 `uv run pytest -m "not integration"`·`npm run test`도 실패 0).
2. `compose.yaml`·`compose.dev.yaml`·`.env.example`이 §3~§5와 같다(§13 결정 반영).
3. HITL-1~7(클린 기동 → 채팅 1회 → 보안 실측) 통과, 결과표 채움.
4. README 상태·시작하기·레포 구조·스택 표 갱신, "MVP" 0건, SECURITY_GUIDE 링크 동작. 사용자가 README 시작하기만 보고 HITL을 따라 했을 때 막힌 곳이 없음(있으면 고침).
5. CLAUDE.md 명령어 절 최종, HITL-8 명령어 대조 통과.
6. §10 불일치 처리 결과를 `PROGRESS.md` 결정 로그에 기록, [A] 문서 정리(Q8 결정대로).
7. 한국어 docstring·단계 주석([CL]). 커밋 `feat/26-release-readiness`, `[Feat] …`/`[Docs] …` + 작업 목록 + `Author:`, AI 공동작성 표기 없음. `dev` 병합은 G5 후. 그 뒤 Phase 6(E2E 설계).

---

## 13. 확인 질문

| # | 질문 | 선택지 | 추천안 |
|---|---|---|---|
| 26-Q1 | 빈 DB에서 ingest가 뜨자마자 놓친 실행 두 개가 돈다(I-11). ① 21 `daily_sync`가 **전체 초기 적재를 스스로 시작**(조건이 "완료 기록 없음"이라 한 번도 시작 안 한 경우 포함) — 잠금 충돌·TourAPI 800건·인덱싱 비용 ② 24 `daily_quality`(03:00 이후 기동 시)가 대화 0건으로 **공격 세트만** 실행 — 약 $0.03~0.10 | A: **①은 21 조건을 "초기 적재를 한 번이라도 시작했고(`ingest_runs` kind='bootstrap' 있음) 아직 안 끝났을 때만 이어하기"로 고침**(21 spec·코드 한 줄, 21 구현 전이면 21에서), **②는 그대로 두고 HITL에서 결과(`eval_reports` 어제 날짜 `skipped` 1행, 공격 세트 방어율)를 확인 항목으로 씀** / B: 둘 다 그대로, HITL은 01:00 전에 하거나 잠금이 풀릴 때까지 기다림 / C: 클린 기동에서 놓친 실행을 끄는 설정 추가(코드·설정 추가) | **A** — ①은 [A] §3.3 "초기 적재는 CLI"와 21의 "이어하기" 뜻에 맞고, 새로 설치한 사람이 모르는 사이 며칠짜리 적재·비용이 시작되지 않음. ②는 비용이 작고 설치 직후 공격 세트가 도는지 바로 확인됨 |
| 26-Q2 | lightrag에 healthcheck가 없어 클린 기동 직후 적재·툴 호출이 LightRAG 준비 전에 갈 수 있다(I-8) | A: **lightrag healthcheck 추가**(이미지 안 python으로 `/health` 호출 — 경로·인증 필요 여부 **미확인**, 구현 시 확인) + tour-tools `lightrag: service_healthy` / B: 그대로, README·HITL에 "로그에서 준비 확인 후 진행" | **A** — 클린 기동 재현이 26의 목적. 설정 몇 줄 |
| 26-Q3 | 외부 이미지(postgres·lightrag·nginx·cloudflared)에도 `no-new-privileges`·`cap_drop`을 넣을까 | A: **[A] §9대로 자체 이미지 4개만 강제**, 외부 이미지는 그대로 / B: 4개 모두 `no-new-privileges:true`만 추가(능력 제거는 안 함 — 기동 확인 필요) / C: cloudflared만 `cap_drop: [ALL]`+`no-new-privileges`(외부와 직접 붙는 유일한 컨테이너, 비루트 이미지로 알려짐 — **미확인**) | **A** — 상위 문서 범위. C는 한 줄이라 원하면 추가 가능(기동 확인 1회) |
| 26-Q4 | postgres healthcheck가 첫 기동 init 도중 통과할 수 있다(I-9, **미확인**) | A: **`pg_isready -h 127.0.0.1 -U postgres -d nadri`로 바꿈**(TCP·nadri DB 기준 — init 끝난 뒤에만 통과) / B: 그대로(실패하면 재시작 정책으로 결국 뜸) | **A** — 한 줄, 클린 기동 HITL에서 효과 확인 |
| 26-Q5 | 조정 설정값(`VERIFY_MAX_REWRITES`·`FAQ_CACHE_THRESHOLD`·`RAG_*` 4개)을 어떻게 넣을까(I-7) — 26 초안 `x-agent-settings`와 24-Q2 `x-tuning`이 겹침 | A: **24의 `x-tuning` 하나로 통일 — 6개 값을 api·tour-tools·ingest에 같은 앵커로**, C-27로 검사 / B: 서비스별로 쓰는 값만 따로 적음(api 2개·tour-tools 4개, ingest는 스냅샷이 기본값을 봄 — 24-Q2와 충돌) | **A** — 24-Q2 결정과 같고, 값을 한 곳에서만 고쳐 평가·스냅샷·운영이 어긋나지 않음 |
| 26-Q6 | 개발 덮어쓰기 포트가 ADR-01("nginx만")보다 많다(I-6) | A: **테스트 기준 "dev 포트는 모두 127.0.0.1"**, ADR-01 문구를 그렇게 고침 / B: dev에선 nginx만 두고 통합 테스트 포트는 별도 파일(`compose.test.yaml`)로 분리 | **A** — 01 통합 테스트 방식 유지, WSL 안에서만 열림 |
| 26-Q7 | Windows에서 레포를 받으면 `01-init.sh` 줄바꿈이 CRLF가 돼 DB 초기화가 깨질 수 있다(I-15, NFR-21) | A: **`.gitattributes`에 `*.sh text eol=lf` + 테스트 C-26** / B: README에 "Windows에선 `core.autocrlf false`" 안내만 | **A** — 파일 1줄로 원인 자체를 없앰 |
| 26-Q8 | [A] §9 비밀값 표·§2 cloudflared 행·ADR-01 문구가 확정 spec과 다르다(I-2·3·4·6) | A: **26에서 architecture.md를 고치고 PROGRESS에 기록**(승인본 수정이므로 사용자 확인) / B: 고치지 않고 이 spec §4를 정본으로 둠 | **A** — 문서끼리 다르면 다음 사람이 또 헷갈림. 바뀌는 건 표 3곳 |
| 26-Q9 | 클린 기동 HITL을 어느 형태로 할까 | A: **운영 형태(`compose.yaml`만 + 터널), 기존 환경은 잠시 멈춤**, 터널 없는 경로(dev + `localhost:8080`)는 선택 확인 / B: 개발 형태(dev 덮어쓰기)로만 — 운영 빌드(web standalone)를 거치지 않음 | **A** — README 기본 경로와 실제 운영 빌드를 그대로 확인 |
