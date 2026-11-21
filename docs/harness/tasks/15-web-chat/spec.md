# 15-web-chat — 채팅 화면·SSE 파서·안전 렌더러 (spec)

> 하네스 Phase 4 산출물 (spec-writer, 작성 2026-11-21). 상태: **초안 — 사용자 검토 대기**. 브랜치 `feat/15-web-chat`, 의존 작업 09-chat-sessions, 11-quota-usage, 14-web-foundation (→ 12·08·02).
> 근거: [PL]=program_list.md(G4 승인본) §2 표·§3 "15-web-chat" · [A]=architecture.md(G3 재승인본) §2.1 web(렌더 규칙)·§3.1(SSE 이벤트 표·실패 처리)·§3.8 [5 화면]·ADR-04·19·22 · [R]=requirements.md FR-10·15·16·17·18·20·21·91, NFR-14·23 · [S]=S16.
> **이어받는 확정 spec**: [02](SSE 전송 형식 §4.1·이벤트 §4.2·`done` 필드 §4.3·순서 §4.4·`Source` 모양·고정 문구는 서버가 보냄) · [08](`meta{session_id,user_text_masked,masked_types}`가 첫 이벤트, `blocked` 코드 5종, `done{blocked:true}`) · [09](세션 API 4개·`SessionOut`·`SessionDetailOut`·`MessageOut`(`allowed_urls` 포함)·`ChatRequest{text, location?}`·`session_not_found`·`session_full`·빈 세션 목록 숨김) · [11](`too_many_requests`·`quota_exceeded` 429·`done.quota_remaining`) · [12](캐시 적중 순서 `status answering → delta(전체 1번) → draft_done → verified → done{cached:true, verify_status:"cached"}` — "`cached` 표시 여부는 15가 정함") · [14](`apiFetch`·`apiJson`·`ApiError`·`AuthGate`·`useMe`·`(chat)/layout.tsx`·임시 `(chat)/page.tsx`).
> **미확인** = 문서·공식 자료로 확인하지 못한 사실.

---

## 1. 작업 목표

로그인한 사용자가 PC·모바일 브라우저에서 질문하고, 답변 초안이 토큰 단위로 흐르다 "✓ 확인됨"·수정본 교체·경고·차단·오류(재시도)로 끝나는 채팅 화면을 만든다. 사이드바에서 지난 대화를 보고 새 대화를 시작하고 삭제한다 [PL §3].

- SSE 파서: `fetch` + `ReadableStream`으로 [A] §3.1 이벤트 전부를 읽고 `: ping`은 무시(S16, POST + CSRF 헤더).
- 안전 렌더러: raw HTML 끔, `img` 안 그림, 링크는 `done.allowed_urls`(이력은 `MessageOut.allowed_urls`)에 있고 `done` 이후일 때만 클릭 가능, 그 외는 일반 글(ADR-22, NFR-14).
- `tool` 이벤트를 받으면 그때까지 보인 delta를 지운다([A] §3.1 — A30). `meta`를 받으면 사용자 말풍선을 가린 텍스트로 바꾼다(NFR-35).

### 1.1 넣지 않는 것
| 빠지는 것 | 들어오는 작업 / 이유 |
|---|---|
| 👍/👎, "추가 요청" 버튼, 위치 동의 토글 | 16 (15는 429 `quota_exceeded`일 때 서버 문구만 표시, 버튼 자리만 둠) |
| 녹음·스피커 버튼 | 17 |
| 오늘 남은 질문 수 표시(`done.quota_remaining`) | 요구사항 없음 — 표시하지 않음(값은 상태에 저장만) |
| 메시지 단위 삭제·수정·복사 버튼 | FR-20(세션 단위 삭제만) |
| 클라이언트 쪽 무응답 시간 초과 | 서버 180초 타임아웃·15초 ping으로 충분 — 넣지 않음 |
| 세션 이름 바꾸기·검색 | 요구사항 없음 |
| 출처 카드의 이미지 | FR-21 |

---

## 2. 생성·수정 파일

| 파일 | 신규/수정 | 역할 |
|---|---|---|
| `web/lib/sse.ts` | 신규 | SSE 줄 파서·이벤트 타입·`streamChat` (§4) |
| `web/lib/chat-state.ts` | 신규 | 화면 메시지 모델·이력 변환·이벤트 적용(순수 함수, §5) |
| `web/lib/chat-api.ts` | 신규 | 세션 API 4개 함수·타입(`SessionOut` 등) (§6) |
| `web/components/chat/ChatView.tsx` | 신규 | 메시지 목록·입력창·전송·스트림 소비·재시도·SSE 전 오류 처리 (§7.1) |
| `web/components/chat/MessageBubble.tsx` | 신규 | 말풍선(사용자/답변), 확인 배지·경고·차단·오류·출처 (§7.2) |
| `web/components/chat/SafeMarkdown.tsx` | 신규 | 안전 마크다운 렌더러·링크 허용 판정 (§8) |
| `web/components/chat/Sidebar.tsx` | 신규 | 세션 목록·새 대화·삭제, 모바일 서랍 (§7.3) |
| `web/components/chat/StatusLine.tsx` | 신규 | 진행 단계 한 줄 (§7.4) |
| `web/app/(chat)/page.tsx` | 교체(14 임시) | 새 대화 화면 (§7.5) |
| `web/app/(chat)/[sessionId]/page.tsx` | 신규 | 대화 이어 보기 (§7.5) |
| `web/app/(chat)/layout.tsx` | 수정(14) | AuthGate 안에 사이드바 + 본문 2열(모바일은 서랍) |
| `web/tests/unit/*`, `web/e2e/chat*.spec.ts`, `web/e2e/fixtures/sse/*.txt` | 신규 | test.md |

> [PL] 파일 목록 밖: `chat-state.ts`(상태 전이를 컴포넌트 밖 순수 함수로 — Vitest "상태 전이" 테스트 대상), `chat-api.ts`(세션 API 함수), `(chat)/layout.tsx` 수정. 백엔드 변경 없음.

---

## 3. 설정

새 환경변수 없음. 상수:

| 상수 | 위치 | 값 | 근거 |
|---|---|---|---|
| `MAX_QUESTION_CHARS` | `ChatView.tsx` | `1000` | 02 `ChatRequest.text` 규칙(1,000자 초과 422) |

---

## 4. SSE 파서 (`web/lib/sse.ts`)

### 4.1 이벤트 타입 (서버 정의 그대로 — 02 §4.2·08·12)
```ts
export type Source =
  | { type: "tour"; contentid: string; title: string | null; source: string | null; as_of: string | null }
  | { type: "web"; url: string; title: string | null };
export type VerifyStatus = "passed" | "failed" | "security_replaced" | "cached";
export type BlockCode = "unsafe" | "self_harm" | "jailbreak" | "injection" | "off_topic";
export type ErrorCode = "llm_unavailable" | "guard_unavailable" | "timeout";

export type ChatEvent =
  | { type: "meta"; session_id: string; user_text_masked: string; masked_types: string[] }
  | { type: "status"; stage: "checking" | "answering" | "verifying" | "revising"; attempt?: number }
  | { type: "tool"; name: string; label: string }
  | { type: "delta"; text: string }
  | { type: "draft_done" }
  | { type: "verified" }
  | { type: "replaced"; text: string; attempt: number }
  | { type: "warning"; code: "unverified"; message: string }
  | { type: "blocked"; code: BlockCode; message: string }
  | { type: "done"; assistant_message_id: number | null; user_message_id: number | null; sources: Source[];
      allowed_urls: string[]; verify_status: VerifyStatus | null; rewrite_count: number; cached: boolean;
      quota_remaining: number | null; blocked: boolean }
  | { type: "error"; code: ErrorCode; message: string };
```

### 4.2 함수
```ts
/**
 * 바이트 조각을 받아 SSE 이벤트(이름, data 문자열)를 내보내는 줄 단위 파서.
 * @param onEvent - 빈 줄로 이벤트 하나가 끝날 때마다 호출(name 기본 "message")
 * @returns push(텍스트 조각) / end()(남은 버퍼 처리)
 */
export function createSseParser(onEvent: (name: string, data: string) => void): { push(text: string): void; end(): void };

/** 이름·data를 ChatEvent로 바꾼다. 모르는 이벤트 이름은 null(무시), JSON이 깨졌으면 SseProtocolError. */
export function toChatEvent(name: string, data: string): ChatEvent | null;

export class SseProtocolError extends Error {}

/**
 * 응답 본문을 읽어 ChatEvent를 차례로 돌려준다. done 또는 error를 받으면 끝낸다.
 * @throws SseProtocolError — done/error 없이 본문이 끝남("stream_ended") 또는 JSON 오류
 */
export async function* readChatEvents(res: Response): AsyncGenerator<ChatEvent>;

/**
 * 질문을 보내고 이벤트 스트림을 돌려준다. SSE 시작 전 실패(401·403·404·409·422·429)는 ApiError로 던진다(14 apiFetch).
 * @param sessionId - 대화 세션 UUID
 * @param body - { text, location? } (location은 16)
 * @param signal - 화면을 떠나거나 새 대화로 갈 때 끊기 위한 AbortSignal
 */
export async function streamChat(sessionId: string, body: { text: string; location?: { lat: number; lng: number } },
                                 signal: AbortSignal): Promise<AsyncGenerator<ChatEvent>>;
```

### 4.3 파싱 규칙 (SSE 표준 중 쓰는 부분)
1. 바이트 → 글: `TextDecoder("utf-8")`를 `{ stream: true }`로 — 한글 3바이트가 조각 경계에서 잘려도 깨지지 않게.
2. 줄 끝: `\n`, `\r\n`, `\r` 모두 허용. 조각 끝의 미완성 줄은 다음 조각과 합친다.
3. `:`로 시작하는 줄(예: `: ping`) → 무시.
4. `event: X` → 이름, `data: Y` → data 줄 추가(여러 줄이면 `\n`으로 이음. 02는 항상 한 줄), 필드 이름 뒤 첫 공백 1개만 제거. `id`·`retry`·모르는 필드 → 무시.
5. 빈 줄 → data가 있으면 `onEvent(name ?? "message", data)` 후 초기화. data 없는 이벤트(ping만)는 내보내지 않는다.
6. `toChatEvent`: 모르는 이름(앞으로 서버가 추가할 이벤트) → `null`로 **무시**. 아는 이름인데 `JSON.parse` 실패 → `SseProtocolError`.
7. `readChatEvents`: `done`·`error`를 내보낸 뒤 즉시 끝(뒤 바이트 무시, `reader.cancel()`). 본문이 그 전에 끝나면 `SseProtocolError("stream_ended")`.
8. `streamChat`: `apiFetch(\`/api/chat/sessions/${encodeURIComponent(sessionId)}/messages\`, { method: "POST", json: body, signal, headers: { Accept: "text/event-stream" } })` → `readChatEvents(res)`.

---

## 5. 화면 메시지 모델·상태 전이 (`web/lib/chat-state.ts`)

### 5.1 모델
```ts
export type Phase = "waiting" | "checking" | "answering" | "drafting" | "verifying" | "revising" | "done" | "blocked" | "error";

export interface UserMessage { kind: "user"; key: string; id: number | null; text: string; maskedTypes: string[] }
export interface AssistantMessage {
  kind: "assistant"; key: string; id: number | null;
  text: string;                 // 지금 보이는 본문(초안·수정본·안전 문구·차단 안내)
  phase: Phase;
  toolLabel: string | null;     // 진행 중인 툴 라벨(StatusLine)
  attempt: number;              // revising 차수
  verified: boolean;            // "✓ 확인됨" 표시 여부
  verifyStatus: VerifyStatus | null;
  warning: string | null;       // 경고 문구(실시간은 서버 message, 이력은 null — §7.2)
  blocked: { code: BlockCode; message: string } | null;
  error: { code: string; message: string } | null;
  sources: Source[];
  allowedUrls: string[];
  linksEnabled: boolean;        // done 이후·이력만 true
  cached: boolean;
  retryText: string | null;     // error일 때 다시 보낼 질문(화면에 안 보임)
}
export type UiMessage = UserMessage | AssistantMessage;
```

### 5.2 함수
```ts
/** 세션 조회 응답(09 MessageOut[])을 화면 메시지로 바꾼다. 이력 답변은 phase "done", linksEnabled true. */
export function fromHistory(messages: MessageOut[]): UiMessage[];
/** 질문을 보낼 때 사용자 말풍선 + 빈 답변(phase waiting) 2개를 만든다. */
export function startTurn(text: string, keySeed: string): [UserMessage, AssistantMessage];
/** 이벤트 1개를 그 턴의 (사용자, 답변) 쌍에 적용한 새 쌍을 돌려준다(순수 함수 — 원본 불변). */
export function applyEvent(pair: [UserMessage, AssistantMessage], ev: ChatEvent): [UserMessage, AssistantMessage];
/** 스트림이 done/error 없이 끊기거나 파싱 오류일 때 답변을 오류 상태로 바꾼다. */
export function failTurn(pair: [UserMessage, AssistantMessage], kind: "stream_ended" | "protocol"): [UserMessage, AssistantMessage];
```

### 5.3 전이 표 (`applyEvent`)
| 이벤트 | 사용자 말풍선 | 답변 |
|---|---|---|
| `meta` | `text = user_text_masked`, `maskedTypes` | — |
| `status checking` | | `phase=checking` |
| `status answering` | | `phase=answering` |
| `tool` | | **`text=""`**(머리말 지움), `toolLabel=label`, `phase=answering` |
| `delta` | | `text += t`, `phase=drafting`, `toolLabel=null` |
| `draft_done` | | (변화 없음 — 링크는 여전히 비활성) |
| `status verifying` | | `phase=verifying` |
| `status revising` | | `phase=revising`, `attempt` |
| `replaced` | | `text = replaced.text` (phase 유지) |
| `verified` | | `verified=true` |
| `warning` | | `warning = message` |
| `blocked` | | `phase=blocked`, `blocked={code,message}`, `text=message` |
| `done` (blocked=false) | `id = user_message_id` | `phase=done`, `id=assistant_message_id`, `sources`, `allowedUrls`, `verifyStatus`, `cached`, **`linksEnabled=true`** |
| `done` (blocked=true) | | `phase=blocked` 유지, `linksEnabled=false` |
| `error` | | `phase=error`, `error={code,message}`, **`text=""`**(검증 못 한 초안 숨김 — 15-Q2), `retryText` = 보낸 질문 |
| (`failTurn`) | | `phase=error`, `error={code:"network", message: MSG_STREAM_ENDED}`, `text=""`, `retryText` |

- `MSG_STREAM_ENDED` = `연결이 끊겨 답변을 받지 못했어요. 다시 시도해 주세요.`(화면 문구, `chat-state.ts` 상수).
- 이벤트 순서가 어긋나도(예: `delta`가 `verifying` 뒤) 표대로 적용만 한다 — 서버가 순서를 보장(02 §4.4). 방어 코드 없음.
- `fromHistory`: assistant는 `verified = verifyStatus in ("passed","cached")`, `warning=null`, `linksEnabled=true`, `allowedUrls = m.allowed_urls ?? []`, `sources = m.sources ?? []`. user는 저장된 가린 텍스트.

---

## 6. 세션 API 함수 (`web/lib/chat-api.ts`)

```ts
export type SessionOut = { id: string; title: string | null; turn_count: number; created_at: string; updated_at: string };
export type MessageOut = { id: number; turn_no: number; role: "user" | "assistant"; content: string; created_at: string;
  pii_types?: string[] | null; sources?: Source[] | null; allowed_urls?: string[] | null; verify_status?: VerifyStatus | null;
  rewrite_count?: number | null; from_cache?: boolean | null; feedback?: { rating: "up" | "down"; reason: string | null } | null };
export type SessionDetailOut = SessionOut & { messages: MessageOut[] };

export function listSessions(): Promise<SessionOut[]>;                 // GET  /api/chat/sessions → .sessions
export function createSession(): Promise<SessionOut>;                  // POST /api/chat/sessions (201)
export function getSession(id: string): Promise<SessionDetailOut>;     // GET  /api/chat/sessions/{id}
export function deleteSession(id: string): Promise<void>;              // DELETE (204)
```
- `feedback`은 13이 넣는 필드(16이 사용). 15는 읽기만 하고 쓰지 않는다.

---

## 7. 컴포넌트·페이지

모두 `"use client"`. 데이터는 브라우저에서만 `/api` 호출(ADR-12).

### 7.1 `ChatView`
```tsx
/**
 * 한 대화의 메시지 목록과 입력창. 질문을 보내 SSE를 받아 화면에 반영한다.
 * @param sessionId - 기존 대화면 UUID, 새 대화 화면이면 null(첫 전송 때 세션을 만든다)
 * @param initialMessages - 이력(fromHistory 결과). 새 대화면 []
 * @param onTurnDone - done을 받았을 때(사이드바 목록 새로고침용)
 */
export function ChatView(props: { sessionId: string | null; initialMessages: UiMessage[]; onTurnDone?: () => void }): JSX.Element;
```
상태: `messages: UiMessage[]`, `sessionId`, `busy: boolean`(스트림 진행 중), `notice: { code: string; message: string; body?: Record<string, unknown> } | null`(입력창 위 알림), `input: string`.

전송 처리 순서:
1. `text = input.trim()`; 비었거나 `busy`면 무시. 입력창 비우고 `busy = true`.
2. `sessionId`가 null이면 `createSession()` → `sessionId` 저장 → **`window.history.replaceState(null, "", \`/${id}\`)`**(라우터 이동 없이 주소만 바꿈 — 컴포넌트가 다시 마운트돼 스트림이 끊기지 않게, Next 16 App Router가 이 방식을 지원 — **미확인**, Playwright로 확인).
3. `startTurn(text)`로 말풍선 2개 추가, 화면 맨 아래로 스크롤.
4. `AbortController` 생성(언마운트 시 `abort()`). `for await (ev of await streamChat(id, {text}, signal))` → `applyEvent`로 그 쌍만 갱신.
5. `done` → `onTurnDone?.()`.
6. `SseProtocolError` → `failTurn`. `AbortError` → 아무것도 안 함(화면을 떠남).
7. **SSE 시작 전 `ApiError`** → 3에서 추가한 말풍선 2개를 지우고 **입력창에 `text`를 되돌린 뒤** `notice`에 서버 문구:

| 코드 | 화면 |
|---|---|
| `unauthenticated`(401) | `router.replace("/login")` |
| `pending_approval`(403) | `router.replace("/pending")` |
| `session_not_found`(404) | notice + "새 대화" 버튼 |
| `session_full`(409) | notice(09 문구 "…50개를 모두 채웠어요. 새 대화를 시작해 주세요.") + "새 대화" 버튼 (FR-15) |
| `too_many_requests`(429) | notice(05 문구) |
| `quota_exceeded`(429) | notice(11 문구) — **16이 여기에 "추가 요청" 버튼을 붙인다**(`notice.body.request_status` 전달) |
| `validation_error`·`csrf_failed`·`network_error`·`server_error` | notice |
8. `finally` → `busy = false`.

재시도(FR-18): 오류 답변의 "다시 시도" 버튼 → 그 쌍을 지우고 `retryText`로 1~8을 다시(같은 세션). 실패 턴은 서버에 저장·차감되지 않았으므로 안전([A] §3.1 실패 처리).

입력창: `<textarea maxLength={1000}>`, Enter = 전송, Shift+Enter = 줄바꿈, 한글 조합 중(`isComposing`) Enter는 전송하지 않음. `busy` 동안 전송 버튼 비활성(같은 세션 동시 질문 방지). 첫 화면(메시지 0개)에는 안내 한 줄 "서울·제주 여행지, 맛집, 축제, 교통을 물어보세요."

### 7.2 `MessageBubble`
```tsx
/** 사용자 또는 답변 말풍선 1개. actions는 16·17이 버튼을 꽂는 자리. */
export function MessageBubble(props: { message: UiMessage; onRetry?: () => void; actions?: React.ReactNode }): JSX.Element;
```
- 사용자: 오른쪽 정렬, 일반 글(마크다운 아님 — 사용자 글은 그대로 텍스트), 가린 부분은 서버가 준 `*` 모양 그대로.
- 답변: 왼쪽, `SafeMarkdown(text, allowedUrls, linksEnabled)`. 아래 줄:

| 상태 | 표시 |
|---|---|
| `phase` 진행 중(`waiting`~`revising`) | 말풍선 아래 `StatusLine` |
| `verified` | 배지 `✓ 확인됨` |
| `warning`(실시간) | 노란 알림 상자에 서버 `message` |
| 이력 `verifyStatus=="failed"` | 배지 `⚠ 확인 못 함`(문구 원문은 이력에 없음 — 15-Q3) |
| `verifyStatus=="security_replaced"` | 배지 없음(본문이 서버 고정 안전 문구) |
| `blocked` | 회색 안내 상자에 서버 `message`(마크다운 아님), 배지 없음 |
| `error` | 빨간 안내 상자에 서버 `message` + "다시 시도" 버튼(`onRetry`) |
| `cached` | 따로 표시 안 함 — `✓ 확인됨`만(15-Q1) |
| `phase=="done"`이고 `sources.length>0` | 출처 목록(§7.2.1) |
| `phase=="done"`이고 `id != null` | `actions` 영역(16·17) |

#### 7.2.1 출처 목록 (FR-21 "출처·기준일")
- tour: `• {title ?? "관광 정보 " + contentid} — {source ?? "한국관광공사"} · 기준일 {as_of}` (`as_of`가 null이면 기준일 생략). 링크 없음.
- web: `• {title ?? url}` — `url`이 허용 목록(§8.2)이고 `linksEnabled`면 링크, 아니면 글.
- 본문 속 `(#126508)` 인용 표기는 그대로 둔다(서버 출처 형식).

### 7.3 `Sidebar`
```tsx
/** 지난 대화 목록·새 대화·삭제. 모바일에선 햄버거 버튼으로 여닫는 서랍. */
export function Sidebar(props: { currentId: string | null; refreshKey: number }): JSX.Element;
```
- `listSessions()` — 마운트 시·`refreshKey` 바뀔 때. 항목: `title ?? "새 대화"`, `updated_at` 날짜(오늘이면 시:분). 현재 세션 강조.
- "새 대화" → `router.push("/")`(세션은 첫 전송 때 만듦 — 빈 세션이 쌓이지 않게, 09 Q6과 같은 취지).
- 삭제(항목 옆 휴지통) → `window.confirm("이 대화를 삭제할까요? 되돌릴 수 없어요.")` → `deleteSession` → 목록에서 제거, 현재 세션이었으면 `router.replace("/")`. 404(이미 없음)도 목록에서 제거.
- 하단: 아이디 + "계정" 링크(`/account`).
- 목록 오류 → 목록 자리에 서버 문구 + "다시 시도".
- 제목은 서버가 첫 답변 뒤 백그라운드로 만든다(09) — `onTurnDone`으로 목록을 다시 받을 때 아직 없으면 "새 대화"로 보이고 다음 갱신 때 바뀐다(추가 폴링 없음).

### 7.4 `StatusLine`
```tsx
/** 진행 단계를 한 줄 글로 보여 준다(점 3개 애니메이션). */
export function StatusLine(props: { phase: Phase; toolLabel: string | null; attempt: number }): JSX.Element | null;
```
| phase | 글 |
|---|---|
| `waiting`·`checking` | 질문을 확인하고 있어요 |
| `answering` | `toolLabel ?? "답변을 준비하고 있어요"` |
| `drafting` | (표시 안 함 — 글이 흐르는 중) |
| `verifying` | 자료와 대조해 확인하고 있어요 |
| `revising` | 답변을 다듬고 있어요 ({attempt}번째) |
| 그 밖 | null |
- 툴 라벨은 서버가 준 글 그대로(02·10 `label`).

### 7.5 페이지
- `(chat)/layout.tsx`(14 수정): `<AuthGate>` 안에 `Sidebar` + `<main>`. PC는 2열, 폭 768px 미만은 사이드바를 서랍으로. `refreshKey`는 레이아웃 상태(컨텍스트로 `bump()` 제공 → ChatView `onTurnDone`).
- `(chat)/page.tsx`(새 대화): `<ChatView sessionId={null} initialMessages={[]} />`.
- `(chat)/[sessionId]/page.tsx`: `getSession(id)` → 로딩 중 "불러오는 중…" → `fromHistory` → `<ChatView key={id} sessionId={id} initialMessages={…} />`. 404 → "대화를 찾을 수 없어요…"(서버 문구) + "새 대화" 링크. `key={id}`로 다른 세션으로 이동하면 진행 중 스트림을 끊는다(언마운트 → abort).
- 정적 경로(`/account`, `/login` 등)·`/sw.js`·`/manifest.webmanifest`가 `[sessionId]`보다 우선하는지 — Next 규칙상 정적 경로·public 파일이 우선(**미확인**, 14 P-PWA-03·15 Playwright로 확인).

---

## 8. 안전 렌더러 (`SafeMarkdown.tsx`) — NFR-14, ADR-22

### 8.1 시그니처·설정
```tsx
/**
 * 답변 마크다운을 안전하게 그린다. raw HTML·이미지는 만들지 않고, 링크는 허용 목록에 있고 linksEnabled일 때만 클릭 가능.
 * @param text - 답변 본문(마크다운)
 * @param allowedUrls - done.allowed_urls 또는 이력의 allowed_urls
 * @param linksEnabled - done 이후·이력이면 true, 초안 단계면 false
 */
export function SafeMarkdown(props: { text: string; allowedUrls: readonly string[]; linksEnabled: boolean }): JSX.Element;

/** href가 허용 목록 URL과 같은지(정규화 후 비교). http·https 외 스킴은 항상 false. */
export function isAllowedUrl(href: string | undefined, allowedUrls: readonly string[]): boolean;
```
- `react-markdown` + `remarkPlugins={[remarkGfm]}`, **`skipHtml`**(raw HTML 노드를 버림), `rehype-raw` 쓰지 않음.
- `disallowedElements={["img"]}` — 이미지 요소를 만들지 않는다(대체 글도 표시 안 함, FR-21). 브라우저가 이미지 주소로 요청하지 않는다(유출 경로 차단).
- `components.a` = `SafeLink`: `linksEnabled && isAllowedUrl(href)`이면 `<a href target="_blank" rel="noopener noreferrer nofollow" referrerPolicy="no-referrer">`, 아니면 `<span>`(자식 글만, 밑줄 없음). GFM 자동 링크(본문의 맨 URL)도 같은 규칙.
- 표(GFM)·목록·굵게·코드는 그대로.

### 8.2 URL 비교 (`isAllowedUrl`)
- `canon(u)`: `new URL(u)` 성공 && 스킴 `http:`/`https:` → 해시 제거 → `href` 문자열 → 끝 `/` 1개 제거. 실패·다른 스킴(`javascript:`·`data:`·`mailto:`·`tel:`) → null.
- `isAllowedUrl(href) = canon(href) !== null && allowedUrls.some(a => canon(a) === canon(href))`.
- 이유: 서버 `allowed_urls`는 원문 표기(02 §4.3), `react-markdown`은 링크 주소의 한글 등을 퍼센트 인코딩할 수 있다(**미확인**) — 양쪽을 `URL`로 정규화하면 같아진다. 서버 `normalize_url`(호스트 소문자·끝 `/`·해시 제거)과 같은 방향.
- 일치하지 않으면 안전한 쪽(글)으로 떨어진다.

---

## 9. 엣지케이스

| 상황 | 동작 |
|---|---|
| 한글이 조각 경계에서 잘림 | `TextDecoder` stream 모드로 정상 |
| `event:`와 `data:`가 다른 조각으로 옴 | 버퍼링으로 정상 |
| 한 조각에 이벤트 여러 개 | 모두 차례로 |
| `: ping`만 계속 옴 | 화면 변화 없음 |
| 모르는 이벤트 이름 | 무시 |
| data JSON 깨짐 | 오류 상태 + 다시 시도 |
| `done` 없이 연결 끊김(모바일 앱 전환 등) | "연결이 끊겨…" + 다시 시도 |
| 툴 호출 전 머리말 "찾아볼게요" delta → `tool` | 머리말 지워짐, 툴 라벨 표시(A30) |
| 초안 속 링크 | 클릭 불가(글) — `done` 뒤 허용분만 링크로 바뀜 |
| 초안 속 `![x](https://evil/?q=…)` | 이미지 요소 없음, 요청 없음 |
| `<script>`·`<img onerror>`·`<a href="javascript:">` | 요소 생성 안 됨 / 글 |
| 허용 목록 밖 URL | 글로 보임 |
| `replaced`(수정본) | 화면 본문 교체 → `verified` → ✓ |
| `replaced`(보안 고정 문구) → `done{security_replaced}` | 교체된 문구, 배지 없음 |
| `warning` | 경고 상자, 본문 유지(또는 앞선 `replaced` 본문) |
| `blocked` | 안내 상자, 사용자 말풍선은 가린 글, 새로고침하면 둘 다 사라짐(저장 안 됨 — ADR-27) |
| `error` | 초안 숨김, 오류 문구 + 다시 시도 |
| 캐시 적중(`delta` 1번에 전체) | 한 번에 나타나고 ✓ |
| 첫 질문 전송 중 세션 생성 실패 | notice, 입력 되돌림 |
| 스트림 중 다른 세션 클릭 | 현재 스트림 끊김(서버도 취소·미저장) |
| 스트림 중 같은 세션에서 또 전송 | 버튼 비활성 |
| 50턴 다 찬 세션에서 질문 | 409 → 안내 + 새 대화 버튼 |
| 하루 한도 초과 | 429 → 서버 문구(버튼은 16) |
| 세션 목록 비었음 | "아직 대화가 없어요." |
| 목록에 없는 빈 세션 주소로 직접 접근 | 09는 `GET /{id}`로 보여 줌 → 빈 대화 화면 |
| 사용자 질문에 마크다운·HTML | 사용자 말풍선은 텍스트 그대로(렌더 안 함) |

---

## 10. 가정 판정

| ID | 확인 방법 | 통과 기준 | 실패 시 |
|---|---|---|---|
| **A11**(모바일 화면 확인 마무리) | HITL-1: 휴대폰(터널 주소, PWA 포함)에서 긴 답변 질문 | 글이 **조각조각 늘어나며** 보임(한 번에 다 나오지 않음), `done`까지 도착, 15초 넘게 걸리는 질문(검증 다시 쓰기)에서도 끊기지 않음 | 02 대안(ping 간격 축소) 확인 후 **멈추고 사용자에게** |
| **A30**(화면 일관성) | HITL-2 + Vitest V-CS-04(`tool` 지움) | 툴을 부르는 질문에서 머리말이 잠깐 보였다가 사라지고 툴 라벨 → 본문 순서로 자연스러움 | 02 대안(프롬프트로 머리말 금지)을 사용자에게 제안 |

결과는 이 절과 `PROGRESS.md` 결정 로그에 기록.

---

## 11. 앞 작업과 달라지는 점 · 앞 작업 테스트 수정

| # | 내용 | 대상 | 처리 |
|---|---|---|---|
| 1 | 14 임시 `(chat)/page.tsx` 교체 | 14 Playwright P-AU-04("임시 채팅 화면") | 기대를 "채팅 입력창 보임"으로 |
| 2 | `(chat)/layout.tsx`에 사이드바 | 14 V-AG-01 | 수정 없음(AuthGate 동작 불변) |
| 3 | 백엔드 변경 없음 | — | — |

상위 문서와의 차이(구현 판단):
1. `error` 때 이미 보인 초안을 숨김(15-Q2) — [A]는 "초안이 보였어도 검증 못 하면 저장 안 함"만 적음.
2. 이력의 사실 검증 실패 답변은 짧은 배지만(15-Q3).
3. 첫 질문 때 세션 생성(빈 세션 안 만듦).

---

## 12. 완료 기준 (DoD)

1. `npm run typecheck && npm run test` 통과(test.md ①-A: 파서·렌더러·상태 전이).
2. Playwright 가짜 SSE 시나리오(①-B) 통과, 실제 compose 1회(P-CH-R1) 통과.
3. HITL-1(모바일 토큰 단위 표시, A11)·HITL-2(A30) 결과 기록.
4. 렌더러: raw HTML·이미지 요소 0, 허용 밖 링크는 글, 초안 단계 링크 클릭 불가(테스트).
5. 사이드바: 목록·제목·새 대화·삭제(확인창) 동작.
6. 모든 함수·컴포넌트에 한국어 JSDoc, 함수 안 단계 주석([CL]).
7. 커밋 `feat/15-web-chat`, `[Feat] …` + 작업 목록 + `Author:`, AI 공동작성 표기 없음. `dev` 병합은 G5 후. `PROGRESS.md` 갱신.

---

## 13. 확인 질문

| # | 질문 | 추천안 | 대안 |
|---|---|---|---|
| 15-Q1 | FAQ 캐시 답변(`done.cached`)을 화면에 따로 표시할까(12가 15에 넘김) | **표시 안 함** — 평소처럼 `✓ 확인됨`만(캐시도 검증 통과본) | "저장된 답변" 작은 표시 |
| 15-Q2 | `error`로 끝나면 이미 보인 초안을 어떻게 할까 | **숨기고 오류 문구 + 다시 시도**(검증 못 한 글은 남기지 않음 — 새로고침해도 없는 글과 일치, D-24 보안 우선) | 초안을 흐리게 남기고 "확인 못 함" 표시 |
| 15-Q3 | 이력에서 사실 검증 실패(`failed`) 답변 표시 — 서버 경고 문구는 이력에 저장돼 있지 않다 | **배지 `⚠ 확인 못 함`만**(화면 고정 글, 문장 경고는 실시간에만) | 09 `MessageOut`에 경고 문구 필드 추가(백엔드 수정) / 웹에 서버 문구를 복사 |
| 15-Q4 | "새 대화"를 누를 때 세션을 바로 만들까 | **첫 질문을 보낼 때 만든다**(빈 세션 안 쌓임, 주소는 `history.replaceState`로 바꿈) | 누르는 즉시 `POST /api/chat/sessions` 후 이동(빈 세션은 09가 목록에서 숨김) |
| 15-Q5 | 삭제 확인 창 | **브라우저 기본 `confirm`**(코드 최소) | shadcn 대화상자(컴포넌트 추가) |
| 15-Q6 | SSE 시작 전 오류(429·409 등)일 때 보낸 질문 처리 | **말풍선을 지우고 입력창에 되돌림 + 입력창 위 알림** | 말풍선을 남기고 그 아래 오류 표시 |
