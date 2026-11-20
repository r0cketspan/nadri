# PROGRESS
- 현재 단계: Phase 3 — 작업 분해 (시작 전)
- 게이트: G1 ✅ (2026-11-07) · G2 ✅ (2026-11-07) · G3 ✅ (2026-11-07, 재검토 재승인 2026-11-21) · G4 · G5 (작업별, 아래 표)
- 다음 할 일: Phase 3 — `task-planner`에 requirements.md·architecture.md·erd.md·SECURITY_GUIDE.md를 넘겨 program_list.md 작성 → G4. 첫 작업은 최소 end-to-end(위험 연동 검증 — architecture.md §12 미확인 가정 A18~A30 등)
- 브랜치: `dev`(작업 기준) · `prod`(릴리스). 2026-11-07 로컬 `master` → `prod` 이름 변경, `dev` 생성. 원격 반영(push·기본 브랜치 변경·원격 master 삭제)은 사용자가 직접

| 작업id | spec/test | 브랜치 | 구현·테스트 | 커밋 | G5 병합 |
|---|---|---|---|---|---|
| (G4 승인 후 작성) | | | | | |

## 산출물
- `docs/harness/requirements.md` — **G1 승인본** (2026-11-07). 확정 전제 D-01~D-22, FR/NFR, G1 직전 확인 O1~O6, G2/PoC 이관 항목, 상충 기록 C1~C12
- `docs/analysis/01-data-sources.md` — 확장 데이터 원천 조사
- `docs/harness/architecture.md` — **G3 승인본** (2026-11-21 재검토 재승인). 이전 G3 승인본(2026-11-07)은 git `a14d89b`. 컨테이너 9개, 데이터 흐름 6개, DB·API 개요, ADR-01~16, 상충 X1~X9, 미검증 가정 A1~A17, 구성도 갱신 사양, 확인 질문 Q1~Q6
- `docs/harness/erd.md` + `docs/images/erd.svg·png` — ERD 19개 테이블(2026-11-21 G3 재승인), README.md 반영. 한글 명칭 정본 = ERD = DDL COMMENT
- `SECURITY_GUIDE.md`(루트) — AI 보안 가이드 (2026-11-21, 사용자 요청으로 간결본: 최근 사고 → 위협 유형 → 막는 방법 → 테스트. 위협 이름은 `한글 (영문 정식 명칭)`, 요구사항 ID·근거 ID 넣지 않음. 세부 설계는 architecture.md에)
- `docs/images/src/` — 구성도·ERD 생성 스크립트(`arch.py`, `erd.py`, `icons.json`). 렌더: debian 컨테이너 + librsvg2-bin + fonts-noto-cjk
- `docs/harness/stack-options.md` — **G2 승인본** (2026-11-07). S1~S21 후보·트레이드오프·사용자 답변, 조사 사실 F1~F12

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
- 2026-11-20 **G3 재검토 중 (아직 반영 전)**: 사용자가 Hermes 제거 → LangGraph로 툴 호출, LLM 호출은 LangChain(`ChatOpenAI`·`OpenAIEmbeddings`, STT만 OpenAI SDK)으로 변경 요청. 결정: A tour-tools 별도 MCP 컨테이너 유지 · D 검증 에이전트 넣음(다시 쓰기 최대 2회, 느리면 줄임) · E 초안 먼저 스트리밍 → 검증 후 교체 + "확인됨" 표시. B `langchain-tavily`를 에이전트에 직접 · C FR-71 삭제, "MVP 이후"→"v1.1 이후" · 평가(FR-70)에 검증 끔/1회/2회 비교 추가.
  추가 요구(2026-11-20): ① 매일 03:00 배치 — 평가 에이전트(전날 대화 채점→보고서) → 개선안 에이전트(개선안 작성) → /admin 품질 리포트에서 사람이 채택/보류/기각(HITL), 채택은 개발 후보로 쌓기만(자동 적용 없음). 채점 기준·강도는 구현(spec) 때 정함. 배치는 ingest 컨테이너에 추가(이름 유지로 이해). 👍/👎 피드백 넣음 ② 보안 — Jailbreak·Prompt Injection·개인정보: 입력 검사(규칙 PII 가리기 + Moderation API + LLM 분류기) → 에이전트 → 읽기 전용 툴 → 검증 에이전트(보안 확인 포함) → 화면(HTML·이미지 끔, 링크 제한), 공격 질문 세트를 매일 평가. 보안 우선, 속도는 v1.1 이후. 확정: 입력 검사는 순서대로(검사 통과 후 생성) · 👍/👎 + 👎 사유 선택지(선택 입력, 필수 아님) · PII v1.0 = 주민·외국인등록번호, 전화(070/080 포함), 이메일, 카드(Luhn), 여권·운전면허, 계좌(문맥 있을 때), 이름은 문맥 패턴만, 주소는 안 가림 · Moderation API(omni-moderation-latest, 무료) 입력·출력 모두, 자해 신호는 거절 대신 안전 안내(109) · AI 보안 설계는 별도 문서 `docs/ai-security.md` + README에 짧은 요약·링크. Moderation 실패 시 차단 · 보안 문서 이름 루트 `SECURITY_GUIDE.md` · G3 재검토 Q1 초안 선스트리밍+완화책, Q2 입력 차단 질문 미저장·1회 차감(Moderation 장애 미차감), Q3 주민번호 검증번호 미사용, Q4 가린 모양 형식 유지+`*`(`010-****-****`). 2026-11-21 사용자 "진행" → requirements.md 개정 완료(§8 개정 이력), 이후 solution-architect로 architecture.md 수정 → requirements·stack-options·TECH_STACK·README·구성도 갱신 → G3 재승인
- 사용자: `.dev` 도메인 구입(Cloudflare Registrar) — 인프라 작업 전까지. Gmail 발신 계정·앱 비밀번호 — 메일 작업 전까지 `.env`에 직접
