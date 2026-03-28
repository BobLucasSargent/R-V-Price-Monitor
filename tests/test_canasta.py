"""Tests for config/canasta.py — COICOP basket integrity."""
import pytest
from config.canasta import (
    DIVISIONES, EXCLUIDAS, get_division, get_all_weights,
    get_divisiones_activas, total_weight, active_weight, covered_weight,
)


def test_12_divisions():
    assert len(DIVISIONES) == 12


def test_original_weights_sum_100():
    total = total_weight()
    assert 99.5 < total < 100.5, f"Weights sum to {total}"


def test_adjusted_weights_sum_100():
    adj = active_weight()
    assert 99.9 < adj < 100.1, f"Adjusted weights sum to {adj}"


def test_excluded_divisions():
    assert EXCLUIDAS == {"03", "10"}


def test_active_divisions_count():
    activas = get_divisiones_activas()
    assert len(activas) == 10  # 12 - 2 excluded


def test_excluded_not_in_weights():
    w = get_all_weights()
    assert "03" not in w
    assert "10" not in w


def test_weights_proportional():
    """Adjusted weights should maintain relative proportions."""
    w = get_all_weights()
    # Alimentos (01) should still be the heaviest
    assert w["01"] > w["08"]  # Alimentos > Comunicación
    assert w["07"] > w["02"]  # Transporte > Bebidas


def test_all_divisions_have_code():
    for div in DIVISIONES:
        assert len(div.codigo) == 2
        assert div.codigo.isdigit()


def test_codes_sequential():
    codes = [int(d.codigo) for d in DIVISIONES]
    assert codes == list(range(1, 13))


def test_all_have_variedades():
    for div in DIVISIONES:
        assert len(div.variedades) > 0, f"Division {div.codigo} has no variedades"


def test_get_division():
    d = get_division("01")
    assert d is not None
    assert d.nombre_corto == "Alimentos"
    assert d.peso_gba == 23.44


def test_get_division_none():
    assert get_division("99") is None


def test_covered_weight():
    cw = covered_weight()
    assert cw > 50  # Should cover >50% of GBA weight


def test_variedades_have_keywords():
    for div in DIVISIONES:
        for var in div.variedades:
            if div.collector_ids:
                assert len(var.keywords) > 0, \
                    f"Variedad {var.codigo} in div {div.codigo} has no keywords"
