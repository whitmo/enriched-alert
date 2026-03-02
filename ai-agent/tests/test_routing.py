import pytest
import yaml

from routing import calculate_severity, lookup_runbook, route_alert


@pytest.fixture
def config_file(tmp_path):
    """Create a temporary routing config for tests."""
    config = {
        "severity_thresholds": [
            {"min_burn_rate": 10.0, "severity": "P1"},
            {"min_burn_rate": 2.0, "severity": "P2"},
            {"min_burn_rate": 0.0, "severity": "P3"},
        ],
        "services": {
            "my-service": {
                "team": "platform-eng",
                "slack_channel": "#platform-alerts",
                "runbook_url": "https://runbooks.internal/my-service",
            },
            "payment-service": {
                "team": "payments",
                "slack_channel": "#payments-alerts",
                "runbook_url": "https://runbooks.internal/payment-service",
            },
        },
        "routing_rules": {
            "P1": {
                "escalation": "page",
                "channels": ["#incident-war-room"],
                "notify_team": True,
            },
            "P2": {
                "escalation": "notify",
                "channels": ["#sre-alerts"],
                "notify_team": True,
            },
            "P3": {
                "escalation": "log",
                "channels": ["#sre-low-priority"],
                "notify_team": False,
            },
        },
        "defaults": {
            "team": "sre",
            "slack_channel": "#sre-alerts",
            "runbook_url": "https://runbooks.internal/unknown-service",
            "routing": {
                "escalation": "notify",
                "channels": ["#sre-alerts"],
                "notify_team": False,
            },
        },
    }
    path = tmp_path / "routing_config.yaml"
    with open(path, "w") as f:
        yaml.dump(config, f)
    return path


# --- calculate_severity ---


class TestCalculateSeverity:
    def test_p1_high_burn_rate(self, config_file):
        assert calculate_severity(15.0, config_path=config_file) == "P1"

    def test_p1_exact_threshold(self, config_file):
        assert calculate_severity(10.0, config_path=config_file) == "P1"

    def test_p2_mid_burn_rate(self, config_file):
        assert calculate_severity(5.0, config_path=config_file) == "P2"

    def test_p2_exact_threshold(self, config_file):
        assert calculate_severity(2.0, config_path=config_file) == "P2"

    def test_p3_low_burn_rate(self, config_file):
        assert calculate_severity(1.0, config_path=config_file) == "P3"

    def test_p3_zero_burn_rate(self, config_file):
        assert calculate_severity(0.0, config_path=config_file) == "P3"

    def test_p3_just_below_p2(self, config_file):
        assert calculate_severity(1.99, config_path=config_file) == "P3"


# --- lookup_runbook ---


class TestLookupRunbook:
    def test_exact_service_match(self, config_file):
        url = lookup_runbook("my-service", config_path=config_file)
        assert url == "https://runbooks.internal/my-service"

    def test_slo_name_with_suffix(self, config_file):
        url = lookup_runbook("my-service-latency", config_path=config_file)
        assert url == "https://runbooks.internal/my-service"

    def test_payment_service(self, config_file):
        url = lookup_runbook("payment-service", config_path=config_file)
        assert url == "https://runbooks.internal/payment-service"

    def test_unknown_service_returns_default(self, config_file):
        url = lookup_runbook("unknown-thing", config_path=config_file)
        assert url == "https://runbooks.internal/unknown-service"

    def test_no_hyphen_unknown(self, config_file):
        url = lookup_runbook("standalone", config_path=config_file)
        assert url == "https://runbooks.internal/unknown-service"


# --- route_alert ---


class TestRouteAlert:
    def test_p1_known_service(self, config_file):
        result = route_alert("P1", "my-service", config_path=config_file)
        assert result["team"] == "platform-eng"
        assert result["escalation"] == "page"
        assert "#incident-war-room" in result["channels"]
        assert result["notify_team"] is True
        # Service channel should be appended when notify_team=True
        assert "#platform-alerts" in result["channels"]

    def test_p2_known_service(self, config_file):
        result = route_alert("P2", "payment-service", config_path=config_file)
        assert result["team"] == "payments"
        assert result["escalation"] == "notify"
        assert "#sre-alerts" in result["channels"]
        assert result["notify_team"] is True
        assert "#payments-alerts" in result["channels"]

    def test_p3_known_service(self, config_file):
        result = route_alert("P3", "my-service", config_path=config_file)
        assert result["team"] == "platform-eng"
        assert result["escalation"] == "log"
        assert "#sre-low-priority" in result["channels"]
        assert result["notify_team"] is False
        # Service channel should NOT be appended when notify_team=False
        assert "#platform-alerts" not in result["channels"]

    def test_unknown_service_uses_defaults(self, config_file):
        result = route_alert("P1", "nonexistent", config_path=config_file)
        assert result["team"] == "sre"
        assert result["slack_channel"] == "#sre-alerts"
        assert result["escalation"] == "page"

    def test_unknown_severity_uses_default_routing(self, config_file):
        result = route_alert("P99", "my-service", config_path=config_file)
        assert result["escalation"] == "notify"
        assert result["notify_team"] is False

    def test_result_has_all_keys(self, config_file):
        result = route_alert("P2", "my-service", config_path=config_file)
        assert "team" in result
        assert "slack_channel" in result
        assert "escalation" in result
        assert "channels" in result
        assert "notify_team" in result
