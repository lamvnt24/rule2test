# Architecture diagrams

Three views of the same system. They render in GitHub markdown without any build step.

## 1. Trust boundaries — untrusted document to signed-off evidence

The single claim of this project: **AI proposes, deterministic engines decide, a human approves.**
Every arrow crossing a boundary is validated, and nothing crosses back.

```mermaid
flowchart LR
  subgraph UNTRUSTED["Untrusted input"]
    DOC["Rule document v1 and v2<br/>JSON, XLSX or Japanese text"]
  end

  subgraph AI["AI proposal zone - never authoritative"]
    EXT["Extraction provider<br/>mock replay or Ollama"]
    SUG["Suggestion provider<br/>candidate inputs only"]
    EMB["Embedding provider<br/>hybrid retrieval"]
  end

  subgraph HOST["Host validation - deterministic"]
    VAL["Strict JSON, schema and<br/>exact-line citation validation"]
    ORACLE["Typed oracle<br/>computes EXPECTED"]
    GAP["Rule delta, impact,<br/>bounded gap search"]
  end

  subgraph HUMAN["Human authority"]
    REV["Rule review<br/>hash-bound decision"]
    TREV["Test review<br/>revision-bound selection"]
  end

  subgraph RUN["Independent execution"]
    SUT["Insurance mock or HTTP SUT<br/>computes ACTUAL"]
    EV["Evidence pack<br/>SHA-256 over the payload"]
    GATE["Regression quality gate<br/>GO / NO-GO"]
  end

  DOC --> EXT
  DOC --> VAL
  EXT --> VAL
  VAL --> REV
  REV -->|"approved only"| GAP
  GAP --> ORACLE
  EMB --> SUG
  SUG --> ORACLE
  ORACLE --> TREV
  TREV -->|"explicitly selected tests"| SUT
  ORACLE -->|"expected, never sent to the SUT"| EV
  SUT -->|"actual"| EV
  EV --> GATE

  classDef ai fill:#fde8d7,stroke:#c96a1b,color:#3b2008
  classDef human fill:#dcecff,stroke:#1c5fa8,color:#0b2545
  class EXT,SUG,EMB ai
  class REV,TREV human
```

**What the diagram encodes.** The SUT never receives the expected result or the rule snapshot. The provider never
sees the ground truth. No arrow returns from `SUT` to `ORACLE`. No path reaches `SUT` without passing through
`TREV`. A provider failure stops at `VAL` and is classified, never retried and never replaced by mock output.

## 2. Layers and dependency direction

Dependencies point downward only. Engines never import transport; the API never re-implements a business rule.

```mermaid
flowchart TB
  subgraph L1["Transport"]
    WEB["web/workspace.html + .js + .css<br/>strict CSP, same-origin, session token"]
    SRV["factory/server.py<br/>loopback ThreadingHTTPServer"]
    API["factory/api/routes + schemas<br/>versioned /api/v1"]
  end

  subgraph L2["Application services"]
    WF["workflow, approval, evidence"]
    AN["rule delta, impact, gap,<br/>generation, coverage, mutation"]
    AIS["extraction, knowledge,<br/>retrieval generation, quality gate"]
  end

  subgraph L3["Domain and engines"]
    MOD["factory/models<br/>frozen contracts, content hashes"]
    ENG["oracle engine, insurance mock,<br/>approved-test executor"]
    VALD["factory/validators"]
  end

  subgraph L4["Adapters"]
    PROV["providers: llm, embedding,<br/>vector, sut"]
    REPO["repositories: SQLite<br/>append-only snapshots"]
  end

  subgraph OBS["Cross-cutting - phase 11"]
    LOG["logger: allowlisted JSON fields"]
    TRC["tracing: one trace per request"]
    MET["metrics: bounded counters"]
  end

  WEB --> SRV --> API --> WF & AN & AIS
  WF & AN & AIS --> MOD & ENG & VALD
  AIS --> PROV
  WF --> REPO
  ENG --> MOD
  PROV -.->|"classified ProviderError"| API
  OBS -.->|"spans and counters"| SRV
  OBS -.-> AIS
  OBS -.-> REPO
```

Observability is drawn with dotted edges because it observes; it never changes a decision. Metrics live in the
process only and reset on restart.

## 3. Review state machine

Taken from `factory/services/workflow_service.py` and `approval_service.py`. Every transition is an explicit
operator action bound to the current revision; a stale revision raises `ConflictError` and changes nothing.

```mermaid
stateDiagram-v2
  [*] --> DRAFT: create or promote a reviewed proposal
  DRAFT --> ANALYZED: analyze
  ANALYZED --> IN_REVIEW: start-review
  IN_REVIEW --> IN_REVIEW: review selected tests
  IN_REVIEW --> APPROVED: finalize
  APPROVED --> EXECUTING: execute
  EXECUTING --> EXECUTED: every approved test ran
  EXECUTING --> INTERRUPTED: failure or lost reservation
  EXECUTED --> EVIDENCED: create evidence pack
  INTERRUPTED --> IN_REVIEW: recover, approvals cleared
  EXECUTING --> IN_REVIEW: recover, approvals cleared
  APPROVED --> IN_REVIEW: reopen-review, approvals cleared
  EXECUTED --> IN_REVIEW: reopen-review, approvals cleared
  EVIDENCED --> IN_REVIEW: reopen-review, approvals cleared
  IN_REVIEW --> DRAFT: revise-rules, analysis reset
  ANALYZED --> DRAFT: revise-rules, analysis reset

  note right of INTERRUPTED
    Recovery is an operator acknowledgement.
    Tests are never replayed automatically.
  end note
```

Reopening review clears approvals and invalidates the current GO context: a gate verdict always belongs to one
workflow revision.

## Where the numbers come from

See [BENCHMARKS.md](BENCHMARKS.md) for every measured value with its source artifact, and
[OBSERVABILITY.md](OBSERVABILITY.md) for what the diagnostics surface does and does not record.
