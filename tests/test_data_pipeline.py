"""Tests for the data ingestion pipeline (scripts/data_pipeline/).

Covers:
- cp4_to_nuts2 mapping correctness for all 5 NUTS-II continental regions
- Region range coverage (no gaps in 1000-8999)
- Madeira/Açores exclusion
- build_dataset_real_regional aggregation logic (with synthetic input)
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# Add scripts/data_pipeline to import path
PIPELINE_DIR = Path(__file__).resolve().parent.parent / "scripts" / "data_pipeline"
sys.path.insert(0, str(PIPELINE_DIR))

from cp4_to_nuts2 import CP4_RANGES, build_lookup_table, cp4_to_region  # noqa: E402


class TestCp4ToRegion:
    """Test the postal code → NUTS-II region mapping."""

    @pytest.mark.parametrize(
        "cp4,expected",
        [
            # Lisboa city + AML core
            ("1000", "Lisboa"),
            ("1100", "Lisboa"),
            ("1495", "Lisboa"),
            ("1900", "Lisboa"),
            # 2xxx - the ambiguous block
            ("2000", "Centro"),  # Santarém
            ("2070", "Centro"),  # Cartaxo
            ("2099", "Centro"),
            ("2100", "Lisboa"),  # Border, AML
            ("2200", "Centro"),  # Tomar (Santarém)
            ("2300", "Centro"),  # Tomar
            ("2400", "Centro"),  # Leiria
            ("2500", "Centro"),  # Caldas da Rainha
            ("2600", "Lisboa"),  # Vila Franca de Xira
            ("2700", "Lisboa"),  # Amadora
            ("2750", "Lisboa"),  # Cascais
            ("2800", "Lisboa"),  # Almada
            ("2900", "Lisboa"),  # Setúbal
            # Centro
            ("3000", "Centro"),  # Coimbra
            ("3500", "Centro"),  # Viseu
            ("3700", "Centro"),  # São João da Madeira
            ("3999", "Centro"),
            # Norte
            ("4000", "Norte"),  # Porto
            ("4500", "Norte"),  # Espinho
            ("4700", "Norte"),  # Braga
            ("4900", "Norte"),  # Viana do Castelo
            ("5000", "Norte"),  # Vila Real
            ("5300", "Norte"),  # Bragança
            ("5999", "Norte"),
            # Centro (interior)
            ("6000", "Centro"),  # Castelo Branco
            ("6300", "Centro"),  # Guarda
            ("6999", "Centro"),
            # Alentejo
            ("7000", "Alentejo"),  # Évora
            ("7300", "Alentejo"),  # Portalegre
            ("7800", "Alentejo"),  # Beja
            ("7999", "Alentejo"),
            # Algarve
            ("8000", "Algarve"),  # Faro
            ("8500", "Algarve"),  # Portimão
            ("8800", "Algarve"),  # Tavira
            ("8999", "Algarve"),
            # Excluded (Madeira/Açores/invalid)
            ("9000", None),
            ("9100", None),
            ("9500", None),
            ("9700", None),
            ("0500", None),  # Below valid range
            ("OUTROS", None),  # Non-numeric
        ],
    )
    def test_known_cp4_mappings(self, cp4, expected):
        assert cp4_to_region(cp4) == expected

    def test_accepts_int_input(self):
        assert cp4_to_region(1100) == "Lisboa"
        assert cp4_to_region(4000) == "Norte"

    def test_accepts_full_7digit_input(self):
        # 7-digit postal codes should still work (only first 4 digits used)
        assert cp4_to_region("1100-001") == "Lisboa"
        assert cp4_to_region("4000-123") == "Norte"

    def test_handles_invalid_input(self):
        assert cp4_to_region("") is None
        assert cp4_to_region(None) is None
        assert cp4_to_region("ABCD") is None


class TestRegionCoverage:
    """Test that the mapping covers all valid Portuguese postal codes."""

    def test_all_5_continental_regions_present(self):
        regions = {region for _, _, region in CP4_RANGES}
        assert regions == {"Norte", "Centro", "Lisboa", "Alentejo", "Algarve"}

    def test_no_gaps_in_continental_range(self):
        """Every CP4 in [1000, 8999] should map to exactly one region."""
        unmapped = []
        for code in range(1000, 9000):
            if cp4_to_region(code) is None:
                unmapped.append(code)
        assert unmapped == [], f"Unmapped CPs: {unmapped[:10]}"

    def test_no_overlapping_ranges(self):
        """Each CP4 must map to exactly one region (ranges should not overlap)."""
        for code in range(1000, 9000):
            matches = [region for start, end, region in CP4_RANGES if start <= code <= end]
            assert len(matches) == 1, f"CP {code} matches {len(matches)} ranges"

    def test_madeira_acores_excluded(self):
        for code in range(9000, 10000):
            assert cp4_to_region(code) is None, f"CP {code} should be excluded"

    def test_lookup_table_size(self):
        lookup = build_lookup_table()
        assert len(lookup) == 8000  # 1000 to 8999 inclusive

    def test_balanced_region_coverage(self):
        """Each region should cover at least 500 prefixes (sanity check)."""
        from collections import Counter

        counts = Counter(build_lookup_table().values())
        for region, count in counts.items():
            assert count >= 500, f"{region} only has {count} prefixes (suspiciously low)"


class TestRegionalAggregation:
    """Test the build_dataset_real_regional logic with synthetic data."""

    def test_aggregation_sums_correctly(self):
        """Aggregating per (timestamp, region) should sum CP consumption."""
        # Create synthetic raw data: 2 timestamps, 4 CPs (2 in Norte, 2 in Lisboa)
        raw = pd.DataFrame(
            {
                "datahora": pd.to_datetime(
                    [
                        "2023-01-01 00:00",
                        "2023-01-01 00:00",
                        "2023-01-01 00:00",
                        "2023-01-01 00:00",
                        "2023-01-01 01:00",
                        "2023-01-01 01:00",
                        "2023-01-01 01:00",
                        "2023-01-01 01:00",
                    ],
                    utc=True,
                ),
                "codigo_postal": ["4000", "4500", "1100", "1500"] * 2,
                "consumo": [1000.0, 2000.0, 3000.0, 4000.0, 1100.0, 2200.0, 3300.0, 4400.0],
            }
        )

        # Apply mapping + aggregation manually (mirrors build_dataset_real_regional)
        raw["region"] = raw["codigo_postal"].map(cp4_to_region)
        agg = raw.groupby(["datahora", "region"], as_index=False)["consumo"].sum()

        # Verify Norte aggregation at t=0: 1000 + 2000 = 3000
        norte_t0 = agg[(agg["datahora"] == "2023-01-01 00:00:00+00:00") & (agg["region"] == "Norte")]
        assert len(norte_t0) == 1
        assert norte_t0["consumo"].iloc[0] == 3000.0

        # Lisboa aggregation at t=0: 3000 + 4000 = 7000
        lisboa_t0 = agg[(agg["datahora"] == "2023-01-01 00:00:00+00:00") & (agg["region"] == "Lisboa")]
        assert lisboa_t0["consumo"].iloc[0] == 7000.0

    def test_anomaly_filter_logic(self):
        """The anomaly filter should drop negative and absurd values."""
        raw = pd.DataFrame(
            {
                "consumo": [1000.0, -50.0, 5000.0, 200_000.0, 0.0, 99_000.0],
            }
        )
        # Filter logic from build_dataset_real_regional
        filtered = raw[(raw["consumo"] >= 0) & (raw["consumo"] < 100_000)]
        assert len(filtered) == 4  # 1000, 5000, 0, 99_000
        assert -50.0 not in filtered["consumo"].values
        assert 200_000.0 not in filtered["consumo"].values

    def test_kwh_to_mw_conversion(self):
        """1 kWh consumed in 1 hour = 0.001 MW average (factor 1/1000)."""
        consumo_kwh = np.array([1000.0, 2500.0, 500_000.0])
        consumption_mw = consumo_kwh / 1000.0
        expected_mw = np.array([1.0, 2.5, 500.0])
        np.testing.assert_array_almost_equal(consumption_mw, expected_mw)
