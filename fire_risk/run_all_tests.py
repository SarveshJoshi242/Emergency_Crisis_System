"""
run_all_tests.py
----------------
Fully self-contained test suite.
No camera, no YOLO, no server needed.

Tests:
  1. density.py  — compute_density() correctness
  2. risk_engine — all four level transitions
  3. movement.py — with synthetic numpy frames
  4. Full pipeline simulation (all 4 required scenarios)
  5. API logic (direct function call, same as uvicorn would do)

Run:
    python run_all_tests.py
Output saved to: test_results.txt
"""
import sys
import json

results = []

def log(msg):
    print(msg)
    results.append(msg)

def passed(label):
    log(f"  ✅ PASS  {label}")

def failed(label, got, expected):
    log(f"  ❌ FAIL  {label} | got={got!r}  expected={expected!r}")

# ──────────────────────────────────────────────────────────────────────────────
log("=" * 65)
log("  FIRE RISK PREDICTION SYSTEM — FULL TEST REPORT")
log("=" * 65)

# ── TEST GROUP 1: density.py ──────────────────────────────────────────────────
log("\n[GROUP 1] density.compute_density()")
log("-" * 40)
from density import compute_density, AREA_CONSTANT

CASES = [
    (0,   0.0,   "LOW"),
    (10,  0.2,   "LOW"),
    (15,  0.3,   "MEDIUM"),
    (25,  0.5,   "MEDIUM"),
    (35,  0.7,   "MEDIUM"),
    (36,  0.72,  "HIGH"),
    (50,  1.0,   "HIGH"),
    (100, 2.0,   "HIGH"),
]

for people, exp_val, exp_label in CASES:
    val, label = compute_density(people)
    ok_val   = abs(val - exp_val) < 0.01
    ok_label = label == exp_label
    tag = f"people={people:3d} → density={val:.4f} [{label}]"
    if ok_val and ok_label:
        passed(tag)
    else:
        failed(tag, (val, label), (exp_val, exp_label))

log(f"\n  [INFO] AREA_CONSTANT = {AREA_CONSTANT}")

# ── TEST GROUP 2: risk_engine.py ──────────────────────────────────────────────
log("\n[GROUP 2] risk_engine.evaluate_risk() — rule transitions")
log("-" * 40)
from risk_engine import evaluate_risk

RULE_CASES = [
    # (label, fire_conf, density_label, density_value, movement, expected_risk, expected_action)
    ("No people, no fire",         0.00, "LOW",    0.00, 0.00, "LOW",      "MONITOR"),
    ("Crowd, no fire, low move",   0.05, "MEDIUM", 0.50, 0.20, "LOW",      "MONITOR"),
    ("Only high movement",         0.10, "LOW",    0.10, 0.65, "MEDIUM",   "NOTIFY_STAFF"),
    ("Only fire >0.5",             0.55, "LOW",    0.05, 0.10, "MEDIUM",   "NOTIFY_STAFF"),
    ("Fire>0.6 + MEDIUM density",  0.65, "MEDIUM", 0.50, 0.30, "HIGH",     "ALERT"),
    ("Fire>0.6 + HIGH density",    0.65, "HIGH",   0.80, 0.30, "HIGH",     "ALERT"),
    ("CRITICAL: all triggers",     0.85, "HIGH",   0.80, 0.75, "CRITICAL", "EVACUATE"),
    ("CRITICAL boundary fire=0.71",0.71, "HIGH",   0.80, 0.61, "CRITICAL", "EVACUATE"),
    ("fire=0.7 (not >0.7) → HIGH", 0.70, "HIGH",   0.80, 0.70, "HIGH",     "ALERT"),
]

for label, fc, dl, dv, mv, exp_risk, exp_action in RULE_CASES:
    r = evaluate_risk(fc, dl, dv, mv)
    score = r["score"]
    ok = r["risk"] == exp_risk and r["action"] == exp_action
    tag = f"{label:38s} → {r['risk']:8s} score={score:5.1f} | {r['action']}"
    if ok:
        passed(tag)
    else:
        failed(tag, (r["risk"], r["action"]), (exp_risk, exp_action))

# ── TEST GROUP 3: movement.py synthetic frame test ────────────────────────────
log("\n[GROUP 3] movement.compute_movement() — synthetic frames")
log("-" * 40)
import numpy as np
from movement import compute_movement

# Identical frames → movement should be 0
frame_a = np.zeros((480, 640, 3), dtype=np.uint8)
frame_b = np.zeros((480, 640, 3), dtype=np.uint8)
score = compute_movement(frame_a, frame_b)
tag = f"Identical black frames → movement={score}"
if score == 0.0:
    passed(tag)
else:
    failed(tag, score, 0.0)

# Completely different frames → score should be very high
frame_c = np.full((480, 640, 3), 200, dtype=np.uint8)
score2 = compute_movement(frame_a, frame_c)
tag2 = f"Black vs bright frame  → movement={score2:.4f} (expect > 0.5)"
if score2 > 0.5:
    passed(tag2)
else:
    failed(tag2, score2, ">0.5")

# First frame None → should return 0
score3 = compute_movement(None, frame_a)
tag3 = f"prev_frame=None        → movement={score3} (expect 0.0)"
if score3 == 0.0:
    passed(tag3)
else:
    failed(tag3, score3, 0.0)

# Partial difference (top half white)
frame_d = np.zeros((480, 640, 3), dtype=np.uint8)
frame_d[:240, :, :] = 200  # top half bright
score4 = compute_movement(frame_a, frame_d)
tag4 = f"Half-different frames  → movement={score4:.4f} (expect ~0.5)"
if 0.3 < score4 < 0.7:
    passed(tag4)
else:
    failed(tag4, score4, "0.3–0.7")

# ── TEST GROUP 4: Full pipeline simulation ────────────────────────────────────
log("\n[GROUP 4] Full integrated pipeline simulation")
log("-" * 40)
log("  Simulates exact flow: detection → movement → density → risk\n")

from density import compute_density
from risk_engine import evaluate_risk

SCENARIOS = [
    {
        "name":        "Scenario A: No People",
        "people":      0,
        "fire_conf":   0.0,
        "movement":    0.0,
        "expect_risk": "LOW",
        "expect_act":  "MONITOR",
    },
    {
        "name":        "Scenario B: Many People, No Fire",
        "people":      25,
        "fire_conf":   0.1,
        "movement":    0.4,
        "expect_risk": "LOW",
        "expect_act":  "MONITOR",
    },
    {
        "name":        "Scenario C: Fire + Crowd",
        "people":      35,
        "fire_conf":   0.75,
        "movement":    0.4,
        "expect_risk": "HIGH",
        "expect_act":  "ALERT",
    },
    {
        "name":        "Scenario D: Fire + Crowd + High Movement (CRITICAL)",
        "people":      40,
        "fire_conf":   0.85,
        "movement":    0.75,
        "expect_risk": "CRITICAL",
        "expect_act":  "EVACUATE",
    },
]

for s in SCENARIOS:
    dv, dl = compute_density(s["people"])
    result  = evaluate_risk(s["fire_conf"], dl, dv, s["movement"])
    ok = result["risk"] == s["expect_risk"] and result["action"] == s["expect_act"]
    log(f"  {s['name']}")
    log(f"    Input  : people={s['people']} | fire={s['fire_conf']} | move={s['movement']}")
    log(f"    Density: {dl} ({dv:.2f})")
    log(f"    Output : {result['risk']} | score={result['score']} | {result['action']}")
    if ok:
        log(f"  ✅ PASS\n")
    else:
        log(f"  ❌ FAIL  expected {s['expect_risk']} / {s['expect_act']}\n")

# ── TEST GROUP 5: API schema validation (no server needed) ────────────────────
log("[GROUP 5] API Pydantic schema validation")
log("-" * 40)
from pydantic import ValidationError
# We test PredictRequest directly without running uvicorn
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from api import PredictRequest, predict

# Valid request
try:
    req = PredictRequest(people_count=40, fire_conf=0.85, movement_score=0.75)
    resp = predict(req)
    tag = f"Valid payload → risk={resp.risk} score={resp.score} action={resp.action}"
    passed(tag)
except Exception as e:
    failed("Valid payload", str(e), "no error")

# Negative fire_conf should fail validation
try:
    bad = PredictRequest(people_count=5, fire_conf=-0.1, movement_score=0.0)
    failed("Negative fire_conf should reject", "no error", "ValidationError")
except ValidationError:
    passed("Negative fire_conf → ValidationError raised correctly")

# Over-range movement_score should fail
try:
    bad2 = PredictRequest(people_count=5, fire_conf=0.5, movement_score=1.5)
    failed("movement_score=1.5 should reject", "no error", "ValidationError")
except ValidationError:
    passed("movement_score=1.5 → ValidationError raised correctly")

# Negative people_count should fail
try:
    bad3 = PredictRequest(people_count=-1, fire_conf=0.0, movement_score=0.0)
    failed("Negative people_count should reject", "no error", "ValidationError")
except ValidationError:
    passed("Negative people_count → ValidationError raised correctly")

# ── TEST GROUP 6: Risk score formula verification ─────────────────────────────
log("\n[GROUP 6] Score formula: (fire×50) + (density×30) + (move×20)")
log("-" * 40)
SCORE_CASES = [
    (0.0,  0.0,  0.0,  0.0),
    (1.0,  1.0,  1.0,  100.0),
    (0.5,  0.5,  0.5,  50.0),
    (0.85, 0.8,  0.75, 91.5),   # fire*50=42.5 + density*30=24 + move*20=15 = 81.5
    (0.7,  0.36, 0.3,  51.8),
]
for fc, dv, mv, exp_score in SCORE_CASES:
    manual = round((fc * 50) + (min(dv,1.0) * 30) + (mv * 20), 2)
    # Compute via engine (risk label doesn't matter for score accuracy)
    dl = "HIGH" if dv > 0.7 else ("MEDIUM" if dv >= 0.3 else "LOW")
    r = evaluate_risk(fc, dl, dv, mv)
    ok = abs(r["score"] - manual) < 0.1
    tag = f"fc={fc} dv={dv} mv={mv} → score={r['score']} (manual={manual})"
    if ok:
        passed(tag)
    else:
        failed(tag, r["score"], manual)

# ── SUMMARY ───────────────────────────────────────────────────────────────────
log("\n" + "=" * 65)
pass_count = sum(1 for r in results if "✅" in r)
fail_count = sum(1 for r in results if "❌" in r)
log(f"  TOTAL PASSED : {pass_count}")
log(f"  TOTAL FAILED : {fail_count}")
log(f"  RESULT       : {'ALL TESTS PASSED ✅' if fail_count == 0 else 'SOME TESTS FAILED ❌'}")
log("=" * 65)

# Write to file
with open("test_results.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(results))
print("\n[INFO] Results saved to test_results.txt")
