# 작업목록 — nadri (관광 챗봇 PWA + 관리자 백오피스)

> 하네스 Phase 3 산출물 (task-planner, 작성 2026-11-21) — **G4 승인 (2026-11-21)**. 확인 질문 Q1~Q9 답변은 §5.2 "결정" 열.
> 입력: `requirements.md`(G1, 2026-11-21 개정본) · `stack-options.md`(G2) · `architecture.md`(G3 2026-11-21 재승인본, **정본**) · `erd.md`/`docs/images/src/erd.py`(ERD 19개 테이블, 한글 명칭 정본) · `SECURITY_GUIDE.md` · `TECH_STACK.md` · `README.md` · `PROGRESS.md` 결정 로그.
> 출처 표기: [R]=requirements.md, [A]=architecture.md, [S]=stack-options.md, [E]=ERD, [SG]=SECURITY_GUIDE.md, [PG]=PROGRESS.md, [CL]=CLAUDE.md.
> 이 문서는 아키텍처에 없는 기능을 만들지 않는다. 모든 작업은 [A]의 모듈·흐름·ADR과 [R]의 FR/NFR로 추적된다(§4).

---

## 1. 개요

### 1.1 작업 분해 원칙
1. **처음 2개 작업은 최소 end-to-end 수직 슬라이스**(G2 결정: 별도 PoC 없음 [PG]). 아키텍처를 바꿀 수 있는 위험 연동 — LightRAG `/query/data`·한국어 추출·CrossEncoder 지연·MCP 어댑터↔`mcp` 1.30·`gpt-6-luna` Responses 툴 루프·스트리밍 usage/캐시·LangGraph 스트림 모드·Moderation·SSE의 Nginx/Cloudflare Named Tunnel 무버퍼링 — 을 **실제 호출로** 확인한다([A] §12의 A7·A8·A9·A11·A12·A16·A18~A23·A25·A26·A30). 실패해 사용자 결정(D-xx·ADR)을 바꿔야 하면 **멈추고 사용자에게 묻는다**.
2. 슬라이스 코드는 버리는 코드가 아니다. 이후 작업이 같은 모듈을 넓혀 간다(예: 01의 `bootstrap --limit` → 03의 예산·이어하기).
3. 작업 하나 = 브랜치 `feat/<작업id>` 하나 = 리뷰 가능한 크기(대략 하루 이내). 02·14는 하루를 조금 넘을 수 있어 표시했다.
4. 테이블은 01(관광·수집 4개)과 04(나머지 15개)에서 만든다 — ERD와 1:1로 대조 리뷰하기 쉽게.
5. 모든 서비스는 Docker Compose, 비밀값은 `.env`만, 자체 이미지는 처음부터 비루트·`cap_drop: [ALL]`·`no-new-privileges`([A] §9). 26에서 일괄 점검.
6. 테스트: 백엔드 pytest(LLM·MCP·Moderation·Tavily·TourAPI·SMTP·ElevenLabs 목킹한 결정적 단위테스트 기본, 실호출은 `@pytest.mark.integration`으로 분리), 프론트 Vitest + React Testing Library, 브라우저 흐름 Playwright [R NFR-70], [S S19]. 전체 E2E 시나리오(NFR-71)는 하네스 Phase 6에서 설계하고, 각 화면 작업은 자기 화면의 Playwright 부분만 갖는다.
7. 주석은 한국어(docstring/JSDoc + 단계 주석) [CL], 커밋은 `[Feat|Fix|Docs…] 요약` + 작업 목록 + `Author:` 줄, AI 공동작성 표기 없음 [R NFR-73].
8. 각 작업의 측정·확인 결과(미검증 가정 판정)는 Phase 4 작업별 spec 문서(`docs/harness/tasks/<작업id>/`)와 `PROGRESS.md` 결정 로그에 남긴다.

### 1.2 의존 순서 그래프

```
01 e2e-tools-slice ─┬─▶ 02 e2e-chat-slice ─┬─▶ 05 auth-core ─┬─▶ 06 password-reset-mail ─┐
                    │                       │                 │                           ├─▶ 14 web-foundation
                    │                       │                 │                           │
                    ├─▶ 04 db-schema ───────┼─▶ (05)          │
                    │                       │                 ▼
                    ├─▶ 07 guard-pii ───────┴────────────▶ 08 guard-pipeline ─▶ 09 chat-sessions ─▶ 11 quota-usage ─▶ 12 faq-cache ─▶ 13 feedback
                    │                                          │                                     │                 │                │
                    ├─▶ 10 tool-tour-live (01·02)              └─▶ 23 eval-attack-set                │                 │                │
                    │                                                                                │                 ▼                │
                    └─▶ 03 ingest-bootstrap ─▶ 20 ingest-hubs-lint (03·11) ─────────────────────────▶ 21 ingest-daily-sync (12·20)       │
                                                                                                                       │                │
 14 + 09 + 11 ─▶ 15 web-chat ─┬─▶ 16 web-chat-actions (13·15)                                                           ▼                │
                              └─▶ 17 voice (11·15)                                       24 eval-daily-quality (13·21·23) ◀─────────────┘
 11 + 14 ─▶ 18 admin-users-quota ─▶ 19 admin-usage                                               │
                              └──────────────────────────────────────────▶ 25 admin-quality-hitl (18·24)
 03 + 08 + 10 + 11 ─▶ 22 eval-golden
 01~25 전부 ─▶ 26 release-readiness
```

- **임계 경로**: 01 → 02 → 05 → 08 → 09 → 11 → 12 → 13 → (20·21) → 24 → 25 → 26.
- **병렬 가능**: 03(초기 적재는 개발계정 한도 때문에 **여러 날** 걸리므로 슬라이스 직후 시작해 백그라운드로 누적), 04·07(01만 있으면 됨), 10.

### 1.3 마일스톤 묶음

| 마일스톤 | 작업 | 끝나면 되는 것 |
|---|---|---|
| **M0 위험 검증 슬라이스** | 01, 02 | 실제 데이터 → LightRAG → MCP 툴 → LangGraph(답변·검증) → SSE가 터널 주소로 흐름. 아키텍처 위험 가정 판정 완료 |
| M1 적재 시작 + 기반 | 03, 04, 05, 06, 07 | 초기 적재 진행 중, 19개 테이블, 가입·로그인·재설정 API, PII 가리기 |
| M2 채팅 백엔드 완성 | 08, 09, 10, 11, 12, 13 | 입력/출력 검사 전체, 대화 저장·이력, 툴 5개, 한도·사용량, FAQ 캐시, 피드백 |
| M3 화면 | 14, 15, 16, 17 | PWA 로그인·채팅·피드백·위치·한도 요청·음성 |
| M4 관리자 | 18, 19 | 가입·한도 승인, 비활성화, 사용량 대시보드 |
| M5 현행화 | 20, 21 | 허브·lint·위키 git, 매일 01:00 현행화·90일 정리 |
| M6 평가·품질 HITL | 22, 23, 24, 25 | 골든 평가·공격 세트·매일 03:00 품질 보고서·개선안 채택/보류/기각 |
| M7 릴리스 준비 | 26 | 클린 기동·보안 설정 점검·실행 문서 → Phase 6(E2E 설계) → `dev`→`prod`, `v1.0` |

`/clear` 안내 시점([CL]): G4 승인 후, 그리고 작업별 G5 통과마다(Phase 4 spec 작성은 5개 안팎마다).

---

## 2. 작업 표

| 작업id | 작업명 | 생성 소스파일 (주요) | 각 파일 역할 | 의존 작업 | 스펙 요약 |
|---|---|---|---|---|---|
| 01-e2e-tools-slice | 최소 E2E ① 데이터→RAG→MCP 툴 | `compose.yaml`, `compose.dev.yaml`, `.env.example`, `infra/postgres/init/01-init.sh`, `infra/lightrag/lightrag.env`, `backend/{pyproject.toml,uv.lock,Dockerfile,alembic.ini}`, `backend/alembic/versions/0001_tour_ingest.py`, `nadri/core/{config,db,tourapi}.py`, `nadri/core/models/{tour,ingest}.py`, `nadri/ingest/{raw,upsert,indexer,bootstrap}.py`, `nadri/ingest/wiki/{render.py,templates/entity.md.j2}`, `nadri/tools/{server,rag_query,data_query,get_datetime,reranker}.py`, `nadri/cli.py` | compose 4서비스(postgres·lightrag·tour-tools·ingest)·볼륨 / DB·롤 초기화 / LightRAG 설정 / uv 프로젝트·버전 고정·이미지 타깃 2개 / 관광·수집 4테이블 / 설정·DB·TourAPI 클라이언트 / raw·upsert·엔티티 위키·LightRAG 인덱싱·`--limit` 적재 / MCP 서버(토큰 미들웨어)·툴 3종·CrossEncoder | — | 서울 관광지 수십 건 실적재 → 위키 → LightRAG → `rag_query`·`data_query`·`get_datetime`을 MCP 어댑터로 실호출. A7·A8·A9·A12·A16·A21 판정. FR-19·40~42·44·50·51·53 |
| 02-e2e-chat-slice | 최소 E2E ② LangGraph·검증·SSE·터널 | `infra/nginx/nginx.conf`, compose(api·nginx·cloudflared 추가), `nadri/api/main.py`, `nadri/api/chat/{router,sse}.py`, `nadri/agent/{state,graph,nodes,tools,evidence}.py`, `nadri/guard/{moderation,output_guard}.py`, `nadri/core/llm.py`, `nadri/prompts/{answer,verify}.md` | Nginx SSE 무버퍼링 / FastAPI 앱·헬스 / 채팅 SSE 엔드포인트(슬라이스: 저장 없음)·이벤트 변환·ping·타임아웃 / StateGraph(answer⇄tools→verify→revise)·MCP+Tavily 툴·툴 결과→출처 / 입력·출력 Moderation(fail-closed)·코드 검사(contentid·URL) / ChatOpenAI 생성(Responses·store=False·cache key) / 프롬프트 | 01 | 터널 주소로 SSE 토큰 단위 수신, 실툴 기반 답변, 검증 구조화 출력, 다시 쓰기 루프, usage·cache_read 수집. A11·A18·A19·A20·A22·A23·A25·A26·A30 판정. FR-10~13·18·22·54·90·91, NFR-11·13·22·23·36·40 |
| 03-ingest-bootstrap | 초기 적재(서울·제주×8종, 이어하기) | `nadri/ingest/budget.py`, `nadri/ingest/bootstrap.py`(확장), `nadri/core/tourapi.py`(확장), `nadri/ingest/wiki/templates/*.md.j2`(8종), `nadri/cli.py`(확장) | 일일 호출 예산(800)·한도 에러코드 / 목록→상세3종→raw→upsert→렌더→해시 인덱싱, 커서 이어하기, `ingest_runs` / 타입별 상세 필드 / 타입별 엔티티 템플릿 | 01 | FR-40·41·42·44·48, ADR-14. 여러 날 백그라운드 누적. A8(넓은 표본)·A12 |
| 04-db-schema | 앱 테이블 15개 + ORM | `backend/alembic/versions/0002_app_tables.py`, `nadri/core/models/{account,chat,quota,quality}.py`, `backend/tests/test_schema_comments.py` | 계정·대화·한도·품질 테이블 DDL + 한글 COMMENT + FK 동작 / ORM / ERD 명칭 대조 테스트 | 01 | ERD 19개 테이블 완성, COMMENT = ERD, 연쇄 삭제 규칙([A] §5.1) |
| 05-auth-core | 가입 신청·로그인·세션·CSRF·잠금·관리자 CLI | `nadri/api/auth/{router,service,sessions,csrf}.py`, `nadri/api/ratelimit.py`, `nadri/api/deps.py`, `nadri/core/data/common_passwords.txt`, `nadri/cli.py`(create-admin) | 인증 API / Argon2id·정책 / `__Host-session` 서버 세션 / 서명 double-submit CSRF / `rate_limits` 고정 윈도·잠금 / 현재 사용자·활성·관리자 의존성 / 흔한 비밀번호 목록 / 첫 관리자 생성 | 02, 04 | FR-01~04·06·80(CLI), NFR-01~06·10·34, ADR-10·15. 슬라이스 채팅 엔드포인트에 `require_active` 연결. A17 |
| 06-password-reset-mail | 이메일 인증코드 비밀번호 재설정 | `nadri/api/mail.py`, `nadri/api/auth/reset.py` | Gmail SMTP 백그라운드 발송 / request·confirm(10분·5회·문구 통일·전 세션 폐기) | 05 | FR-05·07, NFR-03·06 |
| 07-guard-pii | 개인정보 가리기 규칙 | `nadri/guard/pii.py`, `backend/tests/guard/test_pii_table.py` | 규칙 기반 PII 탐지·형식 유지 `*` 가리기·종류 반환 / 가려야·가리면 안 되는 입력 표 테스트 | 01 | NFR-35, ADR-21, G3 Q3·Q4. A27·A29 |
| 08-guard-pipeline | 입력 검사 3단·출력 검사·보안 이벤트 | `nadri/guard/{input_guard,classifier,events}.py`, `nadri/guard/output_guard.py`(확장), `nadri/prompts/{classify.md,fixed_messages.toml}`, `nadri/prompts/{answer,verify}.md`(보강), `nadri/agent/nodes.py`·`nadri/api/chat/router.py`(연결) | PII→Moderation→분류기 순차 / 탈옥·인젝션·범위 밖 분류 / `security_events` 기록 / 카나리·링크 강등 / 고정 안내·109·안전 문구 | 02, 05, 07 | NFR-11~16·35, FR-90(보안 항목), ADR-18·20·21·22·27. A22·A23·A24(초기) |
| 09-chat-sessions | 대화 세션·컨텍스트·저장·제목/요약 | `nadri/api/chat/{router,context,store,background}.py`, `nadri/prompts/{title,summary}.md` | 세션 CRUD·메시지 본 구현 / 요약+최근 10턴·위치 / 한 트랜잭션 저장(툴 결과·검증·timings) / 제목·누적 요약 단발 호출 | 08 | FR-06·10·14~17·20·55(백엔드)·104, D-10, NFR-30·33·35·60, ADR-03 |
| 10-tool-tour-live | `tour_live` 툴 | `nadri/tools/tour_live.py`, `nadri/tools/server.py`·`nadri/core/tourapi.py`·`nadri/agent/tools.py`(확장) | 진행 중 축제·좌표 주변 실시간 조회 / 등록·라벨 | 01, 02 | FR-52·55, NFR-07 |
| 11-quota-usage | 일일 한도·분당 제한·사용량 기록 | `nadri/api/quota.py`, `nadri/api/usage.py`, `nadri/core/pricing.py`, `nadri/api/chat/router.py`(연결) | 50+추가분 한도·추가 요청 API / 호출별 `usage_events`·비용 / 단가표 / 채팅 분당 10회·차감 규칙 | 09 | FR-61·62, NFR-06·40·43·60, ADR-27 |
| 12-faq-cache | FAQ 유사도 캐시 | `nadri/api/faq_cache.py`, `nadri/core/llm.py`(임베딩), `nadri/api/chat/router.py`(연결) | 조회·저장·무효화 함수 / `OpenAIEmbeddings` | 11 | FR-60·92, ADR-13 |
| 13-feedback | 👍/👎 피드백 API | `nadri/api/feedback.py` | upsert·취소, 👎 시 연결 FAQ 캐시 삭제 | 12 | FR-103(백엔드) |
| 14-web-foundation | Next.js 기반·인증 화면·PWA | `web/{package.json,next.config.ts,Dockerfile,vitest.config.ts,playwright.config.ts}`, `web/app/layout.tsx`, `web/app/(auth)/{login,signup,pending,reset}/page.tsx`, `web/app/(chat)/account/page.tsx`, `web/lib/api.ts`, `web/app/manifest.ts`, `web/public/{sw.js,icons/}`, `web/components/RegisterSW.tsx`, compose·nginx(`/` 라우트) | 앱 골격·standalone 빌드 / 로그인·가입·승인 대기·재설정·비밀번호 변경 / CSRF 헤더 붙는 fetch 클라이언트 / manifest·최소 SW(`/api` 미가로채기) | 05, 06 | FR-01~05 화면, NFR-04·05·10·52, ADR-12. (하루 초과 가능) |
| 15-web-chat | 채팅 화면·SSE 파서·안전 렌더러 | `web/lib/sse.ts`, `web/components/chat/{ChatView,MessageBubble,SafeMarkdown,Sidebar,StatusLine}.tsx`, `web/app/(chat)/page.tsx`, `web/app/(chat)/[sessionId]/page.tsx` | §3.1 이벤트 파서 / 초안→✓확인됨·교체·경고·차단·오류 재시도 / raw HTML·이미지 끔·링크 허용 목록 / 세션 목록·삭제 | 09, 11, 14 | FR-10·15~18·20·21·91, NFR-14·23. A11(모바일)·A30(화면) |
| 16-web-chat-actions | 피드백·한도 추가 요청·위치 동의 UI | `web/components/chat/{FeedbackButtons,QuotaRequestButton,LocationToggle}.tsx` | 👍/👎+사유 / 429 시 "추가 요청" / 위치 동의 토글·좌표 전송 | 13, 15 | FR-55·62·103 화면, NFR-33 |
| 17-voice | STT·TTS (Provider 인터페이스) | `nadri/api/voice/stt/{base,openai}.py`, `nadri/api/voice/tts/{base,elevenlabs}.py`, `nadri/api/voice/router.py`, `web/lib/recorder.ts`, `web/components/chat/{PttButton,SpeakerButton}.tsx` | `SttProvider`/`TtsProvider`와 구현체 / `/api/stt`·`/api/tts` / MediaRecorder 60초·포맷 선택 / 녹음·재생 버튼 | 11, 15 | FR-30~32, NFR-06·43·50·51, [S S2·S20]. A13 |
| 18-admin-users-quota | 관리자: 가입·한도 승인·비활성화 | `nadri/api/admin/{router,users,quota_requests}.py`, `web/app/admin/{layout.tsx,users/page.tsx,quota/page.tsx}` | 역할 검사 관리자 API / 승인·거절·비활성화(세션 폐기) / +50 승인 / 백오피스 화면 | 11, 14 | FR-04·80~82·84 |
| 19-admin-usage | 관리자: 사용량 대시보드 | `nadri/api/admin/usage.py`, `web/app/admin/usage/page.tsx` | 사용자·일자·kind별 토큰·비용, 월 누적·$10 경고 | 18 | FR-63·83, NFR-43. A14·A28 |
| 20-ingest-hubs-lint | 허브 페이지·lint·위키 git | `nadri/ingest/wiki/{hubs,lint,git}.py`, `nadri/prompts/hub.md`, `backend/Dockerfile`(git 설치), `nadri/cli.py`(`ingest hubs`) | 시군구 허브 27개 LLM 작성·인덱싱 / 깨진 링크·기준일 경과·모순 리포트 / 위키 볼륨 git 커밋 | 03, 11 | FR-43·46·47, NFR-24 |
| 21-ingest-daily-sync | 매일 01:00 현행화·90일 정리 | `nadri/ingest/{scheduler,sync,cleanup}.py`, `nadri/ingest/jobs/daily_sync.py`, `nadri/cli.py`(`ingest sync --now`), compose(ingest 상주) | APScheduler(Asia/Seoul)+advisory lock / SyncList 변경·삭제 반영 / 90일·만료 정리 / 작업 묶음 | 12, 20 | FR-45, NFR-31, ADR-09 |
| 22-eval-golden | 골든 Q&A 평가 | `eval/golden/golden.jsonl`, `eval/README.md`, `nadri/eval/golden.py`, `nadri/cli.py`(`eval golden`), `nadri/tools/rag_query.py`·`nadri/core/config.py`(리랭커·모드 설정값) | 평가셋(관광·스몰토크) / 정답률·근거 일치율·지연·토큰·비용, 리랭커 on/off·검증 0/1/2·mix/hybrid 비교 | 03, 08, 10, 11 | FR-70(골든). A10·A22(오탐)·A24·A25 |
| 23-eval-attack-set | 공격 질문 세트 | `eval/attack_set/attacks.jsonl`, `nadri/eval/attack.py`, `nadri/cli.py`(`eval attack`) | 유형별 공격(한국어 포함)·통과 기준 / 실제 guard+그래프, 오염된 가짜 웹 툴, 코드 판정 우선 | 08 | NFR-16, FR-70(방어율), [SG] §4 |
| 24-eval-daily-quality | 매일 03:00 평가·개선안 에이전트 | `nadri/eval/{anonymize,quality,proposals}.py`, `nadri/ingest/jobs/daily_quality.py`, `nadri/prompts/{evaluate,propose}.md`, `nadri/ingest/scheduler.py`(등록), `nadri/cli.py`(`eval quality --date`) | 익명화 / 턴 채점·집계·보고서 / 개선안 작성 / 배치 작업 | 13, 21, 23 | FR-100·101·104·105, NFR-36, ADR-09·23 |
| 25-admin-quality-hitl | 관리자: 품질 리포트·개선안 결정 | `nadri/api/admin/quality.py`, `web/app/admin/quality/{page.tsx,[reportId]/page.tsx,proposals/page.tsx}` | 보고서·개선안 조회 API, 채택/보류/기각+메모 / 화면 | 18, 24 | FR-102 |
| 26-release-readiness | 릴리스 준비 점검 | `backend/tests/test_compose_hardening.py`, `compose.yaml`·`.env.example`(최종), `README.md`(시작하기·상태), `CLAUDE.md`(명령어) | compose 보안 설정·서비스별 비밀값 주입 검사 / 클린 볼륨 기동 확인 / 실행 문서 | 01~25 | NFR-08·09·17·20·21, ADR-01·26 |

---

## 3. 작업별 상세

### 01-e2e-tools-slice — 최소 E2E ① 데이터 → RAG → MCP 툴
**목표**: 실제 TourAPI 응답 → raw → `tour_items` → 엔티티 위키(수십 페이지) → LightRAG 인덱싱 → tour-tools MCP 툴 호출까지를 실제로 돌려, 데이터·RAG 쪽 위험 가정을 판정한다. 이후 작업이 넓혀 갈 뼈대(compose, uv 프로젝트, Alembic, 설정)를 만든다.

**생성/수정 파일**
| 파일 | 역할 |
|---|---|
| `compose.yaml` | postgres(`pgvector/pgvector:pg18`)·lightrag(v1.5.7 고정)·tour-tools(tools 타깃)·ingest(app 타깃) 4서비스, 네트워크 1개, named volume `pg-data`·`wiki-data`·`raw-data`, 호스트 포트 없음, 서비스별 필요한 키만 주입 |
| `compose.dev.yaml` | 소스 마운트·핫리로드 |
| `.env.example` | 이 작업에서 쓰는 키 이름만(`OPENAI_API_KEY`, `TOURAPI_SERVICE_KEY`, `LIGHTRAG_API_KEY`, `TOOLS_API_KEY`, DB 비밀번호 4종) |
| `infra/postgres/init/01-init.sh` | DB `nadri`·`lightrag`, 롤 `nadri_app`·`nadri_tools`·`lightrag`, `vector` 확장, `nadri_tools`는 `tour_items`·`wiki_pages` SELECT만(§5 X-c 확인 필요: [A] §7은 `.sql`) |
| `infra/lightrag/lightrag.env` | PG 저장소 + `PGTableGraphStorage`, HNSW, `SUMMARY_LANGUAGE=Korean`, `RERANK_BINDING=null`, LLM `gpt-6-luna`, 임베딩 `text-embedding-3-small`(1536) |
| `backend/pyproject.toml`, `uv.lock` | Python 3.12, [A] §1 고정 후보 버전(`mcp` 1.30.x 등), `reranker` 그룹(torch·sentence-transformers)은 tools 타깃만 |
| `backend/Dockerfile` | 타깃 `app`(api·ingest) / `tools`(tour-tools, 빌드 시 `bge-reranker-v2-m3` 가중치 내려받기), 비루트 |
| `backend/alembic.ini`, `alembic/env.py`, `alembic/versions/0001_tour_ingest.py` | `tour_items`·`wiki_pages`·`ingest_runs`·`ingest_state` + 한글 COMMENT([E] `erd.py`) |
| `nadri/core/config.py` · `db.py` | 환경변수 설정(pydantic-settings) · async 엔진(asyncpg) |
| `nadri/core/models/tour.py` · `ingest.py` | ORM |
| `nadri/core/tourapi.py` | KorService2 클라이언트(`areaBasedList2`, `detailCommon2`·`detailIntro2`·`detailInfo2`), 오류코드 해석 |
| `nadri/ingest/raw.py` · `upsert.py` | 날짜별 불변 JSON 스냅샷 · `tour_items` upsert |
| `nadri/ingest/wiki/render.py`, `templates/entity.md.j2` | LLM 없는 엔티티 페이지 렌더(frontmatter: contentid, source, as_of, updated_at) |
| `nadri/ingest/indexer.py` | 내용 해시 비교 → LightRAG 문서 delete→insert, `wiki_pages` 갱신 |
| `nadri/ingest/bootstrap.py` | `--area --type --limit`로 소량 적재(예산·이어하기는 03) |
| `nadri/tools/server.py` | FastMCP(stateless Streamable HTTP) + `Authorization: Bearer TOOLS_API_KEY` ASGI 미들웨어 |
| `nadri/tools/rag_query.py` · `reranker.py` | LightRAG `/query/data`(mix, 약 30) → CrossEncoder → 상위 5 + `wiki_pages` 메타 |
| `nadri/tools/data_query.py` | `tour_items` 파라미터화 조회(지역·시군구·타입·키워드·near 하버사인·on_date·sort·limit≤20) |
| `nadri/tools/get_datetime.py` | 현재 KST·요일·이번 주말/다음 주 범위 |
| `nadri/cli.py` | `ingest bootstrap` |
| `CLAUDE.md` | "명령어" 절에 빌드·테스트·실행 명령 처음 기록([CL] 지시) |

**핵심 스펙**: FR-19·40·41·42·44·50·51·53, NFR-07(읽기 전용 툴·SELECT 롤)·08(내부망·키)·20·24·32, ADR-02·05(툴 결과는 항목마다 `contentid`·`source`·`as_of`인 구조화 JSON)·06·07·24.

**완료 기준**
- `docker compose up`으로 4서비스 정상 기동, 호스트 포트 없음.
- 서울 관광지 등 30~50건 실적재: raw 파일·`tour_items` 행·위키 md·LightRAG 문서 처리 완료.
- `langchain-mcp-adapters` 클라이언트로 툴 3종 호출 성공, 토큰 없거나 틀리면 401.
- `rag_query` 결과 5개 각각에 contentid·출처·기준일.
- 같은 페이지 재실행 시 LightRAG 중복 문서 없음, 내용 바꾸면 delete→insert.
- 측정치 기록: 50페이지 인덱싱 비용·시간(최초 인덱싱 $15~30 추정 재계산), CrossEncoder 30쌍 지연, 서울·제주×8종 `totalCount` → 적재 일수 추정.

**검증**
- 단위: 엔티티 렌더 스냅샷(frontmatter), upsert 멱등, `data_query` 파라미터 조합·하버사인·limit 상한·SQL 문자열 미조립, `get_datetime` 주말 범위(시각 고정), 인증 미들웨어 401, 인덱서 해시 비교(LightRAG 목킹).
- 통합(`integration`): 실 compose + 실 키로 위 완료 기준 재현.
- HITL: 한국어 엔티티 추출 샘플(엔티티·관계 10~20개)을 사용자에게 보여 품질 판단, 측정치 보고. 기준 미달이면 [A] §12 대안 중 사용자 확인 항목(A8 인덱싱 상위 모델, A9 GPU)을 묻는다.

**이 작업에서 검증할 가정**: **A7**(`/query/data` 식별자·후보 수), **A8**(한국어 추출), **A9**(CPU CrossEncoder 지연), **A12**(일부: 실제 호출·`totalCount`·한도 단위), **A16**(delete→insert·상태 조회 경로), **A21**(어댑터 0.3.2 ↔ mcp 1.30 FastMCP, `headers` 토큰).

---

### 02-e2e-chat-slice — 최소 E2E ② LangGraph·검증·Moderation·SSE·터널
**목표**: api 안 LangGraph(답변 ⇄ 툴 → 검증 → 다시 쓰기)와 입력·출력 Moderation, 자체 SSE 이벤트를 **Nginx·Cloudflare Named Tunnel 경유로** 실제 흘려 에이전트·스트리밍 쪽 위험 가정을 판정한다. 인증·대화 저장·PII·분류기·한도는 넣지 않는다(05·07·08·09·11).

**생성/수정 파일**
| 파일 | 역할 |
|---|---|
| `compose.yaml` | `api`(app 타깃), `nginx`, `cloudflared`(`tunnel run --token`, **05 병합 전까지 `profiles: [tunnel]`로 검증 때만 기동** — §5 Q1) 추가. api에 `LANGSMITH_TRACING=false`, `LANGCHAIN_TRACING_V2=false`, `TAVILY_API_KEY` |
| `compose.dev.yaml` | nginx `127.0.0.1` 포트 |
| `infra/nginx/nginx.conf` | `/api/` → api, `proxy_buffering off`, `proxy_read_timeout 300s`, `client_max_body_size 10m`, `CF-Connecting-IP` → `X-Real-IP` |
| `nadri/api/main.py` | FastAPI 앱, `GET /api/health` |
| `nadri/api/chat/router.py` | `POST /api/chat/sessions/{id}/messages` 슬라이스판(세션 미검증·저장 없음 — 09에서 본 구현) |
| `nadri/api/chat/sse.py` | 그래프 스트림 → [A] §3.1 이벤트(`status`·`tool`·`delta`·`draft_done`·`verified`·`replaced`·`warning`·`done`·`error`), 15초 `: ping`, 전체 타임아웃 180초 |
| `nadri/agent/state.py` · `graph.py` · `nodes.py` | 상태 정의 · `StateGraph`(answer·tools(`ToolNode`)·verify·revise, 조건 간선, `recursion_limit`) · 노드 구현(시도 0만 delta, 다시 쓰기는 모아서 `replaced`) |
| `nadri/agent/tools.py` | MCP 툴 로딩(Streamable HTTP + 토큰 헤더) + `TavilySearch(max_results=5, search_depth="basic", 이미지·raw 끔, auto_parameters 끔)`, 툴 결과를 `<자료 출처=…>` 구분자로 감쌈, 툴 라벨 |
| `nadri/agent/evidence.py` | 툴 결과 → contentid 집합·URL 집합·`sources` |
| `nadri/guard/moderation.py` | OpenAI SDK `omni-moderation-latest`, 5초 타임아웃·실패 = 차단(`guard_unavailable`), 범주 판정(self-harm 계열 구분) 반환 |
| `nadri/guard/output_guard.py` | 코드 검사: 인용 `(#contentid)` ⊆ 툴 결과, 링크 URL ⊆ 툴 결과 URL (카나리·강등은 08) |
| `nadri/core/llm.py` | `ChatOpenAI(gpt-6-luna, use_responses_api=True, store=False, include=["reasoning.encrypted_content"])` 생성, 역할별 `prompt_cache_key` `.bind()` |
| `nadri/prompts/answer.md` · `verify.md` | 고정 답변 프롬프트(한국어, 툴 결과로만 관광 사실, 출처 형식, 자료 속 지시 무시, 우선순위 공공데이터 > 웹) · 검증 프롬프트(사실 일치·지어냄, 구조화 출력) |

**핵심 스펙**: FR-10·11·12·13·18(`error` 이벤트)·22·54·90·91(이벤트 순서), NFR-11·12(Moderation 단계만)·13(Moderation·코드 검사)·22·23·30·36·40·42·60(timings), ADR-03·04·11·16·17·18·19·25·26.

**완료 기준**
- 터널 주소로 `curl -N` 시 이벤트가 토큰 단위로 순서대로 도착(버퍼링 없음), 15초 ping 확인.
- `rag_query`·`data_query`를 실제 호출한 답변, 검증 노드 구조화 출력 파싱 성공, contentid·URL 코드 검사 동작.
- 검증 불합격 → 다시 쓰기 → `replaced` 흐름이 실제 호출에서 1회 이상 재현(필요 시 테스트용 질문으로 유도).
- 같은 고정 프리픽스 두 번째 요청에서 `cache_read > 0`(안 되면 [A] A19 대안 기록).
- Moderation 장애 주입(잘못된 키·타임아웃) → `error{guard_unavailable}`.
- timings(`ttft_ms`·`draft_ms`·`tool_ms`·`verify_ms`·`total_ms`)와 호출별 usage가 로그로 나옴(저장은 11).

**검증**
- 단위: 가짜 Chat 모델(툴 호출 → 답변 → 검증 판정)로 이벤트 순서 스냅샷 4종(시도 0 합격 / 다시 쓰기 1회 / 소진-사실 실패 `warning` / 소진-보안 실패 `replaced` 고정 문구), 툴 호출 전 머리말 delta 뒤 `tool` 이벤트, evidence 추출, 코드 검사, Moderation fail-closed(목킹), SSE 직렬화.
- 통합(`integration`): 실 OpenAI·tour-tools·Tavily 각 1회 이상.
- HITL: 사용자가 터널 주소로 스트리밍을 직접 확인(UI 전이라 curl, 모바일 화면 확인은 15), 지연·비용 측정치 보고. 정상 관광 질문·유해 질문 약 10건으로 Moderation 초기 판정 표 작성.

**이 작업에서 검증할 가정**: **A11**(Named Tunnel SSE), **A18**(Responses·store=False·encrypted reasoning 툴 루프·구조화 출력), **A19**(스트리밍 usage·cache_read), **A20**(stream_mode 조합·`langgraph_node`로 답변 토큰 선별), **A22**(초기 표본), **A23**(초기 가용성·지연), **A25**(지연 측정만, 비교는 22), **A26**(긴 툴 결과 검증), **A30**(머리말 delta 정리).
> 이 작업은 하루를 넘을 수 있다. 넘치면 "nginx·cloudflared"를 같은 브랜치 안 두 번째 커밋으로 나눈다(작업 분리는 하지 않음 — 터널 SSE 검증이 슬라이스의 핵심).

---

### 03-ingest-bootstrap — 초기 적재 (서울·제주 × 8종, 이어하기)
**목표**: 개발계정 일일 한도 안에서 여러 날에 나눠 전체 초기 적재를 이어서 완료한다. 슬라이스 직후 시작해 다른 작업과 병행.

**파일**: `nadri/ingest/budget.py`(일 예산 기본 800, `ingest_state`에 날짜별 사용량, 한도 에러코드 22·23이면 그날 중단) · `nadri/ingest/bootstrap.py` 확장(지역×타입 목록 페이지네이션 → "상세 미수집" 큐 → 상세 3종 → raw → upsert → 렌더 → 해시 인덱싱, 커서 이어하기, `ingest_runs` 기록) · `nadri/core/tourapi.py` 확장(타입별 `detailIntro2` 필드 매핑) · `nadri/ingest/wiki/templates/*.md.j2`(8종) · `nadri/cli.py`(`ingest bootstrap` 이어하기).

**핵심 스펙**: FR-40·41·42·44·48, ADR-14, NFR-24. `tour_live`(10)도 같은 TourAPI 한도를 쓰므로 예산 카운터를 공유하는지 §5 Q6.

**완료 기준**: 중단 후 재실행 시 이어서 진행, 예산 초과 없음, 8종 템플릿 렌더, 해시 같은 페이지는 재인덱싱 안 함, 실행마다 `ingest_runs`(건수·호출 수·오류).

**검증**: 단위 — 예산 소진 시 중단, 커서 재개, 에러코드 22 처리, 8종 템플릿 스냅샷. HITL — 첫날 실행 결과(호출 수·건수)와 예상 완료일 보고. 예상 일수가 길면 운영계정 트래픽 증설 신청 여부를 사용자에게 묻는다([S S8]).

**가정**: **A8**(넓은 표본 재확인), **A12**(한도 단위·실제 일수). `usetime` 자유 텍스트 여부 확인([A] §2.1 "추정").

---

### 04-db-schema — 앱 테이블 15개 + ORM
**목표**: ERD 19개 중 01에서 만들지 않은 15개 테이블을 한 마이그레이션으로 만든다.

**파일**: `backend/alembic/versions/0002_app_tables.py`(users, auth_sessions, rate_limits, password_reset_codes, chat_sessions, chat_messages, faq_cache, daily_quota, quota_requests, usage_events, message_feedback, security_events, eval_reports, eval_scores, improvement_proposals + COMMENT) · `nadri/core/models/{account,chat,quota,quality}.py` · `backend/tests/test_schema_comments.py`(`docs/images/src/erd.py`의 `T` 정의를 AST로 읽어 DB COMMENT와 대조).

**핵심 스펙**: [A] §5.1 컬럼·FK 동작(세션 삭제 → 메시지·피드백·FAQ 캐시·eval_scores 연쇄, `usage_events.message_id`·`security_events.*` set null, `improvement_proposals.report_id` **set null** — §5 X-d), `faq_cache.embedding vector(1536)`, `chat_messages`에 원문·좌표 컬럼 없음(NFR-33·35). 한글 명칭은 ERD 정본(§5 X-e).

**완료 기준**: upgrade/downgrade 왕복, 19개 테이블·컬럼 COMMENT = ERD, FK 연쇄 동작 테스트 통과, `nadri_tools` 롤이 새 테이블에 권한 없음.

**검증**: pytest(테스트 DB 컨테이너) — 마이그레이션 왕복, COMMENT 대조, 연쇄 삭제, 권한 확인.

**가정**: 없음.

---

### 05-auth-core — 가입 신청·로그인·세션·CSRF·잠금·관리자 CLI
**목표**: 인증 API 전체(재설정 제외)와 첫 관리자 CLI. 02 슬라이스 채팅 엔드포인트에 활성 사용자 검사를 붙이고, `cloudflared` 프로필을 풀어 상시 기동한다(§5 Q1).

**파일**: `nadri/api/auth/router.py`(`signup`·`login`·`logout`·`password`·`me`) · `service.py`(Argon2id, 10자 이상·흔한 비밀번호 차단) · `sessions.py`(해시 저장, 로그인 시 재발급, 유휴 2시간·절대 7일, `__Host-session` HttpOnly·Secure·SameSite=Lax·Path=/) · `csrf.py`(서명 double-submit, `SESSION_SECRET`) · `nadri/api/ratelimit.py`(`rate_limits` 고정 윈도, 계정·IP별 5회 → 15분 잠금 + 점진 지연, IP는 `X-Real-IP`) · `nadri/api/deps.py`(`current_user`·`require_active`·`require_admin`) · `nadri/core/data/common_passwords.txt`(출처 §5 Q7) · `nadri/cli.py`(`nadri create-admin`) · `compose.yaml`(cloudflared 프로필 제거, `SESSION_SECRET`).

**핵심 스펙**: FR-01·02·03·04(API)·06·80(CLI), NFR-01~05·06(로그인)·10·34, ADR-10·15. 실패 문구 통일, `pending`은 로그인되나 채팅 403, `rejected`·`disabled`는 일반 실패 문구.

**완료 기준**: 위 동작 전부 테스트 통과, CSRF 없는 상태 변경 요청 403, 비밀번호 변경 시 다른 세션 폐기, 터널 주소에서 로그인 쿠키 동작.

**검증**: pytest + httpx AsyncClient + 테스트 DB(잠금·만료는 시계 주입). HITL — 터널 주소와 `localhost`에서 브라우저 쿠키 확인.

**가정**: **A17**(localhost `__Host-` 쿠키).

---

### 06-password-reset-mail — 이메일 인증코드 비밀번호 재설정
**파일**: `nadri/api/mail.py`(Gmail SMTP 앱 비밀번호, 백그라운드 발송, 실패는 로그만) · `nadri/api/auth/reset.py`(`password-reset/request`·`confirm`) · `.env.example`(`SMTP_USER`·`SMTP_APP_PASSWORD`·`MAIL_FROM`).

**핵심 스펙**: FR-05·07, NFR-03·06(재설정 제한). 6자리 코드 해시 저장, 10분·5회, 미등록 이메일도 같은 응답, 성공 시 전 세션 폐기·코드 소모. 활성 사용자에게만 발송.

**완료 기준·검증**: SMTP 목킹 단위테스트(만료·횟수·문구 통일·세션 폐기). HITL — 사용자가 `.env`에 Gmail 정보를 넣은 뒤 실제 메일 1회 수신 확인.

**가정**: 없음(Gmail 일일 발송 한도는 [S S7] 미확인 — 데모 규모라 기록만).

---

### 07-guard-pii — 개인정보 가리기 규칙
**파일**: `nadri/guard/pii.py`(주민·외국인등록번호: 생년월일 유효 + 성별 자리 1~8 패턴, 검증번호 미사용 / 전화 휴대폰·유선·070·080 / 이메일 / 카드 Luhn / 여권·운전면허 / 계좌는 "계좌" 등 문맥 단어 근처 / 이름은 "제 이름은 ○○○" 류 문맥 패턴 / 주소 안 가림. 형식 유지 + `*` — `010-****-****`, `******-*******`, `****@gmail.com`, `***`. 반환: 가린 텍스트 + 종류 목록) · `backend/tests/guard/test_pii_table.py`.

**핵심 스펙**: NFR-35, ADR-21, G3 재검토 Q3·Q4, [SG] §3 가리는 개인정보 표.

**완료 기준**: 표 테스트 — 가려야 하는 입력 전부 가림, 가리면 안 되는 입력(contentid·요금 숫자·날짜·시간·주소·관광지명) 무변화. 멱등(두 번 가려도 같음 — 24 익명화에서 재사용).

**검증**: pytest 파라미터화 표. HITL — 표의 "가리면 안 되는 입력" 목록을 사용자와 확인.
> 확인 필요: 사용자가 질문에 관광지 대표 전화(예: `064-xxx-xxxx`)를 직접 쓰면 입력 규칙상 가려진다(ADR-21은 출력에만 예외). spec에서 이 동작을 명시한다.

**가정**: **A27**(관광 질문 오탐), **A29**(공식 자료 확인 결과만 기록 — 판정 규칙은 G3 Q3로 이미 결정).

---

### 08-guard-pipeline — 입력 검사 3단·출력 검사·보안 이벤트
**목표**: 5겹 중 1(입력)·4(출력) 겹을 완성하고 채팅 흐름에 연결한다.

**파일**: `nadri/guard/input_guard.py`(① PII 가리기 → ② Moderation → ③ 분류기, 앞 단계 통과해야 다음, 원문은 이 함수 밖으로 나가지 않음) · `classifier.py`(가린 이번 질문 + 직전 1턴 발췌 → `normal|jailbreak|injection|off_topic`, 구조화 출력, `prompt_cache_key=nadri-classify-v1`) · `events.py`(`security_events` 기록 — 가린 발췌 300자 이하, 원문 없음) · `output_guard.py` 확장(카나리 문자열 검사, 저장용 허용 안 된 링크 텍스트 강등 함수) · `nadri/prompts/classify.md` · `nadri/prompts/fixed_messages.toml`(차단 코드별 안내, 자해 109 안내, 보안 실패 고정 안전 문구, `unverified` 경고 — 문구는 spec에서) · `answer.md`(카나리·비밀값 없음 확인)·`verify.md`(보안 항목: 프롬프트 유출·개인정보·범위 이탈·허용 안 된 링크) 보강 · `nadri/agent/nodes.py`(보안 실패 소진 → `replaced` 고정 문구 + 이벤트) · `nadri/api/chat/router.py`(입력 검사 연결, `meta{user_text_masked, masked_types}`, `blocked`, `done{blocked:true}`).

**핵심 스펙**: NFR-11~16·35, FR-90(보안 항목), ADR-18·20·21·22·27. 차단 턴은 대화 미저장(ADR-27). 한도 차감은 11에서 연결.

**완료 기준**: Moderation·분류기 목이 **가린 텍스트만** 받는지 검증, Moderation 실패 → 차단, self-harm 계열 → 109 안내(`self_harm`), 분류기 라벨별 `blocked`, 보안 이벤트에 원문 없음, 카나리 포함 답변 → 고정 안전 문구.

**검증**: pytest 목킹(순서·fail-closed·이벤트 내용). HITL — 109 안내 문구를 공식 출처로 확인(NFR-15), 대표 공격 10건·정상 질문 20건 수동 실행 결과 보고.

**가정**: **A22**, **A23**(재시도 1회 후 차단 정책 유지 여부), **A24**(초기 오탐 표본 — 본 측정은 22).

---

### 09-chat-sessions — 대화 세션·컨텍스트·저장·제목/요약
**파일**: `nadri/api/chat/router.py`(GET/POST `/api/chat/sessions`, GET/DELETE `/api/chat/sessions/{id}`, 메시지 엔드포인트 본 구현 — 본인 세션 확인·`turn_count<50` 아니면 409 `session_full`) · `context.py`(고정부 → `<이전 대화 요약>` 자료 블록 → 최근 10턴 → 이번 질문 + 동의 시 "현재 위치" — 좌표 미저장) · `store.py`(성공 시 한 트랜잭션: user(가린 텍스트·`pii_types`)·assistant(최종본·허용 안 된 링크 강등·`tool_results` 툴당 2,000자·합계 10,000자·`verification`·`verify_status`·`rewrite_count`·`timings`)·`turn_count+1`) · `background.py`(첫 턴 제목, `turn_count>10`이면 누적 요약 — 그래프 밖 단발 `ChatOpenAI`, 낮은 reasoning effort) · `nadri/prompts/{title,summary}.md`.

**핵심 스펙**: FR-06·10·14·15·16·17·20·55(백엔드)·104, D-10, NFR-30·33·35·60, ADR-03·16. 실패·검증 불가·브라우저 연결 끊김(그래프 태스크 취소) → 미저장.

**완료 기준**: 위 규칙 테스트 통과, 타인 세션 접근 404, 세션 삭제 시 메시지 연쇄 삭제, 좌표가 DB·로그에 남지 않음(로그 캡처 검사).

**검증**: pytest(가짜 그래프·LLM). HITL — 실제로 12턴 이상 대화해 요약이 컨텍스트에 들어가는지 확인.

**가정**: 없음(A19 결과에 따라 요약 비용 기록 방식만 반영).

---

### 10-tool-tour-live — `tour_live` 툴
**파일**: `nadri/tools/tour_live.py`(`searchFestival2` 진행 중 축제 / `locationBasedList2` 좌표 주변, 결과 `source=실시간 조회`) · `nadri/tools/server.py` 등록 · `nadri/core/tourapi.py` 확장 · `nadri/agent/tools.py`(라벨 "실시간 정보 확인 중").

**핵심 스펙**: FR-52·55, NFR-07, ADR-08. TourAPI·네트워크 오류는 툴 결과 오류로 LLM에 돌려줌([A] §3.1 실패 처리). 예산 공유는 §5 Q6.

**완료 기준·검증**: TourAPI 목킹 단위테스트(오퍼레이션·파라미터·오류 변환), 통합 1회("오늘 서울에서 하는 축제"). 결과에 `contentid`·`as_of`.

**가정**: 없음.

---

### 11-quota-usage — 일일 한도·분당 제한·사용량 기록
**파일**: `nadri/api/quota.py`(오늘 KST `used < 50 + extra` 아니면 429 `quota_exceeded`, `POST /api/quota/requests` — 그날 1건) · `nadri/api/usage.py`(호출별 `usage_events`: `answer`·`verify`·`classify`·`moderation`(건수)·`title`·`summary`·`embed`·`web_search`(크레딧)·`hub`·`eval`·`proposal`, 입력·캐시 읽기·캐시 쓰기·출력 토큰, 응답 모델명, 비용) · `nadri/core/pricing.py`(gpt-6-luna 입력 0.10·캐시 0.01·캐시 쓰기 0.125·출력 0.50 /1M, 임베딩 0.02, STT $0.0045/분) · `nadri/api/chat/router.py`(분당 10회 429, 차감 규칙 연결).

**핵심 스펙**: FR-61·62, NFR-06(채팅)·40(cached_tokens 기록)·43·60, ADR-27·[A] §3.6 — 성공·캐시 적중 +1, 입력 검사 차단 +1, 장애·중단·Moderation 장애 차단 미차감. `done.quota_remaining`.

**완료 기준·검증**: pytest — 한도 경계(50·추가분), KST 날짜 경계, 차감 규칙 표 테스트, 비용 계산(캐시 쓰기 1.25배), 분당 10회.

**가정**: A19 결과 반영(usage 수집 위치).

---

### 12-faq-cache — FAQ 유사도 캐시
**파일**: `nadri/api/faq_cache.py`(조회: 세션 첫 질문 && 위치 없음 → 가린 질문 임베딩 → 코사인 ≥ 0.95(설정값) → 캐시 답변을 delta로 흘리고 `verified` / 저장: `verify_status=passed` && 툴 결과에 `web_search`·`get_datetime`·`tour_live` 없음 && 근거 contentid ≥ 1 / `invalidate_by_contentids()` — 21에서 사용) · `nadri/core/llm.py`(`OpenAIEmbeddings`) · `nadri/api/chat/router.py` 연결(`from_cache`·`faq_cache_id`·`verify_status=cached`, 한도 +1).

**핵심 스펙**: FR-60·92, ADR-13, NFR-35(가린 텍스트 임베딩). 임베딩 실패 → 캐시 건너뛰고 정상 진행([A] §4).

**완료 기준·검증**: pytest — 저장 조건 표, 임계값 경계, 무효화, 임베딩 실패 시 우회. 적중 시 SSE 이벤트 순서 스냅샷.

**가정**: 없음(임계값은 22 평가로 조정).

---

### 13-feedback — 👍/👎 피드백 API
**파일**: `nadri/api/feedback.py`(`PUT·DELETE /api/chat/messages/{id}/feedback`, 본인 assistant 메시지 확인, 메시지당 1개 upsert, 사유 `wrong|outdated|misunderstood|other|null`, 👎이면 `source_message_id=id` 또는 그 메시지의 `faq_cache_id` 캐시 행 삭제) · 세션 조회 응답에 내 피드백 포함.

**핵심 스펙**: FR-103(백엔드), [A] §3.9.

**완료 기준·검증**: pytest — 권한, upsert·취소, 👎 시 캐시 삭제(원 메시지·캐시 적중 메시지 두 경우).

**가정**: 없음.

---

### 14-web-foundation — Next.js 기반·인증 화면·PWA
**파일**: `web/package.json`(Next.js 16·React 19·Tailwind 4·shadcn/ui·react-markdown·remark-gfm 고정), `next.config.ts`(standalone), `Dockerfile`(비루트), `vitest.config.ts`, `playwright.config.ts` · `web/app/layout.tsx` · `web/app/(auth)/{login,signup,pending,reset}/page.tsx`(가입·재설정 화면에 비밀번호 규칙 "10자 이상, 흔한 비밀번호 사용 불가"를 미리 표시하고 거절 시 같은 문구로 이유 표시 — §5 Q7) · `web/app/(chat)/account/page.tsx`(비밀번호 변경, 같은 규칙 표시) · `web/lib/api.ts`(같은 출처 fetch, CSRF 쿠키 → `X-CSRF-Token`, 토큰을 localStorage에 두지 않음) · `web/app/manifest.ts`, `web/public/icons/`, `web/public/sw.js`(최소, `/api/*` 가로채지 않음, 오프라인 캐시 없음), `web/components/RegisterSW.tsx` · `compose.yaml`(web)·`infra/nginx/nginx.conf`(`/`·`/admin` → web).

**핵심 스펙**: FR-01~05 화면, NFR-04·05·10·52, ADR-12(데이터는 브라우저에서만 `/api` 호출), [S S16~S19].

**완료 기준**: 가입 신청 → (DB에서 수동 승인) → 로그인 → 승인 대기/채팅 진입 분기, 재설정 흐름, 설치 가능 PWA.

**검증**: Vitest(api 클라이언트 CSRF 헤더, 폼 검증), Playwright(로그인·가입·재설정 화면 — API는 실제 compose). HITL — Android Chrome "앱 설치", iOS Safari "홈 화면에 추가" 전체화면 실행 확인.
> 하루를 넘을 수 있다.

**가정**: 없음([S S17] Android 설치 조건은 HITL로 확인).

---

### 15-web-chat — 채팅 화면·SSE 파서·안전 렌더러
**파일**: `web/lib/sse.ts`(fetch + ReadableStream, [A] §3.1 이벤트 전체, ping 무시) · `web/components/chat/ChatView.tsx`(상태 기계: checking → answering → 초안 → verifying/revising → ✓ 확인됨 / 교체 / 경고 / 차단 / 오류 + 재시도) · `MessageBubble.tsx` · `SafeMarkdown.tsx`(raw HTML 끔, `img` 렌더 안 함, 링크는 `done.allowed_urls`에 있고 `done` 이후만 클릭, 그 외 텍스트) · `Sidebar.tsx`(세션 목록·제목·새 대화·삭제) · `StatusLine.tsx` · `web/app/(chat)/page.tsx`, `[sessionId]/page.tsx`.

**핵심 스펙**: FR-10·15(새 대화 안내)·16·17·18·20·21·91, NFR-14·23, ADR-19·22. `tool` 이벤트 받으면 표시 중 delta 지움. `meta`로 사용자 말풍선을 가린 텍스트로 교체.

**완료 기준·검증**: Vitest — 파서(청크 경계 분할·ping·여러 이벤트), 렌더러(HTML·이미지·허용 안 된 링크·초안 단계 링크 비활성), 상태 전이. Playwright — 가짜 SSE 응답(route mock)으로 시나리오 4종 + 실제 compose 1회. HITL — **모바일 브라우저(터널 주소)에서 토큰 단위 표시** 확인.

**가정**: **A11**(모바일 화면 확인 마무리), **A30**(화면 일관성).

---

### 16-web-chat-actions — 피드백·한도 추가 요청·위치 동의 UI
**파일**: `web/components/chat/FeedbackButtons.tsx`(👍/👎, 👎 사유 선택 — 선택 입력) · `QuotaRequestButton.tsx`(429 `quota_exceeded` 시 "추가 요청", 요청 후 대기 표시) · `LocationToggle.tsx`(동의 시에만 `navigator.geolocation`으로 그 질문에 좌표 첨부, 저장 안 함).

**핵심 스펙**: FR-55·62(화면)·103(화면), NFR-33.

**완료 기준·검증**: Vitest(컴포넌트 상태), Playwright(피드백 변경·취소, 한도 초과 화면, 위치 거부 시 좌표 미전송 — 요청 본문 검사).

**가정**: 없음.

---

### 17-voice — STT·TTS (Provider 인터페이스)
**파일**: `nadri/api/voice/stt/base.py`(`SttProvider` Protocol — [TECH_STACK §8.1] 시그니처) · `stt/openai.py`(`gpt-transcribe`, `language=ko`) · `tts/base.py`(`TtsProvider`) · `tts/elevenlabs.py`(`eleven_flash_v2_5`, `ELEVENLABS_VOICE_ID` 고정) · `voice/router.py`(`POST /api/stt` multipart·MIME·10MB 재검사·분당 제한 / `POST /api/tts {message_id}` 본인 assistant 최종본만, 마크다운·링크 제거, 1,500자 상한, `audio/mpeg` 중계, `usage_events` stt·tts) · `STT_PROVIDER`·`TTS_PROVIDER` 설정으로 선택 · `web/lib/recorder.ts`(MediaRecorder, `webm/opus`·`mp4/aac` 선택, 60초 자동 종료) · `web/components/chat/{PttButton,SpeakerButton}.tsx`(전사 텍스트를 입력창에 채움 → 사용자 수정 후 전송).

**핵심 스펙**: FR-30·31·32, NFR-06(STT)·43·50·51, [S S2·S20]. `faster_whisper`·Drama 3 구현체는 만들지 않음(인터페이스만, [R] §5).

**완료 기준·검증**: pytest(Provider 선택, 크기·MIME 거부, 타인 메시지 TTS 거부, 목킹), Vitest(녹음기 상태·60초), Playwright(Chromium 가짜 마이크 파일 주입). HITL — Chrome(webm)·iOS Safari PWA(mp4) 실제 전사, TTS 재생.

**가정**: **A13**(두 포맷 전사, iOS PWA 마이크 — 실패 시 ffmpeg 변환은 사용자 확인 후).

---

### 18-admin-users-quota — 관리자: 가입·한도 승인·비활성화
**파일**: `nadri/api/admin/router.py`(`require_admin`) · `users.py`(`GET /api/admin/users?status=`, approve·reject·disable — disable 시 `auth_sessions` 전부 삭제) · `quota_requests.py`(목록·approve(+50 그날만)·reject) · `web/app/admin/layout.tsx`(관리자만, 서버 판단은 api) · `users/page.tsx` · `quota/page.tsx`.

**핵심 스펙**: FR-04·80·81·82·84, [A] §3.4·§3.6. 승인 결과 메일·재활성화 버튼 없음([A] §13).

**완료 기준·검증**: pytest(일반 사용자 403, 상태 전이, 비활성화 즉시 채팅 차단), Playwright(승인 → 그 사용자 로그인 → 채팅 가능).

**가정**: 없음.

---

### 19-admin-usage — 관리자: 사용량 대시보드
**파일**: `nadri/api/admin/usage.py`(`GET /api/admin/usage?from=&to=` — 사용자·일자·kind별 토큰·비용, Moderation 건수, Tavily 크레딧, ElevenLabs 글자 수, 월 누적, $10 초과 경고 플래그 — 차단 없음) · `web/app/admin/usage/page.tsx`("앱 기록 기준 추정" 표기 — LightRAG 내부 호출 미포함).

**핵심 스펙**: FR-63·83, NFR-43, [A] §10.

**완료 기준·검증**: pytest(집계·KST 월 경계·경고 임계), Playwright(화면 표시). HITL — OpenAI 대시보드 금액과 대조해 차이 기록.

**가정**: **A14**(LightRAG 사용량 집계 불가 확인 → "추정" 표기), **A28**(Tavily 월 1,000크레딧 내 사용 추이).

---

### 20-ingest-hubs-lint — 허브 페이지·lint·위키 git
**파일**: `nadri/ingest/wiki/hubs.py`(시군구 허브 27개를 `ChatOpenAI`로 작성, 인덱싱, `usage_events kind=hub`) · `nadri/prompts/hub.md` · `wiki/lint.py`(깨진 링크·기준일 경과·모순 → `ingest_runs.lint`) · `wiki/git.py`(`wiki-data` 볼륨 안 git 커밋) · `backend/Dockerfile`(app 타깃에 git) · `nadri/cli.py`(`ingest hubs [--sigungu]` — 초기 허브 생성·재실행), bootstrap 완료 시 허브 생성 호출.

**핵심 스펙**: FR-43·46·47, NFR-24, G3 Q4(허브 27개). "모순" 탐지는 코드 규칙만(§5 Q4 결정): 위키 페이지의 휴무일·주소·전화 등 핵심 필드 ↔ 원본 `tour_items` 대조, 허브가 삭제된 contentid를 가리키는지 확인. LLM 미사용.

**완료 기준·검증**: pytest(lint 규칙 표, git 커밋 — 임시 저장소, 허브 프롬프트 입력 조립·LLM 목킹). HITL — 허브 2~3개 샘플 품질 확인, 27개 생성 비용 기록.

**가정**: 없음.

---

### 21-ingest-daily-sync — 매일 01:00 현행화·90일 정리
**파일**: `nadri/ingest/scheduler.py`(APScheduler, `Asia/Seoul`, 상주 — compose `ingest` 서비스 기본 명령) · `nadri/ingest/jobs/daily_sync.py`([A] §3.3 1~10 순서, advisory lock 키 1) · `nadri/ingest/sync.py`(`areaBasedSyncList2` 마지막 성공 이후 → 변경분 상세 재수집, 삭제분 `deleted_at`·위키·LightRAG·`wiki_pages` 삭제, 영향 허브만 재작성, FAQ 무효화) · `nadri/ingest/cleanup.py`(90일: `chat_sessions`(연쇄), `security_events`, `eval_reports`(→ 미결정 개선안 삭제, 채택·보류는 evidence만 비움), 만료 `auth_sessions`·재설정 코드·오래된 `rate_limits`) · `nadri/cli.py`(`ingest sync --now`).

**핵심 스펙**: FR-45, NFR-31, ADR-09·13.

**완료 기준·검증**: pytest(lock 중복 실행 건너뜀, 변경·삭제 처리, 정리 규칙 표 — 시계 주입). HITL — `ingest sync --now` 실행 결과(변경 건수·호출 수) 확인, 다음 날 01:00 자동 실행 로그 확인.

**가정**: **A12**(SyncList 파라미터·응답 — 실제 호출로 마무리).

---

### 22-eval-golden — 골든 Q&A 평가
**파일**: `eval/golden/golden.jsonl`(질문·정답·근거 contentid — 관광 사실·조건·주변·축제·웹 필요 질문 + 스몰토크·상식·후속 질문 묶음(분류기 오탐 측정용); 작성 방식 §5 Q5) · `eval/README.md`(형식·판정 규칙) · `nadri/eval/golden.py`(guard + 그래프를 같은 코드로 프로세스 안 실행, FAQ 캐시 우회, 정답률·근거 일치율·첫 토큰 지연·토큰·비용·입력 검사 오탐률·검증 오판 집계) · `nadri/cli.py`(`eval golden --rerank on|off --verify-max 0|1|2 --rag-mode mix|hybrid`) · `nadri/tools/rag_query.py`·`nadri/core/config.py`(리랭커 on/off·LightRAG 모드 설정값 — 평가 비교용).

**핵심 스펙**: FR-70(골든 부분). 임베딩 모델 비교(bge-m3)는 §5 Q3. 목표 수치는 정하지 않고 측정·기록만([R] 목표 6).

**완료 기준·검증**: pytest(채점 함수·집계, 가짜 그래프). HITL — 비교 결과표를 사용자에게 보고하고 `VERIFY_MAX_REWRITES`·질의 모드·FAQ 임계값 결정을 받는다(설정값만 변경).

**가정**: **A10**(mix ≥ hybrid), **A22**(정상 질문 오탐률), **A24**(분류기 오탐 — 높으면 "off_topic 안내형 완화"는 사용자 확인), **A25**(검증 0/1/2 정확도·지연·비용).

---

### 23-eval-attack-set — 공격 질문 세트
**파일**: `eval/attack_set/attacks.jsonl`(탈옥·직접/간접 인젝션·프롬프트 유출·링크/이미지 유출·PII·유해·자해·범위 이탈, 한국어 포함, 약 60건, 항목별 기대 결과) · `nadri/eval/attack.py`(실제 `input_guard` + 그래프 실행, 웹 툴은 항목의 "오염된 결과"를 돌려주는 고정 가짜 툴로 교체(Tavily 비용 없음), 판정은 코드 우선 — 차단 여부·카나리 미노출·허용 안 된 URL 없음·PII 가려짐, 애매한 것만 LLM 판정 → 유형별 방어율·실패 id) · `nadri/cli.py`(`eval attack`).

**핵심 스펙**: NFR-16, FR-70(방어율)·105(재료), [SG] §4.1~4.2, [A] §3.7 5).

**완료 기준·검증**: pytest(판정 함수, 가짜 웹 툴 주입). HITL — 첫 실행 방어율 보고, 실패 케이스를 사용자와 검토(방어 보완은 별도 결정).

**가정**: A22(유해 탐지율 측정 마무리).

---

### 24-eval-daily-quality — 매일 03:00 평가·개선안 에이전트
**파일**: `nadri/eval/anonymize.py`(user_id → "사용자 A" 별칭, 대응표 미저장, session_id 제거, PII 가리기 재적용) · `nadri/eval/quality.py`(전날 KST 수집 → 평가 에이전트(툴 없음, 구조화 출력, 👎 우선, 상한 `EVAL_MAX_ITEMS=200`) → `eval_scores`, 코드 집계(검증 통과율·다시 쓰기 분포·지연 p50/p95·비용·피드백·👍/👎와 점수 일치율·보안 이벤트 요약·공격 세트 방어율) + 요약문 → `eval_reports`) · `nadri/eval/proposals.py`(보고서 + 현재 설정 스냅샷(`prompts/*`·툴 설명·리랭커·검증·FAQ 임계값·데이터 범위) → `improvement_proposals(status=new)`) · `nadri/ingest/jobs/daily_quality.py`(advisory lock 키 2, 같은 날짜 완료본 있으면 건너뜀, 대화 0건이면 채점·개선안 건너뛰고 공격 세트만, 실패 시 `failed`+error, 자동 재시도 없음) · `nadri/prompts/{evaluate,propose}.md` · `nadri/ingest/scheduler.py`(03:00 등록) · `nadri/cli.py`(`eval quality --date YYYY-MM-DD`) · compose(ingest에 `./eval:/app/eval:ro`).

**핵심 스펙**: FR-100·101·104(활용)·105, NFR-36, ADR-09·23. 채점 기준·강도는 Phase 4 spec에서 정한다([R] FR-100). 코드·프롬프트·설정 자동 변경 경로 없음.

**완료 기준·검증**: pytest(익명화 — 원 user_id·session_id 미포함, 건너뜀 조건, 상태 전이, 집계 계산, LLM 목킹). HITL — 실제 하루치 보고서·개선안을 사용자가 읽고 채점 기준 적절성 판단.

**가정**: 없음(평가 비용은 [A] §10 추정과 대조해 기록).

---

### 25-admin-quality-hitl — 관리자: 품질 리포트·개선안 결정
**파일**: `nadri/api/admin/quality.py`(`GET /api/admin/quality/reports?from=&to=`, `GET …/reports/{id}`(본문·집계·공격 세트 결과·개선안), `GET …/proposals?status=`, `POST …/proposals/{id}/decision {status: adopted|held|rejected, note}` → `decided_by`·`decided_at`) · `web/app/admin/quality/page.tsx`(목록) · `[reportId]/page.tsx`(보고서·개선안 결정) · `proposals/page.tsx`(채택 = 개발 후보 목록).

**핵심 스펙**: FR-102, ADR-23. 보안 이벤트 전용 화면 없음([A] §13).

**완료 기준·검증**: pytest(권한·결정 전이·메모), Playwright(개선안 채택 → 개발 후보 목록에 표시).

**가정**: 없음.

---

### 26-release-readiness — 릴리스 준비 점검
**파일**: `backend/tests/test_compose_hardening.py`(compose.yaml 파싱 — 자체 이미지 비루트·`cap_drop: [ALL]`·`no-new-privileges`·docker.sock 미마운트, nginx 외 호스트 포트 없음(dev 덮어쓰기 제외), 서비스별 비밀값 주입이 [A] §9 표와 일치, `LANGSMITH_*` 키 미주입·추적 끔) · `compose.yaml`·`.env.example` 최종 정리 · `README.md`(시작하기·상태 갱신, "MVP 이후" → "v1.1 이후" 표기 — §5 X-f, SECURITY_GUIDE 링크 확인) · `CLAUDE.md`(명령어 절 최종).

**핵심 스펙**: NFR-08·09·17·20·21, ADR-01·26.

**완료 기준·검증**: 위 테스트 통과, 빈 볼륨에서 `compose up` → 마이그레이션 → `create-admin` → `ingest bootstrap --limit` → 채팅 1회가 문서대로 재현(HITL). 이후 Phase 6 E2E 설계(NFR-71 전체 시나리오).

**가정**: 없음.

---

## 4. 요구사항 추적표

### 4.1 기능 요구사항
| ID | 작업 | ID | 작업 |
|---|---|---|---|
| FR-01 | 05, 14 | FR-40 | 01, 03 |
| FR-02 | 05, 14 | FR-41 | 01, 03 |
| FR-03 | 05, 14 | FR-42 | 01, 03 |
| FR-04 | 05, 14, 18 | FR-43 | 20 |
| FR-05 | 06, 14 | FR-44 | 01, 03 |
| FR-06 | 05, 09 | FR-45 | 21 |
| FR-07 | 06 | FR-46 | 20 |
| FR-10 | 02, 09, 15 | FR-47 | 20 |
| FR-11 | 02, 10 | FR-48 | 03 |
| FR-12 | 02, 08, 09 | FR-49 | **범위 밖 (v1.1 이후)** — 확장 지점은 [A] §2·§4 서술만, 작업 없음 |
| FR-13 | 02 | FR-50 | 01 |
| FR-14 | 09 | FR-51 | 01 |
| FR-15 | 09, 15 | FR-52 | 10 |
| FR-16 | 09, 15 | FR-53 | 01 |
| FR-17 | 09, 15 | FR-54 | 02 |
| FR-18 | 02, 15 | FR-55 | 09, 10, 16 |
| FR-19 | 01 | FR-60 | 12 |
| FR-20 | 09, 15 | FR-61 | 11 |
| FR-21 | 15 | FR-62 | 11, 16, 18 |
| FR-22 | 02 | FR-63 | 19 |
| FR-30 | 17 | FR-70 | 22, 23 |
| FR-31 | 17 | FR-71 | **삭제됨 (2026-11-21)** |
| FR-32 | 17 | FR-80 | 05(CLI), 18 |
| FR-90 | 02, 08 | FR-81 | 18 |
| FR-91 | 02, 15 | FR-82 | 18 |
| FR-92 | 12 | FR-83 | 19 |
| FR-100 | 24 | FR-84 | 18 |
| FR-101 | 24 | FR-103 | 13, 16 |
| FR-102 | 25 | FR-104 | 09, 24 |
| FR-105 | 23, 24 | | |

### 4.2 비기능 요구사항
| ID | 작업 | ID | 작업 |
|---|---|---|---|
| NFR-01 | 05 | NFR-30 | 02, 09 |
| NFR-02 | 05 | NFR-31 | 21 |
| NFR-03 | 05, 06 | NFR-32 | 01 (임베딩 고정·변경 시 재인덱싱 — 22 Q3와 연관) |
| NFR-04 | 05, 14 | NFR-33 | 09, 16 |
| NFR-05 | 05, 14 | NFR-34 | 05 |
| NFR-06 | 05(로그인), 06(재설정), 11(채팅), 17(STT) | NFR-35 | 07, 08, 09 |
| NFR-07 | 01, 02, 10 | NFR-36 | 02, 24, 26 |
| NFR-08 | 01, 02, 26 | NFR-40 | 02, 11 |
| NFR-09 | 01~26 공통, 26 점검 | NFR-41 | 공통 (모든 LLM 호출 `gpt-6-luna`, `core/llm.py` 02) |
| NFR-10 | 02, 14 | NFR-42 | 02 (fallback 코드 없음 — 준수 확인) |
| NFR-11 | 02, 08 | NFR-43 | 11, 17, 19 |
| NFR-12 | 02(Moderation), 08 | NFR-50 | 17 |
| NFR-13 | 02, 08 | NFR-51 | 17 |
| NFR-14 | 08(저장 강등), 15(렌더러) | NFR-52 | 14 |
| NFR-15 | 08 | NFR-60 | 02, 09, 11 |
| NFR-16 | 08, 23 | NFR-61 | 설계 전제 (작업 없음) |
| NFR-17 | 이미 충족(`SECURITY_GUIDE.md` 존재·README 링크) — 26에서 링크 확인 | NFR-70 | 전 작업 |
| NFR-20 | 01, 02, 14, 26 | NFR-71 | 15·16·17·18·25의 Playwright 부분 + **Phase 6 E2E 설계** |
| NFR-21 | 26 | NFR-72 | 전 작업 |
| NFR-22 | 02 | NFR-73 | 전 작업 (커밋) |
| NFR-23 | 02, 15 | NFR-74 | 전 작업 (게이트·브랜치) |
| NFR-24 | 01, 03, 20 | | |

### 4.3 범위 밖 (작업 없음, [R] §5·[A] §13)
FR-49 확장 원천 4곳, `stt-gpu`/faster-whisper·Drama 3 구현(인터페이스만 17), 소셜 로그인, 네이티브 앱, 메신저, 로컬 LLM·fallback·클라우드, 개선안 자동 적용, LangSmith 등 외부 관측, 감독자형 멀티 에이전트·로컬 NER, 보안 이벤트 전용 화면, lint 리포트 화면, 승인 메일·재활성화 버튼, 서비스워커 오프라인 캐시, 답변 이미지, 다국어, Tavily extract, 지연 최적화(D-24), 서울·제주 외 지역.

### 4.4 미검증 가정 → 작업
| 가정 | 작업 | 가정 | 작업 |
|---|---|---|---|
| A7 | 01 | A20 | 02 |
| A8 | 01, 03 | A21 | 01 (02에서 api 쪽 재확인) |
| A9 | 01 | A22 | 02, 08, 22, 23 |
| A10 | 22 | A23 | 02, 08 |
| A11 | 02 (터널 SSE), 15 (모바일 화면) | A24 | 08, 22 |
| A12 | 01, 03, 21 | A25 | 02 (지연), 22 (비교) |
| A13 | 17 | A26 | 02 |
| A14 | 19 | A27 | 07 |
| A16 | 01 | A28 | 19 |
| A17 | 05 | A29 | 07 |
| A18 | 02 | A30 | 02, 15 |
| A19 | 02, 11 | A1~A6·A15 | 해당 없음([A] §12.2) |

---

## 5. 문서 간 상충 · 사용자 확인 필요

### 5.1 발견한 상충 (삭제하지 않고 기록)
| ID | 내용 | 출처 A | 출처 B | 처리 제안 |
|---|---|---|---|---|
| X-a | 산출물 요약이 옛 수치 | [PG] 산출물 줄: "컨테이너 9개 … ADR-01~16 … A1~A17" | [A] 2026-11-21: 컨테이너 8개, ADR-01~27, A1~A30 | [A] 기준. G4 승인 시 PROGRESS.md 갱신 때 함께 고침 |
| X-b | 아키텍처 승인 상태 표기 | [A] 머리말 "재작성 (…승인 대기)" | [PG] "G3 재승인 2026-11-21" | [PG] 기준(재승인). [A] 머리말 문구 갱신 필요 — 확인 필요 |
| X-c | DB 초기화 파일 형식 | [A] §5.1·§7 `infra/postgres/init/01-init.sql` | 롤 비밀번호를 `.env`에서 읽어야 함(NFR-09) — `.sql`은 환경변수 치환 불가 | 01에서 `01-init.sh`(psql 호출)로 만든다 — **확인 필요**(Q8) |
| X-d | `improvement_proposals.report_id` FK 동작 | [A] §5.1 컬럼 설명 "fk cascade — 미결정분만" | 같은 표 비고 "fk **set null**로 두고 90일 정리 때 new·rejected 삭제" | 비고(set null + 정리 코드) 기준으로 04·21 구현 — 확인 필요 |
| X-e | 테이블 한글 명칭 | [A] §5.1 (예: `daily_quota` "일일 사용 한도", `tour_items` "관광 항목") | [E] `erd.py` ("일일 사용량", "관광 정보") | [A]가 "다르면 ERD를 따른다"고 명시 → ERD 기준 |
| X-f | 버전 표기 | [README] "MVP 이후", 상태 "G3 재검토 중" | [R] D-23 "v1.1 이후", [PG] G3 재승인 | 26에서 README 갱신(G4 승인 직후 상태 줄만 먼저 고쳐도 됨) |
| X-g | 대화 메시지 컬럼 | [TECH_STACK] §6 `chat_messages(… tool_trace, tokens …)` 초안 | [A] §5.1 `tool_results` 등 | [A] 기준(초안 표기) |
| X-h | 첫 작업 검증 범위 | [A] §12 본문 "첫 작업에서 A7·A9·A16·A18~A26·A30" | [A] §12.2 표: A24·A25 "평가 작업", A8 "첫 작업", A11 "인프라 작업" | 표 + 요청(터널 SSE를 슬라이스에서) 기준으로 배정(§4.4). A24·A25는 02에서 초기 측정, 판정은 22 |
| X-i | 커밋 공동작성 표기 | 하네스·도구 기본 attribution(Co-Authored-By) | [R] NFR-73·사용자 메모리: AI 공동작성 표기 없음 | 사용자 규칙 우선 — 구현 커밋에 넣지 않음 |

### 5.2 사용자 확인 질문
| # | 질문 | 추천안 | 대안 | 결정 (2026-11-21) |
|---|---|---|---|---|
| Q1 | 02에서 인증 없는 슬라이스 채팅 엔드포인트가 생긴다. 터널로 노출되면 OpenAI 비용 위험 | **05 병합 전까지 `cloudflared`를 compose `tunnel` 프로필로 두고 SSE 검증할 때만 잠깐 기동**, 05에서 `require_active` 연결 후 상시 기동 | B: 05(인증)를 02보다 먼저(슬라이스 지연) / C: Cloudflare Access로 터널 앞단 보호(설정 추가) | 추천안 |
| Q2 | 01·02 시작 전 준비물: `.dev` 도메인 + Named Tunnel 토큰, TourAPI 인증키, OpenAI 키, Tavily 키. 01 시작 시점에 준비됐나? | 01은 TourAPI·OpenAI 키만으로 시작, 02 전까지 도메인·터널·Tavily 준비 | 도메인이 늦으면 02에서 터널 검증만 뒤로 미루고 A11을 "미검증"으로 남김(15 전에 반드시 확인) | 추천안. OpenAI 키 보유. TourAPI 키·`.dev` 도메인·Named Tunnel 토큰·Tavily 키 **발급 방법은 02 시작 직전에 안내** |
| Q3 | FR-70의 **임베딩 모델 비교(bge-m3)** 를 v1.0에 넣을까? 로컬 임베딩 실행 환경과 별도 LightRAG 작업공간·재인덱싱이 필요해 8컨테이너 구성([A] ADR-01) 밖의 일회성 구성이 든다 | **v1.0에서는 제외하고 v1.1 이후로**(22는 리랭커·검증·질의 모드 비교만) | B: 22에 "위키 50페이지 표본, 일회성 `docker compose run`" 하위 실험으로 포함(하루 추가) | 추천안 (bge-m3 비교 v1.1 이후) |
| Q4 | FR-46 lint의 **"모순 탐지"** 방법이 정해져 있지 않다 | **코드 규칙만**: 위키 frontmatter·본문 핵심 필드 ↔ `tour_items` 불일치, 허브가 삭제된 contentid 링크 | B: LLM으로 허브 ↔ 엔티티 모순 점검(비용 추가) | 추천안 (코드 규칙만 — 휴무일·주소·전화 등 핵심 정보 대조) |
| Q5 | 골든 Q&A 평가셋(22) 작성 주체 | **적재 데이터에서 에이전트가 초안 40~60문항 생성 → 사용자 검수·수정** | B: 사용자가 직접 작성 | 추천안 (에이전트 초안 → 사용자 검수) |
| Q6 | `tour_live`(10)의 TourAPI 호출도 일일 한도(개발계정 1,000건)를 같이 쓴다. ingest 예산(ADR-14, 800)과 카운터를 공유할까? | **공유 카운터**: ingest 800 + 실시간 툴 200 예약, 초과 시 툴 오류로 LLM에 전달 | B: 실시간 호출은 세지 않음(ingest가 한도 에러로 중단될 수 있음) | 추천안 (공유 카운터 800+200) |
| Q7 | NFR-01 흔한 비밀번호 목록의 출처 | **공개 목록(예: SecLists 상위 10만) 중 10자 이상 항목만 파일로 포함**, 출처·라이선스는 05 spec에 기록 | B: 직접 만든 소규모 목록 | 추천안 + 가입·재설정·비밀번호 변경 화면에 규칙 미리 표시(14) |
| Q8 | X-c: DB 초기화 스크립트 `.sql` → `.sh` 변경 | **`.sh`로 변경**(롤 비밀번호를 `.env`에서 주입) | B: `.sql` + 비밀번호는 api 기동 시 별도 설정(복잡) | 추천안 (`01-init.sh`) |
| Q9 | 01 슬라이스 적재량 | **서울 관광지(타입 12) 30건 + 제주 관광지 20건** — 한도 약 150호출 | B: 서울만 50건 | 추천안 (서울 30 + 제주 20) |
