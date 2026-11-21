# PROGRESS
- 현재 단계: Phase 4 — 작업별 spec/test 작성 (01~07 확정, 08~12 초안 작성·확인 질문 답변 대기)
- 게이트: G1 ✅ (2026-11-07) · G2 ✅ (2026-11-07) · G3 ✅ (2026-11-07, 재검토 재승인 2026-11-21) · G4 ✅ (2026-11-21) · G5 (작업별, 아래 표)
- 다음 할 일: 08~12 확인 질문(각 spec 끝 표) 사용자 답변 반영 → 13~17 spec/test 작성. (원래 계획: `spec-writer`로 `docs/harness/tasks/<작업id>/spec.md`·`test.md` 작성. 26개라 M0(01·02)부터 5개 안팎씩 묶어 진행. 02 시작 직전에 TourAPI 키·`.dev` 도메인·Named Tunnel 토큰·Tavily 키 발급 방법 안내(G4 Q2))
- 브랜치: `dev`(작업 기준) · `prod`(릴리스). 2026-11-07 로컬 `master` → `prod` 이름 변경, `dev` 생성. 원격 반영(push·기본 브랜치 변경·원격 master 삭제)은 사용자가 직접

| 작업id | spec/test | 브랜치 | 구현·테스트 | 커밋 | G5 병합 |
|---|---|---|---|---|---|
| 01-e2e-tools-slice | ✅ | feat/01-e2e-tools-slice | | | |
| 02-e2e-chat-slice | ✅ | feat/02-e2e-chat-slice | | | |
| 03-ingest-bootstrap | ✅ | feat/03-ingest-bootstrap | | | |
| 04-db-schema | ✅ | feat/04-db-schema | | | |
| 05-auth-core | ✅ | feat/05-auth-core | | | |
| 06-password-reset-mail | ✅ | feat/06-password-reset-mail | | | |
| 07-guard-pii | ✅ | feat/07-guard-pii | | | |
| 08-guard-pipeline | 초안 (Q1~Q7 대기) | feat/08-guard-pipeline | | | |
| 09-chat-sessions | 초안 (Q1~Q9 대기) | feat/09-chat-sessions | | | |
| 10-tool-tour-live | 초안 (Q1~Q8 대기) | feat/10-tool-tour-live | | | |
| 11-quota-usage | 초안 (Q1~Q6 대기) | feat/11-quota-usage | | | |
| 12-faq-cache | 초안 (Q1~Q5 대기) | feat/12-faq-cache | | | |
| 13-feedback | | feat/13-feedback | | | |
| 14-web-foundation | | feat/14-web-foundation | | | |
| 15-web-chat | | feat/15-web-chat | | | |
| 16-web-chat-actions | | feat/16-web-chat-actions | | | |
| 17-voice | | feat/17-voice | | | |
| 18-admin-users-quota | | feat/18-admin-users-quota | | | |
| 19-admin-usage | | feat/19-admin-usage | | | |
| 20-ingest-hubs-lint | | feat/20-ingest-hubs-lint | | | |
| 21-ingest-daily-sync | | feat/21-ingest-daily-sync | | | |
| 22-eval-golden | | feat/22-eval-golden | | | |
| 23-eval-attack-set | | feat/23-eval-attack-set | | | |
| 24-eval-daily-quality | | feat/24-eval-daily-quality | | | |
| 25-admin-quality-hitl | | feat/25-admin-quality-hitl | | | |
| 26-release-readiness | | feat/26-release-readiness | | | |

## 산출물
- `docs/harness/requirements.md` — **G1 승인본** (2026-11-07). 확정 전제 D-01~D-22, FR/NFR, G1 직전 확인 O1~O6, G2/PoC 이관 항목, 상충 기록 C1~C12
- `docs/analysis/01-data-sources.md` — 확장 데이터 원천 조사
- `docs/harness/architecture.md` — **G3 승인본** (2026-11-21 재검토 재승인). 이전 G3 승인본(2026-11-07)은 git `a14d89b`. 컨테이너 8개, LangGraph 답변+검증 에이전트, 입력·출력 검사, 매일 03:00 평가 배치, 미검증 가정 A1~A30(§12)
- `docs/harness/program_list.md` — **G4 승인본** (2026-11-21). 작업 26개·마일스톤 M0~M7·요구사항 추적표·상충 X-a~X-i·확인 질문 Q1~Q9 결정
- `docs/harness/erd.md` + `docs/images/erd.svg·png` — ERD 19개 테이블(2026-11-21 G3 재승인), README.md 반영. 한글 명칭 정본 = ERD = DDL COMMENT
- `SECURITY_GUIDE.md`(루트) — AI 보안 가이드 (2026-11-21, 사용자 요청으로 간결본: 최근 사고 → 위협 유형 → 막는 방법 → 테스트. 위협 이름은 `한글 (영문 정식 명칭)`, 요구사항 ID·근거 ID 넣지 않음. 세부 설계는 architecture.md에)
- `docs/images/src/` — 구성도·ERD 생성 스크립트(`arch.py`, `erd.py`, `icons.json`). 렌더: debian 컨테이너 + librsvg2-bin + fonts-noto-cjk
- `docs/harness/stack-options.md` — **G2 승인본** (2026-11-07). S1~S21 후보·트레이드오프·사용자 답변, 조사 사실 F1~F12

- `docs/harness/tasks/01-e2e-tools-slice/`, `02-e2e-chat-slice/` — spec.md·test.md (2026-11-21, 확인 질문 결정 반영)
- `docs/harness/tasks/03`~`07` — spec.md·test.md (2026-11-21, 확인 질문 결정 반영).
- `docs/harness/tasks/08`~`12` — spec.md·test.md 초안 (2026-11-21). 08이 `TurnStore`·`TurnInput`·`api/chat/store.py`를 먼저 만들고 09·11·12가 넓힘. 10은 `0003` 테이블 생성 스크립트(호출 수 세기 DB 함수 2개). `answer.md`는 08·09·10이 모두 규칙을 덧붙임(병합 때 번호 맞춤). 앞 작업 테스트 수정 목록은 각 spec "앞 작업 테스트" 절 앞 작업 테스트를 고치는 부분: 03은 01 예산 함수·테스트 교체, 04는 02의 네트워크 차단 테스트 설정에 DB 테스트 허용, 05는 02 채팅 테스트에 인증·CSRF 반영

## 결정 로그 (게이트에서 바뀐 것)
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
- 2026-11-21 Phase 4 08~12 확인 질문(1차): 10-Q1 `nadri_tools`에 호출 수 세기 DB 함수 2개 실행 권한만 추가(NFR-07·[A] §5.1 예외 문구 반영) · 11-Q2 장애 턴도 실제 쓴 AI 비용은 `usage_events`에 기록(한도 차감은 안 함, [A] §3.1 10)과 다름) · 11-Q3 동시 요청으로 일일 한도 1~2회 초과 허용 · 08 `meta` 이벤트를 09가 아니라 08에서 추가(02-Q3 변경) · 12-Q4 캐시 답변은 출력 검사 재실행 안 함. 나머지 30개 답변 대기
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

## 막힌 것 / 사용자 확인 필요
- (해결) 2026-11-20 G3 재검토 요청 → 2026-11-21 재승인 완료. 상세 내용은 위 "G3 재검토 요약"·결정 로그, requirements.md §8
- 사용자: `.dev` 도메인 구입(Cloudflare Registrar) — 인프라 작업 전까지. Gmail 발신 계정·앱 비밀번호 — 메일 작업 전까지 `.env`에 직접
