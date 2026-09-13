"""Optional FAISS IndexFlatIP over normalized vectors. No untrusted binary index loading."""
from factory.exceptions import ConfigurationError
from .base import normalized

class FaissVectorBackend:
    name="faiss-flat-ip"
    def scores(self,vectors,query):
        query=normalized(query,len(query))
        rows=[normalized(v,len(query)) for v in vectors]
        if not rows:return ()
        try:
            import faiss
            import numpy as np
        except ImportError as exc:raise ConfigurationError("Install requirements-retrieval.txt to select FAISS") from exc
        index=faiss.IndexFlatIP(len(query))
        index.add(np.asarray(rows,dtype="float32"))
        distances,positions=index.search(np.asarray([query],dtype="float32"),len(rows))
        result=[0.0]*len(rows)
        for score,position in zip(distances[0],positions[0]):result[int(position)]=float(score)
        return tuple(result)
