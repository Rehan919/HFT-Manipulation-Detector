from backend.detector import resolve_signal


def test_resolve_signal_marks_high_risk_when_anomaly_has_strong_spike() -> None:
    assert resolve_signal(True, 5.2, 1.4) == "HIGH_RISK"


def test_resolve_signal_marks_suspicious_when_anomaly_has_moderate_spike() -> None:
    assert resolve_signal(True, 3.5, 1.1) == "SUSPICIOUS"


def test_resolve_signal_marks_normal_for_stable_event() -> None:
    assert resolve_signal(False, 0.7, 1.2) == "NORMAL"
