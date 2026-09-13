"""Deterministic hashed lexical features; not semantic language embeddings."""
import hashlib,re,math
from factory.models.common import require

def tokens(text):
    text=text.casefold()
    words=re.findall(r"[a-z0-9_]+",text)
    japanese=re.findall(r"[\u3040-\u30ff\u3400-\u9fff]+",text)
    return set(words+[part[i:i+2] for part in japanese for i in range(max(1,len(part)-1))])

class MockEmbeddingProvider:
    identity="mock-hashed-lexical-v1-128"
    dimensions=128
    simulated=True
    def embed(self,texts):
        result=[]
        for text in texts:
            require(type(text) is str and len(text)<=100000,"Embedding text exceeds limit")
            vector=[0.0]*self.dimensions
            for token in tokens(text):
                digest=hashlib.sha256(token.encode()).digest()
                vector[int.from_bytes(digest[:4],"big")%self.dimensions]+=1.0 if digest[4]%2 else -1.0
            length=math.sqrt(sum(x*x for x in vector))
            result.append(tuple(x/length if length else 0.0 for x in vector))
        return tuple(result)
