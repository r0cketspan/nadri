# PROGRESS
- 현재 단계: Phase 2a — 기술스택 후보 (시작 전)
- 게이트: G1 ✅ (2026-11-07) · G2 ⏳ · G3 · G4 · G5 (작업별, 아래 표)
- 다음 할 일: Phase 2a — `solution-architect` 에이전트에 requirements.md(G1 승인본)·TECH_STACK.md(초안)를 넘겨 기술스택 후보·트레이드오프 제시 → 사용자 선택(G2). requirements §6 "G2/PoC로 넘기는 항목"이 주요 결정 대상
- 브랜치: `dev`(작업 기준) · `prod`(릴리스). 2026-11-07 로컬 `master` → `prod` 이름 변경, `dev` 생성. 원격 반영(push·기본 브랜치 변경·원격 master 삭제)은 사용자가 직접

| 작업id | spec/test | 브랜치 | 구현·테스트 | 커밋 | G5 병합 |
|---|---|---|---|---|---|
| (G4 승인 후 작성) | | | | | |

## 산출물
- `docs/harness/requirements.md` — **G1 승인본** (2026-11-07). 확정 전제 D-01~D-22, FR/NFR, G1 직전 확인 O1~O6, G2/PoC 이관 항목, 상충 기록 C1~C12
- `docs/analysis/01-data-sources.md` — 확장 데이터 원천 조사

## 결정 로그 (게이트에서 바뀐 것)
- 2026-10-25 (G1 전): 리버스 프록시 Caddy → **Nginx**
- 2026-10-25 (G1 전): 프로젝트 이름 **nadri**. 로컬 디렉터리는 `myAgent` 유지
- 2026-10-25 (G1 전): 확장 데이터 원천 4곳을 MVP 이후 항목으로 추가(FR-49). 크롤링 기본 미사용
- 2026-11-07 (G1 전, Q1~Q18 답변): 관리자 백오피스 + 챗봇 PWA · 가입 신청→관리자 승인 · 이메일 인증코드 비밀번호 재설정 · 본인 데모 · Cloudflare Tunnel로 HTTPS · 서울+제주 8종 · 매일 01:00 현행화 · 1인 하루 50회(초과 시 추가요청→관리자 승인 +50) · 웹 검색 Tavily · Hermes만 사용(OpenAI SDK 비교는 MVP 이후 실험) · TTS ElevenLabs(Edge 제외) · dev/prod 브랜치 · 위치 정보는 동의 시에만 · 세션 단위 삭제 
- 2026-11-07 (G1 전, O1~O6): 개발 중 Cloudflare 임시 주소·데모 전 도메인 구입 · 인증코드 10분/5회 · 월 $10 초과 시 경고만 · **답변 이미지 표시 안 함** · 비교 실험 MVP 이후 포함 · 첫 관리자 CLI 생성·사용자 비활성화 포함

## 기타 산출물
- `README.md`, `.gitignore`, `docs/images/architecture.svg`·`architecture.png` (구성도, SVG가 원본)
- 구성도·TECH_STACK에는 아직 백오피스·Tavily·ElevenLabs 단독·Cloudflare Tunnel 미반영 → G2/G3 결과로 함께 갱신

## 막힌 것 / 사용자 확인 필요
- 없음 (G2 진행 대기)
