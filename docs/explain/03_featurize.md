# 03 — transport/featurize.py(特徴量テーブル生成)

### 0. 図中の対応箇所

図のノード `featurize.py(Magpie統計量 + MP登録値)` に対応。流入エッジ `transport_dataset.csv →(組成式・登録値)`、流出エッジ `→ features_dataset.csv(145特徴量に変換)`。図との相違は無い。

### 1. このファイルの役割

`transport_dataset.csv` の各行(1 材料)を、機械学習モデルが受け取れる数値ベクトルに変換する。組成式から計算する [[Magpie記述子]] 132 次元と、MP 登録値に由来するスカラー 13 次元を横に連結し、[[目的変数]] 4 列・メタ 2 列と共に `features_dataset.csv` として保存する。ステージ2・3 は**この同一テーブルを共用**する。

### 2. 入力と出力

**入力**: `transport/data/transport_dataset.csv`(15,479 行 × 19 列)。使用する列は `formula_pretty`(str、組成式)、`SCALAR_FEATURES` の 5 列(27-33 行: band_gap_mp_eV [eV], density_g_cm3 [g/cm³], volume_per_atom_A3 [Å³], nsites [個], spacegroup_number [整数 1–230])、`is_gap_direct`(bool)、`crystal_system`(str、7 値)。

**出力**: `transport/data/features_dataset.csv`(15,479 行 × 151 列、git 管理外)。列構成:

| 区分 | 列数 | 内容 |
|---|---|---|
| メタ | 2 | material_id, formula_pretty |
| 目的変数 | 4 | seebeck_p_uV_K, seebeck_n_uV_K, sigma_p_S_m, sigma_n_S_m |
| スカラー特徴量 | 5 | SCALAR_FEATURES(上記) |
| フラグ | 1 | is_gap_direct_int(0.0/1.0) |
| [[one-hotエンコーディング]] | 7 | crystal_Cubic … crystal_Triclinic(0.0/1.0) |
| Magpie | 132 | 元素物性 22 種 × 統計量 6 種 |

特徴量は計 145 次元。全列 float(メタ以外)。中間ファイル・他の副作用は無い。

### 3. 関数ごとの解説

このファイルの関数は `main()`(36-71 行)のみ。処理は 4 段からなる。

**(1) 組成オブジェクト化**(42-44 行): [[matminer]] の `StrToComposition` が `formula_pretty` 文字列を pymatgen の Composition に変換する。`ignore_errors=True` のため解釈不能な組成は例外ではなく NaN になり、後段の dropna で行ごと落ちる。

**(2) Magpie 記述子**(45-47 行): `ElementProperty.from_preset("magpie")`。組成に含まれる元素集合を $E$、元素 $e$ の原子分率を $x_e$($\sum_{e \in E} x_e = 1$)、元素物性(原子番号、融点、電気陰性度、価電子数、未充填軌道数など 22 種)の値を $p_e$ とすると、物性ごとに次の 6 統計量を出す:

$$\mathrm{mean} = \sum_{e \in E} x_e\, p_e,\qquad \mathrm{avg\_dev} = \sum_{e \in E} x_e\, |p_e - \mathrm{mean}|$$

$$\mathrm{min} = \min_{e \in E} p_e,\quad \mathrm{max} = \max_{e \in E} p_e,\quad \mathrm{range} = \mathrm{max} - \mathrm{min},\quad \mathrm{mode} = p_{e^*}\ (e^* = \arg\max_e x_e)$$

mean と avg_dev は分率加重、min/max/range は存在元素上の非加重統計、mode は最多分率元素の値である。$22 \times 6 = 132$ 列。列名は `MagpieData mean NdUnfilled` のような形式で、metrics.json の top10_features に現れる名前と一致する。

**(3) 構造スカラー**(50-54 行): `is_gap_direct` を float 化し、`pd.get_dummies` で `crystal_system` を 7 列の 0/1 に展開する。[[ランダムフォレスト]]を含む scikit-learn の回帰器は文字列カテゴリを受け取れないため数値化が必須。space­group_number は 1–230 の整数ラベルをそのまま連続値として与えている(順序に物理的意味は部分的にしかない。設計判断は [91_design_decisions.md](91_design_decisions.md))。

**(4) 選別と保存**(64-69 行): メタ + 目的変数 + 特徴量 151 列に絞り、`dropna()` で欠損行を除外して保存する。現データでは除外 0 行(15,479 → 15,479)。

計算量: Magpie 計算は行数 $N$ と元素数に対して線形で、`featurize_dataframe` の 2 回のパス(マルチプロセス)が実行時間の大半を占める(数分)。

### 4. なぜこの処理が必要か

**物理側**: [[ゼーベック係数]]や[[電気伝導率]]は結晶の電子構造で決まるが、電子構造そのものを入力にすると[[DFT]] 計算が必要になり、代替という目的に反する。組成の元素統計(電気陰性度・価電子数など)と構造スカラー(密度・空間群)は、計算済みデータベース値と組成式だけから求まる安価な[[記述子]]であり、電子構造の代理情報になる。同じ [[BoltzTraP]] 計算に由来する[[有効質量]] $m^*$ を意図的に除外している(7-9 行のコメント)のは、目的変数と生成元を共有する量を入力に使うと[[データリーク]]になるためである。

**機械学習側**: モデルは固定長の数値ベクトルしか受け取れない。可変長の組成式を 132 次元の固定長統計量へ写像するのが Magpie の役割で、これにより任意の無機組成を同一のモデルに入力できる。

### 5. この処理を外したらどうなるか

- ファイルごと外す: `features_dataset.csv` が無く train.py:189 が `FileNotFoundError` で停止。
- Magpie 132 列だけ外す: 特徴量が 13 次元になる。metrics.json の top10_features では Magpie 列が S_n で 10 中 8、σ_n で 10 中 7 を占めており、主要な説明変数群を失う。精度低下の定量値は再実験が必要(コードからは判断不能)。
- one-hot を外して `crystal_system` を文字列のまま含める: `model.fit` が ValueError で停止する。列ごと落とすなら 7 次元の情報損失で済み、動作はする。
- `dropna()` を外す: 現データでは影響なし(欠損 0)。組成解釈に失敗する行が将来混入した場合、RandomForestRegressor が NaN を受けて ValueError で停止する。
