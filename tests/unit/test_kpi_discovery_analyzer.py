"""Unit tests for KPIDiscoveryAnalyzer — pure analysis logic, no DB required."""

from core.kpi_discovery.analyzer import KPIDiscoveryAnalyzer
from core.kpi_discovery.models import DiscoveredKPI, KPIDiscoveryResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_fingerprint(logins: int = 0, entity_id: str = "student_1") -> dict:
    return {
        "entity_type": "student",
        "entity_id": entity_id,
        "pattern_name": "disengagement",
        "metrics": {"logins": logins},
    }


# ---------------------------------------------------------------------------
# Empty input
# ---------------------------------------------------------------------------

def test_empty_fingerprint_list_returns_empty_kpis():
    result = KPIDiscoveryAnalyzer().analyze([])
    assert result.kpis == {}


def test_empty_fingerprint_list_analyzed_count_is_zero():
    result = KPIDiscoveryAnalyzer().analyze([])
    assert result.analyzed_count == 0


def test_empty_fingerprint_list_metadata_is_empty():
    result = KPIDiscoveryAnalyzer().analyze([])
    assert result.metadata == {}


def test_empty_fingerprint_list_returns_kpi_discovery_result():
    result = KPIDiscoveryAnalyzer().analyze([])
    assert isinstance(result, KPIDiscoveryResult)


# ---------------------------------------------------------------------------
# Returns KPI list when metrics exist
# ---------------------------------------------------------------------------

def test_single_fingerprint_produces_avg_logins_kpi():
    result = KPIDiscoveryAnalyzer().analyze([make_fingerprint(logins=10)])
    assert "avg_logins" in result.kpis


def test_multiple_fingerprints_produce_avg_logins_kpi():
    fingerprints = [make_fingerprint(logins=5), make_fingerprint(logins=15)]
    result = KPIDiscoveryAnalyzer().analyze(fingerprints)
    assert "avg_logins" in result.kpis


def test_analyzed_count_matches_input_length():
    fingerprints = [make_fingerprint(), make_fingerprint(), make_fingerprint()]
    result = KPIDiscoveryAnalyzer().analyze(fingerprints)
    assert result.analyzed_count == 3


def test_avg_logins_in_metadata():
    result = KPIDiscoveryAnalyzer().analyze([make_fingerprint(logins=10)])
    assert "avg_logins" in result.metadata


def test_avg_logins_metadata_value_is_correct():
    fingerprints = [make_fingerprint(logins=10), make_fingerprint(logins=20)]
    result = KPIDiscoveryAnalyzer().analyze(fingerprints)
    assert result.metadata["avg_logins"] == 15.0


def test_avg_logins_metadata_single_fingerprint():
    result = KPIDiscoveryAnalyzer().analyze([make_fingerprint(logins=8)])
    assert result.metadata["avg_logins"] == 8.0


# ---------------------------------------------------------------------------
# Expected KPI structure
# ---------------------------------------------------------------------------

def test_avg_logins_kpi_name():
    result = KPIDiscoveryAnalyzer().analyze([make_fingerprint(logins=5)])
    kpi = result.kpis["avg_logins"]
    assert kpi.kpi_name == "avg_logins"


def test_avg_logins_source_pattern():
    result = KPIDiscoveryAnalyzer().analyze([make_fingerprint(logins=5)])
    kpi = result.kpis["avg_logins"]
    assert kpi.source_pattern == "auto"


def test_avg_logins_entity_type():
    result = KPIDiscoveryAnalyzer().analyze([make_fingerprint(logins=5)])
    kpi = result.kpis["avg_logins"]
    assert kpi.entity_type == "student"


def test_avg_logins_formula():
    result = KPIDiscoveryAnalyzer().analyze([make_fingerprint(logins=5)])
    kpi = result.kpis["avg_logins"]
    assert kpi.formula == "avg(logins)"


def test_avg_logins_confidence():
    result = KPIDiscoveryAnalyzer().analyze([make_fingerprint(logins=5)])
    kpi = result.kpis["avg_logins"]
    assert kpi.confidence == 0.8


def test_avg_logins_sample_size_matches_input_count():
    fingerprints = [make_fingerprint(logins=1), make_fingerprint(logins=2)]
    result = KPIDiscoveryAnalyzer().analyze(fingerprints)
    assert result.kpis["avg_logins"].sample_size == 2


def test_kpi_is_discovered_kpi_instance():
    result = KPIDiscoveryAnalyzer().analyze([make_fingerprint(logins=5)])
    assert isinstance(result.kpis["avg_logins"], DiscoveredKPI)


# ---------------------------------------------------------------------------
# Missing metrics key in fingerprint rows
# ---------------------------------------------------------------------------

def test_fingerprint_without_metrics_key_defaults_logins_to_zero():
    """Row has no 'metrics' key at all — logins must default to 0."""
    fingerprint = {"entity_type": "student", "entity_id": "s1", "pattern_name": "x"}
    result = KPIDiscoveryAnalyzer().analyze([fingerprint])
    assert result.metadata["avg_logins"] == 0.0


def test_fingerprint_with_metrics_but_no_logins_defaults_to_zero():
    """Row has 'metrics' dict but no 'logins' key — must default to 0."""
    fingerprint = {"entity_type": "student", "entity_id": "s1", "metrics": {"sessions": 5}}
    result = KPIDiscoveryAnalyzer().analyze([fingerprint])
    assert result.metadata["avg_logins"] == 0.0


def test_mixed_rows_some_with_logins_some_without():
    """Average is computed across all rows; missing logins count as 0."""
    fingerprints = [
        make_fingerprint(logins=10),
        {"entity_type": "student", "entity_id": "s2", "pattern_name": "x"},  # no metrics
    ]
    result = KPIDiscoveryAnalyzer().analyze(fingerprints)
    assert result.metadata["avg_logins"] == 5.0  # (10 + 0) / 2


# ---------------------------------------------------------------------------
# Malformed rows
# ---------------------------------------------------------------------------

def test_empty_dict_row_does_not_raise():
    """An empty dict fingerprint must not raise — logins defaults to 0."""
    result = KPIDiscoveryAnalyzer().analyze([{}])
    assert result.analyzed_count == 1
    assert result.metadata["avg_logins"] == 0.0


def test_multiple_empty_dict_rows_produce_zero_avg():
    result = KPIDiscoveryAnalyzer().analyze([{}, {}, {}])
    assert result.metadata["avg_logins"] == 0.0
    assert result.analyzed_count == 3


def test_logins_value_zero_is_valid():
    """Explicitly set logins=0 must be treated as 0, not as missing."""
    result = KPIDiscoveryAnalyzer().analyze([make_fingerprint(logins=0)])
    assert result.metadata["avg_logins"] == 0.0
    assert "avg_logins" in result.kpis
