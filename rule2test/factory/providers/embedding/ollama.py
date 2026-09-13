"""Optional local embedding adapter, bounded batches and explicit model revision identity."""
import json
from decimal import Decimal
from urllib.request import Request,build_opener,ProxyHandler
from factory.models.common import require,nonempty
from factory.parsers.common import strict_json
from factory.exceptions import ProviderError
from factory.providers.vector.base import normalized
from factory.providers.llm.ollama import NoRedirect

class OllamaEmbeddingProvider:
    simulated=False
    def __init__(self,model,dimensions,revision,timeout_seconds=30,device="auto"):
        nonempty(model,"embedding model");nonempty(revision,"embedding revision")
        require(type(dimensions) is int and 1<=dimensions<=4096,"Embedding dimensions must be 1..4096")
        require(type(timeout_seconds) is int and 1<=timeout_seconds<=120,"Embedding timeout must be 1..120 seconds")
        require(device in ("auto","cpu"),"Embedding device must be auto or cpu")
        self.device=device
        self.model=model;self.dimensions=dimensions;self.timeout_seconds=timeout_seconds
        self.identity="ollama-embed-v1:"+model+":"+revision+":"+str(dimensions)+(":cpu" if device=="cpu" else "")
    def embed(self,texts):
        require(len(texts)<=500 and all(type(t) is str and len(t.encode("utf-8"))<=65536 for t in texts),"Embedding text exceeds 64 KiB or 500 rows")
        output=[]
        for start in range(0,len(texts),16):
            batch=texts[start:start+16]
            payload=dict(model=self.model,input=batch,truncate=False,dimensions=self.dimensions)
            if self.device=="cpu":payload["options"]={"num_gpu":0}
            body=json.dumps(payload,ensure_ascii=False).encode("utf-8")
            request=Request("http://127.0.0.1:11434/api/embed",data=body,headers={"Content-Type":"application/json"},method="POST")
            try:
                with build_opener(ProxyHandler({}),NoRedirect()).open(request,timeout=self.timeout_seconds) as response:
                    raw=response.read(4*1024*1024+1)
                require(len(raw)<=4*1024*1024,"Embedding response exceeds 4 MiB")
                result=strict_json(raw.decode("utf-8"))
                require(type(result) is dict and result.get("model")==self.model,"Embedding response model differs from configured model; use its exact tag")
                vectors=result.get("embeddings")
                require(type(vectors) is list and len(vectors)==len(batch),"Embedding row count mismatch")
                for vector in vectors:
                    require(type(vector) is list and all(type(x) in (int,float,Decimal) for x in vector),"Invalid embedding numbers")
                    output.append(normalized(tuple(float(x) for x in vector),self.dimensions))
            except Exception as exc:raise ProviderError("Local embedding request failed; check model, revision, dimensions and server") from exc
        return tuple(output)

