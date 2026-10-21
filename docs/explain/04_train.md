# 04 — transport/train.py(ステージ2・3: 学習・評価・SHAP)

### 0. 図中の対応箇所

図のノード `train.py(RandomForest --stage 2/3)` と `transport/results/(metrics.json・model・SHAP)`、エッジ `features_dataset.csv →(学習入力)`・`→ transport/results/(モデル・指標・SHAP)` に対応。図ではステージ2と3が 1 ノードに統合されているが、コードでは別々の実行・別々の出力ディレクトリである([00_verify.md](00_verify.md) の粒度の注記)。

### 1. このファイルの役割

`features_dataset.csv` を入力に、[[目的変数]] 1 つにつき 1 本の[[ランダムフォレスト]]回帰モデルを学習・評価する。`--stage 2` で[[ゼーベック係数]](p 型・n 型)、`--stage 3` で[[電気伝導率]](log₁₀σ の p 型・n 型)を扱い、計 4 モデルになる。ステージ3 はステージ2 の予測値を**使わない**(カスケード禁止)。あわせて [[SHAP]] による特徴量寄与の定量化と成果物一式の保存を行う。

### 2. 入力と出力

**入力**: `transport/data/features_dataset.csv`(15,479 行 × 151 列)。特徴量は「メタ 2 列 + 目的変数 4 列を除く全列」として動的に決まる(190 行)= 145 列。CLI 引数 `--stage {2,3}`。

**出力**(`transport/results/stage2_seebeck/` または `stage3_conductivity/`):

| ファイル | 内容 |
|---|---|
| `model_{target}.joblib` | 学習済みモデル(compress=3、各約 45 MB、git 管理外) |
| `metrics.json` | 2 ターゲット分の指標リスト(n_train/n_test, test MAE/RMSE/R², CV R² 平均・標準偏差, band_gap_shap_rank, top10_features) |
| `parity_{target}.png` | [[パリティプロット]](150 dpi) |
| `shap_summary_{target}.png` | SHAP beeswarm 図 |
| `shap_importance_{target}.csv` | 145 特徴量の重要度ランキング(feature, mean_abs_shap, rank) |

### 3. 関数ごとの解説

**`train_one_target(df, feature_cols, target, log_transform, label, out_dir) -> dict`**(121-177 行)

ステージ3 のみ[[対数変換]]を適用する(127-130 行)。$y_i$ を材料 $i$ の目的変数値として

$$y_i^{\rm (fit)} = \log_{10} \sigma_i \quad (\sigma_i > 0 \text{ の行のみ。現データでは全行が正})$$

[[train/test分割]]は `train_test_split(X, y, test_size=0.2, random_state=SEED)`(133-135 行)。$N = 15{,}479$ が train 12,383 / test 3,096 に無作為分割される。分割は行単位であり、同一組成の[[多形]]が train と test に分かれて入り得る(この含意は [92_audit.md](92_audit.md))。

モデルは `RandomForestRegressor(n_estimators=300, min_samples_leaf=2, random_state=SEED, n_jobs=-1)`(138-140 行)。$B = 300$ 本の回帰木 $T_b$ をブートストラップ標本で学習し、予測は平均:

$$\hat y(x) = \frac{1}{B} \sum_{b=1}^{B} T_b(x)$$

`min_samples_leaf=2` は葉に最低 2 標本を要求して過剰な深さを抑える。評価指標(144-147 行)は、テスト集合の $n = 3{,}096$ 行に対して

$$\mathrm{MAE} = \frac{1}{n}\sum_{i}|y_i - \hat y_i|,\qquad \mathrm{RMSE} = \sqrt{\frac{1}{n}\sum_{i}(y_i - \hat y_i)^2},\qquad R^2 = 1 - \frac{\sum_i (y_i - \hat y_i)^2}{\sum_i (y_i - \bar y)^2}$$

($\bar y$ はテスト集合の平均)。[[交差検証]]は**訓練側 12,383 行のみ**を 5 分割し(150-151 行、シャッフル無しの KFold)、fold ごとに新しいモデルを学習して $R^2$ の平均と標準偏差を報告する。テスト集合は CV に関与しない。

引数の影響: `log_transform=True` は σ の数桁のレンジを圧縮し、大きい値への二乗誤差の偏重を防ぐ。`test_size` を変えると n_train/n_test と全指標が変わる。`SEED=42` 固定により分割・木構造・CV が決定的で、metrics.json は再実行で同一値になる(入力 CSV が同一である限り)。計算量は木 1 本あたり $O(m \cdot n \log n)$($m=145$ 特徴量、$n$=訓練行数)で、それが $B \times (1 + 5)$ 回(本体 + CV)走る。実行時間は数分、fit が支配的。

**`shap_analysis(model, X_test, target, out_dir) -> pd.DataFrame`**(98-118 行)

テスト集合から最大 `SHAP_SAMPLE_SIZE = 1000` 行を抽出し、[[TreeExplainer]] で SHAP 値 $\phi_{ij}$(標本 $i$ における特徴量 $j$ の寄与)を厳密計算する。SHAP の加法性

$$\hat y(x_i) = \phi_0 + \sum_{j=1}^{145} \phi_{ij}$$

($\phi_0$ は学習データ平均に対応する基準値)により、予測値が特徴量ごとの寄与に分解される。重要度は標本平均絶対値 $I_j = \frac{1}{1000}\sum_i |\phi_{ij}|$ で(112-115 行)、降順ランキングを CSV 保存する。`check_additivity=False` は数値誤差チェックの無効化で値自体は変えない。

**`parity_plot(...)`**(73-95 行): 横軸に BoltzTraP 値、縦軸に予測値を等スケールで描き、対角線 $\hat y = y$ を参照線とする散布図。

**`main()`**(180-201 行): `STAGE_CONFIG`(48-67 行)からターゲット 2 つと変換フラグを取り、順に `train_one_target` を実行して metrics.json に書く。

### 4. なぜこの処理が必要か

**物理側**: 学習済みモデルは [[DFT]]+[[BoltzTraP]] という高コスト計算の代替(サロゲート)である。SHAP による `band_gap_mp_eV` の順位(S で 1 位、σ で 4/7 位)は、「[[バンドギャップ]]が輸送物性を駆動する」という設計時の物理仮説をデータで定量化する役割を持つ。

**機械学習側**: ランダムフォレストはスケーリング不要・非線形・混合スケールの 145 特徴量をそのまま扱え、TreeExplainer による厳密 SHAP 計算と両立する。CV はテスト 1 回分割の偶然性を補い、平均 ± 標準偏差で汎化性能の安定性を示す。

### 5. この処理を外したらどうなるか

- ファイルごと外す: モデル・metrics.json が生成されず、`web/build_data.py:63` が metrics.json を読めず `FileNotFoundError` で停止。
- 対数変換を外す(σ を線形で学習): 目的変数が約 5 桁のレンジを持つため二乗誤差が大値側に支配され、$R^2$ の意味が変質する。定量的な低下幅は再実験が必要。
- CV を外す: 動作・保存物は metrics.json の cv_* 2 項目が欠けるだけだが、単一分割の R² のみとなり評価の信頼区間を失う。
- SHAP を外す: band_gap_shap_rank が計算できず 162 行で KeyError。README とダッシュボードの中心的主張(E_g SHAP 1 位)の根拠が消える。
