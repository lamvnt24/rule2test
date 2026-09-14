# Phase 10 — Live AI configuration and evaluation

## Implementation and environment status

The project now provides digest-pinned Ollama profiles, local readiness diagnostics, explicit capability probes, a profile-based workspace launcher and an artifact-producing evaluator for extraction, hybrid retrieval and grounded suggestions.

The implementation has been exercised with mocked transports and the offline replay providers. At implementation time, no Ollama service was reachable at 127.0.0.1:11434 and no Ollama executable was found on PATH. That was the initial state; the subsequent live connection and measurements are recorded below. The saved mock report must not be presented as real AI performance.

A live run requires a running local Ollama server, an installed chat model suitable for Japanese structured output, and an installed embedding model. Models are not downloaded or chosen automatically.

## Configure actual installed models

From the project directory, first inspect the local service:

```powershell
python -B scripts/ai_doctor.py
```

Install/start Ollama if needed using the [official Windows instructions](https://docs.ollama.com/windows). Choose model tags appropriate to your machine and install them separately. This project does not require cloud credentials.

The doctor lists exact installed names and digests from [Ollama's model inventory API](https://docs.ollama.com/api/tags). Create a profile using those names:

```powershell
python -B scripts/ai_doctor.py --chat-model "YOUR_EXACT_CHAT_TAG" --embedding-model "YOUR_EXACT_EMBEDDING_TAG" --dimensions 768 --write-profile data/ai_profiles/ollama.local.json
```

Replace both tags and 768 with the chosen embedding model's supported dimension count. The value is an example, not a recommendation for every model. Profile creation tests chat and embedding capabilities and writes only if all probes pass. Existing profile files are not overwritten.

Chat and suggestion roles initially share the selected chat model. A profile can specify separate model tags and digests by editing both role fields consistently and rerunning the doctor.

```powershell
python -B scripts/ai_doctor.py --profile data/ai_profiles/ollama.local.json --probe
python -B scripts/run_ai_workspace.py --profile data/ai_profiles/ollama.local.json
```

The launcher exports only known Rule2Test settings in its own process and starts the existing workspace. It does not modify the user's global environment or load .env automatically. Human rule/test review remains required.

Exact model digests are checked at startup. If a model tag is updated, create a new profile and rebuild its embedding corpus. Startup checks do not pin an already loaded model cryptographically for the lifetime of the server; rerun diagnostics/restart after model changes.

## Readiness levels

| Status | Meaning |
| --- | --- |
| mock_only | Offline replay; no evidence of live inference readiness |
| configured | Installed names/digests match; inference has not been probed |
| probe_passed | Both chat roles returned the probe JSON and embedding returned valid vectors |
| blocked | Service/model/digest/capability check failed |
| mixed_configuration / unpinned_configuration | Workspace uses legacy environment settings that do not form a complete digest-pinned live profile |

A successful probe verifies connectivity and output shape, not insurance interpretation quality. The probe contains synthetic text only. There is no automatic fallback to mock.

In the browser, **Overview → Inspect AI configuration** shows configuration and local model inventory. This metadata request does not invoke inference or install anything. It is also exposed as GET /api/v1/ai-status.

## Evaluate the three AI roles

Offline baseline:

```powershell
python -B scripts/evaluate_ai.py --profile data/ai_profiles/mock.json
```

Live evaluation after successful setup:

```powershell
python -B scripts/evaluate_ai.py --profile data/ai_profiles/ollama.local.json
```

To name a new artifact directory:

```powershell
python -B scripts/evaluate_ai.py --profile data/ai_profiles/ollama.local.json --run-dir data/generated/my-live-evaluation
```

The directory must not already exist. Each run preserves:

- report.json: stage results, profile/model identity, dataset hash, timings and limitations.
- dataset.json: the exact authored source/truth dataset used.
- evaluation.db: extraction proposals, synthetic reviewed retrieval corpus, vectors and unapproved suggestion batches, if inference stages ran.

The standard dataset has ten authored Japanese single-rule cases: three exact replay pairs, three paraphrases, one unseen numeric change, one document-instruction case, and two insufficient-information cases. It is synthetic and has not been independently reviewed by an insurance SME.

The provider receives only the versioned source text. Truth is compared after the call and is never included in the extraction prompt. A valid proposal is checked against both old and new condition/action/default projections. Extra rules or unexpected temporal semantics cannot silently count as a match.

The evaluator never approves/promotes the ten extracted evaluation proposals. Retrieval uses a separate corpus created through explicitly scripted synthetic reviews; those approvals are fixture setup, not observed reviewer acceptance. Suggestion batches remain unattached and unapproved.

## Metrics and practical limits

| Stage | Reported measurement | Limit |
| --- | --- | --- |
| Extraction | Matched/total semantic spot checks; schema/citation-valid count; provider errors; category breakdown; median elapsed time | Ten authored cases, not general Japanese extraction accuracy |
| Retrieval | Top-1 correct/accuracy and MRR@3 over nine queries | Hybrid ranking combines lexical and vector signals over only three approved test records |
| Suggestions | Whether the fixed age-66 → ALLOW witness is present, novel/duplicate counts, grounded candidates and unchanged target | One witness; host oracle computes expected outcomes, so this is not model reasoning accuracy |

Top-3 recall is deliberately omitted from the tiny retrieval corpus because it would be weak evidence of ranking quality. An empty suggestion batch is not automatically labeled incorrect; the fixed-witness result is recorded separately.

The recorded offline baseline in data/generated/phase10-mock-evaluation/report.json matched 5/10 extraction cases and ranked the expected test first for 5/9 retrieval queries. These numbers describe that mock run. The five extraction matches comprise the three exact replays and two ambiguity outcomes; paraphrases/numeric changes are outside the mock's replay behavior.

Report status completed means measurements were recorded, **not that a quality threshold was passed**. Provider-error counts and semantic mismatches must still be inspected. Partial means at least one downstream stage failed. Blocked means the live preflight failed and no model inference was attempted. Invalidated means the observed model inventory changed between preflight and postflight; do not compare those measurements as one model version.

Pre/post inventory comparisons detect observed changes, not every possible transient change during a call. Latency is host-measured scenario time and may include cold model loading. Token usage, monetary cost, production accuracy, manual effort savings and real reviewer acceptance remain explicitly unmeasured.

CLI exit codes: evaluate_ai.py returns 0 for completed measurements, 2 for blocked/partial/invalidated runs, and 1 for setup/output failure. ai_doctor.py returns 2 for blocked inventory/readiness and 1 for invalid arguments/profile/output failures. No score is fabricated when a provider is unavailable.

## Configuration contract

factory.ai_config.AIProfile rejects unknown fields, mixed mock/live claims, invalid dimensions, invalid digests and out-of-range timeouts. Timeout is 1–120 seconds per provider operation; an entire evaluation makes multiple calls and can take longer. Embedding batches remain bounded by the existing adapter.

The live adapters use the local [chat endpoint](https://docs.ollama.com/api/chat) for JSON output and [embedding endpoint](https://docs.ollama.com/api/embed) with truncation disabled. Redirects, tools and unsupported response shapes are rejected. Chat/extraction and embedding models must support their respective operations.

The profile stores exact extraction/suggestion model digests and uses the embedding digest as corpus revision identity. The evaluator records profile/hash, source dataset/hash and prompt version for reproducibility. Existing unpinned environment-based workflows remain compatible, but their diagnostics do not claim a fully pinned profile.

A report hash uses SHA-256 of canonical JSON without report_hash (sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False). It is an integrity fingerprint, not a signature.

## Verification and next step

```powershell
python -B -m unittest discover -s tests -v
python -B scripts/check_workspace_browser.py
```

Automated tests cover wrong model digests, probe failures, no hidden fallback, private-error sanitization, exclusion of gold truth, old/new semantics, source limits, output preservation and absence of automatic approval of evaluated proposals.

To finish the real-model evidence milestone, run the live profile on installed models, inspect failed cases, obtain SME-reviewed labels, and repeat on a broader representative dataset. No live quality claim should be made before those results exist.



## Verified Cloud Free connection

Profile: data/ai_profiles/ollama-cloud.local.json. Extraction and suggestions use gpt-oss:120b-cloud through the signed-in local gateway. Embedding uses embeddinggemma:latest, 768 dimensions, with embedding_device=cpu. All three probes passed with simulated=false.

Start from the project root:

    python -B scripts/run_ai_workspace.py --profile data/ai_profiles/ollama-cloud.local.json

Plain factory.server does not automatically load this profile.

The GPU embedding attempt failed with a CUDA device-kernel error. CPU mode sends options.num_gpu=0 only on embedding requests and uses a distinct index identity. Rebuild any corpus created with the auto-device identity.

Tags ending in -cloud omit format and request JSON through the prompt. Strict host JSON/schema/citation validation remains mandatory; no prose stripping, output repair or automatic retry is performed. Other tags retain format=json.

Cloud digests identify local gateway manifests, not immutable remote weights. Reports record cloud/local execution locations and this digest scope.

The initial live report at data/generated/phase10-cloud-evaluation/report.json matched 2/10 extraction cases. Prompt rule-extraction-v2 then clarified required technical IDs and integer versions without inventing business rules.

The subsequent data/generated/phase10-cloud-prompt-v2/report.json records 4/10 extraction matches, 9/9 retrieval top-1 matches over three approved test records, and the age-66/ALLOW suggestion witness. These are real-model calls on synthetic development data. No evaluation proposals were automatically approved.

The prompt was changed after inspecting failures, so the second run is not independent held-out validation. Extraction still has rejected schema/citation outputs and requires further work. Successful connection does not establish reliable insurance interpretation.
