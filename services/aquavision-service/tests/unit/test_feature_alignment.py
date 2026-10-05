"""Tests for the serving feature-alignment layer (old models + evolving feature sets)."""
import numpy as np

from ml.models.flood_predictor import align_features


def test_identical_names_returns_input_unchanged():
    X = np.array([[1.0, 2.0, 3.0]])
    names = ["a", "b", "c"]
    out = align_features(X, names, names)
    assert out is X


def test_reorders_columns_to_model_order():
    X = np.array([[1.0, 2.0, 3.0]])
    out = align_features(X, ["a", "b", "c"], ["c", "a", "b"])
    np.testing.assert_array_equal(out, [[3.0, 1.0, 2.0]])


def test_missing_model_columns_filled_with_zero():
    X = np.array([[1.0, 2.0]])
    out = align_features(X, ["a", "b"], ["a", "b", "gee_ndvi"])
    np.testing.assert_array_equal(out, [[1.0, 2.0, 0.0]])


def test_extra_incoming_columns_dropped():
    X = np.array([[1.0, 2.0, 3.0, 4.0]])
    out = align_features(X, ["a", "b", "gee_rain_mm", "gee_ndvi"], ["a", "b"])
    np.testing.assert_array_equal(out, [[1.0, 2.0]])


def test_preserves_multiple_rows_and_values():
    X = np.array([[1.0, 9.0], [2.0, 8.0]])
    out = align_features(X, ["x", "y"], ["y", "x"])
    np.testing.assert_array_equal(out, [[9.0, 1.0], [8.0, 2.0]])


def test_unknown_incoming_column_ignored():
    X = np.array([[1.0, 2.0]])
    out = align_features(X, ["a", "unknown"], ["a"])
    np.testing.assert_array_equal(out, [[1.0]])
