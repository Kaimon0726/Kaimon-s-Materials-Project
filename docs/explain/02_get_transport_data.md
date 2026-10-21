# 02 — transport/get_transport_data.py(ステージ2・3: データセット構築)

### 0. 図中の対応箇所

図のノード `get_transport_data.py(結合・安定相/半導体フィルタ)` に対応。流入エッジは `.env →(APIキー)`、`MP Summary API →(登録値)`、`MPContribs →(S・σ)` の 3 本、流出エッジは `→ transport_dataset.csv(選別済み)`。ただし図に無いキャッシュファイル `data/carrier_transport_raw.csv` への書き込み・読み込みがある([00_verify.md](00_verify.md) の相違 1)。

### 1. このファイルの役割

[[目的変数]](ゼーベック係数・電気伝導率)を持つ [[MPContribs]] の `carrier_transport` データセットと、[[特徴量]]の素材(登録バンドギャップ・構造スカラー)を持つ [[Materials Project]] 本体の summary API を、[[mp-id]] をキーに内部結合して 1 枚の表にする。パイプライン本体の起点であり、これ以降のすべての工程は API に触れず、この出力だけを入力とする。

### 2. 入力と出力

**入力**
- `.env` の `MP_API_KEY`(31-36 行。ルート直下の `.env` を明示パスで読む)。
- MPContribs `carrier_transport`: `metal = No` の全エントリ(30,467 件)。各エントリから `identifier`、`formula`、`data.dE.value`、`data.S.{p,n}.value`、`data.sigma.{p,n}.value` の 7 項目(61-69 行)。
- MP summary API: mp-id 照合で `band_gap`、`is_gap_direct`、`energy_above_hull`、`density`、`volume`、`nsites`、`symmetry` など(113-123 行)。

**出力**
- `transport/data/carrier_transport_raw.csv` — MPContribs 取得結果の生キャッシュ。30,467 行 × 7 列(material_id, formula_ricci, band_gap_boltztrap_eV, seebeck_p_uV_K, seebeck_n_uV_K, sigma_over_tau_p, sigma_over_tau_n)。git 管理外(.gitignore:9)。
- `transport/data/transport_dataset.csv` — 最終出力。15,479 行 × 19 列(上記 7 列 + MP 由来 10 列 + 換算 σ 2 列)、utf-8-sig。

単位: ゼーベック係数 µV/K、σ/τ は 1/(fΩ·m·s)、換算後の σ は S/m、E_hull は eV/atom、密度 g/cm³、体積 Å³。

### 3. 関数ごとの解説

**`fetch_carrier_transport() -> pd.DataFrame`**(50-97 行)

キャッシュ `carrier_transport_raw.csv` が存在すればそれを読んで即座に返す(52-54 行)。**API に接続するのは初回のみ**である。初回は `query_contributions(query={"project": "carrier_transport", "data__metal__exact": "No"}, ..., paginate=True)` で全ページを取得し、入れ子 dict を安全に辿る内部関数 `_val` で値を取り出し、`drop_duplicates(subset="material_id")` で mp-id 重複を除去して保存する(93-95 行)。計算量は取得件数 $N=30{,}467$ に対して $O(N)$、実時間は API のページネーション(数分)が支配的。

**`fetch_mp_summary(material_ids: list[str], chunk_size: int = 1000) -> pd.DataFrame`**(100-150 行)

mp-id のリストを `chunk_size`(既定 1000)件ずつに分割して `materials.summary.search(material_ids=chunk, ...)` を呼ぶ。分割は API のクエリ長制限を超えないための処置。2017 年当時の mp-id が現行 MP に存在しない場合、その id の応答が返らないため、この段階で自然に脱落する(30,467 → 22,623 件)。`volume_per_atom_A3 = volume / nsites` の派生列をここで作る(144 行)。引数 `chunk_size` は結果に影響せず、リクエスト回数(⌈N/chunk_size⌉)だけを変える。

**`main()`**(153-197 行)

5 段の処理を順に適用する。件数は 2026-09-15 時点のスナップショット(作者回答により固定値として扱う):

1. MPContribs 取得: 30,467 件
2. MP summary と内部結合(`merge(..., how="inner")`、160 行): → 22,623 件
3. 安定相フィルタ(165-166 行): $E_{\mathrm{hull}} \le 0.05$ eV/atom、かつ欠損は除外 → 15,682 件
4. 半導体フィルタ(171 行): MP 登録[[バンドギャップ]] $E_g^{\mathrm{MP}} > 0$ → 15,479 件
5. 目的変数 4 列(S の p/n、σ/τ の p/n)の欠損行を除外(176-177 行。現データでは 0 行削除)し、σ を単位換算(180-181 行)。

換算の根拠(45-47 行のコメント): Ricci データセットの σ は[[定緩和時間近似]]の下で緩和時間 $\tau$ により規格化された $\sigma/\tau$(単位 $1/(\mathrm{f\Omega \cdot m \cdot s}) = 10^{15}\,\Omega^{-1}\mathrm{m}^{-1}\mathrm{s}^{-1}$)である。$\tau = 10^{-14}\,\mathrm{s}$ を掛け戻すと

$$\sigma\,[\mathrm{S/m}] = \underbrace{(\sigma/\tau)_{\rm raw}}_{\texttt{sigma\_over\_tau\_p/n}} \times 10^{15} \times 10^{-14} = 10 \times (\sigma/\tau)_{\rm raw}$$

これがコードの `SIGMA_UNIT_FACTOR = 10.0`(47 行)である。最後に代表的[[熱電材料]](Bi₂Te₃, Mg₂Si, CoSb₃, ZrNiSn)の残存を表示して健全性を確認する(188-197 行)。

### 4. なぜこの処理が必要か

**物理側**: 目的変数([[BoltzTraP]] 計算の S と σ/τ)と特徴量の素材(登録バンドギャップ等)は別のデータベースに分かれて存在し、MP 本体 API には輸送物性が一切無い(docs/DATA_SOURCES.md で全 69 フィールドを列挙して確認済み)。結合しなければ学習データが成立しない。E_hull フィルタは合成可能性の低い仮想構造を、$E_g > 0$ フィルタは金属(ゼーベック係数の振る舞いが本質的に異なる)を除く。

**機械学習側**: `metal=No` フラグは 2017 年の計算に基づくため、現行 MP で $E_g = 0$ に更新された材料が混ざる。フィルタ 4 は特徴量(`band_gap_mp_eV`)と母集団の定義を一致させ、「半導体のみ」という学習条件を特徴量側の値で保証する。

### 5. この処理を外したらどうなるか

- ファイルごと外す: `transport_dataset.csv` が生成されず、featurize.py 以降(37 行の `read_csv`)が `FileNotFoundError` で停止する。パイプライン全体が動かない。
- フィルタ 3(E_hull)だけ外す: 行数が 22,623 に増え、準安定・仮想構造が学習に混入する。精度指標への影響は再実験しないと不明(コードからは判断不能)。
- フィルタ 4($E_g>0$)だけ外す: $E_g=0$ の 203 行(15,682−15,479)が混入し、「バンドギャップ→輸送物性」という設計前提の母集団定義が崩れる。
- σ 換算(180-181 行)だけ外す: 後段は `sigma_p_S_m` 列名を直接参照するため(featurize.py:24)`KeyError` で停止する。なお換算は定数倍なので、[[対数変換]]後は切片が 1 ずれるだけであり、モデルの[[決定係数]]には影響しない。
