# ============================================================
#  InfernoGuard · Fire Risk Prediction System
#  Module  : demo.py
#  Purpose : Offline scenario demo — no camera or server needed
# ============================================================
#
#  Tests all 4 required risk scenarios and prints the result.
#  Perfect for hackathon demonstration without any hardware.
#
#  Run:
#    python demo.py
# ============================================================

from density     import compute_density
from risk_engine import evaluate_risk

# ── Risk level colour codes ──────────────────────────────────────────────────
_COLOUR = {
    "LOW"      : "\033[92m",
    "MEDIUM"   : "\033[93m",
    "HIGH"     : "\033[91m",
    "CRITICAL" : "\033[95m",
    "RESET"    : "\033[0m",
}

def _c(text, level):
    return f"{_COLOUR.get(level,'')}{text}{_COLOUR['RESET']}"


# ── Demo scenarios ───────────────────────────────────────────────────────────

SCENARIOS = [
    {
        "label"     : "Scenario 1 · Empty Area",
        "people"    : 0,
        "fire_conf" : 0.00,
        "movement"  : 0.00,
        "expected"  : "LOW",
    },
    {
        "label"     : "Scenario 2 · Large Crowd, No Fire",
        "people"    : 25,
        "fire_conf" : 0.10,
        "movement"  : 0.40,
        "expected"  : "LOW",
    },
    {
        "label"     : "Scenario 3 · Fire Detected + Dense Crowd",
        "people"    : 35,
        "fire_conf" : 0.75,
        "movement"  : 0.40,
        "expected"  : "HIGH",
    },
    {
        "label"     : "Scenario 4 · Fire + Crowd + Panic Movement",
        "people"    : 40,
        "fire_conf" : 0.85,
        "movement"  : 0.75,
        "expected"  : "CRITICAL",
    },
]


def run_demo():
    print("\n" + "═" * 62)
    print("  🔥  InfernoGuard · Fire Risk Prediction System  🔥")
    print("       Real-time AI Safety Assessment — Demo Mode")
    print("═" * 62 + "\n")

    all_pass = True

    for s in SCENARIOS:
        density_value, density_label = compute_density(s["people"])
        result = evaluate_risk(s["fire_conf"], density_label, density_value, s["movement"])

        status = "✅ PASS" if result["risk"] == s["expected"] else "❌ FAIL"
        if result["risk"] != s["expected"]:
            all_pass = False

        print(f"  {s['label']}")
        print(f"  ┌─ Input  : 👥 People={s['people']}  🔥 Fire={s['fire_conf']}  🏃 Move={s['movement']}")
        print(f"  ├─ Density: {density_label} ({density_value:.2f})")
        risk_str = _c(f"{result['risk']} (score: {result['score']})", result["risk"])
        print(f"  ├─ Risk   : {risk_str}")
        print(f"  ├─ Action : {result['action']}")
        print(f"  └─ Test   : {status}")
        print()

    print("═" * 62)
    if all_pass:
        print("  ✅  All scenarios passed — system is operating correctly.")
    else:
        print("  ❌  Some scenarios failed — review risk engine rules.")
    print("═" * 62 + "\n")


if __name__ == "__main__":
    run_demo()
