#!/usr/bin/env python3
"""Power / CI-width arithmetic for the verdict-probe AUROC (Hanley-McNeil 1982 normal approximation).

All inputs are assumptions stated on the command line or in the table; nothing here is measured except
the class counts passed in. Run: python3 probe_power.py
"""
import math
from statistics import NormalDist

N = NormalDist()
Z975, Z95 = N.inv_cdf(0.975), N.inv_cdf(0.95)


def hm_se(auc, n1, n0):
    q1 = auc / (2 - auc)
    q2 = 2 * auc ** 2 / (1 + auc)
    v = (auc * (1 - auc) + (n1 - 1) * (q1 - auc ** 2) + (n0 - 1) * (q2 - auc ** 2)) / (n1 * n0)
    return math.sqrt(v)


def half_width(auc, n1, n0):
    return Z975 * hm_se(auc, n1, n0)


def n_for_halfwidth(auc, prev, hw, deff=1.0):
    for n in range(20, 5000):
        n1 = max(2, round(n * prev)); n0 = n - n1
        if half_width(auc, n1, n0) * math.sqrt(deff) <= hw:
            return n
    return None


def power_kill(auc_true, auc_null, n1, n0):
    """P(lower one-sided 95% bound of AUROC > auc_null) when truth is auc_true (probe 'alive' test)."""
    se = hm_se(auc_true, n1, n0)
    return 1 - N.cdf((auc_null - auc_true) / se + Z95)


def n_for_power(auc_true, auc_null, prev, power=0.8):
    for n in range(20, 5000):
        n1 = max(2, round(n * prev)); n0 = n - n1
        if power_kill(auc_true, auc_null, n1, n0) >= power:
            return n
    return None


def paired_diff_n(auc_a, auc_b, prev, rho, power=0.8):
    """N for a one-sided 5% test that AUC_a - AUC_b > 0, SE of the difference from HM SEs and an assumed correlation rho."""
    for n in range(20, 8000):
        n1 = max(2, round(n * prev)); n0 = n - n1
        sa, sb = hm_se(auc_a, n1, n0), hm_se(auc_b, n1, n0)
        sd = math.sqrt(sa ** 2 + sb ** 2 - 2 * rho * sa * sb)
        if 1 - N.cdf(Z95 - (auc_a - auc_b) / sd) >= power:
            return n
    return None


if __name__ == "__main__":
    print("1. 95% CI half-width of AUROC for the observed class counts")
    for label, n1, n0 in [("all 76 (20 pos / 56 neg)", 20, 56), ("sound 66 (18/48)", 18, 48),
                          ("sound, non-empty patch 55 (18/37)", 18, 37), ("non-empty patch 64 (19/45)", 19, 45),
                          ("all 129 dev tasks at 27% resolved (35/94)", 35, 94), ("114 sound dev tasks at 25% (28/86)", 28, 86)]:
        print(f"  {label:48s}", "  ".join(f"AUC {a:.2f}: +/-{half_width(a, n1, n0):.3f}" for a in (0.6, 0.7, 0.8)))
    print("\n2. N traces (independent tasks) for 95% CI half-width, positive rate 0.27")
    for a in (0.65, 0.70, 0.75, 0.80):
        print(f"  AUC {a:.2f}: half-width 0.10 -> N={n_for_halfwidth(a, .27, .10)}, 0.075 -> N={n_for_halfwidth(a, .27, .075)}, 0.05 -> N={n_for_halfwidth(a, .27, .05)}")
    print("\n3. Kill test 'lower one-sided 95% bound > 0.65' (probe alive): power at current counts, and N for 80% power (prev 0.27)")
    for a in (0.70, 0.75, 0.80, 0.85):
        print(f"  true AUC {a:.2f}: power at 18/37 = {power_kill(a, .65, 18, 37):.2f}, at 28/86 = {power_kill(a, .65, 28, 86):.2f}, N for 80% = {n_for_power(a, .65, .27)}")
    print("\n4. Probe must beat the best cheap baseline: N for 80% power of a one-sided paired test (assumed rho between the two score sets)")
    for base in (0.75, 0.80):
        for gap in (0.05, 0.10, 0.15):
            if base + gap <= 0.97:
                print(f"  baseline {base:.2f}, probe {base+gap:.2f}: " + ", ".join(f"rho={r}: N={paired_diff_n(base+gap, base, .27, r)}" for r in (0.3, 0.5, 0.7)))
    print("\n5. Repeated runs of the same tasks: effective independent labels = k / (1 + (k-1) * ICC)")
    for icc in (0.70, 0.75):
        print(f"  ICC {icc}: k=2 -> {2/(1+icc):.2f}, k=3 -> {3/(1+2*icc):.2f}, k=5 -> {5/(1+4*icc):.2f} per task")
