"""
Unit tests for Revenue Engine - Direct testing of calculate_revenue function.

Tests:
- Percentage commercial calculation
- Fixed fee commercial
- Level-based commercial with slab matching
- Level-based with no slab match error
- Error cases: missing salary, missing commercial
"""
import pytest
import sys
sys.path.insert(0, '/app/backend')

from services.revenue_engine import calculate_revenue, RevenueCalculationError


class TestPercentageCommercial:
    """Tests for percentage commercial type."""

    def test_percentage_basic_calculation(self):
        """Percentage: salary * pct/100, rounded to rupee."""
        commercial = {
            "type": "percentage",
            "percentage_value": 8.33
        }
        result = calculate_revenue(1200000, commercial)
        
        assert result["commercial_type"] == "percentage"
        assert result["percentage_used"] == 8.33
        assert result["slab_applied"] is None
        # 1200000 * 8.33 / 100 = 99960
        assert result["revenue_amount"] == 99960
        print(f"✅ Percentage: 1200000 * 8.33% = {result['revenue_amount']}")

    def test_percentage_rounding(self):
        """Verify rounding to nearest integer."""
        commercial = {
            "type": "percentage",
            "percentage_value": 10
        }
        # 1234567 * 10% = 123456.7 -> rounds to 123457
        result = calculate_revenue(1234567, commercial)
        assert result["revenue_amount"] == 123457
        print(f"✅ Rounding: 1234567 * 10% = {result['revenue_amount']} (rounded from 123456.7)")

    def test_percentage_with_fee_percentage_key(self):
        """Support legacy key fee_percentage."""
        commercial = {
            "type": "percentage",
            "fee_percentage": 12
        }
        result = calculate_revenue(1000000, commercial)
        assert result["percentage_used"] == 12
        assert result["revenue_amount"] == 120000
        print("✅ Legacy fee_percentage key works")

    def test_percentage_missing_value_raises_error(self):
        """Percentage with no percentage_value raises error."""
        commercial = {
            "type": "percentage",
            "percentage_value": None
        }
        with pytest.raises(RevenueCalculationError) as exc:
            calculate_revenue(1000000, commercial)
        assert "percentage" in str(exc.value).lower()
        print("✅ Missing percentage_value raises RevenueCalculationError")


class TestFixedCommercial:
    """Tests for fixed fee commercial type."""

    def test_fixed_returns_fixed_amount(self):
        """Fixed: returns fixed amount regardless of salary."""
        commercial = {
            "type": "fixed",
            "fixed_fee_amount": 75000
        }
        result = calculate_revenue(1500000, commercial)
        
        assert result["commercial_type"] == "fixed"
        assert result["percentage_used"] is None
        assert result["slab_applied"] is None
        assert result["revenue_amount"] == 75000
        print(f"✅ Fixed fee: always {result['revenue_amount']} regardless of salary")

    def test_fixed_with_fixed_amount_key(self):
        """Support alternative key fixed_amount."""
        commercial = {
            "type": "fixed",
            "fixed_amount": 100000
        }
        result = calculate_revenue(2000000, commercial)
        assert result["revenue_amount"] == 100000
        print("✅ Alternative fixed_amount key works")

    def test_fixed_missing_amount_raises_error(self):
        """Fixed with no amount raises error."""
        commercial = {
            "type": "fixed",
            "fixed_fee_amount": None
        }
        with pytest.raises(RevenueCalculationError) as exc:
            calculate_revenue(1000000, commercial)
        assert "fixed" in str(exc.value).lower()
        print("✅ Missing fixed_fee_amount raises RevenueCalculationError")


class TestLevelBasedCommercial:
    """Tests for level-based (slab) commercial type."""

    def test_level_based_matches_correct_slab(self):
        """Level-based: matches salary to correct slab."""
        commercial = {
            "type": "level_based",
            "level_config": [
                {"min_salary": 100000, "max_salary": 1200000, "percentage": 8.33},
                {"min_salary": 1200001, "max_salary": 2000000, "percentage": 10.0},
                {"min_salary": 2000001, "max_salary": 3000000, "percentage": 12.0}
            ]
        }
        
        # Test salary in first slab
        result = calculate_revenue(1000000, commercial)
        assert result["commercial_type"] == "level_based"
        assert result["percentage_used"] == 8.33
        assert result["slab_applied"]["min_salary"] == 100000
        assert result["slab_applied"]["max_salary"] == 1200000
        # 1000000 * 8.33% = 83300
        assert result["revenue_amount"] == 83300
        print(f"✅ Slab 1: 1000000 * 8.33% = {result['revenue_amount']}")

    def test_level_based_second_slab(self):
        """Level-based: matches salary in second slab."""
        commercial = {
            "type": "level_based",
            "level_config": [
                {"min_salary": 100000, "max_salary": 1200000, "percentage": 8.33},
                {"min_salary": 1200001, "max_salary": 2000000, "percentage": 10.0},
                {"min_salary": 2000001, "max_salary": 3000000, "percentage": 12.0}
            ]
        }
        
        result = calculate_revenue(1500000, commercial)
        assert result["percentage_used"] == 10.0
        assert result["slab_applied"]["min_salary"] == 1200001
        # 1500000 * 10% = 150000
        assert result["revenue_amount"] == 150000
        print(f"✅ Slab 2: 1500000 * 10% = {result['revenue_amount']}")

    def test_level_based_third_slab(self):
        """Level-based: matches salary in third slab."""
        commercial = {
            "type": "level_based",
            "level_config": [
                {"min_salary": 100000, "max_salary": 1200000, "percentage": 8.33},
                {"min_salary": 1200001, "max_salary": 2000000, "percentage": 10.0},
                {"min_salary": 2000001, "max_salary": 3000000, "percentage": 12.0}
            ]
        }
        
        result = calculate_revenue(2500000, commercial)
        assert result["percentage_used"] == 12.0
        # 2500000 * 12% = 300000
        assert result["revenue_amount"] == 300000
        print(f"✅ Slab 3: 2500000 * 12% = {result['revenue_amount']}")

    def test_level_based_boundary_match(self):
        """Level-based: boundary salary exactly on min/max matches."""
        commercial = {
            "type": "level_based",
            "level_config": [
                {"min_salary": 100000, "max_salary": 1200000, "percentage": 8.33},
                {"min_salary": 1200001, "max_salary": 2000000, "percentage": 10.0}
            ]
        }
        
        # Exact max of first slab
        result = calculate_revenue(1200000, commercial)
        assert result["percentage_used"] == 8.33
        print("✅ Boundary 1200000 matches first slab (8.33%)")

    def test_level_based_no_slab_match_raises_error(self):
        """Level-based: raises error if no slab matched."""
        commercial = {
            "type": "level_based",
            "level_config": [
                {"min_salary": 100000, "max_salary": 1200000, "percentage": 8.33},
                {"min_salary": 1200001, "max_salary": 2000000, "percentage": 10.0}
            ]
        }
        
        # Salary too high (no slab covers > 2000000)
        with pytest.raises(RevenueCalculationError) as exc:
            calculate_revenue(3000000, commercial)
        assert "slab" in str(exc.value).lower()
        print("✅ No slab match raises RevenueCalculationError")

    def test_level_based_salary_too_low(self):
        """Level-based: raises error if salary below all slabs."""
        commercial = {
            "type": "level_based",
            "level_config": [
                {"min_salary": 100000, "max_salary": 1200000, "percentage": 8.33}
            ]
        }
        
        # Salary too low
        with pytest.raises(RevenueCalculationError) as exc:
            calculate_revenue(50000, commercial)
        assert "slab" in str(exc.value).lower()
        print("✅ Salary too low raises RevenueCalculationError")

    def test_level_based_empty_config_raises_error(self):
        """Level-based: empty level_config raises error."""
        commercial = {
            "type": "level_based",
            "level_config": []
        }
        
        with pytest.raises(RevenueCalculationError) as exc:
            calculate_revenue(1000000, commercial)
        assert "configured" in str(exc.value).lower() or "slab" in str(exc.value).lower()
        print("✅ Empty level_config raises RevenueCalculationError")


class TestErrorCases:
    """Tests for error scenarios."""

    def test_missing_salary_raises_error(self):
        """Missing salary raises error (no silent fallback to 0)."""
        commercial = {"type": "percentage", "percentage_value": 10}
        
        with pytest.raises(RevenueCalculationError) as exc:
            calculate_revenue(0, commercial)
        assert "salary" in str(exc.value).lower()
        print("✅ Zero salary raises RevenueCalculationError")

    def test_negative_salary_raises_error(self):
        """Negative salary raises error."""
        commercial = {"type": "percentage", "percentage_value": 10}
        
        with pytest.raises(RevenueCalculationError) as exc:
            calculate_revenue(-100000, commercial)
        assert "salary" in str(exc.value).lower()
        print("✅ Negative salary raises RevenueCalculationError")

    def test_none_salary_raises_error(self):
        """None salary raises error."""
        commercial = {"type": "percentage", "percentage_value": 10}
        
        with pytest.raises(RevenueCalculationError) as exc:
            calculate_revenue(None, commercial)
        assert "salary" in str(exc.value).lower()
        print("✅ None salary raises RevenueCalculationError")

    def test_missing_commercial_raises_error(self):
        """Missing commercial config raises error."""
        with pytest.raises(RevenueCalculationError) as exc:
            calculate_revenue(1000000, None)
        assert "commercial" in str(exc.value).lower()
        print("✅ None commercial raises RevenueCalculationError")

    def test_empty_commercial_raises_error(self):
        """Empty commercial config raises error."""
        with pytest.raises(RevenueCalculationError) as exc:
            calculate_revenue(1000000, {})
        assert "commercial" in str(exc.value).lower()
        print("✅ Empty commercial raises RevenueCalculationError")

    def test_unknown_type_raises_error(self):
        """Unknown commercial type raises error."""
        commercial = {"type": "unknown_type"}
        
        with pytest.raises(RevenueCalculationError) as exc:
            calculate_revenue(1000000, commercial)
        assert "unknown" in str(exc.value).lower()
        print("✅ Unknown type raises RevenueCalculationError")


class TestStructuredReturn:
    """Verify structured return format."""

    def test_return_structure_percentage(self):
        """Verify return structure for percentage type."""
        commercial = {"type": "percentage", "percentage_value": 10}
        result = calculate_revenue(1000000, commercial)
        
        assert "salary" in result
        assert "commercial_type" in result
        assert "slab_applied" in result
        assert "percentage_used" in result
        assert "revenue_amount" in result
        
        assert result["salary"] == 1000000
        assert result["commercial_type"] == "percentage"
        assert result["slab_applied"] is None
        assert result["percentage_used"] == 10
        assert result["revenue_amount"] == 100000
        print("✅ Structured return verified for percentage")

    def test_return_structure_level_based(self):
        """Verify return structure for level_based type."""
        commercial = {
            "type": "level_based",
            "level_config": [
                {"min_salary": 100000, "max_salary": 2000000, "percentage": 10}
            ]
        }
        result = calculate_revenue(1000000, commercial)
        
        assert result["commercial_type"] == "level_based"
        assert result["slab_applied"] is not None
        assert "min_salary" in result["slab_applied"]
        assert "max_salary" in result["slab_applied"]
        assert "percentage" in result["slab_applied"]
        print("✅ Structured return verified for level_based")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
