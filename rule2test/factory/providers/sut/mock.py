"""Adapter for the independently configured local insurance application."""
from factory.providers.sut.base import SUTAdapter
from factory.engines.insurance_engine import InsuranceEngine
from factory.exceptions import ProviderError

class MockSUTAdapter(SUTAdapter):
    def __init__(self,engine: InsuranceEngine):
        self.engine=engine
    @property
    def name(self):
        return "mock-insurance-v2/"+self.engine.profile+"/"+self.engine.fault
    def execute(self,inputs,*,timeout_seconds):
        if timeout_seconds<=0: raise ProviderError("SUT timeout")
        return self.engine.decide(inputs)
