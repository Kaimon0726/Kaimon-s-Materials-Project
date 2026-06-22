"""
Materials Project API を使って半導体材料のバンドギャップデータを取得するスクリプト
"""

import os
import pandas as pd
from dotenv import load_dotenv
from mp_api.client import MPRester

# .env ファイルから API キーを読み込む
load_dotenv()
API_KEY = os.getenv("MP_API_KEY")

if not API_KEY:
    raise ValueError(".env ファイルに MP_API_KEY が設定されていません")

# 取得対象の代表的な半導体材料（元素記号）
# Si: シリコン, Ge: ゲルマニウム, GaAs: ガリウムヒ素,
# GaN: 窒化ガリウム, ZnO: 酸化亜鉛, InP: リン化インジウム
TARGET_FORMULAS = ["Si", "Ge", "GaAs", "GaN", "ZnO", "InP", "CdTe", "ZnS"]

def fetch_band_gap_data(api_key: str, formulas: list[str]) -> pd.DataFrame:
    """
    指定した組成式の材料についてバンドギャップ等のデータを取得し DataFrame で返す。

    取得フィールド:
      - material_id    : Materials Project の材料 ID
      - formula_pretty : 組成式（可読形式）
      - band_gap       : バンドギャップ (eV)
      - is_gap_direct  : 直接遷移かどうか
      - crystal_system : 結晶系（立方晶・六方晶など）
      - spacegroup_symbol : 空間群記号
      - volume         : 単位格子体積 (Å³)
      - nsites         : 単位格子中の原子数
      - energy_above_hull : 生成エネルギー差 (eV/atom) — 安定性の指標
    """
    records = []

    with MPRester(api_key) as mpr:
        for formula in formulas:
            print(f"取得中: {formula} ...")

            # バンドギャップが定義されている材料を検索
            docs = mpr.materials.summary.search(
                formula=formula,
                fields=[
                    "material_id",
                    "formula_pretty",
                    "band_gap",
                    "is_gap_direct",
                    "symmetry",
                    "volume",
                    "nsites",
                    "energy_above_hull",
                ],
            )

            total = len(docs)
            excluded = 0

            for doc in docs:
                # 不安定構造を除外: energy_above_hull が 0.05 eV/atom より大きいものはスキップ
                if doc.energy_above_hull is not None and doc.energy_above_hull > 0.05:
                    excluded += 1
                    continue

                # 結晶系と空間群を symmetry オブジェクトから取り出す
                crystal_system = None
                spacegroup_symbol = None
                if doc.symmetry:
                    crystal_system = str(doc.symmetry.crystal_system.value) if doc.symmetry.crystal_system else None
                    spacegroup_symbol = doc.symmetry.symbol

                records.append({
                    "material_id": doc.material_id,
                    "formula_pretty": doc.formula_pretty,
                    "band_gap_eV": doc.band_gap,
                    "is_gap_direct": doc.is_gap_direct,
                    "crystal_system": crystal_system,
                    "spacegroup_symbol": spacegroup_symbol,
                    "volume_A3": doc.volume,
                    "nsites": doc.nsites,
                    "energy_above_hull_eV_per_atom": doc.energy_above_hull,
                })

            print(f"  → 取得: {total} 件 / 除外（不安定構造）: {excluded} 件 / 採用: {total - excluded} 件")

    return pd.DataFrame(records)


def main():
    # データ取得
    df = fetch_band_gap_data(API_KEY, TARGET_FORMULAS)

    if df.empty:
        print("データが取得できませんでした。API キーや検索条件を確認してください。")
        return

    # バンドギャップの昇順で並べ替え
    df = df.sort_values(["formula_pretty", "band_gap_eV"]).reset_index(drop=True)

    # CSV として保存
    output_path = "semiconductor_band_gaps.csv"
    df.to_csv(output_path, index=False, encoding="utf-8-sig")  # BOM 付きで Excel でも文字化けしない
    print(f"\nデータを {output_path} に保存しました（{len(df)} 件）")

    # 材料ごとの最小バンドギャップを表示（参考）
    print("\n--- 材料ごとの最小バンドギャップ (eV) ---")
    summary = (
        df[df["band_gap_eV"] > 0]  # バンドギャップが 0 より大きいもの（絶縁体・半導体）
        .groupby("formula_pretty")["band_gap_eV"]
        .min()
        .sort_values()
    )
    print(summary.to_string())


if __name__ == "__main__":
    main()
