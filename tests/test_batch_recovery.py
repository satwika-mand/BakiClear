from ai.batch_recovery import run_batch_recovery


def test_batch_recovery_report_is_repeatable_and_labeled_simulation():
    report = run_batch_recovery()

    assert report["scenario_count"] == 15
    assert report["total_recovered"] > 0
    assert report["total_recovered"] < report["total_due"]
    assert "simulation" in report["label"].lower()
    assert report["verdict_counts"]["human_approval"] > 0
