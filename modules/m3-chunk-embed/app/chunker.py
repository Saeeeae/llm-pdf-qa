import hashlib

_MODEL_NAME = "BAAI/bge-m3"


class Chunker:
    def __init__(self, model_name: str = _MODEL_NAME, chunk_size: int = 512, overlap: int = 50):
        # Deferred import: avoids failure at startup when transformers isn't installed.
        from transformers import AutoTokenizer
        self.tok = AutoTokenizer.from_pretrained(model_name)
        self.chunk_size = chunk_size
        self.overlap = overlap

    def chunk(self, text: str) -> list[tuple[str, str]]:
        ids = self.tok.encode(text, add_special_tokens=False)
        step = self.chunk_size - self.overlap
        out = []
        for i in range(0, len(ids), step):
            piece = self.tok.decode(ids[i : i + self.chunk_size]).strip()
            if not piece:
                continue
            h = hashlib.sha256(piece.encode()).hexdigest()
            out.append((piece, h))
        return out
