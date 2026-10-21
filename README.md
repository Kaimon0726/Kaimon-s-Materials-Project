# Thermoelectric Property Prediction from DFT Descriptors

Machine-learning models that predict the **Seebeck coefficient *S*** and the
**electrical conductivity σ** of inorganic semiconductors, using the
DFT-computed band gap registered in the
[Materials Project](https://materialsproject.org/) (MP) as one of the input
features. *S* and σ are predicted by **two independent models trained on the same
feature table** — neither model's output is fed into the other. The goal is to
replace expensive BoltzTraP transport calculations (which require a DFT band
structure as input) with cheap ML surrogates for materials screening.

| Target property | Expensive route being replaced | Dataset |
|---|---|---|
| Seebeck coefficient *S* | DFT + BoltzTraP transport | 15,479 semiconductors |
| Electrical conductivity σ | DFT + BoltzTraP transport | 15,479 semiconductors |

The two models are labeled **Stage 2** (*S*) and **Stage 3** (σ) to match the
`train.py --stage 2|3` argument and the `transport/results/stage{2,3}_*/`
directories. The labels are identifiers only: they do not imply a sequential
pipeline, and the two models can be trained and evaluated in either order.

## Motivation

Semiconductor and thermoelectric properties are physically connected: a smaller
band gap makes carriers easier to excite, which shapes both the electrical
conductivity and the Seebeck coefficient. This project uses that relationship as a
**physical hypothesis**, not as a chain of predictions:

- The band gap enters both models as an **input feature**, and it is the
  **DFT value registered in MP** (`band_gap_mp_eV`) — not a predicted value.
- The σ model does **not** use the predicted *S* as a feature; both targets are
  predicted independently from registered quantities.

The reason: feeding one model's predictions into the next propagates its errors
downstream, making it impossible to tell whether poor downstream accuracy comes
from the model design or from inherited error. Keeping every input grounded in
registered data means **each model is independently evaluable**. Whether the band
gap actually drives the transport properties is then checked after training with
SHAP analysis (see [Results](#results-test-set)).

`get_data.py` is an **early exploratory script** that tried out band-gap retrieval
from the MP API for 8 classic semiconductors (Si, Ge, GaAs, GaN, ZnO, InP, CdTe,
ZnS → `semiconductor_band_gaps.csv`, 114 rows). It performs no machine learning,
and its output is **not used** by the training data or the models.

## Data sources

Verified by direct API queries before implementation — see
[docs/DATA_SOURCES.md](docs/DATA_SOURCES.md) for the full investigation.

- **Targets:** MPContribs
  [`carrier_transport`](https://contribs.materialsproject.org/projects/carrier_transport)
  — Ricci et al., *Sci. Data* **4**, 170085 (2017),
  [doi:10.1038/sdata.2017.85](https://doi.org/10.1038/sdata.2017.85) (CC-BY 4.0).
  BoltzTraP-computed Seebeck coefficient (µV/K) and conductivity σ/τ at 300 K and
  a carrier concentration of 10¹⁸ cm⁻³, for p- and n-type doping. Conductivity
  uses the constant relaxation-time approximation (τ = 10⁻¹⁴ s).
  The MP core API itself exposes **no** transport properties (verified: 0 of 69
  summary fields), which is why this companion dataset is required.
- **Features & filters:** MP core `summary` API — registered band gap, energy
  above hull, density, volume, symmetry.

Dataset construction (`transport/get_transport_data.py`):
30,467 non-metallic entries → 22,623 join with the current MP database →
15,682 after the stable-phase filter (E_hull ≤ 0.05 eV/atom) → registered band
gap > 0 → rows with missing targets dropped → **15,479** materials. Classic
thermoelectric families (Bi₂Te₃, SnSe, Mg₂Si, half-Heusler ZrNiSn, skutterudite
CoSb₃) are all present.

## Features

145 features per material (`transport/featurize.py`), shared by both models:

- **Registered band gap** (`band_gap_mp_eV`) and direct/indirect flag — the MP
  DFT values.
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
separately), with a random 80/20 train/test split and 5-fold cross-validation
on the training set (also random folds — see [Known limitations](#known-limitations)).
Conductivity is learned as log₁₀ σ because it spans several orders of magnitude.
SHAP (TreeExplainer) quantifies feature contributions.

### Results (test set)

| Stage | Target | MAE | RMSE | R² | 5-fold CV R² | Band-gap SHAP rank |
|---|---|---|---|---|---|---|
| 2 | *S* p-type (µV/K) | 49.4 | 75.1 | 0.701 | 0.683 ± 0.033 | **1 / 145** |
| 2 | *S* n-type (µV/K) | 54.3 | 80.4 | 0.731 | 0.676 ± 0.032 | **1 / 145** |
| 3 | log₁₀ σ p-type (S/m) | 0.240 | 0.354 | 0.680 | 0.676 ± 0.016 | 4 / 145 |
| 3 | log₁₀ σ n-type (S/m) | 0.215 | 0.354 | 0.757 | 0.729 ± 0.019 | 7 / 145 |

SHAP confirms the band-gap hypothesis from the data: **the registered band gap is
the single most important feature for the Seebeck coefficient** (top SHAP rank
for both doping types, by a ~4× margin over the runner-up), and remains a top-10
feature for conductivity. The SHAP direction is physically sensible: small gaps
sharply suppress *S* (bipolar/metallic-like behavior). For conductivity,
electron-count descriptors (unfilled d-states, p-valence) and density dominate,
with the gap contributing secondarily. This band-gap → transport relationship is
an **observed feature contribution**, not a chain of predictions.

Per-target artifacts under `transport/results/stage{2,3}_*/`: `metrics.json`,
parity plot, SHAP beeswarm plot, and the full SHAP importance ranking (CSV).
Trained models (`.joblib`, ~45 MB each) are written to the same directories but
are not committed to git — rerun `train.py` (a few minutes) to regenerate them.

## Known limitations

- **Requires DFT-computed inputs.** The features include values that come from a
  DFT calculation (band gap, density, space group of the relaxed structure), so
  the models currently **cannot be applied to materials not yet computed in MP**.
  They speed up the BoltzTraP step, not the DFT step.
- **Targets are BoltzTraP calculations, not experiments.** The models reproduce
  computed values under fixed conditions — 300 K, carrier concentration
  10¹⁸ cm⁻³, constant relaxation time τ = 10⁻¹⁴ s (σ is only defined up to τ) —
  on GGA band structures, which systematically underestimate band gaps.
  Validation against experimental datasets (e.g. UCSB thermoelectrics) has not
  been done.
- **Test scores may be optimistic.** `train_test_split` splits rows at random,
  and 4,666 of the 15,479 rows share their chemical formula with another row
  (polymorphs: same composition, different crystal structure). Polymorphs of one
  compound can land in both train and test, and since the 132 Magpie features
  depend only on composition, the test set is not fully unseen. The 5-fold CV
  uses random folds too. A group split by formula (e.g. `GroupKFold`) would give
  a more conservative estimate.

## Future work

- **Extend to uncomputed materials** by adding a front-end model that predicts
  the band gap from composition alone, then feeding that prediction into the
  *S*/σ models. This would deliberately introduce the prediction cascade that the
  current design avoids, so it requires evaluating **error propagation** — how
  much the band-gap prediction error degrades *S* and σ accuracy compared with
  using the registered DFT value.
- Group-aware (formula-level) train/test splitting, and validation against
  experimental thermoelectric data.

## Repository layout

```
get_data.py                     Early exploratory script: MP API band-gap retrieval
                                (8 compounds; not used for training)
semiconductor_band_gaps.csv     Output of get_data.py (not read by any other code)
transport/
  get_transport_data.py         Dataset construction (MPContribs + MP join)
  featurize.py                  matminer feature generation
  train.py                      Training/evaluation (--stage 2: S | --stage 3: σ)
  data/                         Built datasets (CSV)
  results/                      Metrics, plots, SHAP rankings, trained models
web/                            Interactive dashboard (static SPA, no build step)
  build_data.py                 Exports dataset/results to web/data/*.json
  index.html / style.css / app.js
docs/DATA_SOURCES.md            Data-source investigation record
```

## Web dashboard

A dependency-free static dashboard (`web/`) presents the project: a design
overview, an interactive scatter explorer over all 15,479 materials
(crystal-system filter, formula search, per-material detail with Materials
Project links, sortable table view), and per-target model metrics with SHAP
rankings and parity plots. Light/dark themes included.

No server needed — just open `web/index.html` in a browser (data ships as JS
globals, so `file://` works). After retraining:

```bash
python web/build_data.py      # refresh web/data/*.js from the CSVs/metrics
python web/build_single.py    # optional: one-file bundle at web/dist/milab-dashboard.html
```

The single-file bundle inlines everything (data, images, code) and can be
mailed, double-clicked, or dropped on any static host as-is.

## Reproducing

```bash
conda activate mi-env
echo "MP_API_KEY=<your key>" > .env

python transport/get_transport_data.py   # build dataset (~10 min, cached)
python transport/featurize.py            # generate features
python transport/train.py --stage 2      # Seebeck coefficient
python transport/train.py --stage 3      # electrical conductivity
```
