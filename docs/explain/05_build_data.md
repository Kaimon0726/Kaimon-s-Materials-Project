# 05 — web/build_data.py(ダッシュボード用データ書き出し)

### 0. 図中の対応箇所

図のノード `build_data / build_single(CSV・JSON → 埋め込みJS)` の前半に対応。流入エッジは `transport_dataset.csv →(実データ)` と `transport/results/ →(精度指標)`。出力先である `web/data/dataset.js`・`web/data/results.js` は図にノードとして描かれていない([00_verify.md](00_verify.md) の欠落 3)。

### 1. このファイルの役割

パイプラインの成果物(データセット CSV、metrics.json、SHAP ランキング CSV)を、ブラウザが `<script src>` で読める JavaScript ファイル 2 つに変換する。作者回答(2026-09-15)により配布の正は `web/index.html` の直接オープンであり、このスクリプトの出力がその表示データの全てになる。

### 2. 入力と出力

**入力**
- `transport/data/transport_dataset.csv`(15,479 行 × 19 列。17 行)
- `transport/results/{stage2_seebeck,stage3_conductivity}/metrics.json`(62-63 行)
- 同ディレクトリの `shap_importance_{target}.csv` × 4(66-67 行)

**出力**(`web/data/`、いずれも JSON を JS グローバル代入文で包んだもの)
- `dataset.js` — `window.MILAB_DATA = {columns: [...], rows: [[...], ...]}`。列指向ではなく**行配列**の配列で、1 行 = 14 要素(material_id, formula, band_gap_eV, is_gap_direct, seebeck_p, seebeck_n, log10_sigma_p, log10_sigma_n, density, volume_per_atom, nsites, spacegroup, crystal_system, e_hull_meV)。実測 1.49 MB。
- `results.js` — `window.MILAB_RESULTS = {metrics: {target: {...}}, shap: {target: {n_features, top: [...]}}}`。metrics.json の全項目と、SHAP 上位 15 件のみ。

### 3. 関数ごとの解説

ファイルはスクリプト直書きで、関数は丸め用の `r(x, nd)`(19-20 行)のみ: `pd.isna(x)` なら `None`(JSON では null)、そうでなければ `round(float(x), nd)`。

**dataset 生成**(22-51 行): 各行のタプルを固定順の配列に写像する。数値は列ごとに桁を落として転送量を削る(band_gap 4 桁、seebeck 1 桁、density 3 桁など)。σ はここで[[対数変換]]される(37-38 行):

$$\texttt{log10\_sigma\_p} = \mathrm{round}(\log_{10} \sigma_p^{\rm [S/m]},\ 3)$$

すなわちダッシュボードが表示する σ は学習時と同じ log₁₀ スケールである。[[energy above hull]] は eV/atom から meV/atom へ換算する(44 行、$\times 1000$)。書き出しは `json.dumps(..., separators=(",", ":"))` で空白を除去し、`window.MILAB_DATA=...;` の代入文にする(50-51 行)。JSON ファイルを `fetch` で読む方式にしなかったのは、`file://` で開いたときに fetch がブロックされるためで、`<script>` 読み込みならローカルの二重クリックでも動く(49 行のコメント)。

**results 生成**(53-76 行): 2 ステージの metrics.json を連結して target 名で引ける dict にし、SHAP ランキングは各 145 行のうち `head(15)` だけを `{feature, value}` の配列で持つ。`n_features: 145` は UI の「/ 145」表示の分母になる。

計算量: 15,479 行の 1 パス変換で $O(N)$、実行は数秒。

### 4. なぜこの処理が必要か

**物理側**: 固有の物理計算は無い。σ の log₁₀ 化は、数桁にわたる量を軸上で読めるようにする表示上の必然で、学習時の変換([04_train.md](04_train.md))と目盛りを一致させる。

**機械学習側**: これも固有の学習処理は無いが、「学習に使った 15,479 行そのもの」を可視化する経路である点が重要。ダッシュボードの散布図・KPI・SHAP 表示は、このスクリプトが機械的に転記した値であり、手書きの数値ではない(例外は app.js 内のハードコード。[07_app.md](07_app.md) 参照)。

### 5. この処理を外したらどうなるか

`web/data/*.js` が存在しない・古いままの場合、ページ自体は開くが `window.MILAB_DATA` が undefined になり、app.js の boot(640-647 行)が「データの読み込みに失敗しました。`python web/build_data.py` で web/data/ を生成してください。」と表示して初期化を中断する。再学習後にこのスクリプトを実行し忘れると、**エラーは出ずに旧データが表示され続ける**(ファイルが残っているため)。metrics.json だけ更新して dataset.js を作り直さない、といった部分的な実行でも同様に新旧混在が起きる。数値の劣化としては丸めのみで、誤差は最終表示桁の半分未満(例: band_gap は 0.00005 eV 未満)である。
