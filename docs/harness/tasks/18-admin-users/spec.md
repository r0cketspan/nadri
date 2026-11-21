# 18-admin-users — 관리자: 가입 승인·비활성화 (spec)

> 하네스 Phase 4 산출물 (spec-writer, 작성 2026-11-22). 상태: **초안 — 확인 질문 대기**(마지막 절 표). 브랜치 `feat/18-admin-users`, 의존 작업 11-quota-usage, 14-web-foundation([PL] 표 그대로 — 실제 코드 의존은 05·14뿐, §12 Q1).
> 근거: [PL]=program_list.md(G4 승인본, 2026-11-22 개정) §2 표·§3 "18-admin-users"·§4.1 · [A]=architecture.md(G3 재승인본) §2.1 web(`/admin`)·`admin` 모듈·§3.4·§6.1(관리자 API 4개, "관리자 API는 role=admin 서버 검사")·§13(승인 결과 메일·재활성화 버튼 없음)·ADR-12 · [R]=requirements.md FR-04·80·81·84(FR-82는 2026-11-22 삭제, id만 유지), NFR-03·04·05·10·34·61·71 · [E]=erd.md(`users` 한글 명칭 정본) · [PG]=PROGRESS.md 결정 로그 2026-11-22("한도 추가 요청 기능 삭제", 18 id 변경, 관리자는 일일 한도 없음).
> **이어받는 확정 spec**: [04](`User`·`USER_ROLES`·`USER_STATUSES`·`ck_users_status`·`fk_users_approved_by` SET NULL·`ix_auth_sessions_user_id`·`db_sf` 픽스처) · [05](`require_admin`·`current_user`(rejected·disabled면 세션 삭제 후 401)·`CurrentUser`·`get_db`·`get_now`·`revoke_all_sessions`·`ApiError`·`errors.py`·`MSG_FORBIDDEN`·CSRF 미들웨어·`create-admin` CLI·테스트 헬퍼 `make_user`·`login`·`post`·`clock`) · [11](관리자 한도 제외 — 18은 손대지 않음) · [14](`apiFetch`·`apiJson`·`ApiError`·`AuthGate`·`useMe`·`Me`·`(chat)/account/page.tsx`·nginx `location /`가 `/admin`도 web으로·Playwright `e2e/helpers/db.ts`·`global-setup.ts`(`e2e_` 사용자 정리)) · [15](`lib/chat-api.ts` 이름 규칙 — 18은 `lib/admin-api.ts`).
> **19-admin-usage·25-admin-quality-hitl과의 약속**: `nadri/api/admin/router.py`(관리자 라우터 + `require_admin` 일괄 적용)와 `web/app/admin/layout.tsx`(+ `AdminShell`의 메뉴 목록)는 **18이 만들고 19·25가 넓힌다**(§9).
> **미확인** = 문서·공식 자료로 확인하지 못한 사실.

---

## 1. 작업 목표

관리자(`role=admin`)만 쓰는 API와 백오피스 화면을 만들어, 가입 신청을 **승인·거절**하고 사용자를 **비활성화**(세션 폐기 → 즉시 로그아웃·채팅 차단)한다 [A] §3.4, [R] FR-04·80·81·84.

- `GET /api/admin/users?status=` — 사용자 목록(상태별).
- `POST /api/admin/users/{id}/approve` · `/reject` · `/disable` — 상태 전이(§5). 비활성화는 그 사용자의 `auth_sessions`를 모두 지운다.
- 모든 `/api/admin/*`는 서버에서 `require_admin`(05)으로 검사한다(FR-80). 화면은 보조 — 권한 판단은 api(ADR-12).
- `/admin` 화면: 관리자 공통 틀(`layout.tsx` — 로그인·관리자 확인, 메뉴) + `/admin/users`(목록·버튼).
- 끝나면: 가입 신청 → 관리자가 `/admin/users`에서 승인 → 그 사용자가 로그인해 채팅을 쓴다. 비활성화하면 그 사용자는 다음 요청부터 401(로그인 화면), 다시 로그인해도 "아이디 또는 비밀번호가 맞지 않아요."

### 1.1 넣지 않는 것
| 빠지는 것 | 들어오는 작업 / 이유 |
|---|---|
| 한도 추가 요청 목록·승인(FR-82) | **삭제(2026-11-22)** — 기능 자체가 없음. 관리자 한도 제외는 11이 이미 처리 |
| 사용량 대시보드·월 $10 경고 | 19 (18의 라우터·레이아웃에 메뉴 1개 추가) |
| 품질 리포트·개선안 결정 | 25 |
| 승인·거절 결과 메일, 관리자 실시간 알림 | 범위 밖([A] §13) |
| 비활성 사용자 **다시 켜기**(재활성화) 버튼 | 범위 밖([A] §13) — 필요하면 DB 명령(§8 끝) |
| 관리자 승격·강등, 사용자 삭제, 이메일·아이디 수정 | 요구사항 없음 |
| 목록 페이지 나누기·검색 | 사용자 1~5명(NFR-61) — 넣지 않음(§12 Q5) |
| 거절·비활성화 시각·처리자 DB 저장 | ERD에 컬럼 없음 — 로그 1줄로 대신(§12 Q7) |
| 관리자 API 요청 제한(분당) | 넣지 않음 — 관리자만, 외부 호출·비용 없음 |

---

## 2. 생성·수정 파일

경로의 `nadri/`는 `backend/src/nadri/`.

| 파일 | 신규/수정 | 역할 |
|---|---|---|
| `nadri/api/admin/__init__.py` | 신규 | 빈 파일 |
| `nadri/api/admin/router.py` | 신규 | `admin_router`(접두어 `/api/admin`, 라우터 전체에 `Depends(require_admin)`), 하위 라우터 모으기 (§4.1, §9) |
| `nadri/api/admin/users.py` | 신규 | 응답 모델, `list_users`·`apply_action` 서비스, 목록·동작 엔드포인트 (§4·§5) |
| `nadri/api/errors.py` | 수정(05) | `user_not_found`·`user_status_conflict`·`admin_target` 코드·문구 (§4.4) |
| `nadri/api/main.py` | 수정 | `admin_router` 등록 |
| `web/app/admin/layout.tsx` | 신규 | 서버 컴포넌트, `<AuthGate><AdminShell>{children}</AdminShell></AuthGate>` (§6.1) |
| `web/components/admin/AdminShell.tsx` | 신규 | 관리자 확인·상단 메뉴(`ADMIN_NAV`) (§6.1) |
| `web/app/admin/page.tsx` | 신규 | `/admin` → `/admin/users`로 보냄 (§6.2) |
| `web/app/admin/users/page.tsx` | 신규 | 가입 신청·사용자 목록 화면 (§6.3) |
| `web/lib/admin-api.ts` | 신규 | 관리자 API 함수·타입, `formatKst` (§6.4) |
| `web/app/(chat)/account/page.tsx` | 수정(14) | 관리자에게만 "관리자 화면" 링크 (§6.5, §12 Q4) |
| `web/e2e/helpers/db.ts` | 수정(14) | `makeAdmin(username, password)` 헬퍼 (test.md) |
| `backend/tests/...`, `web/tests/unit/...`, `web/e2e/admin.spec.ts` | 신규·수정 | test.md, 앞 작업 테스트 수정(§10) |

> [PL] 파일 목록 밖: `admin/__init__.py`, `errors.py`·`main.py` 수정, `AdminShell.tsx`(Next.js는 `layout.tsx`에서 기본 내보내기 외의 값(메뉴 목록 등)을 내보내면 빌드 타입 검사에서 막는 것으로 알려짐 — **미확인**. 메뉴 목록을 19·25가 고칠 수 있게 별도 파일로 뺌), `admin/page.tsx`(`/admin` 주소가 404가 되지 않게), `admin-api.ts`(15 `chat-api.ts`와 같은 방식), `account/page.tsx` 링크, e2e 헬퍼.

---

## 3. 설정 · 상수

새 환경변수 없음. compose·nginx 변경 없음(`/admin`은 14 nginx `location /`가 이미 web으로 보냄).

| 상수 | 위치 | 값 |
|---|---|---|
| `ADMIN_ACTIONS` | `api/admin/users.py` | `{"approve": ("pending", "active"), "reject": ("pending", "rejected"), "disable": ("active", "disabled")}` — 동작 → (허용하는 현재 상태, 바뀔 상태) |
| `USER_ROLES`·`USER_STATUSES` | `core/models/account.py`(04) | 재사용 |
| `ADMIN_NAV` | `web/components/admin/AdminShell.tsx` | `[{ href: "/admin/users", label: "사용자" }]` — 19·25가 항목 추가 |
| `STATUS_LABEL` | `web/lib/admin-api.ts` | `pending` 승인 대기 · `active` 활성 · `rejected` 거절됨 · `disabled` 비활성 (ERD `users.status` "가입 상태" 값) |

---

## 4. API

모두 05 오류 본문 `{"code","message"}`. `POST`는 05 CSRF 미들웨어 적용.

### 4.1 관리자 라우터 (`api/admin/router.py`)
```python
admin_router = APIRouter(prefix="/api/admin", dependencies=[Depends(require_admin)])
"""관리자 API 묶음. 이 라우터에 붙인 모든 경로는 require_admin(05)을 먼저 통과해야 한다(FR-80).
하위 라우터(users — 18, usage — 19, quality — 25)는 접두어 없이 경로를 적고 여기서 include한다."""
admin_router.include_router(users.router)
```
- `main.py`: `app.include_router(admin_router)`.
- 권한 검사 순서: CSRF(미들웨어, POST만) → 라우터 의존성 `require_admin`(미로그인 401 `unauthenticated` / 관리자 아님·관리자인데 active 아님 403 `forbidden`) → 경로·쿼리 형식 검사(422) → 처리. **관리자가 아니면 형식이 틀려도 403**이다(FastAPI는 의존성 예외를 경로 값 검사 오류보다 먼저 던지는 것으로 알려짐 — **미확인**, test A-ADR-04로 확인. 다르면 그대로 두고 결과만 기록 — 어느 쪽이든 관리자 아닌 사람에게 데이터는 나가지 않음).
- 엔드포인트가 관리자 정보(`approved_by`)를 쓰려면 같은 함수로 `cu: CurrentUser = Depends(require_admin)`을 다시 선언한다 — FastAPI가 한 요청 안에서 같은 의존성 결과를 재사용하므로 검사는 1번만 돈다.

### 4.2 엔드포인트 (`api/admin/users.py`, `router = APIRouter()`)
| 메서드·경로 | 요청 | 성공 | 실패 |
|---|---|---|---|
| `GET /api/admin/users` | 쿼리 `status?: pending\|active\|rejected\|disabled` (없으면 전체) | 200 `AdminUserListOut` | 401·403(§4.1) / 422(허용 밖 status) |
| `POST /api/admin/users/{user_id}/{action}` (`action` ∈ `approve`·`reject`·`disable`) | 본문 없음 | 200 `AdminUserOut`(바뀐 뒤 값) | 401·403 / 403 `csrf_failed` / 404 `user_not_found` / 409 `admin_target`·`user_status_conflict` / 422(경로 형식·허용 밖 action) |

```python
class AdminUserOut(BaseModel):
    """관리자 화면에 보여 줄 사용자 1명. 비밀번호 해시는 넣지 않는다."""
    id: int
    username: str
    email: str
    role: Literal["user", "admin"]
    status: Literal["pending", "active", "rejected", "disabled"]
    created_at: datetime            # 가입 신청 일시 (UTC, ISO 8601 +00:00)
    approved_at: datetime | None    # 승인 일시

class AdminUserListOut(BaseModel):
    """사용자 목록 응답(09 {"sessions": [...]}와 같은 모양)."""
    users: list[AdminUserOut]
```
- 경로 `user_id: int = Path(ge=1, le=2**63 - 1)`(bigint 넘침 500 방지 — 13과 같은 방식), `action: Literal["approve", "reject", "disable"]`.
- [A] §6.1의 `POST …/approve`·`/reject`·`/disable` 3개 경로를 `{action}` 경로 1개로 받는다(바깥에서 보이는 주소는 같음). 허용 밖 action(`/users/1/delete`)은 404가 아니라 422.
- `approved_by`는 응답에 넣지 않는다(관리자 1명 — 화면에서 쓸 곳 없음).

### 4.3 처리 순서

**목록** (FR-81)
1. `SELECT id, username, email, role, status, created_at, approved_at FROM users [WHERE status = :status] ORDER BY created_at DESC, id DESC`.
2. 200 `{"users": [...]}`. 관리자 계정도 목록에 나온다(`role` 표시, 버튼 없음 — §6.3).

**동작** `apply_action` (FR-04·81·84, [A] §3.4)
1. `SELECT … FROM users WHERE id = :uid FOR UPDATE` → 없으면 404 `user_not_found`.
2. `role == "admin"`이면 409 `admin_target`(자기 자신 포함 — 관리자 계정은 이 화면에서 바꾸지 않는다, §12 Q3).
3. `(from_status, to_status) = ADMIN_ACTIONS[action]`. 현재 `status != from_status`면 409 `user_status_conflict`(본문에 `"status": 현재 상태`).
4. `UPDATE users SET status = :to` — `approve`면 `approved_at = now`(05 `get_now`), `approved_by = cu.user.id`도 함께.
5. `disable`이면 `revoked = await revoke_all_sessions(db, uid)`(05) — 그 사용자의 모든 세션 삭제. 그 밖은 `revoked = 0`.
6. 커밋 → 200 `AdminUserOut`.
7. 로그 1줄(INFO): 이벤트 이름 `admin_user_action`, `admin_id`, `user_id`, `action`, `from`, `to`, `sessions_revoked`. **아이디·이메일은 넣지 않는다**(NFR-34 취지 — id로 충분).

- 1의 행 잠금(`FOR UPDATE`) 때문에 같은 사용자에 대한 동시 요청 2건(관리자 둘, 또는 버튼 두 번)은 하나만 성공하고 다른 하나는 3에서 409.
- **거절은 세션을 따로 지우지 않는다**: pending 사용자는 로그인 상태일 수 있지만, 05 `current_user`가 다음 요청에서 `rejected`를 보고 그 세션을 지우고 401을 준다 — 결과가 같으므로 코드를 늘리지 않는다. 비활성화만 [A] §3.4대로 즉시 폐기한다(FR-84 "세션 폐기").

```python
async def list_users(db: AsyncSession, status: str | None) -> list[User]:
    """status가 있으면 그 상태만, 없으면 전체를 가입 신청 최신순으로 돌려준다."""

async def apply_action(db: AsyncSession, *, admin_id: int, user_id: int,
                       action: Literal["approve", "reject", "disable"], now: datetime) -> tuple[User, int]:
    """§4.3 동작 1~6을 처리하고 (바뀐 사용자, 지운 세션 수)를 돌려준다. 커밋까지 한다.
    Raises: ApiError(404 user_not_found / 409 admin_target / 409 user_status_conflict)."""

def next_status(action: str, current: str) -> str | None:
    """ADMIN_ACTIONS 표로 다음 상태를 돌려준다. 허용되지 않는 전이면 None(순수 함수 — 표 테스트 대상)."""
```

### 4.4 사용자에게 보이는 문구 (`errors.py`에 추가)
| code | HTTP | 상수 | 문구 |
|---|---|---|---|
| `user_not_found` | 404 | `MSG_USER_NOT_FOUND` | 사용자를 찾을 수 없어요. |
| `user_status_conflict` | 409 | `MSG_USER_STATUS_CONFLICT` | 이미 처리된 사용자예요. 목록을 새로고침했어요. |
| `admin_target` | 409 | `MSG_ADMIN_TARGET` | 관리자 계정은 이 화면에서 바꿀 수 없어요. |
| (05) `forbidden` | 403 | `MSG_FORBIDDEN` | 접근 권한이 없어요. |

- `user_status_conflict` 본문: `{"code","message","status"}`. 화면은 이 문구를 보여 주고 목록을 다시 불러온다(그래서 문구가 "새로고침했어요").
- 성공 문구는 화면 고정 문구(§6.3) — API는 바뀐 사용자만 돌려준다.

---

## 5. 상태 전이 (정본 표)

| 현재 상태 \ 동작 | approve | reject | disable |
|---|---|---|---|
| `pending` | → `active` (승인 일시·승인 관리자 기록) | → `rejected` | 409 |
| `active` | 409 | 409 | → `disabled` + 세션 전부 삭제 |
| `rejected` | 409 (다시 승인 없음 — §12 Q2) | 409 | 409 |
| `disabled` | 409 (재활성화 없음 — [A] §13) | 409 | 409 |
| 대상이 `role=admin` | 409 `admin_target` | 409 `admin_target` | 409 `admin_target` |

상태별 결과(05 동작 그대로):
| 상태 | 로그인 | 채팅 |
|---|---|---|
| `pending` | 됨 → "승인 대기" 화면 | 403 `pending_approval` |
| `active` | 됨 | 됨 |
| `rejected` / `disabled` | 401 `login_failed`(없는 아이디와 같은 문구 — NFR-03) | 기존 세션도 다음 요청에서 401 |

---

## 6. 화면

공통: 14 규칙(모바일 우선, `<label>` 연결, 처리 중 버튼 비활성, 오류는 `role="alert"` 영역에 `ApiError.message` 그대로). 데이터는 브라우저에서만 `/api/admin/*` 호출(ADR-12). 서버 컴포넌트에서 쿠키를 읽어 판단하지 않는다.

### 6.1 관리자 공통 틀 (`app/admin/layout.tsx`, `components/admin/AdminShell.tsx`)
```tsx
// app/admin/layout.tsx — 서버 컴포넌트(데이터 호출 없음)
/** /admin 아래 화면을 로그인 확인(AuthGate)과 관리자 확인(AdminShell)으로 감싼다. */
export default function AdminLayout({ children }: { children: React.ReactNode }) {
  return <AuthGate><AdminShell>{children}</AdminShell></AuthGate>;
}
```
```tsx
// components/admin/AdminShell.tsx — "use client"
/** 관리자 화면 메뉴 항목. 19(사용량)·25(품질)가 항목을 덧붙인다. */
export const ADMIN_NAV: ReadonlyArray<{ href: string; label: string }>;
/**
 * 관리자만 children을 보여 주고, 위에 메뉴를 그린다.
 * @param children - /admin 아래 각 화면
 * @returns 관리자면 메뉴+children, 아니면 권한 없음 안내(children은 그리지 않음 → 관리자 API 호출도 없음)
 */
export function AdminShell({ children }: { children: React.ReactNode }): JSX.Element;
```
- 흐름: `AuthGate`(14)가 미로그인 → `/login`, pending → `/pending`을 이미 처리한다. `AdminShell`은 `useMe().role`만 본다.
  - `role !== "admin"` → "접근 권한이 없어요."(05 `MSG_FORBIDDEN`과 같은 문구) + "채팅으로" 링크(`/`). 자동 이동은 하지 않는다.
  - `role === "admin"` → 상단: 제목 "nadri 관리자", `ADMIN_NAV` 링크들(현재 경로는 `aria-current="page"`, `usePathname`), 오른쪽 "채팅으로"(`/`). 그 아래 `children`.
- 화면 숨김은 편의일 뿐이다. 일반 사용자가 주소를 직접 불러도 api가 403을 준다(FR-80).

### 6.2 `/admin` (`app/admin/page.tsx`)
- 서버 컴포넌트에서 `redirect("/admin/users")`(`next/navigation`, 데이터 호출 없음). 19·25가 생겨도 첫 화면은 사용자 목록.

### 6.3 사용자 목록 `/admin/users` (`app/admin/users/page.tsx`, `"use client"`)
- **상태 탭**: 승인 대기(기본) · 활성 · 거절됨 · 비활성 · 전체. 탭을 바꾸면 `listUsers(status)` 다시 호출(전체는 `status` 없음). 탭 상태는 화면 안에서만(주소 쿼리에 넣지 않음).
- **목록**: 사용자마다 한 줄(좁은 화면은 카드). 표시 — 아이디, 이메일, 상태(`STATUS_LABEL`), 관리자면 "관리자" 표시, 가입 신청 일시, 승인 일시(없으면 "—"). 일시는 `formatKst`(KST `YYYY-MM-DD HH:mm`).
- **버튼**(관리자 계정 줄에는 없음):
  | 상태 | 버튼 | 확인 창 |
  |---|---|---|
  | 승인 대기 | [승인] [거절] | 승인: 없음 / 거절: `"{아이디} 님의 가입 신청을 거절할까요? 되돌릴 수 없어요."` |
  | 활성 | [비활성화] | `"{아이디} 님을 비활성화할까요? 바로 로그아웃되고, 다시 켤 수 없어요."` |
  | 거절됨·비활성 | 없음 | — |
  - 확인 창은 브라우저 기본 `window.confirm`(§12 Q6). 취소하면 요청하지 않는다.
- **처리 결과**:
  | 결과 | 화면 |
  |---|---|
  | 200 | 알림(`role="status"`): 승인 `"{아이디} 님을 승인했어요."` / 거절 `"{아이디} 님의 가입 신청을 거절했어요."` / 비활성화 `"{아이디} 님을 비활성화했어요."` → 지금 탭 목록 다시 불러오기 |
  | 409 (`user_status_conflict`·`admin_target`) · 404 | 오류 알림에 서버 문구 → 목록 다시 불러오기 |
  | 401 | `router.replace("/login")` |
  | 403 `forbidden` | 오류 알림 "접근 권한이 없어요." (목록 숨김) |
  | 403 `csrf_failed`(14 재시도 후에도) · 네트워크 · 서버 오류 | 오류 알림(14 문구) |
- 처리 중에는 그 줄의 버튼만 비활성("처리 중…"). 다른 줄은 누를 수 있다.
- **빈 목록**: 탭별 `"승인 대기 중인 신청이 없어요."` / `"활성 사용자가 없어요."` / `"거절된 신청이 없어요."` / `"비활성 사용자가 없어요."` / `"사용자가 없어요."`.
- 로딩: "불러오는 중…". 자동 새로고침(폴링) 없음 — 탭을 다시 누르면 새로 불러온다.

### 6.4 API 함수 (`web/lib/admin-api.ts`)
```ts
export type UserStatus = "pending" | "active" | "rejected" | "disabled";
export type AdminAction = "approve" | "reject" | "disable";
export type AdminUser = {
  id: number; username: string; email: string;
  role: "user" | "admin"; status: UserStatus;
  created_at: string; approved_at: string | null;   // ISO 8601
};
export const STATUS_LABEL: Record<UserStatus, string>;
/** 사용자 목록을 가져온다. status가 없으면 전체. */
export function listUsers(status?: UserStatus): Promise<AdminUser[]>;         // GET /api/admin/users[?status=]
/** 사용자 1명에게 승인·거절·비활성화를 적용하고 바뀐 값을 돌려준다. */
export function applyUserAction(id: number, action: AdminAction): Promise<AdminUser>;   // POST /api/admin/users/{id}/{action}
/** ISO 시각을 한국 시간 "YYYY-MM-DD HH:mm"으로 바꾼다(19 사용량 화면도 재사용). */
export function formatKst(iso: string): string;
```
- 둘 다 14 `apiJson` 사용(CSRF 헤더·오류 정규화·csrf 재시도 1회는 14가 처리).
- `formatKst`: `Intl.DateTimeFormat("en-US", { timeZone: "Asia/Seoul", year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).formatToParts(new Date(iso))`에서 부분을 꺼내 `${year}-${month}-${day} ${hour}:${minute}`로 조립(로캘별 표기 차이를 피함). 자정은 `00`.

### 6.5 계정 화면 링크 (`(chat)/account/page.tsx`, 14 수정)
- `useMe().role === "admin"`일 때만 "관리자 화면" 링크(`/admin`)를 "채팅으로" 링크 옆에 둔다(§12 Q4). 그 밖 14 동작은 그대로.

---

## 7. 엣지케이스

| 상황 | 동작 |
|---|---|
| 로그인 안 하고 `GET /api/admin/users` | 401 `unauthenticated` |
| 일반 사용자(active) | 403 `forbidden` (형식이 틀린 요청도 403 — §4.1) |
| pending 사용자 | 403 `forbidden`(05 `require_admin` — role이 admin 아님) |
| 관리자인데 status가 active 아님(DB로 바꾼 경우) | 403 `forbidden` |
| CSRF 헤더 없이 POST | 403 `csrf_failed`(라우터 실행 안 함) |
| `?status=deleted` | 422 |
| `/users/abc/approve`, `/users/0/approve`, `/users/9223372036854775808/approve` | 422 |
| `/users/1/delete` | 422 |
| 없는 사용자 id | 404 `user_not_found` |
| pending 승인 | active, `approved_at = now`, `approved_by = 관리자 id` |
| 이미 active인데 승인(버튼 두 번·관리자 둘) | 409 `user_status_conflict`, `"status":"active"`, DB 그대로(`approved_at` 덮어쓰지 않음) |
| pending 거절 | rejected. 그 사용자가 로그인 상태였으면 다음 요청에서 401(05 `current_user`가 세션 삭제) |
| rejected 승인 | 409 (§12 Q2) |
| active 비활성화 | disabled, 그 사용자 세션 0개, 관리자 세션은 그대로 |
| 비활성화 직후 그 사용자 채팅 요청 | 401 `unauthenticated` |
| 비활성화 때 그 사용자의 답변이 스트리밍 중 | 그 답변 1개는 끝까지 간다(SSE 시작 전에만 인증 검사 — 05 §6.8). 저장도 된다. 다음 요청부터 401 |
| disabled 사용자 다시 로그인 | 401 `login_failed`(같은 문구 — NFR-03) |
| disabled 사용자의 비밀번호 재설정 | 06: 코드 메일 안 감, 확인 단계 `reset_failed` |
| disabled 재활성화 | 409. 필요하면 DB 명령(§8) |
| 관리자 자신·다른 관리자 대상 동작 | 409 `admin_target` |
| 승인한 관리자 계정이 나중에 지워짐 | `approved_by` NULL(04 FK SET NULL) |
| disabled 사용자의 대화·사용량 기록 | 그대로 남음(90일 정리는 21 규칙) |
| 관리자가 하루 50회를 넘게 채팅 | 11 규칙(관리자는 한도 없음) — 18 변경 없음 |
| 일반 사용자가 `/admin/users` 주소 입력 | 화면 "접근 권한이 없어요.", `/api/admin/*` 요청 0회 |
| pending 사용자가 `/admin` | `/pending`(14 AuthGate) |
| 목록이 아주 길어짐(가입 스팸) | 페이지 없이 전부 표시. 가입은 IP별 1시간 5회(05) — 데모 규모에서 받아들임(§12 Q5) |

---

## 8. 운영 명령 (CLAUDE.md·HITL용, 코드 아님)

- 첫 관리자: `docker compose run --rm api nadri create-admin --username admin --email <이메일>`(05, 변경 없음).
- 잘못 거절·비활성화했을 때 되돌리기(화면 없음 — [A] §13):
  `docker compose exec postgres psql -U postgres -d nadri -c "update users set status='active', approved_at=now() where username='<아이디>'"`

---

## 9. 19·25가 넓히는 방법 (약속)

| 대상 | 18이 정하는 것 | 19 / 25가 하는 것 |
|---|---|---|
| `nadri/api/admin/router.py` | `admin_router`(접두어 `/api/admin`, `dependencies=[Depends(require_admin)]`), `admin_router.include_router(users.router)` | `usage.py`(19)·`quality.py`(25)에 `router = APIRouter()`를 만들고(접두어 없음, 경로는 `/usage`·`/quality/...`), 여기서 `admin_router.include_router(...)` 한 줄 추가. **하위 라우터에 권한 검사를 다시 달 필요 없다** |
| 권한 누락 방지 테스트 | `tests/api/admin/test_admin_guard.py` A-ADR-06: 앱의 모든 경로 중 `/api/admin`으로 시작하는 것은 의존성 트리에 `require_admin`이 있어야 함 | 19·25 경로가 추가되면 이 테스트가 자동으로 검사(수정 불필요) |
| `web/app/admin/layout.tsx` | 위 §6.1 그대로 | 고치지 않는다 |
| `web/components/admin/AdminShell.tsx` `ADMIN_NAV` | `[{href:"/admin/users", label:"사용자"}]` | 19: `{href:"/admin/usage", label:"사용량"}`, 25: `{href:"/admin/quality", label:"품질"}` 추가 |
| `web/lib/admin-api.ts` | 타입·`listUsers`·`applyUserAction`·`formatKst` | 각자 API 함수를 이 파일에 추가하거나 별도 파일(19·25 spec이 정함). `formatKst` 재사용 |
| `errors.py` | 18 코드 3개 | 각자 추가 |

- 19와 18이 동시에 작성·구현되면 `router.py`·`AdminShell.tsx`는 **18이 먼저 병합**되는 것을 전제로 한다(19 의존 작업 = 18, [PL] §2).

---

## 10. 앞 작업과 달라지는 점 · 앞 작업 테스트 수정

| # | 내용 | 대상 | 처리 |
|---|---|---|---|
| 1 | `errors.py`에 문구 상수 3개 | 05 문구 상수 테스트(상수 목록을 고정 비교하면) | 목록에 추가 |
| 2 | `main.py`가 `admin_router` 등록 | 05 A-ADM-1(테스트 전용 `/api/_test/admin`) | 수정 없음 — 그대로 둠(05 의존성 단위 확인용) |
| 3 | `(chat)/account/page.tsx`에 관리자 링크 | 14 Vitest 계정 화면 테스트(`V-PG-*`) | 기존 테스트는 일반 사용자 `me`라 링크 없음 → 수정 없음. 18 test에 관리자 케이스 추가 |
| 4 | `e2e/helpers/db.ts`에 `makeAdmin` | 14 Playwright | 수정 없음(함수 추가만). `global-setup.ts`가 `e2e_%` 사용자를 지우므로 `e2e_admin_*`도 같이 지워짐 |
| 5 | 05 HITL H-3 4번·14 Playwright `approve()`(psql 직접 승인) | 문서·테스트 | 그대로 둠(테스트 준비용으로 계속 유효). 18 HITL은 화면으로 승인 |
| 6 | 백엔드 다른 모듈·DB 변경 없음 | — | — |

상위 문서와의 차이(구현 판단):
1. **동작 경로 3개를 `{action}` 1개로** 받는다(§4.2) — 바깥 주소는 [A] §6.1과 같다. 허용 밖 action은 422.
2. **관리자 계정 대상 동작 금지**(`admin_target`, §12 Q3) — 문서에 없음. 마지막 관리자를 스스로 비활성화해 아무도 `/admin`에 못 들어가는 일을 막는다.
3. **거절은 세션을 즉시 지우지 않음**(05 `current_user`가 다음 요청에 처리) — [A] §3.4는 비활성화만 세션 삭제를 적었다.
4. `/admin` → `/admin/users` 이동 화면, `AdminShell.tsx`, 계정 화면 링크 추가([PL] 파일 목록 밖, §2).
5. **의존 작업**: [PL] 표는 11·14지만 11 의존은 삭제된 "한도 추가 요청" 때문이었다. 18 코드는 11의 어떤 것도 쓰지 않는다(§12 Q1).

문서 정리 필요(18 범위 밖, 보고만):
- [PL] §1.2 의존 그래프에 옛 이름 `18 admin-users-quota`가 남아 있다.
- [A] §7 디렉터리 `web/app/admin/(users, quota, usage, quality/)`에 삭제된 `quota`가 남아 있다.
- 14 spec §1.1 표 "피드백·**한도 요청**·위치·음성"에 삭제된 기능 이름이 남아 있다.

---

## 11. 완료 기준 (DoD)

1. test.md ① 전부 통과: `cd ~/code/myAgent/backend && uv run pytest -m "not integration"`, `cd ~/code/myAgent/web && npm run typecheck && npm run test`, compose 기동 상태에서 `npm run e2e`(18의 `admin.spec.ts` 포함). §10 앞 작업 테스트 수정 후 통과.
2. 권한: 미로그인 401, 일반·pending 사용자 403, CSRF 없음 403, 모든 `/api/admin/*` 경로에 `require_admin`(A-ADR-06).
3. 상태 전이 표(§5) 전 칸 테스트 통과, 승인 시 `approved_at`·`approved_by` 기록.
4. 비활성화 → 그 사용자 세션 0개, 다음 요청(채팅 포함) 401, 재로그인 `login_failed`.
5. Playwright: 가입 신청 → 관리자 화면에서 승인 → 그 사용자 로그인 → 채팅 화면 진입. 일반 사용자는 `/admin`에서 권한 없음 안내.
6. HITL-1·2 결과 보고.
7. 모든 함수·컴포넌트에 한국어 docstring/JSDoc(요약·인자·반환), 함수 안 단계 주석([CL]). 커밋 `feat/18-admin-users`, `[Feat] …` + 작업 목록 + `Author:`, AI 공동작성 표기 없음. `dev` 병합은 G5 후. `PROGRESS.md` 갱신. `CLAUDE.md` 명령어 절에 §8 되돌리기 명령 한 줄.

---

## 12. 확인 질문

| # | 질문 | 추천안 | 대안 |
|---|---|---|---|
| 18-Q1 | [PL] 표의 18 의존 작업은 "11, 14"인데, 11 의존은 삭제된 한도 추가 요청 때문이었다. 18 코드는 11을 쓰지 않는다(실제 의존 05·14). 의존을 고칠까 | **[PL] 표를 "05, 14"로 고친다**(문서만 — 병합 순서는 지금 계획대로 두어도 됨). 18 spec 머리말도 맞춤 | 그대로 "11, 14"(11 병합 뒤에만 시작) |
| 18-Q2 | 거절(`rejected`)한 신청을 나중에 승인할 수 있게 할까 | **안 함**(409) — [A] §13 "재활성화 없음"과 같은 원칙, 잘못 거절했으면 §8 DB 명령으로 되돌림 | 거절됨 → 승인 허용(버튼 1개 추가, 표 1칸 변경) |
| 18-Q3 | 관리자 계정(자기 자신 포함)을 이 화면에서 비활성화할 수 있게 할까 | **막는다**(409 `admin_target`) — 실수로 마지막 관리자를 끄면 `/admin`에 아무도 못 들어감. 관리자 계정은 CLI·DB로만 관리 | 자기 자신만 막고 다른 관리자는 허용 / 막지 않음 |
| 18-Q4 | 관리자가 `/admin`으로 가는 링크를 어디에 둘까(문서에 없음) | **`/account` 화면에 관리자만 보이는 "관리자 화면" 링크**(14 파일 한 줄, 15 채팅 화면은 건드리지 않음) | 15 사이드바 하단 "계정" 옆 / 링크 없이 주소 직접 입력 |
| 18-Q5 | 사용자 목록에 페이지 나누기·검색을 넣을까 | **넣지 않음** — 사용자 1~5명(NFR-61), 가입은 IP별 시간당 5회 제한(05). 기본 탭 "승인 대기", 가입 신청 최신순 | 50명 단위 페이지 / 아이디 검색 |
| 18-Q6 | 거절·비활성화 전 확인을 어떻게 받을까 | **브라우저 기본 확인 창(`window.confirm`)을 거절·비활성화에만**(되돌릴 수 없는 동작만, 승인은 바로) — 컴포넌트 추가 없음 | shadcn Dialog 추가(모양 통일, 파일·의존성 증가) / 승인도 확인 |
| 18-Q7 | 거절·비활성화한 시각·관리자를 DB에 남길까(ERD에는 `approved_at`·`approved_by`만 있음) | **남기지 않음 — 로그 1줄**(`admin_user_action`: 관리자 id·사용자 id·동작·전후 상태). ERD 그대로 | `users`에 처리 일시·처리 관리자 컬럼 추가(ERD·04 테이블 변경 — G3 범위) |
| 18-Q8 | 이미 처리된 사용자에 같은 동작을 다시 보내면(버튼 두 번·관리자 둘) | **409 `user_status_conflict` + 화면이 목록을 다시 불러옴**(무엇이 일어났는지 알 수 있음, 승인 일시를 덮어쓰지 않음) | 결과가 같으면 200(멱등 — 13 피드백 DELETE 방식) |
| 18-Q9 | [PL] §3 18 "FR-82 … id는 유지, 이름 정리는 확인 필요"의 "이름 정리"를 18에서 할 일이 있는가 | **없음** — 18 추적은 FR-04·80·81·84로 적고 FR-82는 "삭제됨"으로만 언급. 요구사항 번호는 다시 매기지 않음(추적표가 이미 "삭제됨" 표시) | FR-83·84를 앞당겨 번호를 다시 매김(문서 여러 곳 수정) |
