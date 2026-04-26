"""
test_scenarios.py
-----------------
Offline unit-style tests for the risk engine and density calculator.
No camera or YOLO required – verifies rule logic deterministically.

Run:
    python test_scenarios.py
"""

from density import compute_density
from risk_engine import evaluate_risk


def _check(label: str, people: int, fire_conf: float, movement: float,
           expected_risk: str) -> None:
    density_value, density_label = compute_density(people)
    result = evaluate_risk(fire_conf, density_label, density_value, movement)
    status = "✅ PASS" if result["risk"] == expected_risk else "❌ FAIL"
    print(
        f"{status}  [{label}]  "
        f"People:{people:3d} | Fire:{fire_conf:.2f} | Move:{movement:.2f} "
        f"→ {result['risk']:8s} (score: {result['score']:5.1f}) | {result['action']}"
        f"  [expected: {expected_risk}]"
    )


def run_tests() -> None:
    print("=" * 70)
    print("  Fire Risk System – Scenario Tests")
    print("=" * 70)

    # Scenario 1: No people, no fire → LOW
    _check("No people",
           people=0, fire_conf=0.0, movement=0.0,
           expected_risk="LOW")

    # Scenario 2: Many people, no fire, low movement → LOW
    _check("Crowd no fire",
           people=20, fire_conf=0.05, movement=0.2,
           expected_risk="LOW")

    # Scenario 3: Large crowd, moderate movement (no fire) → MEDIUM (movement)
    _check("Crowd + movement",
           people=30, fire_conf=0.1, movement=0.65,
           expected_risk="MEDIUM")

    # Scenario 4: Moderate fire, medium crowd → HIGH
    _check("Fire + medium crowd",
           people=20, fire_conf=0.65, movement=0.3,
           expected_risk="HIGH")

    # Scenario 5: Fire + high crowd + high movement → CRITICAL
    _check("CRITICAL scenario",
           people=40, fire_conf=0.85, movement=0.75,
           expected_risk="CRITICAL")

    # Scenario 6: Only fire confidence above 0.5, small crowd → MEDIUM
    _check("Fire only (low crowd)",
           people=5, fire_conf=0.55, movement=0.1,
           expected_risk="MEDIUM")

    # Scenario 7: High crowd, high movement, no fire → MEDIUM (movement)
    _check("Crowd + high movement no fire",
           people=35, fire_conf=0.0, movement=0.8,
           expected_risk="MEDIUM")

    print("=" * 70)
    print("Tests complete.")


if __name__ == "__main__":
    run_tests()
