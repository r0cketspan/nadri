# nadri 백엔드 이미지 — 타깃 app(ingest, 02부터 api) / tools(tour-tools, 리랭커 int8 ONNX 모델 포함)
# 빌드: docker compose build  (레포 루트에서)

# uv 바이너리(버전 고정)
FROM ghcr.io/astral-sh/uv:0.13.10 AS uv

# 1) 공통 기반: Python 3.12 + uv, 비루트 사용자, 데이터 폴더
FROM python:3.12-slim AS base
COPY --from=uv /uv /uvx /usr/local/bin/
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PATH=/app/.venv/bin:$PATH \
    PYTHONUNBUFFERED=1
# 빈 named volume을 처음 마운트할 때 이 소유권이 복사되어 비루트로 쓸 수 있다
RUN groupadd -g 10001 nadri \
    && useradd -u 10001 -g nadri -m -s /usr/sbin/nologin nadri \
    && mkdir -p /data/wiki /data/raw \
    && chown -R nadri:nadri /data
WORKDIR /app
COPY pyproject.toml uv.lock ./

# 2) app: 리랭커 없이. 기본 명령은 테이블 생성 스크립트 적용 후 종료
FROM base AS app
RUN uv sync --frozen --no-dev --no-group reranker --no-install-project
COPY alembic.ini ./
COPY alembic ./alembic
COPY src ./src
RUN uv sync --frozen --no-dev --no-group reranker
USER nadri
CMD ["alembic", "upgrade", "head"]

# 3) reranker-export: 빌드 전용 — torch로 가중치를 ONNX로 내보내고 int8 양자화(이 스테이지는 최종 이미지에 안 들어감)
FROM base AS reranker-export
RUN uv sync --frozen --only-group reranker-export --no-install-project
# BAAI/bge-reranker-v2-m3 — 커밋 고정, 모델 파일만
RUN python -c "from huggingface_hub import snapshot_download; snapshot_download('BAAI/bge-reranker-v2-m3', revision='953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e', local_dir='/build/hf', allow_patterns=['*.json', '*.safetensors', 'sentencepiece.bpe.model'])"
COPY scripts/export_reranker_onnx.py ./
RUN python export_reranker_onnx.py /build/hf /opt/models/bge-reranker-v2-m3

# 4) tools: 리랭커 런타임(onnxruntime·tokenizers, torch 없음) + 빌드 스테이지가 만든 int8 ONNX 모델
FROM base AS tools
RUN uv sync --frozen --no-dev --group reranker --no-install-project
COPY --from=reranker-export /opt/models/bge-reranker-v2-m3 /opt/models/bge-reranker-v2-m3
COPY alembic.ini ./
COPY alembic ./alembic
COPY src ./src
RUN uv sync --frozen --no-dev --group reranker
USER nadri
EXPOSE 8000
CMD ["nadri-tools"]
