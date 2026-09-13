"""Embedding contract. Identity must change when model or preprocessing changes."""
from typing import Protocol
class EmbeddingProvider(Protocol):
    identity: str
    dimensions: int
    simulated: bool
    def embed(self,texts: tuple[str,...]) -> tuple[tuple[float,...],...]: ...
