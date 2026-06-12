"""Regression tests for the Phase 57.2 graded V2 name matcher.

Tuned against the 2,372-card badge-audit benchmark: precision went
0.763 → 0.976 (67 of 71 wrong-person badges eliminated). Every FP pair
below is a REAL wrong-person badge from production audits; every TP pair
is a real correct badge that must keep working.

Grades: 0 = no match, 1 = weak (needs a strong corroborator), 2 = strong.

Run: cd /app/backend && python -m pytest tests/test_name_match_v2.py -v
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from routes.extension_check import _loose_name_match_v2 as grade  # noqa: E402
from routes.extension_check import _V2_STRONG_CORROBS  # noqa: E402


# ── Real production false positives — must NOT match at all ──────────────
def test_middle_token_contradiction_rejected():
    # first+last agree but the actual given names differ
    assert grade("Mohd Monis Siddiqui", "MOHD. MOAZZAM SIDDIQUI") == 0


def test_different_surnames_rejected():
    assert grade("Ramesh Kannan", "RAMESH KALIYAN") == 0
    assert grade("Akash G. Bangalwar", "Akash gangwar") == 0
    assert grade("Abdul Rab", "Abdul Wahab") == 0
    assert grade("Deepak Giri", "Deepak gaur") == 0
    assert grade("Abhishek Kumar Jha", "Abhishek Kalra") == 0
    assert grade("Ajay Kumar Srivastav", "Ajay  Kumar Prasad") == 0
    assert grade("Aakash Kumar", "Aakash Kulkarni") == 0


def test_initials_contradiction_rejected():
    # 1-2 char tokens must be initials of SOME other-side token
    assert grade("Amit Saraswat", "Amit Kr") == 0          # K ≠ Saraswat
    assert grade("Ashok Subramani", "ASHOK M R") == 0      # M/R ≠ Subramani
    assert grade("Anandu Suresh", "Anandu V M") == 0       # V/M ≠ Suresh
    assert grade("ARJUN RJ", "Arjun Chaturvedi") == 0      # RJ ≠ Chaturvedi
    assert grade("ASHWINI S", "Ashwini Raj Pandey") == 0   # S ≠ Raj/Pandey


# ── Real production true positives — must still match ────────────────────
def test_exact_and_case_variants_strong():
    assert grade("Ramesh Kannan", "Ramesh kannan") == 2
    assert grade("Prasanna Kumar Dash", "Prasanna kumar Dash") == 2
    assert grade("KAUSHIK CHAKRABORTY", "KAUSHIK CHAKRABORTY") == 2


def test_compatible_initials_still_match():
    assert grade("Ramesh K", "Ramesh Kannan") >= 1         # K = Kannan ✓
    assert grade("Rajkumar P", "Rajkumar Patel") >= 1


def test_token_reorder_strong():
    assert grade("Kannan Ramesh", "Ramesh Kannan") == 2


def test_letter_split_despace_strong():
    assert grade("A J I T H", "Ajith") == 2


def test_typo_tolerance_weak():
    # same surname + one-char typo in given name → weak (needs corroborator)
    assert grade("Rajut Gupta", "Rajat Gupta") == 1


def test_single_vs_multi_weak():
    # "Yash" card vs "Yash Vardhan" in bank — possible but weak evidence
    assert grade("Yash", "Yash Vardhan") == 1


def test_single_exact_strong():
    assert grade("Nupur", "Nupur") == 2


# ── Corroborator gating contract ──────────────────────────────────────────
def test_strong_corroborator_set_contents():
    assert "employer" in _V2_STRONG_CORROBS
    assert "location" in _V2_STRONG_CORROBS
    # coincidence-prone signals must NOT be able to confirm a weak name
    assert "experience" not in _V2_STRONG_CORROBS
    assert "education" not in _V2_STRONG_CORROBS
    assert "ctc" not in _V2_STRONG_CORROBS
    assert "skills" not in _V2_STRONG_CORROBS  # live FP: "Amit Saraswat" → "amit" via shared "sales" skill


def test_weak_grade_with_experience_only_would_not_badge():
    """Replicates the route's gating math for a real FP:
    'Rakesh Kumar Thakur' vs bank 'Rakesh' with [name, experience]."""
    g = grade("Rakesh Kumar Thakur", "Rakesh")
    signals = ["name", "experience"]
    corrob = len(signals) >= 2
    if g and g < 2:
        corrob = corrob and any(s in _V2_STRONG_CORROBS for s in signals)
    assert g == 1 and corrob is False
