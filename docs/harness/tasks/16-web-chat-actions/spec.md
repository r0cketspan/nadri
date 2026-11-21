# 16-web-chat-actions — 피드백·위치 동의 UI (spec)

> 하네스 Phase 4 산출물 (spec-writer, 작성 2026-11-21). 상태: **확정(2026-11-22)** — 확인 질문은 모두 추천안대로 결정(마지막 절 표). 브랜치 `feat/16-web-chat-actions`, 의존 작업 13-feedback, 15-web-chat.
> 근거: [PL]=program_list.md(G4 승인본) §2 표·§3 "16-web-chat-actions" · [A]=architecture.md(G3 재승인본) §2.1 web(👍/👎·위치 동의)·§3.9·§6.1 · [R]=requirements.md FR-55·103, NFR-33.
> **이어받는 확정 spec**: [09](`ChatRequest.location{lat,lng}` 범위 −90~90·−180~180, 좌표는 질문 처리에만·저장 안 함) · [12](위치가 있으면 FAQ 캐시 안 씀) · [13](`PUT`·`DELETE /api/chat/messages/{id}/feedback`·`FeedbackIn`·`FeedbackOut`·`MessageOut.feedback`·사유 코드 4개·404 `message_not_found`) · [14](`apiJson`·`ApiError`) · [15](`ChatView` 전송 순서·`notice`·`MessageBubble.actions` 자리·`streamChat(…, body{text, location?})`·`AssistantMessage`·`fromHistory`).
> **미확인** = 문서·공식 자료로 확인하지 못한 사실.
> **2026-11-22 변경(사용자 요청)**: 한도 추가 요청 기능 삭제(FR-62 변경·FR-82 삭제)로 `QuotaRequestButton`·`requestMoreQuota`와 16-Q5를 뺐다. 하루 한도 초과 화면은 15의 SSE 전 오류 처리(입력창 되돌림 + 서버 문구 알림)로 충분하다 — 15 §7.1·P-CH-12.

---

## 1. 작업 목표

15 채팅 화면에 두 가지를 붙인다 [PL §3].
1. **👍/👎**(FR-103): 저장된 답변마다 버튼 2개, 👎를 누르면 사유 4개(틀린 정보·오래된 정보·질문 이해 못함·기타)를 **선택 입력**으로 보여 준다. 다시 누르면 취소.
2. **위치 동의**(FR-55, NFR-33): 입력창 옆 토글. 켠 상태에서만 질문을 보낼 때 `navigator.geolocation`으로 그 순간 좌표를 받아 **그 요청 본문에만** 넣는다. 브라우저에 저장하지 않는다. 거부·실패면 좌표 없이 보낸다(지명 기준으로 답함).

### 1.1 넣지 않는 것
| 빠지는 것 | 이유 |
|---|---|
| 👎 사유 자유 입력 | FR-103은 선택지만 |
| 한도 초과 화면·"추가 요청" 버튼 | 한도 초과 안내는 15가 함, 추가 요청 기능은 삭제(2026-11-22) |
| 오늘 한도 상태 조회 API·남은 횟수 표시 | 11에 조회 API 없음, 요구사항 없음 |
| 위치 동의 설정 기억(새로고침 후 유지) | NFR-33 취지 — 매번 켬(16-Q2) |
| 좌표를 지도에 표시 | 요구사항 없음 |
| 피드백 대상: 차단·오류·저장 안 된 답변 | 메시지 id가 없음(저장 안 됨 — ADR-27·ADR-03) |

---

## 2. 생성·수정 파일

| 파일 | 신규/수정 | 역할 |
|---|---|---|
| `web/components/chat/FeedbackButtons.tsx` | 신규 | 👍/👎·사유 선택·취소, 낙관적 갱신 (§4) |
| `web/components/chat/LocationToggle.tsx` | 신규 | 위치 동의 토글 + `getCurrentLocation()` (§5) |
| `web/lib/chat-api.ts` | 수정(15) | `putFeedback`·`deleteFeedback` 함수 (§3) |
| `web/lib/chat-state.ts` | 수정(15) | `AssistantMessage.feedback` 필드, `fromHistory`가 13 `feedback` 채움 |
| `web/components/chat/ChatView.tsx` | 수정(15) | 위치 토글 상태·전송 시 좌표 첨부, 답변 `actions`에 `FeedbackButtons` (§6) |
| `web/tests/unit/*`, `web/e2e/chat-actions.spec.ts` | 신규 | test.md |

> [PL] 파일 목록 밖: `chat-api.ts`·`chat-state.ts`·`ChatView.tsx` 수정 — 두 컴포넌트를 15 화면에 끼우는 자리. 백엔드 변경 없음.

---

## 3. API 함수 (`web/lib/chat-api.ts`에 추가)

```ts
export type FeedbackReason = "wrong" | "outdated" | "misunderstood" | "other";
export type Feedback = { rating: "up" | "down"; reason: FeedbackReason | null };

/** PUT /api/chat/messages/{id}/feedback — 저장된 피드백을 돌려준다(13 FeedbackOut). */
export function putFeedback(messageId: number, fb: Feedback): Promise<Feedback>;
/** DELETE 같은 경로(204). */
export function deleteFeedback(messageId: number): Promise<void>;
```
- `putFeedback`은 `rating == "up"`이면 `reason`을 보내지 않는다(13: up + reason은 422).

사유 문구(화면 고정, FR-103):
```ts
export const REASON_LABELS: Record<FeedbackReason, string> = {
  wrong: "틀린 정보", outdated: "오래된 정보", misunderstood: "질문 이해 못함", other: "기타",
};
```

---

## 4. `FeedbackButtons`

```tsx
/**
 * 저장된 답변 1개의 👍/👎 버튼. 👎를 누르면 사유 선택(선택 입력)이 펼쳐진다.
 * @param messageId - assistant 메시지 id(done.assistant_message_id 또는 이력 id)
 * @param initial - 이력의 feedback(없으면 null)
 */
export function FeedbackButtons(props: { messageId: number; initial: Feedback | null }): JSX.Element;
```
상태: `current: Feedback | null`, `pending: boolean`(요청 중), `error: string | null`, `showReasons: boolean`.

동작(요청 중엔 모든 버튼 비활성 — 순서 꼬임 방지):
| 현재 | 누른 것 | 요청 | 결과 상태 |
|---|---|---|---|
| 없음 / down | 👍 | `PUT {rating:"up"}` | up, 사유 숨김 |
| up | 👍 | `DELETE` | 없음 |
| 없음 / up | 👎 | `PUT {rating:"down"}` | down(사유 null), **사유 칩 펼침** |
| down | 👎 | `DELETE` | 없음, 사유 숨김 |
| down | 사유 칩 X(선택 안 된 것) | `PUT {rating:"down", reason:X}` | down+X |
| down+X | 같은 칩 X | `PUT {rating:"down", reason:null}` | down(사유 없음) |

- **낙관적 갱신**: 누르는 즉시 화면을 바꾸고, 실패하면 이전 상태로 되돌린 뒤 버튼 아래 작은 글로 `ApiError.message`(예: 404 "답변을 찾을 수 없어요…", 네트워크 문구). 3초 뒤 오류 글 사라짐.
- 접근성: 버튼 `aria-pressed`, 라벨 "도움이 됐어요"/"도움이 안 됐어요". 사유 칩은 `role="radiogroup"`.
- 👎만 하고 사유를 안 골라도 된다(선택 입력). 칩은 그 답변에 👎가 있는 동안 계속 보인다.

---

## 5. `LocationToggle`

```tsx
/** 입력창 옆 "내 위치 사용" 토글. 켜는 순간 권한을 묻고, 거부되면 다시 꺼진다. */
export function LocationToggle(props: { enabled: boolean; onChange: (enabled: boolean) => void;
                                        geo?: Geolocation }): JSX.Element | null;

/**
 * 지금 위치를 한 번 받는다. 좌표는 돌려주기만 하고 어디에도 저장·기록하지 않는다(NFR-33).
 * @param geo - 테스트용 주입(기본 navigator.geolocation)
 * @returns {lat, lng} 또는 실패 사유
 */
export function getCurrentLocation(geo?: Geolocation):
  Promise<{ ok: true; lat: number; lng: number } | { ok: false; reason: "unsupported" | "denied" | "unavailable" | "timeout" }>;
```
- `getCurrentLocation`: `geo`가 없으면 `unsupported`. `getCurrentPosition(…, { enableHighAccuracy: false, timeout: 10000, maximumAge: 60000 })`. 오류 코드 1 → `denied`, 2 → `unavailable`, 3 → `timeout`. 좌표는 받은 값 그대로(반올림 없음 — 서버가 질문 처리에만 쓰고 저장 직전 지움, 09 §6.4).
- `LocationToggle`:
  - `navigator.geolocation`이 없으면 렌더하지 않음(null).
  - 끔 → 켬: `getCurrentLocation()`을 1번 불러 권한 창을 띄운다. `ok`면 `onChange(true)`(좌표는 버림 — 전송 때 새로 받음). 실패면 `onChange(false)` + 토글 아래 글: `denied` → "위치 권한이 꺼져 있어요. 브라우저 설정에서 허용해 주세요." / 그 밖 → "위치를 가져오지 못했어요."
  - 켬 → 끔: `onChange(false)`.
  - 라벨 "내 위치 사용"(켜짐 상태 `aria-checked`). 켜져 있을 때 작은 설명 "질문할 때만 현재 위치를 보내고 저장하지 않아요."
- 상태 `enabled`는 `ChatView`의 React 상태에만(새로고침하면 꺼짐). localStorage 등에 저장하지 않는다.

---

## 6. `ChatView` 수정 (15 §7.1 전송 순서에 끼움)

1. (15-1) 뒤에 **1a)**: `location = undefined`; `locationEnabled`면 `r = await getCurrentLocation()`:
   - `ok` → `location = {lat: r.lat, lng: r.lng}`
   - 실패 → 토글 끄기 + `notice` "위치를 가져오지 못해 위치 없이 보냈어요. 지명으로 물어봐 주세요." (전송은 계속 — FR-55 "거부·미동의면 지명 기준")
2. (15-4) `streamChat(id, location ? { text, location } : { text }, signal)` — 좌표 변수는 이 함수 지역 변수로만, 상태·로그(`console.*`)에 넣지 않는다. 재시도(`retryText`)는 **다시 위치를 받는다**(좌표를 들고 있지 않으므로).
3. 답변 `MessageBubble`의 `actions` = `<FeedbackButtons messageId={m.id} initial={m.feedback} />` — `phase == "done"`이고 `id != null`일 때(15 §7.2 규칙 그대로 — 차단·오류·id null이면 안 나옴). 실시간 답변은 `initial = null`.
4. 입력창 옆에 `<LocationToggle enabled={locationEnabled} onChange={setLocationEnabled} />`.

`chat-state.ts`: `AssistantMessage`에 `feedback: Feedback | null` 추가, `fromHistory`는 `m.feedback ?? null`, `startTurn`은 null.

---

## 7. 엣지케이스

| 상황 | 동작 |
|---|---|
| 👍 빠르게 두 번 | 첫 요청 끝날 때까지 비활성 → 요청 1번 |
| 👎 실패(네트워크) | 원래 상태로 되돌림 + 오류 글 |
| 남의/삭제된 메시지(404) | 되돌림 + "답변을 찾을 수 없어요…" |
| 새로고침 | 이력의 `feedback`으로 버튼 상태 복원, 👎면 사유 칩 펼침 |
| 차단·오류 답변 | 버튼 없음 |
| `security_replaced`·`failed` 답변 | 버튼 있음(평가 재료) |
| 하루 한도 초과(429) | 15 그대로 — 입력창 되돌림 + 서버 문구, 버튼 없음 |
| 위치 지원 안 하는 브라우저 | 토글 안 보임 |
| http 주소(보안 출처 아님) | 브라우저가 `geolocation`을 막음 → `denied`/`unsupported` 처리(터널 https·localhost는 정상) |
| 토글 켬 → 권한 거부 | 토글 꺼짐 + 안내 |
| 켠 채로 전송 시 10초 안에 위치 못 받음 | 위치 없이 전송 + 안내, 토글 꺼짐 |
| 켠 채로 전송, 좌표 받음 | 요청 본문에 `location`, 화면·저장소·콘솔 어디에도 좌표 없음 |
| 위치 켠 첫 질문 | 서버가 FAQ 캐시 안 씀(12) — 화면은 차이 없음 |
| 다시 시도 | 위치를 다시 받음 |

---

## 8. 앞 작업과 달라지는 점 · 앞 작업 테스트 수정

| # | 내용 | 대상 | 처리 |
|---|---|---|---|
| 1 | `AssistantMessage.feedback` 추가 | 15 V-CS(객체 전체 비교가 있으면) | 기대에 `feedback: null` 추가 |
| 2 | 답변 아래 👍/👎 | 15 V-MB-06·P-CH-04 | actions가 FeedbackButtons로 채워짐 — 차단 답변에 없음 기대는 그대로 |
| 3 | 백엔드 변경 없음 | — | — |

---

## 9. 완료 기준 (DoD)

1. `npm run typecheck && npm run test` 통과(컴포넌트 상태 — test.md ①-A).
2. Playwright(①-B): 피드백 변경·취소(요청 방법·본문 확인), 위치 거부 시 **요청 본문에 `location` 없음**, 허용 시 있음.
3. 좌표가 `localStorage`·`sessionStorage`·쿠키·`console` 출력에 없음(테스트).
4. HITL-1·2 결과 보고.
5. 한국어 JSDoc·단계 주석([CL]). 커밋 `feat/16-web-chat-actions`, `[Feat] …` + 작업 목록 + `Author:`, AI 공동작성 표기 없음. `dev` 병합은 G5 후. `PROGRESS.md` 갱신.

---

## 10. 확인 질문

| # | 질문 | 추천안 | 대안 |
|---|---|---|---|
| 16-Q1 | 👎를 누르면 바로 저장할까, 사유를 고른 뒤 저장할까 | **결정(2026-11-22): 추천안대로** — **바로 저장(사유 null) 후 사유 칩을 보여 줌**(사유는 선택 입력 — FR-103, 칩을 안 눌러도 👎는 남음) | 사유 창을 먼저 띄우고 "보내기"로 저장 |
| 16-Q2 | 위치 동의 토글 상태를 새로고침 뒤에도 기억할까 | **결정(2026-11-22): 추천안대로** — **기억 안 함**(매번 꺼진 상태로 시작 — 좌표·동의 흔적을 브라우저에 남기지 않음, NFR-33 취지) | localStorage에 켬/끔만 저장 |
| 16-Q3 | 위치 토글을 켤 때 권한을 바로 물을까 | **결정(2026-11-22): 추천안대로** — **켜는 순간 1번 물음**(거부하면 바로 꺼져 사용자가 알 수 있음), 좌표는 전송 때 새로 받음 | 전송할 때 처음 물음 |
| 16-Q4 | 좌표 정밀도 | **결정(2026-11-22): 추천안대로** — **브라우저 값 그대로**(`enableHighAccuracy: false` — 대략 위치), 반올림 없음(서버가 저장 전 지움) | 소수 3자리(약 100m)로 반올림해 보냄 |
| ~~16-Q5~~ | ~~추가 요청 뒤 승인됐는지 자동으로 확인할까~~ | **질문 없어짐(2026-11-22)** — 한도 추가 요청 기능 삭제 | — |
