# Data Source Investigation (Stages 2 & 3)

This document records the investigation carried out **before** implementing Stages 2
(Seebeck coefficient) and 3 (electrical conductivity), what data sources were
considered, and why the final choice was made. All findings below were verified by
actually querying the APIs (July 2026), not assumed from documentation.

## 1. Requirement

Stages 2 and 3 need, for hundreds-to-thousands of compounds:

- Seebeck coefficient and electrical conductivity as regression targets
- The **as-registered** (DFT-computed, database-recorded) band gap as an input
  feature — *not* the value predicted by the Stage 1 model
- Energy above hull for stable-phase filtering (same criterion as Stage 1)
- Enough metadata to build composition/structure descriptors with matminer

## 2. Candidate sources examined

### 2.1 Materials Project core API (`mp-api`, `materials.summary`)

**Verified result: no transport properties are available.**

All 69 fields of the `summary` endpoint were enumerated programmatically; none
match Seebeck, conductivity, mobility, carrier, effective mass, or thermoelectric
keywords. The sub-endpoint list (`absorption`, `dielectric`, `elasticity`,
`electronic_structure`, `phonon`, ...) likewise contains no electronic transport
endpoint. The MP core database therefore **cannot** serve as the source of the
regression targets on its own.

It *does* provide what Stage 2/3 need as inputs: `band_gap`,
`energy_above_hull`, `density`, `volume`, `nsites`, `symmetry`, `is_gap_direct`.

### 2.2 MPContribs `carrier_transport` project (Ricci et al.) — **adopted**

**Verified result: exists, accessible with the same MP API key, and sufficient.**

| Item | Verified value |
|---|---|
| Dataset | *An ab initio electronic transport database for inorganic materials* |
| Reference | F. Ricci et al., *Scientific Data* **4**, 170085 (2017), [doi:10.1038/sdata.2017.85](https://doi.org/10.1038/sdata.2017.85) |
| Hosting | MPContribs project `carrier_transport` (also mirrored on Dryad, [doi:10.5061/dryad.gn001](https://doi.org/10.5061/dryad.gn001)) |
| License | **CC-BY 4.0** — reuse in a public portfolio is permitted with attribution |
| Size | 47,737 contributions; **30,467 flagged as non-metallic** (`metal = No`) |
| Identifiers | Materials Project `mp-id` → directly joinable with the MP core API |
| Method | BoltzTraP (semi-classical Boltzmann transport) on top of MP GGA/GGA+U band structures, constant relaxation-time approximation (CRTA) |

Available quantities (per material, for both p-type and n-type doping):

- Seebeck coefficient **S** (µV/K)
- Electrical conductivity **σ/τ** (reported divided by a constant relaxation time
  τ = 10⁻¹⁴ s; unit 1/fΩ/m/s)
- Electronic thermal conductivity κₑ, power factor PF, conductivity effective mass m*
- All scalar values are averages of the tensor eigenvalues at fixed conditions:
  **T = 300 K, carrier concentration 10¹⁸ cm⁻³**; separate `atMax` fields hold
  optima over T ∈ [100, 1300] K and c ∈ [10¹⁶, 10²¹] cm⁻³

Join test (random sample of 200 non-metallic entries): 137 (68.5%) of the 2017-era
mp-ids still resolve in today's MP core database; of those, 94 satisfy
E_hull ≤ 0.05 eV/atom and 92 additionally have a registered band gap > 0.
Extrapolated to the full dataset this yields a **five-figure dataset**, far above
the hundreds-scale minimum required. Presence of the classic thermoelectric
families was confirmed explicitly: Bi₂Te₃ (mp-34202), SnSe, Mg₂Si (mp-1367),
half-Heusler ZrNiSn (mp-924129), and skutterudite CoSb₃ (mp-1317).

### 2.3 Alternatives considered but not needed

- **Experimental datasets (e.g. UCSB thermoelectrics / Citrine, ESTM)** —
  experimental Seebeck/conductivity for ~1k samples, but keyed by composition and
  measurement conditions rather than mp-id, which breaks the "MP-registered band
  gap as feature" design and the E_hull filter. Kept as a candidate for a future
  validation stage against experiment.
- **Scraping `atMax` optima or full temperature/doping tables** — richer, but the
  fixed-condition (300 K, 10¹⁸ cm⁻³) scalars are the cleanest regression targets
  and match the single-value-per-material design of Stage 1.

## 3. Decisions that follow from the investigation

1. **Targets** — Stage 2: S at 300 K / 10¹⁸ cm⁻³ (p- and n-type separately).
   Stage 3: log₁₀ σ under the CRTA with τ = 10⁻¹⁴ s (p- and n-type separately);
   the log is taken because σ spans several orders of magnitude.
2. **Band gap feature** — taken from the MP core `summary` endpoint
   (`band_gap_mp_eV`), i.e. the database-registered value, never the Stage 1
   prediction. Rows whose registered band gap is 0 (metallic in today's MP) are
   dropped for consistency.
3. **Effective mass is deliberately excluded from the features.** It is produced
   by the same BoltzTraP run as the targets, so using it would leak
   target-adjacent information and inflate apparent accuracy.
4. **Carrier concentration is not a feature** — it is fixed at 10¹⁸ cm⁻³ by the
   dataset definition, so it carries no information across samples.
5. **Stable-phase filter** — E_hull ≤ 0.05 eV/atom from the MP core API, the same
   criterion Stage 1 uses.
6. **Caveat recorded in the README** — targets are BoltzTraP/CRTA computed values,
   not experimental measurements, and GGA band gaps are systematically
   underestimated. Both models predict "the expensive calculation," which is
   exactly the screening use-case of this pipeline.
