"""Tests for engine/imputation.py — Missing price handling."""
import pytest
from engine.imputation import imputar_faltantes


class TestImputarFaltantes:
    def test_all_observed(self):
        """All prices present — no imputation needed."""
        results = imputar_faltantes(
            precios_actuales=[100, 200, 300],
            precios_anteriores=[95, 190, 285],
        )
        assert len(results) == 3
        assert all(r.metodo == "observado" for r in results)

    def test_one_missing_above_50pct(self):
        """2/3 observed (>50%) — impute by variety variation."""
        results = imputar_faltantes(
            precios_actuales=[105, None, 315],
            precios_anteriores=[100, 200, 300],
        )
        assert len(results) == 3
        assert results[0].metodo == "observado"
        assert results[1].metodo == "variacion_variedad"
        assert results[2].metodo == "observado"
        # Imputed price should be close to 200 × avg variation
        assert results[1].precio_imputado > 200

    def test_below_50pct_above_20pct(self):
        """1/3 observed (33%) — impute by superior grouping."""
        results = imputar_faltantes(
            precios_actuales=[None, None, 315],
            precios_anteriores=[100, 200, 300],
            variacion_superior=5.0,
        )
        assert len(results) == 3
        assert results[0].metodo == "variacion_superior"
        assert abs(results[0].precio_imputado - 105) < 0.01

    def test_below_20pct(self):
        """0/5 observed (<20%) — all discarded."""
        results = imputar_faltantes(
            precios_actuales=[None, None, None, None, None],
            precios_anteriores=[100, 200, 300, 400, 500],
            variacion_superior=3.0,
        )
        assert len(results) == 5
        assert all("descartado" in r.metodo or "repetido" in r.metodo for r in results)

    def test_empty(self):
        results = imputar_faltantes([], [])
        assert results == []
