"""빌드 전용: bge-reranker-v2-m3 가중치를 ONNX로 내보내고 int8 동적 양자화한다(Dockerfile reranker-export 스테이지)."""

import shutil
import sys
import tempfile
from pathlib import Path


def main(src: str, out: str) -> None:
    """
    HF 가중치 폴더를 읽어 out에 model.onnx(int8)와 tokenizer.json을 만든다.

    Args:
        src: snapshot_download로 받은 가중치 폴더(config.json·model.safetensors·tokenizer.json)
        out: 결과 폴더 — 런타임 리랭커(RERANKER_MODEL_PATH)가 읽는다

    Side effects:
        out 폴더를 만들고 파일 2개를 쓴다. 중간 산출물(fp32 ONNX, 약 2.3GB)은 임시 폴더에서 지운다.
    """
    import onnx
    import torch
    from onnxruntime.quantization import QuantType, quantize_dynamic
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    out_dir = Path(out)
    out_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        # 1) 모델을 올린다 — eager 어텐션으로 내보내야 패딩 마스크가 그래프에 그대로 남는다
        tok = AutoTokenizer.from_pretrained(src)
        model = AutoModelForSequenceClassification.from_pretrained(src, attn_implementation="eager").eval()

        # 2) 길이가 다른 쌍 2개(패딩 포함)를 예시 입력으로 fp32 ONNX를 만든다 — 배치·길이는 동적 축
        enc = tok([("질문", "길이가 조금 더 긴 예시 문단"), ("질문", "짧음")], padding=True, return_tensors="pt")
        raw = f"{tmp}/raw.onnx"
        torch.onnx.export(
            model,
            (enc["input_ids"], enc["attention_mask"]),
            raw,
            input_names=["input_ids", "attention_mask"],
            output_names=["logits"],
            dynamic_axes={
                "input_ids": {0: "batch", 1: "seq"},
                "attention_mask": {0: "batch", 1: "seq"},
                "logits": {0: "batch"},
            },
            opset_version=17,
            dynamo=False,
        )

        # 3) 2GB 넘는 fp32 가중치를 외부 파일 1개로 모은다(양자화 입력용)
        fp32 = f"{tmp}/fp32.onnx"
        onnx.save(onnx.load(raw), fp32, save_as_external_data=True, all_tensors_to_one_file=True, location="fp32.onnx.data")

        # 4) 가중치만 int8로 동적 양자화한다(약 570MB, 단일 파일)
        quantize_dynamic(fp32, str(out_dir / "model.onnx"), weight_type=QuantType.QInt8)

    # 5) 런타임 토크나이저(tokenizers 라이브러리)용 파일을 옆에 둔다
    shutil.copy(Path(src) / "tokenizer.json", out_dir / "tokenizer.json")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
