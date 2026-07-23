"""Unit tests for the pure transformation logic -- the parts that don't need a
live database. Run with: pytest tests/
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.append(str(Path(__file__).resolve().parent.parent))
from etl import transform
from data_generation.generate_synthetic_data import weighted_choice


def test_transform_sales_flips_quantity_sign_for_returns():
    raw = pd.DataFrame({
        "date_id": [20210101, 20210101],
        "store_id": [1, 1],
        "product_id": [1, 1],
        "customer_id": [1, 1],
        "quantity": [2, 3],
        "unit_price": [10.0, 10.0],
        "unit_cost": [4.0, 4.0],
        "discount_pct": [0.0, 0.0],
        "is_return": [False, True],
    })
    result = transform.transform_sales(raw)
    assert result.loc[0, "quantity"] == 2
    assert result.loc[1, "quantity"] == -3


def test_transform_sales_computes_net_revenue_and_margin():
    raw = pd.DataFrame({
        "date_id": [20210101], "store_id": [1], "product_id": [1], "customer_id": [1],
        "quantity": [2], "unit_price": [100.0], "unit_cost": [40.0],
        "discount_pct": [0.10], "is_return": [False],
    })
    result = transform.transform_sales(raw)
    assert result.loc[0, "net_revenue"] == pytest.approx(180.0)   # 2 * 100 * 0.9
    assert result.loc[0, "gross_margin"] == pytest.approx(100.0)  # 180 - 2*40


def test_transform_sales_drops_null_keys():
    raw = pd.DataFrame({
        "date_id": [20210101, None], "store_id": [1, 1], "product_id": [1, 1], "customer_id": [1, 1],
        "quantity": [1, 1], "unit_price": [10.0, 10.0], "unit_cost": [4.0, 4.0],
        "discount_pct": [0.0, 0.0], "is_return": [False, False],
    })
    result = transform.transform_sales(raw)
    assert len(result) == 1


def test_weighted_choice_respects_zero_weight():
    rng = np.random.default_rng(0)
    weights = np.array([1.0, 0.0, 0.0])
    draws = weighted_choice(weights, size=1000, rng=rng)
    assert set(draws.tolist()) == {0}


def test_weighted_choice_returns_valid_indices():
    rng = np.random.default_rng(0)
    weights = np.array([0.1, 0.5, 0.4])
    draws = weighted_choice(weights, size=500, rng=rng)
    assert draws.min() >= 0
    assert draws.max() < len(weights)
