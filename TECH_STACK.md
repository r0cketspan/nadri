# TECH_STACK.md

관광 챗봇의 기술 구성 문서 (개발자용). **G2(기술스택)·G3(아키텍처) 승인 전 초안**이다.
`[미확인]` = 문서로 확정 못 해 PoC/G2에서 확인할 항목. 버전은 G2에서 고정한다.

---

## 1. 한눈에 보기

| 영역 | 선택 | 비고 |
|---|---|---|
| 실행 환경 | WSL2 Ubuntu-22.04 + Docker Compose | Rocky Linux·Windows Docker Desktop으로 이식 가능 |
| 프론트엔드 | **Next.js** (App Router, TypeScript) | 반응형 채팅 UI, 모바일 브라우저 대응 |
| 백엔드(BFF) | **FastAPI** (Python) | 브라우저가 호출하는 유일한 API. 인증·세션·대화이력·STT·TTS 중계 |
| 에이전트 | **Hermes Agent** (Nous Research) | API Server(OpenAI 호환, `:8642`)로 FastAPI가 호출 |
| LLM | **OpenAI API** — 메인 `gpt-6-luna`, 보조 `gpt-5-nano` | 다른 LLM 프로바이더로 fallback 하지 않음 |
| Graph RAG | **LightRAG** | 그래프 + 벡터, 문서 단위 삭제·증분 갱신 |
| DB | **PostgreSQL + pgvector** (단일 DB) | 벡터·그래프 테이블·관광 정형데이터·사용자·세션·대화 |
| 임베딩 | OpenAI `text-embedding-3-small` (기본) | 로컬 `bge-m3`와 비교 후 G2 확정 — **바꾸면 전체 재인덱싱** |
| 리랭커 | `BAAI/bge-reranker-v2-m3` (로컬, CPU 가능) | 서빙 방식 G2 확정 (§5.3) |
| 툴 연결 | **MCP 서버** (Python, 자체 개발) | Hermes `mcp_servers`로 등록 |
| STT | OpenAI 전사 API (`gpt-4o-mini-transcribe`) | `SttProvider` 인터페이스로 추후 로컬 GPU faster-whisper 전환 |
| TTS | Edge TTS(개발) → ElevenLabs(데모) | `TtsProvider` 인터페이스, Drama 3는 API로 실험 |
| 리버스 프록시 | **Nginx** | HTTPS, 단일 진입점, SSE 버퍼링 off |
| 데이터 원천 | **한국관광공사 TourAPI 4.0** (`KorService2`) | 공공데이터포털 인증키 |

---

## 2. 시스템 구성도

```
 [PC/모바일 브라우저]
        │ HTTPS
        ▼
 ┌─────────────┐   /        ┌──────────────┐
 │   Nginx     │──────────▶ │  Next.js     │  채팅 UI, 녹음(MediaRecorder), TTS 재생
 │ (443)       │   /api/*   ├──────────────┤
 │             │──────────▶ │  FastAPI     │  인증·세션·대화이력·컨텍스트 조립·STT·TTS
 └─────────────┘            └──────┬───────┘
                                   │ OpenAI 호환 (/v1/chat/completions, SSE)
                                   ▼
                            ┌──────────────┐        ┌──────────────┐
                            │ Hermes Agent │──────▶ │ OpenAI API   │
                            │ (gateway)    │        └──────────────┘
                            └──────┬───────┘
                                   │ MCP (HTTP)
                                   ▼
                            ┌──────────────┐  rag_query ──▶ LightRAG ──┐
                            │ tour-tools   │  data_query ─────────────┤
                            │ (MCP 서버)   │  tour_live ──▶ TourAPI   │
                            └──────────────┘                          ▼
                                                            ┌──────────────────┐
 ┌────────────────────┐  wiki 갱신·인덱싱                    │ PostgreSQL       │
 │ ingest (배치/스케줄)│ ───────────────────────────────────▶│ + pgvector       │
 │ TourAPI → raw →    │                                      │ (RAG·정형·세션)  │
 │ 정형DB + LLM Wiki  │                                      └──────────────────┘
 └────────────────────┘
```

외부에 열리는 포트는 **Nginx 443 하나**. Hermes·LightRAG·PostgreSQL·MCP는 Compose 내부 네트워크에만 노출.

---

## 3. 데이터 — TourAPI & 현행화 (LLM Wiki)

### 3.1 원천
- 기본 URL: `https://apis.data.go.kr/B551011/KorService2`
- 주요 오퍼레이션: `areaBasedList2`(지역 목록), `locationBasedList2`(좌표 주변), `searchKeyword2`, `searchFestival2`(행사), `searchStay2`(숙박), `detailCommon2`/`detailIntro2`/`detailInfo2`/`detailImage2`(상세), **`areaBasedSyncList2`(변경분 동기화 → 현행화 핵심)** [미확인: 공식 명세서로 최종 확인]
- 콘텐츠 타입: 관광지·문화시설·행사/축제·여행코스·레포츠·숙박·쇼핑·음식점
- **트래픽 제약**: 개발계정 일일 호출 한도가 작음(관광공사 API 다수가 1,000건/일) [미확인: KorService2 한도] → 초기 전체 적재에 수일 소요 가능. 대응: **MVP는 지역 1곳으로 범위 축소** 또는 운영계정 트래픽 증설 신청.
- 이미지·저작권: 공공누리 유형 표기 및 "한국관광공사" 출처 표기 필요.

### 3.2 처리 흐름
```
TourAPI ─▶ raw/ (응답 JSON, 날짜별 스냅샷, 불변)
              │
              ├─▶ PostgreSQL 정형 테이블 tour_items (contentid, type, title, addr, 좌표, tel, 운영시간, 요금, modifiedtime …)
              │      └─ data_query 툴이 조회 (필터·정렬·집계·거리 계산)
              │
              └─▶ LLM Wiki (wiki/*.md)
                     ├─ 엔티티 페이지: 관광지 1건 = 1페이지 (템플릿 렌더링 — LLM 비용 0)
                     ├─ 허브 페이지: 지역 개요·테마·코스 (LLM이 작성·유지)
                     └─ frontmatter: contentid, source, 기준일(as_of), updated_at
                            │
                            ▼
                     LightRAG 인덱싱 (임베딩 → pgvector, 엔티티/관계 → 그래프 테이블)
```

### 3.3 현행화
1. 스케줄러가 `areaBasedSyncList2`로 **변경·삭제된 contentid**만 조회
2. 변경분 상세 재수집 → raw 저장 → 정형 테이블 upsert
3. 해당 엔티티 위키 페이지 재렌더 → LightRAG에서 **그 문서만 delete → insert**
4. 영향받는 허브 페이지만 LLM이 갱신
5. **lint**: 깨진 링크·오래된 페이지(기준일 경과)·모순 탐지 리포트
6. 위키 디렉터리는 별도 git으로 커밋 → 변경 이력 추적

---

## 4. 질의 처리 — 에이전트 & Tool Calling

### 4.1 흐름
```
사용자 질문
  └▶ FastAPI: 인증 확인 → 대화 컨텍스트 조립(§6) → Hermes 호출(stream)
       └▶ Hermes(LLM)가 판단
            ├─ 스몰토크·일반 상식  → 툴 없이 바로 답변
            ├─ 관광 지식 질문      → rag_query
            ├─ 조건·수치·주변 검색 → data_query
            ├─ 실시간성 필요       → tour_live
            └─ DB에 없는 최신 정보 → web_search / web_fetch
       └▶ 툴 결과를 근거로 답변 생성 (출처·기준일 포함) → SSE 스트리밍
```

### 4.2 툴 목록 (초안)
| 툴 | 제공 | 설명 |
|---|---|---|
| `rag_query` | tour-tools | 위키를 임베딩한 **벡터DB(pgvector) + 그래프** 검색 → 리랭크 → 상위 문단 반환 |
| `data_query` | tour-tools | `tour_items` 정형 조회 (지역·타입·키워드·거리·운영여부). **SQL 직접 생성 금지 — 파라미터화된 조회 함수만** |
| `tour_live` | tour-tools | TourAPI 실시간 호출 (진행 중 축제, 좌표 주변 등) |
| `web_search` / `web_fetch` | Hermes 내장 | DuckDuckGo(무료)/Brave/SearXNG 중 G2 확정 |
| `get_datetime` | tour-tools | "이번 주말", "오늘 하는 축제" 해석용 |

**우선순위 규칙**(시스템 프롬프트): 공공데이터(정형·위키) > 웹 검색. 웹 결과는 출처 표기. 운영시간·요금 같은 사실은 **LLM 기억으로 답하지 말고 툴 결과로만** 답한다.

### 4.3 Hermes 보안 설정
- Hermes는 터미널·파일·브라우저 등 범용 툴을 가진 자율 에이전트 → **위 툴만 허용(whitelist)**, 나머지 비활성화 [미확인: 정확한 toolset 설정 키]
- API Server는 `API_SERVER_KEY` 필수, 내부 네트워크에만 바인딩. 브라우저는 Hermes를 직접 호출하지 않는다.

### 4.4 (선택) 최소 에이전트 루프
역량 증빙용. OpenAI SDK로 "모델 호출 → 툴 호출 요청이면 실행 후 결과를 붙여 재호출 → 툴 요청이 없으면 최종 답변" 루프를 50줄 내외로 직접 구현해 Hermes와 응답 품질·지연·토큰을 비교.

---

## 5. RAG 상세

### 5.1 LightRAG + PostgreSQL
| 스토리지 | 설정 | 비고 |
|---|---|---|
| KV / 벡터 / 문서상태 | PostgreSQL 계열 스토리지 | `LIGHTRAG_KV_STORAGE`, `LIGHTRAG_VECTOR_STORAGE`, `LIGHTRAG_DOC_STATUS_STORAGE` |
| 그래프 | **`PGTableGraphStorage`** | 일반 PostgreSQL 테이블 — Apache AGE 불필요 → 공식 `pgvector/pgvector:pg18` 이미지로 충분 |
| 벡터 인덱스 | `POSTGRES_VECTOR_INDEX_TYPE=HNSW` | |
| 언어 | `SUMMARY_LANGUAGE=Korean` | [미확인: 한국어 엔티티 추출 품질 → PoC] |
| 인증 | `LIGHTRAG_API_KEY` | 내부망 전용 + 키 |

### 5.2 검색 파이프라인 (`rag_query` 내부, 고정 순서)
```
질문 ─▶ ① 벡터+그래프 검색 (후보 30개, 빠르고 넓게)
     ─▶ ② 리랭커 재채점 (질문-문단 쌍을 직접 비교, 상위 5개)
     ─▶ ③ 상위 5개 + 출처·기준일을 LLM에 전달 → 답변 생성
```
리랭커 효과: 정확도↑, LLM 입력 토큰↓(비용↓). 대가: 지연 +1~2초.

### 5.3 리랭커 서빙
LightRAG 리랭크 바인딩은 `cohere`/`jina`/`aliyun` 형식만 지원 → 로컬 모델을 쓰려면 Cohere 호환 `/rerank` 엔드포인트가 필요.
- 후보 A: 리랭커 전용 컨테이너(Cohere 호환 API 제공 서버) [미확인: 후보 서버 선정]
- 후보 B: `tour-tools` 안에서 CrossEncoder로 직접 재정렬 (LightRAG 리랭크 off)

---

## 6. 대화 · 세션

**정본은 우리 PostgreSQL.** Hermes는 stateless(`/v1/chat/completions`)로 호출하고, FastAPI가 매 요청마다 컨텍스트를 조립한다 → 유지 범위·요약·삭제 정책을 우리가 통제.

| 정책 | 값 |
|---|---|
| 모델에 보내는 원문 | 최근 **10턴** |
| 그 이전 대화 | **누적 요약 1개**로 압축 (`gpt-5-nano`) |
| 세션당 최대 | **50턴** → 초과 시 새 대화 안내 |
| 보관 | **90일** 후 자동 삭제 |
| 세션 제목 | 첫 문답 후 `gpt-5-nano`로 한 줄 요약 생성 → 사이드바 이력 목록 |

테이블 초안: `users`, `auth_sessions`, `chat_sessions(id, user_id, title, summary, turn_count, created_at, updated_at)`, `chat_messages(id, session_id, role, content, tool_trace, tokens, created_at)`.

---

## 7. 인증 (로그인)

**결정: 일반 로그인(아이디 + 비밀번호) + 서버 세션 쿠키.** 소셜 로그인 사용 안 함.

| 항목 | 방식 |
|---|---|
| 로그인 | 아이디 + 비밀번호. FastAPI가 처리 |
| 비밀번호 저장 | **Argon2id** 해시(솔트 포함). 평문·가역 암호화 저장 금지 |
| 비밀번호 정책 | 최소 10자, 흔한 비밀번호 목록 차단 (복잡도 강제보다 길이 우선 — NIST SP 800-63B 방식) |
| 무차별 대입 방지 | 계정별·IP별 실패 횟수 제한 (예: 5회 실패 → 15분 잠금), 점진적 지연 |
| 계정 열거 방지 | 실패 메시지는 항상 "아이디 또는 비밀번호가 올바르지 않습니다" 하나로 통일 |
| 비밀번호 변경 | 변경 시 해당 사용자의 다른 세션 전부 폐기 |
| 세션 | 서버측 세션(PostgreSQL `auth_sessions`). 브라우저에는 랜덤 세션 ID만 |
| 쿠키 | `__Host-session`; `HttpOnly`; `Secure`; `SameSite=Lax`; `Path=/` |
| 토큰 보관 | **localStorage에 토큰 저장 금지** (XSS 탈취 방지) |
| 세션 수명 | 유휴 만료 + 절대 만료, 로그인 시 세션 ID 재발급(고정 공격 방지), 로그아웃 시 서버에서 폐기 |
| CSRF | SameSite + 상태변경 요청에 CSRF 토큰(double-submit) |
| 남용 방지 | 로그인·STT·채팅 엔드포인트 rate limit, 사용자별 일일 질의 한도(비용 보호) |
| 동일 출처 | Nginx가 `/`와 `/api`를 한 도메인으로 묶음 → CORS 불필요, 쿠키 단순 |

미정(G1에서 결정): **회원가입 개방 범위**(누구나 가입 시 OpenAI 비용 노출 → 초대코드/관리자 승인 검토), **비밀번호 재설정 방식**(이메일 발송 필요 여부 — 없으면 관리자 재설정).

---

## 8. 음성

### 8.1 STT — Push-to-talk (비실시간)
```
[🎙 시작] → MediaRecorder 녹음 → [⏹ 종료] → POST /api/stt (파일 1개)
   → SttProvider.transcribe() → 텍스트를 입력창에 채움 → 사용자 확인·수정 후 전송
```
```python
class SttProvider(Protocol):
    """음성 파일을 텍스트로 바꾸는 공통 인터페이스. 구현체는 STT_PROVIDER 설정으로 선택한다."""
    async def transcribe(self, audio: bytes, mime_type: str, language: str = "ko") -> str: ...

# STT_PROVIDER=openai          → OpenAISttProvider        (현재)
# STT_PROVIDER=faster_whisper  → FasterWhisperProvider    (추후: 별도 GPU 컨테이너, NVIDIA Container Toolkit)
```
- 포맷: Chrome `webm/opus`, iOS Safari `mp4/aac` — 둘 다 OpenAI 전사 API 지원
- **모바일 마이크는 HTTPS 필수**(브라우저 보안 정책)
- 녹음 길이 상한(예: 60초)·파일 크기 상한을 둔다

### 8.2 TTS
`TtsProvider` 동일 패턴. 답변 옆 🔊 버튼 → `/api/tts` → 오디오 스트림 재생.
Edge TTS(무료, `ko-KR`) → ElevenLabs(데모). Drama 3는 35B 모델이라 로컬 불가, API로만 실험(라이선스 제한 확인).

---

## 9. 배포 (Docker Compose)

| 서비스 | 이미지/빌드 | 외부 노출 |
|---|---|---|
| `nginx` | nginx | **443** |
| `web` | Next.js 빌드 | ✗ |
| `api` | FastAPI 빌드 | ✗ |
| `hermes` | `nousresearch/hermes-agent` (`gateway run`) | ✗ |
| `tour-tools` | 자체 빌드 (MCP 서버) | ✗ |
| `lightrag` | LightRAG 서버 | ✗ |
| `postgres` | `pgvector/pgvector:pg18` | ✗ |
| `reranker` | §5.3 결정에 따름 | ✗ |
| `ingest` | 자체 빌드 (스케줄 배치) | ✗ |
| `stt-gpu` | (추후) faster-whisper | ✗ |

**이식성**: 같은 compose + 이미지로 Rocky Linux·Windows(Docker Desktop, WSL2 백엔드)에서 실행 가능. 단,
- CPU 아키텍처가 다르면(ARM 서버/맥) `linux/amd64`·`arm64` 멀티아키 빌드 필요
- Rocky는 기본이 Podman → Docker CE 설치 권장
- GPU 컨테이너는 호스트에 NVIDIA 드라이버 + NVIDIA Container Toolkit 필요
- 데이터는 named volume, 비밀값은 `.env` → 서버 이전 시 볼륨 백업/복원

**리버스 프록시(Nginx)를 두는 이유**: ① HTTPS(모바일 마이크 필수, 쿠키 `Secure`. Nginx는 인증서 자동 발급이 없어 인증서를 직접 준비) ② `/`·`/api` 단일 진입점, 내부 서비스 은닉 ③ SSE 스트리밍 버퍼링 설정 일원화. 클라우드 배포는 하지 않는다.

---

## 10. 비용 최적화
- **프롬프트 캐싱**: 시스템 프롬프트·툴 정의를 고정 프리픽스로(1,024토큰 이상이면 자동 캐싱, 캐시 입력은 1/10 가격). `prompt_cache_key` 사용, 응답의 `cached_tokens`로 적중률 측정.
- **모델 분리**: 답변 `gpt-6-luna` / 제목·요약·키워드 `gpt-5-nano`.
- **FAQ 응답 캐시**: 동일·유사 질문 결과 재사용 (데이터 기준일 바뀌면 무효화).
- **위키 엔티티 페이지는 템플릿 렌더링**(LLM 미사용), LLM은 허브 페이지에만.
- **사용량 대시보드**: 사용자·일자별 토큰/비용.
- **LLM 장애 시**: 다른 프로바이더로 넘기지 않음 → "시스템 장애" 안내 + 재시도 버튼.

참고 단가(OpenAI 공식, 2026-10-24, $/1M tokens): `gpt-6-luna` 입력 0.10 / 캐시 0.01 / 출력 0.50, `gpt-5-nano` 0.05 / 0.005 / 0.40, `text-embedding-3-small` 0.02, `gpt-4o-mini-transcribe` $0.003/분.

---

## 11. 평가 · 테스트
- **단위테스트**: pytest(FastAPI·툴·ingest), 외부 API·LLM은 목킹한 결정적 테스트 우선.
- **골든 Q&A 평가셋**: 관광 질문 + 정답 + 근거 contentid → 정답률·근거 일치율, 리랭커 on/off·임베딩 모델 비교에 사용.
- **E2E**: 로그인 → 질문 → 스트리밍 답변 → 이력 조회 → 음성 입력 (하네스 Phase 6 `integration_test.md`).

---

## 12. 레포 구조 (초안, G3에서 확정)
```
myAgent/
├── apps/
│   ├── web/            # Next.js
│   └── api/            # FastAPI (BFF)
├── services/
│   ├── tour-tools/     # MCP 서버 (rag_query, data_query, tour_live, get_datetime)
│   └── ingest/         # TourAPI 수집 · 위키 생성 · LightRAG 인덱싱
├── infra/
│   ├── compose.yaml
│   ├── nginx/nginx.conf
│   └── hermes/         # config.yaml 템플릿 (비밀값 제외)
├── eval/               # 골든 Q&A 평가셋 · 평가 스크립트
├── docs/
│   ├── analysis/       # 사전 분석
│   └── harness/        # 하네스 산출물 (requirements, architecture, program_list, tasks/…)
├── CLAUDE.md
└── TECH_STACK.md
```
위키·raw 데이터는 용량이 커서 레포가 아닌 **데이터 볼륨**(자체 git 이력)에 둔다.
