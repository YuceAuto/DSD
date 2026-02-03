# modules/semantic_store.py
import numpy as np

class LocalVectorStore:
    """
    Basit ve hızlı bir vektör mağazası:
    - Vektörleri L2 normalize eder
    - FAISS varsa onu kullanır, yoksa NumPy ile cosine arama yapar
    """
    def __init__(self, dim: int):
        self.dim = dim
        self.vecs = None          # (N, dim) float32 normalized
        self.meta = []            # len N, her öğe dict
        self._use_faiss = False
        self._faiss_index = None
        try:
            import faiss  # type: ignore
            self._faiss = faiss
            self._use_faiss = True
        except Exception:
            self._faiss = None
            self._use_faiss = False

    @staticmethod
    def _l2_normalize(x: np.ndarray) -> np.ndarray:
        x = x.astype("float32")
        norms = np.linalg.norm(x, axis=1, keepdims=True) + 1e-8
        return x / norms

    def build(self, vectors: np.ndarray, metas: list[dict]):
        assert vectors.ndim == 2 and vectors.shape[1] == self.dim
        assert len(metas) == vectors.shape[0]
        self.vecs = self._l2_normalize(vectors)
        self.meta = metas

        if self._use_faiss:
            idx = self._faiss.IndexFlatIP(self.dim)
            idx.add(self.vecs)  # normalize + inner product = cosine
            self._faiss_index = idx

    def search(self, query_vec: np.ndarray, top_k: int = 5):
        """
        query_vec: (dim,) veya (1, dim) float32 normalized
        return: list of tuples (score, meta, index)
        """
        if query_vec.ndim == 1:
            query_vec = query_vec[None, :]
        query_vec = self._l2_normalize(query_vec)

        if self._use_faiss:
            scores, ids = self._faiss_index.search(query_vec, top_k)
            scores, ids = scores[0], ids[0]
        else:
            # NumPy cosine: (1,dim) @ (dim,N) -> (1,N)
            sims = (query_vec @ self.vecs.T)[0]
            ids = np.argsort(-sims)[:top_k]
            scores = sims[ids]

        out = []
        for s, i in zip(scores, ids):
            if i == -1:
                continue
            out.append((float(s), self.meta[int(i)], int(i)))
        return out
