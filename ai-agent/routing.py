"""Phase 2: Deterministic alert routing.

Provides severity calculation from burn rates, runbook lookup by SLO name,
and alert routing to channels/teams based on severity and service ownership.
"""

from pathlib import Path
from typing import Any

import yaml

_CONFIG_PATH = Path(__file__).parent / "routing_config.yaml"
_config: dict[str, Any] | None = None


def _load_config(config_path: Path | None = None) -> dict[str, Any]:
    """Load and cache the routing config. Reloads if a custom path is given."""
    global _config
    path = config_path or _CONFIG_PATH
    if _config is None or config_path is not None:
        with open(path) as f:
            _config = yaml.safe_load(f)
    return _config


def calculate_severity(burn_rate: float, config_path: Path | None = None) -> str:
    """Map a burn rate value to a severity level (P1/P2/P3).

    Thresholds are evaluated highest-first; first match wins.
    Returns the lowest severity if no threshold matches.
    """
    cfg = _load_config(config_path)
    thresholds = cfg["severity_thresholds"]
    for entry in thresholds:
        if burn_rate >= entry["min_burn_rate"]:
            return entry["severity"]
    # Fallback to lowest severity
    return thresholds[-1]["severity"]


def lookup_runbook(slo_name: str, config_path: Path | None = None) -> str:
    """Return the runbook URL for a given SLO name.

    Looks up the service portion of the SLO name (everything before the last
    hyphenated segment) in the services config. Falls back to default URL.
    """
    cfg = _load_config(config_path)
    services = cfg.get("services", {})
    defaults = cfg.get("defaults", {})

    # Try exact match on slo_name as service name first
    if slo_name in services:
        return services[slo_name].get("runbook_url", defaults.get("runbook_url", ""))

    # Try matching service prefix: "my-service-latency" -> "my-service"
    parts = slo_name.rsplit("-", 1)
    if len(parts) > 1:
        service_prefix = parts[0]
        if service_prefix in services:
            return services[service_prefix].get(
                "runbook_url", defaults.get("runbook_url", "")
            )

    return defaults.get("runbook_url", "")


def route_alert(
    severity: str, service: str, config_path: Path | None = None
) -> dict[str, Any]:
    """Determine the routing destination for an alert.

    Returns a dict with: team, slack_channel, escalation, channels, notify_team.
    """
    cfg = _load_config(config_path)
    services = cfg.get("services", {})
    defaults = cfg.get("defaults", {})
    routing_rules = cfg.get("routing_rules", {})

    # Service ownership info
    svc = services.get(service, {})
    team = svc.get("team", defaults.get("team", "sre"))
    slack_channel = svc.get("slack_channel", defaults.get("slack_channel", ""))

    # Routing rule for this severity
    rule = routing_rules.get(severity, cfg.get("defaults", {}).get("routing", {}))
    escalation = rule.get("escalation", "notify")
    channels = list(rule.get("channels", []))
    notify_team = rule.get("notify_team", False)

    # If notify_team is set, add the service's channel to the list
    if notify_team and slack_channel and slack_channel not in channels:
        channels.append(slack_channel)

    return {
        "team": team,
        "slack_channel": slack_channel,
        "escalation": escalation,
        "channels": channels,
        "notify_team": notify_team,
    }
