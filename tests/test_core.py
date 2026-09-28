from finjev.core.models import NoulAnswer
from finjev.core.policies import WeightedSignal, apply_noul_policy, compose_weighted_score
from finjev.core.state import hash_state, stable_json


def test_state_hash_is_order_independent() -> None:
    assert stable_json({"b": 2, "a": 1}) == stable_json({"a": 1, "b": 2})
    assert hash_state({"b": 2, "a": 1}) == hash_state({"a": 1, "b": 2})


def test_noul_policy_keeps_uncertainty_explicit() -> None:
    decision = apply_noul_policy(NoulAnswer(noul=0.5), positive=0.8, negative=0.3)
    assert decision.action == "VERIFY"


def test_composition_uses_explicit_weights() -> None:
    result = compose_weighted_score(
        [
            # The high signal has twice the weight of the low signal.
            WeightedSignal("high", 1.0, 2.0),
            WeightedSignal("low", 0.0, 1.0),
        ]
    )
    assert result["value"] == 2 / 3
