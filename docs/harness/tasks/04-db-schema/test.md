# 04-db-schema — 테스트 설계 (test)

> spec.md와 짝. 절 번호 §n은 spec.md 기준. 작성 2026-11-21. 상태: 초안 — 사용자 검토 대기.
> 두 방향: ① pytest(결정적 — 실모델·외부 API 없음. DB가 필요한 것은 **일회용 테스트 DB 컨테이너**, 마커 `db`) ② HITL(사용자가 개발 compose에서 직접 확인).

---

## 0. 실행 방법

WSL2 Ubuntu, 레포 `~/code/myAgent`.
```bash
cd backend
uv sync --no-group reranker                       # pgvector·testcontainers 추가분 설치
uv run pytest -m "not integration" -q             # 단위 + DB 테스트 (Docker 필요)
uv run pytest -m "not integration and not db" -q  # Docker 없이 도는 것만
```
- 프레임워크: `pytest` + `pytest-asyncio`(`asyncio_mode=auto`), DB는 SQLAlchemy async + asyncpg, 컨테이너는 `testcontainers[postgres]`.
- 02의 네트워크 차단 autouse 픽스처(`socket.socket.connect` 차단)는 `db` 마크 테스트에서 Docker 소켓(AF_UNIX)과 `127.0.0.1`만 허용하도록 고친다(그 밖의 외부 접속은 계속 실패). 확인: U-NET-1 — `db` 테스트 안에서 `example.com:80` 접속 시도는 여전히 실패.
- 픽스처: spec §7의 `pg_container`(세션 범위·동기), `db_engine`·`db_sf`(테스트마다, 시작 전 앱 테이블 15개 TRUNCATE), `super_engine`(postgres superuser).
- ERD 읽기 헬퍼 `tests/erd_loader.py`(테스트 전용):
```python
def load_erd() -> dict[str, tuple[str, list[tuple[str, str, str, str]]]]:
    """docs/images/src/erd.py 를 실행하지 않고 AST로 읽어 T 딕셔너리를 돌려준다(ast.literal_eval)."""
def clean_name(s: str) -> str:
    """ERD 한글 명칭에서 각주 표시(①~⑳)와 그 앞 공백을 뺀다(spec §3-1)."""
def expected_columns(erd) -> dict[str, dict[str, tuple[str, str]]]:
    """{테이블: {컬럼: (한글 명칭, ERD 타입)}}. 'lat · lng'/'위도 · 경도' 행은 lat→위도, lng→경도 두 컬럼으로 나눈다."""
```
  - `erd.py`는 스크립트 실행 시 파일을 쓰므로 **import·exec 하지 않는다**(AST로 `T = {...}` 대입문만 찾아 `literal_eval`).
  - 경로: `Path(__file__).resolve().parents[1].parent / "docs/images/src/erd.py"`(backend/tests → 레포 루트).
- ERD 타입 ↔ PostgreSQL `format_type` 대응표(테스트 상수):
  `bigint→bigint`, `int→integer`, `smallint→smallint`, `text→text`, `timestamptz→timestamp with time zone`, `date→date`, `jsonb→jsonb`, `uuid→uuid`, `boolean→boolean`, `numeric→numeric`, `float8→double precision`, `text[]→text[]`, `vector(1536)→vector(1536)`.

---

## ① pytest

### 1. ERD ↔ ORM (DB 없음) — `tests/test_schema_comments.py`

| ID | 대상 | 입력 | 기대 |
|---|---|---|---|
| U-ERD-1 | `load_erd()` | 실제 `erd.py` | 테이블 19개, `users` 행 9개, 실행 부작용 없음(임시 디렉터리 파일 변화 없음) |
| U-ERD-2 | `clean_name` | `"가입 상태 ①"`, `"FAQ 캐시 ID ⑤"`, `"내용 (가린 텍스트)"`, `"비용(USD)"` | `"가입 상태"`, `"FAQ 캐시 ID"`, 나머지 그대로 |
| U-ERD-3 | `expected_columns` | `tour_items` | `lat→("위도","float8")`, `lng→("경도","float8")`, `"lat · lng"` 키 없음 |
| U-SCH-1 | 테이블 집합 | `Base.metadata.tables` | 이름 집합 == ERD 19개 |
| U-SCH-2 | 테이블 COMMENT | 19개 각각 | `table.comment == clean_name(T[t][1])` |
| U-SCH-3 | 컬럼 집합·COMMENT | 19개 각각 | 컬럼 이름 집합 == ERD, `column.comment == 기대값` (파라미터화: 테이블별 1케이스) |
| U-SCH-4 | ORM 클래스 이름 | `account`·`chat`·`quota`·`quality` 모듈 | spec §4의 15개 클래스가 정확한 `__tablename__`으로 존재 |
| U-SCH-5 | 원문·좌표 컬럼 없음 | `chat_messages`, `security_events` | 컬럼 이름에 `raw`, `original`, `lat`, `lng`, `location` 이 들어간 것이 없음(NFR-33·35) |
| U-SCH-6 | `in_check` | `("status", ("a","b"))` | `"status IN ('a','b')"` |
| U-SCH-7 | 순환 FK | `chat_messages.faq_cache_id` FK | `use_alter=True`, 이름 `fk_chat_messages_faq_cache_id`, `ondelete == "SET NULL"` |
| U-SCH-8 | FK 동작 표 | ORM 모든 FK | (테이블.컬럼 → ondelete) 가 spec §4.5·§4 표와 같음(기대 표를 상수로) |

### 2. 테이블 생성 스크립트·DB (마커 `db`) — `tests/db/test_schema_db.py`

#### 2.1 적용·되돌리기
| ID | 절차 | 기대 |
|---|---|---|
| D-MIG-1 | (세션 픽스처) `upgrade head` 직후 `information_schema.tables` | public 스키마 앱 테이블 19개 + `alembic_version` |
| D-MIG-2 | **동기 테스트**: `downgrade("0001")` → 테이블 목록 → `upgrade("head")` | 중간 목록 = 01의 4개 + `alembic_version`, 끝 = 19개. 01 테이블에 미리 넣은 `ingest_state` 1행이 되돌리기 전후 유지 |
| D-MIG-3 | `upgrade head` 한 번 더 | 오류 없음, 변화 없음 |

#### 2.2 COMMENT·타입 (실제 DB)
| ID | 대상 | 기대 |
|---|---|---|
| D-CMT-1 | `obj_description(oid,'pg_class')` 19개 | `clean_name(T[t][1])`과 같음 |
| D-CMT-2 | `col_description` + `format_type(atttypid, atttypmod)` 모든 컬럼 | COMMENT == 기대값, 타입 == 대응표(§0). 실패 시 메시지에 테이블·컬럼·기대·실제 |
| D-ORM-1 | `alembic.autogenerate.compare_metadata(MigrationContext(conn), Base.metadata)` | 차이 목록 빈 리스트. 단 `faq_cache.embedding` 타입 비교 잡음은 무시 목록(spec §10, 무시했다면 테스트 안 주석에 이유) |

#### 2.3 외래키 삭제 동작 (spec §4.5) — 공통 준비 함수 `seed_graph(db)`
사용자 U1(일반)·A1(관리자, U1의 `approved_by`), U1의 대화 S1·S2, S1에 메시지 M1(user)·M2(assistant), S2에 M3(assistant, `faq_cache_id`=C1), C1(`source_message_id`=M2), 피드백 F(M2), 보고서 R(eval_scores E(M2), 개선안 P1(`decided_by`=A1)), usage_events UE(M2, U1), security_events SE(U1, S1, M1), auth_sessions·password_reset_codes·daily_quota·quota_requests(U1, `decided_by`=A1) 각 1행.

| ID | 삭제 | 기대 |
|---|---|---|
| D-FK-1 | `DELETE chat_sessions S1` | M1·M2·F·C1·E 없음 / M3 남고 `faq_cache_id IS NULL` / UE.message_id NULL / SE.session_id·message_id NULL / S2 남음 |
| D-FK-2 | `DELETE eval_reports R` | E 없음, P1 남고 `report_id IS NULL` |
| D-FK-3 | `DELETE users U1` | U1의 auth_sessions·password_reset_codes·chat_sessions(→메시지 전부)·daily_quota·quota_requests·message_feedback 없음 / UE.user_id NULL / SE.user_id NULL / A1 남음 |
| D-FK-4 | `DELETE users A1` | U1.approved_by NULL, (U1 남아 있을 때) quota_requests.decided_by NULL, P1.decided_by NULL |
| D-FK-5 | `DELETE faq_cache C1`만 | M3.faq_cache_id NULL, M2 남음 |

#### 2.4 CHECK·UNIQUE
| ID | 입력 | 기대 |
|---|---|---|
| D-CHK-1 | (파라미터화) `(테이블, 컬럼, ORM 상수)` 전 목록: users.role/status, chat_messages.role/verify_status, quota_requests.status, usage_events.kind, message_feedback.rating, security_events.stage/check_name/outcome, eval_reports.status, improvement_proposals.target/priority/status | `pg_get_constraintdef`(`ck_<테이블>_<컬럼>`)에 상수의 모든 값이 들어 있고, 상수에 없는 값 `'zzz'` INSERT는 `IntegrityError` |
| D-CHK-2 | message_feedback `rating='up', reason='wrong'` / `rating='down', reason='wrong'` / `rating='down', reason=NULL` | 오류 / 성공 / 성공 |
| D-CHK-3 | security_events excerpt 300자 / 301자 | 성공 / 오류 |
| D-CHK-4 | daily_quota `used=-1` | 오류 |
| D-UQ-1 | users 같은 username 2번 | `IntegrityError`, 제약 이름 `uq_users_username`을 꺼낼 수 있음(asyncpg 원인 예외의 `constraint_name` — 경로 **미확인**, 실패 시 대체 방법을 05 헬퍼에 반영) |
| D-UQ-2 | users 같은 email | `uq_users_email` |
| D-UQ-3 | quota_requests 같은 (user, day) | `uq_quota_requests_user_id_day` |
| D-UQ-4 | faq_cache 같은 source_message_id 2행 | `uq_faq_cache_source_message_id` |
| D-UQ-5 | improvement_proposals `report_id=NULL, seq=1` 2행 | 성공(NULL끼리는 중복 아님) |
| D-VEC-1 | faq_cache embedding 1536차원 / 1535차원 | 성공 / 오류 |
| D-DEF-1 | users·chat_sessions·chat_messages를 필수 컬럼만으로 INSERT | `status='pending'`, `role='user'`, `chat_sessions.id` uuid 생성, `turn_count=0`, `pii_types='{}'`, `from_cache=false`, `rewrite_count=0`, 시각 컬럼 채워짐 |

#### 2.5 권한 (NFR-07)
| ID | 대상 | 기대 |
|---|---|---|
| D-PRV-1 | `has_table_privilege('nadri_tools', t, p)` — 15개 테이블 × `SELECT`·`INSERT`·`UPDATE`·`DELETE` | 모두 false |
| D-PRV-2 | 같은 함수 — `tour_items`·`wiki_pages` SELECT | true (01 부여 유지) |
| D-PRV-3 | `nadri_tools`(test-tools)로 실제 접속해 `SELECT 1 FROM users` | 권한 오류(`InsufficientPrivilegeError`) |
| D-PRV-4 | 15개 테이블 소유자(`pg_tables.tableowner`) | 전부 `nadri_app` |

### 통과 기준
- 위 전부 통과. `-m "not integration and not db"` 실행 시 1절(U-*)만 돌고 Docker 없이 통과.
- DB 테스트 전체 소요 시간을 기록(컨테이너 기동 포함) — 05·06에서 DB 테스트가 늘어날 때 기준.

---

## ② HITL (사용자가 직접 실행)

모든 명령은 WSL2 Ubuntu `~/code/myAgent`에서.

### H-0 Docker 권한 (테스트 DB 컨테이너 전제)
```bash
docker ps
```
- 기대: sudo 없이 목록이 나온다. `permission denied`면 `sudo usermod -aG docker $USER` 후 WSL 재시작(`wsl --shutdown`은 Windows PowerShell에서) — 사용자 작업.

### H-1 테스트 실행
```bash
cd backend && uv run pytest -m "not integration" -q
```
- 기대: 전부 통과. 처음엔 `pgvector/pgvector:pg18` 이미지 내려받기로 오래 걸릴 수 있다.

### H-2 개발 DB에 적용
```bash
cd ~/code/myAgent
docker compose build ingest
docker compose up -d postgres
docker compose run --rm ingest            # 기본 명령 = alembic upgrade head (01 Q1)
docker compose exec postgres psql -U postgres -d nadri -c "\dt+"
docker compose exec postgres psql -U postgres -d nadri -c "\d+ users"
docker compose exec postgres psql -U postgres -d nadri -c "\d+ chat_messages"
```
- 기대: 테이블 19개와 한글 설명(사용자·로그인 세션·…·개선안). `\d+ users`의 설명 열이 아이디·이메일·비밀번호 해시·권한·가입 상태·…, CHECK·UNIQUE 제약 이름이 spec §4와 같음. `chat_messages`에 위치·원문 컬럼 없음.

### H-3 권한 눈으로 확인
```bash
docker compose exec -e PGPASSWORD="$(grep ^TOOLS_DB_PASSWORD .env | cut -d= -f2)" postgres \
  psql -h localhost -U nadri_tools -d nadri -c "select count(*) from users"
```
- 기대: `permission denied for table users`.

### H-4 (선택) 되돌리기·재적용 — 개발 DB에 대화 데이터가 생기기 전(05 이전)에만
```bash
docker compose run --rm ingest alembic downgrade 0001
docker compose exec postgres psql -U postgres -d nadri -c "\dt"    # 4개만 (01 적재 데이터 유지)
docker compose run --rm ingest alembic upgrade head
```
- 기대: 01 관광 데이터(`select count(*) from tour_items`)가 전후 같음.

### HITL 보고 양식 (구현자가 사용자에게)
| 항목 | 결과 |
|---|---|
| H-0 Docker 권한 | |
| H-1 테스트 수·소요 시간 | |
| H-2 테이블 19개·설명 일치 | |
| H-3 `nadri_tools` 거부 | |
| H-4 왕복(선택) | |
| spec §10 미확인 항목 결과 | |
