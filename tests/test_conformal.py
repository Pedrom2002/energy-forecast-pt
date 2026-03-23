"""
Tests for conformal prediction CI support in the prediction layer.

Verifies that:
- _compute_ci_half_width returns "conformal" method and uses conformal_q90
  when a calibration quantile is present.
- _compute_ci_half_width falls back to "gaussian_z_rmse" when conformal_q90
  is absent.
- The conformal and Gaussian half-widths are numerically distinct (they use
  different base quantities: q90 vs Z_SCORE_90 × RMSE).
- Region and hour scaling applies consistently under both methods.
- PredictionResponse.ci_method is surfaced correctly in the API response.
"""

import pytest

from src.api.prediction import Z_SCORE_90, _compute_ci_half_width, _hour_scale_factor, _scaled_rmse


class TestComputeCIHalfWidth:
    """Unit tests for _compute_ci_half_width."""

    RMSE = 86.55
    REGION = "Lisboa"
    HOUR_PEAK = 14  # peak hours → hour_scale=1.15
    HOUR_NIGHT = 3  # night hours → hour_scale=0.85
    HOUR_TRANS = 7  # transition → hour_scale=1.0
    Q90 = 50.0

    def test_conformal_method_when_q90_present(self) -> None:
        """Returns 'conformal' method when conformal_q90 is provided."""
        _, method = _compute_ci_half_width(self.RMSE, self.REGION, self.HOUR_PEAK, self.Q90)
        assert method == "conformal"

    def test_gaussian_method_when_q90_absent(self) -> None:
        """Falls back to 'gaussian_z_rmse' when conformal_q90 is None."""
        _, method = _compute_ci_half_width(self.RMSE, self.REGION, self.HOUR_PEAK, None)
        assert method == "gaussian_z_rmse"

    def test_conformal_differs_from_gaussian(self) -> None:
        """Conformal and Gaussian half-widths must be numerically different."""
        hw_conf, _ = _compute_ci_half_width(self.RMSE, self.REGION, self.HOUR_PEAK, self.Q90)
        hw_gauss, _ = _compute_ci_half_width(self.RMSE, self.REGION, self.HOUR_PEAK, None)
        assert abs(hw_conf - hw_gauss) > 0.1, f"Expected conformal ({hw_conf:.2f}) ≠ gaussian ({hw_gauss:.2f})"

    def test_conformal_value_peak_hour(self) -> None:
        """Conformal half-width = q90 × region_scale × hour_scale (peak)."""
        from src.api.prediction import REGION_UNCERTAINTY_SCALE

        hw, method = _compute_ci_half_width(self.RMSE, self.REGION, self.HOUR_PEAK, self.Q90)
        region_scale = REGION_UNCERTAINTY_SCALE["Lisboa"]  # 1.10
        expected = self.Q90 * region_scale * 1.15  # peak hour_scale
        assert abs(hw - expected) < 1e-9
        assert method == "conformal"

    def test_conformal_value_night_hour(self) -> None:
        """Night-hour conformal half-width uses hour_scale=0.85."""
        from src.api.prediction import REGION_UNCERTAINTY_SCALE

        hw, _ = _compute_ci_half_width(self.RMSE, self.REGION, self.HOUR_NIGHT, self.Q90)
        region_scale = REGION_UNCERTAINTY_SCALE["Lisboa"]
        expected = self.Q90 * region_scale * 0.85
        assert abs(hw - expected) < 1e-9

    def test_conformal_value_transition_hour(self) -> None:
        """Transition-hour conformal half-width uses hour_scale=1.0."""
        from src.api.prediction import REGION_UNCERTAINTY_SCALE

        hw, _ = _compute_ci_half_width(self.RMSE, self.REGION, self.HOUR_TRANS, self.Q90)
        region_scale = REGION_UNCERTAINTY_SCALE["Lisboa"]
        expected = self.Q90 * region_scale * 1.0
        assert abs(hw - expected) < 1e-9

    def test_gaussian_value_matches_z_times_scaled_rmse(self) -> None:
        """Gaussian half-width = Z_SCORE_90 × _scaled_rmse(...)."""
        hw, method = _compute_ci_half_width(self.RMSE, self.REGION, self.HOUR_PEAK, None)
        expected = Z_SCORE_90 * _scaled_rmse(self.RMSE, self.REGION, self.HOUR_PEAK)
        assert abs(hw - expected) < 1e-9
        assert method == "gaussian_z_rmse"

    def test_custom_scale_dict_overrides_default(self) -> None:
        """Custom scale_dict is used in place of module-level REGION_UNCERTAINTY_SCALE."""
        custom = {"Lisboa": 2.0}
        hw_custom, _ = _compute_ci_half_width(self.RMSE, "Lisboa", self.HOUR_PEAK, self.Q90, scale_dict=custom)
        hw_default, _ = _compute_ci_half_width(self.RMSE, "Lisboa", self.HOUR_PEAK, self.Q90, scale_dict=None)
        # custom scale 2.0 vs default 1.10 — must differ
        assert abs(hw_custom - hw_default) > 0.1

    def test_unknown_region_uses_fallback_scale_1(self) -> None:
        """Unknown region defaults to scale=1.0 (neutral)."""
        hw, _ = _compute_ci_half_width(self.RMSE, "Madeira", self.HOUR_PEAK, self.Q90)
        expected = self.Q90 * 1.0 * 1.15
        assert abs(hw - expected) < 1e-9

    @pytest.mark.parametrize(
        "hour,expected_scale",
        [
            (0, 0.85),  # night
            (5, 0.85),  # still night
            (6, 1.0),  # transition starts
            (7, 1.0),  # transition
            (8, 1.15),  # peak starts
            (12, 1.15),  # peak
            (19, 1.15),  # last peak hour
            (20, 1.0),  # transition starts again
            (21, 1.0),  # transition
            (22, 0.85),  # night again
        ],
    )
    def test_hour_scale_boundaries(self, hour: int, expected_scale: float) -> None:
        """Verify hour-of-day scaling at every boundary transition."""
        hw, _ = _compute_ci_half_width(self.RMSE, "Centro", hour, self.Q90)
        from src.api.prediction import REGION_UNCERTAINTY_SCALE

        region_scale = REGION_UNCERTAINTY_SCALE["Centro"]  # 1.0
        expected = self.Q90 * region_scale * expected_scale
        assert abs(hw - expected) < 1e-9, f"hour={hour}: expected hw={expected:.4f}, got {hw:.4f}"


class TestParametrizedQ90:
    """Verify conformal CI behaviour across a range of q90 values."""

    RMSE = 86.55
    REGION = "Centro"  # scale=1.0 → cleanest numbers
    HOUR_PEAK = 12

    @pytest.mark.parametrize("q90", [10.0, 20.0, 28.5, 35.0, 50.0, 100.0])
    def test_conformal_hw_scales_linearly_with_q90(self, q90: float) -> None:
        """Half-width must be proportional to q90 (linear relationship)."""
        hw, method = _compute_ci_half_width(self.RMSE, self.REGION, self.HOUR_PEAK, q90)
        assert method == "conformal"
        # Centro region_scale=1.0, peak hour_scale=1.15
        expected = q90 * 1.0 * 1.15
        assert abs(hw - expected) < 1e-9, f"q90={q90}: expected {expected}, got {hw}"

    @pytest.mark.parametrize("q90", [10.0, 20.0, 28.5, 35.0, 50.0, 100.0])
    def test_conformal_always_differs_from_gaussian_for_various_q90(self, q90: float) -> None:
        """For any realistic q90 the conformal and Gaussian methods must not coincide."""
        hw_conf, method_conf = _compute_ci_half_width(self.RMSE, self.REGION, self.HOUR_PEAK, q90)
        hw_gauss, method_gauss = _compute_ci_half_width(self.RMSE, self.REGION, self.HOUR_PEAK, None)
        assert method_conf == "conformal"
        assert method_gauss == "gaussian_z_rmse"
        # Gaussian baseline: Z_SCORE_90 * RMSE * 1.0 * 1.15 ≈ 163.79 (for RMSE=86.55)
        # Only coincides if q90 happens to equal Z*RMSE — which none of our test values do
        assert (
            abs(hw_conf - hw_gauss) > 0.01
        ), f"q90={q90}: conformal ({hw_conf:.4f}) must differ from gaussian ({hw_gauss:.4f})"

    @pytest.mark.parametrize(
        "q90,expected_ordering",
        [
            (10.0, "conformal_lower"),  # small q90 → tighter CI than Gaussian
            (200.0, "conformal_higher"),  # large q90 → wider CI than Gaussian
        ],
    )
    def test_conformal_ordering_relative_to_gaussian(self, q90: float, expected_ordering: str) -> None:
        """Conformal CI is narrower than Gaussian for small q90, wider for large."""
        hw_conf, _ = _compute_ci_half_width(self.RMSE, self.REGION, self.HOUR_PEAK, q90)
        hw_gauss, _ = _compute_ci_half_width(self.RMSE, self.REGION, self.HOUR_PEAK, None)
        if expected_ordering == "conformal_lower":
            assert hw_conf < hw_gauss
        else:
            assert hw_conf > hw_gauss


class TestHourScaleFactor:
    """Unit tests for the extracted _hour_scale_factor helper."""

    @pytest.mark.parametrize(
        "hour,expected",
        [
            (0, 0.85),
            (1, 0.85),
            (5, 0.85),  # night
            (6, 1.0),
            (7, 1.0),  # transition morning
            (8, 1.15),
            (12, 1.15),
            (19, 1.15),  # peak
            (20, 1.0),
            (21, 1.0),  # transition evening
            (22, 0.85),
            (23, 0.85),  # night again
        ],
    )
    def test_all_hour_bands(self, hour: int, expected: float) -> None:
        assert _hour_scale_factor(hour) == expected, f"hour={hour}: expected {expected}, got {_hour_scale_factor(hour)}"

    def test_peak_greater_than_transition(self) -> None:
        assert _hour_scale_factor(12) > _hour_scale_factor(7)

    def test_transition_greater_than_night(self) -> None:
        assert _hour_scale_factor(7) > _hour_scale_factor(2)


class TestScaledRMSE:
    """Unit tests for _scaled_rmse (region + hour heteroscedastic scaling)."""

    def test_all_five_regions_have_distinct_scales(self) -> None:
        """All five Portuguese regions should have different scaling factors."""
        regions = ["Norte", "Lisboa", "Centro", "Alentejo", "Algarve"]
        scaled = [_scaled_rmse(100.0, r, 12) for r in regions]
        assert len(set(scaled)) == len(regions), "Expected distinct scales per region"

    def test_norte_larger_than_algarve(self) -> None:
        """Norte (industrial north) should have higher uncertainty than Algarve (seasonal)."""
        norte = _scaled_rmse(100.0, "Norte", 12)
        algarve = _scaled_rmse(100.0, "Algarve", 12)
        assert norte > algarve

    def test_custom_scale_dict(self) -> None:
        """Custom scale_dict is respected over default."""
        custom = {"Norte": 3.0}
        result = _scaled_rmse(100.0, "Norte", 12, scale_dict=custom)
        assert abs(result - 100.0 * 3.0 * 1.15) < 1e-9
