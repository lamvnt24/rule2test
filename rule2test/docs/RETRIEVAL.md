# Phase 7: reviewed knowledge and grounded test suggestions

Phase 7 indexes reviewed rule/test snapshots, retrieves related examples and proposes new test inputs. The current policy oracle computes expected results. Retrieved old expectations cannot override it.

The offline default uses hashed lexical embeddings and a scripted input provider. Optional FAISS, Ollama embeddings and Ollama suggestions are implemented. FAISS was exercised locally; live Ollama models were not evaluated.

## Offline demo

```powershell
Set-Location -LiteralPath "E:\AI hackathon\rule2test"
python -B scripts/run_retrieval_demo.py
```

Use the optional FAISS backend:

```powershell
python -m pip install --user -r requirements-retrieval.txt
python -B scripts/run_retrieval_demo.py --backend faiss
```

The demo creates a separate data/retrieval-demo.db. It performs explicitly labeled synthetic source approvals to seed three rule records and three reviewed test records. These fixture approvals are not real SME decisions. The target has a new maximum age of 70 and no new approvals.

The demo retrieves the old age-66 test, whose historical expected result was DENY. The current oracle computes ALLOW. Six repeated boundary inputs are removed and one additional regression example remains. The batch is persisted for inspection; it is not attached or approved automatically.

This extra example does not close a previously missing boundary obligation. An empty obligation_ids field is deliberate, and the demo does not claim increased boundary coverage.

## Architecture

```mermaid
flowchart LR
    R[Reviewed source workflows] --> I[Immutable corpus + embedding vectors]
    I --> H[Metadata filters + lexical/vector ranking]
    H --> V[Revalidate current source approval]
    V --> P[Mock or Ollama input suggestions]
    P --> C[Schema + citation IDs + current oracle + deduplication]
    C --> B[Persist proposal batch]
    B --> A[Explicit attach to IN_REVIEW]
    A --> Q[QA test approval]
    Q --> E[Execution and evidence]
```

## Components

| Module | Responsibility |
| --- | --- |
| factory/providers/embedding/base.py | Embedding identity, dimensions and simulation contract |
| factory/providers/embedding/mock.py | Deterministic hashed word/Japanese-bigram features; not semantic embeddings |
| factory/providers/embedding/ollama.py | Optional loopback embedding provider with limits and declared model revision |
| factory/providers/vector/base.py | Python cosine backend and vector validation |
| factory/providers/vector/faiss.py | Optional normalized IndexFlatIP scoring |
| factory/models/knowledge.py | Corpus, records, vectors, retrieval hits and candidate batch contracts |
| factory/repositories/knowledge_repository.py | Immutable corpus/batch storage in the existing SQLite object store |
| factory/services/knowledge_service.py | Review-aware indexing, current-source checks and hybrid ranking |
| factory/providers/llm/test_suggestions.py | Scripted or optional Ollama candidate-input proposal |
| factory/services/retrieval_generation_service.py | Candidate validation, oracle expected values, deduplication and transactional attachment |
| scripts/retrieval_cli.py | Build, search, propose, inspect and attach |
| scripts/run_retrieval_demo.py | Synthetic corpus, changed policy and labeled retrieval checks |

No database migration is required. Vectors and metadata persist together in a hashed JSON model in SQLite. FAISS indexes are reconstructed in memory from those vectors; the application does not load external FAISS binary files.

## Which records are trusted?

Rules require an approved phase-6 extraction and promotion proof. The current table must still match the promoted table. A test approval alone never counts as rule approval.

Tests require a current APPROVED decision bound to their exact revision, content hash and rule references. Other tests in the same workflow can remain pending; they are excluded.

Search checks the live workflow again. Editing a test, rejecting its review, revising rules or reopening review can make old indexed entries ineligible. The immutable index remains available as history; new searches omit stale records without requiring a rebuild.

Approval is also checked after provider generation and again during attachment. A source review change during a slow model call cannot quietly become an attached candidate.

Indexes are built from 1..20 explicitly selected workflows, with at most 500 records. This is an explicit corpus scope, not authentication or tenant isolation. Reviewer identity remains self-declared.

## Hybrid ranking

Filters apply before scoring: required business fields, record kind, selected workflow IDs and an optional excluded target workflow. Only current eligible source snapshots are considered.

The score is:

```text
0.45 * query-token overlap
+ 0.35 * max(0, cosine similarity)
+ 0.20 * matching rule ID
```

Rule IDs are a ranking boost, not a hard filter. Scores are ranking signals, not probabilities. Ties are resolved by stable record ID. The result includes lexical/vector contributions and source proof metadata.

Mock embeddings use hashed lexical features and cannot demonstrate general semantic or cross-language retrieval quality. Empty/no-evidence queries may return no hits. If no hits remain, proposal generation returns no candidates and does not call the suggestion provider.

FAISS uses normalized vectors with inner-product scoring, following [FAISS's cosine similarity guidance](https://github.com/facebookresearch/faiss/wiki/MetricType-and-distances). The Python backend uses the same cosine definition. Tests compare their scores.

## CLI on an existing workflow database

Choose the database containing your approved source workflows and target workflow. All IDs below refer to that same database.

Build a corpus from reviewed sources:

```powershell
$i = python -B scripts/retrieval_cli.py --db data/extraction.db build --workflow YOUR_SOURCE_WORKFLOW_ID --actor Curator | ConvertFrom-Json
```

Repeat --workflow to include additional source workflows. Rebuilding creates a new immutable index.

Search and inspect current references:

```powershell
python -B scripts/retrieval_cli.py --db data/extraction.db --backend faiss search --index $i.index_id --query "age eligibility" --field age --kind test --top-k 5
```

Create suggestions for a target already at ANALYZED or IN_REVIEW. Use its current revision:

```powershell
$b = python -B scripts/retrieval_cli.py --db data/extraction.db propose --workflow YOUR_TARGET_WORKFLOW_ID --revision 3 --index $i.index_id --query "age eligibility" --actor BA | ConvertFrom-Json
python -B scripts/retrieval_cli.py --db data/extraction.db show --batch $b.batch_id
```

After inspecting the input, source and expected result, explicitly attach the batch:

```powershell
$w = python -B scripts/retrieval_cli.py --db data/extraction.db attach --batch $b.batch_id --hash $b.batch_hash --actor BA | ConvertFrom-Json
```

Attachment adds pending tests to IN_REVIEW. It creates no test approvals. Existing decisions on unchanged tests remain intact. Continue with the phase-4 review/finalize/execute commands using the new workflow revision.

For the demo, use data/retrieval-demo.db and the printed index_id, target_workflow, target_revision, batch_id and batch_hash.

## Candidate contract and controls

The suggestion provider returns exactly:

```json
{
  "candidates": [
    {
      "inputs": [
        {"field":"age","value":{"kind":"integer","data":66,"currency":null}}
      ],
      "reference_ids": ["a-retrieved-KB-record-ID"],
      "reason": "A short explanation grounded in the supplied reference."
    }
  ]
}
```

At most 20 candidates are permitted. Every candidate must cite one or more IDs from its actual retrieval context. Unknown IDs, unexpected fields, invalid input shapes and supplied expected values are rejected. Validation failure saves no batch and changes no workflow.

The host binds current rule references and recomputes expected through the oracle. Deduplication uses canonical input semantics: input order is ignored, equivalent Decimal scales match, and omitted/MISSING values have the same key. QA review remains mandatory.

Gap obligation IDs are assigned only when candidate inputs match currently missing deterministic witnesses. Extra regression examples do not receive an invented coverage claim.

The provider cannot submit test IDs, approvals, workflow changes, executable code or authoritative expected results. Retrieved text is untrusted prompt data. Citation validity does not prove that the proposed test is useful; this remains part of review.

## Batch history and evidence

A batch binds target workflow/revision/table hash, index/hash, query, retrieved records and scores, provider/simulation flag, raw response, candidates and duplicate count.

Attachment rechecks target revision and source eligibility, then writes the workflow revision, archived corpus and archived batch in one transaction. An archive failure rolls back the workflow update. A repeated attach using the old revision is rejected.

Each proposed test points to the archived corpus record through a JSON Pointer and document hash. The corpus records retain original source workflow, rule/test snapshots and approval proof IDs/hashes. Historical records remain traceable even when later excluded from fresh retrieval.

This is content-integrity and audit linkage, not a signed ledger. An administrator capable of rewriting all data and hashes is outside this control.

## Optional real providers

For real embeddings, configure a local installed Ollama embedding model:

```powershell
$env:RULE2TEST_EMBEDDING_PROVIDER="ollama"
$env:RULE2TEST_EMBEDDING_MODEL="your-installed-model:exact-tag"
$env:RULE2TEST_EMBEDDING_DIMENSIONS="768"
$env:RULE2TEST_EMBEDDING_REVISION="your-weights-or-preprocessing-revision"
```

Choose dimensions supported by your model. The revision string is operator-supplied: update it and rebuild the index whenever weights or preprocessing change. It is not an automatically verified model-weight digest. Index/search enforce the configured identity and dimensions; they cannot detect a model tag silently repointed to different weights under the same declared revision.

The adapter calls the loopback /api/embed endpoint, uses truncate=false and validates returned model, row count, dimensions and finite numbers. These parameters follow [Ollama's embedding API](https://docs.ollama.com/api/embed). Inputs are limited to 64 KiB per text and batches of 16; response size is bounded to 4 MiB. No download or mock fallback occurs.

For optional LLM suggestions:

```powershell
$env:RULE2TEST_SUGGESTION_PROVIDER="ollama"
$env:RULE2TEST_SUGGESTION_MODEL="your-installed-chat-model"
```

Embedding and suggestion models are separate roles. To return to offline mode:

```powershell
$env:RULE2TEST_EMBEDDING_PROVIDER="mock"
$env:RULE2TEST_SUGGESTION_PROVIDER="mock"
```

Use a matching mock index or rebuild it. The demo script always uses mock embeddings/suggestions so its fixture results remain reproducible.

The HTTP adapters disable proxies and redirects, bound response sizes and use socket timeouts. These are not hard process-wide deadlines or guaranteed cancellation of model work. No live Ollama model was evaluated during implementation.

## Evaluation and limitations

The demo uses three independently declared query-to-source-workflow labels. It reports Recall@3 and MRR@3 under synthetic_lexical_retrieval_checks. The observed fixture result was 3/3 sources ranked first. This very small lexical fixture is not a semantic retrieval benchmark.

Tests exercise real FAISS/Python parity, mocked Ollama transport, stale reviews, wrong embedding identity, forged reference IDs, old expected values, duplicates, transactional rollback and pending test review.

```powershell
python -B -m unittest tests.unit.test_retrieval_vectors tests.integration.test_retrieval_workflow -v
python -B -m unittest discover -s tests
```

The interface is currently CLI/Python. UI integration, production-scale indexing, larger labeled retrieval evaluation, authenticated corpus permissions and calibrated ranking are later work.
