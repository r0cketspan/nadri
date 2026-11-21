# 15-web-chat — 테스트 설계 (test)

> spec.md와 짝. 절 번호 §n은 spec.md 기준. 작성 2026-11-21. 상태: 확정(2026-11-22).
> ① 자동 — A: Vitest(파서·상태 전이·렌더러·컴포넌트, 서버 없음) / B: Playwright(가짜 SSE를 `page.route`로 주입 + 실제 compose 1회) ② HITL(휴대폰 터널 주소에서 토큰 단위 표시 — A11, A30).

---

## ① 자동 테스트

### 0. 실행
```bash
cd ~/code/myAgent/web
npm run typecheck && npm run test
npm run e2e -- --grep-invert @real        # 가짜 SSE 시나리오(백엔드 응답은 route로 대체 — compose의 web만 필요)
npm run e2e -- --grep @real               # 실제 compose 1회(OpenAI 비용 소량, 수동 실행)
```
- 공통 픽스처 `tests/unit/sse-fixtures.ts`: 이벤트 배열 → SSE 텍스트(`event: X\ndata: {...}\n\n`) 만드는 `sse(...events)`, 문자열을 지정 위치로 쪼개 `ReadableStream`으로 만드는 `chunked(text, cuts)`(바이트 단위로 쪼갤 수 있음).
- 시나리오 SSE 텍스트 파일(`web/e2e/fixtures/sse/*.txt`)은 Vitest·Playwright가 같이 쓴다:

| 파일 | 이벤트 열 |
|---|---|
| `pass.txt` | meta(가린 글 "010-****-**** 경복궁 시간") → status checking → status answering → delta "찾아볼게요" → tool{rag_query,"관광 정보 찾는 중"} → delta×5("경복궁은 … [홈페이지](https://www.royalpalace.go.kr/) (#126508)") → draft_done → status verifying → verified → done{passed, allowed_urls:["https://www.royalpalace.go.kr/"], sources:[tour 126508 "경복궁" "한국관광공사" "2026-11-20"], assistant_message_id:11, user_message_id:10} |
| `replaced.txt` | … draft_done → verifying → revising{1} → verifying → replaced{"수정본 …", 1} → verified → done{passed, rewrite_count:1} |
| `warning.txt` | … → replaced{…} → warning{unverified, "이 답변은 자료와 끝까지 대조하지 못해…"} → done{failed} |
| `security.txt` | … → replaced{"죄송해요, 이 질문에는 안전하게…"} → done{security_replaced, allowed_urls:[]} |
| `blocked.txt` | meta → checking → blocked{jailbreak, "이 요청은 처리할 수 없어요…"} → done{blocked:true} |
| `error.txt` | meta → checking → answering → delta "초안…" → error{llm_unavailable, "일시적인 시스템 장애로…"} |
| `cached.txt` | meta → checking → answering → delta(전체 1개) → draft_done → verified → done{cached:true, verify_status:"cached"} |
| `cut.txt` | meta → checking → answering → delta "초안" (끝 — done/error 없음) |

---

### A. Vitest

#### A1. 파서 — `tests/unit/sse.test.ts` (§4.3)

| ID | 입력 | 기대 |
|---|---|---|
| V-SSE-01 | `pass.txt` 한 조각 | ChatEvent 열이 파일 순서와 같음 |
| V-SSE-02 | `pass.txt`를 **모든 바이트 위치**에서 둘로 쪼갠 경우 전부(반복) | 결과가 V-SSE-01과 같음(한글 깨짐 없음) |
| V-SSE-03 | 이벤트 사이에 `: ping\n\n` 3개 | ping은 이벤트로 안 나옴 |
| V-SSE-04 | 줄 끝 `\r\n` / `\r` | 같은 결과 |
| V-SSE-05 | `event: future_thing\ndata: {}\n\n` 섞음 | 무시, 나머지 정상 |
| V-SSE-06 | `event: delta\ndata: {깨짐\n\n` | `SseProtocolError` |
| V-SSE-07 | `cut.txt` | 이벤트 4개 뒤 `SseProtocolError("stream_ended")` |
| V-SSE-08 | `done` 뒤에 쓰레기 바이트 | `done`에서 끝, 뒤는 읽지 않음(reader.cancel 호출) |
| V-SSE-09 | `data:` 두 줄 이벤트 | `\n`으로 이어 붙인 data |
| V-SSE-10 | `data:{"text":"a"}`(콜론 뒤 공백 없음) | 정상 파싱 |
| V-SSE-11 | `streamChat` — `apiFetch`가 429 ApiError | 제너레이터 만들기 전에 ApiError 던짐 |
| V-SSE-12 | `streamChat` 요청 | `POST /api/chat/sessions/<id>/messages`, `Accept: text/event-stream`, CSRF 헤더, 본문 `{"text":…}` |

#### A2. 상태 전이 — `tests/unit/chat-state.test.ts` (§5.3)

| ID | 적용 | 기대 |
|---|---|---|
| V-CS-01 | `startTurn("010-1234-5678 경복궁 시간")` | user 원문, assistant `phase "waiting"` |
| V-CS-02 | + meta | user `text` = `"010-****-**** 경복궁 시간"`, `maskedTypes ["phone"]` |
| V-CS-03 | + checking / answering | phase 차례로 |
| V-CS-04 | delta "찾아볼게요" → tool | `text ""`, `toolLabel "관광 정보 찾는 중"` (A30) |
| V-CS-05 | + delta 여러 개 | 합친 본문, `phase drafting`, toolLabel null |
| V-CS-06 | + draft_done | `linksEnabled false` 유지 |
| V-CS-07 | + verifying → verified | `verified true`, 아직 `phase verifying` |
| V-CS-08 | + done | `phase done`, `id 11`, user `id 10`, `linksEnabled true`, sources·allowedUrls 채움 |
| V-CS-09 | `replaced.txt` 전체 | 마지막 본문 = 수정본, `verified true`, `verifyStatus passed`, revising 단계에서 `attempt 1` |
| V-CS-10 | `warning.txt` | `warning` = 서버 문구, `verified false`, `verifyStatus failed` |
| V-CS-11 | `security.txt` | 본문 = 안전 문구, `verified false`, `allowedUrls []` |
| V-CS-12 | `blocked.txt` | `phase blocked`, `blocked.code jailbreak`, `linksEnabled false`, id null |
| V-CS-13 | `error.txt` | `phase error`, `text ""`, `retryText` = 보낸 질문, error.message = 서버 문구 |
| V-CS-14 | `failTurn(…, "stream_ended")` | `phase error`, 메시지 `연결이 끊겨 답변을 받지 못했어요. 다시 시도해 주세요.` |
| V-CS-15 | `cached.txt` | `verified true`, `cached true`, `verifyStatus cached` |
| V-CS-16 | `applyEvent`가 입력 쌍을 바꾸지 않음 | 원본 객체 불변(Object.freeze로 확인) |
| V-CS-17 | `fromHistory`(09 응답 예: passed·failed·security_replaced·cached 답변 각 1) | passed·cached → verified true / failed → false / 모두 `linksEnabled true`, `allowedUrls` = 응답 값 |

#### A3. 렌더러 — `tests/unit/safe-markdown.test.tsx` (§8)

| ID | 입력 (`allowedUrls`, `linksEnabled`) | 기대 (DOM) |
|---|---|---|
| V-MD-01 | `"**굵게** 와 표\n\n|a|b|\n|-|-|\n|1|2|"` | `<strong>`, `<table>` 있음 |
| V-MD-02 | `"<script>alert(1)</script>안녕"` | `script` 요소 0, "안녕" 보임 |
| V-MD-03 | `"<img src=x onerror=alert(1)>"` / `"<b>굵게</b>"` | `img`·`b` 요소 0 |
| V-MD-04 | `"![지도](https://evil.example/leak?q=1)"` | `img` 요소 0, `evil.example` 요청 없음(fetch·Image 감시) |
| V-MD-05 | `"[홈](https://www.royalpalace.go.kr/)"`, 허용 `["https://www.royalpalace.go.kr/"]`, true | `a[href="https://www.royalpalace.go.kr/"]`, `target=_blank`, `rel`에 `noopener`·`noreferrer` |
| V-MD-06 | 같은 입력, `linksEnabled false` | `a` 0, `span` 안에 "홈" |
| V-MD-07 | `"[여기](https://evil.example/)"`, 허용 목록에 없음 | `a` 0 |
| V-MD-08 | 본문 맨 URL `https://www.royalpalace.go.kr` (자동 링크), 허용 `["https://www.royalpalace.go.kr/"]` | 링크(끝 `/` 차이 정규화) |
| V-MD-09 | `"[x](javascript:alert(1))"`, 허용 목록에 같은 문자열 | `a` 0 |
| V-MD-10 | 한글 경로 `https://example.org/경복궁` 허용, 본문 같은 주소 | 링크(퍼센트 인코딩 차이 정규화) |
| V-MD-11 | `isAllowedUrl` 표: `#frag` 차이 같음 / 호스트 대소문자 같음 / 쿼리 다름 → false / `mailto:`·`tel:`·`data:` → false / `undefined` → false | 표대로 |

#### A4. 컴포넌트 — `tests/unit/chat-view.test.tsx`, `message-bubble.test.tsx`, `sidebar.test.tsx`, `status-line.test.tsx`

| ID | 대상 | 동작 | 기대 |
|---|---|---|---|
| V-CV-01 | ChatView(sessionId null) | 질문 전송 | `POST /api/chat/sessions` → 주소가 `/<id>`로(`history.replaceState` 호출), 이어서 메시지 POST |
| V-CV-02 | ChatView | `pass.txt` 응답 | 마지막 화면에 `✓ 확인됨`, 링크 1개 클릭 가능, `onTurnDone` 1회 |
| V-CV-03 | ChatView | 전송 중 | 전송 버튼 비활성, Enter 눌러도 요청 1회 |
| V-CV-04 | ChatView | 한글 조합 중 Enter(`isComposing`) | 전송 안 함 |
| V-CV-05 | ChatView | 공백만 | 전송 안 함 |
| V-CV-06 | ChatView | 429 `quota_exceeded` | 말풍선 없음, 입력창에 질문 되돌림, 알림에 서버 문구, 버튼 없음 |
| V-CV-07 | ChatView | 409 `session_full` | 알림 + "새 대화" 버튼 → `router.push("/")` |
| V-CV-08 | ChatView | 401 | `router.replace("/login")` |
| V-CV-09 | ChatView | 403 `pending_approval` | `replace("/pending")` |
| V-CV-10 | ChatView | `error.txt` → "다시 시도" | 같은 질문으로 POST 1회 더, 오류 쌍 제거 |
| V-CV-11 | ChatView | 스트림 중 언마운트 | `AbortController.abort` 호출, 오류 표시 없음 |
| V-CV-12 | ChatView | 1001자 붙여넣기 | `maxLength`로 1000자 |
| V-MB-01 | MessageBubble | 진행 중 답변 | StatusLine 보임, 배지 없음 |
| V-MB-02 | MessageBubble | 이력 failed | `⚠ 확인 못 함` |
| V-MB-03 | MessageBubble | blocked | 회색 안내, `actions` 안 그림 |
| V-MB-04 | MessageBubble | done + sources(tour·web) | `경복궁 — 한국관광공사 · 기준일 2026-11-20`, web은 허용이면 링크 |
| V-MB-05 | MessageBubble | 사용자 글 `"**x** <b>y</b>"` | 글 그대로(마크다운·HTML 해석 없음) |
| V-MB-06 | MessageBubble | done + id 있음 + `actions` | actions 렌더 / id null이면 안 그림 |
| V-SB-01 | Sidebar | 목록 2개(title null 1개) | "새 대화"·제목 표시, 현재 강조 |
| V-SB-02 | Sidebar | 삭제 → confirm 취소 | DELETE 없음 |
| V-SB-03 | Sidebar | 삭제 → 확인, 현재 세션 | DELETE → 목록에서 제거 → `replace("/")` |
| V-SB-04 | Sidebar | DELETE 404 | 목록에서 제거, 오류 없음 |
| V-SB-05 | Sidebar | `refreshKey` 변경 | GET 다시 |
| V-SL-01 | StatusLine | 표(§7.4) 각 phase | 해당 글 / drafting·done은 null |

---

### B. Playwright — `web/e2e/chat.spec.ts`

로그인·세션은 route로 대체: `GET /api/auth/me` → active 사용자, `GET /api/chat/sessions` → 목록, `POST /api/chat/sessions` → `{id:"00000000-0000-0000-0000-000000000001", …}`, `GET /api/chat/sessions/<id>` → 이력, `POST …/messages` → `route.fulfill({status:200, headers:{"content-type":"text/event-stream"}, body: 파일 내용})`. (본문이 한 번에 오므로 "토큰 단위 표시"는 HITL에서 본다.)

| ID | 시나리오 | 기대 |
|---|---|---|
| P-CH-01 합격 | `pass.txt` | 사용자 말풍선이 `010-****-****…`로 바뀜, 본문, `✓ 확인됨`, 링크 클릭 시 새 탭 `royalpalace.go.kr`(새 페이지 이벤트만 확인, 실제 이동은 `route.abort`), 출처 줄 |
| P-CH-02 교체 | `replaced.txt` | 본문이 수정본, `✓ 확인됨` |
| P-CH-03 경고 | `warning.txt` | 경고 상자 문구 |
| P-CH-04 차단 | `blocked.txt` | 안내 상자, 👍 등 버튼 영역 없음, 새로고침(이력 route = 빈 메시지) 후 사라짐 |
| P-CH-05 오류·재시도 | 첫 응답 `error.txt`, 두 번째 `pass.txt` | 오류 문구 → "다시 시도" → `✓ 확인됨`, 요청 본문 두 번 다 같은 text |
| P-CH-06 첫 질문 주소 | `/`에서 전송 | 주소 `/00000000-…-0001`, 스트림 끊기지 않음(`done`까지 화면 반영) — `history.replaceState` 확인 |
| P-CH-07 이력 | `/<id>` 이력(passed·failed·security_replaced) | 배지·링크 규칙대로 |
| P-CH-08 사이드바·삭제 | 목록 → 삭제 확인(dialog accept) | DELETE 요청, 목록에서 사라짐 |
| P-CH-09 모바일 | `mobile-chrome` 프로젝트, 햄버거로 서랍 열기 → 세션 선택 | 서랍 닫히고 그 대화 |
| P-CH-10 렌더러 안전 | 본문에 `<img src=…>`·`![x](https://evil.example/a.png)` 포함 SSE | 페이지 전체 `img` 0, `evil.example` 요청 0(`page.on("request")`) |
| P-CH-11 정적 경로 우선 | `/account`, `/sw.js`, `/manifest.webmanifest` | 각각 계정 화면·JS·JSON(동적 `[sessionId]`로 가지 않음) |
| P-CH-12 한도 초과 | 메시지 route가 429 `{code:"quota_exceeded", message:"오늘 질문 한도(50회)를 다 썼어요. 내일 0시(한국 시간)에 다시 이용해 주세요.", limit:50, used:50}` | 말풍선 없음, 입력창에 질문 되돌림, 알림에 그 문구, "추가 요청" 같은 버튼 없음(FR-62, 2026-11-22) |
| P-CH-R1 `@real` | 실제 compose, active 사용자(14 `approve`), "경복궁 관람 시간 알려줘" | `✓ 확인됨` 또는 경고로 끝남, 사이드바에 세션, 새로고침 후 이력 같음 |

### 통과 기준
- A 전부, B(`@real` 제외) 전부 통과. `@real`은 G5 전 1회 실행 결과를 보고.

---

## ② HITL

전제: 15 적용 compose, 터널 주소 `<HOST>`, active 계정, 01·03 적재 데이터(관광 질문 답이 나올 것).

### HITL-1 모바일 토큰 단위 표시 (A11)
1. 휴대폰(Android Chrome, 가능하면 iOS Safari도)에서 `https://<HOST>` 로그인(14 PWA로 설치했다면 홈 화면 앱으로).
2. 긴 답이 나올 질문: "제주 동쪽 1박 2일 일정 짜줘. 관광지 5곳 넣어서."
3. 확인: 글이 **몇 글자씩 늘어나며** 보이는지(한 번에 통째로 나오지 않는지), 위 상태 줄이 "질문을 확인하고 있어요 → 관광 정보 찾는 중 → 자료와 대조해 확인하고 있어요" 순서로 바뀌는지, 끝에 `✓ 확인됨` 또는 경고.
4. 화면 녹화(선택)로 남긴다.

### HITL-2 머리말·교체 화면 일관성 (A30)
1. 툴을 부르는 질문 3개(예: "이번 주말 서울 축제", "국립중앙박물관 휴관일", "경복궁 근처 맛집") — 머리말("찾아볼게요")이 보였다가 툴 라벨로 바뀌며 지워지는지, 어색한 깜박임이 있는지.
2. 수정본 교체(`replaced`)가 나오면(나오지 않으면 기록만) 화면이 자연스럽게 바뀌는지.

### HITL-3 안전 렌더러 수동 확인
1. "경복궁 공식 홈페이지 주소 알려줘" → 답변의 홈페이지 링크가 초안 동안 눌리지 않고, `✓ 확인됨` 뒤에 눌리는지.
2. "<b>굵게</b> 라고 그대로 써줘" → 굵게 보이지 않고 글로 보이거나 사라지는지.

### HITL-4 사이드바·이력·삭제
1. 질문 2개 → 사이드바 제목 생김(몇 초 뒤 다른 대화 클릭했다 돌아오면) → 새로고침해도 같은 이력·배지·링크.
2. 삭제 → 확인창 → 목록에서 사라지고 주소로 직접 가면 "대화를 찾을 수 없어요".

### HITL 결과 보고 양식
| 항목 | 결과 (기기·브라우저) |
|---|---|
| A11 모바일 토큰 단위 표시(Android / iOS) | 통과·실패 |
| 상태 줄 전환 순서 | |
| A30 머리말 지움 어색함 여부 | |
| 초안 중 링크 비활성 → 확인 뒤 활성 | |
| HTML이 그려지지 않음 | |
| 제목 생성·이력·삭제 | |
| `@real` Playwright 결과 | |
