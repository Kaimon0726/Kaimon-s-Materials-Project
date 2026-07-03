"""
ステージ2 (ゼーベック係数) / ステージ3 (電気伝導度) の回帰モデルを学習・評価するスクリプト。

使い方:
    python transport/train.py --stage 2   # ゼーベック係数 (p 型・n 型)
    python transport/train.py --stage 3   # 電気伝導度 log10(σ) (p 型・n 型)

設計方針 (README の Motivation を参照):
  - 両ステージとも同一の特徴量テーブル (features_dataset.csv) を使い、独立に学習する。
  - ステージ3 はステージ2 の予測値を特徴量に使わない (予測誤差の伝播を防ぎ、
    各ステージを独立に評価可能にするため)。
  - バンドギャップの寄与は SHAP 値で可視化し、「バンドギャップ → 電気的特性」という
    物性連鎖ストーリーを定量的に裏付ける。

出力 (results/stage{N}_*/ 以下):
  - model_{target}.joblib          学習済みモデル
  - metrics.json                   回帰精度指標 (test MAE / RMSE / R², 5-fold CV R²)
  - parity_{target}.png            パリティプロット (予測値 vs 実際の値)
  - shap_summary_{target}.png      SHAP beeswarm プロット
  - shap_importance_{target}.csv   平均 |SHAP| による特徴量重要度ランキング
"""

import argparse
import json
import os

import joblib
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import shap
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import cross_val_score, train_test_split

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FEATURES_PATH = os.path.join(BASE_DIR, "data", "features_dataset.csv")

META_COLS = ["material_id", "formula_pretty"]
TARGET_COLS = ["seebeck_p_uV_K", "seebeck_n_uV_K", "sigma_p_S_m", "sigma_n_S_m"]

# プロットの配色 (単一系列は単色 + 控えめなグレー)
COLOR_MAIN = "#4269d0"
COLOR_REF = "#9ca3af"

STAGE_CONFIG = {
    2: {
        "name": "stage2_seebeck",
        "title": "Seebeck coefficient",
        # (目的変数列, 対数変換するか, 表示ラベル)
        "targets": [
            ("seebeck_p_uV_K", False, "Seebeck coefficient, p-type ($\\mu$V/K)"),
            ("seebeck_n_uV_K", False, "Seebeck coefficient, n-type ($\\mu$V/K)"),
        ],
    },
    3: {
        "name": "stage3_conductivity",
        "title": "Electrical conductivity",
        # σ は桁が数桁にわたるため log10 で学習する (τ = 1e-14 s の定緩和時間近似)
        "targets": [
            ("sigma_p_S_m", True, "log$_{10}$ $\\sigma$, p-type (S/m)"),
            ("sigma_n_S_m", True, "log$_{10}$ $\\sigma$, n-type (S/m)"),
        ],
    },
}

SEED = 42
SHAP_SAMPLE_SIZE = 1000  # SHAP 計算に使うテストサンプル数の上限


def parity_plot(y_true, y_pred, label: str, r2: float, mae: float, path: str):
    """予測値 vs 実際の値のパリティプロットを保存する。"""
    fig, ax = plt.subplots(figsize=(5.5, 5.5))
    lo = min(y_true.min(), y_pred.min())
    hi = max(y_true.max(), y_pred.max())
    pad = (hi - lo) * 0.05
    lims = (lo - pad, hi + pad)

    ax.plot(lims, lims, "--", color=COLOR_REF, linewidth=1.5, zorder=1)
    ax.scatter(y_true, y_pred, s=10, alpha=0.25, color=COLOR_MAIN,
               edgecolors="none", zorder=2)

    ax.set_xlim(lims)
    ax.set_ylim(lims)
    ax.set_xlabel(f"DFT+BoltzTraP value: {label}")
    ax.set_ylabel(f"Predicted: {label}")
    ax.set_title(f"$R^2$ = {r2:.3f},  MAE = {mae:.3g}", fontsize=11)
    ax.grid(alpha=0.3, linewidth=0.5)
    ax.spines[["top", "right"]].set_visible(False)
    ax.set_aspect("equal")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def shap_analysis(model, X_test: pd.DataFrame, target: str, out_dir: str) -> pd.DataFrame:
    """SHAP 値を計算し、beeswarm プロットと重要度ランキング CSV を保存する。"""
    sample = X_test.sample(n=min(SHAP_SAMPLE_SIZE, len(X_test)), random_state=SEED)
    explainer = shap.TreeExplainer(model)
    shap_values = explainer.shap_values(sample, check_additivity=False)

    # beeswarm プロット (shap 標準の赤青ダイバージング配色は慣習として維持)
    plt.figure()
    shap.summary_plot(shap_values, sample, max_display=15, show=False)
    plt.tight_layout()
    plt.savefig(os.path.join(out_dir, f"shap_summary_{target}.png"), dpi=150)
    plt.close("all")

    # 平均 |SHAP| による重要度ランキング
    importance = pd.DataFrame({
        "feature": sample.columns,
        "mean_abs_shap": np.abs(shap_values).mean(axis=0),
    }).sort_values("mean_abs_shap", ascending=False).reset_index(drop=True)
    importance["rank"] = importance.index + 1
    importance.to_csv(os.path.join(out_dir, f"shap_importance_{target}.csv"), index=False)
    return importance


def train_one_target(df: pd.DataFrame, feature_cols: list[str], target: str,
                     log_transform: bool, label: str, out_dir: str) -> dict:
    """1 つの目的変数についてモデルを学習・評価し、指標の dict を返す。"""
    data = df.copy()
    if log_transform:
        # log10 のため正の値のみ採用
        data = data[data[target] > 0]
        y = np.log10(data[target])
    else:
        y = data[target]
    X = data[feature_cols]

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=SEED
    )
    print(f"\n=== {target} | train: {len(X_train)} / test: {len(X_test)} ===")

    model = RandomForestRegressor(
        n_estimators=300, min_samples_leaf=2, random_state=SEED, n_jobs=-1
    )
    model.fit(X_train, y_train)

    # テスト評価
    y_pred = model.predict(X_test)
    mae = mean_absolute_error(y_test, y_pred)
    rmse = np.sqrt(mean_squared_error(y_test, y_pred))
    r2 = r2_score(y_test, y_pred)

    # 5-fold クロスバリデーション (訓練データ)
    cv_r2 = cross_val_score(model, X_train, y_train, cv=5,
                            scoring="r2", n_jobs=-1)
    print(f"test MAE = {mae:.4g}, RMSE = {rmse:.4g}, R2 = {r2:.4f}")
    print(f"5-fold CV R2 = {cv_r2.mean():.4f} ± {cv_r2.std():.4f}")

    # 成果物の保存
    parity_plot(y_test, y_pred, label, r2, mae,
                os.path.join(out_dir, f"parity_{target}.png"))
    importance = shap_analysis(model, X_test, target, out_dir)
    joblib.dump(model, os.path.join(out_dir, f"model_{target}.joblib"), compress=3)

    # バンドギャップの寄与 (物性連鎖ストーリーの裏付け)
    bg_row = importance[importance["feature"] == "band_gap_mp_eV"].iloc[0]
    print(f"band_gap_mp_eV の SHAP 重要度: {int(bg_row['rank'])} 位 / {len(feature_cols)} 特徴量")

    return {
        "target": target,
        "log10_transformed": log_transform,
        "n_train": len(X_train),
        "n_test": len(X_test),
        "test_mae": mae,
        "test_rmse": rmse,
        "test_r2": r2,
        "cv_r2_mean": cv_r2.mean(),
        "cv_r2_std": cv_r2.std(),
        "band_gap_shap_rank": int(bg_row["rank"]),
        "top10_features": importance.head(10)["feature"].tolist(),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", type=int, choices=[2, 3], required=True)
    args = parser.parse_args()

    config = STAGE_CONFIG[args.stage]
    out_dir = os.path.join(BASE_DIR, "results", config["name"])
    os.makedirs(out_dir, exist_ok=True)

    df = pd.read_csv(FEATURES_PATH)
    feature_cols = [c for c in df.columns if c not in META_COLS + TARGET_COLS]
    print(f"ステージ{args.stage}: {config['title']}")
    print(f"データ: {len(df)} 件, 特徴量: {len(feature_cols)} 次元")

    metrics = []
    for target, log_transform, label in config["targets"]:
        metrics.append(train_one_target(df, feature_cols, target,
                                        log_transform, label, out_dir))

    with open(os.path.join(out_dir, "metrics.json"), "w") as f:
        json.dump(metrics, f, indent=2, ensure_ascii=False)
    print(f"\n評価結果を保存しました: {out_dir}/metrics.json")


if __name__ == "__main__":
    main()
