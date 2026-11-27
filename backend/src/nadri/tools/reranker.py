"""bge-reranker-v2-m3 리랭커(ONNX Runtime int8, CPU) 래퍼와 상위 k 선택."""

import asyncio
from collections.abc import Sequence


class CrossEncoderReranker:
    """bge-reranker-v2-m3(크로스 인코더)를 ONNX Runtime CPU로 돌려 질문-문단 쌍 점수를 낸다. onnxruntime·tokenizers는 생성자에서 지연 import."""

    def __init__(self, model_path: str, max_length: int = 512) -> None:
        """
        토크나이저와 int8 ONNX 모델을 메모리에 올린다(서버 기동 때 1회).

        Args:
            model_path: 이미지 빌드 때 만든 폴더(model.onnx·tokenizer.json, 런타임 다운로드 없음)
            max_length: 질문+문단 최대 토큰 수(A9 대안: 256으로 낮추면 빨라짐)
        """
        # 리랭커 그룹이 없는 개발·테스트 환경에서도 이 모듈을 import할 수 있게 여기서 import한다
        import onnxruntime as ort
        from tokenizers import Tokenizer

        # 1) 토크나이저: 쌍을 합쳐 max_length를 넘으면 긴 쪽부터 자른다(sentence-transformers CrossEncoder와 같은 방식)
        self._tok = Tokenizer.from_file(f"{model_path}/tokenizer.json")
        self._tok.enable_truncation(max_length=max_length, strategy="longest_first")
        self._tok.enable_padding(pad_id=self._tok.token_to_id("<pad>"), pad_token="<pad>")
        # 2) 모델: CPU 실행, 스레드 수는 onnxruntime 기본값(물리 코어 수)
        self._session = ort.InferenceSession(f"{model_path}/model.onnx", providers=["CPUExecutionProvider"])

    def score(self, query: str, passages: Sequence[str]) -> list[float]:
        """
        질문과 각 문단의 관련도 점수(0~1, 로짓의 sigmoid)를 낸다(블로킹 — rerank가 스레드에서 부름).

        Args:
            query: 질문
            passages: 후보 문단들

        Returns:
            passages와 같은 순서의 점수 목록
        """
        import numpy as np

        # 1) 모든 쌍을 한 배치로 토큰화한다(가장 긴 쌍 길이로 패딩)
        enc = self._tok.encode_batch([(query, p) for p in passages])
        ids = np.array([e.ids for e in enc], dtype=np.int64)
        mask = np.array([e.attention_mask for e in enc], dtype=np.int64)
        # 2) 한 번에 추론해 쌍마다 로짓 1개를 얻는다
        logits = self._session.run(["logits"], {"input_ids": ids, "attention_mask": mask})[0][:, 0]
        # 3) 기존 CrossEncoder.predict와 같은 의미가 되도록 sigmoid로 0~1 점수로 바꾼다
        return [float(s) for s in 1 / (1 + np.exp(-logits))]


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
