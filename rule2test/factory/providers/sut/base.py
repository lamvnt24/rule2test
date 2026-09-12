"""SUT receives inputs only; expected results and rules never cross this boundary."""
from abc import ABC, abstractmethod
from factory.models.test_case import TestInput
from factory.models.rule import Action

class SUTAdapter(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...
    @abstractmethod
    def execute(self,inputs: tuple[TestInput,...],*,timeout_seconds: float) -> Action:
        """Implementations must enforce their I/O timeout and raise ProviderError on failure."""
