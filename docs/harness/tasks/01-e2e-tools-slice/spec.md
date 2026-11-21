# 01-e2e-tools-slice — 최소 E2E ① 데이터 → RAG → MCP 툴

> 하네스 Phase 4 산출물 (spec-writer, 작성 2026-11-21). 상태: **초안 — 사용자 검토 대기**.
> 입력: `program_list.md` §2 표·§3 "01-e2e-tools-slice"(G4 승인본) · `architecture.md`(G3 재승인본) §1·§2.1·§4·§5·§6.2·§7·§8·§9·§12 · `erd.md`/`docs/images/src/erd.py` · `requirements.md` · `TECH_STACK.md` · `PROGRESS.md` 결정 로그(G4 Q1~Q9).
> 출처 표기: [PL]=program_list.md, [A]=architecture.md, [R]=requirements.md, [E]=ERD(`erd.py`), [TS]=TECH_STACK.md, [S]=stack-options.md, [PG]=PROGRESS.md.
> **미확인** = 문서·공식 자료로 확인하지 못해 구현 중 실제 호출/소스로 확인해야 하는 사실. 이 작업의 가정 판정(§9) 항목과 겹친다.

---

## 1. 작업 목표

실제 TourAPI 응답 → raw 스냅샷 → `tour_items` → 엔티티 위키 페이지 → LightRAG 인덱싱 → tour-tools MCP 툴 호출까지를 **실제로** 돌려 데이터·RAG 쪽 위험 가정 A7·A8·A9·A12(일부)·A16·A21을 판정한다. 이후 작업이 넓혀 갈 뼈대(compose 4서비스, uv 프로젝트, Alembic, 설정, CLI)를 만든다 [PL §3].

- 적재 규모: **서울 관광지(타입 12) 30건 + 제주 관광지(타입 12) 20건 = 50건** (G4 Q9). TourAPI 약 152호출(목록 2 + 상세 3종 × 50).
- 추적 요구사항: FR-19·40·41·42·44·50·51·53, NFR-07·08·20·24·32, ADR-02·05·06·07·24 [PL §3].

### 1.1 범위 밖 (이 작업에서 하지 않는다)
| 하지 않는 것 | 담당 작업 |
|---|---|
| api·nginx·cloudflared 컨테이너, LangGraph·답변/검증 에이전트, Moderation, SSE | 02 |
| 일일 호출 **예산 강제**(800 소진 시 중단)·이어하기 커서·8종 템플릿·타입별 `detailIntro2` 매핑 | 03 (01은 호출 수 **기록**과 실행 전 간단 점검만, §6.4) |
| 앱 테이블 14개 | 04 |
| `tour_live` 툴(TourAPI 실시간) — tour-tools에 `TOURAPI_SERVICE_KEY`를 주입하지 않음 | 10 |
| 허브 페이지·lint·위키 git | 20 |
| 01:00 현행화 스케줄러(ingest 상주) | 21 |
| 리랭커 on/off·mix/hybrid 비교 | 22 |

---

## 2. 생성 파일과 역할

경로는 레포 루트 기준. Python 패키지는 `backend/src/nadri/`(src 레이아웃, [A] §7). [PL]의 `nadri/...`는 `backend/src/nadri/...`를 뜻한다.

| 파일 | 역할 |
|---|---|
| `compose.yaml` | 4서비스(postgres·lightrag·tour-tools·ingest), 프로젝트 이름 `nadri`, 네트워크 1개(기본), named volume `pg-data`·`wiki-data`·`raw-data`·`lightrag-data`, **호스트 포트 없음**, 서비스별 필요한 키만 주입(§5) |
| `compose.dev.yaml` | 개발 덮어쓰기: 소스 마운트·tour-tools 핫리로드, 통합 테스트용 `127.0.0.1` 포트(postgres·lightrag·tour-tools) |
| `.env.example` | 이 작업에서 쓰는 키 이름 8개만(§4) |
| `infra/postgres/init/01-init.sh` | 롤 3개·DB 2개·`vector` 확장·접속 권한 (G4 Q8 — `.sh`, 비밀번호는 환경변수) |
| `infra/lightrag/lightrag.env` | LightRAG 비밀 아닌 설정(PG 저장소, `PGTableGraphStorage`, HNSW, 한국어, 리랭크 off, 모델) |
| `backend/pyproject.toml`, `backend/uv.lock` | Python 3.12, 의존 버전 고정, 그룹 `reranker`(tools 타깃만)·`dev`(테스트) |
| `backend/Dockerfile` | 타깃 `app`(ingest, 02부터 api) / `tools`(tour-tools, 빌드 시 리랭커 가중치 내려받기), 비루트 |
| `backend/alembic.ini`, `backend/alembic/env.py`, `backend/alembic/versions/0001_tour_ingest.py` | async Alembic, 테이블 4개 + 한글 COMMENT + `nadri_tools` SELECT 권한 부여 |
| `backend/src/nadri/__init__.py` | 패키지 표시(빈 파일) |
| `backend/src/nadri/core/config.py` | 환경변수 설정(pydantic-settings) |
| `backend/src/nadri/core/db.py` | async 엔진(asyncpg)·세션 팩토리 |
| `backend/src/nadri/core/models/__init__.py` | `Base`(DeclarativeBase) |
| `backend/src/nadri/core/models/tour.py` | ORM `TourItem`, `WikiPage` |
| `backend/src/nadri/core/models/ingest.py` | ORM `IngestRun`, `IngestState` |
| `backend/src/nadri/core/tourapi.py` | KorService2 클라이언트(목록·상세 3종), 응답 파싱, 오류코드 해석 |
| `backend/src/nadri/ingest/raw.py` | 날짜별 불변 JSON 스냅샷 저장 |
| `backend/src/nadri/ingest/upsert.py` | TourAPI 응답 → `TourItemRecord` 변환, `tour_items` upsert |
| `backend/src/nadri/ingest/wiki/render.py`, `templates/entity.md.j2` | LLM 없는 엔티티 페이지 렌더·해시·원자적 파일 쓰기 |
| `backend/src/nadri/ingest/indexer.py` | LightRAG 문서 API 클라이언트, 해시 비교 → delete→insert, `wiki_pages` 갱신 |
| `backend/src/nadri/ingest/bootstrap.py` | `--area --type --limit` 소량 적재, `reindex`, `count`, 호출 수 기록 |
| `backend/src/nadri/tools/server.py` | FastMCP(stateless Streamable HTTP) + Bearer 토큰 ASGI 미들웨어 + 툴 3종 등록 + 실행 진입점 |
| `backend/src/nadri/tools/rag_query.py` | LightRAG `/query/data`(mix, 후보 30) → 리랭크 → 상위 5 + `wiki_pages` 메타 |
| `backend/src/nadri/tools/reranker.py` | `bge-reranker-v2-m3` CrossEncoder(CPU) 래퍼 |
| `backend/src/nadri/tools/data_query.py` | `tour_items` 파라미터화 조회, 하버사인 |
| `backend/src/nadri/tools/get_datetime.py` | 현재 KST·요일·이번 주말/다음 주 범위 |
| `backend/src/nadri/cli.py` | `nadri` 명령: `ingest bootstrap·reindex·count`, `tools smoke`, `lightrag sample` (§6.9) |
| `backend/tests/**` | pytest 단위·통합 테스트(test.md) |
| `CLAUDE.md` | "명령어" 절에 빌드·테스트·실행 명령 처음 기록 [PL §3] |

> [PL] 파일 목록에 없는 것: `nadri/__init__.py`, `core/models/__init__.py`(Base 위치), `tests/`, CLI 하위 명령 4개(측정·판정용). 확인 질문 Q5.

---

## 3. 데이터베이스

### 3.1 `01-init.sh` (G4 Q8)
`postgres` 이미지의 `/docker-entrypoint-initdb.d/`로 마운트(읽기 전용). **빈 `pg-data` 볼륨에서 처음 기동할 때만 실행**된다 — 나중에 `.env` 비밀번호를 바꿔도 반영되지 않는다(README/CLAUDE.md에 명시, 바꾸려면 `ALTER ROLE` 또는 볼륨 재생성).

처리 순서:
1. 필수 환경변수 확인: `APP_DB_PASSWORD`·`TOOLS_DB_PASSWORD`·`LIGHTRAG_DB_PASSWORD` 하나라도 비면 `: "${VAR:?}"`로 즉시 실패.
2. `psql -v ON_ERROR_STOP=1 -v app_pw="$APP_DB_PASSWORD" …`로 변수 전달, SQL 안에서는 `:'app_pw'`로 인용(셸 문자열 조립·SQL 인젝션 방지).
3. 롤 생성: `nadri_app`(LOGIN), `nadri_tools`(LOGIN), `lightrag`(LOGIN). 모두 superuser·createdb·createrole 아님.
4. DB 생성: `nadri`(OWNER `nadri_app`), `lightrag`(OWNER `lightrag`).
5. 두 DB 모두 `REVOKE CONNECT ON DATABASE … FROM PUBLIC`. `nadri`에는 `nadri_app`·`nadri_tools`만 CONNECT, `lightrag`에는 `lightrag`만.
6. 두 DB 각각 superuser로 `CREATE EXTENSION IF NOT EXISTS vector`.
7. `nadri` DB: `GRANT USAGE ON SCHEMA public TO nadri_tools`.

> **[PL]과 다른 점**: [PL]은 "`nadri_tools`는 `tour_items`·`wiki_pages` SELECT만"을 init 스크립트 역할로 적었지만, init 시점에는 테이블이 없어 테이블 단위 GRANT를 할 수 없다. 그래서 **테이블 SELECT 부여는 테이블 생성 스크립트 `0001`의 마지막 단계**에서 한다(§3.3). 확인 질문 Q2.

### 3.2 테이블 4개 (ERD 한글명 = COMMENT)
한글 명칭 정본은 `docs/images/src/erd.py`의 `T`. [A] §5.1 표의 명칭("관광 항목", "수집 실행 기록")과 다르면 **ERD를 따른다**([PL] X-e). 모든 시각 `timestamptz`.

**`tour_items` — COMMENT '관광 정보'**
| 컬럼 | 타입 | 제약 | COMMENT |
|---|---|---|---|
| contentid | text | PK | 관광지 ID |
| content_type_id | int | not null | 관광 유형 |
| area | text | not null (`서울`/`제주`) | 지역 |
| sigungu_code | text | null | 시군구 코드 |
| title | text | not null | 명칭 |
| addr | text | null | 주소 |
| lat | float8 | null | 위도 |
| lng | float8 | null | 경도 |
| tel | text | null | 전화번호 |
| usetime | text | null | 이용시간 |
| fee | text | null | 이용요금 |
| restdate | text | null | 휴무일 |
| event_start | date | null | 행사 시작일 |
| event_end | date | null | 행사 종료일 |
| extra | jsonb | not null default `'{}'` | 유형별 상세 |
| modifiedtime | timestamptz | null | 원천 수정 일시 |
| detail_synced_at | timestamptz | null | 상세 수집 일시 |
| as_of | date | not null | 기준일 |
| deleted_at | timestamptz | null | 삭제 일시 |
| updated_at | timestamptz | not null default `now()` | 수정 일시 |

- ERD 행 "`lat · lng` / 위도 · 경도"는 두 컬럼으로 나눠 COMMENT `위도`, `경도`로 넣는다. 04의 `test_schema_comments.py`는 이 분리를 알아야 한다(04 spec에 전달).
- 인덱스: `ix_tour_items_area_type (area, content_type_id) WHERE deleted_at IS NULL`. 그 외 인덱스는 만들지 않는다(50~수천 건 규모).

**`wiki_pages` — COMMENT '위키 페이지'**
| 컬럼 | 타입 | 제약 | COMMENT |
|---|---|---|---|
| path | text | PK (예: `entity/12/126508.md`) | 페이지 경로 |
| kind | text | not null, CHECK in (`entity`,`hub`) | 페이지 종류 |
| contentid | text | null, FK → `tour_items.contentid` (ON DELETE 기본 NO ACTION — 관광 항목은 soft delete라 실제 삭제 경로 없음) | 관광지 ID |
| title | text | not null | 제목 |
| area | text | null | 지역 |
| sigungu_code | text | null | 시군구 코드 |
| as_of | date | null | 기준일 |
| content_hash | text | null (인덱싱 **성공 후에만** 채움) | 내용 해시 |
| lightrag_doc_id | text | null | RAG 문서 ID |
| indexed_at | timestamptz | null | 인덱싱 일시 |

**`ingest_runs` — COMMENT '수집 실행 이력'**
| 컬럼 | 타입 | 제약 | COMMENT |
|---|---|---|---|
| id | bigint | PK, identity | 실행 ID |
| kind | text | not null (01: `bootstrap`·`reindex`) | 실행 종류 |
| started_at | timestamptz | not null default now() | 시작 일시 |
| finished_at | timestamptz | null | 종료 일시 |
| status | text | not null, CHECK in (`running`,`done`,`failed`) | 결과 |
| stats | jsonb | not null default `'{}'` | 처리 통계 |
| lint | jsonb | null (20에서 사용) | 점검 결과 |
| error | text | null | 오류 메시지 |

**`ingest_state` — COMMENT '수집 상태'**
| 컬럼 | 타입 | 제약 | COMMENT |
|---|---|---|---|
| key | text | PK | 상태 키 |
| value | jsonb | not null | 상태 값 |

01에서 쓰는 키: `tourapi_calls:YYYY-MM-DD`(KST 날짜) → `{"ingest": <정수>, "live": 0}` — G4 Q6 공유 카운터의 저장 형식. `live`는 10에서 채운다.

### 3.3 테이블 생성 스크립트 `0001_tour_ingest` (Alembic)
> 용어: 이 문서에서 "테이블 생성 스크립트"는 Alembic 리비전 파일(`backend/alembic/versions/NNNN_*.py`)을 말한다. 테이블 생성·변경 SQL을 번호 순서대로 두고, DB에 아직 적용되지 않은 번호만 실행한다. 데이터 이관(다른 DB로 옮기기)과는 무관하다.
- `upgrade()`: 4테이블 생성(위 COMMENT 포함 — `sa.Column(..., comment=)`, `sa.Table(..., comment=)`) → 인덱스 → `GRANT SELECT ON tour_items, wiki_pages TO nadri_tools`.
- `downgrade()`: GRANT 회수 → 테이블 4개 삭제(역순).
- 실행 주체: `ingest` 서비스 기동 명령(§5.2). 롤 `nadri_app`(테이블 소유자).
- `alembic/env.py`: `nadri.core.config.get_settings().database_url`을 사용, async 엔진 + `run_sync(do_run_migrations)` 표준 패턴. `target_metadata = Base.metadata`.

### 3.4 ORM
`core/models/tour.py`의 `TourItem`·`WikiPage`, `core/models/ingest.py`의 `IngestRun`·`IngestState`. SQLAlchemy 2.x `Mapped[...]`/`mapped_column(..., comment=...)`, `__table_args__ = {"comment": "관광 정보"}` 식. 테이블 생성 스크립트과 ORM의 COMMENT 문자열은 같아야 한다(단위테스트로 대조, test.md U-CFG-3).

---

## 4. 설정 · 환경변수

### 4.1 `.env.example` (키 이름만, 값 비움 + 한 줄 설명 주석)
```
# OpenAI — LightRAG 인덱싱·질의(gpt-6-luna, text-embedding-3-small)
OPENAI_API_KEY=
# 공공데이터포털 TourAPI(KorService2) 인증키 — "Decoding" 키를 넣는다(Encoding 키는 이중 인코딩으로 오류 30)
TOURAPI_SERVICE_KEY=
# 내부 토큰 — openssl rand -hex 32 로 생성
LIGHTRAG_API_KEY=
TOOLS_API_KEY=
# PostgreSQL 비밀번호 — 빈 볼륨 첫 기동 때만 적용된다
POSTGRES_PASSWORD=
APP_DB_PASSWORD=
TOOLS_DB_PASSWORD=
LIGHTRAG_DB_PASSWORD=
```
> TourAPI 키 Decoding/Encoding 구분은 공공데이터포털 화면 기준(**미확인** — httpx가 쿼리 파라미터를 다시 인코딩하므로 Decoding 키가 맞다는 추론).

### 4.2 `nadri.core.config.Settings` (pydantic-settings, `extra="ignore"`, `.env` 파일 직접 읽지 않음 — compose가 주입)
| 필드 (환경변수) | 타입 | 기본값 | 쓰는 곳 |
|---|---|---|---|
| `DB_HOST` | str | `postgres` | 전부 |
| `DB_PORT` | int | `5432` | 전부 |
| `DB_NAME` | str | `nadri` | 전부 |
| `DB_USER` | str | 필수 | ingest=`nadri_app`, tour-tools=`nadri_tools` |
| `DB_PASSWORD` | SecretStr | 필수 | compose가 `APP_DB_PASSWORD`/`TOOLS_DB_PASSWORD`를 넣음 |
| `TOURAPI_SERVICE_KEY` | SecretStr \| None | None | ingest |
| `TOURAPI_BASE_URL` | str | `https://apis.data.go.kr/B551011/KorService2` | ingest |
| `TOURAPI_TIMEOUT_S` | float | `15.0` | ingest |
| `TOURAPI_DAILY_INGEST_BUDGET` | int | `800` | ingest 실행 전 점검(§6.4) — ADR-14·G4 Q6 |
| `LIGHTRAG_URL` | str | `http://lightrag:9621` | ingest, tour-tools |
| `LIGHTRAG_API_KEY` | SecretStr \| None | None | ingest, tour-tools |
| `TOOLS_URL` | str | `http://tour-tools:8000/mcp` | ingest(`tools smoke`) |
| `TOOLS_API_KEY` | SecretStr \| None | None | tour-tools(검사), ingest(호출) |
| `WIKI_DIR` | Path | `/data/wiki` | ingest |
| `RAW_DIR` | Path | `/data/raw` | ingest |
| `RAG_CANDIDATES` | int | `30` | tour-tools (A9 대안 "후보 20" 대비) |
| `RAG_TOP_K` | int | `5` | tour-tools |
| `RERANKER_MODEL_PATH` | str | `/opt/models/bge-reranker-v2-m3` | tour-tools |
| `RERANKER_MAX_LENGTH` | int | `512` | tour-tools (A9 대안 "max_length 축소" 대비) |
| `INDEX_TIMEOUT_S` | int | `1800` | ingest(LightRAG 처리 대기 상한) |

- 서비스에 필요한 키가 없으면(예: ingest에서 `TOURAPI_SERVICE_KEY` 없음) 해당 명령 시작 시 `require(settings.tourapi_service_key, "TOURAPI_SERVICE_KEY")`로 한국어 메시지와 함께 종료 코드 2.
- `SecretStr`이라 `repr`·로그에 값이 나오지 않는다.

```python
class Settings(BaseSettings):
    """nadri 백엔드 공통 설정. 컨테이너 환경변수에서 읽는다(서비스마다 필요한 키만 주입됨)."""
    @property
    def database_url(self) -> str:
        """asyncpg 접속 URL(`postgresql+asyncpg://user:pw@host:port/db`). 비밀번호는 URL 인코딩한다."""

@lru_cache
def get_settings() -> Settings: ...
def require(value: SecretStr | None, name: str) -> str:
    """필수 비밀값을 꺼낸다. 없으면 한국어 안내와 함께 SystemExit(2)."""
```

### 4.3 `infra/lightrag/lightrag.env` (비밀 아님, 커밋)
| 키 | 값 | 비고 |
|---|---|---|
| `HOST` / `PORT` | `0.0.0.0` / `9621` | |
| `LLM_BINDING` / `LLM_MODEL` | `openai` / `gpt-6-luna` | S4 |
| `EMBEDDING_BINDING` / `EMBEDDING_MODEL` / `EMBEDDING_DIM` | `openai` / `text-embedding-3-small` / `1536` | NFR-32 — 바꾸면 전체 재인덱싱(F12) |
| `LIGHTRAG_KV_STORAGE` | `PGKVStorage` | |
| `LIGHTRAG_VECTOR_STORAGE` | `PGVectorStorage` | |
| `LIGHTRAG_DOC_STATUS_STORAGE` | `PGDocStatusStorage` | |
| `LIGHTRAG_GRAPH_STORAGE` | `PGTableGraphStorage` | F11 — AGE 불필요 |
| `POSTGRES_HOST` / `POSTGRES_PORT` / `POSTGRES_USER` / `POSTGRES_DATABASE` | `postgres` / `5432` / `lightrag` / `lightrag` | 비밀번호는 compose `environment` |
| `POSTGRES_VECTOR_INDEX_TYPE` | `HNSW` | |
| `SUMMARY_LANGUAGE` | `Korean` | A8 |
| `RERANK_BINDING` | `null` | 리랭크는 tour-tools CrossEncoder |

비밀값(compose `environment`): `LLM_BINDING_API_KEY=${OPENAI_API_KEY}`, `EMBEDDING_BINDING_API_KEY=${OPENAI_API_KEY}`, `LIGHTRAG_API_KEY=${LIGHTRAG_API_KEY}`, `POSTGRES_PASSWORD=${LIGHTRAG_DB_PASSWORD}`.
> **미확인**: 위 키 이름은 LightRAG v1.5.7 `env.example` 기준 추정(F11에서 일부 확인). 구현 첫 단계에서 v1.5.7 태그의 `env.example`과 대조해 다르면 그 이름을 쓰고 이 표를 고친다. 동시 처리 수(`MAX_PARALLEL_INSERT` 등)는 기본값.

---

## 5. Compose 서비스 정의 요지

### 5.1 공통
- `name: nadri` (네트워크 `nadri_default`). 호스트 `ports:` 없음(compose.yaml).
- 자체 이미지(tour-tools·ingest): `user` 비루트(이미지에서 uid 10001 `nadri`), `cap_drop: [ALL]`, `security_opt: ["no-new-privileges:true"]`, docker.sock 미마운트 [A] §9.
- `restart: unless-stopped`(ingest 제외).

### 5.2 서비스별
| 서비스 | 이미지/빌드 | 주입 환경변수 | 볼륨 | 기동 순서·헬스 |
|---|---|---|---|---|
| `postgres` | `pgvector/pgvector:pg18` | `POSTGRES_PASSWORD`, `APP_DB_PASSWORD`, `TOOLS_DB_PASSWORD`, `LIGHTRAG_DB_PASSWORD` | `pg-data:/var/lib/postgresql/data`(**미확인**: pg18 이미지의 데이터 경로가 바뀌었을 수 있음 — 이미지 문서로 확인), `./infra/postgres/init:/docker-entrypoint-initdb.d:ro` | healthcheck `pg_isready -U postgres` |
| `lightrag` | LightRAG 공식 이미지 **v1.5.7 태그 고정**(이미지 주소 **미확인** — 예: `ghcr.io/hkuds/lightrag:v1.5.7`) | §4.3 비밀값 4개 + `env_file: infra/lightrag/lightrag.env` | `lightrag-data:<작업 디렉터리>`(경로 **미확인** — v1.5.7 이미지의 `WORKING_DIR` 확인, Q7) | `depends_on: postgres(service_healthy)` |
| `ingest` | `build: {context: ./backend, target: app}` | `DB_USER=nadri_app`, `DB_PASSWORD=${APP_DB_PASSWORD}`, `TOURAPI_SERVICE_KEY`, `LIGHTRAG_API_KEY`, `TOOLS_API_KEY`, `LANGSMITH_TRACING=false`, `LANGCHAIN_TRACING_V2=false` | `wiki-data:/data/wiki`, `raw-data:/data/raw` | `depends_on: postgres(service_healthy)`. **기본 명령 `alembic upgrade head` 후 종료(0)**, `restart: "no"`. 적재는 `docker compose run --rm ingest nadri …` (Q1) |
| `tour-tools` | `build: {context: ./backend, target: tools}` | `DB_USER=nadri_tools`, `DB_PASSWORD=${TOOLS_DB_PASSWORD}`, `LIGHTRAG_API_KEY`, `TOOLS_API_KEY` | 없음 | `depends_on: postgres(service_healthy), lightrag(service_started), ingest(service_completed_successfully)`. healthcheck: `GET http://localhost:8000/health` → 200 (python 한 줄 스크립트, curl 의존 안 함) |

- `OPENAI_API_KEY`는 01에서 **lightrag에만** 주입. [A] §9는 ingest에도 주지만 01의 ingest는 OpenAI를 직접 부르지 않으므로 20(허브)에서 추가한다(NFR-09 "필요한 키만").
- `TOURAPI_SERVICE_KEY`는 01에서 **ingest에만**. tour-tools 주입은 10.
- 비루트 + named volume 권한: Dockerfile에서 `/data/wiki`·`/data/raw`를 `nadri:nadri`로 만들어 두면 빈 named volume 첫 마운트 때 소유권이 복사된다(Docker 동작). 구현 시 쓰기 확인.

### 5.3 `compose.dev.yaml`
- ingest·tour-tools: `./backend/src:/app/src`(소스 마운트 — 이미지의 editable 설치가 이 경로를 가리킴), `./backend/alembic:/app/alembic`.
- tour-tools: `command: uvicorn nadri.tools.server:build_app --factory --host 0.0.0.0 --port 8000 --reload --reload-dir /app/src`.
- 통합 테스트용 포트(WSL 안에서만 접속, `127.0.0.1` 바인드): postgres `127.0.0.1:5432`, lightrag `127.0.0.1:9621`, tour-tools `127.0.0.1:8001→8000`. 운영 `compose.yaml`에는 여전히 호스트 포트 없음.

### 5.3a 개발·테스트 환경 (Q4 결정, 2026-11-21)
- 코드 작성·테스트는 **WSL2 Ubuntu**에서 한다. uv를 설치하고 `backend/`에서 `uv sync`(Python 3.12는 uv가 받음, 시스템 Python 3.11 미사용) → `backend/.venv` 생성(`.gitignore` 대상). 리랭커 그룹은 받지 않는다(`uv sync --no-group reranker`, torch 불필요).
- 단위테스트: `cd backend && uv run pytest -m "not integration"`.
- 통합 테스트: compose를 dev 덮어쓰기로 띄운 뒤 접속 주소만 바꿔 실행 — `DB_HOST=127.0.0.1 LIGHTRAG_URL=http://127.0.0.1:9621 TOOLS_URL=http://127.0.0.1:8001/mcp uv run pytest -m integration` (비밀값은 레포 루트 `.env`에서 읽음).
- 서비스(postgres·lightrag·tour-tools·ingest)는 계속 Docker Compose로만 띄운다.

### 5.4 `backend/Dockerfile` (멀티 스테이지)
1. `base`: `python:3.12-slim` + `uv`(공식 이미지에서 바이너리 복사, 버전 고정), 사용자 `nadri`(uid 10001), `WORKDIR /app`, `/data/wiki`·`/data/raw` 생성·소유권.
2. `app`: `uv sync --frozen --no-dev --no-group reranker` → 소스 복사 → `USER nadri` → `CMD ["alembic","upgrade","head"]`.
3. `tools`: `uv sync --frozen --no-dev --group reranker` → 빌드 시 `huggingface_hub.snapshot_download("BAAI/bge-reranker-v2-m3", revision=<고정 커밋>, local_dir=/opt/models/bge-reranker-v2-m3)` → `ENV HF_HUB_OFFLINE=1` → `USER nadri` → `CMD ["nadri-tools"]`(= `nadri.tools.server:main`).
- torch는 **CPU 전용 휠**을 쓴다(`[tool.uv.sources]`에 pytorch CPU 인덱스 지정) — CUDA 휠은 수 GB가 더 붙는다. 가중치 약 2.3GB(**미확인**, 빌드 후 이미지 크기 기록).

### 5.5 `backend/pyproject.toml`
- `requires-python = ">=3.12,<3.13"`, `[project.scripts] nadri = "nadri.cli:main"`, `nadri-tools = "nadri.tools.server:main"`.
- 의존(01에서 쓰는 것만, `==`로 고정 — [A] §1 고정 후보 버전): `mcp==1.30.0`, `langchain-mcp-adapters==0.3.2`, `langchain-core==1.8.4`, `pydantic-settings`, `sqlalchemy[asyncio]`, `asyncpg`, `alembic`, `httpx`, `jinja2`, `uvicorn`. 버전 미지정 항목은 구현 시점 최신으로 `uv.lock`에 고정.
- 그룹 `reranker`: `torch`(CPU 인덱스), `sentence-transformers`, `huggingface-hub`. 그룹 `dev`: `pytest`, `pytest-asyncio`, `pyyaml`(frontmatter 파싱 테스트).
- `[tool.pytest.ini_options]`: `markers = ["integration: 실 compose·실 키가 필요한 테스트"]`, `asyncio_mode = "auto"`, 기본 실행에서 integration 제외는 명령에서 `-m "not integration"`.
- LangGraph·langchain-openai·FastAPI 등은 02에서 추가한다.

---

## 6. 모듈별 입출력 · 시그니처

주석 규칙([CL]): 모든 함수·클래스에 한국어 docstring(요약 → Args → Returns → Raises/부수효과), 함수 안 단계 주석 `# 1) …`. 아래 docstring은 요약 한 줄만 적었다.

### 6.1 `core/db.py`
```python
def create_engine(settings: Settings) -> AsyncEngine:
    """설정의 접속 정보로 asyncpg 엔진을 만든다(pool_size=5, pool_pre_ping=True)."""
def session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """expire_on_commit=False 세션 팩토리를 만든다."""
```

### 6.2 `core/tourapi.py`
상수:
```python
KST = ZoneInfo("Asia/Seoul")
AREAS: dict[str, dict[str, str]] = {"서울": {"areaCode": "1"}, "제주": {"areaCode": "39"}}
CONTENT_TYPES: dict[int, str] = {12: "관광지", 14: "문화시설", 15: "축제공연행사", 25: "여행코스",
                                 28: "레포츠", 32: "숙박", 38: "쇼핑", 39: "음식점"}
QUOTA_CODES = {"22"}       # 일일 한도 초과 (F7)
RATE_CODES = {"23"}        # 초당 한도 초과 (F7)
```
> **미확인**: KorService2가 `areaCode`(서울 1·제주 39)를 계속 받는지, 법정동 코드(`lDongRegnCd`) 체계로 바뀌었는지. 첫 실호출(A12)에서 확인해 `AREAS` 값만 바꾼다. 응답 필드명(`sigungucode`, `mapx`, `mapy`, `modifiedtime` 등)도 같은 시점에 확인한다.

```python
class TourApiError(Exception):
    """TourAPI 호출 실패. code는 공공데이터포털 resultCode/returnReasonCode 또는 'http_<상태>'·'timeout'·'parse'."""
    code: str
    message: str
    @property
    def quota_exceeded(self) -> bool: ...   # code in QUOTA_CODES
    @property
    def rate_limited(self) -> bool: ...     # code in RATE_CODES

@dataclass(frozen=True)
class TourApiResponse:
    """한 번의 TourAPI 호출 결과. body는 raw 저장용 원본, params에는 serviceKey가 없다."""
    operation: str
    params: dict[str, str]
    body: dict
    items: list[dict]
    total_count: int
    fetched_at: datetime   # KST tz-aware

def parse_response(operation: str, status_code: int, text: str) -> tuple[dict, list[dict], int]:
    """응답 본문을 해석해 (원본 dict, item 목록, totalCount)를 돌려준다. 오류 응답이면 TourApiError."""

class TourApiClient:
    """KorService2 비동기 클라이언트. 호출 1회마다 on_call 콜백으로 호출 수를 알린다."""
    def __init__(self, service_key: str, base_url: str, *, timeout: float = 15.0,
                 transport: httpx.AsyncBaseTransport | None = None,
                 on_call: Callable[[str], Awaitable[None]] | None = None,
                 clock: Callable[[], datetime] = lambda: datetime.now(KST)) -> None: ...
    async def area_based_list(self, area: str, content_type_id: int, *, num_of_rows: int, page_no: int = 1) -> TourApiResponse: ...
    async def detail_common(self, contentid: str) -> TourApiResponse: ...
    async def detail_intro(self, contentid: str, content_type_id: int) -> TourApiResponse: ...
    async def detail_info(self, contentid: str, content_type_id: int) -> TourApiResponse: ...
    async def aclose(self) -> None: ...
```
- 공통 파라미터: `serviceKey`, `MobileOS=ETC`, `MobileApp=nadri`, `_type=json`. 목록은 `numOfRows`, `pageNo`, `arrange=C`(수정일순 — 표본 선택 기준, **미확인**: v2 정렬 코드), `areaCode`, `contentTypeId`. 상세는 `contentId`(+`contentTypeId`). v2에서 `defaultYN` 등 플래그가 없어졌는지 **미확인** — 실호출로 확인.
- `parse_response` 규칙:
  1. HTTP 상태 ≠ 200 → `TourApiError("http_<상태>")`.
  2. 본문이 XML(`<OpenAPI_ServiceResponse>` 등 게이트웨이 오류)이면 `returnReasonCode`·`returnAuthMsg`를 정규식으로 뽑아 `TourApiError(code)`. 해석 못 하면 `code="parse"`.
  3. JSON이면 `response.header.resultCode`가 `"0000"`이 아니면 `TourApiError(resultCode, resultMsg)`.
  4. `response.body.items`가 `""`/없음 → `[]`, `items.item`이 dict 하나면 `[dict]`, list면 그대로.
  5. `totalCount` 없으면 0.
- 네트워크 타임아웃 → `TourApiError("timeout")`. **자동 재시도 없음**(호출 수를 아끼고 단순하게).
- `serviceKey`는 `TourApiResponse.params`·로그·예외 메시지에 넣지 않는다(httpx 요청 URL을 로그로 남기지 않음).
- `on_call`은 HTTP 요청을 **보낸 직후**(응답 성공 여부와 무관하게) 호출 — 실패 호출도 포털 트래픽에 잡힐 수 있어서(**미확인**, 보수적으로 셈).

### 6.3 `ingest/raw.py`
```python
def save_raw(raw_dir: Path, resp: TourApiResponse, key: str) -> Path:
    """응답 원본을 {raw_dir}/{KST 날짜}/{operation}/{key}.json 에 불변으로 저장하고 경로를 돌려준다."""
```
- `key`: 목록은 `{area}_{type}_p{page}`(예: `서울_12_p1`), 상세는 contentid. `[0-9A-Za-z가-힣_-]` 외 문자는 `_`로 바꾼다.
- 저장 내용: `{"operation", "params"(serviceKey 없음), "fetched_at", "body"}`, `ensure_ascii=False`, `indent=2`.
- **덮어쓰지 않는다**: `open(mode="x")`. 같은 경로가 있으면 `{key}.2.json`, `{key}.3.json` … 순번으로 새 파일(FR-40 불변).

### 6.4 `ingest/upsert.py`
```python
@dataclass(frozen=True)
class TourItemRecord:
    """tour_items 한 행에 넣을 값(updated_at·deleted_at 제외)."""
    contentid: str; content_type_id: int; area: str; sigungu_code: str | None; title: str
    addr: str | None; lat: float | None; lng: float | None; tel: str | None; usetime: str | None
    fee: str | None; restdate: str | None; event_start: date | None; event_end: date | None
    extra: dict; modifiedtime: datetime | None; detail_synced_at: datetime; as_of: date

def clean_text(value: str | None) -> str | None:
    """TourAPI 문자열의 HTML을 정리한다. <br> → 줄바꿈, 다른 태그 제거, 엔티티 해제, 앞뒤 공백 제거, 빈 값 → None."""

def build_record(area: str, common: dict, intro: dict, info: list[dict], fetched_at: datetime) -> TourItemRecord:
    """detailCommon2·detailIntro2·detailInfo2 item을 TourItemRecord로 바꾼다(순수 함수)."""

def build_upsert_stmt(rec: TourItemRecord) -> Insert:
    """INSERT … ON CONFLICT (contentid) DO UPDATE … WHERE 값이 달라졌을 때만, RETURNING (xmax = 0) 문을 만든다."""

async def upsert_tour_item(session: AsyncSession, rec: TourItemRecord) -> Literal["inserted", "updated", "unchanged"]:
    """한 건을 upsert하고 결과 종류를 돌려준다. 내용이 같으면 행을 건드리지 않는다(updated_at 유지)."""
```
매핑(타입 12 기준, 나머지 타입은 03):
| 컬럼 | 출처 |
|---|---|
| contentid, content_type_id, title | common `contentid`·`contenttypeid`(int)·`title` |
| area | 인자(`서울`/`제주`) |
| sigungu_code | common `sigungucode`(없으면 None) |
| addr | `addr1` + " " + `addr2` (공백 정리, 둘 다 없으면 None) |
| lat / lng | `mapy` / `mapx` → float, 빈 값·0 → None |
| tel | common `tel`, 없으면 intro `infocenter` |
| usetime, restdate | intro `usetime`, `restdate` |
| fee | info 목록에서 `infoname`에 "입장료" 또는 "이용요금"이 들어간 첫 항목의 `infotext`, 없으면 None (**미확인**: 타입 12 요금 위치) |
| event_start / end | None (15는 03) |
| extra | `{"overview": common.overview, "homepage": common.homepage, "intro": {매핑 안 한 intro 필드}, "info": [{"name": infoname, "text": infotext}]}` — 모든 문자열 `clean_text` 적용, 빈 값 키 제외 |
| modifiedtime | common `modifiedtime`(`%Y%m%d%H%M%S`, KST) — 형식 다르면 None |
| detail_synced_at | `fetched_at` |
| as_of | `fetched_at`의 KST 날짜 |

- 모든 문자열 컬럼에 `clean_text` 적용(raw에는 원문이 남는다).
- upsert의 `WHERE`: 갱신 대상 컬럼 묶음 `IS DISTINCT FROM` excluded 묶음. 내용이 같으면 RETURNING 행이 없어 `"unchanged"`. 갱신 시 `updated_at = now()`, `deleted_at = NULL`.
- 비교 대상: `detail_synced_at`을 **뺀** 나머지 값 컬럼 전부(`as_of` 포함). `detail_synced_at`은 비교하지 않고, 다른 컬럼이 바뀌어 갱신될 때만 함께 바뀐다 — 같은 날 재실행이 시각 차이만으로 `updated`가 되지 않게(멱등). 결과적으로 **다른 날 다시 받으면** 내용이 같아도 `as_of`가 바뀌어 `updated` → 페이지가 바뀌어 재인덱싱된다. 03 이후는 "상세 미수집" 큐로 같은 항목을 다시 받지 않으므로 수용한다.

### 6.5 `ingest/wiki/render.py` · `templates/entity.md.j2`
```python
SOURCE_LABEL = "한국관광공사 TourAPI 4.0 (KorService2)"

def entity_path(content_type_id: int, contentid: str) -> str:
    """엔티티 페이지 상대 경로 'entity/{유형}/{contentid}.md'를 만든다."""
def render_entity(item: TourItem) -> str:
    """tour_items 행 하나를 엔티티 마크다운으로 렌더한다(LLM 없음, 같은 입력 → 같은 출력)."""
def content_hash(text: str) -> str:
    """UTF-8 바이트의 sha256 16진 문자열."""
def write_page(wiki_dir: Path, rel_path: str, text: str) -> Path:
    """임시 파일에 쓰고 rename해 원자적으로 저장한다. 디렉터리는 자동 생성."""
```
- Jinja2 환경: `autoescape=False`, `StrictUndefined`, `trim_blocks=True`, `lstrip_blocks=True`, `keep_trailing_newline=True`, 커스텀 필터 `yq`(= `json.dumps(v, ensure_ascii=False)` — YAML 안전 인용 + 한글 그대로). 기본 `tojson`은 한글을 `\uXXXX`로 바꾸므로 쓰지 않는다.
- 결정성: 현재 시각·랜덤 값을 넣지 않는다. frontmatter `updated_at` = `tour_items.updated_at`(행이 바뀔 때만 바뀜), `as_of` = `tour_items.as_of`. extra의 키 순서는 고정(정렬).
- 템플릿 형태:
```markdown
---
contentid: "126508"
content_type_id: 12
title: "경복궁"
area: "서울"
sigungu_code: "23"
source: "한국관광공사 TourAPI 4.0 (KorService2)"
as_of: 2026-11-21
updated_at: "2026-11-21T10:00:00+09:00"
---
# 경복궁

관광지 ID: 126508 · 유형: 관광지 · 지역: 서울

## 개요
(overview)

## 기본 정보
- 주소: …
- 전화: …
- 이용시간: …
- 휴무일: …
- 이용요금: …

## 추가 정보
- (intro 나머지 필드·info 항목: "이름: 값")

---
출처: 한국관광공사 TourAPI 4.0 (공공누리), 기준일 2026-11-21
```
- 값이 없는 줄·빈 절은 출력하지 않는다("None"·빈 불릿 금지). `sigungu_code`가 None이면 frontmatter 키 생략.
- intro 필드 표시 이름: 01은 필드명 그대로(예: `parking: …`). 한글 라벨 매핑은 03 타입별 템플릿에서.
- **LightRAG에는 frontmatter 포함 파일 전체를 넣는다**(본문의 "관광지 ID: …" 줄과 함께 A7 대안 근거). frontmatter가 잡음 엔티티를 만들면 A8 대안으로 본문만 넣는다(§9).

### 6.6 `ingest/indexer.py`
```python
@dataclass(frozen=True)
class PageToIndex:
    """인덱싱 후보 페이지. old_*는 wiki_pages에 저장된 이전 값."""
    path: str; text: str; content_hash: str; old_hash: str | None; old_doc_id: str | None

@dataclass(frozen=True)
class IndexOutcome:
    """페이지 하나의 처리 결과."""
    path: str
    status: Literal["skipped", "indexed", "failed"]
    doc_id: str | None
    content_hash: str | None
    reason: str | None
    elapsed_s: float

class LightRagError(Exception): ...

class LightRagClient:
    """LightRAG 서버 문서 API 클라이언트(헤더 X-API-Key)."""
    def __init__(self, base_url: str, api_key: str, *, timeout: float = 60.0,
                 transport: httpx.AsyncBaseTransport | None = None) -> None: ...
    async def insert_text(self, text: str, file_source: str) -> str: ...          # track_id
    async def track_status(self, track_id: str) -> list[dict]: ...                # [{id, status, file_path, error?}]
    async def delete_documents(self, doc_ids: list[str]) -> None: ...
    async def document_exists(self, doc_id: str) -> bool: ...
    async def count_documents(self) -> dict[str, int]: ...                        # 상태별 문서 수
    async def aclose(self) -> None: ...

def needs_indexing(new_hash: str, old_hash: str | None, old_doc_id: str | None) -> bool:
    """새 해시가 저장 해시와 다르거나, 이전 인덱싱 기록(doc_id)이 없으면 True."""

async def index_pages(client: LightRagClient, pages: list[PageToIndex], *, timeout_s: float,
                      poll_interval_s: float = 5.0,
                      sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
                      clock: Callable[[], float] = time.monotonic) -> list[IndexOutcome]:
    """바뀐 페이지만 LightRAG에서 delete→insert하고 처리 완료까지 기다려 결과를 돌려준다(DB는 건드리지 않음)."""

async def apply_outcomes(session: AsyncSession, outcomes: list[IndexOutcome]) -> None:
    """indexed는 content_hash·lightrag_doc_id·indexed_at 저장, failed는 셋 다 NULL로 비워 다음 실행에서 재시도."""
def outcome_to_values(o: IndexOutcome, now: datetime) -> dict | None:
    """apply_outcomes가 쓰는 순수 함수: 결과 하나를 wiki_pages 갱신 값으로 바꾼다(skipped면 None)."""
```
`index_pages` 처리 순서:
1. `needs_indexing`이 False인 페이지 → `skipped`(HTTP 호출 없음).
2. 나머지 페이지마다 순서대로: `old_doc_id`가 있으면 `delete_documents([old_doc_id])` → `document_exists`가 False가 될 때까지 폴링(삭제가 비동기일 수 있음, **미확인** A16). 삭제 실패·타임아웃이면 그 페이지 `failed`(insert 하지 않음 — 중복 방지 우선).
3. `insert_text(text, file_source=path)` → track_id 수집.
4. 모든 track_id를 `poll_interval_s`마다 `track_status`로 확인, 문서 상태가 처리 완료(`processed`, **미확인**: 상태 문자열)면 `indexed`+doc_id, 실패(`failed`)면 `failed`+error, `timeout_s` 경과면 남은 것 모두 `failed("timeout")`.
- **엔드포인트 미확인**(A16): `POST /documents/text`(본문 `{text, file_source}` → `track_id`), `GET /documents/track_status/{track_id}`, `DELETE /documents/delete_document`(본문 `{doc_ids, …}`), 문서 목록/상태 조회 경로. 구현 첫 단계에서 v1.5.7 `document_routes.py`로 확인하고 이 절을 고친다.
- LightRAG는 문서 ID를 내용 해시로 만드는 것으로 알려져 있다(**미확인**). 그래서 내용이 바뀌면 doc_id가 바뀌고 이전 문서를 지우지 않으면 중복이 남는다 → 2) 단계가 필수.
- 해시가 같아도 `old_doc_id`가 LightRAG에 실제로 없는 경우(수동 삭제 등)는 01에서 감지하지 않는다(상태 대조는 20 lint 범위).

### 6.7 `ingest/bootstrap.py`
```python
@dataclass
class BootstrapResult:
    """한 번의 적재 실행 요약(ingest_runs.stats에 그대로 저장)."""
    run_id: int; calls: int; listed: int
    upserted: dict[str, int]            # inserted/updated/unchanged
    pages_written: int
    indexed: int; skipped: int; failed: int
    index_elapsed_s: float; elapsed_s: float
    errors: list[str]                   # "contentid: 사유"

def estimate_calls(limit: int) -> int:
    """이번 실행 예상 호출 수 = 목록 1 + 상세 3 × limit."""
def budget_allows(used_today: int, estimated: int, budget: int) -> bool:
    """오늘 ingest 사용량 + 예상 호출 ≤ 예산이면 True. (01의 최소 점검 — 강제 예산은 03)"""
def validate_args(area: str, content_type_id: int, limit: int) -> None:
    """bootstrap 인자를 검사한다(area ∈ AREAS, 유형 12만, 1 ≤ limit ≤ 50). 어긋나면 ValueError."""
def estimate_days(totals: dict[tuple[str, int], int], budget: int, rows_per_list_call: int = 100) -> dict[str, int]:
    """totalCount 표로 적재 일수를 두 가지로 추정한다 {"service_wide": …, "per_operation": …} (§9 식)."""

async def record_call(sf: async_sessionmaker[AsyncSession], day: date, kind: Literal["ingest"] = "ingest") -> None:
    """ingest_state 'tourapi_calls:{day}'의 kind 카운터를 원자적으로 +1 한다(INSERT … ON CONFLICT … jsonb_set)."""
async def calls_today(sf, day: date) -> dict[str, int]: ...

async def run_bootstrap(area: str, content_type_id: int, limit: int, *, settings: Settings,
                        sf: async_sessionmaker[AsyncSession], tourapi: TourApiClient,
                        lightrag: LightRagClient) -> BootstrapResult:
    """목록 1페이지(limit건) → 건별 상세 3종 → raw → upsert → 렌더·파일 → wiki_pages → 바뀐 페이지 인덱싱."""
async def run_reindex(contentids: list[str] | None, *, settings, sf, lightrag) -> BootstrapResult:
    """TourAPI 없이 tour_items에서 다시 렌더해 바뀐 페이지만 인덱싱한다(A16 확인용)."""
async def count_totals(tourapi: TourApiClient, areas: list[str], types: list[int]) -> dict[tuple[str, int], int]:
    """지역×유형별 totalCount를 numOfRows=1 목록 호출로 센다(16호출)."""
    # count는 raw를 저장하지 않는다(측정용 호출). 호출 수는 기록한다.
```
`run_bootstrap` 처리 순서:
1. 인자 검증: `area ∈ AREAS`, `content_type_id == 12`(01 템플릿은 관광지만 — 다른 유형은 03까지 거부), `1 ≤ limit ≤ 50`.
2. 예산 점검: `budget_allows(calls_today()["ingest"], estimate_calls(limit), TOURAPI_DAILY_INGEST_BUDGET)`가 False면 시작하지 않고 종료 코드 3.
3. `ingest_runs`에 `kind=bootstrap, status=running` 행 생성.
4. `area_based_list(area, type, num_of_rows=limit)` → raw 저장.
5. 항목마다: 상세 3종 호출·raw 저장 → `build_record` → upsert(항목마다 커밋) → 렌더 → `write_page` → `wiki_pages` upsert(path·kind=entity·contentid·title·area·sigungu_code·as_of만; 해시·doc_id는 건드리지 않음).
   - 항목 하나의 `TourApiError`(한도 외)·매핑 오류 → `errors`에 기록하고 다음 항목.
   - `quota_exceeded`/`rate_limited` → 남은 항목 중단, 이미 받은 것은 유지하고 6)으로.
6. 이번 실행에서 쓴 페이지들을 `PageToIndex`로 만들어 `index_pages` → `apply_outcomes`.
7. `ingest_runs` 갱신: `finished_at`, `stats=asdict(result)`, `status = failed`(한도 중단·인덱싱 실패 1건 이상·예외) / `done`. 예외는 `error`에 메시지(비밀값 없음) 저장 후 다시 던진다.
- 호출 수 기록: `TourApiClient(on_call=lambda op: record_call(sf, today))`.
- 표준 출력: 진행 줄(`[12/30] 126508 경복궁 inserted`)과 마지막 요약 JSON.

### 6.8 `tools/` — MCP 서버와 툴 3종

#### 공통 출력 규칙 (ADR-05)
- 모든 툴은 dict(JSON)를 돌려준다. 항목 목록이 있는 결과는 `{"items": [...], "count": n}`, 각 항목에 `contentid`·`source`·`as_of` 필수.
- 입력 오류는 `ValueError`(FastMCP가 `isError` 결과로 변환), 외부 오류(LightRAG·DB)는 한국어 짧은 메시지의 예외 — 내부 URL·키·스택은 메시지에 넣지 않는다.
- 로그: 툴 호출마다 한 줄 `tool=<이름> ms=<총> …`(인자 원문은 남기지 않음 — 02 이후 가린 텍스트가 들어와도 같은 규칙).

#### `tools/server.py`
```python
@dataclass
class ToolDeps:
    """툴 함수가 쓰는 공유 자원(서버 기동 시 1회 생성)."""
    settings: Settings
    sf: async_sessionmaker[AsyncSession]       # nadri_tools 롤
    lightrag_http: httpx.AsyncClient
    reranker: CrossEncoderReranker

class BearerAuthMiddleware:
    """Authorization: Bearer <TOOLS_API_KEY>가 맞을 때만 내부 앱으로 넘기는 순수 ASGI 미들웨어."""
    def __init__(self, app: ASGIApp, token: str) -> None: ...
    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None: ...

def build_mcp(deps: ToolDeps) -> FastMCP:
    """FastMCP('nadri-tour-tools', stateless_http=True)에 rag_query·data_query·get_datetime을 등록한다."""
def build_app() -> ASGIApp:
    """설정을 읽어 ToolDeps·FastMCP를 만들고 streamable_http_app()을 인증 미들웨어로 감싼다(uvicorn --factory용)."""
def main() -> None:
    """리랭커를 미리 올린 뒤 uvicorn으로 0.0.0.0:8000에서 서비스한다."""
```
- 미들웨어 규칙: `scope["type"] != "http"`(lifespan 등) → 그대로 통과. `GET /health` → 토큰 없이 200 `ok`(헬스체크 전용, 다른 정보 없음). 그 외 → 헤더가 정확히 `Bearer <token>`이고 `hmac.compare_digest`로 같으면 통과, 아니면 401 `{"error":"unauthorized"}`(본문에 이유 구분 없음). 토큰이 빈 문자열이면 `build_app`이 기동을 거부.
- MCP 경로는 FastMCP 기본 `/mcp`. 끝 슬래시 리다이렉트(307) 여부 **미확인** — 어댑터가 따라가지 못하면 클라이언트 URL을 맞춘다.
- 툴 등록은 각 모듈의 함수를 `deps`를 묶은 얇은 래퍼로 등록한다. 래퍼 docstring = LLM이 보는 툴 설명(한국어, 짧게, 고정 문자열 — NFR-40 고정 프리픽스).

#### `tools/rag_query.py`
```python
@dataclass(frozen=True)
class Candidate:
    """LightRAG 후보 문단 하나."""
    chunk_id: str | None; file_path: str | None; content: str

def parse_query_data(payload: dict) -> list[Candidate]:
    """/query/data 응답에서 청크 목록을 뽑는다(순수 함수). 형식이 다르면 LightRagError."""
async def fetch_candidates(http: httpx.AsyncClient, question: str, *, top_k: int) -> tuple[list[Candidate], dict]:
    """POST /query/data {query, mode:'mix', top_k, chunk_top_k} → (후보, 원본 응답)."""
async def rag_query(question: str, deps: ToolDeps,
                    lookup_pages: Callable[[list[str]], Awaitable[dict[str, PageMeta]]] | None = None) -> dict:
    """질문으로 위키 문단 후보 30개를 받아 리랭크하고 상위 5개를 출처·기준일과 함께 돌려준다."""
```
처리 순서:
1. `question` 앞뒤 공백 제거, 비었거나 500자 초과면 `ValueError`.
2. `fetch_candidates(top_k=RAG_CANDIDATES)` — 타임아웃 30초. 실패 → 예외 "지식 검색을 할 수 없습니다".
3. 후보 0개 → `{"items": [], "count": 0}` (리랭커 호출 안 함).
4. `rerank(question, [c.content …])` → 상위 `RAG_TOP_K` 인덱스.
5. 상위 후보의 `file_path`로 `wiki_pages` 조회(`path IN (...)`) → 메타가 없는 후보는 버린다(삭제 경합 등). 버린 뒤 5개가 안 되어도 채우지 않는다.
6. 결과 항목: `{"contentid", "title", "source": SOURCE_LABEL, "as_of": "YYYY-MM-DD", "path", "score": float(소수 4자리), "text": 청크 원문}`. 점수 내림차순.
7. 로그: `tool=rag_query candidates=<n> lightrag_ms= rerank_ms= total_ms=` (A9·A7 측정용).
- 요청 본문의 `top_k`/`chunk_top_k` 의미, 응답의 `data.chunks[].file_path` 존재 여부는 **미확인**(A7). 같은 페이지의 청크 여러 개는 합치지 않는다(엔티티 페이지는 대부분 1청크로 예상 — A7에서 기록).
- `PageMeta`(`contentid`, `title`, `as_of`)는 rag_query.py 안의 작은 dataclass. `lookup_pages` 기본값은 `deps.sf`로 SELECT하는 함수(테스트에서 대체).

#### `tools/reranker.py`
```python
class CrossEncoderReranker:
    """bge-reranker-v2-m3 CrossEncoder를 CPU에서 돌려 질문-문단 쌍 점수를 낸다. sentence_transformers는 생성자에서 지연 import."""
    def __init__(self, model_path: str, max_length: int = 512) -> None: ...
    def score(self, query: str, passages: Sequence[str]) -> list[float]: ...

def top_k_indices(scores: Sequence[float], k: int) -> list[int]:
    """점수 내림차순 상위 k개 인덱스. 동점이면 원래 순서(LightRAG 순위)를 유지한다."""
async def rerank(reranker, query: str, passages: Sequence[str], k: int) -> list[tuple[int, float]]:
    """score를 스레드에서 실행(이벤트 루프 막지 않음)하고 (인덱스, 점수) 상위 k개를 돌려준다."""
```
- 모델 로드는 `main()`에서 1회(첫 요청 지연 방지). `HF_HUB_OFFLINE=1`이라 런타임 다운로드 없음.

#### `tools/data_query.py`
```python
class NearPoint(BaseModel):
    """주변 검색 기준점."""
    lat: float = Field(ge=-90, le=90); lng: float = Field(ge=-180, le=180)
    radius_km: float = Field(default=3.0, gt=0, le=20)

class DataQueryParams(BaseModel):
    """data_query 입력. LLM이 채우는 값이라 엄격히 검증한다."""
    area: Literal["서울", "제주"]
    sigungu_code: str | None = Field(default=None, pattern=r"^\d{1,5}$")
    content_type: Literal[12, 14, 15, 25, 28, 32, 38, 39] | None = None
    keyword: str | None = Field(default=None, max_length=50)   # 공백만이면 None
    near: NearPoint | None = None
    on_date: date | None = None
    sort: Literal["title", "distance", "modified"] = "title"
    limit: int = Field(default=10, ge=1)                        # 20 초과는 20으로 낮춤

def escape_like(s: str) -> str:
    """LIKE 와일드카드(\\, %, _)를 이스케이프한다."""
def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """두 좌표 사이 대원 거리(km, 지구 반지름 6371.0088)."""
def bounding_box(lat: float, lng: float, radius_km: float) -> tuple[float, float, float, float]:
    """반경을 덮는 (min_lat, max_lat, min_lng, max_lng) — SQL 1차 거르기용."""
def build_select(p: DataQueryParams) -> Select:
    """검증된 파라미터로 SQLAlchemy Select를 만든다. 모든 값은 바인드 파라미터(문자열 SQL 조립 없음)."""
def apply_near(rows: list[dict], near: NearPoint, sort_by_distance: bool, limit: int) -> list[dict]:
    """거리 계산·반경 필터·(선택) 거리순 정렬 후 limit개로 자른다. 각 행에 distance_km 추가."""
def row_to_item(row: Mapping[str, Any]) -> dict:
    """DB 행을 툴 결과 항목(dict)으로 바꾼다. 날짜는 ISO 문자열, source 추가, extra 제외."""
async def data_query(p: DataQueryParams, deps: ToolDeps) -> dict:
    """tour_items를 조건으로 조회해 항목 목록을 돌려준다."""
```
조회 규칙:
1. 항상 `deleted_at IS NULL AND area = :area`.
2. `sigungu_code`·`content_type` 같음 조건. `keyword` → `title ILIKE :kw OR addr ILIKE :kw` (`%escape_like(kw)%`, `escape='\\'`).
3. `on_date` → `event_start <= :d AND event_end >= :d` (행사 기간이 없는 행은 제외 — 운영시간 해석은 `usetime` 원문을 LLM이 함, [A] §2.1).
4. `near` → 좌표 NOT NULL + bounding box 조건, SQL `LIMIT 500`(안전 상한) → Python `apply_near`.
5. `sort=distance`인데 `near` 없음 → `ValueError`. `title` → `title, contentid`. `modified` → `modifiedtime DESC NULLS LAST, contentid`.
6. `limit` > 20 → 20. near 없을 때는 SQL `LIMIT`.
7. 항목: `contentid, title, content_type_id, area, sigungu_code, addr, lat, lng, tel, usetime, fee, restdate, event_start, event_end, as_of, source(SOURCE_LABEL)` (+`distance_km` 소수 2자리). `extra`는 넣지 않는다(서술 정보는 rag_query).

#### `tools/get_datetime.py`
```python
def datetime_info(now: datetime) -> dict:
    """tz-aware 시각을 KST로 바꿔 날짜·요일·이번 주말·다음 주 범위를 계산한다(순수 함수). naive면 ValueError."""
async def get_datetime() -> dict:
    """현재 시각으로 datetime_info를 돌려준다(툴 진입점)."""
```
- 출력: `{"now": ISO8601(+09:00, 초 단위), "date", "weekday": "토요일", "timezone": "Asia/Seoul", "this_weekend": {"start","end"}, "next_week": {"start","end"}, "source": "시스템 시계", "as_of": date}`.
- **이번 주말** = 오늘이 속한 주(월~일)의 토~일. 토요일이면 오늘~내일, **일요일이면 어제~오늘**. **다음 주** = 다음 월요일~일요일. 이 정의를 툴 설명에도 한 줄로 적는다.
- 항목 목록이 아니라 contentid가 없다(ADR-05의 "항목마다"는 목록형 결과에 적용 — 해석).

### 6.9 `cli.py` (argparse, `nadri` 진입점)
| 명령 | 동작 | 서비스 |
|---|---|---|
| `nadri ingest bootstrap --area 서울 --type 12 --limit 30` | §6.7 `run_bootstrap` | ingest |
| `nadri ingest reindex [--contentid ID ...]` | §6.7 `run_reindex`, LightRAG 문서 수 전후(`count_documents`) 출력 | ingest |
| `nadri ingest count` | 서울·제주 × 8종 `totalCount` 표 + 적재 일수 추정(§9 A12 공식), 16호출(예산 점검 적용) | ingest |
| `nadri tools smoke [--question TEXT] [--repeat N]` | `langchain-mcp-adapters` `MultiServerMCPClient({"tour": {"transport": "streamable_http", "url": TOOLS_URL, "headers": {"Authorization": "Bearer …"}}})`로 툴 목록 → 3종 각각 호출(기본 질문 "경복궁 관람 시간과 휴무일", data_query `{area:"서울", keyword:"궁", limit:5}`, get_datetime) → 이름·소요 ms·결과 요약 출력. `--repeat`은 rag_query만 N회(A9 측정) | ingest |
| `nadri lightrag sample --query TEXT [--limit 20]` | `/query/data` 원본에서 엔티티·관계 상위 N개를 표로 출력(A8 HITL) | ingest |
- 종료 코드: 성공 0, 실행 실패 1, 설정·인자 오류 2, 예산 초과로 시작 안 함 3.
- 모든 명령은 `asyncio.run`으로 실행, 끝에서 HTTP 클라이언트·엔진 정리.

---

## 7. 엣지케이스 정리
| 상황 | 동작 |
|---|---|
| TourAPI 키 미등록·활성화 전(오류 30 등) | 첫 호출에서 `TourApiError` → 실행 `failed`, 메시지에 코드 표시. 키는 발급 후 활성화까지 시간이 걸릴 수 있음(**미확인**) |
| 일일 한도(22)·초당 한도(23) | 남은 항목 중단, 받은 것만 인덱싱, `failed` + 사유 |
| 게이트웨이 XML 오류 본문 | `parse_response`가 XML에서 코드 추출 |
| `items` 빈 문자열/단일 dict | 빈 목록/한 원소 목록으로 정규화 |
| 좌표 0·빈 값 | lat/lng None → data_query near 결과에서 제외 |
| HTML 섞인 텍스트(`<br>`, `&amp;`) | DB·위키는 정리된 텍스트, raw는 원문 |
| 같은 날 bootstrap 재실행 | upsert `unchanged`, 페이지 같음 → 인덱싱 `skipped`, raw는 순번 파일로 추가 저장(호출은 다시 소모) |
| 페이지 내용 변경 | 이전 doc 삭제 확인 후 insert, 성공 시 해시·doc_id 교체 |
| LightRAG 삭제 실패 | 그 페이지 insert 안 함(중복 방지), `failed`, 해시 유지 → 다음 실행 재시도 |
| insert 후 처리 실패/타임아웃 | `failed`, wiki_pages 해시·doc_id NULL → 다음 실행에서 다시 insert |
| LightRAG 다운 상태에서 rag_query | 툴 오류 결과(한국어 짧은 메시지) |
| 후보 file_path가 wiki_pages에 없음 | 그 후보 버림 |
| MCP 토큰 없음/틀림/`Bearer` 접두어 없음 | 401, 이유 구분 없는 같은 본문 |
| data_query `limit` 0·음수 | 검증 오류 / 21 이상 → 20 |
| data_query 키워드에 `%`·`_`·`'` | 이스케이프된 바인드 값, SQL 문자열 불변 |
| `sort=distance` + near 없음 | 검증 오류 |
| get_datetime 일요일 호출 | 이번 주말 = 어제~오늘 |
| 연말(12-31 목) | 이번 주말 2027-01-02~03 |
| `.env` 비밀번호 변경 후 재기동 | 반영 안 됨(빈 볼륨에서만 init) — 문서화 |
| tour-tools 기동 시 테이블 생성 스크립트 전 | `depends_on: ingest(service_completed_successfully)`로 순서 보장 |

---

## 8. 완료 기준 (DoD)
1. `docker compose up -d`로 postgres(healthy)·lightrag(running)·tour-tools(healthy) 기동, ingest는 테이블 생성 스크립트 후 **종료 코드 0**. `docker compose ps`에 게시된 호스트 포트 없음.
2. `nadri_tools` 롤: `tour_items`·`wiki_pages` SELECT 가능, 그 외 테이블 SELECT·모든 테이블 INSERT/UPDATE/DELETE는 권한 거부. `lightrag` DB 접속 불가.
3. 4테이블과 컬럼 COMMENT가 §3.2 표(=ERD)와 같다.
4. 서울 30 + 제주 20 실적재: raw 파일(목록 2 + 상세 150), `tour_items` 50행, 위키 md 50개, `wiki_pages` 50행 모두 `content_hash`·`lightrag_doc_id`·`indexed_at` 채워짐, `ingest_runs` 2행 `done`, `ingest_state` 호출 수 = 실제 호출 수.
5. `nadri tools smoke`(langchain-mcp-adapters)로 툴 3종 호출 성공. 토큰 없음·틀림 → 401.
6. `rag_query` 결과 최대 5개, 각 항목 `contentid`·`source`·`as_of`가 비어 있지 않고 `contentid`가 `tour_items`에 있다.
7. 같은 페이지 재실행(`reindex`) → 전부 `skipped`, LightRAG 문서 수 불변. 한 행을 바꾸고 `reindex` → 그 페이지만 delete→insert, 이전 doc_id 없음, 문서 수 불변.
8. 단위테스트 전부 통과(`-m "not integration"`), 통합 테스트 통과.
9. §9 가정 6개 판정 결과와 측정치(인덱싱 비용·시간 → 최초 인덱싱 비용 재추정, CrossEncoder 30쌍 지연, `totalCount` → 적재 일수)를 §10 표에 기록하고 `PROGRESS.md` 결정 로그에 요약. 실패 → 대안 중 사용자 확인 항목은 **멈추고 묻는다**.
10. 코드 주석 규칙 준수(한국어 docstring + 단계 주석), `CLAUDE.md` "명령어" 절에 빌드·테스트·적재·스모크 명령 기록.
11. 커밋은 `feat/01-e2e-tools-slice` 브랜치, `[Feat] …` + 작업 목록 + `Author:` 줄, AI 공동작성 표기 없음(NFR-73). `dev` 병합은 G5 승인 후.

---

## 9. 가정 판정 방법

| 가정 | 확인 방법 | 통과 | 실패 / 대안 |
|---|---|---|---|
| **A7** `/query/data`가 청크·문서 식별자 반환, 후보 ~30 조절 | 1) v1.5.7 `query_routes.py`로 요청·응답 스키마 확인 2) `nadri lightrag sample`·통합 테스트로 실제 응답 저장(키 이름 기록) 3) `top_k`/`chunk_top_k`=30 요청 시 청크 수, 10/20으로 바꿨을 때 수 변화 | 청크마다 `file_path`(= 넣은 `file_source`)가 있어 `wiki_pages.path`로 100% 매핑되고, 요청 값으로 후보 수가 조절됨(위키 50페이지라 30 미만일 수 있음 — 그 경우 "요청 값 이하로 줄어드는지"로 판단) | file_path 없음/변형 → 청크 본문 "관광지 ID: N" 줄(또는 frontmatter `contentid`)을 정규식으로 뽑아 매핑(코드 변경, 사용자 확인 불필요). 후보 수 조절 불가 → 받은 만큼 쓰고 기록. 둘 다 안 되면 LightRAG 라이브러리 직접 사용 → ADR-06 변경이라 **사용자 확인** |
| **A8** 한국어 엔티티 추출 품질 | 50페이지 인덱싱 후 `nadri lightrag sample --query`를 "경복궁", "성산일출봉", "한라산" 등 3개로 실행 → 엔티티·관계 10~20개씩 사용자에게 제시 | 사용자 판단 "쓸 만함". 참고 기준(제안): 엔티티 80% 이상이 한국어 고유명사·시설·지역으로 올바름, frontmatter 키(`source`, `as_of` 등)가 엔티티로 잡히지 않음, 관계 70% 이상 의미가 맞음 | ① frontmatter 제거 후 본문만 인덱싱 ② LightRAG 엔티티 유형·프롬프트 조정 ③ 질의 `naive` 비교 ④ 인덱싱만 상위 모델 → **사용자 확인**(비용·D-05). ①②는 재인덱싱 비용(50페이지분)만 듦 |
| **A9** CPU CrossEncoder 30쌍 지연 | `nadri tools smoke --repeat 10`(워밍업 1회 제외) → tour-tools 로그 `rerank_ms`로 p50·p95, 컨테이너 CPU 정보(`nproc`, 모델명) 기록. 후보가 30 미만이면 실제 개수도 기록하고, 별도로 30개 문단(위키 페이지 본문 반복)으로 `CrossEncoderReranker.score`를 직접 10회 측정 | p95 ≤ 2.0초 (TECH_STACK "+1~2초" 기준 — Q3) | 2~5초: `RERANKER_MAX_LENGTH=256`, `RAG_CANDIDATES=20`으로 재측정, 통과하면 설정값만 바꾸고 기록. 그래도 초과 또는 5초 초과: ONNX 변환·리랭커 끔·GPU → **사용자 확인** |
| **A12**(일부) TourAPI 실제 호출·`totalCount`·한도 단위 | 1) 실적재 호출 성공·응답 필드 기록(`areaCode` 체계, `sigungucode`·`mapx/mapy`·`modifiedtime` 유무, 타입 12 요금 위치) 2) `nadri ingest count`로 16칸 `totalCount` 3) `ingest_state` 호출 수와 공공데이터포털 마이페이지 트래픽 표시를 대조하고, 한도가 오퍼레이션별인지 서비스 전체인지 화면으로 확인(사용자) | 호출 성공, 16칸 기록, 셈이 포털과 일치, 한도 단위 확인(못 하면 "미확인 — 서비스 전체로 보수 가정" 기록) | 키 오류 → 재발급·활성화 대기. 필드명 다름 → 매핑·`AREAS` 수정(코드). 적재 일수가 길면 운영계정 트래픽 증설 신청 여부 → **사용자 확인**(03에서 최종) |
| **A16** delete→insert·상태 조회 경로 | 1) v1.5.7 `document_routes.py`로 insert·track_status·delete·문서 조회 경로 확인 2) DoD 7 절차(재실행 skipped → 행 수정 → reindex) 3) 삭제 후 이전 doc_id 조회 결과, 문서 수 전후, 수정 내용이 `rag_query`에 반영되는지 | 재실행 시 LightRAG 호출 0, 수정 시 이전 doc 없음 + 새 doc 1개 + 문서 수 불변 + 새 내용 검색됨 | 삭제가 비동기·파이프라인 busy로 거부 → 폴링·재시도 간격 조정(코드). doc_id로 삭제 불가 → file_path 기준 삭제·해시 문서 ID(코드). 그래프 엔티티가 지워지지 않고 남음 → 기록 후 "정기 전체 재인덱싱" 정책 여부 **사용자 확인** |
| **A21** 어댑터 0.3.2 ↔ mcp 1.30 FastMCP, `headers` 토큰 | `uv.lock`에서 `mcp==1.30.0`·`langchain-mcp-adapters==0.3.2` 확인 → `nadri tools smoke`로 `get_tools()` 3종·스키마·호출 결과 → 통합 테스트로 토큰 없음/틀림 401, 맞음 200 | 3종 모두 호출 성공, 401/200 구분 | 어댑터가 헤더를 안 보냄 → 어댑터 `httpx_client_factory` 등으로 헤더 주입(코드). 버전 비호환 → `mcp>=1.24,<2` 범위 다른 버전(코드, 기록). 토큰 전달 자체 불가 → 내부망 신뢰로 퇴화(NFR-08 영향) **사용자 확인** |

**측정치 계산식**
- 인덱싱 비용: OpenAI 대시보드(Usage) 적재 전후 차이 ÷ 50 = 페이지당 비용 → × Σ`totalCount`(서울·제주 8종) = 최초 인덱싱 비용 재추정(기존 추정 $15~30). 대시보드 반영 지연이 있으므로 다음 날 확인 가능(**미확인**). LightRAG 내부 호출은 앱에서 셀 수 없음(A14).
- 인덱싱 시간: `BootstrapResult.index_elapsed_s` ÷ 인덱싱된 페이지 수 → × 전체 페이지 수.
- 적재 일수: 서비스 전체 한도라면 `ceil((Σ ceil(totalCount/100) + 3 × ΣtotalCount) / 800)`(목록 1회 100건 가정), 오퍼레이션별 한도라면 `ceil(ΣtotalCount / 800)`(상세 오퍼레이션 하나가 병목). 둘 다 기록.

## 10. 판정 결과 기록 (구현 시 채움)
| 가정·측정 | 결과 | 수치 | 판정 | 후속 |
|---|---|---|---|---|
| A7 | | | | |
| A8 | | | | |
| A9 | | p50 / p95 | | |
| A12 | | 16칸 totalCount, 한도 단위 | | |
| A16 | | | | |
| A21 | | | | |
| 인덱싱 비용·시간 | | 페이지당 $·초, 전체 추정 | | |
| 적재 일수 | | | | |
| 이미지 크기 | | app / tools | | |

---

## 11. 확인 질문
| # | 질문 | 추천안 | 대안 |
|---|---|---|---|
| Q1 | 테이블 생성 스크립트 실행 주체와 01의 ingest 기동 방식 — 문서에 정해져 있지 않다 | **결정(2026-11-21): 추천안대로** — **ingest 기본 명령 = `alembic upgrade head` 후 종료**(one-shot), tour-tools는 그 완료를 기다림. 21에서 ingest가 상주 스케줄러가 될 때 "테이블 생성 스크립트 실행 후 스케줄러 시작"으로 바꾼다 | B: 별도 `migrate` 서비스(컨테이너 수 증가, ADR-01과 어긋남) / C: 02의 api 기동 시 실행(01에선 수동) |
| Q2 | `nadri_tools`의 테이블 SELECT 권한을 init 스크립트가 아니라 테이블 생성 스크립트 `0001`의 `GRANT`로 부여 (init 시점에 테이블 없음) | **결정(2026-11-21): 추천안대로** (init은 롤·CONNECT·USAGE만) | B: init에서 `ALTER DEFAULT PRIVILEGES … GRANT SELECT ON TABLES` — 앱 테이블 14개(04)에도 자동 부여돼 NFR-07 위반 |
| Q3 | A9 통과 기준 수치 | **결정(2026-11-21): 추천안대로** — **30쌍 p95 ≤ 2.0초** 통과, 2~5초는 설정 조정 후 재측정 | 다른 기준(예: 3초) |
| Q4 | 테스트 실행 위치 | **결정(2026-11-21): WSL2 Ubuntu에 uv + `backend/.venv`**, 단위·통합 테스트 모두 WSL에서 실행. 서비스는 Docker Compose(§5.3a) | (폐기) compose `test` 서비스 |
| Q5 | CLI 하위 명령 추가 — [PL]은 `ingest bootstrap`만 적었지만 측정·판정에 `ingest reindex`(A16), `ingest count`(A12), `tools smoke`(A21·A9), `lightrag sample`(A8)이 필요 | **결정(2026-11-21): 추천안대로** — **4개 추가** (각각 수십 줄) | B: 통합 테스트·일회성 스크립트로 대체(사용자가 결과를 직접 보기 어려움) |
| Q6 | TourAPI 공유 카운터(G4 Q6) — 01은 ingest 호출 수 기록 + 실행 전 "오늘 사용량 + 예상 ≤ 800" 점검만 한다. 10의 `tour_live`는 tour-tools(SELECT 전용 롤)에서 호출되므로 카운터를 쓸 권한이 없다 | **결정(2026-11-21): 추천안대로** — 01은 추천 범위 그대로. **10 spec에서** "`nadri_tools`에 `ingest_state` 해당 키 갱신 권한만 추가" vs "카운터 갱신용 SECURITY DEFINER 함수"를 결정 | — (01에서 정할 것은 저장 형식 `tourapi_calls:YYYY-MM-DD → {"ingest", "live"}`뿐) |
| Q7 | LightRAG 컨테이너의 로컬 작업 디렉터리 볼륨 — [A] named volume 목록(`pg-data`·`wiki-data`·`raw-data`)에 없다 | **결정(2026-11-21): 처음부터 `lightrag-data` 볼륨 추가** — 저장소는 PostgreSQL이지만 로컬 파일 유실로 재인덱싱 비용이 드는 위험을 없앤다 | (폐기) 볼륨 없이 시작 |
| Q8 | 표본 선택 정렬(`arrange=C` 수정일순) — 유명 관광지가 표본에 안 들어갈 수 있어 A8 판단이 어려울 수 있다 | **결정(2026-11-21): 추천안대로** — **수정일순** 유지, 표본에 "경복궁"·"성산일출봉"이 없으면 `lightrag sample` 질의어를 표본에 있는 이름으로 바꾼다 | B: 제목순·인기순 등 다른 정렬(코드 확인 필요) |
