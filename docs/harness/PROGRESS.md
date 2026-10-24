# PROGRESS
- 현재 단계: Phase 1 — 요구사항 (초안 작성 완료, 미해결 질문 답변 대기)
- 게이트: G1 ⏳ · G2 · G3 · G4 · G5 (작업별, 아래 표)
- 다음 할 일: 사용자에게 Q1~Q18 답변 받기 → `requirements.md`에 반영 → 확정본 제시 → G1 승인 요청

| 작업id | spec/test | 브랜치 | 구현·테스트 | 커밋 | G5 병합 |
|---|---|---|---|---|---|
| (G4 승인 후 작성) | | | | | |

## 산출물
- `docs/harness/requirements.md` — 초안 (2026-10-24). 확정 전제 D-01~D-20, FR/NFR, 미해결 질문 Q1~Q18, 상충 기록 C1~C11

## 결정 로그 (게이트에서 바뀐 것)
- 2026-10-25 (G1 전): 리버스 프록시 Caddy → **Nginx** (사용자 결정). requirements D-15·NFR-08, TECH_STACK, README, 구성도 반영. Nginx는 인증서 자동 발급이 없어 인증서 준비 방식은 Q4에서 함께 결정
- 2026-10-25 (G1 전): 프로젝트 이름 **nadri** 확정 (README·구성도 제목). 로컬 디렉터리는 `myAgent` 유지
- 2026-10-25 (G1 전): 확장 데이터 원천 4곳(비짓제주, 서울 실시간 도시데이터, 문화데이터광장, 관광빅데이터)을 MVP 이후 항목으로 추가 — requirements FR-49, `docs/analysis/01-data-sources.md`, 구성도 반영. 크롤링은 기본 미사용

## 기타 산출물
- `README.md`, `.gitignore`, `docs/images/architecture.svg`·`architecture.png` (구성도, SVG가 원본)

## 막힌 것 / 사용자 확인 필요
- Q1~Q18 답변 대기 (질문·선택지·추천안은 `requirements.md` §6 및 2026-10-24 세션 대화 참조)
- 미해소 상충: C3(웹 검색 툴 포함 여부 → Q8), C8(기준 브랜치 master/main → Q13)
