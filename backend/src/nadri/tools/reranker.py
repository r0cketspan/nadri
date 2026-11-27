"""bge-reranker-v2-m3 CrossEncoder(CPU) 래퍼와 상위 k 선택."""

import asyncio
from collections.abc import Sequence


class CrossEncoderReranker:
    """bge-reranker-v2-m3 CrossEncoder를 CPU에서 돌려 질문-문단 쌍 점수를 낸다. sentence_transformers는 생성자에서 지연 import."""

    def __init__(self, model_path: str, max_length: int = 512) -> None:
        """
        모델을 메모리에 올린다(수 초 걸림 — 서버 기동 때 1회).

        Args:
            model_path: 이미지에 내려받아 둔 가중치 폴더(HF_HUB_OFFLINE=1, 런타임 다운로드 없음)
            max_length: 질문+문단 최대 토큰 수(A9 대안: 256으로 낮추면 빨라짐)
        """
        # 리랭커 그룹이 없는 개발·테스트 환경에서도 이 모듈을 import할 수 있게 여기서 import한다
        from sentence_transformers import CrossEncoder

        self._model = CrossEncoder(model_path, max_length=max_length, device="cpu")

    def score(self, query: str, passages: Sequence[str]) -> list[float]:
        """
        질문과 각 문단의 관련도 점수를 낸다(블로킹 — rerank가 스레드에서 부름).

        Args:
            query: 질문
            passages: 후보 문단들

        Returns:
            passages와 같은 순서의 점수 목록
        """
        return [float(s) for s in self._model.predict([(query, p) for p in passages])]


def top_k_indices(scores: Sequence[float], k: int) -> list[int]:
    """
    점수 내림차순 상위 k개 인덱스. 동점이면 원래 순서(LightRAG 순위)를 유지한다.

    Args:
        scores: 점수 목록
        k: 고를 개수

    Returns:
        인덱스 목록(최대 k개)
    """
    # sorted는 안정 정렬이라 동점일 때 원래 순서가 유지된다
    return sorted(range(len(scores)), key=lambda i: -scores[i])[:k]


async def rerank(reranker, query: str, passages: Sequence[str], k: int) -> list[tuple[int, float]]:
    """
    score를 스레드에서 실행(이벤트 루프 막지 않음)하고 (인덱스, 점수) 상위 k개를 돌려준다.

    Args:
        reranker: score(query, passages)를 가진 객체
        query: 질문
        passages: 후보 문단들
        k: 고를 개수

    Returns:
        점수 내림차순 (후보 인덱스, 점수) 목록
    """
    # 1) CPU 연산을 스레드로 보내 다른 요청을 막지 않는다
    scores = await asyncio.to_thread(reranker.score, query, list(passages))
    # 2) 상위 k개를 고른다
    return [(i, scores[i]) for i in top_k_indices(scores, k)]
