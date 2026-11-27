# PROGRESS
- 현재 단계: Phase 5 — 구현 (01 구현·검증 완료 2026-11-28, G5 대기)
- 게이트: G1 ✅ (2026-11-07) · G2 ✅ (2026-11-07) · G3 ✅ (2026-11-07, 재검토 재승인 2026-11-21) · G4 ✅ (2026-11-21) · G5 (작업별, 아래 표)
- 다음 할 일: **01 G5(dev 병합) 사용자 승인 대기** — 남은 사용자 확인: A8 엔티티 품질 판단(추천 쓸 만함), 포털 트래픽 화면의 한도 단위·호출 수(A12), 다음 날 OpenAI Usage로 인덱싱 비용. 승인 후 02-e2e-chat-slice(02 시작 직전에 `.dev` 도메인·Named Tunnel 토큰·Tavily 키 발급 방법 안내, G4 Q2). Node LTS(fnm)는 14 구현 시작 때
- 브랜치: `dev`(작업 기준) · `prod`(릴리스). 2026-11-07 로컬 `master` → `prod` 이름 변경, `dev` 생성. 원격 반영(push·기본 브랜치 변경·원격 master 삭제)은 사용자가 직접

| 작업id | spec/test | 브랜치 | 구현·테스트 | 커밋 | G5 병합 |
|---|---|---|---|---|---|
| 01-e2e-tools-slice | ✅ | feat/01-e2e-tools-slice | ✅ 단위 125·통합 8 통과, HITL 완료 | 7332115 | 대기 |
| 02-e2e-chat-slice | ✅ | feat/02-e2e-chat-slice | | | |
| 03-ingest-bootstrap | ✅ | feat/03-ingest-bootstrap | | | |
| 04-db-schema | ✅ | feat/04-db-schema | | | |
| 05-auth-core | ✅ | feat/05-auth-core | | | |
| 06-password-reset-mail | ✅ | feat/06-password-reset-mail | | | |
| 07-guard-pii | ✅ | feat/07-guard-pii | | | |
| 08-guard-pipeline | ✅ | feat/08-guard-pipeline | | | |
| 09-chat-sessions | ✅ | feat/09-chat-sessions | | | |
| 10-tool-tour-live | ✅ | feat/10-tool-tour-live | | | |
| 11-quota-usage | ✅ | feat/11-quota-usage | | | |
| 12-faq-cache | ✅ | feat/12-faq-cache | | | |
| 13-feedback | ✅ | feat/13-feedback | | | |
| 14-web-foundation | ✅ | feat/14-web-foundation | | | |
| 15-web-chat | ✅ | feat/15-web-chat | | | |
| 16-web-chat-actions | ✅ | feat/16-web-chat-actions | | | |
| 17-voice | ✅ | feat/17-voice | | | |
| 18-admin-users | ✅ | feat/18-admin-users | | | |
| 19-admin-usage | ✅ | feat/19-admin-usage | | | |
| 20-ingest-hubs-lint | ✅ | feat/20-ingest-hubs-lint | | | |
| 21-ingest-daily-sync | ✅ | feat/21-ingest-daily-sync | | | |
| 22-eval-golden | ✅ | feat/22-eval-golden | | | |
| 23-eval-attack-set | ✅ | feat/23-eval-attack-set | | | |
| 24-eval-daily-quality | ✅ | feat/24-eval-daily-quality | | | |
| 25-admin-quality-hitl | ✅ | feat/25-admin-quality-hitl | | | |
| 26-release-readiness | ✅ | feat/26-release-readiness | | | |

## 산출물
- `docs/harness/requirements.md` — **G1 승인본** (2026-11-07). 확정 전제 D-01~D-22, FR/NFR, G1 직전 확인 O1~O6, G2/PoC 이관 항목, 상충 기록 C1~C12
- `docs/analysis/01-data-sources.md` — 확장 데이터 원천 조사
- `docs/harness/architecture.md` — **G3 승인본** (2026-11-21 재검토 재승인). 이전 G3 승인본(2026-11-07)은 git `a14d89b`. 컨테이너 8개, LangGraph 답변+검증 에이전트, 입력·출력 검사, 매일 03:00 평가 배치, 미검증 가정 A1~A30(§12)
- `docs/harness/program_list.md` — **G4 승인본** (2026-11-21). 작업 26개·마일스톤 M0~M7·요구사항 추적표·상충 X-a~X-i·확인 질문 Q1~Q9 결정
- `docs/harness/erd.md` + `docs/images/erd.svg·png` — ERD 18개 테이블(2026-11-21 G3 재승인 19개 → 2026-11-22 `quota_requests` 삭제), README.md 반영. 한글 명칭 정본 = ERD = DDL COMMENT
- `SECURITY_GUIDE.md`(루트) — AI 보안 가이드 (2026-11-21, 사용자 요청으로 간결본: 최근 사고 → 위협 유형 → 막는 방법 → 테스트. 위협 이름은 `한글 (영문 정식 명칭)`, 요구사항 ID·근거 ID 넣지 않음. 세부 설계는 architecture.md에)
- `docs/images/src/` — 구성도·ERD 생성 스크립트(`arch.py`, `erd.py`, `icons.json`). 렌더: debian 컨테이너 + librsvg2-bin + fonts-noto-cjk
- `docs/harness/stack-options.md` — **G2 승인본** (2026-11-07). S1~S21 후보·트레이드오프·사용자 답변, 조사 사실 F1~F12

- `docs/harness/tasks/01-e2e-tools-slice/`, `02-e2e-chat-slice/` — spec.md·test.md (2026-11-21, 확인 질문 결정 반영)
- `docs/harness/tasks/03`~`07` — spec.md·test.md (2026-11-21, 확인 질문 결정 반영).
- `docs/harness/tasks/08`~`12` — spec.md·test.md (2026-11-21, 확인 질문 결정 반영). 08이 `TurnStore`·`TurnInput`·`api/chat/store.py`를 먼저 만들고 09·11·12가 넓힘. 10은 `0003` 테이블 생성 스크립트(호출 수 세기 DB 함수 2개). `answer.md`는 08·09·10이 모두 규칙을 덧붙임(병합 때 번호 맞춤). 앞 작업 테스트 수정 목록은 각 spec "앞 작업 테스트" 절 앞 작업 테스트를 고치는 부분: 03은 01 예산 함수·테스트 교체, 04는 02의 네트워크 차단 테스트 설정에 DB 테스트 허용, 05는 02 채팅 테스트에 인증·CSRF 반영
- `docs/harness/tasks/13`~`17` — spec.md·test.md (2026-11-22, 확인 질문 결정 반영). 발견한 앞 작업과의 불일치: 12 캐시 저장 조건에 "👎 없음" 누락(13-Q1), TECH_STACK §8.1 STT 시그니처로 사용량(초) 기록 불가(17-Q1), 웹 테스트용 Node가 WSL에 필요(14-Q1 → 결정 시 CLAUDE.md·README 갱신), 14가 02의 nginx `location /` 404를 web 프록시로 바꿈
- `docs/harness/tasks/18`~`22` — spec.md·test.md (2026-11-22, 확인 질문 전부 추천안대로 확정). 병렬 작성, 서로 맞춘 것: 18이 `admin_router`(`require_admin`)·`AdminShell.tsx`의 `ADMIN_NAV`를 만들고 19가 include 1줄·메뉴 1개 추가(layout.tsx는 안 고침) · 20이 공개 함수(`write_hubs`·`affected_hubs`·`missing_hubs`·`run_lint`·`commit_wiki`)와 잠금 `nadri/ingest/lock.py`를 만들고 21이 호출 · 19 kind 목록에 22의 `eval` 포함. 발견한 앞 작업 불일치: ingest가 상주하면 01·05의 `service_completed_successfully` 의존이 안 풀림(21-Q4), 03 `--follow`가 01:00 현행화와 잠금·예산 충돌(21-Q1), 02 `TAVILY_API_KEY` 필수 설정이 ingest에서 실패(20-Q12) ↔ 22는 평가용으로 ingest에 Tavily 키 추가(22-Q8) — 서로 맞춰야 함, 01 rag_query 허브 청크에 contentid 없음(20-Q4), 01 `fetch_candidates` mode 고정(22-Q1), 문서에 옛 이름 `admin-users-quota`·`quota` 화면 남음([PL] §1.2·[A] §7·14 §1.1)
- `docs/harness/tasks/23`~`26` — spec.md·test.md (2026-11-22 초안, 2026-11-28 확인 질문 결정 반영). 병렬 작성 후 24를 기준으로 맞춤: 24가 `eval_reports.stats` 구조의 주인(§9, 공격 세트는 `stats.attack_set`), 23 `run_attack_set`은 `AttackReport`를 돌려주고 24 `to_attack_summary`가 변환(`to_stats()`는 CLI 결과 파일용), 23이 `sf` 없이도 사용량 기록, `UsageRecord.kind`는 23이 `eval`·24가 `proposal` 추가 · 25 화면 키는 24 §9 그대로 + 모르는 키는 "기타 집계" 표 · 조정 설정값은 compose `x-tuning` 하나로 api·tour-tools·ingest 공유(24-Q2·26-Q5, 26 C-27 검사). 발견한 앞 작업 불일치: **21 빈 DB에서 스케줄러가 전체 초기 적재를 스스로 시작**(26-Q1), **간접 인젝션 공격자 주소가 "툴 결과에 있던 주소" 규칙을 통과**(23-Q11, 지금은 검증 에이전트만 막음), 04 `PROPOSAL_TARGETS`에 `faq_cache` 없음(24-Q1), 20 `lock.py`에 키 2 없음(24-Q14), [PL] 23 의존 08→08·22(23-Q10)·25가 19 함수 사용(25-Q6), 03 `--limit`→`--max-items`([PL] 26 완료 기준), [A] §9·§2·ADR-01 문구가 확정 spec과 다름(26-Q8), lightrag healthcheck 없음(26-Q2)

## 결정 로그 (게이트에서 바뀐 것)
- 2026-11-28 01 구현 중 확인(spec.md "확인됨" 반영): LightRAG v1.5.7 env 키 이름 일치, 문서 API 경로·`X-API-Key` 확인, 이미지 `ghcr.io/hkuds/lightrag:v1.5.7`·WORKING_DIR `/app/data/rag_storage`, pg18 데이터 볼륨 `/var/lib/postgresql`. LightRAG가 file_source를 basename으로 저장 → 경로 `/`를 `__`로 바꿔 보냄(A7 대안 범위, 코드 처리). FastMCP는 `host="0.0.0.0"`으로 생성(기본값이면 DNS 리바인딩 보호로 `tour-tools` 호스트 거부). 이미지 크기 app 415MB / tools 5.13GB(CUDA 휠 없음)
- 2026-10-25 (G1 전): 리버스 프록시 Caddy → **Nginx**
- 2026-10-25 (G1 전): 프로젝트 이름 **nadri**. 로컬 디렉터리는 `myAgent` 유지
- 2026-10-25 (G1 전): 확장 데이터 원천 4곳을 MVP 이후 항목으로 추가(FR-49). 크롤링 기본 미사용
- 2026-11-07 (G1 전, Q1~Q18 답변): 관리자 백오피스 + 챗봇 PWA · 가입 신청→관리자 승인 · 이메일 인증코드 비밀번호 재설정 · 본인 데모 · Cloudflare Tunnel로 HTTPS · 서울+제주 8종 · 매일 01:00 현행화 · 1인 하루 50회(초과 시 추가요청→관리자 승인 +50) · 웹 검색 Tavily · Hermes만 사용(OpenAI SDK 비교는 MVP 이후 실험) · TTS ElevenLabs(Edge 제외) · dev/prod 브랜치 · 위치 정보는 동의 시에만 · 세션 단위 삭제 
- 2026-11-07 (G1 전, O1~O6): 개발 중 Cloudflare 임시 주소·데모 전 도메인 구입 · 인증코드 10분/5회 · 월 $10 초과 시 경고만 · **답변 이미지 표시 안 함** · 비교 실험 MVP 이후 포함 · 첫 관리자 CLI 생성·사용자 비활성화 포함

- 2026-11-07 G2: S1 보조 모델 제거 → `gpt-6-luna` 하나로 답변·제목·요약·인덱싱 (`gpt-5-nano` 2026-12-11 종료) · S2 STT `gpt-transcribe` · S3 `text-embedding-3-small`(bge-m3는 비교 실험만) · S4 LightRAG 인덱싱 `gpt-6-luna`, 질의 `mix`로 시작 · S5 리랭커 tour-tools 내장 CrossEncoder · S6 **`.dev` 도메인 + Named Tunnel을 개발 중부터**(O1 변경, Quick Tunnel SSE 미지원) · S7 Gmail SMTP · S8 개발계정 분할 적재 · S9 Hermes 태그 고정·memory off · S10~S21 추천안(Tailwind, Vitest+Playwright, APScheduler, PostgreSQL만) · S20 ElevenLabs 기본 보이스 1개, 사용자 선택 없음
- 2026-11-07 G2: **별도 PoC 없음** — 아키텍처를 바꿀 수 있는 위험 연동을 첫 구현 작업(최소 end-to-end)에서 실행 검증, 나머지는 해당 작업에서 확인
- 2026-11-07 G2: 실사용자는 사실상 1명(5명은 상한 가정). 예상 월 약 $1.5 + 최초 인덱싱 약 $15~30
- 2026-11-07: 기술스택 확정·변경 시 README.md도 항상 갱신 (사용자 요청)
- 2026-11-07 G3: Q1 `backend/` 단일 프로젝트(이미지 2종), 컨테이너명 `ingest` 유지 · Q2 같은 인스턴스 별도 DB `lightrag` · Q3 답변 끝 출처 블록 파싱 · Q4 허브 시군구 27개 · Q5 성공·캐시 적중 차감, 장애 미차감 · Q6 제목·요약은 api 직접 호출, Hermes는 에이전트 루프 전용 유지
- 2026-11-07 G3: LangGraph·LangChain 검토 후 미사용 (Hermes 유지, FR-71 비교 대상 그대로)
- 2026-11-21 G3 재승인: Hermes 제거 → LangGraph(답변+검증 에이전트)·LangChain, 매일 품질 평가·HITL, AI 보안, ERD 19개, SECURITY_GUIDE.md 간결본
- 2026-11-21 G4: 작업 26개 승인. 임계 경로 01→02→05→08→09→11→12→13→20·21→24→25→26, 03 적재는 슬라이스 직후 병행
- 2026-11-21 G4 Q1~Q9: Q1 05 병합 전까지 cloudflared는 SSE 검증 때만 기동 · Q2 01은 TourAPI·OpenAI 키로 시작(OpenAI 키 보유), 나머지 키 발급 방법은 02 직전 안내 · Q3 bge-m3 임베딩 비교 v1.1 이후 · Q4 lint 모순 탐지 = 코드 규칙만(휴무일·주소·전화 등 핵심 필드 ↔ tour_items 대조, 삭제된 contentid 링크) · Q5 골든셋은 에이전트 초안 40~60 → 사용자 검수 · Q6 TourAPI 카운터 공유(적재 800 + 실시간 200) · Q7 흔한 비밀번호는 SecLists 공개 목록 10자 이상, 가입·재설정·변경 화면에 규칙 미리 표시 · Q8 DB 초기화 `01-init.sh` · Q9 01 적재 서울 30 + 제주 20
- 2026-11-21 G4: 리랭커는 tour-tools CrossEncoder로 켜 둠(LightRAG 내장 리랭크만 off). 구성도 LightRAG 부제 "리랭크 off" → "Graph RAG (후보 30개 검색)"
- 2026-11-21 Phase 4 M0 확인 질문: 01-Q1 Alembic 유지(문서 명칭은 "테이블 생성 스크립트", ingest가 기동 시 실행 후 종료) · 01-Q4 개발 도구는 WSL2 Ubuntu에 uv + `backend/.venv`, 테스트도 WSL에서(CLAUDE.md 작업 환경 갱신: 호스트 OS = Windows 11) · 01-Q7 `lightrag-data` 볼륨 처음부터 · 01-Q5 측정용 CLI 4개 추가 · 01-Q6 카운터 쓰기 권한은 10에서 최소 권한으로 · 02-Q2 `blocked` 이벤트 02부터 · 02-Q5 터널 토큰 환경변수 · 02-Q8 Moderation 재시도 0회, 08에서 재검토 · 02-Q9 nginx `127.0.0.1:8080`(Windows 브라우저 `localhost:8080` 접속 확인) · 02-Q7 §4.6 고정 문구 초안 그대로 사용 · 나머지 추천안
- 2026-11-21 Phase 4 03~07 확인 질문: 전부 추천안대로 — 05-Q3 가입 시 이미 쓰인 이메일은 409로 알려 줌(06 재설정의 가입 여부 숨김과 다르지만 수용) · 07-Q1 질문에 쓴 관광지 대표 전화도 가림, SECURITY_GUIDE §4.2 문구 수정(답변에선 안 가림) · 03-Q1 TourAPI 호출 전 카운터 예약(01 예산 함수·테스트 교체) · 03-Q2 오류 22는 그날 중단, 23은 이번 실행만 중단 · 03-Q6 상세 전 껍데기 행도 검색에 노출 · 03-Q9 예상 남은 일수 14일 초과 시 운영계정 증설 문의
- 2026-11-21 Phase 4 08~12 확인 질문(1차): 10-Q1 `nadri_tools`에 호출 수 세기 DB 함수 2개 실행 권한만 추가(NFR-07·[A] §5.1 예외 문구 반영) · 11-Q2 장애 턴도 실제 쓴 AI 비용은 `usage_events`에 기록(한도 차감은 안 함, [A] §3.1 10)과 다름) · 11-Q3 동시 요청으로 일일 한도 1~2회 초과 허용 · 08 `meta` 이벤트를 09가 아니라 08에서 추가(02-Q3 변경) · 12-Q4 캐시 답변은 출력 검사 재실행 안 함. 나머지 30개는 추천안대로 확정
- 2026-11-22 Phase 4 13~17 확인 질문: 전부 추천안대로 — 13-Q1 👎 받은 답변은 FAQ 캐시에 저장하지 않음(12 저장 조건 보완) · 13-Q5 👎→👍여도 캐시 되살리지 않음 · 14-Q1 웹 개발 도구(Node LTS·npm·Playwright)도 WSL에(CLAUDE.md·README 반영) · 14-Q7 가입은 원래대로 관리자 승인, 승인 대기 화면은 [다시 확인] 버튼만 · 17-Q1 STT 사용량은 브라우저가 보낸 녹음 길이(60초 상한). 14가 nginx `location /`를 web으로 바꿈
- 2026-11-22 **요구사항 변경(사용자 요청)**: 한도 추가 요청 기능 삭제 — FR-62 하루 50회 초과 시 그날 차단·안내만, FR-82 삭제, `quota_requests` 테이블·`daily_quota.extra` 삭제(ERD 18개). 04·11·16 spec, requirements·architecture·erd·program_list 반영. 18 작업 id `18-admin-users-quota` → `18-admin-users`(가입 승인·비활성화). 관리자(role=admin)는 일일 한도 없음(분당 10회 제한·사용량 기록은 동일), 한도 초과 문구 "오늘 질문 한도(50회)를 다 썼어요. 내일 0시(한국 시간)에 다시 이용해 주세요." 확정. (검토 중 "체험 5회 후 정식 사용 요청" 안이 나왔으나 사용자가 철회)
- 2026-11-22 Phase 4 18~22 확인 질문: 전부 추천안대로 — 18-Q1 18 의존 "05, 14"([PL] 표·그래프 수정) · 18-Q3 관리자 계정은 비활성화 불가 · 18-Q2 거절 후 승인 불가 · 19-Q1 KST 월·날짜 · 20-Q4 rag_query가 허브 결과에 `places` 붙임(01 수정) · 20-Q11 잠금 `nadri/ingest/lock.py`로 이동 · 20-Q12 02 `TAVILY_API_KEY`는 쓰는 곳에서 확인 + 22-Q8 평가용으로 ingest에 Tavily 키 추가 · 21-Q1 01:00 작업 하나가 현행화 → 초기 적재 이어하기(`--follow` 중지) · 21-Q2 놓친 실행은 기동 때 1회 · 21-Q4 ingest healthcheck + tour-tools·api `service_healthy`(컨테이너 8개 유지) · 22-Q1 리랭커·모드는 요청 헤더로 그 실행만 덮어씀 · 22-Q2 검증 끔·0·1·2는 상한 2 실행을 잘라 계산 · 22-Q7 `usage_events kind=eval`. 문서 정리: 옛 이름 `admin-users-quota`·`quota` 화면 제거([PL] §1.2·[A] §7·14 §1.1)
- 2026-11-28 Phase 4 23~26 확인 질문: 전부 추천안대로. 사용자가 따로 본 것 — 26-Q1 21 이어하기 조건에 "초기 적재를 한 번이라도 시작했을 때만" 추가(빈 DB에서 스케줄러가 전체 적재를 스스로 시작하지 않음, 21 spec 반영) · 23-Q11 공격자 주소가 "툴 결과에 있던 주소" 규칙을 통과하는 빈틈은 23에서 측정만, 보완은 첫 실행 결과 보고 따로 결정 · 24-Q1 개선안 대상에 `faq_cache` 추가(04 spec·[A] §5.1 반영) · 24-Q3/Q4 블라인드 채점(👍/👎 안 보여 줌), 0·1·2 엄격 · 25-Q2 결정은 채택·보류·기각 사이 언제든 변경, 취소 없음 · 26-Q8 [A] §9·§2·ADR-01 문구는 26 구현 때 수정 · 23-Q5 공격 세트 62건 에이전트 초안 → 사용자 검수. [PL] 의존: 23 = 08·22, 25 = 18·19·24
- 2026-11-28 작업 방식(사용자 요청): 확인 질문은 비용·보안·승인본 변경 등 중요한 것만 사용자에게 묻고, 세부는 추천안대로 확정 후 보고
- 2026-11-07 G3: ERD 승인, 테이블·컬럼 한글 명칭을 DDL COMMENT로 넣는다. 구성도 재작성, 문서 상충 X1~X9 정리

## 기타 산출물
- `README.md`, `.gitignore`, `docs/images/architecture.svg`·`architecture.png` (구성도, SVG가 원본)
- TECH_STACK·README·requirements는 G2 결과 반영 완료. 구성도(architecture.svg/png)는 2026-11-21 재작성(hermes 제거, LangGraph·입력/출력 검사·평가 배치 반영). 생성 스크립트는 `docs/images/src/`

## G3 재검토 요약 (2026-11-21 재승인)
- Hermes 제거 → api 안 **LangGraph**: 답변 에이전트 ⇄ 검증 에이전트(다시 쓰기 ≤2), LLM 호출은 LangChain(STT·Moderation만 OpenAI SDK). 컨테이너 9 → 8
- 입력 검사(PII 가리기 → Moderation → LLM 분류기, 실패 시 차단) / 출력 검사(검증 에이전트 + Moderation + 코드 검사), 초안 먼저 스트리밍 → "✓ 확인됨"/수정본 교체
- 매일 03:00 평가 에이전트 → 개선안 에이전트 → /admin 품질 리포트에서 사람이 채택·보류·기각(HITL), 👍/👎+사유, 공격 질문 세트 매일 실행
- ERD 14 → 19 테이블(피드백·보안 이벤트·품질 보고서·턴별 채점·개선안), 구성도에 에이전트 4개를 보라색 도형으로 표시
- 비용: 질문 1건 약 $0.0019, 1인 월 약 $3~4. `mcp`는 1.30.x 고정(어댑터가 `mcp<2` 요구)
- 확인 질문 Q1~Q4 답변 완료(위 결정 로그 참고)

## 01 HITL 진행 (2026-11-28)
- H-2·H-3 통과(포트 없음, 테이블 4개 한글 설명, nadri_tools는 ingest_runs 거부) · H-8 `401 401`
- H-4: KorService2는 `areaCode`가 아니라 법정동 코드 `lDongRegnCd`(서울 11·제주 50) — 수정 커밋 `e172331`. 16칸 합계 10,061, 적재 일수 서비스 전체 한도 38일 / 오퍼레이션별 13일(14일 초과 → 03에서 운영계정 증설 여부 결정). 여행코스(25)는 두 지역 모두 0
- H-5: 서울 30(91호출, 인덱싱 278초)·제주 20(61호출, 186초), 실패 0, wiki_pages 50/50/50, 카운터 ingest 184. **sigungu_code 50건 모두 비어 있음**(응답의 `sigungucode` 빈 값, 대신 `lDongSignguCd` 있음 → 20 허브 시군구 기준에 영향). 페이지에 입장료·전화 중복, `heritage1: 0` 같은 잡음(03 템플릿에서 정리)
- H-6(A8): 엔티티 이름 한국어 정상, frontmatter 키가 엔티티로 잡히지 않음. 엔티티 유형이 한/영 섞임(location·장소), 전화번호·"화장실 정보" 같은 잡음 엔티티 일부 — 사용자 판단 대기
- H-7: 툴 3종 정상, data_query 27ms, get_datetime 21ms, **rag_query 약 30초(lightrag 2초 + rerank 28초)** → ONNX 전환 필요(사용자 결정)
- H-10: 전체 reindex skipped 50·문서 수 50 유지 ✅. 1건 변경 reindex는 indexed 1·문서 수 유지지만 **doc_id가 바뀌지 않음**(LightRAG 문서 ID가 내용 해시가 아닐 수 있음), 변경 문구가 rag_query 상위 결과에 안 보임 → ONNX 후 재확인
- ONNX int8 전환 커밋 `858fd7e`: tools 이미지 5.13GB→1.34GB(torch 제거), 원본 대비 상위5 겹침 평균 0.88·1위 5/5 일치. **rerank p50 17.1초/p95 19.2초(512·30)**, 256·20이면 p50 6.2초/p95 10.5초 — 여전히 2초 기준 초과(이 CPU에 int8 가속 명령 없음 추정). 사용자 결정 대기: 작은 다국어 리랭커 교체 / 후보·길이 축소 / 리랭커 끄고 22 평가에서 재판단 / GPU / 기준 완화. 원본 이미지 `nadri-tools:torch-baseline` 보존 중
- 2026-11-28 사용자 결정: **리랭커 끔**(compose `RAG_RERANK_ENABLED=false`, 코드·ONNX 모델은 유지). 끔 상태 rag_query p50 0.29초/p95 0.59초(같은 질문 반복이라 LightRAG 캐시 영향 가능, 새 질문은 약 2초). 켤지는 22 골든셋 on/off 비교로 재판단
- H-10 재확인 ✅: doc_id는 경로 기반(내용이 바뀌어도 같음), 변경 문구가 LightRAG 저장 본문·검색 1위 결과에 반영. 통합 테스트 I-1~I-8 통과(I-8 기대값 수정). spec §10 판정표 기록. H-11(핫리로드)은 생략. 현재 compose는 dev 덮어쓰기(127.0.0.1 포트)로 떠 있음 → H-10 재확인 → 통합 테스트(I-1~I-8) → spec §10 판정 → G5

## 막힌 것 / 사용자 확인 필요
- 01 A9(리랭커 지연) 사전 측정(2026-11-28, 실 키 없이 tools 컨테이너에서 직접): bge-reranker-v2-m3 CPU, 30쌍(쌍당 약 325토큰) p50 **16.3초**, max_length 256으로도 약 12초(Ryzen 5 5600, torch 스레드 6). 기준 p95 ≤ 2초를 크게 넘어 spec §9상 **사용자 결정 필요**(ONNX 변환·리랭커 끔·GPU·후보 수 축소 등). H-9 실측(실제 위키 페이지)으로 다시 확인 후 결정
  - 2026-11-28 사용자 결정: **ONNX 변환으로 CPU 최적화** 방향. H-9 전에 tour-tools 리랭커를 ONNX(필요 시 int8 양자화)로 바꿔 재측정, 그래도 2초 초과면 후보 수 축소 등 다시 결정
- (해결) 2026-11-20 G3 재검토 요청 → 2026-11-21 재승인 완료. 상세 내용은 위 "G3 재검토 요약"·결정 로그, requirements.md §8
- 사용자: `.dev` 도메인 구입(Cloudflare Registrar) — 인프라 작업 전까지. Gmail 발신 계정·앱 비밀번호 — 메일 작업 전까지 `.env`에 직접
