"""
nadri 구성도(docs/images/architecture.svg)를 그린다 — architecture.md §14 사양.

스타일(defs)과 아이콘은 같은 폴더의 icons.json에서 읽는다.
사용법: python3 docs/images/src/arch.py docs/images/architecture.svg
PNG 변환: rsvg-convert -z 2 architecture.svg -o architecture.png (Noto Sans CJK 글꼴 필요)
"""
import json
import os
import re
import sys

ICON = json.load(open(os.path.join(os.path.dirname(__file__), "icons.json")))

W, H = 1960, 1420
out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">', ICON["_defs"],
       '<style>.cht { font-size: 15px; font-weight: 700; } .chs { font-size: 12.5px; fill: #475569; } '
       '.nl { font-size: 21px; font-weight: 700; fill: #0f172a; } .sl { font-size: 15px; fill: #64748b; }</style>',
       '<rect width="100%" height="100%" fill="#ffffff"/>', '<rect width="100%" height="100%" fill="url(#dots)"/>',
       '<text x="40" y="76" class="h1">nadri</text>',
       '<text x="40" y="110" class="h2">관광 챗봇 아키텍처</text>',
       '<text x="40" y="136" class="h2">한국관광공사 TourAPI 기반</text>']


def place(icon, x, y):
    """아이콘 SVG 조각을 (x, y)에 놓는다."""
    return icon.replace("<svg", f'<svg x="{x}" y="{y}"', 1)


def group(x, y, w, h, color, label, dashed=False, fill=0.045, label_pos="top"):
    """배경 영역(그룹)과 이름표."""
    dash = ' stroke-dasharray="7 5"' if dashed else ""
    out.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="18" fill="{color}" fill-opacity="{fill}" stroke="{color}" stroke-opacity="0.4" stroke-width="1.6"{dash}/>')
    if label_pos == "top":
        lx, ly, anchor = x + 18, y + 31, "start"
    elif label_pos == "bottom":
        lx, ly, anchor = x + 18, y + h - 16, "start"
    else:  # bottom-right
        lx, ly, anchor = x + w - 44, y + h - 16, "end"
    out.append(f'<text x="{lx}" y="{ly}" class="ft" fill="{color}" text-anchor="{anchor}">{label}</text>')


# 1) 영역
out.append('<rect x="400" y="350" width="1530" height="790" rx="18" fill="none" stroke="#475569" stroke-opacity="0.4" stroke-width="1.6" stroke-dasharray="7 5"/>')
out.append(place(ICON["_docker"], 414, 1103))
out.append('<text x="446" y="1122" class="ft" fill="#475569">Docker Compose 내부 네트워크 <tspan class="fs">· 호스트 인바운드 포트 없음 · 에이전트는 api 안 LangGraph (stateless)</tspan></text>')
group(425, 400, 170, 470, "#ea580c", "진입")
group(640, 400, 520, 232, "#2563eb", "API", label_pos="bottom-right")
group(640, 642, 220, 228, "#2563eb", "화면")
group(900, 642, 240, 228, "#7c3aed", "툴")
group(1180, 400, 730, 722, "#059669", "데이터")
group(1600, 428, 290, 452, "#0f766e", "데이터 볼륨", dashed=True, fill=0.04, label_pos="bottom-right")
out.append('<rect x="1300" y="1160" width="630" height="150" rx="18" fill="#f8fafc" stroke="#64748b" stroke-opacity="0.6" stroke-width="1.6" stroke-dasharray="7 5"/>')
out.append(place(ICON["_layers"], 1316, 1173))
out.append('<text x="1348" y="1192" class="ft" fill="#64748b">확장 데이터 원천 <tspan class="fs">v1.1 이후</tspan></text>')

# 2) 연결선 (타일보다 먼저 그려 뒤로 깔리게)
STYLE = {"req": ("#2563eb", ""), "tool": ("#7c3aed", ""), "data": ("#059669", ""),
         "ext": ("#64748b", ' stroke-dasharray="7 5"')}


def line(d, kind):
    """화살표 하나. d는 SVG path 문자열."""
    c, dash = STYLE[kind]
    out.append(f'<path d="{d}" fill="none" stroke="{c}" stroke-width="2.2" stroke-linejoin="round"{dash} marker-end="url(#m{c[1:]})"/>')


# 사용자 요청 경로
line("M152 470 H205 V565 H252", "req")
line("M152 690 H205 V595 H252", "req")
line("M342 580 H400 V470 H462", "req")
line("M510 575 V640", "req")
line("M552 705 H702", "req")
line("M552 675 H612 V480 H654", "req")
# API(LangGraph) → 툴
line("M1020 622 V640", "tool")
# 데이터 흐름
line("M1062 675 H1165 V470 H1252", "data")
line("M1062 705 H1252", "data")
line("M1300 575 V640", "data")
line("M880 622 V890 H1205 V722 H1252", "data")
line("M1468 912 H1405 V715 H1348", "data")
line("M1510 888 V500 H1348", "data")
line("M1552 915 H1640 V690 H1672", "data")
line("M1552 950 H1870 V470 H1768", "data")
line("M1625 815 H1545 V880", "data")
# 외부 서비스 호출
line("M690 420 V330 H470 V208", "ext")
line("M710 420 V300 H620 V240", "ext")
line("M760 420 V262 H1000 V240", "ext")
line("M900 420 V285 H1015 V240", "ext")
line("M1100 420 V330 H1300 V208", "ext")
line("M1315 428 V290 H1308 A8 8 0 0 0 1292 290 H1050 V240", "ext")
line("M1552 968 H1945 V20 H1060 V44", "ext")
line("M1020 862 V882 A8 8 0 0 1 1020 898 V1162", "ext")
line("M1468 960 H1080 V1162", "ext")
line("M1330 1160 V1086", "ext")


# 3) 타일
def tile(cx, top, title, sub, pill=None, pill_color="#db2777"):
    """아이콘 타일 + 제목·부제 (+ 교체 가능 구현체 알약)."""
    x = cx - 42
    out.append(f'<rect x="{x}" y="{top}" width="84" height="84" rx="20" fill="#ffffff" stroke="#e2e8f0" stroke-width="1.5" filter="url(#sh)"/>')
    out.append(place(ICON[title], x + 17, top + 17))
    out.append(f'<text x="{cx}" y="{top + 114}" class="nt">{title}</text>')
    out.append(f'<text x="{cx}" y="{top + 137}" class="ns">{sub}</text>')
    if pill:
        pw = 30 + 9.5 * len(pill)
        out.append(f'<rect x="{cx - pw / 2}" y="{top + 151}" width="{pw}" height="26" rx="13" fill="#fff" stroke="{pill_color}" stroke-width="1.6" stroke-dasharray="4 3"/>')
        out.append(f'<text x="{cx}" y="{top + 169}" class="pl" fill="{pill_color}">{pill}</text>')


def chips(cx, top, names, color="#7c3aed"):
    """타일 아래 2열 칩 (툴 이름 등)."""
    for i, chip in enumerate(names):
        x = cx - 55 + 114 * (i % 2) - 57 * (len(names) > 1)
        y = top + 30 * (i // 2)
        out.append(f'<rect x="{x - 55}" y="{y}" width="110" height="25" rx="6" fill="#f5f3ff" stroke="#ddd6fe"/>')
        out.append(f'<text x="{x}" y="{y + 17.5}" class="ch">{chip}</text>')


tile(110, 428, "사용자", "PC · 모바일 PWA")
tile(110, 648, "관리자", "백오피스 /admin")
tile(300, 538, "Cloudflare", "HTTPS · .dev 도메인")
tile(510, 428, "cloudflared", "Named Tunnel")
tile(510, 648, "Nginx", "SSE 버퍼링 off")

# FastAPI 카드: 입력 검사 → [LangGraph: 답변 에이전트 ⇄ 검증 에이전트] → 출력 검사
def agent_box(x, y, w, title, sub, h=76):
    """에이전트(LLM이 판단·반복하는 단위)를 로봇 아이콘이 있는 상자로 그린다."""
    out.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="12" fill="#ede9fe" stroke="#7c3aed" stroke-width="1.8"/>')
    out.append(place(ICON["agent"], x + w / 2 - 12, y + 6).replace('width="50" height="50"', 'width="24" height="24"'))
    out.append(f'<text x="{x + w / 2}" y="{y + 48}" class="cht" fill="#5b21b6" text-anchor="middle">{title}</text>')
    out.append(f'<text x="{x + w / 2}" y="{y + 66}" class="chs" text-anchor="middle">{sub}</text>')


def check_box(x, y, w, title, sub1, sub2, h=76):
    """보안 검사 단계 상자."""
    out.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="10" fill="#fef2f2" stroke="#dc2626" stroke-opacity="0.5"/>')
    out.append(f'<text x="{x + w / 2}" y="{y + 26}" class="cht" fill="#dc2626" text-anchor="middle">{title}</text>')
    out.append(f'<text x="{x + w / 2}" y="{y + 47}" class="chs" text-anchor="middle">{sub1}</text>')
    out.append(f'<text x="{x + w / 2}" y="{y + 64}" class="chs" text-anchor="middle">{sub2}</text>')


out.append('<rect x="660" y="420" width="490" height="200" rx="16" fill="#ffffff" stroke="#e2e8f0" stroke-width="1.5" filter="url(#sh)"/>')
out.append(place(ICON["FastAPI"], 676, 432).replace('width="50" height="50"', 'width="40" height="40"'))
out.append('<text x="728" y="456" class="nl">FastAPI · api</text>')
out.append('<text x="728" y="478" class="sl">BFF · 인증 · 한도 · 대화 · 피드백 · STT/TTS</text>')
out.append('<rect x="788" y="492" width="234" height="122" rx="12" fill="#faf5ff" stroke="#7c3aed" stroke-width="1.4" stroke-dasharray="5 4"/>')
check_box(670, 500, 112, "입력 검사", "PII · Moderation", "LLM 분류기")
agent_box(796, 500, 102, "답변 에이전트", "툴 5개로 초안")
agent_box(912, 500, 102, "검증 에이전트", "툴 결과와 대조")
check_box(1034, 500, 112, "출력 검사", "링크 · ID", "카나리")
out.append('<text x="905" y="606" class="chs" text-anchor="middle" style="fill:#6d28d9;font-weight:700">LangGraph · 실패 시 다시 쓰기 ≤2</text>')
out.append('<path d="M782 538 H792" stroke="#94a3b8" stroke-width="2" marker-end="url(#m64748b)"/>')
out.append('<path d="M898 528 H908" stroke="#7c3aed" stroke-width="2" marker-end="url(#m7c3aed)"/>')
out.append('<path d="M912 552 H902" stroke="#7c3aed" stroke-width="2" marker-end="url(#m7c3aed)"/>')
out.append('<path d="M1022 538 H1030" stroke="#94a3b8" stroke-width="2" marker-end="url(#m64748b)"/>')

tile(750, 648, "Next.js", "채팅 · PWA · 관리자 화면")
tile(1020, 648, "tour-tools", "MCP 서버 · 리랭커")
chips(1077, 798, ("rag_query", "data_query", "tour_live", "get_datetime"))
tile(1300, 428, "LightRAG", "Graph RAG (후보 30개 검색)")
tile(1300, 648, "PostgreSQL", "pgvector · DB 2개")
tile(1720, 428, "LLM Wiki", "엔티티 · 허브 (git)")
tile(1720, 648, "raw 스냅샷", "TourAPI 응답 원본")
out.append('<rect x="1625" y="795" width="240" height="40" rx="10" fill="#ffffff" stroke="#0f766e" stroke-opacity="0.5" filter="url(#sh2)"/>')
out.append('<text x="1745" y="821" class="xp">eval/ · 골든 · 공격 세트</text>')
tile(1510, 888, "ingest", "01:00 수집 · 03:00 평가")
out.append('<rect x="1270" y="1040" width="150" height="40" rx="8" fill="#ecfdf5" stroke="#a7f3d0"/>')
out.append('<text x="1345" y="1065" class="ch" style="fill:#047857">수집 · 위키 · 인덱싱</text>')
agent_box(1440, 1036, 118, "평가 에이전트", "03:00 전날 대화 채점", h=72)
agent_box(1582, 1036, 132, "개선안 에이전트", "→ 관리자 결정(HITL)", h=72)
out.append('<path d="M1558 1072 H1578" stroke="#7c3aed" stroke-width="2" marker-end="url(#m7c3aed)"/>')
tile(470, 48, "Gmail SMTP", "인증코드 메일")
tile(620, 48, "TTS", "ElevenLabs", pill="+ Drama 3")
tile(1020, 48, "OpenAI API", "gpt-6-luna · 임베딩 · STT · Moderation", pill="+ faster-whisper (STT)")
tile(1300, 48, "Tavily", "웹 검색")
tile(1020, 1168, "TourAPI 4.0", "한국관광공사")
for i, name in enumerate(("비짓제주 관광정보", "서울 실시간 도시데이터", "문화데이터광장 · 전시/공연", "관광빅데이터 · 방문자 수")):
    x = 1320 + 300 * (i % 2)
    y = 1212 + 46 * (i // 2)
    out.append(f'<rect x="{x}" y="{y}" width="290" height="36" rx="10" fill="#ffffff" stroke="#cbd5e1" filter="url(#sh2)"/>')
    out.append(f'<text x="{x + 145}" y="{y + 24}" class="xp">{name}</text>')

# 4) 선 라벨
LABELS = [
    (205, 520, "HTTPS", "#2563eb", "middle"), (372, 568, "터널", "#2563eb", "middle"),
    (520, 614, "HTTP :80", "#2563eb", "start"), (618, 632, "/api/* (SSE)", "#2563eb", "start"),
    (627, 735, "/ · /admin", "#2563eb", "middle"),
    (1030, 638, "MCP", "#7c3aed", "start"),
    (1208, 460, "rag_query", "#059669", "middle"), (1200, 695, "data_query", "#059669", "middle"),
    (1310, 614, "벡터 · 그래프", "#059669", "start"), (1034, 918, "사용자 · 대화 · 한도 · 사용량 · 피드백 · 보안 이벤트", "#059669", "start"),
    (1398, 840, "정형 upsert · 보고서", "#059669", "end"), (1430, 488, "문서 교체", "#059669", "middle"),
    (1596, 680, "저장", "#059669", "middle"), (1790, 940, "렌더링 · git 커밋", "#059669", "middle"),
    (1588, 806, "공격 세트", "#059669", "middle"),
    (600, 322, "인증코드", "#64748b", "middle"), (665, 292, "TTS", "#64748b", "middle"),
    (850, 236, "분류 · 답변 · 검증", "#64748b", "middle"), (850, 255, "제목 · 요약 · 임베딩 · STT", "#64748b", "middle"),
    (955, 310, "Moderation", "#64748b", "middle"),
    (1200, 322, "웹 검색", "#64748b", "middle"), (1325, 380, "인덱싱 · 임베딩", "#64748b", "start"),
    (1500, 40, "허브 · 평가 · 개선안 · 공격 세트", "#64748b", "middle"),
    (1010, 1010, "tour_live", "#64748b", "end"), (1270, 952, "변경분 동기화 · 상세 수집", "#64748b", "middle"),
    (1340, 1150, "추후 연동", "#64748b", "start"),
]
for x, y, t, c, a in LABELS:
    out.append(f'<text x="{x}" y="{y}" class="el" fill="{c}" text-anchor="{a}">{t}</text>')

# 5) 범례
ly = 1180
for i, (c, dash, t) in enumerate((("#2563eb", "", "사용자 요청"), ("#059669", "", "데이터 흐름"),
                                  ("#7c3aed", "", "에이전트 → 툴 (MCP)"), ("#64748b", ' stroke-dasharray="7 5"', "외부 서비스 호출"))):
    y = ly + 32 * i
    out.append(f'<line x1="40" y1="{y}" x2="88" y2="{y}" stroke="{c}" stroke-width="2.4"{dash}/><text x="100" y="{y + 6}" class="lg">{t}</text>')
y = ly + 32 * 4
out.append(f'<rect x="40" y="{y - 11}" width="48" height="22" rx="11" fill="#fff" stroke="#db2777" stroke-width="1.6" stroke-dasharray="4 3"/><text x="100" y="{y + 6}" class="lg">교체 가능한 구현체 (확장)</text>')
y += 32
out.append(f'<rect x="40" y="{y - 11}" width="48" height="22" rx="6" fill="#fef2f2" stroke="#dc2626" stroke-opacity="0.5"/><text x="100" y="{y + 6}" class="lg">보안 검사 (입력 · 출력)</text>')
y += 32
out.append(f'<rect x="40" y="{y - 13}" width="48" height="26" rx="7" fill="#ede9fe" stroke="#7c3aed" stroke-width="1.8"/>')
out.append(place(ICON["agent"], 52, y - 12).replace('width="50" height="50"', 'width="24" height="24"'))
out.append(f'<text x="100" y="{y + 6}" class="lg">에이전트 (LLM이 판단·반복)</text>')
out.append("</svg>")
open(sys.argv[1], "w").write("\n".join(out))
