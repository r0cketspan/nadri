# 19-admin-usage — 테스트 설계 (test)

> spec.md와 짝. 절 번호 §n은 spec.md 기준. 작성 2026-11-22. 상태: **확정(2026-11-22)**.
> ① 자동 — A: pytest(결정적, 외부 호출 없음, DB는 04 테스트 컨테이너 — 마커 `db`) / B: Vitest(서식·API 함수) / C: Playwright(가짜 응답을 `page.route`로 주입 + 실제 compose 1회 `@real`) ② HITL(화면 확인, **OpenAI 대시보드 금액 대조**, A14·A28).

---

## ① 자동 테스트

### 0. 공통
```bash
cd ~/code/myAgent/backend && uv run pytest -m "not integration"            # Docker 필요(db 마커)
cd ~/code/myAgent/web && npm run typecheck && npm run test
npm run e2e -- --grep-invert @real     # 가짜 응답 — compose의 web만 필요
npm run e2e -- --grep @real            # 실제 compose(외부 API 비용 없음 — 사용량 행은 psql로 넣음)
```
- 재사용: 05 헬퍼(`app`·`client`·`client2`·`make_user`·`login`·`clock`), 04 `db_sf`, 09 `make_session`, 11 `usage_rows`.
- 추가 헬퍼(`tests/helpers/usage.py`):

| 이름 | 역할 |
|---|---|
| `add_usage(db_sf, *, kind, created_at, user_id=None, input=None, cached=None, write=None, output=None, units=None, cost="0")` | `usage_events` 1행 직접 INSERT(`created_at` 명시, `cost_usd` Decimal) |
| `get_usage(client, **params)` | `GET /api/admin/usage`(params를 쿼리로) |

- 시계: `clock.now` 기본 `2026-11-22T03:00:00+00:00` = KST 2026-11-22 12:00.
- 금액 비교는 문자열 그대로(`"0.00190000"`).

---

### A. pytest

#### A1. 순수 함수 — `tests/api/admin/test_usage_pure.py` (DB 없음)

| ID | 입력 | 기대 |
|---|---|---|
| U-UG-01 | `resolve_range(None, None, now=2026-11-22T03:00Z)` | `(2026-11-01, 2026-11-22)` |
| U-UG-02 | `resolve_range(None, None, now=2026-11-30T15:00Z)`(KST 12-01 00:00) | `(2026-12-01, 2026-12-01)` |
| U-UG-03 | `resolve_range(None, 2026-10-15, now)` | `(2026-10-01, 2026-10-15)` |
| U-UG-04 | `resolve_range(2026-11-05, None, now)` | `(2026-11-05, 2026-11-22)` |
| U-UG-05 | `resolve_range(2026-11-23, None, now)`(내일) | `ApiError(400, "invalid_range")`, 문구 `MSG_INVALID_RANGE` |
| U-UG-06 | `resolve_range(2026-11-10, 2026-11-09, now)` | 400 `invalid_range` |
| U-UG-07 | `resolve_range(2025-11-23, 2026-11-23, now)`(366일) / `(2025-11-22, 2026-11-23)`(367일) | 통과 / 400 |
| U-UG-08 | `resolve_range(2026-12-01, 2026-12-31, now)`(둘 다 미래) | 통과(오류 아님) |
| U-UG-09 | `kst_bounds(2026-11-21, 2026-11-21)` | `(2026-11-20T15:00Z, 2026-11-21T15:00Z)`, 둘 다 tz-aware |
| U-UG-10 | `kst_bounds(2026-12-01, 2026-12-31)` | 끝 = `2026-12-31T15:00Z`(2027-01-01 00:00 KST) |
| U-UG-11 | `month_range(2026-11-22T03:00Z)` / `month_range(2026-10-31T15:00Z)`(KST 11-01 00:00) / `month_range(2026-10-31T14:59:59Z)` | `(11-01, 11-22)` / `(11-01, 11-01)` / `(10-01, 10-31)` |
| U-UG-12 | `fmt_usd(Decimal("0.0019"))` / `Decimal("12")` / `Decimal("0")` | `"0.00190000"` / `"12.00000000"` / `"0.00000000"` |
| U-UG-13 | `external_from([moderation calls 5, web_search units 3, tts units 1200, stt units 75])` | `{5, 3, 1200, 75}` |
| U-UG-14 | `external_from([])` | 전부 0 |
| U-UG-15 | `openai_cost([answer 1.0, web_search 0.5, tts 2.0, stt 0.1])` | `Decimal("1.1")` |
| U-UG-16 | `totals_from([answer {calls 2, input 100, cost 0.001}, verify {calls 1, input 50, cost 0.0005}])` | calls 3, input 150, cost `"0.00150000"` |
| U-UG-17 | `UsageReport` 직렬화(`model_dump(mode="json", by_alias=True)`) | 키 `"from"` 있고 `"from_"` 없음, 금액은 문자열 |
| U-UG-18 | `web/lib/admin-usage.ts`의 `UsageKind`와 04 `USAGE_KINDS` | 같은 13개(파이썬 테스트에서 TS 파일을 정규식으로 읽어 대조 — 한쪽만 바뀌면 실패) |

#### A2. 집계 SQL — `tests/api/admin/test_usage_sql.py` (마커 `db`)

준비: `alice`(user), `admin`(admin), 그리고 아래 행.

| # | kind | created_at (UTC) | user | input/cached/write/output | units | cost |
|---|---|---|---|---|---|---|
| r1 | answer | 2026-11-21T03:00Z | alice | 7000/3500/0/500 | — | 0.000635 |
| r2 | verify | 2026-11-21T14:59:59Z | alice | 6000/1500/0/300 | — | 0.000435 |
| r3 | moderation | 2026-11-21T15:00:00Z | alice | NULL | 1 | 0 |
| r4 | web_search | 2026-11-22T01:00Z | admin | NULL | 1 | 0 |
| r5 | stt | 2026-11-22T01:00Z | alice | NULL | 42 | 0.00315 |
| r6 | tts | 2026-11-22T01:10Z | alice | NULL | 120 | 0 |
| r7 | eval | 2026-11-22T00:00Z | NULL(시스템) | 1000/0/0/100 | — | 0.00015 |
| r8 | answer | 2026-10-31T14:59:59Z(KST 10-31) | alice | 100/0/0/10 | — | 0.000015 |

| ID | 호출 | 기대 |
|---|---|---|
| D-UG-01 | `sum_by_kind(kst_bounds(11-01, 11-22))` | r8 빠짐. answer calls 1·input 7000·cost 0.000635, moderation calls 1·units 1·input 0(NULL→0), stt units 42, tts units 120, web_search units 1, 순서 = `USAGE_KINDS` 순서(answer, verify, moderation, stt, tts, web_search, eval) |
| D-UG-02 | `sum_by_day(같은 구간)` | 11-22: r3·r4·r5·r6·r7(5건) / 11-21: r1·r2(2건). 내림차순(11-22 먼저). r2(14:59:59Z)는 11-21, r3(15:00Z)은 11-22 |
| D-UG-03 | `sum_by_user(같은 구간)` | alice(r1·r2·r3·r5·r6, cost 0.00422), 시스템 `user_id None, username None`(r7, 0.00015), admin(r4, 0) 순 — 비용 큰 순 |
| D-UG-04 | `sum_by_kind(kst_bounds(10-31, 10-31))` | r8만(경계 KST 23:59:59 포함) |
| D-UG-05 | `sum_by_kind(kst_bounds(11-21, 11-21))` | r1·r2만(r3 = KST 11-22 00:00은 빠짐) |
| D-UG-06 | 빈 구간(2026-01-01) | 세 함수 모두 `[]` |
| D-UG-07 | 같은 비용의 사용자 2명 + 시스템 | username 순, 시스템은 맨 아래 |
| D-UG-08 | 토큰이 전부 NULL인 kind만 있는 구간 | 토큰 합 0(None 아님), calls는 행 수 |

#### A3. API — `tests/api/admin/test_usage_api.py` (마커 `db`)

준비: A2의 행 + `clock.now = 2026-11-22T03:00Z`.

| ID | 요청 | 기대 |
|---|---|---|
| A-UG-01 | admin 로그인, 쿼리 없음 | 200, `from "2026-11-01"`, `to "2026-11-22"`, `timezone "Asia/Seoul"`, `by_kind`·`by_day`·`by_user`가 D-UG-01~03과 같음, `totals.calls 7`, `external {moderation_calls 1, tavily_credits 1, elevenlabs_chars 120, stt_seconds 42}` |
| A-UG-02 | 〃 | `month {month "2026-11", start "2026-11-01", end "2026-11-22", openai_cost_usd "0.00437000"(r1+r2+r5+r7, tts·web_search 제외), warn_threshold_usd "10.00", warning false, tavily_free_credits 1000}` |
| A-UG-03 | `?from=2026-10-01&to=2026-10-31` | 기간 표는 r8만, `month`는 그대로 11월(A-UG-02와 같음) |
| A-UG-04 | alice(일반) 로그인 | 403 `forbidden`, 문구 `MSG_FORBIDDEN` |
| A-UG-05 | pending 사용자 | 403 |
| A-UG-06 | 로그인 안 함(`client2`) | 401 `unauthenticated` |
| A-UG-07 | `?from=2026-11-10&to=2026-11-09` | 400 `invalid_range` |
| A-UG-08 | `?from=2026-13-01` / `?to=abc` | 422 |
| A-UG-09 | 이번 달 OpenAI 비용 합이 정확히 `10.00000000`이 되게 행 추가(기존 0.00437 + `answer` 행 9.99563) | `warning false`, `openai_cost_usd "10.00000000"` |
| A-UG-10 | 같은데 추가 행이 9.99563001(합 `10.00000001`) | `warning true`, `openai_cost_usd "10.00000001"` |
| A-UG-11 | 이번 달 `tts` 행 비용 `20`(가상) + 나머지 합 < 10 | `warning false`(OpenAI 비용에서 tts 제외), 기간 `totals.cost_usd`에는 20 포함 |
| A-UG-12 | 지난달(10월) 행 비용 50 | 이번 달 `warning false`(달이 다르면 누적 안 함) |
| A-UG-13 | `clock.now = 2026-11-30T15:00:01Z`(KST 12-01) | `month "2026-12"`, 11월 행 미포함, `openai_cost_usd "0.00000000"` |
| A-UG-14 | `POST /api/admin/usage`(CSRF 포함) | 405 |
| A-UG-15 | 쿼리 수: 요청 1번에 `before_cursor_execute`로 SELECT 수를 셈(인증 쿼리 제외 — `usage_events` 포함 문만) | 4개(기간 3 + 이번 달 1) |
| A-UG-16 | 로그(caplog) | `admin_usage` 1줄, 관리자 id·from·to만(사용자명·금액 없음) |
| A-UG-17 | 11의 실제 `record_usage`로 넣은 행(answer·moderation·web_search 3건, `created_at` 기본값 now) | 응답 `by_kind`에 그대로 보임(11 → 19 연결 확인) |

#### A4. 앞 작업 회귀
- 18·05 테스트 전체 재실행(spec §8). 18 A-ADR-06(관리자 경로 권한 누락 검사)이 `/api/admin/usage`도 통과해야 한다. 05 문구 상수 목록 테스트가 있으면 `MSG_INVALID_RANGE` 추가.

---

### B. Vitest — `web/tests/unit/admin-usage.test.ts`

| ID | 입력 | 기대 |
|---|---|---|
| V-UG-01 | `formatUsd("0.00000000")` | `"$0"` |
| V-UG-02 | `formatUsd("0.00190000")` / `"0.00004000"` | `"$0.0019"` / `"$0.0000"` |
| V-UG-03 | `formatUsd("3.12345678")` / `"12.00000000"` | `"$3.12"` / `"$12.00"` |
| V-UG-04 | `formatInt(1234567)` | `"1,234,567"` |
| V-UG-05 | `KIND_LABELS` 키 | `UsageKind` 13개 전부(빠진 것 없음), 값은 spec §6.1 표와 같음 |
| V-UG-06 | `unitLabel("moderation")`·`"web_search"`·`"stt"`·`"tts"`·`"answer"` | `"건"`·`"크레딧"`·`"초"`·`"자"`·`null` |
| V-UG-07 | `getAdminUsage()`(fetch 가짜) | 요청 URL `/api/admin/usage`(쿼리 없음), 메서드 GET, CSRF 헤더 없음 |
| V-UG-08 | `getAdminUsage("2026-11-01", "2026-11-22")` | `/api/admin/usage?from=2026-11-01&to=2026-11-22` |
| V-UG-09 | `getAdminUsage("", "2026-11-22")` | `/api/admin/usage?to=2026-11-22`(빈 값 뺌) |
| V-UG-10 | 서버 400 `invalid_range` | `ApiError` code `invalid_range`, message 서버 문구 그대로 |

---

### C. Playwright — `web/e2e/admin-usage.spec.ts`

가짜 응답 시나리오: `page.route("**/api/auth/me", …)`로 관리자(`role:"admin", status:"active"`)를 돌려주고(14 `AuthGate`·18 `AdminShell` 통과), `page.route("**/api/admin/usage*", …)`로 아래 고정 JSON(`web/e2e/fixtures/usage/*.json`)을 돌려준다.

| 파일 | 내용 |
|---|---|
| `normal.json` | A-UG-01·02 응답과 같은 모양(행 7개, warning false) |
| `warning.json` | `month.openai_cost_usd "12.34000000"`, `warning true` |
| `empty.json` | `by_kind`·`by_day`·`by_user` 빈 배열, totals 0 |

| ID | 시나리오 | 기대 |
|---|---|---|
| P-UG-01 | `normal.json`, `/admin/usage` 열기 | "이번 달 비용 (2026년 11월, 한국 시간)", "$0.0044", **"앱 기록 기준 추정"** 배지와 `ESTIMATE_NOTE` 문구 보임, 경고 배너(`role="alert"`) 없음, 종류별 표에 "답변"·"안전 검사(Moderation, 무료)"·"음성 인식(STT)" 행, STT 사용량 "42초", 사용자별 표에 "시스템(배치)" |
| P-UG-02 | `warning.json` | `role="alert"`에 "이번 달 OpenAI 비용이 $10를 넘었어요(현재 $12.34)" |
| P-UG-03 | `empty.json` | "이 기간에 기록된 사용량이 없어요.", 이번 달 카드는 보임 |
| P-UG-04 | 날짜 칸에 2026-10-01 ~ 2026-10-31 입력 → [조회] | 가로챈 두 번째 요청 URL에 `from=2026-10-01&to=2026-10-31`. 처음 열 때 첫 요청은 쿼리 없음, 응답 `from`·`to`로 날짜 칸이 채워짐 |
| P-UG-05 | 두 번째 요청에 400 `{"code":"invalid_range","message":…}` | 알림에 서버 문구, 이전 표는 그대로 또는 비움(둘 중 구현이 정한 것 — 오류 문구가 보이는 것만 검사) |
| P-UG-06 | `mobile-chrome` 프로젝트, `normal.json` | `document.documentElement.scrollWidth <= window.innerWidth`(페이지 가로 넘침 없음), 표 상자는 가로 스크롤 가능 |
| P-UG-07 | `/admin/users`에서 관리자 메뉴(18 `AdminShell`) "사용량" 클릭 | `/admin/usage`로 이동, "사용량" 링크에 `aria-current="page"` |
| P-UG-08 `@real` | e2e 관리자 만들기(18 `helpers/db.ts`의 `makeAdmin` — 가입 API → psql로 `role='admin', status='active'`) → psql로 그 사용자 `usage_events` 3행(answer cost 0.001, web_search units 1, tts units 50, `created_at now()`) → 로그인 → `/admin/usage` | 사용자별 표에 그 아이디 행, 호출 3, 비용 "$0.0010". (다른 행은 개발 DB 상태에 따라 다르므로 검사 안 함) |
| P-UG-09 `@real` | e2e 일반 사용자 로그인 → `page.request.get("/api/admin/usage")` | 403 `forbidden` |

- `@real` 정리: `global-setup.ts`(spec §8 #3)가 다음 실행 때 e2e 사용자의 `usage_events`를 먼저 지운다.

### 통과 기준
- A·B·C 전부 통과(`@real` 포함), 실패 0.

---

## ② HITL

전제: 19 적용 compose(개발 모드 가능), `nadri create-admin`으로 만든 관리자 계정, 며칠 동안 실제로 채팅·음성을 쓴 기록(11·17 병합 후). 브라우저는 Windows에서 `http://localhost:8080`(또는 터널 주소).

### HITL-1 화면 확인
1. 관리자로 로그인 → 메뉴 "사용량" → `/admin/usage`.
2. 이번 달 카드의 금액·외부 사용량, 종류별 표를 아래 psql 결과와 비교한다(같아야 함):
   ```bash
   docker compose exec postgres psql -U postgres -d nadri -c "
   select kind, count(*), coalesce(sum(input_tokens),0) inp, coalesce(sum(cached_tokens),0) cached,
          coalesce(sum(output_tokens),0) outp, coalesce(sum(units),0) units, sum(cost_usd) cost
   from usage_events
   where created_at >= date_trunc('month', now() at time zone 'Asia/Seoul') at time zone 'Asia/Seoul'
   group by kind order by kind"
   ```
3. 날짜 칸을 지난주로 바꿔 [조회] → 일자별 표 날짜가 한국 날짜인지(밤 12시~오전 9시 사이에 쓴 기록이 그 날짜에 들어가는지) 확인.
4. 휴대폰(터널 주소)으로 같은 화면 — 표만 옆으로 밀리고 페이지는 안 넘치는지.
5. 일반 사용자 계정으로 `/admin/usage` 주소를 직접 열기 → "접근 권한이 없어요."(18 `AdminShell`), 개발자 도구 네트워크 탭에 `/api/admin/usage` 요청이 없는지.

### HITL-2 OpenAI 대시보드 금액 대조 (A14, 기록만)
1. 비교할 날 1~3일을 고른다(채팅을 꽤 쓴 날, 가능하면 03 초기 적재·LightRAG 인덱싱이 **없던** 날 1개와 **있던** 날 1개).
2. 앱 기록 — OpenAI 비용만, **UTC 날짜**와 **KST 날짜** 둘 다:
   ```bash
   docker compose exec postgres psql -U postgres -d nadri -c "
   select (created_at at time zone 'UTC')::date utc_day, sum(cost_usd) app_cost
   from usage_events where kind not in ('web_search','tts') group by 1 order by 1 desc limit 7"
   docker compose exec postgres psql -U postgres -d nadri -c "
   select (created_at at time zone 'Asia/Seoul')::date kst_day, sum(cost_usd) app_cost
   from usage_events where kind not in ('web_search','tts') group by 1 order by 1 desc limit 7"
   ```
3. OpenAI 웹사이트(platform) → Usage(사용량) 화면에서 같은 날 비용을 본다. 화면이 어느 시간대 날짜를 쓰는지 화면 안내로 확인해 적는다(**미확인** — UTC로 알려짐). 모델별로 나눠 보이면 `gpt-6-luna`·임베딩·`gpt-transcribe` 금액도 적는다.
4. 차이를 아래 표에 적는다. 예상 이유: LightRAG 내부 호출(인덱싱·키워드 추출 — 앱 집계 없음), 단가표 차이(11), 대시보드 반영 지연, 시간대 차이.
5. 차이가 "인덱싱 없던 날"에도 크면(예: 앱 합계가 대시보드의 70% 미만) 그 날 `kind`별 합과 함께 보고 — 19-Q5(키 분리) 결정 재료.

### HITL-3 LightRAG 사용량 API 유무 (A14)
```bash
docker compose run --rm ingest python -c "
import json, os, urllib.request
req = urllib.request.Request('http://lightrag:9621/openapi.json', headers={'X-API-Key': os.environ.get('LIGHTRAG_API_KEY','')})
paths = json.load(urllib.request.urlopen(req))['paths']
print('\n'.join(p for p in paths if any(w in p.lower() for w in ('usage','token','cost','stat'))) or '(관련 경로 없음)')"
```
- 기대: `(관련 경로 없음)` → A14 가정대로(추정 표기 유지). 경로가 나오면 그 목록을 보고하고 멈춘다(spec §9).
- `openapi.json` 위치·인증 헤더가 다르면(**미확인** — 01 `LightRagDocs`는 `X-API-Key`) 브라우저 없이 `docker compose logs lightrag`의 시작 로그에서 API 문서 주소를 찾아 바꿔 실행한다.

### HITL-4 $10 경고 표시 (실제 DB)
1. 가짜 비용 행을 넣는다(시스템 행, id를 적어 둔다):
   ```bash
   docker compose exec postgres psql -U postgres -d nadri -At -c "insert into usage_events(kind, cost_usd) values ('eval', 10.5) returning id"
   ```
2. `/admin/usage` 새로고침 → 위에 경고 배너, 이번 달 금액 $10 초과. 채팅은 그대로 되는지(차단 없음) 한 번 질문.
3. 지우기: `docker compose exec postgres psql -U postgres -d nadri -c "delete from usage_events where id = <1의 id>"` → 새로고침 → 배너 사라짐.

### HITL-5 Tavily 크레딧 (A28)
1. 이번 달 카드의 "웹 검색(Tavily): n / 1,000 크레딧"을 적는다.
2. Tavily 웹사이트 대시보드의 이번 달 사용 크레딧과 비교(월 초기화 날짜가 달력 1일인지도 적는다 — **미확인**).
3. `n ÷ (오늘 날짜) × 30`으로 월말 예상치를 계산해 1,000 안인지 적는다.

### HITL 결과 보고
| 항목 | 결과 |
|---|---|
| HITL-1 화면 = psql 합계, 날짜 KST, 휴대폰 표시, 일반 사용자 차단 | |
| HITL-2 날짜별 앱 합계(UTC·KST) vs OpenAI 대시보드, 차이·이유 추정, 대시보드 시간대 | |
| HITL-3 LightRAG 사용량 경로 유무(A14 판정) | |
| HITL-4 경고 배너 표시·해제, 채팅 차단 없음 | |
| HITL-5 Tavily 앱 숫자 vs Tavily 대시보드, 월말 예상(A28 판정) | |
