"""
nadri DB ERD(docs/images/erd.svg)를 그린다.

테이블·컬럼의 한글 명칭은 DDL COMMENT의 정본이다 (architecture.md §5.1).
사용법: python3 docs/images/src/erd.py docs/images/erd.svg
PNG 변환: rsvg-convert -z 1.5 erd.svg -o erd.png (Noto Sans CJK 글꼴 필요)
"""
import sys
from xml.sax.saxutils import escape

W_BOX, ROW, HEAD = 540, 32, 58
COLS = [40, 690, 1340, 1990, 2640, 3290]
TOP = 150
GAP = 50

GROUPS = {
    "auth": ("#2563eb", "계정·인증"),
    "chat": ("#7c3aed", "대화"),
    "quota": ("#d97706", "한도·비용"),
    "quality": ("#db2777", "품질·보안"),
    "tour": ("#059669", "관광 데이터"),
    "ingest": ("#64748b", "수집 작업"),
}

# 테이블 → (그룹, 한글 명칭, [(키, 컬럼, 타입, 한글 명칭)])
T = {
    "users": ("auth", "사용자", [
        ("PK", "id", "bigint", "사용자 ID"), ("UK", "username", "text", "아이디"), ("UK", "email", "text", "이메일"),
        ("", "password_hash", "text", "비밀번호 해시"), ("", "role", "text", "권한"), ("", "status", "text", "가입 상태 ①"),
        ("", "created_at", "timestamptz", "가입 신청 일시"), ("", "approved_at", "timestamptz", "승인 일시"),
        ("FK", "approved_by", "bigint", "승인 관리자")]),
    "auth_sessions": ("auth", "로그인 세션", [
        ("PK", "id_hash", "text", "세션 키 해시"), ("FK", "user_id", "bigint", "사용자 ID"),
        ("", "created_at", "timestamptz", "로그인 일시"), ("", "last_seen_at", "timestamptz", "마지막 활동 일시"),
        ("", "expires_at", "timestamptz", "만료 일시")]),
    "password_reset_codes": ("auth", "비밀번호 재설정 코드", [
        ("PK", "id", "bigint", "코드 ID"), ("FK", "user_id", "bigint", "사용자 ID"), ("", "code_hash", "text", "인증코드 해시"),
        ("", "expires_at", "timestamptz", "만료 일시"), ("", "attempts", "int", "시도 횟수"),
        ("", "consumed_at", "timestamptz", "사용 일시")]),
    "rate_limits": ("auth", "요청 제한", [
        ("PK", "key", "text", "제한 키 ③"), ("", "window_start", "timestamptz", "집계 시작 일시"),
        ("", "count", "int", "횟수"), ("", "locked_until", "timestamptz", "잠금 해제 일시")]),
    "ingest_runs": ("ingest", "수집 실행 이력", [
        ("PK", "id", "bigint", "실행 ID"), ("", "kind", "text", "실행 종류"), ("", "started_at", "timestamptz", "시작 일시"),
        ("", "finished_at", "timestamptz", "종료 일시"), ("", "status", "text", "결과"), ("", "stats", "jsonb", "처리 통계"),
        ("", "lint", "jsonb", "점검 결과"), ("", "error", "text", "오류 메시지")]),
    "ingest_state": ("ingest", "수집 상태", [
        ("PK", "key", "text", "상태 키"), ("", "value", "jsonb", "상태 값")]),
    "daily_quota": ("quota", "일일 사용량", [
        ("PK FK", "user_id", "bigint", "사용자 ID"), ("PK", "day", "date", "사용일"),
        ("", "used", "int", "사용 횟수")]),
    "usage_events": ("quota", "사용량 이력", [
        ("PK", "id", "bigint", "이력 ID"), ("FK", "user_id", "bigint", "사용자 ID"), ("FK", "message_id", "bigint", "메시지 ID"),
        ("", "kind", "text", "사용 종류"), ("", "model", "text", "모델명"), ("", "input_tokens", "int", "입력 토큰"),
        ("", "cached_tokens", "int", "캐시 읽기 토큰"), ("", "cache_write_tokens", "int", "캐시 쓰기 토큰"),
        ("", "output_tokens", "int", "출력 토큰"), ("", "units", "numeric", "사용량"),
        ("", "cost_usd", "numeric", "비용(USD)"), ("", "ttft_ms", "int", "첫 토큰 지연"), ("", "total_ms", "int", "전체 소요"),
        ("", "tool_ms", "int", "툴 소요"), ("", "created_at", "timestamptz", "기록 일시")]),
    "chat_sessions": ("chat", "대화 세션", [
        ("PK", "id", "uuid", "대화 ID"), ("FK", "user_id", "bigint", "사용자 ID"), ("", "title", "text", "제목"),
        ("", "summary", "text", "요약"), ("", "turn_count", "int", "질문 수"), ("", "created_at", "timestamptz", "생성 일시"),
        ("", "updated_at", "timestamptz", "최종 대화 일시")]),
    "chat_messages": ("chat", "대화 메시지", [
        ("PK", "id", "bigint", "메시지 ID"), ("FK", "session_id", "uuid", "대화 ID"), ("", "turn_no", "int", "턴 번호"),
        ("", "role", "text", "발화자"), ("", "content", "text", "내용 (가린 텍스트)"), ("", "pii_types", "text[]", "가린 개인정보 종류"),
        ("", "tool_results", "jsonb", "툴 결과"), ("", "sources", "jsonb", "출처"), ("", "from_cache", "boolean", "캐시 여부"),
        ("FK", "faq_cache_id", "bigint", "FAQ 캐시 ID ⑤"), ("", "verify_status", "text", "검증 상태"),
        ("", "rewrite_count", "smallint", "다시 쓰기 횟수"), ("", "verification", "jsonb", "검증 기록"),
        ("", "timings", "jsonb", "지연 기록"), ("", "created_at", "timestamptz", "생성 일시")]),
    "faq_cache": ("chat", "FAQ 캐시", [
        ("PK", "id", "bigint", "캐시 ID"), ("FK", "source_message_id", "bigint", "원본 메시지 ID"),
        ("", "question", "text", "질문"), ("", "embedding", "vector(1536)", "질문 임베딩"), ("", "answer", "text", "답변"),
        ("", "sources", "jsonb", "출처"), ("", "contentids", "text[]", "근거 관광지 ID ②"), ("", "hit_count", "int", "재사용 횟수"),
        ("", "created_at", "timestamptz", "생성 일시")]),
    "message_feedback": ("quality", "답변 피드백", [
        ("PK FK", "message_id", "bigint", "메시지 ID"), ("FK", "user_id", "bigint", "사용자 ID ⑤"),
        ("", "rating", "text", "평가 (up / down)"), ("", "reason", "text", "비추천 사유 (선택)"),
        ("", "created_at", "timestamptz", "생성 일시"), ("", "updated_at", "timestamptz", "수정 일시")]),
    "security_events": ("quality", "보안 이벤트", [
        ("PK", "id", "bigint", "이벤트 ID"), ("FK", "user_id", "bigint", "사용자 ID ⑤"), ("FK", "session_id", "uuid", "대화 ID ⑤"),
        ("FK", "message_id", "bigint", "메시지 ID"), ("", "stage", "text", "검사 단계 (입력·출력)"),
        ("", "check_name", "text", "검사 종류"), ("", "outcome", "text", "처리 결과"), ("", "categories", "text[]", "탐지 분류"),
        ("", "excerpt", "text", "발췌 (가린 텍스트)"), ("", "detail", "jsonb", "세부 정보"),
        ("", "created_at", "timestamptz", "발생 일시")]),
    "eval_scores": ("quality", "턴별 채점", [
        ("PK", "id", "bigint", "채점 ID"), ("FK", "report_id", "bigint", "보고서 ID"), ("FK", "message_id", "bigint", "메시지 ID"),
        ("", "scores", "jsonb", "항목별 점수"), ("", "issues", "text", "지적 사항"), ("", "created_at", "timestamptz", "생성 일시")]),
    "eval_reports": ("quality", "품질 보고서", [
        ("PK", "id", "bigint", "보고서 ID"), ("UK", "report_date", "date", "대상 날짜"), ("", "status", "text", "상태"),
        ("", "stats", "jsonb", "집계"), ("", "body_md", "text", "보고서 본문"), ("", "model", "text", "모델명"),
        ("", "started_at", "timestamptz", "시작 일시"), ("", "finished_at", "timestamptz", "종료 일시"),
        ("", "error", "text", "오류 메시지")]),
    "improvement_proposals": ("quality", "개선안", [
        ("PK", "id", "bigint", "개선안 ID"), ("FK", "report_id", "bigint", "보고서 ID"), ("", "seq", "int", "순번"),
        ("", "target", "text", "개선 대상"), ("", "title", "text", "제목"), ("", "problem", "text", "문제"),
        ("", "evidence", "jsonb", "근거 발췌"), ("", "cause", "text", "원인 추정"), ("", "proposal", "text", "제안"),
        ("", "expected_effect", "text", "예상 효과"), ("", "cost_note", "text", "비용"), ("", "risk", "text", "위험"),
        ("", "priority", "text", "우선순위"), ("", "status", "text", "결정 상태 ④"), ("", "decision_note", "text", "결정 메모"),
        ("FK", "decided_by", "bigint", "결정 관리자 ⑤"), ("", "decided_at", "timestamptz", "결정 일시"),
        ("", "created_at", "timestamptz", "생성 일시")]),
    "tour_items": ("tour", "관광 정보", [
        ("PK", "contentid", "text", "관광지 ID"), ("", "content_type_id", "int", "관광 유형"), ("", "area", "text", "지역"),
        ("", "sigungu_code", "text", "시군구 코드"), ("", "title", "text", "명칭"), ("", "addr", "text", "주소"),
        ("", "lat · lng", "float8", "위도 · 경도"), ("", "tel", "text", "전화번호"), ("", "usetime", "text", "이용시간"),
        ("", "fee", "text", "이용요금"), ("", "restdate", "text", "휴무일"), ("", "event_start", "date", "행사 시작일"),
        ("", "event_end", "date", "행사 종료일"), ("", "extra", "jsonb", "유형별 상세"),
        ("", "modifiedtime", "timestamptz", "원천 수정 일시"), ("", "detail_synced_at", "timestamptz", "상세 수집 일시"),
        ("", "as_of", "date", "기준일"), ("", "deleted_at", "timestamptz", "삭제 일시"), ("", "updated_at", "timestamptz", "수정 일시")]),
    "wiki_pages": ("tour", "위키 페이지", [
        ("PK", "path", "text", "페이지 경로"), ("", "kind", "text", "페이지 종류"), ("FK", "contentid", "text", "관광지 ID"),
        ("", "title", "text", "제목"), ("", "area", "text", "지역"), ("", "sigungu_code", "text", "시군구 코드"),
        ("", "as_of", "date", "기준일"), ("", "content_hash", "text", "내용 해시"), ("", "lightrag_doc_id", "text", "RAG 문서 ID"),
        ("", "indexed_at", "timestamptz", "인덱싱 일시")]),
}

LAYOUT = [
    ["auth_sessions", "password_reset_codes", "rate_limits", "ingest_runs", "ingest_state"],
    ["users", "daily_quota", "usage_events"],
    ["chat_sessions", "chat_messages", "faq_cache"],
    ["message_feedback", "security_events", "eval_scores"],
    ["eval_reports", "improvement_proposals"],
    ["tour_items", "wiki_pages"],
]

# 1) 테이블 위치를 열 단위로 위에서부터 쌓는다
pos = {}
for ci, names in enumerate(LAYOUT):
    y = TOP
    for n in names:
        pos[n] = (COLS[ci], y)
        y += HEAD + ROW * len(T[n][2]) + GAP


def row_y(table, col):
    """테이블의 특정 컬럼 행 중앙 y."""
    x, y = pos[table]
    for i, r in enumerate(T[table][2]):
        if r[1] == col:
            return y + HEAD + ROW * i + ROW / 2
    raise KeyError(col)


def bottom(table):
    """테이블 박스 아래 끝 y."""
    return pos[table][1] + HEAD + ROW * len(T[table][2])


BODY_H = max(bottom(c[-1]) for c in LAYOUT)
H = BODY_H + 300
WIDTH = COLS[-1] + W_BOX + 90
out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{H}" viewBox="0 0 {WIDTH} {H}">']
out.append("""<defs>
<filter id="sh" x="-10%" y="-10%" width="120%" height="125%"><feDropShadow dx="0" dy="3" stdDeviation="5" flood-color="#0f172a" flood-opacity="0.10"/></filter>
<style>
text { font-family: 'Noto Sans CJK KR','Noto Sans KR','Malgun Gothic',sans-serif; }
.mono { font-family: 'Noto Sans Mono CJK KR','DejaVu Sans Mono',monospace; }
.tk { font-size: 22px; font-weight: 800; fill: #fff; }
.te { font-size: 18px; font-weight: 700; fill: #ffffffeb; }
.ck { font-size: 15.5px; fill: #0f172a; }
.cn { font-size: 15.5px; fill: #475569; }
.ct { font-size: 12.5px; fill: #94a3b8; }
.kb { font-size: 11px; font-weight: 700; }
.rl { font-size: 15px; font-weight: 800; fill: #334155; }
.lg { font-size: 16px; fill: #334155; }
.nt { font-size: 15px; fill: #475569; }
</style></defs>""")
out.append(f'<rect width="{WIDTH}" height="{H}" fill="#f8fafc"/>')
out.append('<text x="40" y="62" style="font-size:34px;font-weight:800;fill:#0f172a">nadri DB 구조 (ERD)</text>')
out.append('<text x="40" y="100" style="font-size:17px;fill:#475569">PostgreSQL 1대 안의 <tspan style="font-weight:700">nadri</tspan> DB — 우리 앱 테이블 18개. '
           'RAG용 벡터·그래프는 같은 PostgreSQL의 별도 DB <tspan style="font-weight:700">lightrag</tspan>에 있고 LightRAG가 직접 관리 (그림에 없음)</text>')

# 2) 관계선 — 테이블 박스보다 먼저 그려 박스 뒤로 깔리게 한다
lines = []


def rel(path, p_lab, c_lab, dashed=False, color="#64748b", hops=()):
    """
    꺾은선 관계를 그린다.

    Args:
        path: [(x, y), ...] 부모 → 자식 꼭짓점
        p_lab, c_lab: 양 끝 개수 라벨 (1, N, 0..1)
        dashed: FK 없는 논리 관계면 True
        hops: 다른 선과 교차하는 수평 구간의 x 좌표들 — 반원으로 넘어간다
    """
    # 1) 수평 구간에 교차점이 있으면 반원(hop)을 끼워 넣은 경로 문자열을 만든다
    d = f"M{path[0][0]:.0f} {path[0][1]:.0f}"
    for (x0, y0), (x1, y1) in zip(path, path[1:]):
        if y0 == y1:
            step = 1 if x1 > x0 else -1
            for hx in sorted((h for h in hops if min(x0, x1) < h < max(x0, x1)), reverse=step < 0):
                d += f" H{hx - 8 * step:.0f} A8 8 0 0 {1 if step > 0 else 0} {hx + 8 * step:.0f} {y0:.0f}"
        d += f" L{x1:.0f} {y1:.0f}"
    dash = ' stroke-dasharray="8 6"' if dashed else ""
    lines.append(f'<path d="{d}" fill="none" stroke="{color}" stroke-width="2.2"{dash}/>')
    # 2) 양 끝에 점과 개수 라벨
    for (x, y), (nx, _), lab in ((path[0], path[1], p_lab), (path[-1], path[-2], c_lab)):
        dx = 7 if nx > x else -7 - 8.5 * len(lab)
        lines.append(f'<circle cx="{x}" cy="{y}" r="4" fill="{color}"/>')
        lines.append(f'<text x="{x + dx}" y="{y - 8}" class="rl">{escape(lab)}</text>')


L = lambda t: pos[t][0]
R = lambda t: pos[t][0] + W_BOX
G12 = (COLS[0] + W_BOX + COLS[1]) / 2
G23, G34, G45, G56 = (COLS[i] + W_BOX for i in (1, 2, 3, 4))
uy = row_y("users", "id")
my = row_y("chat_messages", "id")
# 사용자 → 왼쪽 열 (계정·인증)
for t, gx in (("auth_sessions", G12 + 12), ("password_reset_codes", G12 - 12)):
    rel([(L("users"), uy), (gx, uy), (gx, row_y(t, "user_id")), (R(t), row_y(t, "user_id"))], "1", "N")
# 사용자 → 같은 열 아래 (한도·비용), 오른쪽 통로로 돌아 내려간다
for t, gx in (("daily_quota", G23 + 18), ("usage_events", G23 + 40)):
    rel([(R("users"), uy), (gx, uy), (gx, row_y(t, "user_id")), (R(t), row_y(t, "user_id"))], "1", "N")
# 사용자 → 대화
rel([(R("users"), uy), (G23 + 66, uy), (G23 + 66, row_y("chat_sessions", "user_id")),
     (L("chat_sessions"), row_y("chat_sessions", "user_id"))], "1", "N")
# 메시지 → 사용량 기록, 메시지 → FAQ 캐시 (왼쪽 통로)
rel([(L("chat_messages"), my), (G23 + 84, my), (G23 + 84, row_y("usage_events", "message_id")),
     (R("usage_events"), row_y("usage_events", "message_id"))], "1", "N")
rel([(L("chat_messages"), my), (G23 + 100, my), (G23 + 100, row_y("faq_cache", "source_message_id")),
     (L("faq_cache"), row_y("faq_cache", "source_message_id"))], "1", "0..1")
# 대화 → 메시지 (오른쪽 통로)
rel([(R("chat_sessions"), row_y("chat_sessions", "id")), (G34 + 20, row_y("chat_sessions", "id")),
     (G34 + 20, row_y("chat_messages", "session_id")), (R("chat_messages"), row_y("chat_messages", "session_id"))], "1", "N")
# 메시지 → 품질·보안 테이블 (오른쪽 통로, 대화→메시지 선을 넘어간다)
for t, gx, lab in (("message_feedback", G34 + 40, "0..1"), ("security_events", G34 + 58, "N"), ("eval_scores", G34 + 76, "N")):
    rel([(R("chat_messages"), my), (gx, my), (gx, row_y(t, "message_id")), (L(t), row_y(t, "message_id"))],
        "1", lab, hops=(G34 + 20,))
# 보고서 → 채점 (왼쪽 통로), 보고서 → 개선안 (오른쪽 통로)
ry = row_y("eval_reports", "id")
rel([(L("eval_reports"), ry), (G45 + 40, ry), (G45 + 40, row_y("eval_scores", "report_id")),
     (R("eval_scores"), row_y("eval_scores", "report_id"))], "1", "N")
rel([(R("eval_reports"), ry), (G56 + 22, ry), (G56 + 22, row_y("improvement_proposals", "report_id")),
     (R("improvement_proposals"), row_y("improvement_proposals", "report_id"))], "1", "N")
# 관광지 → 위키 페이지 (오른쪽 바깥 통로)
gx = R("tour_items") + 44
rel([(R("tour_items"), row_y("tour_items", "contentid")), (gx, row_y("tour_items", "contentid")),
     (gx, row_y("wiki_pages", "contentid")), (R("wiki_pages"), row_y("wiki_pages", "contentid"))], "1", "N")
# FAQ 캐시 ··· 관광지 (FK 없는 논리 관계) — 모든 표 아래로 돌아간다
band = BODY_H + 26
fy = row_y("faq_cache", "contentids")
rel([(R("faq_cache"), fy), (G34 + 94, fy), (G34 + 94, band), (G56 + 70, band),
     (G56 + 70, row_y("tour_items", "contentid")), (L("tour_items"), row_y("tour_items", "contentid"))],
    "N", "N", dashed=True, color="#059669")
out += lines

# 3) 테이블 박스: 머리글은 영문 테이블명 + 한글 명칭(COMMENT), 행은 컬럼명 → 한글 명칭 → 타입
KEY_COLOR = {"PK": "#b45309", "FK": "#1d4ed8", "UK": "#0f766e", "PK FK": "#b45309"}
for n, (g, kname, rows) in T.items():
    x, y = pos[n]
    color = GROUPS[g][0]
    h = HEAD + ROW * len(rows)
    out.append(f'<g filter="url(#sh)"><rect x="{x}" y="{y}" width="{W_BOX}" height="{h}" rx="10" fill="#fff" stroke="{color}" stroke-width="1.5"/></g>')
    out.append(f'<path d="M{x} {y + HEAD} V{y + 10} Q{x} {y} {x + 10} {y} H{x + W_BOX - 10} Q{x + W_BOX} {y} {x + W_BOX} {y + 10} V{y + HEAD} Z" fill="{color}"/>')
    out.append(f'<text x="{x + 18}" y="{y + 37}" class="tk mono">{n}</text>')
    out.append(f'<text x="{x + W_BOX - 18}" y="{y + 37}" class="te" text-anchor="end">{escape(kname)}</text>')
    for i, (k, c, ty, ko) in enumerate(rows):
        ry_ = y + HEAD + ROW * i
        if i % 2:
            out.append(f'<rect x="{x + 1.5}" y="{ry_}" width="{W_BOX - 3}" height="{ROW}" fill="#f1f5f9"/>')
        cy = ry_ + ROW / 2 + 5.5
        if k:
            bc = KEY_COLOR[k]
            bw = 48 if k == "PK FK" else 28
            out.append(f'<rect x="{x + 12}" y="{ry_ + 7}" width="{bw}" height="18" rx="4" fill="{bc}1a" stroke="{bc}" stroke-width="1"/>')
            out.append(f'<text x="{x + 12 + bw / 2}" y="{ry_ + 20.5}" class="kb" fill="{bc}" text-anchor="middle">{k}</text>')
        out.append(f'<text x="{x + 70}" y="{cy}" class="ck mono">{escape(c)}</text>')
        out.append(f'<text x="{x + 270}" y="{cy}" class="cn">{escape(ko)}</text>')
        out.append(f'<text x="{x + W_BOX - 14}" y="{cy}" class="ct mono" text-anchor="end">{escape(ty)}</text>')

# 4) 범례·주석
ly = BODY_H + 80
out.append(f'<line x1="40" y1="{ly - 22}" x2="{WIDTH - 40}" y2="{ly - 22}" stroke="#cbd5e1"/>')
lx = 40
for g, (c, name) in GROUPS.items():
    out.append(f'<rect x="{lx}" y="{ly}" width="20" height="20" rx="4" fill="{c}"/><text x="{lx + 28}" y="{ly + 16}" class="lg">{name}</text>')
    lx += 165
for k, txt in (("PK", "기본키 (행을 구분하는 값)"), ("FK", "외래키 (다른 테이블을 가리킴)"), ("UK", "중복 불가")):
    bc = KEY_COLOR[k]
    out.append(f'<rect x="{lx}" y="{ly + 1}" width="28" height="18" rx="4" fill="{bc}1a" stroke="{bc}"/><text x="{lx + 14}" y="{ly + 14.5}" class="kb" fill="{bc}" text-anchor="middle">{k}</text>'
               f'<text x="{lx + 36}" y="{ly + 16}" class="lg">{txt}</text>')
    lx += 60 + 15 * len(txt)
ly2 = ly + 42
out.append(f'<line x1="40" y1="{ly2 + 10}" x2="100" y2="{ly2 + 10}" stroke="#64748b" stroke-width="2.2"/>'
           f'<text x="112" y="{ly2 + 16}" class="lg">관계선 — 끝의 1·N은 개수 (예: 사용자 1명 ─ 대화 N개)</text>')
out.append(f'<line x1="760" y1="{ly2 + 10}" x2="820" y2="{ly2 + 10}" stroke="#059669" stroke-width="2.2" stroke-dasharray="8 6"/>'
           f'<text x="832" y="{ly2 + 16}" class="lg">외래키 없이 ID 값만 저장한 연결</text>')
for i, note in enumerate((
        "① 가입 상태: pending 승인 대기 · active 사용 중 · rejected 거절 · disabled 정지      "
        "② 답변 출처에서 뽑은 관광지 ID 목록 — 밤 수집에서 그 관광지가 바뀌면 이 ID가 든 캐시를 지움",
        "③ 예: login:ip:1.2.3.4 (IP별 로그인 실패 횟수)      "
        "④ 결정 상태: new 미결정 · adopted 채택 · held 보류 · rejected 기각 (관리자가 결정, 자동 적용 없음)",
        "⑤ 선을 생략한 외래키: 사용자 ID → users, 대화 ID → chat_sessions, FAQ 캐시 ID → faq_cache, 결정 관리자 → users      "
        "· 위치 좌표·대화 원문(가리기 전)은 어떤 테이블에도 저장하지 않음",
        "· 한글 명칭은 실제 DDL의 COMMENT로 그대로 들어감      · 주요 규칙: 세션 유휴 2시간·최대 7일 / 인증코드 10분·5회 / 대화당 질문 50개 / 대화·피드백·보안 이벤트·보고서 90일 후 삭제")):
    out.append(f'<text x="40" y="{ly2 + 58 + 28 * i}" class="nt">{escape(note)}</text>')
out.append("</svg>")
open(sys.argv[1], "w").write("\n".join(out))
