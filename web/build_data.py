"""Export the transport dataset and model results as JSON for the web frontend.

Run from the repository root:
    python web/build_data.py
"""
import json
import math
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
OUT = Path(__file__).resolve().parent / "data"
OUT.mkdir(exist_ok=True)

# --- dataset.json: compact column-oriented dump of the 15,479 materials ---
df = pd.read_csv(ROOT / "transport/data/transport_dataset.csv")

def r(x, nd):
    return None if pd.isna(x) else round(float(x), nd)

dataset = {
    "columns": [
        "material_id", "formula", "band_gap_eV", "is_gap_direct",
        "seebeck_p", "seebeck_n", "log10_sigma_p", "log10_sigma_n",
        "density", "volume_per_atom", "nsites", "spacegroup",
        "crystal_system", "e_hull_meV",
    ],
    "rows": [
        [
            row.material_id,
            row.formula_pretty,
            r(row.band_gap_mp_eV, 4),
            bool(row.is_gap_direct),
            r(row.seebeck_p_uV_K, 1),
            r(row.seebeck_n_uV_K, 1),
            r(math.log10(row.sigma_p_S_m), 3),
            r(math.log10(row.sigma_n_S_m), 3),
            r(row.density_g_cm3, 3),
            r(row.volume_per_atom_A3, 2),
            int(row.nsites),
            int(row.spacegroup_number),
            row.crystal_system,
            r(row.energy_above_hull_eV_per_atom * 1000, 1),
        ]
        for row in df.itertuples()
    ],
}
# written as a JS global (not fetched JSON) so the page also works from file://
(OUT / "dataset.js").write_text(
    "window.MILAB_DATA=" + json.dumps(dataset, separators=(",", ":")) + ";")

# --- results.json: metrics + top-15 SHAP importances per target ---
targets = {
    "seebeck_p_uV_K": ("stage2_seebeck", "shap_importance_seebeck_p_uV_K.csv"),
    "seebeck_n_uV_K": ("stage2_seebeck", "shap_importance_seebeck_n_uV_K.csv"),
    "sigma_p_S_m": ("stage3_conductivity", "shap_importance_sigma_p_S_m.csv"),
    "sigma_n_S_m": ("stage3_conductivity", "shap_importance_sigma_n_S_m.csv"),
}

metrics = []
for stage_dir in ("stage2_seebeck", "stage3_conductivity"):
    metrics += json.loads((ROOT / "transport/results" / stage_dir / "metrics.json").read_text())

results = {"metrics": {m["target"]: m for m in metrics}, "shap": {}}
for target, (stage_dir, csv_name) in targets.items():
    shap = pd.read_csv(ROOT / "transport/results" / stage_dir / csv_name)
    results["shap"][target] = {
        "n_features": len(shap),
        "top": [
            {"feature": row.feature, "value": round(float(row.mean_abs_shap), 4)}
            for row in shap.head(15).itertuples()
        ],
    }
(OUT / "results.js").write_text(
    "window.MILAB_RESULTS=" + json.dumps(results, separators=(",", ":")) + ";")

print(f"dataset.js: {len(dataset['rows'])} rows, "
      f"{(OUT / 'dataset.js').stat().st_size / 1e6:.2f} MB")
print(f"results.js: {(OUT / 'results.js').stat().st_size / 1e3:.1f} kB")
