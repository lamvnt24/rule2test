"""Bounded cosine similarity contract shared by Python and optional FAISS."""
import math
from typing import Protocol
from factory.models.common import require

def normalized(vector,dimension):
    require(type(vector) is tuple and len(vector)==dimension and dimension>0,"Vector dimension mismatch")
    require(all(type(x) is float and math.isfinite(x) for x in vector),"Vectors require finite floats")
    norm=math.sqrt(sum(x*x for x in vector))
    require(math.isfinite(norm),"Vector norm overflow")
    return tuple(x/norm if norm else 0.0 for x in vector)

class VectorBackend(Protocol):
    name: str
    def scores(self,vectors,query): ...

class PythonVectorBackend:
    name="python-cosine"
    def scores(self,vectors,query):
        query=normalized(query,len(query))
        return tuple(sum(a*b for a,b in zip(normalized(v,len(query)),query)) for v in vectors)
