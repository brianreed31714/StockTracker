"""Legacy deployment-agent supervision policy during TradingOps migration.

Compatibility default is enabled until a separately verified Windows cutover.
Set LEGACY_DEPLOYMENT_AGENT_SUPERVISION_ENABLED=0 in host configuration to
stop the supervisor from *starting* the legacy agent. This does not stop an
already running agent or disable Windows Scheduled Tasks.
"""


def supervise_legacy_deployment_agent(value: str | None) -> bool:
    if value is None:
        return True
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError("Invalid LEGACY_DEPLOYMENT_AGENT_SUPERVISION_ENABLED; expected 1 or 0")
