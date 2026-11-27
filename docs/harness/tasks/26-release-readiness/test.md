# 26-release-readiness — 테스트 설계 (test)

> spec.md와 짝. 절 번호 §n·검사 ID C-xx는 spec.md 기준. 작성 2026-11-22. 상태: **확정(2026-11-28, 확인 질문 전부 추천안대로)**.
> ① pytest(결정적 — 파일만 읽음. Docker·DB·네트워크·실 키 없음. C-20만 Docker CLI가 있으면 실행) ② HITL(사용자가 직접 — 빈 볼륨 클린 기동 → 테이블 생성 → `create-admin` → 소량 적재 → 채팅 1회, 보안 설정 실측, 문서 명령 대조).

---

## ① pytest — `backend/tests/test_compose_hardening.py`

### 0. 공통
- 실행: `cd ~/code/myAgent/backend && uv run pytest tests/test_compose_hardening.py -v`. 전체 회귀: `uv run pytest -m "not integration"`.
- 프레임워크: pytest + PyYAML(01 dev 그룹). 새 의존 없음.
- 두 방향: **A. 검사 함수 자체**(작은 가짜 dict·임시 파일로 위반을 일부러 만들어 메시지가 나오는지) → **B. 실제 레포 파일**(위반 0).
- 가짜 데이터 도우미(같은 파일 안): `svc(**kw)`(기본 = 규칙을 다 지킨 자체 이미지 서비스 dict: `build`, `user:"10001:10001"`, `cap_drop:["ALL"]`, `security_opt:["no-new-privileges:true"]`, `restart:"unless-stopped"`), `compose_of(**services)`(`{"services": …, "volumes": {…NAMED_VOLUMES}}`), `tmp_dockerfile(tmp_path, text)`.

### A. 도우미·검사 함수 (가짜 입력)

| ID | 입력 | 기대 |
|---|---|---|
| U-H-01 | `env_of({"environment": ["A=1", "B=${X}"]})` / 사전형 `{"A": "1"}` | `{"A":"1","B":"${X}"}` / `{"A":"1"}` |
| U-H-02 | `env_of({"environment": {"LANGSMITH_TRACING": False}})` | ValueError, 메시지에 "따옴표" |
| U-H-03 | `refs_in({"a": ["${A}", "x ${B:-3} ${C:?없음}"], "b": {"c": "$${D}"}})` | `[("A",None),("B",":-3"),("C",":?없음")]` — `$${D}`(이스케이프)는 참조 아님 |
| U-H-04 | `env_example_keys`: `# 주석`·빈 줄·`A=`·`B=` | `{"A":"","B":""}` / 같은 키 2번 → ValueError |
| U-H-05 | `bind_mounts`: `["pg-data:/x", "./eval:/app/eval:ro", {"type":"bind","source":"./a","target":"/a","read_only":true}]` | `[("./eval","/app/eval",True),("./a","/a",True)]` (named volume 제외) |
| U-H-06 | `final_user`: `FROM python AS base\nUSER nadri\nFROM base AS app\nRUN x` | target `app` → `"nadri"`(부모에서 상속) |
| U-H-07 | `final_user`: `FROM node AS runner\nUSER node\nUSER root` / USER 없음 | `"root"` / `None` |
| U-C-01 | 서비스 7개 / 9개 / `networks: {back: {}}` | C-01 위반(빠진·남는 이름, 네트워크) |
| U-C-02 | `svc(user="0")` / `user` 없음 / `"root:root"` | C-03 위반 각각 |
| U-C-03 | `cap_drop: ["NET_RAW"]` / 없음 | C-05 위반 |
| U-C-04 | `security_opt` 없음 / `["no-new-privileges"]` | 위반 / 통과(두 표기 모두 허용) |
| U-C-05 | 외부 이미지 서비스에 `/var/run/docker.sock:/var/run/docker.sock` | C-07 위반(외부 이미지도 검사) |
| U-C-06 | `privileged: true` / `cap_add: [SYS_ADMIN]` / `network_mode: host` | C-08 위반 각각 |
| U-C-07 | compose.yaml의 nginx에 `ports: ["8080:80"]` | C-09 위반(nginx도 예외 아님) |
| U-C-08 | dev: `["8080:80"]` / `["0.0.0.0:8080:80"]` / `["127.0.0.1:8080:80"]` / 긴 문법 `host_ip: 127.0.0.1` | 위반 / 위반 / 통과 / 통과 |
| U-C-09 | dev가 api에 `user: "0"` 또는 `security_opt: []` | C-11 위반 |
| U-C-10 | api에 `TOURAPI_SERVICE_KEY: ${TOURAPI_SERVICE_KEY}` 추가 | C-12 "api: 받으면 안 되는 키 TOURAPI_SERVICE_KEY" |
| U-C-11 | api에서 `SESSION_SECRET` 빠짐 | C-12 "api: 빠진 키 SESSION_SECRET" |
| U-C-12 | `DB_PASSWORD: ${APP_DB_PASSWORD}` (이름 다름) | C-12 통과(참조 키로 판정) |
| U-C-13 | `OPENAI_API_KEY: sk-abc` / `TOOLS_API_KEY: ${TOOLS_API_KEY:-dev}` | C-13 위반(글자 그대로 / 기본값) |
| U-C-14 | cloudflared `command: tunnel run --token ${CLOUDFLARE_TUNNEL_TOKEN}` | C-14·C-25 위반 |
| U-C-15 | `env_file: .env` / 허용 env_file 안에 `POSTGRES_PASSWORD=x` | C-15 위반 각각 |
| U-C-16 | api `LANGSMITH_TRACING: "true"` / `LANGSMITH_API_KEY: ${LANGSMITH_API_KEY}` / ingest에 `LANGCHAIN_TRACING_V2` 없음 / tour-tools에 `LANGSMITH_PROJECT: x` | C-16 위반 각각 |
| U-C-17 | `LANGSMITH_TRACING: "FALSE"` | 통과(대소문자 무시) |
| U-C-18 | `.env.example`에 `FOO=` 추가(아무도 안 씀) / `OPENAI_API_KEY=sk-x`(값 있음) / compose에 `${NEW_KEY}` 참조인데 `.env.example`에 없음 / `${SSE_PING_S:-15}` | 위반 / 위반 / 위반 / 통과(기본값 있는 조정값) |
| U-C-19 | top-level 볼륨에 `name: fixed` / `external: true` / 바인드 `./data:/data` / postgres init 마운트에 `:ro` 없음 / api에 `wiki-data` | C-19 위반 각각 |
| U-C-20 | api `depends_on: {ingest: {condition: service_completed_successfully}}` / ingest healthcheck 없음 | C-21 위반 |
| U-C-21 | web에 `restart` 없음 | C-22 위반 |
| U-C-22 | `image: nginx` / `nginx:latest` / `nginx:1.29-alpine` | 위반 / 위반 / 통과 |
| U-C-23 | cloudflared `profiles: [tunnel]` | C-25 위반 |
| U-C-24 | `build` 있는 서비스가 `SELF_BUILT`와 다름(예: nginx에 build) | C-02 위반 |
| U-C-26 | `x-tuning` 원문에서 tour-tools만 `<<: *tuning` 빠짐 / ingest가 `VERIFY_MAX_REWRITES: "1"`로 덮어씀 / web에 `RAG_TOP_K` / 값이 따옴표 없는 숫자 | C-27 위반 각각 |
| U-C-25 | 위반 여러 개를 한 dict에 | 모든 위반이 한 번에 목록으로(첫 위반에서 멈추지 않음), 메시지가 `서비스: …` 형식·한국어 |

### B. 실제 레포 파일 (위반 0이어야 통과)

| ID | 검사 | 파일 |
|---|---|---|
| R-01 | C-01·C-02 서비스 8개·자체 이미지 4개·네트워크 1개 | compose.yaml |
| R-02 | C-03·C-05·C-06 자체 이미지 `user`·`cap_drop`·`no-new-privileges` | compose.yaml |
| R-03 | C-04 Dockerfile 최종 USER: backend `app`·`tools` = `nadri`, web `runner` = `node` | backend/web Dockerfile |
| R-04 | C-07·C-08 docker.sock·특권 설정 없음 | 두 compose |
| R-05 | C-09 compose.yaml 포트 없음 / C-10·C-11 dev 포트 127.0.0.1만, 보안 설정 덮어쓰기 없음 | 두 compose |
| R-06 | C-12 서비스별 `.env` 키 == spec §4 표 | compose.yaml |
| R-07 | C-13·C-14·C-15 비밀값 형식·위치·env_file | compose.yaml, lightrag.env |
| R-08 | C-16 추적 끔·LANGSMITH 키 없음 | compose.yaml, .env.example |
| R-09 | C-17 `.env.example` 16키·값 비움·서로 일치 | 두 파일 |
| R-10 | C-18 `.env` git 제외·추적 안 됨 | .gitignore, git |
| R-11 | C-19 볼륨·바인드 | compose.yaml |
| R-12 | C-21·C-22·C-23 기동 순서·재시작·healthcheck(lightrag 포함 — Q2, postgres `pg_isready -h 127.0.0.1` — Q4) | compose.yaml |
| R-13 | C-24·C-25 이미지 태그 고정·cloudflared | compose.yaml |
| R-14 | C-20 `docker compose … config -q` 성공 + JSON 병합 결과에서 C-05·C-09 (Docker CLI 없으면 skip, 사유 출력) | 두 compose |
| R-15 | C-26 `infra/**/*.sh` CR 없음, `.gitattributes` | 파일 |
| R-16 | C-27 `x-tuning`: 앵커 있음, api·tour-tools·ingest가 `<<: *tuning`, 병합 결과 6개 값이 세 서비스에서 같음 | compose.yaml |

### C. 앞 작업 회귀
- 전체 `uv run pytest -m "not integration"`, `cd web && npm run typecheck && npm run test` 실패 0.
- compose를 고친 뒤(lightrag·postgres healthcheck, `x-tuning`) `npm run e2e`(compose 기동 상태) 통과 — 기동 순서·healthcheck 변경이 웹 테스트를 깨지 않는지.

### 통과 기준
A·B·C 전부 통과. R-14가 skip이면 HITL-1에서 `docker compose config -q`를 직접 돌려 대신 확인.

---

## ② HITL

> **경고**: 아래 모든 명령은 `-p nadri-clean`을 붙인다. 붙이지 않고 `down -v`를 하면 **기존 적재 데이터가 지워진다.** 명령은 이 문서에서 그대로 복사한다.

### 전제
- 01~25가 `dev`에 병합되어 있고, 26 브랜치에서 확정 결정을 반영한 compose·`.env.example`·`.gitattributes`·README, 21 따라잡기 조건 수정(26-Q1①)이 들어간 21 구현.
- `.env`에 실 키(TourAPI·OpenAI·Tavily·터널 토큰, 가능하면 Gmail·ElevenLabs).
- 기존 환경의 오늘 TourAPI 사용량이 적을 때(`docker compose exec ingest nadri ingest status`의 오늘 카운터 — 같은 키의 하루 1,000건 한도를 같이 씀). 01:00·03:00 작업 시간대는 피한다.
- 예상 비용: TourAPI 약 90~150건, OpenAI 약 $0.1~0.5(인덱싱 30페이지 + 채팅 1회, **추정**) + 03:00 KST 이후 기동이면 24 놓친 실행의 공격 세트 약 $0.03~0.10.
- 이번 HITL은 사용자가 **README "시작하기"만 보고** 따라 한다(에이전트는 막힌 곳만 기록). 막히면 README를 고치는 것이 이 작업의 일.

### HITL-0 기존 환경 멈춤 (삭제 아님)
```bash
cd ~/code/myAgent
docker compose stop                               # 데이터는 그대로
docker volume ls | grep nadri                     # nadri_pg-data 등 기존 볼륨 이름 확인(메모)
```
- 확인: `docker compose ps`에 실행 중 없음.

### HITL-1 빈 볼륨 클린 기동 (운영 형태 — Q9)
```bash
docker compose -f compose.yaml --env-file .env.example config -q && echo 문법OK
docker compose -p nadri-clean up -d --build
docker compose -p nadri-clean ps
docker compose -p nadri-clean logs -f ingest      # "scheduler started" 확인 후 Ctrl+C
```
- [ ] 새 볼륨 4개가 `nadri-clean_` 접두어로 생김(`docker volume ls | grep nadri-clean`), 기존 `nadri_` 볼륨 그대로
- [ ] postgres·lightrag·ingest·tour-tools·api·web `healthy`, nginx·cloudflared `running`
- [ ] `docker compose -p nadri-clean ps --format '{{.Name}} {{.Ports}}'`에 호스트로 게시된 포트(`0.0.0.0:`·`127.0.0.1:`) 없음
- [ ] 재시작 반복 없음(`ps`의 Status에 `Restarting` 없음). 첫 1분 사이 lightrag·ingest 재시작 횟수 기록(`docker inspect -f '{{.RestartCount}}'`) — Q4·Q2 효과 확인
- [ ] ingest 로그에 따라잡기 실행이 보이면 끝날 때까지 기다림(`daily_sync done`). 이 실행이 초기 적재를 시작하지 않음(26-Q1①)(`kind='bootstrap'` 행 0개)
- [ ] 03:00 KST 이후 기동이면 `daily_quality start date=<어제>` → `done … status=skipped attack=n/m` 로그, `$P -d nadri -Atc "select report_date,status,stats->'attack_set'->>'defense_rate' from eval_reports"`(HITL-2의 `P` 사용)에 어제 날짜 `skipped` 1행. 03:00 전 기동이면 행 없음(정상) — 결과표에 기동 시각과 함께 기록
- 걸린 시간(빌드 포함) 기록

### HITL-2 테이블 생성 확인
```bash
P="docker compose -p nadri-clean exec -T postgres psql -U postgres"
$P -d nadri -Atc "select count(*) from information_schema.tables where table_schema='public' and table_name<>'alembic_version'"
$P -d nadri -Atc "select version_num from alembic_version"
$P -Atc "select rolname from pg_roles where rolname in ('nadri_app','nadri_tools','lightrag') order by 1"
$P -Atc "select datname from pg_database where datname in ('nadri','lightrag') order by 1"
$P -d nadri -Atc "select extname from pg_extension where extname='vector'"
```
- [ ] 테이블 18개(ERD), alembic 최신 리비전, 롤 3개, DB 2개, `vector`
- [ ] `$P -d nadri -c "\dt+ users"`에 한글 COMMENT 보임(04)

### HITL-3 첫 관리자
```bash
docker compose -p nadri-clean run --rm api nadri create-admin --username admin --email <내 이메일>
```
- [ ] 비밀번호 입력 안내(10자 이상·흔한 비밀번호 거절) 후 생성 메시지, 종료 코드 0

### HITL-4 소량 적재
```bash
docker compose -p nadri-clean run --rm ingest nadri ingest bootstrap --area 서울 --type 12 --max-items 30
docker compose -p nadri-clean run --rm ingest nadri ingest status
docker compose -p nadri-clean run --rm ingest nadri tools smoke
```
- [ ] 적재 종료 코드 0(잠금 때문에 4면 HITL-1의 따라잡기가 끝나기를 기다린 뒤 다시 — 결과표에 기록), 30건 상세·인덱싱 완료
- [ ] `tools smoke`에서 `rag_query`·`data_query`·`get_datetime`(+`tour_live`) 결과, 경복궁 등 적재 항목이 나옴
- [ ] 사용한 TourAPI 호출 수(`ingest status` 오늘 카운터) 기록

### HITL-5 채팅 1회 (터널)
1. 휴대폰 또는 PC 브라우저로 터널 주소(`https://<도메인>`) → admin 로그인.
2. "경복궁 관람 시간 알려줘" 전송.
- [ ] 답변이 글자 단위로 흘러나옴 → `✓ 확인됨`(또는 경고 문구)
- [ ] 출처(한국관광공사)·기준일 표시, 링크는 완료 뒤에만 눌림
- [ ] 사이드바에 세션, 새로고침 후 같은 이력
- [ ] `/admin` 사용량 화면에 이 질문의 비용 행
- (선택, 터널 없는 경로) HITL-6 뒤에 `docker compose -p nadri-clean -f compose.yaml -f compose.dev.yaml up -d --scale cloudflared=0` → Windows 브라우저 `http://localhost:8080`에서 같은 질문 1회

### HITL-6 보안 설정 실측
```bash
C="docker compose -p nadri-clean exec -T"
for s in api ingest tour-tools web; do
  echo "== $s"; $C $s id -u
  $C $s sh -c 'grep -E "^(CapEff|NoNewPrivs)" /proc/1/status'
done
for s in api ingest; do echo "== $s"; $C $s env | grep -E '^(LANGSMITH|LANGCHAIN)_' ; done
docker compose -p nadri-clean ps -q | xargs docker inspect -f '{{.Name}} {{range .Mounts}}{{.Source}} {{end}}' | grep -c docker.sock
$C api env | grep -cE '^(TOURAPI_SERVICE_KEY|LIGHTRAG_API_KEY|POSTGRES_PASSWORD)='
$C web env | grep -cE '(KEY|SECRET|PASSWORD|TOKEN)='
```
- [ ] `id -u`: api·ingest·tour-tools `10001`, web `1000`
- [ ] `CapEff: 0000000000000000`, `NoNewPrivs: 1` (4개 모두)
- [ ] api·ingest: `LANGSMITH_TRACING=false`, `LANGCHAIN_TRACING_V2=false` 두 줄만
- [ ] docker.sock 개수 `0`, api의 받으면 안 되는 키 `0`, web 비밀값 `0`
- (web 이미지에 `sh`·`grep`이 없으면 `docker inspect`의 `HostConfig.CapDrop`·`SecurityOpt`·`Config.User`로 대신 — 결과표에 방법 기록)

### HITL-7 정리
```bash
docker compose -p nadri-clean down -v             # ← -p nadri-clean 꼭 확인
docker volume ls | grep nadri                     # nadri-clean_ 없음, 기존 nadri_ 그대로
docker compose up -d                              # 기존 환경 복귀 (평소 쓰던 -f 옵션 그대로)
docker compose ps
```
- [ ] 기존 환경이 healthy로 돌아오고, 이전 대화·적재 데이터가 그대로(브라우저에서 지난 세션 1개 열어 봄)
- (선택) 클린용 이미지 지우기: `docker image ls | grep nadri-clean` → `docker image rm …`

### HITL-8 문서 대조
1. README "시작하기"를 처음부터 읽으며 HITL-1~5에서 실제 친 명령과 한 줄씩 대조 — 다른 곳·빠진 설명을 목록으로.
2. CLAUDE.md "명령어" 절의 명령을 기존 환경에서 하나씩 실행(비용 드는 `eval golden`·`eval attack` 본 실행·`@real` e2e는 `--check`·`--help`로 대신, `eval quality`는 `--date <어제>`로 "이미 있음" 종료 코드 0 확인) — 실패·오타 목록.
3. `grep -n "MVP" README.md TECH_STACK.md` 0건, README의 `SECURITY_GUIDE.md` 링크 열림.
- [ ] 목록이 비었거나, 찾은 것을 고친 뒤 다시 확인

### HITL 결과 보고
| 항목 | 결과 |
|---|---|
| ① pytest 결과(R-14 실행/skip) | |
| 1 기동 시간, healthy까지, 재시작 횟수(lightrag·ingest), 게시 포트 없음 | |
| 1 따라잡기 동작(초기 적재 시작 안 함 — 26-Q1①), 24 놓친 실행(기동 시각·`skipped` 행·방어율·비용) | |
| 2 테이블 수·롤·DB·확장 | |
| 3 create-admin | |
| 4 적재 30건, TourAPI 호출 수, tools smoke | |
| 5 채팅(✓/경고, 출처·기준일, 이력, 비용 행), 선택 localhost 경로 | |
| 6 uid·CapEff·NoNewPrivs·추적 끔·docker.sock·키 주입 | |
| 7 정리 후 기존 데이터 보존 | |
| 8 README·CLAUDE.md 고친 곳 | |
| 실제 비용(OpenAI·TourAPI) vs 추정 | |
