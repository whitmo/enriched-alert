"""Phase 2: Deterministic alert routing.

Provides severity calculation from burn rates, runbook lookup by SLO name,
and alert routing to channels/teams based on severity and service ownership.
"""

import logging
import math
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger("ai-agent.routing")

_VALID_SEVERITIES = {"P1", "P2", "P3"}

_CONFIG_PATH = Path(__file__).parent / "routing_config.yaml"
_config: dict[str, Any] | None = None


def _validate_config(cfg: dict[str, Any]) -> None:
    """Validate routing config structure and values. Raises ValueError on problems."""
    # severity_thresholds must exist and be non-empty
    thresholds = cfg.get("severity_thresholds")
    if not thresholds or not isinstance(thresholds, list):
        raise ValueError("routing config: severity_thresholds must be a non-empty list")

    prev_rate: float | None = None
    for i, entry in enumerate(thresholds):
        if "min_burn_rate" not in entry or "severity" not in entry:
            raise ValueError(
                f"routing config: severity_thresholds[{i}] missing required keys"
            )
        sev = entry["severity"]
        if sev not in _VALID_SEVERITIES:
            raise ValueError(
                f"routing config: invalid severity '{sev}' at index {i}, "
                f"must be one of {_VALID_SEVERITIES}"
            )
        rate = float(entry["min_burn_rate"])
        if prev_rate is not None and rate >= prev_rate:
            raise ValueError(
                f"routing config: severity_thresholds not in descending order "
                f"at index {i} ({rate} >= {prev_rate})"
            )
        prev_rate = rate


def _load_config(config_path: Path | None = None) -> dict[str, Any]:
    """Load and cache the routing config. Reloads if a custom path is given."""
    global _config
    path = config_path or _CONFIG_PATH
    if _config is None or config_path is not None:
        with open(path) as f:
            cfg = yaml.safe_load(f)
        if not cfg or not isinstance(cfg, dict):
            raise ValueError("routing config: file is empty or not a YAML mapping")
        _validate_config(cfg)
        _config = cfg
    return _config


def calculate_severity(
    burn_rate: float | None, config_path: Path | None = None
) -> str:
    """Map a burn rate value to a severity level (P1/P2/P3).

    Special cases:
    - None  → P3 with warning (missing data)
    - NaN   → P1 (data corruption is urgent)
    - < 0   → P3 with warning (nonsensical value)

    Thresholds are evaluated highest-first; first match wins.
    Returns the lowest severity if no threshold matches.
    """
    cfg = _load_config(config_path)
    thresholds = cfg["severity_thresholds"]

    if burn_rate is None:
        logger.warning("burn_rate is None, treating as P3")
        return "P3"

    if math.isnan(burn_rate):
        logger.warning("burn_rate is NaN (possible data corruption), treating as P1")
        return "P1"

    if burn_rate < 0:
        logger.warning("burn_rate is negative (%s), treating as P3", burn_rate)
        return "P3"

    for entry in thresholds:
        if burn_rate >= entry["min_burn_rate"]:
            return entry["severity"]
    # Fallback to lowest severity
    return thresholds[-1]["severity"]


def lookup_runbook(slo_name: str, config_path: Path | None = None) -> str:
    """Return the runbook URL for a given SLO name.

    Strips known SLO type suffixes (e.g. -error-rate, -latency-p99) from the
    name to find the owning service. Falls back to default URL.
    """
    cfg = _load_config(config_path)
    services = cfg.get("services", {})
    defaults = cfg.get("defaults", {})
    slo_suffixes = cfg.get("slo_suffixes", [])

    # Try exact match on slo_name as service name first
    if slo_name in services:
        return services[slo_name].get("runbook_url", defaults.get("runbook_url", ""))

    # Strip known SLO suffixes (longest-first ordering in config)
    for suffix in slo_suffixes:
        candidate = f"-{suffix}"
        if slo_name.endswith(candidate):
            service_prefix = slo_name[: -len(candidate)]
            if service_prefix in services:
                return services[service_prefix].get(
                    "runbook_url", defaults.get("runbook_url", "")
                )

    # Legacy fallback: split on last hyphen
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
