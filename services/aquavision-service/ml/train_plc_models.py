# ml/train_plc_models.py
# Train on REAL PLC control signals from the HAI ICS testbed.
#
# Why this is not just train_rtu_models with a different CSV:
#
# RTU telemetry is analog measurement - level, discharge - and the useful
# question is "what will it read next". PLC data is CONTROL LOGIC, and the
# useful questions are different in kind:
#
#   1. Does feedback follow command?  Every actuator has a demand tag and a
#      feedback tag (P1_PP01AD -> P1_PP01AR, P1_FCV01D -> P1_FCV01Z). When they
#      diverge, either the actuator has failed or someone is spoofing the HMI.
#      This is the canonical PLC fault signature and it has no RTU analogue.
#
#   2. Are the discrete states reachable?  DI/DO signals form a state machine.
#      A state vector never seen during normal operation is, by construction,
#      something the control logic should not have produced.
#
#   3. Can we detect a real attack?  HAI ships labels, so unlike the RTU work
#      this can be scored with precision/recall/F1 against ground truth rather
#      than an assumed contamination rate.
#
# Signal classes present in HAI (all four, unlike USGS which is AI-only):
#   AI  P1_LIT01, P3_FIT01      level / flow transmitters
#   DI  P1_PP01AR, P3_LH01      pump run feedback, level limit switches
#   DO  P1_PP01AD, P1_SOL01D    pump demand, solenoid demand
#   AO  x1001_05_SETPOINT_OUT   controller setpoints
#
# Data: https://github.com/icsdataset/hai (HAI 23.05, Git LFS)
#   hai-train1.csv  - attack-free normal operation
#   hai-test1.csv   + label-test1.csv - labelled attacks
#
# Usage:
#   python -m ml.train_plc_models --train data/raw/real/hai/hai-train1.csv \
#          --test data/raw/real/hai/hai-test1.csv \
#          --labels data/raw/real/hai/label-test1.csv

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger("aquavision.ml.plc")

ARTIFACT_DIR = Path(__file__).resolve().parent / "artifacts"

# HAI tag suffixes: D = demand/command, R = run feedback, Z = position feedback.
FEEDBACK_SUFFIXES = ("R", "Z")
BINARY_MAX_CARDINALITY = 2


# ─── Signal classification ─────────────────────────────────────────────────

def classify_signals(df: pd.DataFrame) -> Dict[str, List[str]]:
    """Split columns into discrete (DI/DO) and continuous (AI/AO) by cardinality.

    Done from the data rather than a hand-written tag list: HAI has 80+ tags and
    the naming convention alone does not say which are binary.
    """
    discrete, continuous = [], []
    for col in df.columns:
        if col == "timestamp":
            continue
        nunique = df[col].nunique(dropna=True)
        if nunique <= BINARY_MAX_CARDINALITY:
            discrete.append(col)
        else:
            continuous.append(col)
    logger.info("Signal classes: %d discrete (DI/DO), %d continuous (AI/AO)",
                len(discrete), len(continuous))
    return {"discrete": discrete, "continuous": continuous}


def find_command_feedback_pairs(columns: List[str]) -> List[Tuple[str, str]]:
    """Match each demand tag ending in 'D' to its feedback tag ending R or Z."""
    colset = set(columns)
    pairs = []
    for col in columns:
        if not col.endswith("D"):
            continue
        base = col[:-1]
        for suffix in FEEDBACK_SUFFIXES:
            candidate = base + suffix
            if candidate in colset:
                pairs.append((col, candidate))
                break
    logger.info("Command/feedback pairs found: %d", len(pairs))
    for cmd, fb in pairs:
        logger.info("    %-16s -> %s", cmd, fb)
    return pairs


# ─── Loading ───────────────────────────────────────────────────────────────

def load_hai(path: Path, labels_path: Path = None) -> pd.DataFrame:
    df = pd.read_csv(path)
    df.columns = [c.strip() for c in df.columns]
    df["timestamp"] = pd.to_datetime(df["timestamp"])

    if labels_path is not None:
        lab = pd.read_csv(labels_path)
        lab.columns = [c.strip() for c in lab.columns]
        lab["timestamp"] = pd.to_datetime(lab["timestamp"])
        label_col = "label" if "label" in lab.columns else lab.columns[-1]
        df = df.merge(lab[["timestamp", label_col]], on="timestamp", how="left")
        df = df.rename(columns={label_col: "attack"})
        df["attack"] = df["attack"].fillna(0).astype(int)
        n_attack = int(df["attack"].sum())
        logger.info("%s: %d rows, %d attack seconds (%.2f%%)",
                    path.name, len(df), n_attack, 100 * n_attack / len(df))
    else:
        logger.info("%s: %d rows (assumed attack-free)", path.name, len(df))

    return df


# ─── Model 1: command/feedback divergence ──────────────────────────────────

def build_divergence_features(df: pd.DataFrame, pairs: List[Tuple[str, str]],
                              spreads: Dict[str, float] = None) -> pd.DataFrame:
    """Residual between each actuator's command and its feedback.

    Normalised per pair so a valve moving 0-100 and a pump flag moving 0-1
    contribute comparably.

    `spreads` MUST be the values captured at fit time. Recomputing them from
    whatever frame is being scored puts fit and score on different scales, so
    the learned band no longer means the same thing.
    """
    out = pd.DataFrame(index=df.index)
    for cmd, fb in pairs:
        c = pd.to_numeric(df[cmd], errors="coerce")
        f = pd.to_numeric(df[fb], errors="coerce")
        if spreads is not None and f"div_{cmd}" in spreads:
            spread = spreads[f"div_{cmd}"]
        else:
            spread = max(float(c.std() or 0), float(f.std() or 0), 1e-6)
        out[f"div_{cmd}"] = (c - f) / spread
    return out.fillna(0.0)


def compute_spreads(df: pd.DataFrame, pairs: List[Tuple[str, str]]) -> Dict[str, float]:
    """Per-pair normalisation scale, captured once at fit time."""
    spreads = {}
    for cmd, fb in pairs:
        c = pd.to_numeric(df[cmd], errors="coerce")
        f = pd.to_numeric(df[fb], errors="coerce")
        spreads[f"div_{cmd}"] = max(float(c.std() or 0), float(f.std() or 0), 1e-6)
    return spreads


def train_divergence_model(train_df: pd.DataFrame, pairs: List[Tuple[str, str]]) -> dict:
    """Learn the normal command-feedback relationship on attack-free data."""
    if not pairs:
        logger.warning("No command/feedback pairs - skipping divergence model")
        return {}

    spreads = compute_spreads(train_df, pairs)
    feats = build_divergence_features(train_df, pairs, spreads)
    # Empirical quantiles, not mean/sigma. In normal operation feedback tracks
    # command almost exactly, so the residual std collapses toward zero and a
    # 6-sigma band ends up narrower than the sensor noise - which flagged 97% of
    # rows. Quantiles of the observed normal residual are bounded by construction.
    stats = {
        col: {
            "lo": float(feats[col].quantile(0.0005)),
            "hi": float(feats[col].quantile(0.9995)),
            "std": float(feats[col].std() or 1e-6),
        }
        for col in feats.columns
    }

    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    import joblib
    joblib.dump({"pairs": pairs, "stats": stats, "spreads": spreads},
                ARTIFACT_DIR / "plc_divergence.joblib")

    logger.info("Divergence model: %d actuator pairs profiled", len(pairs))
    return {"pairs": len(pairs), "tags": [c for c, _ in pairs]}


def score_divergence(df: pd.DataFrame, pairs, stats, spreads=None,
                     margin: float = 0.25, persist: int = 5) -> np.ndarray:
    """Flag when an actuator's command/feedback residual leaves its normal band.

    Two guards against the false-positive storm a raw threshold produces:
      - the band is widened by `margin` of its own width, so noise at the edge
        of normal operation does not trip it;
      - a deviation must persist for `persist` consecutive seconds. A single
        sample out of band is a scan artefact; a sustained one is an actuator
        that is not obeying its command.
    """
    feats = build_divergence_features(df, pairs, spreads)
    flags = np.zeros(len(df), dtype=bool)
    per_pair = {}
    for col in feats.columns:
        s = stats.get(col)
        if not s:
            continue
        lo, hi = s["lo"], s["hi"]
        pad = max((hi - lo) * margin, 1e-9)
        out = ((feats[col] < lo - pad) | (feats[col] > hi + pad))
        if persist > 1:
            out = out.rolling(persist, min_periods=persist).sum().fillna(0) >= persist
        arr = out.to_numpy().astype(bool)
        per_pair[col] = float(arr.mean())
        flags |= arr
    for col, rate in sorted(per_pair.items(), key=lambda x: -x[1]):
        logger.info("    %-20s flags %.1f%% of rows", col, 100 * rate)
    return flags


# ─── Model 2: discrete state reachability ──────────────────────────────────

def _state_vector(df: pd.DataFrame, discrete: List[str]) -> pd.Series:
    """Encode the discrete signals of each row as a single state string.

    Coerces numerically first: HAI stores some binary tags as floats (1.0) and
    some columns arrive as object dtype, so a direct integer cast raises. NaN
    becomes -1 so a dropout is its own state rather than silently merging with 0.
    """
    disc = df[discrete].apply(pd.to_numeric, errors="coerce").fillna(-1)
    return disc.round(0).astype("int64").astype(str).agg("|".join, axis=1)


def train_state_model(train_df: pd.DataFrame, discrete: List[str]) -> dict:
    """Record every discrete state vector and transition seen in normal operation."""
    if not discrete:
        logger.warning("No discrete signals - skipping state model")
        return {}

    states = _state_vector(train_df, discrete)
    seen_states = set(states.unique())
    transitions = set(zip(states.iloc[:-1], states.iloc[1:]))

    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    import joblib
    joblib.dump({"discrete": discrete, "states": seen_states, "transitions": transitions},
                ARTIFACT_DIR / "plc_state_machine.joblib")

    logger.info("State machine: %d distinct states, %d transitions over %d discrete tags",
                len(seen_states), len(transitions), len(discrete))
    return {"discrete_tags": len(discrete),
            "distinct_states": len(seen_states),
            "transitions": len(transitions)}


def score_states(df: pd.DataFrame, discrete, seen_states, transitions) -> np.ndarray:
    """Flag rows whose discrete state or transition was never seen when normal."""
    states = _state_vector(df, discrete)
    unseen_state = ~states.isin(seen_states)
    prev = states.shift(1)
    unseen_trans = pd.Series(
        [(p, c) not in transitions if pd.notna(p) else False
         for p, c in zip(prev, states)],
        index=df.index,
    )
    return (unseen_state | unseen_trans).to_numpy()


# ─── Model 3: supervised attack detection ──────────────────────────────────

def train_attack_classifier(test_df: pd.DataFrame, feature_cols: List[str],
                            pairs: List[Tuple[str, str]], spreads=None) -> dict:
    """Supervised detector scored against HAI's real attack labels.

    Chronological split - an attack is a contiguous episode, so a random split
    puts seconds from the same event on both sides and inflates every metric.
    """
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.metrics import (average_precision_score, classification_report,
                                 confusion_matrix, f1_score, precision_score,
                                 recall_score, roc_auc_score)

    base = test_df[feature_cols].apply(pd.to_numeric, errors="coerce").fillna(0.0)
    if pairs:
        base = pd.concat([base, build_divergence_features(test_df, pairs, spreads)], axis=1)

    # Temporal context. HAI attack episodes run 56-628 seconds, so a per-second
    # snapshot cannot express what makes them anomalous - the signal is how each
    # tag has MOVED. Restricted to the tags that actually vary, to keep the
    # feature count sane across 86 columns.
    varying = [c for c in base.columns if base[c].std() > 1e-9]
    frames = [base]
    for window in (30, 120):
        roll = base[varying].rolling(window, min_periods=1)
        frames.append(roll.mean().add_suffix(f"_mean{window}"))
        frames.append(roll.std().fillna(0.0).add_suffix(f"_std{window}"))
    for lag in (10, 60):
        frames.append(base[varying].diff(lag).fillna(0.0).add_suffix(f"_d{lag}"))
    X = pd.concat(frames, axis=1).fillna(0.0)

    logger.info("Feature matrix: %d columns (%d base + temporal over %d varying tags)",
                X.shape[1], base.shape[1], len(varying))
    y = test_df["attack"].to_numpy()

    cut = int(len(X) * 0.6)
    X_tr, y_tr = X.iloc[:cut], y[:cut]
    X_te, y_te = X.iloc[cut:], y[cut:]

    if y_tr.sum() == 0 or y_te.sum() == 0:
        logger.warning("Split leaves a side with no attacks (train=%d test=%d) - "
                       "supervised metrics would be meaningless",
                       int(y_tr.sum()), int(y_te.sum()))
        return {"skipped": "attack episodes not present on both sides of the split"}

    # Attacks are ~5% of rows, so the default 0.5 cut optimises accuracy by
    # predicting "normal" almost always. class_weight rebalances the fit, and
    # the operating point is then chosen on the training fold - never on the
    # test fold, which would leak.
    model = HistGradientBoostingClassifier(
        max_iter=250, learning_rate=0.1, max_depth=8,
        class_weight="balanced", random_state=42,
    )
    model.fit(X_tr, y_tr)

    from sklearn.metrics import precision_recall_curve
    tr_proba = model.predict_proba(X_tr)[:, 1]
    prec, rec, thr = precision_recall_curve(y_tr, tr_proba)
    f1s = 2 * prec * rec / np.maximum(prec + rec, 1e-9)
    threshold = float(thr[int(np.nanargmax(f1s[:-1]))]) if len(thr) else 0.5
    logger.info("Operating threshold chosen on train fold: %.4f", threshold)

    proba = model.predict_proba(X_te)[:, 1]
    pred = (proba >= threshold).astype(int)

    metrics = {
        "n_train": int(len(X_tr)), "n_test": int(len(X_te)),
        "attack_seconds_train": int(y_tr.sum()), "attack_seconds_test": int(y_te.sum()),
        "attack_rate_test": round(float(y_te.mean()), 5),
        "precision": round(float(precision_score(y_te, pred, zero_division=0)), 4),
        "recall": round(float(recall_score(y_te, pred, zero_division=0)), 4),
        "f1": round(float(f1_score(y_te, pred, zero_division=0)), 4),
        "roc_auc": round(float(roc_auc_score(y_te, proba)), 4),
        "threshold": round(threshold, 4),
        "avg_precision": round(float(average_precision_score(y_te, proba)), 4),
        "confusion_matrix": confusion_matrix(y_te, pred).tolist(),
    }

    logger.info("Attack detector: precision %.3f recall %.3f F1 %.3f (AP %.3f)",
                metrics["precision"], metrics["recall"], metrics["f1"],
                metrics["avg_precision"])
    logger.info("\n%s", classification_report(y_te, pred, zero_division=0,
                                              target_names=["normal", "attack"]))

    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    import joblib
    joblib.dump({"model": model, "features": list(X.columns)},
                ARTIFACT_DIR / "plc_attack_detector.joblib")
    return metrics


def evaluate_unsupervised(test_df, pairs, div_stats, discrete, seen_states,
                          transitions, div_spreads=None) -> dict:
    """Score the two normal-trained models against the real labels.

    This is the honest test: both were fitted on attack-free data only and have
    never seen an attack.
    """
    from sklearn.metrics import precision_score, recall_score, f1_score

    y = test_df["attack"].to_numpy()
    result = {}

    if pairs and div_stats:
        flags = score_divergence(test_df, pairs, div_stats, div_spreads)
        result["divergence"] = {
            "flagged": int(flags.sum()),
            "precision": round(float(precision_score(y, flags, zero_division=0)), 4),
            "recall": round(float(recall_score(y, flags, zero_division=0)), 4),
            "f1": round(float(f1_score(y, flags, zero_division=0)), 4),
        }
        logger.info("Command/feedback divergence: P %.3f R %.3f F1 %.3f (%d flagged)",
                    result["divergence"]["precision"], result["divergence"]["recall"],
                    result["divergence"]["f1"], result["divergence"]["flagged"])

    if discrete and seen_states:
        flags = score_states(test_df, discrete, seen_states, transitions)
        result["state_machine"] = {
            "flagged": int(flags.sum()),
            "precision": round(float(precision_score(y, flags, zero_division=0)), 4),
            "recall": round(float(recall_score(y, flags, zero_division=0)), 4),
            "f1": round(float(f1_score(y, flags, zero_division=0)), 4),
        }
        logger.info("Discrete state reachability: P %.3f R %.3f F1 %.3f (%d flagged)",
                    result["state_machine"]["precision"], result["state_machine"]["recall"],
                    result["state_machine"]["f1"], result["state_machine"]["flagged"])

    return result


# ─── Entry point ───────────────────────────────────────────────────────────

def main(train_path: Path, test_path: Path, labels_path: Path) -> dict:
    test_df = load_hai(test_path, labels_path)

    if train_path is not None:
        train_df = load_hai(train_path)
        normal_source = train_path.name
    else:
        # Fallback: profile normal behaviour from the rows LABELLED normal in the
        # test file. Weaker than a dedicated attack-free file - the profile has
        # seen normal data interleaved with the attacks it is later scored on -
        # so results from this path are interim, not final.
        train_df = test_df[test_df["attack"] == 0].drop(columns=["attack"]).reset_index(drop=True)
        normal_source = f"{test_path.name} (rows labelled normal)"
        logger.warning("No attack-free training file supplied - profiling normal "
                       "behaviour from %d normal-labelled rows of the test file. "
                       "Re-run with --train for a clean result.", len(train_df))

    classes = classify_signals(train_df)
    pairs = find_command_feedback_pairs(
        [c for c in train_df.columns if c != "timestamp"]
    )

    report = {
        "source": "HAI 23.05 (icsdataset/hai)",
        "data_origin": "REAL",
        "normal_profile_source": normal_source,
        "clean_train_file": train_path.name if train_path else None,
        "test_file": test_path.name,
        "signal_classes": {
            "discrete_DI_DO": len(classes["discrete"]),
            "continuous_AI_AO": len(classes["continuous"]),
        },
        "command_feedback_pairs": [f"{c}->{f}" for c, f in pairs],
    }

    logger.info("--- Model 1: command/feedback divergence (fit on normal) ---")
    report["divergence_model"] = train_divergence_model(train_df, pairs)

    logger.info("--- Model 2: discrete state reachability (fit on normal) ---")
    report["state_model"] = train_state_model(train_df, classes["discrete"])

    logger.info("--- Evaluating normal-trained models against real attack labels ---")
    import joblib
    div = joblib.load(ARTIFACT_DIR / "plc_divergence.joblib") if pairs else {}
    sm = (joblib.load(ARTIFACT_DIR / "plc_state_machine.joblib")
          if classes["discrete"] else {})
    report["unsupervised_vs_labels"] = evaluate_unsupervised(
        test_df, pairs, div.get("stats"), sm.get("discrete"),
        sm.get("states"), sm.get("transitions"), div.get("spreads"),
    )

    logger.info("--- Model 3: supervised attack detector ---")
    feature_cols = [c for c in test_df.columns if c not in ("timestamp", "attack")]
    report["attack_detector"] = train_attack_classifier(
        test_df, feature_cols, pairs, div.get("spreads"))

    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    out = ARTIFACT_DIR / "plc_metrics.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    logger.info("Wrote metrics -> %s", out)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Train models on real HAI PLC signals")
    parser.add_argument("--train", default=None,
                        help="Attack-free HAI training CSV (omit to profile from "
                             "normal-labelled rows of --test, which is weaker)")
    parser.add_argument("--test", required=True, help="HAI test CSV")
    parser.add_argument("--labels", required=True, help="Matching label CSV")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    for p in (args.train, args.test, args.labels):
        if p is not None and not Path(p).exists():
            raise SystemExit(f"File not found: {p}")

    main(Path(args.train) if args.train else None,
         Path(args.test), Path(args.labels))
