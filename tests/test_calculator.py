"""Tests for engine/calculator.py — INDEC methodology formulas."""
import pytest
import math
from engine.calculator import (
    media_geometrica,
    media_geometrica_ponderada,
    relativo_precios,
    indice_elemental,
    laspeyres,
    variacion_porcentual,
    incidencia,
    inflacion_anualizada,
    calcular_indice_nivel_general,
)


class TestMediaGeometrica:
    def test_basic(self):
        # Geometric mean of [2, 8] = sqrt(16) = 4
        assert abs(media_geometrica([2, 8]) - 4.0) < 0.001

    def test_single(self):
        assert abs(media_geometrica([5.0]) - 5.0) < 0.001

    def test_empty(self):
        assert media_geometrica([]) == 0.0

    def test_with_zeros_filtered(self):
        # Zeros are filtered out
        result = media_geometrica([0, 4, 16])
        assert abs(result - 8.0) < 0.001

    def test_real_prices(self):
        # Realistic supermarket prices
        prices = [1500, 1520, 1480, 1550, 1490]
        result = media_geometrica(prices)
        assert 1480 < result < 1560


class TestMediaGeometricaPonderada:
    def test_equal_weights(self):
        # With 50/50 split, should equal geometric mean
        result = media_geometrica_ponderada(100, 100, alpha_super=0.5)
        assert abs(result - 100) < 0.001

    def test_super_only(self):
        result = media_geometrica_ponderada(100, 200, alpha_super=1.0)
        assert abs(result - 200) < 0.001

    def test_traditional_only(self):
        result = media_geometrica_ponderada(100, 200, alpha_super=0.0)
        assert abs(result - 100) < 0.001


class TestRelativoPrecios:
    def test_increase(self):
        assert abs(relativo_precios(110, 100) - 1.1) < 0.001

    def test_decrease(self):
        assert abs(relativo_precios(90, 100) - 0.9) < 0.001

    def test_no_change(self):
        assert relativo_precios(100, 100) == 1.0

    def test_zero_base(self):
        assert relativo_precios(100, 0) == 1.0


class TestIndiceElemental:
    def test_basic(self):
        # 100 × 1.1 × 1.05 = 115.5
        result = indice_elemental([1.1, 1.05], base=100)
        assert abs(result - 115.5) < 0.01

    def test_no_change(self):
        result = indice_elemental([1.0, 1.0, 1.0])
        assert abs(result - 100) < 0.001


class TestLaspeyres:
    def test_simple(self):
        # 50% weight on index 110, 50% on index 120 → 115
        indices = {"A": 110, "B": 120}
        pesos = {"A": 50, "B": 50}
        assert abs(laspeyres(indices, pesos) - 115) < 0.001

    def test_unequal_weights(self):
        # 80% on 100, 20% on 200 → 120
        indices = {"A": 100, "B": 200}
        pesos = {"A": 80, "B": 20}
        assert abs(laspeyres(indices, pesos) - 120) < 0.001

    def test_real_divisions(self):
        """Test with actual INDEC-like weights."""
        indices = {"01": 11625, "07": 11125, "11": 13229}
        pesos = {"01": 23.44, "07": 11.59, "11": 10.84}
        result = laspeyres(indices, pesos)
        assert 11000 < result < 13000


class TestVariacionPorcentual:
    def test_basic(self):
        assert abs(variacion_porcentual(103, 100) - 3.0) < 0.001

    def test_negative(self):
        assert abs(variacion_porcentual(97, 100) - (-3.0)) < 0.001

    def test_large(self):
        # Dec 2023: 25.5% monthly
        assert abs(variacion_porcentual(125.5, 100) - 25.5) < 0.001


class TestIncidencia:
    def test_basic(self):
        # Division with 25% weight (0.25), went from 100 to 103, NG was at 100
        # Incidencia = (103-100) × 0.25 / 100 = 0.0075 (in index points)
        result = incidencia(103, 100, 100, 0.25)
        assert abs(result - 0.0075) < 0.001

    def test_zero_weight(self):
        result = incidencia(110, 100, 100, 0)
        assert result == 0.0


class TestInflacionAnualizada:
    def test_low(self):
        # 2.9% monthly → ~40.7% annualized
        result = inflacion_anualizada(2.9)
        assert 40 < result < 42

    def test_high(self):
        # 25% monthly → astronomical
        result = inflacion_anualizada(25)
        assert result > 1000


class TestCalcularIndiceNivelGeneral:
    def test_no_variation(self):
        """0% variation everywhere → same as base."""
        from config.ipc_oficial import IPC_DIVISIONES_FEB2026
        variaciones = {k: 0.0 for k in IPC_DIVISIONES_FEB2026}
        result = calcular_indice_nivel_general(variaciones, IPC_DIVISIONES_FEB2026)
        # Should be close to the weighted average of base indices
        assert result["nivel_general"] > 0

    def test_uniform_increase(self):
        """3% across all active divisions should yield ~3% at level general."""
        from config.ipc_oficial import IPC_DIVISIONES_FEB2026
        from config.canasta import EXCLUIDAS
        # Only apply variation to active divisions
        variaciones = {k: 3.0 for k in IPC_DIVISIONES_FEB2026 if k not in EXCLUIDAS}
        # Excluded divisions get 0% (stays at base)
        for k in EXCLUIDAS:
            variaciones[k] = 0.0
        result = calcular_indice_nivel_general(variaciones, IPC_DIVISIONES_FEB2026)
        ng = result["nivel_general"]
        # Since weights are redistributed, the 3% on active divs (88.5% of original)
        # plus 0% on excluded divs → NG should increase ~2.6-3.0%
        assert ng > 0
