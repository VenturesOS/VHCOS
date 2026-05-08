"""
Regression tests for AI capture consistency — ensures top-card data
(experience_years, current_ctc, expected_ctc, notice_period, location)
are extracted correctly across the 3 common Naukri layouts:

  A) COMPACT:   "10y ₹18 Lacs (expects: ₹25 Lacs) Bangalore"  (inline adjacency)
  B) LABELED:   "Experience\n19 Years\nCurrent CTC\n₹25 Lacs"  (stacked labels)
  C) MIXED:     compact header + labeled notice period

These fixtures mirror the real Naukri Resdex DOM text captured by the extension.
Regressions here indicate a data-leakage bug similar to the Ramakant case.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..")))

from services.naukri_regex_parser import extract_full_profile_regex  # noqa: E402


# ────────────────────────────────────────────────────────────────────────────
# Fixtures — representative top-card layouts
# ────────────────────────────────────────────────────────────────────────────

# Layout A: compact adjacency (most common — "19y ₹25 Lacs Pune")
FIX_COMPACT = """Koushik Sangiri Save123
10y ₹ 18 Lacs (expects: ₹ 25 Lacs) Bangalore
Current: Senior Architect at TCS
Notice Period: 2 Months
Key Skills
Java, Spring Boot, AWS, Kubernetes
"""

# Layout B: labeled stacked (Ramakant's layout — the failing case)
FIX_LABELED = """Ramakant Pandey Save456
Senior Manager - IR and ER at Advik Hi Tech Pvt Ltd since Aug 2023
Experience
19 Years
Current CTC
₹ 25 Lacs
Expected CTC
₹ 34 Lacs
Current Location
Rudrapur, Pantnagar
Notice Period
3 Months
Highest Qualification
MBA/PGDM
Key Skills
Industrial Relations, Employee Relations, Union Management
"""

# Layout C: year+month compact w/ Immediate
FIX_COMPACT_YM = """Tushar Sonawane Save9
14y 0m  ₹ 30 Lacs Pune
Immediate Joiner
Current: Lead Engineer at Infosys
"""

# Layout D: labeled with "15 Days or less" notice
FIX_LABELED_15DAYS = """Mary Lee Save12
Experience
8 Years
Current CTC
₹ 22 Lacs
Expected CTC
₹ 30 Lacs
Current Location
Chennai
Notice Period
15 Days or less
"""

# Layout E: labeled with "5 Years 3 Months" (year+month label)
FIX_LABELED_YM = """John Doe Save55
Experience
5 Years 3 Months
Current CTC
₹ 12 Lacs
Expected CTC
₹ 18 Lacs
Current Location
Mumbai
Notice Period
Immediate
"""


# ────────────────────────────────────────────────────────────────────────────
# Tests
# ────────────────────────────────────────────────────────────────────────────

def test_compact_layout_extracts_top_card():
    r = extract_full_profile_regex(FIX_COMPACT)
    assert r["experience_years"] == 10.0, f"exp: {r['experience_years']}"
    assert r["current_ctc"] == 1_800_000, f"ctc: {r['current_ctc']}"
    assert r["expected_ctc"] == 2_500_000, f"exp_ctc: {r['expected_ctc']}"
    assert r["notice_period"] == "2 Months"
    assert r["location"] == "Bangalore"


def test_labeled_layout_extracts_top_card_ramakant_case():
    """Regression: the Ramakant Pandey bug — labeled top-card was leaking 0y / Unknown."""
    r = extract_full_profile_regex(FIX_LABELED)
    assert r["experience_years"] == 19.0, f"exp: {r['experience_years']}"
    assert r["current_ctc"] == 2_500_000, f"ctc: {r['current_ctc']}"
    assert r["expected_ctc"] == 3_400_000, f"exp_ctc: {r['expected_ctc']}"
    assert r["notice_period"] == "3 Months"
    assert "Rudrapur" in (r["location"] or "") or "Pantnagar" in (r["location"] or "")
    assert "Advik" in (r["current_employer"] or "")


def test_compact_ym_layout_immediate():
    r = extract_full_profile_regex(FIX_COMPACT_YM)
    assert r["experience_years"] == 14.0
    assert r["current_ctc"] == 3_000_000
    assert r["notice_period"] == "Immediate"
    assert r["location"] == "Pune"


def test_labeled_15_days_or_less():
    r = extract_full_profile_regex(FIX_LABELED_15DAYS)
    assert r["experience_years"] == 8.0
    assert r["current_ctc"] == 2_200_000
    assert r["expected_ctc"] == 3_000_000
    assert r["notice_period"] == "15 Days or less"
    assert r["notice_period_days"] == 15
    assert r["location"] == "Chennai"


def test_labeled_with_years_and_months():
    r = extract_full_profile_regex(FIX_LABELED_YM)
    # 5 Years 3 Months -> 5.03 (custom formula)
    assert r["experience_years"] == 5.03, f"exp: {r['experience_years']}"
    assert r["current_ctc"] == 1_200_000
    assert r["expected_ctc"] == 1_800_000
    assert r["notice_period"] == "Immediate"
    assert r["location"] == "Mumbai"


def test_no_data_loss_when_only_labels_present():
    """If ONLY labels are present (no adjacency), must still extract."""
    t = """Some Name
Experience
12 Years
Current CTC
₹ 20 Lacs
Notice Period
1 Month
"""
    r = extract_full_profile_regex(t)
    assert r["experience_years"] == 12.0
    assert r["current_ctc"] == 2_000_000
    assert r["notice_period"] in ("1 Month", "1 Months")


if __name__ == "__main__":
    tests = [
        test_compact_layout_extracts_top_card,
        test_labeled_layout_extracts_top_card_ramakant_case,
        test_compact_ym_layout_immediate,
        test_labeled_15_days_or_less,
        test_labeled_with_years_and_months,
        test_no_data_loss_when_only_labels_present,
    ]
    passed = 0
    for t in tests:
        try:
            t()
            print(f"✅ {t.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"❌ {t.__name__}: {e}")
    print(f"\n{passed}/{len(tests)} passed")
    sys.exit(0 if passed == len(tests) else 1)
