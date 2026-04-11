"""End-to-end tests for the regional data pipeline.

Covers scripts/data_pipeline/build_dataset_real_regional.py with synthetic
input data — verifies the full aggregate→filter→join workflow produces an
output parquet with the expected structure.

Complements tests/test_data_pipeline.py, which only exercises individual
helpers (cp4_to_region, aggregation logic in isolation).

The real dataset smoke test at the bottom will run against
data/processed/processed_data.parquet when it exists, otherwise it is
skipped — keeping the suite portable.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pandas as pd
import pytest

# Add scripts/data_pipeline to import path (same convention as test_data_pipeline.py)
PIPELINE_DIR = Path(__file__).resolve().parent.parent / "scripts" / "data_pipeline"
sys.path.insert(0, str(PIPELINE_DIR))

import build_dataset_real_regional as pipeline  # noqa: E402
from cp4_to_nuts2 import cp4_to_region  # noqa: E402


# ---------------------------------------------------------------------------
# Synthetic data helpers
# ---------------------------------------------------------------------------

WEATHER_COLUMNS = [
    "temperature",
    "humidity",
    "dew_point",
    "temperature_feels_like",
    "pressure",
    "cloud_cover",
    "wind_speed",
    "wind_direction",
    "precipitation",
    "solar_radiation",
]


def _make_weather_row(ts: pd.Timestamp, region: str, temp: float = 15.0) -> dict:
    return {
        "temperature": temp,
        "humidity": 60,
        "dew_point": 8.5,
        "temperature_feels_like": temp - 1.0,
        "pressure": 1015.0,
        "cloud_cover": 30,
        "wind_speed": 5.0,
        "wind_direction": 180,
        "precipitation": 0.0,
        "solar_radiation": 250.0,
        "timestamp": ts,
        "region": region,
    }


def _write_synthetic_inputs(
    raw_dir: Path,
    consumption_rows: list[dict],
    weather_rows: list[dict],
) -> None:
    """Write the two raw parquet files the pipeline expects."""
    raw_dir.mkdir(parents=True, exist_ok=True)
    cons_df = pd.DataFrame(consumption_rows)
    cons_df["datahora"] = pd.to_datetime(cons_df["datahora"], utc=True)
    cons_df.to_parquet(raw_dir / "regional_hourly_cp4_eredes.parquet", index=False)

    weather_df = pd.DataFrame(weather_rows)
    weather_df["timestamp"] = pd.to_datetime(weather_df["timestamp"], utc=True)
    weather_df.to_parquet(raw_dir / "weather_hourly_all_regions.parquet", index=False)


@pytest.fixture
def pipeline_env(tmp_path, monkeypatch):
    """Redirect the pipeline's RAW_DIR / OUTPUT_PATH into tmp_path.

    Returns (raw_dir, output_path). The pipeline module is reloaded inside
    the test if needed, but monkeypatch.setattr on module attributes is
    sufficient here because the functions dereference the module globals
    at call time.
    """
    raw_dir = tmp_path / "raw" / "real"
    processed_dir = tmp_path / "processed"
    output_path = processed_dir / "processed_data.parquet"

    monkeypatch.setattr(pipeline, "RAW_DIR", raw_dir)
    monkeypatch.setattr(pipeline, "PROCESSED_DIR", processed_dir)
    monkeypatch.setattr(pipeline, "OUTPUT_PATH", output_path)

    return raw_dir, output_path


# ---------------------------------------------------------------------------
# 1. End-to-end test
# ---------------------------------------------------------------------------


class TestEndToEnd:
    def test_main_produces_expected_output(self, pipeline_env):
        raw_dir, output_path = pipeline_env

        # 3 timestamps × 2 CPs per region × 2 regions = 12 consumption rows
        timestamps = [
            "2023-01-01 00:00",
            "2023-01-01 01:00",
            "2023-01-01 02:00",
        ]
        cps_by_region = {
            "Norte": ["4000", "4500"],
            "Lisboa": ["1100", "1500"],
        }

        consumption_rows = []
        for ts in timestamps:
            for _region, cps in cps_by_region.items():
                for cp in cps:
                    consumption_rows.append(
                        {"datahora": ts, "codigo_postal": cp, "consumo": 1500.0}
                    )

        weather_rows = []
        for ts in timestamps:
            for region in cps_by_region:
                weather_rows.append(_make_weather_row(pd.Timestamp(ts, tz="UTC"), region))

        _write_synthetic_inputs(raw_dir, consumption_rows, weather_rows)

        pipeline.main()

        assert output_path.exists(), "main() did not write the output parquet"

        df = pd.read_parquet(output_path)

        # Expected: 3 timestamps * 2 regions = 6 rows
        assert len(df) == 6

        # Required columns (union of consumption + weather + engineered)
        required_cols = {
            "timestamp",
            "region",
            "consumption_mw",
            "temperature",
            "humidity",
            "year",
        }
        assert required_cols.issubset(set(df.columns))

        # Join correctness: 2 CPs × 1500 kWh = 3000 kWh → 3.0 MW per region hour
        assert df["consumption_mw"].unique().tolist() == [3.0]

        # Both regions present
        assert set(df["region"].unique()) == {"Norte", "Lisboa"}

        # Sorted by timestamp then region
        assert df.equals(df.sort_values(["timestamp", "region"]).reset_index(drop=True))

    def test_all_five_regions_appear_in_output(self, pipeline_env):
        """CP4 → region integration: input covering all 5 regions must survive."""
        raw_dir, output_path = pipeline_env

        region_cps = {
            "Norte": "4000",
            "Centro": "3000",
            "Lisboa": "1100",
            "Alentejo": "7000",
            "Algarve": "8000",
        }
        ts = pd.Timestamp("2023-03-15 12:00", tz="UTC")

        consumption_rows = [
            {"datahora": ts, "codigo_postal": cp, "consumo": 2000.0}
            for cp in region_cps.values()
        ]
        weather_rows = [_make_weather_row(ts, region) for region in region_cps]

        _write_synthetic_inputs(raw_dir, consumption_rows, weather_rows)
        pipeline.main()

        df = pd.read_parquet(output_path)

        assert set(df["region"].unique()) == set(region_cps.keys())
        assert len(df) == 5
        # sanity: CP → region mapping actually applied
        for expected_region, cp in region_cps.items():
            assert cp4_to_region(cp) == expected_region


# ---------------------------------------------------------------------------
# 2. Anomaly filter regression
# ---------------------------------------------------------------------------


class TestAnomalyFilter:
    def test_drops_negative_and_absurd_values(self, pipeline_env):
        raw_dir, output_path = pipeline_env

        ts = pd.Timestamp("2023-02-01 00:00", tz="UTC")
        # 6 rows: 1 negative, 1 zero, 1 normal, 1 at threshold (dropped),
        # 1 just under threshold (kept), 1 absurd.
        consumption_rows = [
            {"datahora": ts, "codigo_postal": "4000", "consumo": -50.0},      # drop
            {"datahora": ts, "codigo_postal": "4100", "consumo": 0.0},        # keep
            {"datahora": ts, "codigo_postal": "4200", "consumo": 1500.0},     # keep
            {"datahora": ts, "codigo_postal": "4300", "consumo": 100_000.0},  # drop (>=100k)
            {"datahora": ts, "codigo_postal": "4400", "consumo": 99_000.0},   # keep
            {"datahora": ts, "codigo_postal": "4500", "consumo": 5_000_000.0},  # drop
        ]
        weather_rows = [_make_weather_row(ts, "Norte")]

        _write_synthetic_inputs(raw_dir, consumption_rows, weather_rows)
        pipeline.main()

        df = pd.read_parquet(output_path)

        # Surviving rows are all in Norte at this single timestamp:
        # 0 + 1500 + 99_000 = 100_500 kWh → 100.5 MW
        assert len(df) == 1
        assert df["consumption_mw"].iloc[0] == pytest.approx(100.5)

    def test_anomaly_filter_with_only_bad_rows_yields_empty(self, pipeline_env):
        raw_dir, output_path = pipeline_env
        ts = pd.Timestamp("2023-02-01 00:00", tz="UTC")
        consumption_rows = [
            {"datahora": ts, "codigo_postal": "4000", "consumo": -1.0},
            {"datahora": ts, "codigo_postal": "4100", "consumo": 500_000.0},
        ]
        weather_rows = [_make_weather_row(ts, "Norte")]

        _write_synthetic_inputs(raw_dir, consumption_rows, weather_rows)
        pipeline.main()

        df = pd.read_parquet(output_path)
        assert len(df) == 0


# ---------------------------------------------------------------------------
# 3. Region aggregation
# ---------------------------------------------------------------------------


class TestRegionAggregation:
    def test_multiple_cps_sum_per_region(self, pipeline_env):
        raw_dir, output_path = pipeline_env
        ts = pd.Timestamp("2023-04-10 09:00", tz="UTC")

        # 3 CPs in Norte (4000, 4500, 5000) and 2 in Lisboa (1100, 1500).
        consumption_rows = [
            {"datahora": ts, "codigo_postal": "4000", "consumo": 1000.0},
            {"datahora": ts, "codigo_postal": "4500", "consumo": 2000.0},
            {"datahora": ts, "codigo_postal": "5000", "consumo": 3000.0},  # Norte (5xxx)
            {"datahora": ts, "codigo_postal": "1100", "consumo": 4000.0},
            {"datahora": ts, "codigo_postal": "1500", "consumo": 500.0},
        ]
        weather_rows = [
            _make_weather_row(ts, "Norte"),
            _make_weather_row(ts, "Lisboa"),
        ]

        _write_synthetic_inputs(raw_dir, consumption_rows, weather_rows)
        pipeline.main()

        df = pd.read_parquet(output_path).set_index("region")

        # Norte: (1000 + 2000 + 3000) / 1000 = 6.0 MW
        # Lisboa: (4000 + 500)        / 1000 = 4.5 MW
        assert df.loc["Norte", "consumption_mw"] == pytest.approx(6.0)
        assert df.loc["Lisboa", "consumption_mw"] == pytest.approx(4.5)


# ---------------------------------------------------------------------------
# 4. Weather join
# ---------------------------------------------------------------------------


class TestWeatherJoin:
    def test_rows_without_weather_are_dropped(self, pipeline_env):
        """Inner join: consumption rows for a (ts, region) with no weather row
        must not appear in the output."""
        raw_dir, output_path = pipeline_env

        ts1 = pd.Timestamp("2023-05-01 00:00", tz="UTC")
        ts2 = pd.Timestamp("2023-05-01 01:00", tz="UTC")

        # Consumption: 2 timestamps × Norte
        consumption_rows = [
            {"datahora": ts1, "codigo_postal": "4000", "consumo": 1000.0},
            {"datahora": ts2, "codigo_postal": "4000", "consumo": 2000.0},
        ]
        # Weather: ONLY ts1 has data — ts2 must be dropped by inner join
        weather_rows = [_make_weather_row(ts1, "Norte")]

        _write_synthetic_inputs(raw_dir, consumption_rows, weather_rows)
        pipeline.main()

        df = pd.read_parquet(output_path)
        assert len(df) == 1
        assert df["timestamp"].iloc[0] == ts1

    def test_weather_for_missing_region_ignored(self, pipeline_env):
        """Weather rows for a region with no consumption must not appear."""
        raw_dir, output_path = pipeline_env
        ts = pd.Timestamp("2023-06-01 00:00", tz="UTC")

        consumption_rows = [
            {"datahora": ts, "codigo_postal": "4000", "consumo": 1000.0},
        ]
        weather_rows = [
            _make_weather_row(ts, "Norte"),
            _make_weather_row(ts, "Algarve"),  # dangling
        ]

        _write_synthetic_inputs(raw_dir, consumption_rows, weather_rows)
        pipeline.main()

        df = pd.read_parquet(output_path)
        assert len(df) == 1
        assert df["region"].iloc[0] == "Norte"


# ---------------------------------------------------------------------------
# 5. Real dataset smoke test
# ---------------------------------------------------------------------------


REAL_PROCESSED_PATH = (
    Path(__file__).resolve().parent.parent / "data" / "processed" / "processed_data.parquet"
)


@pytest.mark.skipif(
    not REAL_PROCESSED_PATH.exists(),
    reason="Real processed dataset not available in this environment",
)
class TestRealDatasetSmoke:
    @pytest.fixture(scope="class")
    def real_df(self) -> pd.DataFrame:
        return pd.read_parquet(REAL_PROCESSED_PATH)

    def test_schema(self, real_df):
        required = {"timestamp", "region", "consumption_mw", "temperature", "year"}
        assert required.issubset(set(real_df.columns))

    def test_row_count(self, real_df):
        assert len(real_df) > 30_000

    def test_all_five_regions_present(self, real_df):
        assert set(real_df["region"].unique()) == {
            "Norte",
            "Centro",
            "Lisboa",
            "Alentejo",
            "Algarve",
        }

    def test_no_nans_in_key_columns(self, real_df):
        assert real_df["consumption_mw"].isna().sum() == 0
        assert real_df["temperature"].isna().sum() == 0

    def test_period_within_expected_window(self, real_df):
        lower = pd.Timestamp("2022-11-01", tz="UTC")
        upper = pd.Timestamp("2023-09-30 23:59:59", tz="UTC")
        assert real_df["timestamp"].min() >= lower
        assert real_df["timestamp"].max() <= upper


# Silence unused-import warning for importlib if a future reload is added.
_ = importlib
