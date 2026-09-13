"""One trace per HTTP request or CLI run, with nested spans. Records durations and outcomes only."""
import contextvars,functools,time,uuid
from contextlib import contextmanager
from factory.observability import logger,metrics

MAX_DEPTH=16
_SPANS=contextvars.ContextVar("rule2test_spans",default=())

def current_span():
    stack=_SPANS.get()
    return stack[-1] if stack else None

def depth():
    return len(_SPANS.get())

@contextmanager
def span(name,*,component="app",**fields):
    stack=_SPANS.get();parent=stack[-1] if stack else None
    token=_SPANS.set(stack+(name,)) if len(stack)<MAX_DEPTH else None
    started=time.perf_counter();outcome="ok";error_type=None;error_kind=None
    try:
        yield name
    except BaseException as exc:
        outcome="error";error_type=type(exc).__name__;error_kind=getattr(exc,"kind",None)
        raise
    finally:
        elapsed=(time.perf_counter()-started)*1000
        if token is not None:_SPANS.reset(token)
        metrics.observe("span_duration_ms",elapsed,component=component,operation=name,outcome=outcome)
        if outcome=="error":metrics.increment("span_errors_total",component=component,operation=name,kind=error_kind or error_type)
        logger.event("span","error" if outcome=="error" else "debug",span=name,parent=parent,depth=len(stack),
            duration_ms=round(elapsed,3),outcome=outcome,component=component,error_type=error_type,
            error_kind=error_kind,**fields)

@contextmanager
def trace(name,*,component="app",**fields):
    """Start a fresh trace identity; nested calls reuse the running trace instead."""
    if logger.trace_id():
        with span(name,component=component,**fields) as active:yield logger.trace_id()
        return
    token=logger.bind(uuid.uuid4().hex[:16]);stack=_SPANS.set(())
    try:
        with span(name,component=component,**fields):yield logger.trace_id()
    finally:
        _SPANS.reset(stack);logger.unbind(token)

def traced(name,*,component="service"):
    def decorate(function):
        @functools.wraps(function)
        def call(*args,**kwargs):
            with span(name,component=component):return function(*args,**kwargs)
        return call
    return decorate
