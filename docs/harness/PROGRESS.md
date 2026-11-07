# PROGRESS
- 현재 단계: Phase 2b — 아키텍처 설계 (시작 전)
- 게이트: G1 ✅ (2026-11-07) · G2 ✅ (2026-11-07) · G3 ⏳ · G4 · G5 (작업별, 아래 표)
- 다음 할 일: Phase 2b — `solution-architect`에 requirements.md·stack-options.md(G2 확정)·TECH_STACK.md를 넘겨 architecture.md 작성 → G3. 미검증 가정(Hermes toolset 화이트리스트·memory off·gpt-6-luna 툴 호출, LightRAG `/query/data`·한국어 추출, CPU 리랭커 지연)은 가정+대안으로 표시하고 첫 구현 작업에서 검증. 구성도(architecture.svg) 갱신 포함
- 브랜치: `dev`(작업 기준) · `prod`(릴리스). 2026-11-07 로컬 `master` → `prod` 이름 변경, `dev` 생성. 원격 반영(push·기본 브랜치 변경·원격 master 삭제)은 사용자가 직접

| 작업id | spec/test | 브랜치 | 구현·테스트 | 커밋 | G5 병합 |
|---|---|---|---|---|---|
| (G4 승인 후 작성) | | | | | |

## 산출물
- `docs/harness/requirements.md` — **G1 승인본** (2026-11-07). 확정 전제 D-01~D-22, FR/NFR, G1 직전 확인 O1~O6, G2/PoC 이관 항목, 상충 기록 C1~C12
- `docs/analysis/01-data-sources.md` — 확장 데이터 원천 조사
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

## 기타 산출물
- `README.md`, `.gitignore`, `docs/images/architecture.svg`·`architecture.png` (구성도, SVG가 원본)
- TECH_STACK·README·requirements는 G2 결과 반영 완료. 구성도(architecture.svg)는 아직 백오피스·Tavily·Cloudflare Tunnel 미반영 → G3에서 갱신

## 막힌 것 / 사용자 확인 필요
- 사용자: `.dev` 도메인 구입(Cloudflare Registrar) — 인프라 작업 전까지. Gmail 발신 계정·앱 비밀번호 — 메일 작업 전까지 `.env`에 직접
