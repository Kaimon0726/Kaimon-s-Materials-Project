"""
transport_dataset.csv から機械学習用の特徴量テーブルを生成するスクリプト。

特徴量の設計方針 (README の Motivation を参照):
  - バンドギャップは MP 登録値 (band_gap_mp_eV) を使う。ステージ1の予測値は使わない。
  - 組成記述子: matminer の Magpie プリセット (元素物性の統計量 132 次元)
  - 構造スカラー記述子: 密度・原子あたり体積・空間群番号・結晶系 (one-hot)・直接遷移フラグ
  - carrier_transport 側の有効質量 (m*) は、目的変数と同じ BoltzTraP 計算に由来する
    ためリークの恐れがあり、意図的に特徴量から除外している。
"""

import os

import pandas as pd
from matminer.featurizers.composition import ElementProperty
from matminer.featurizers.conversions import StrToComposition

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_PATH = os.path.join(BASE_DIR, "data", "transport_dataset.csv")
OUTPUT_PATH = os.path.join(BASE_DIR, "data", "features_dataset.csv")

# 目的変数・メタ情報の列 (特徴量には含めない)
META_COLS = ["material_id", "formula_pretty"]
TARGET_COLS = ["seebeck_p_uV_K", "seebeck_n_uV_K", "sigma_p_S_m", "sigma_n_S_m"]

# MP 登録値ベースのスカラー特徴量
SCALAR_FEATURES = [
    "band_gap_mp_eV",
    "density_g_cm3",
    "volume_per_atom_A3",
    "nsites",
    "spacegroup_number",
]


def main():
    df = pd.read_csv(INPUT_PATH)
    print(f"入力データ: {len(df)} 件")

    # --- 組成記述子 (Magpie) ---
    print("組成記述子 (Magpie) を生成中...")
    df = StrToComposition(target_col_id="composition").featurize_dataframe(
        df, "formula_pretty", ignore_errors=True
    )
    ep = ElementProperty.from_preset("magpie")
    df = ep.featurize_dataframe(df, "composition", ignore_errors=True)
    magpie_cols = ep.feature_labels()

    # --- 構造・電子構造のスカラー特徴量 ---
    df["is_gap_direct_int"] = df["is_gap_direct"].astype(float)

    # 結晶系の one-hot エンコード
    crystal_dummies = pd.get_dummies(df["crystal_system"], prefix="crystal").astype(float)
    df = pd.concat([df, crystal_dummies], axis=1)

    feature_cols = (
        SCALAR_FEATURES
        + ["is_gap_direct_int"]
        + list(crystal_dummies.columns)
        + magpie_cols
    )

    # --- 欠損のある行を除外して保存 ---
    out = df[META_COLS + TARGET_COLS + feature_cols].copy()
    n_before = len(out)
    out = out.dropna()
    print(f"特徴量の欠損除外: {n_before} → {len(out)} 件")

    out.to_csv(OUTPUT_PATH, index=False)
    print(f"特徴量テーブルを保存しました: {OUTPUT_PATH}")
    print(f"  特徴量次元: {len(feature_cols)} (Magpie {len(magpie_cols)} + スカラー/カテゴリ {len(feature_cols) - len(magpie_cols)})")


if __name__ == "__main__":
    main()
