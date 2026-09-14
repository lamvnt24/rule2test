# AI profiles

`mock.json` is the offline default and needs nothing installed.

`ollama.template.json` is a placeholder, not a working profile: the digests are zeros and the model
tags are not real. Generate a valid one on the target machine, where the real digests exist:

```powershell
.\rule2test.exe doctor
py -3 -B scripts/ai_doctor.py --chat-model "YOUR_TAG" --embedding-model "YOUR_TAG" \
  --dimensions 768 --write-profile data/ai_profiles/ollama.local.json
```

No model is ever downloaded automatically, and there is no fallback to mock if a live model fails.
