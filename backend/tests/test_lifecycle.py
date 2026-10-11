import pytest

from app.lifecycle import InvalidTransition, Lifecycle


def test_valid_chain_recorded():
    lc = Lifecycle()
    d = {}
    lc.start(d, alert_id="A1", delivery_id="D1", actor="rules")
    for s in ["Generated", "Delivered", "Acknowledged", "Superseded"]:
        lc.transition(d, s, alert_id="A1", delivery_id="D1", actor="test")
    assert d["state"] == "Superseded"
    assert [e["to_state"] for e in lc.for_alert("A1")] == ["Drafted", "Generated", "Delivered", "Acknowledged", "Superseded"]
    assert all(e["actor"] and e["time"] for e in lc.events)


@pytest.mark.parametrize("path,bad", [
    ([], "Acknowledged"),                 # acknowledged before delivered
    ([], "Delivered"),                    # delivered before generated
    (["Generated"], "Acknowledged"),
    (["Generated", "Cancelled"], "Delivered"),   # terminal states are final
    (["Superseded"], "Generated"),
])
def test_invalid_transitions_rejected(path, bad):
    lc = Lifecycle()
    d = {}
    lc.start(d, alert_id="A", delivery_id=None, actor="t")
    for s in path:
        lc.transition(d, s, alert_id="A", delivery_id=None, actor="t")
    n = len(lc.events)
    with pytest.raises(InvalidTransition):
        lc.transition(d, bad, alert_id="A", delivery_id=None, actor="t")
    assert len(lc.events) == n  # nothing recorded for the rejected transition
