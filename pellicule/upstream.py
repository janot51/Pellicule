from __future__ import annotations

from dataclasses import dataclass

from pellicule.keys import KeysError, UpstreamCredentials, load_upstream, provider_names


@dataclass(frozen=True)
class ResolvedUpstream:
    credentials: UpstreamCredentials
    upstream_model: str


def resolve_model(model: str, upstream_header: str | None) -> ResolvedUpstream:
    model = model.strip()
    header = (upstream_header or "").strip().lower()

    if "/" in model:
        prefix, rest = model.split("/", 1)
        prefix_lower = prefix.lower()
        known = provider_names()
        if prefix_lower in known:
            creds = load_upstream(prefix_lower)
            return ResolvedUpstream(credentials=creds, upstream_model=rest)

    if header:
        creds = load_upstream(header)
        return ResolvedUpstream(credentials=creds, upstream_model=model)

    known = ", ".join(provider_names()) or "(aucun — créez pellicule.keys)"
    raise KeysError(
        f"Préfixe provider/model requis (providers configurés : {known}), "
        "ou en-tête X-Pellicule-Upstream."
    )


def resolve_provider(provider: str) -> ResolvedUpstream:
    creds = load_upstream(provider.strip().lower())
    return ResolvedUpstream(credentials=creds, upstream_model="")


def chat_completions_url(creds: UpstreamCredentials) -> str:
    base = creds.base_url.rstrip("/")
    if base.endswith("/v1"):
        return f"{base}/chat/completions"
    return f"{base}/v1/chat/completions"


def models_url(creds: UpstreamCredentials) -> str:
    base = creds.base_url.rstrip("/")
    if base.endswith("/v1"):
        return f"{base}/models"
    return f"{base}/v1/models"


def upstream_headers(creds: UpstreamCredentials, *, json_body: bool = False) -> dict[str, str]:
    headers: dict[str, str] = {}
    if creds.api_key:
        headers["Authorization"] = f"Bearer {creds.api_key}"
    if json_body:
        headers["Content-Type"] = "application/json"
    return headers
