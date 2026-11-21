# 16-web-chat-actions — 테스트 설계 (test)

> spec.md와 짝. 절 번호 §n은 spec.md 기준. 작성 2026-11-21. 상태: 초안 — 사용자 검토 대기.
> ① 자동 — A: Vitest(컴포넌트 상태, `fetch`·`geolocation` 가짜) / B: Playwright(route 가짜 + 브라우저 위치 권한 제어) ② HITL(실제 휴대폰 위치 권한·피드백·한도).

---

## ① 자동 테스트

### 0. 실행
```bash
cd ~/code/myAgent/web
npm run typecheck && npm run test
npm run e2e -- chat-actions
```
- 14 `mockFetch`, 15 SSE 픽스처 재사용. 가짜 위치 `fakeGeo({ result: {lat, lng} | {code: 1|2|3}, delayMs? })` — `getCurrentPosition` 호출 수·옵션 기록.

### A. Vitest

#### A1. `tests/unit/feedback-buttons.test.tsx` (§4)

| ID | 초기 | 동작 | 요청 | 화면 |
|---|---|---|---|---|
| V-FB-01 | 없음 | 👍 | `PUT /api/chat/messages/11/feedback {"rating":"up"}` (reason 키 없음) | 👍 `aria-pressed=true` |
| V-FB-02 | up | 👍 | `DELETE` | 둘 다 false |
| V-FB-03 | 없음 | 👎 | `PUT {"rating":"down","reason":null}` | 👎 true, 사유 칩 4개("틀린 정보","오래된 정보","질문 이해 못함","기타") |
| V-FB-04 | down | 칩 "오래된 정보" | `PUT {"rating":"down","reason":"outdated"}` | 그 칩 선택됨 |
| V-FB-05 | down+outdated | 같은 칩 | `PUT {"rating":"down","reason":null}` | 선택 없음 |
| V-FB-06 | down | 👎 | `DELETE` | 칩 숨김 |
| V-FB-07 | down | 👍 | `PUT up` | 칩 숨김 |
| V-FB-08 | 없음 | 👍, 응답 지연 중 👎 | 요청 1개만(두 번째 클릭 무시 — 비활성) | |
| V-FB-09 | 없음 | 👍, 응답 404 `message_not_found` | | 원래(없음)로 되돌림, 서버 문구 보임, 3초 뒤 사라짐(가짜 타이머) |
| V-FB-10 | `initial={down, wrong}` | 렌더 | 요청 없음 | 👎 true, "틀린 정보" 선택, 칩 보임 |

#### A2. `tests/unit/quota-request.test.tsx` (§5)

| ID | `requestStatus` / 응답 | 기대 |
|---|---|---|
| V-QR-01 | null | "추가 요청" 버튼 |
| V-QR-02 | "pending" | "요청 대기 중", 버튼 없음 |
| V-QR-03 | "approved" / "rejected" | 아무것도 없음 |
| V-QR-04 | null → 클릭 → 201 | `POST /api/quota/requests` 1회(CSRF 헤더), "요청 대기 중" + 서버 message |
| V-QR-05 | 409 `quota_request_exists` | "요청 대기 중" + 서버 문구 |
| V-QR-06 | 409 `quota_not_exhausted` | 서버 문구, 버튼 숨김 |
| V-QR-07 | 네트워크 오류 | 문구, 버튼 다시 활성 |
| V-QR-08 | 요청 중 | 버튼 비활성, 두 번 클릭해도 1회 |

#### A3. `tests/unit/location.test.tsx` (§6)

| ID | 대상 | 준비 | 기대 |
|---|---|---|---|
| V-LC-01 | `getCurrentLocation` | geo 없음 | `{ok:false, reason:"unsupported"}` |
| V-LC-02 | 〃 | 성공 37.5796/126.977 | `{ok:true, lat:37.5796, lng:126.977}`, 옵션 `{enableHighAccuracy:false, timeout:10000, maximumAge:60000}` |
| V-LC-03 | 〃 | 오류 코드 1/2/3 | denied / unavailable / timeout |
| V-LC-04 | `LocationToggle` | geo 없음 | 렌더 안 함 |
| V-LC-05 | 〃 | 끔 → 클릭, 성공 | `onChange(true)`, 설명 글 보임 |
| V-LC-06 | 〃 | 끔 → 클릭, denied | `onChange(false)`, "위치 권한이 꺼져 있어요…" |
| V-LC-07 | 〃 | 켬 → 클릭 | `onChange(false)`, geo 호출 0 |

#### A4. `tests/unit/chat-view-actions.test.tsx` (§7)

| ID | 동작 | 기대 |
|---|---|---|
| V-CA-01 | 위치 끔, 전송 | 요청 본문 `{"text":…}` — `location` 키 없음, geo 호출 0 |
| V-CA-02 | 위치 켬(성공), 전송 | 본문 `{"text":…,"location":{"lat":37.5796,"lng":126.977}}` |
| V-CA-03 | 위치 켬, 전송 때 timeout | 본문에 `location` 없음, 토글 꺼짐, 안내 "위치를 가져오지 못해…", 스트림은 진행 |
| V-CA-04 | V-CA-02 뒤 `error.txt` → 다시 시도 | geo 다시 호출, 두 번째 본문에도 `location` |
| V-CA-05 | 429 `quota_exceeded` `request_status:null` | 알림에 서버 문구 + "추가 요청" 버튼 |
| V-CA-06 | `pass.txt` 완료 | 답변 아래 👍/👎(id 11) |
| V-CA-07 | `blocked.txt` / `error.txt` | 👍/👎 없음 |
| V-CA-08 | 이력 `feedback:{down,"other"}` | 👎 눌림, "기타" 선택 |
| V-CA-09 | V-CA-02 동안 `console.*`·`localStorage.setItem`·`sessionStorage.setItem`·`document.cookie` 쓰기 감시 | 좌표 문자열(`37.5796`, `126.977`) 포함 호출 0 |

### B. Playwright — `web/e2e/chat-actions.spec.ts`

route 가짜는 15와 같음. 요청 본문은 `route.request().postDataJSON()`으로 검사.

| ID | 시나리오 | 기대 |
|---|---|---|
| P-CA-01 피드백 | `pass.txt` 뒤 👍 → 👎 → "틀린 정보" → 👎(취소) | 요청 순서 PUT up / PUT down(null) / PUT down(wrong) / DELETE, 화면 상태 일치 |
| P-CA-02 피드백 복원 | 이력 route에 `feedback:{rating:"up"}` | 새로고침 후 👍 눌린 상태 |
| P-CA-03 한도 초과 | 메시지 route가 429 `{code:"quota_exceeded", message:"오늘 질문 50회를…", limit:50, used:50, request_status:null}` | 입력창에 질문 되돌림, 알림 문구, "추가 요청" → `POST /api/quota/requests`(route 201) → "요청 대기 중" |
| P-CA-04 대기 중 | 429 `request_status:"pending"` | "요청 대기 중", 버튼 없음 |
| P-CA-05 위치 거부 | 컨텍스트 권한 없음(`permissions: []`) → 토글 켬 | 토글 꺼짐·안내, 전송 본문에 `location` 없음 |
| P-CA-06 위치 허용 | `context.grantPermissions(["geolocation"])`, `setGeolocation({latitude:37.5796, longitude:126.977})` → 토글 켬 → 전송 | 본문 `location == {lat:37.5796, lng:126.977}` |
| P-CA-07 좌표 흔적 | P-CA-06 뒤 `localStorage`·`sessionStorage`·`document.cookie`·콘솔 메시지 | `37.5796` 없음 |
| P-CA-08 새로고침 | P-CA-06 뒤 새로고침 | 토글 꺼짐 |

### 통과 기준
- A·B 전부 통과.

---

## ② HITL

전제: 16 적용 compose, 13 병합, 터널 주소 `<HOST>`, active 계정, 휴대폰.

### HITL-1 피드백
1. 휴대폰에서 질문 → 답변 아래 👍/👎 → 👎 → 사유 "오래된 정보".
2. 새로고침 → 같은 상태. DB 확인:
   ```bash
   docker compose exec postgres psql -U postgres -d nadri -c "select message_id, rating, reason from message_feedback order by updated_at desc limit 3"
   ```
3. 👎 다시 눌러 취소 → 행 사라짐.

### HITL-2 한도 초과·추가 요청
1. 오늘 사용량을 한도로 맞춘다:
   ```bash
   docker compose exec postgres psql -U postgres -d nadri -c "insert into daily_quota(user_id, day, used) select id, (now() at time zone 'Asia/Seoul')::date, 50 from users where username='<내 아이디>' on conflict (user_id, day) do update set used = 50"
   ```
2. 질문 → 한도 문구 + "추가 요청" → 누르면 "요청 대기 중". `select * from quota_requests order by id desc limit 1` → pending.
3. 다시 질문 → "추가 요청을 관리자가 확인하고 있어요…" + "요청 대기 중".
4. (18 전) 승인 흉내: `update quota_requests set status='approved' where …; update daily_quota set extra = 50 where …` → 다시 질문 → 답변 옴.
5. 정리: `update daily_quota set used=0, extra=0 where …`.

### HITL-3 위치 동의 (휴대폰, 터널 https)
1. "내 위치 사용" 켬 → 브라우저 권한 창 → 허용 → "내 주변 박물관 알려줘" → 실제 근처 결과인지.
2. 휴대폰 설정에서 그 사이트 위치 권한 차단 → 새로고침 → 토글 켬 → 꺼지며 안내 문구.
3. 위치 끈 채 "경복궁 근처 카페" → 지명 기준 답.
4. 좌표 흔적: 09 HITL-3의 psql·로그 검색 명령 재실행 → 0.

### HITL 결과 보고 양식
| 항목 | 결과 (기기·브라우저) |
|---|---|
| 👍/👎·사유·취소·새로고침 복원 | |
| 한도 초과 → 추가 요청 → 대기 → (흉내) 승인 후 질문 | |
| 위치 허용 시 근처 결과 | |
| 위치 거부 시 토글 꺼짐·안내 | |
| DB·로그 좌표 흔적 0 | |
