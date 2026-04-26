# ============================================================
#  InfernoGuard · Fire Risk Prediction System
#  Module  : density.py
#  Purpose : Crowd density estimation from person count
# ============================================================
#
#  Formula  : density = people_count / AREA_CONSTANT
#  Constant : AREA_CONSTANT = 50  (normalised reference area)
#
#  Density thresholds:
#    LOW    →  density < 0.3    (sparse crowd)
#    MEDIUM →  0.3 ≤ density ≤ 0.7  (moderate crowd)
#    HIGH   →  density > 0.7    (dense crowd — elevated risk)
# ============================================================

# Reference area constant (adjust per deployment zone)
AREA_CONSTANT: float = 50.0


def compute_density(people_count: int) -> tuple:
    """
    Convert a raw person count into a normalised density value and label.

    Parameters
    ----------
    people_count : int   Number of persons detected in the current frame

    Returns
    -------
    (density_value: float, density_label: str)
        density_value — continuous score (can exceed 1.0 in very dense crowds)
        density_label — categorical level: "LOW" | "MEDIUM" | "HIGH"
    """
    density = people_count / AREA_CONSTANT

    if density < 0.3:
        label = "LOW"
    elif density <= 0.7:
        label = "MEDIUM"
    else:
        label = "HIGH"

    return round(density, 4), label
