"""Bounded loopback inventory and explicit synthetic probes; no pull, install or fallback."""
from urllib.request import Request, build_opener, ProxyHandler
from factory.providers.llm.ollama import NoRedirect
from factory.parsers.common import strict_json
from factory.models.common import require, sha256
from factory.exceptions import ProviderError

def inventory():
    try:
        request = Request("http://127.0.0.1:11434/api/tags")
        with build_opener(ProxyHandler({}), NoRedirect()).open(request, timeout=5) as response:
            raw = response.read(1024 * 1024 + 1)
        require(len(raw) <= 1024 * 1024, "Model inventory exceeds 1 MiB")
        result = strict_json(raw.decode("utf-8"))
        require(type(result) is dict and type(result.get("models")) is list, "Invalid model inventory")
        models = []
        for row in result["models"]:
            require(type(row) is dict and type(row.get("name")) is str, "Invalid model name")
            sha256(row.get("digest"), "Installed model digest")
            models.append(dict(name=row["name"], digest=row["digest"]))
        require(len({m["name"] for m in models}) == len(models), "Duplicate installed model name")
        return dict(available=True, endpoint="http://127.0.0.1:11434", models=models)
    except Exception:
        return dict(available=False, endpoint="http://127.0.0.1:11434", models=[],
                    error="Ollama inventory unavailable or invalid; start the local server and check /api/tags")

def readiness(profile, *, probe=False):
    if profile.mode == "mock":
        return dict(status="mock_only", live_ready=False, simulated=True, checks=[],
                    note="Offline replay configuration; this does not establish live AI readiness.")
    result = inventory()
    checks = []
    installed = {row["name"]: row["digest"] for row in result["models"]}
    for role in ("extraction", "suggestion", "embedding"):
        model = getattr(profile, role + "_model")
        digest = getattr(profile, role + "_digest")
        checks.append(dict(role=role, model=model, expected_digest=digest,
                           observed_digest=installed.get(model),
                           passed=installed.get(model) == digest))
    passed = result["available"] and all(c["passed"] for c in checks)
    probes = []
    if passed and probe:
        extraction, embedding, suggestion = profile.providers()
        for role, operation in (
            ("extraction", lambda: strict_json(extraction.complete(system_prompt='Return exactly {"ready":true}.',
                                user_message="Synthetic connectivity check only.", timeout_seconds=profile.timeout_seconds))),
            ("suggestion", lambda: strict_json(suggestion.client.complete(system_prompt='Return exactly {"ready":true}.',
                                user_message="Synthetic connectivity check only.", timeout_seconds=profile.timeout_seconds))),
            ("embedding", lambda: embedding.embed(("加入年齢の上限", "保険金の免責額"))),
        ):
            try:
                value = operation()
                okay = (type(value) is dict and set(value) == {"ready"} and value["ready"] is True) if role != "embedding" else len(value) == 2
                probes.append(dict(role=role, passed=okay))
            except Exception:
                probes.append(dict(role=role, passed=False, error="Probe failed; check model capabilities and timeout"))
        passed = passed and all(p["passed"] for p in probes)
    return dict(status=("probe_passed" if probe else "configured") if passed else "blocked",
                live_ready=passed and probe, simulated=False, inventory=result, checks=checks, probes=probes,
                note="Inventory checks do not run inference. Probes check transport/schema, not insurance accuracy.")

def require_ready(profile):
    result = readiness(profile)
    if profile.mode == "ollama" and result["status"] == "blocked":
        raise ProviderError("Live AI configuration is blocked; run scripts/ai_doctor.py and verify installed model digests")
    return result
