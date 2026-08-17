"""Testes unitários para o cache de census do loop de saúde.

Cobre a melhoria imp-20260816-tick-de-sa-de-reexecuta-checagens-completas-a-ca:
checagens estáveis (presença de binários/credenciais) são cacheadas com TTL curto,
e itens que falharam são sempre reexecutados no tick seguinte.
"""
from __future__ import annotations

import time
from unittest.mock import patch

from agentic.loop import _CensusCache, _cached_check, _census_cache


def _reset_global_cache() -> None:
    """Limpa o cache global entre testes para evitar contaminação."""
    _census_cache._store.clear()


class TestCensusCache:
    def setup_method(self) -> None:
        self.cache = _CensusCache(ttl_seconds=2)

    def test_put_true_and_get_within_ttl(self) -> None:
        self.cache.put("k", True)
        assert self.cache.get("k") is True

    def test_put_false_never_cached(self) -> None:
        self.cache.put("k", False)
        assert self.cache.get("k") is None

    def test_get_returns_none_for_missing_key(self) -> None:
        assert self.cache.get("missing") is None

    def test_expired_entry_returns_none(self) -> None:
        self.cache.put("k", True)
        # Avança o relógio monotónico além do TTL
        with patch("agentic.loop._monotonic", return_value=time.monotonic() + 3):
            assert self.cache.get("k") is None

    def test_invalidate_removes_entry(self) -> None:
        self.cache.put("k", True)
        self.cache.invalidate("k")
        assert self.cache.get("k") is None


class TestCachedCheck:
    def setup_method(self) -> None:
        _reset_global_cache()

    def teardown_method(self) -> None:
        _reset_global_cache()

    def test_calls_fn_on_first_invocation(self) -> None:
        calls = {"n": 0}

        def probe() -> bool:
            calls["n"] += 1
            return True

        result = _cached_check("probe_true", probe)
        assert result is True
        assert calls["n"] == 1

    def test_skips_fn_when_cached_true(self) -> None:
        calls = {"n": 0}

        def probe() -> bool:
            calls["n"] += 1
            return True

        _cached_check("probe_skip", probe)
        _cached_check("probe_skip", probe)
        assert calls["n"] == 1

    def test_reexecutes_fn_when_previous_result_was_false(self) -> None:
        results = iter([False, True])
        calls = {"n": 0}

        def probe() -> bool:
            calls["n"] += 1
            return next(results)

        assert _cached_check("probe_retry", probe) is False
        assert _cached_check("probe_retry", probe) is True
        assert calls["n"] == 2

    def test_different_keys_are_independent(self) -> None:
        calls_a = {"n": 0}
        calls_b = {"n": 0}

        def probe_a() -> bool:
            calls_a["n"] += 1
            return True

        def probe_b() -> bool:
            calls_b["n"] += 1
            return True

        _cached_check("indep_a", probe_a)
        _cached_check("indep_b", probe_b)
        _cached_check("indep_a", probe_a)
        _cached_check("indep_b", probe_b)

        assert calls_a["n"] == 1
        assert calls_b["n"] == 1