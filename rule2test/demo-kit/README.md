# Rule2Test — demo and test kit

Everything needed to run, demonstrate and check Rule2Test on a machine that has none of the source code.
Synthetic data throughout.

## Start here — five minutes

1. Run `app/rule2test.exe`. It checks its own preconditions, starts the workspace and opens a browser.
2. Type any reviewer name in the header. It is self-declared; there is no authentication.
   Vietnamese readers: `docs/vi/HUONG-DAN-SU-DUNG.md` walks through everything below in detail.
3. **Document intake → Eligibility · age 60 → 65 → Create synthetic workflow.**
4. **Analyze & generate.** You should get **14 candidate tests**.
5. **Open test review**, select all, write a reason, **Approve selected**, then **Finalize review**.
6. **Run & evidence → Execute approved tests** with fault *None*: **14 pass, 0 fail**.
7. **Create evidence pack**, then **Evaluate current revision**: **GO**.
8. **Reopen review** with a reason, re-approve, re-finalize, set fault to **Boundary**, execute again and
   evaluate again: **13 pass, 1 fail**, gate **NO-GO**.

Step 8 is the point of the whole demo. Full minute-by-minute scripts, speaker notes and a recovery path for
every step that can fail are in `docs/COMPETITION_DEMO.md`.

## What is in this folder

| Path | What it is |
| --- | --- |
| `EXPECTED-RESULTS.md` | Every number you should see, produced by running the real pipeline |
| `expectations.json` | The same results as data, for automated checking |
| `MANIFEST.json` | Every file with its SHA-256, so you can verify nothing was altered in transit |
| `docs/` | Demo script, benchmarks, architecture diagrams, observability and packaging guides |
| `docs/vi/` | Vietnamese system overview, roadmap and step-by-step user guide |
| `docs/slides/final-round2.pdf` | Round 2 final-submission deck for Track 2, in Vietnamese — hand this to the organisers |
| `docs/slides/final-round2.html` | The same deck as a live page, for presenting |
| `docs/slides/index.html` | General pitch deck; open it from disk, arrow keys to navigate |
| `data/import/` | Versioned JSON and XLSX documents to import through **Document intake** |
| `data/ai-extraction/` | Japanese rule-document pairs for **AI rule review**, with separate truth files |
| `data/ai-profiles/` | Offline mock profile and a template for pinning a real local model |
| `backup/` | Screenshot replay of the whole demo, for when the live run cannot happen |
| `app/` | The portable executable, if it was built when this kit was assembled |

## Verify the kit arrived intact

`MANIFEST.json` lists every file with its SHA-256. On the target machine, with no Python needed:

```powershell
$m = Get-Content MANIFEST.json | ConvertFrom-Json
$m.files | ForEach-Object {
  $actual = (Get-FileHash $_.path -Algorithm SHA256).Hash.ToLower()
  if ($actual -ne $_.sha256) { "CHANGED: " + $_.path }
}
```

Silence means every file matches. This detects corruption in transit; it is not a signature.

## Testing it rather than demonstrating it

- `app/rule2test.exe check` runs the preflight alone and exits 2 if something is wrong.
- Import each file in `data/import/` and compare against `EXPECTED-RESULTS.md`.
- Load each pair in `data/ai-extraction/` through **AI rule review**: paste `rules_v1.txt` and
  `rules_v2.txt` into the two source boxes, then compare the proposal status with the
  `ground_truth.json` beside them. The truth file is never shown to the provider. The optional
  *Existing tests JSON* box is inside a collapsed **Existing tests JSON** section — expand it first
  if you want to supply `existing_tests.json`; leaving it empty is fine.
- **Overview → Run diagnostics** shows request counts, durations and the logging configuration for the
  running process. Counters reset when you stop the application.

## If something fails

Every error message carries a trace id, and the same id appears in the console output. Provider failures are
classified with a remediation hint and are never retried or silently replaced by mock output. `docs/OBSERVABILITY.md`
explains the diagnostics surface; `docs/COMPETITION_DEMO.md` has the recovery table.

## Honest limits

- Windows x64 only, and the executable is unsigned, so SmartScreen warns on first run.
- Live AI needs a local Ollama service and installed models on the target machine. Without one the kit runs on
  offline mock providers, labelled simulated everywhere they appear.
- SHA-256 in `MANIFEST.json` detects corruption in transit. It is not a signature.
