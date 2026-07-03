"""
ステージ2・3用の熱電輸送物性データセットを構築するスクリプト。

データソース:
  1. MPContribs "carrier_transport" プロジェクト (Ricci et al., Sci. Data 4, 170085, 2017)
     - BoltzTraP 計算によるゼーベック係数 S・電気伝導度 σ/τ (300 K, キャリア濃度 10^18 cm^-3)
     - p 型 / n 型ドーピング別に収録。ライセンス: CC-BY 4.0
  2. Materials Project summary API
     - バンドギャップ (MP 登録値)・energy_above_hull・構造スカラー記述子

処理の流れ:
  carrier_transport から半導体 (metal=No) を全件取得
  → mp-id で MP summary と結合 (旧 ID で照合できないものは除外)
  → E_hull <= 0.05 eV/atom の安定相フィルタリング (ステージ1と同じ基準)
  → band_gap > 0 の半導体のみ採用
  → transport_dataset.csv として保存

注意: ステージ1で扱った「予測バンドギャップ」は一切使わない。
      特徴量となるバンドギャップは MP 登録値 (band_gap_mp_eV) である。
"""

import os
import sys

import pandas as pd
from dotenv import load_dotenv
from mp_api.client import MPRester
from mpcontribs.client import Client

# .env は リポジトリルートに置いてある
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(ROOT_DIR, ".env"))
API_KEY = os.getenv("MP_API_KEY")

if not API_KEY:
    raise ValueError(".env ファイルに MP_API_KEY が設定されていません")

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
RAW_CACHE_PATH = os.path.join(DATA_DIR, "carrier_transport_raw.csv")
OUTPUT_PATH = os.path.join(DATA_DIR, "transport_dataset.csv")

# ステージ1と同じ安定相フィルタリング基準
E_HULL_THRESHOLD = 0.05  # eV/atom

# Ricci データセットの σ は緩和時間 τ = 10^-14 s で規格化された値 (σ/τ, 単位 1/fΩ/m/s)。
# σ [S/m] に直すには: σ = (値 × 1e15 [1/Ω/m/s]) × 1e-14 [s] = 値 × 10
SIGMA_UNIT_FACTOR = 10.0


def fetch_carrier_transport() -> pd.DataFrame:
    """carrier_transport プロジェクトから半導体 (metal=No) の輸送物性を全件取得する。"""
    if os.path.exists(RAW_CACHE_PATH):
        print(f"キャッシュを使用: {RAW_CACHE_PATH}")
        return pd.read_csv(RAW_CACHE_PATH)

    client = Client(apikey=API_KEY, project="carrier_transport")
    print("MPContribs carrier_transport から半導体エントリを取得中（数分かかります）...")

    result = client.query_contributions(
        query={"project": "carrier_transport", "data__metal__exact": "No"},
        fields=[
            "identifier",           # mp-id
            "formula",
            "data.dE.value",        # BoltzTraP 計算時のバンドギャップ (参考値)
            "data.S.p.value",       # ゼーベック係数 p 型 [µV/K] @300K, 1e18 cm^-3
            "data.S.n.value",       # ゼーベック係数 n 型 [µV/K]
            "data.sigma.p.value",   # 電気伝導度 σ/τ p 型 [1/fΩ/m/s]
            "data.sigma.n.value",   # 電気伝導度 σ/τ n 型 [1/fΩ/m/s]
        ],
        paginate=True,
    )

    records = []
    for doc in result["data"]:
        data = doc.get("data", {})

        def _val(*keys):
            node = data
            for key in keys:
                node = node.get(key, {}) if isinstance(node, dict) else {}
            return node.get("value") if isinstance(node, dict) else None

        records.append({
            "material_id": doc.get("identifier"),
            "formula_ricci": doc.get("formula"),
            "band_gap_boltztrap_eV": _val("dE"),
            "seebeck_p_uV_K": _val("S", "p"),
            "seebeck_n_uV_K": _val("S", "n"),
            "sigma_over_tau_p": _val("sigma", "p"),
            "sigma_over_tau_n": _val("sigma", "n"),
        })

    df = pd.DataFrame(records).drop_duplicates(subset="material_id")
    os.makedirs(DATA_DIR, exist_ok=True)
    df.to_csv(RAW_CACHE_PATH, index=False)
    print(f"取得完了: {len(df)} 件 → キャッシュ保存: {RAW_CACHE_PATH}")
    return df


def fetch_mp_summary(material_ids: list[str], chunk_size: int = 1000) -> pd.DataFrame:
    """MP summary API からバンドギャップ (登録値)・E_hull・構造スカラー記述子を取得する。

    material_ids は API の上限を超えないよう chunk_size 件ずつに分割して照合する。
    """
    print(f"Materials Project summary を照合中: {len(material_ids)} 件の mp-id ...")

    docs = []
    with MPRester(API_KEY) as mpr:
        for i in range(0, len(material_ids), chunk_size):
            chunk = material_ids[i:i + chunk_size]
            docs.extend(mpr.materials.summary.search(
                material_ids=chunk,
                fields=[
                    "material_id",
                    "formula_pretty",
                    "band_gap",           # MP 登録値 (特徴量として使用)
                    "is_gap_direct",
                    "energy_above_hull",
                    "density",
                    "volume",
                    "nsites",
                    "symmetry",
                ],
            ))
            print(f"  {min(i + chunk_size, len(material_ids))} / {len(material_ids)} 件処理済み")

    records = []
    for doc in docs:
        crystal_system = None
        spacegroup_number = None
        if doc.symmetry:
            crystal_system = str(doc.symmetry.crystal_system.value) if doc.symmetry.crystal_system else None
            spacegroup_number = doc.symmetry.number

        records.append({
            "material_id": str(doc.material_id),
            "formula_pretty": doc.formula_pretty,
            "band_gap_mp_eV": doc.band_gap,
            "is_gap_direct": doc.is_gap_direct,
            "energy_above_hull_eV_per_atom": doc.energy_above_hull,
            "density_g_cm3": doc.density,
            "volume_A3": doc.volume,
            "nsites": doc.nsites,
            "volume_per_atom_A3": doc.volume / doc.nsites if doc.volume and doc.nsites else None,
            "crystal_system": crystal_system,
            "spacegroup_number": spacegroup_number,
        })

    print(f"  → 照合成功: {len(records)} 件（旧 mp-id で現行 MP に存在しないものは除外）")
    return pd.DataFrame(records)


def main():
    # 1. 輸送物性 (MPContribs)
    df_transport = fetch_carrier_transport()
    print(f"carrier_transport 半導体エントリ: {len(df_transport)} 件")

    # 2. MP summary との結合
    df_mp = fetch_mp_summary(df_transport["material_id"].dropna().unique().tolist())
    df = df_transport.merge(df_mp, on="material_id", how="inner")
    print(f"MP と結合後: {len(df)} 件")

    # 3. 安定相フィルタリング (ステージ1と同じ基準)
    n_before = len(df)
    df = df[df["energy_above_hull_eV_per_atom"].notna()
            & (df["energy_above_hull_eV_per_atom"] <= E_HULL_THRESHOLD)]
    print(f"E_hull <= {E_HULL_THRESHOLD} eV/atom フィルタ: {n_before} → {len(df)} 件")

    # 4. MP 登録値でも半導体であるものだけ採用 (band_gap > 0)
    n_before = len(df)
    df = df[df["band_gap_mp_eV"].notna() & (df["band_gap_mp_eV"] > 0)]
    print(f"band_gap > 0 フィルタ: {n_before} → {len(df)} 件")

    # 5. 目的変数の欠損を除外し、σ を S/m に換算した列を追加
    n_before = len(df)
    target_cols = ["seebeck_p_uV_K", "seebeck_n_uV_K", "sigma_over_tau_p", "sigma_over_tau_n"]
    df = df.dropna(subset=target_cols)
    print(f"目的変数の欠損除外: {n_before} → {len(df)} 件")

    df["sigma_p_S_m"] = df["sigma_over_tau_p"] * SIGMA_UNIT_FACTOR
    df["sigma_n_S_m"] = df["sigma_over_tau_n"] * SIGMA_UNIT_FACTOR

    df = df.sort_values("material_id").reset_index(drop=True)
    df.to_csv(OUTPUT_PATH, index=False, encoding="utf-8-sig")
    print(f"\nデータセットを保存しました: {OUTPUT_PATH}（{len(df)} 件）")

    # 参考: 代表的な熱電材料が含まれているか確認
    print("\n--- 代表的な熱電材料の収録確認 ---")
    for name, mpid in [("Bi2Te3", "mp-34202"), ("Mg2Si", "mp-1367"),
                       ("CoSb3", "mp-1317"), ("ZrNiSn", "mp-924129")]:
        hit = df[df["material_id"] == mpid]
        if len(hit):
            row = hit.iloc[0]
            print(f"  {name} ({mpid}): S_p = {row['seebeck_p_uV_K']:.0f} µV/K, "
                  f"Eg(MP) = {row['band_gap_mp_eV']:.2f} eV")
        else:
            print(f"  {name} ({mpid}): 収録なし")


if __name__ == "__main__":
    main()
