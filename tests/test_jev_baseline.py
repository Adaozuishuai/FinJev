from finjev.evals.jev_baseline import _predicted_score_label, summarize


def test_predicted_score_label_prefers_named_probabilities() -> None:
    answer = {
        "score": 1.2,
        "probabilities": {"0": 0.05, "1": 0.1, "2": 0.8, "3": 0.05},
        "legend": {"0": "low", "1": "medium", "2": "high", "3": "critical"},
    }
    assert _predicted_score_label(answer, ["low", "medium", "high", "critical"]) == "high"


def test_summary_reports_high_value_recall_and_does_not_score_policy_action() -> None:
    rows = [
        {
            "status": "ok",
            "model": "fixture",
            "latency_ms": 10,
            "usage": {"input_tokens": 20, "output_tokens": 4},
            "reference": {"event_type": "earnings", "materiality": "critical"},
            "prediction": {
                "event_type": "earnings",
                "materiality": "high",
                "policy_action": "VERIFY",
            },
        },
        {
            "status": "ok",
            "model": "fixture",
            "latency_ms": 20,
            "usage": {"input_tokens": 30, "output_tokens": 5},
            "reference": {"event_type": "financing", "materiality": "high"},
            "prediction": {
                "event_type": "operations",
                "materiality": "medium",
                "policy_action": "ACCEPT",
            },
        },
    ]
    report = summarize(rows)
    assert report["event_type"]["accuracy"] == 0.5
    assert report["high_value_recall"] == 0.5
    assert report["critical_severe_undercall_rate"] == 0.0
    assert report["usage"] == {"input_tokens": 50, "output_tokens": 9}
    assert "policy_action" not in report
