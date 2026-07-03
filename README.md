# Materials Property Prediction Pipeline

A three-stage machine-learning pipeline that predicts electronic and thermoelectric
properties of inorganic semiconductors, built on the
[Materials Project](https://materialsproject.org/) ecosystem. The goal is to
replace expensive first-principles workflows (DFT band structures, BoltzTraP
transport calculations) with cheap ML surrogates for materials screening.

| Stage | Target property | Expensive route being replaced | Dataset |
|---|---|---|---|
| 1 | Band gap | DFT band-structure calculation | 8 classic semiconductors (intro demo) |
| 2 | Seebeck coefficient *S* | DFT + BoltzTraP transport | ~15,000 semiconductors |
| 3 | Electrical conductivity σ | DFT + BoltzTraP transport | ~15,000 semiconductors |

## Motivation

Semiconductor and thermoelectric properties form a causal chain: a smaller band
gap makes carriers easier to excite, which directly shapes electrical conductivity
and the Seebeck coefficient. This pipeline is designed around that chain — but
**deliberately not as a cascade of predictions**:

- Stage 1 predicts the band gap itself, as a stand-in for the expensive property.
- Stages 2 and 3 build on the *insight* from Stage 1 — that the band gap drives
  electrical behavior — by using the **database-registered band gap** (the MP
  value, not the Stage 1 prediction) as an input feature to predict the even more
  expensive thermoelectric properties.
- Stage 3 likewise does **not** use Stage 2's predicted Seebeck coefficient as a
  feature; it predicts conductivity independently from registered quantities.

The reason: feeding one model's predictions into the next propagates its errors
downstream, making it impossible to tell whether poor downstream accuracy comes
from the model design or from inherited error. Keeping every stage's inputs
grounded in registered data means **each model is independently evaluable** —
the data flow is decoupled while the physical story stays connected. The SHAP
analyses in Stages 2 and 3 then *quantify* that story, showing how much the band
gap actually contributes to each transport property.

## Data sources

Verified by direct API queries before implementation — see
[docs/DATA_SOURCES.md](docs/DATA_SOURCES.md) for the full investigation.

- **Targets (Stages 2–3):** MPContribs
  [`carrier_transport`](https://contribs.materialsproject.org/projects/carrier_transport)
  — Ricci et al., *Sci. Data* **4**, 170085 (2017),
  [doi:10.1038/sdata.2017.85](https://doi.org/10.1038/sdata.2017.85) (CC-BY 4.0).
  BoltzTraP-computed Seebeck coefficient (µV/K) and conductivity σ/τ at 300 K and
  a carrier concentration of 10¹⁸ cm⁻³, for p- and n-type doping. Conductivity
  uses the constant relaxation-time approximation (τ = 10⁻¹⁴ s).
  The MP core API itself exposes **no** transport properties (verified: 0 of 69
  summary fields), which is why this companion dataset is required.
- **Features & filters (all stages):** MP core `summary` API — registered band
  gap, energy above hull, density, volume, symmetry.

Dataset construction (`transport/get_transport_data.py`):
30,467 non-metallic entries → 22,623 join with the current MP database →
15,682 after the stable-phase filter (E_hull ≤ 0.05 eV/atom, same criterion as
Stage 1) → **15,479** with a registered band gap > 0. Classic thermoelectric
families (Bi₂Te₃, SnSe, Mg₂Si, half-Heusler ZrNiSn, skutterudite CoSb₃) are all
present.

## Features

- **Registered band gap** (`band_gap_mp_eV`) and direct/indirect flag — the
  physical link from Stage 1.
- **Composition descriptors:** matminer Magpie element-property statistics
  (132 features).
- **Structure scalars:** density, volume per atom, number of sites, space-group
  number, one-hot crystal system.
- Deliberately **excluded:** the dataset's conductivity effective mass m* (it
  comes from the same BoltzTraP run as the targets — using it would leak
  target-adjacent information), and carrier concentration (fixed at 10¹⁸ cm⁻³
  by the dataset definition).

## Models & evaluation

Random-forest regressors (scikit-learn), one per target (p-type and n-type
separately), with an 80/20 train/test split and 5-fold cross-validation.
Conductivity is learned as log₁₀ σ because it spans several orders of magnitude.
SHAP (TreeExplainer) quantifies feature contributions.

### Results (test set)

| Stage | Target | MAE | RMSE | R² | 5-fold CV R² | Band-gap SHAP rank |
|---|---|---|---|---|---|---|
| 2 | *S* p-type (µV/K) | 49.4 | 75.1 | 0.701 | 0.683 ± 0.033 | **1 / 145** |
| 2 | *S* n-type (µV/K) | 54.3 | 80.4 | 0.731 | 0.676 ± 0.032 | **1 / 145** |
| 3 | log₁₀ σ p-type (S/m) | 0.240 | 0.354 | 0.680 | 0.676 ± 0.016 | 4 / 145 |
| 3 | log₁₀ σ n-type (S/m) | 0.215 | 0.354 | 0.757 | 0.729 ± 0.019 | 7 / 145 |

**The registered band gap is the single most important feature for the Seebeck
coefficient** (top SHAP rank for both doping types, by a ~4× margin over the
runner-up), and remains a top-10 feature for conductivity. The SHAP direction is
physically sensible: small gaps sharply suppress *S* (bipolar/metallic-like
behavior), consistent with the band-gap → transport causal chain this pipeline
is built around. For conductivity, electron-count descriptors (unfilled d-states,
p-valence) and density dominate, with the gap contributing secondarily.

Per-target artifacts under `transport/results/stage{2,3}_*/`: `metrics.json`,
parity plot, SHAP beeswarm plot, and the full SHAP importance ranking (CSV).
Trained models (`.joblib`, ~45 MB each) are written to the same directories but
are not committed to git — rerun `train.py` (a few minutes) to regenerate them.

## Repository layout

```
get_data.py                     Stage 1: band-gap data acquisition (intro demo)
semiconductor_band_gaps.csv     Stage 1 output
transport/
  get_transport_data.py         Stage 2/3 dataset construction (MPContribs + MP join)
  featurize.py                  matminer feature generation
  train.py                      Training/evaluation (--stage 2 | --stage 3)
  data/                         Built datasets (CSV)
  results/                      Metrics, plots, SHAP rankings, trained models
docs/DATA_SOURCES.md            Data-source investigation record
```

## Reproducing

```bash
conda activate mi-env
echo "MP_API_KEY=<your key>" > .env

python transport/get_transport_data.py   # build dataset (~10 min, cached)
python transport/featurize.py            # generate features
python transport/train.py --stage 2      # Seebeck coefficient
python transport/train.py --stage 3      # electrical conductivity
```

## Caveats

- Targets are **computed** (BoltzTraP/CRTA on GGA band structures), not
  experimental values; GGA band gaps are systematically underestimated. The
  models are surrogates for the expensive calculation — exactly the screening
  use-case — and validation against experimental datasets (e.g. UCSB
  thermoelectrics) is a natural next step.
- σ is only defined up to the constant relaxation time τ = 10⁻¹⁴ s.
