"""Process-local counters and duration histograms. Bounded cardinality; every value resets on restart."""
import math,threading
from bisect import bisect_left

BUCKETS_MS=(1,5,10,25,50,100,250,500,1000,2500,5000,10000,30000)
LABELS=("component","operation","route","method","status","outcome","kind","provider","backend")
MAX_SERIES=256
MAX_LABEL=64
_SAFE=set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._:/-")
_LOCK=threading.Lock()
_COUNTERS={}
_DURATIONS={}
_STATE=dict(dropped=0)

def _label(value):
    # Only allowlisted label names reach this point, so a caller cannot turn a document
    # identifier or reviewer name into an unbounded metric dimension.
    text=value if type(value) is str else str(value)
    return text if 1<=len(text)<=MAX_LABEL and set(text)<=_SAFE else "invalid"

def _key(name,labels):
    return (str(name)[:MAX_LABEL],)+tuple((k,_label(v)) for k,v in sorted(labels.items()) if k in LABELS)

def _room(key,table):
    if key in table:return True
    if len(_COUNTERS)+len(_DURATIONS)>=MAX_SERIES:_STATE["dropped"]+=1;return False
    return True

def increment(name,amount=1,**labels):
    if type(amount) is not int or amount<0:return
    key=_key(name,labels)
    with _LOCK:
        if not _room(key,_COUNTERS):return
        _COUNTERS[key]=_COUNTERS.get(key,0)+amount

def observe(name,duration_ms,**labels):
    if type(duration_ms) not in (int,float) or not math.isfinite(duration_ms) or duration_ms<0:return
    key=_key(name,labels)
    with _LOCK:
        if not _room(key,_DURATIONS):return
        row=_DURATIONS.get(key)
        if row is None:row=_DURATIONS[key]=dict(count=0,sum_ms=0.0,max_ms=0.0,buckets=[0]*(len(BUCKETS_MS)+1))
        row["count"]+=1;row["sum_ms"]+=float(duration_ms);row["max_ms"]=max(row["max_ms"],float(duration_ms))
        row["buckets"][bisect_left(BUCKETS_MS,duration_ms)]+=1

def _upper_bound(row,quantile):
    seen=0;target=row["count"]*quantile
    for index,count in enumerate(row["buckets"]):
        seen+=count
        if seen>=target:return BUCKETS_MS[index] if index<len(BUCKETS_MS) else None
    return None

def snapshot():
    with _LOCK:
        counters=[dict(name=key[0],labels=dict(key[1:]),value=value) for key,value in sorted(_COUNTERS.items())]
        durations=[dict(name=key[0],labels=dict(key[1:]),count=row["count"],sum_ms=round(row["sum_ms"],3),
            mean_ms=round(row["sum_ms"]/row["count"],3),max_ms=round(row["max_ms"],3),
            p50_ms_upper_bound=_upper_bound(row,0.5),p95_ms_upper_bound=_upper_bound(row,0.95),
            buckets=dict(zip([str(b) for b in BUCKETS_MS]+["overflow"],list(row["buckets"]))))
            for key,row in sorted(_DURATIONS.items())]
        dropped=_STATE["dropped"]
    return dict(schema_version=1,series=len(counters)+len(durations),max_series=MAX_SERIES,dropped_series=dropped,
        bucket_upper_bounds_ms=list(BUCKETS_MS),counters=counters,durations=durations,
        scope="Process-local in-memory diagnostics. Values reset on restart and are never persisted or exported.",
        limitation="Host-observed operation counts and wall-clock durations only; not sampled, not a production metrics backend, and not a quality measurement.")

def reset():
    with _LOCK:
        _COUNTERS.clear();_DURATIONS.clear();_STATE["dropped"]=0
