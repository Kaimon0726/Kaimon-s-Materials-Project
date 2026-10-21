# 01 — get_data.py(ステージ1: バンドギャップ取得)

### 0. 図中の対応箇所

元のアーキテクチャ図(docs/mi-project-architecture.html)には対応ノードが無い([00_verify.md](00_verify.md) の「コードにあるが図に無い要素」参照)。修正版 mermaid ではサブグラフ「ステージ1」内の `get_data.py` ノードと、`.env → get_data.py(APIキー)`・`get_data.py → semiconductor_band_gaps.csv` の 2 本のエッジに対応する。2026-09-15 の作者回答によりステージ1は現行構成として維持する。

### 1. このファイルの役割

[[Materials Project]](MP)の API から 8 種の代表的半導体の[[バンドギャップ]]と構造情報を取得し、`semiconductor_band_gaps.csv` に保存するステージ1のスクリプト。パイプライン全体の最初に位置するが、出力 CSV を読むコードはリポジトリに存在せず、ステージ2・3 とはデータ的に接続していない独立のデモである。後段と共有しているのは安定相フィルタ基準(E_hull ≤ 0.05 eV/atom)という**設計上の規約**だけである。

### 2. 入力と出力

**入力**
- `.env` の環境変数 `MP_API_KEY`(文字列 1 個)。無ければ 14-15 行目で `ValueError` を送出して停止する。
- コード内定数 `TARGET_FORMULAS`(get_data.py:20): `["Si", "Ge", "GaAs", "GaN", "ZnO", "InP", "CdTe", "ZnS"]` の 8 組成。
- API 応答: 組成ごとの `SummaryDoc` オブジェクト列(取得フィールドは 44-56 行で 8 個に限定)。

**出力**: リポジトリルートの `semiconductor_band_gaps.csv`(現状 114 データ行 × 9 列、エンコーディング utf-8-sig)。スキーマ:

| 列 | dtype | 単位 |
|---|---|---|
| material_id | str([[mp-id]]) | — |
| formula_pretty | str | — |
| band_gap_eV | float | eV |
| is_gap_direct | bool | — |
| crystal_system | str | — |
| spacegroup_symbol | str | — |
| volume_A3 | float | Å³ |
| nsites | int | 個 |
| energy_above_hull_eV_per_atom | float | eV/atom |

中間ファイルは無い。副作用は stdout への取得件数ログのみ。

### 3. 関数ごとの解説

**`fetch_band_gap_data(api_key: str, formulas: list[str]) -> pd.DataFrame`**(get_data.py:22-88)

組成式ごとに `mpr.materials.summary.search(formula=formula, ...)` を 1 回ずつ呼び(44-56 行)、返された各材料 `doc` に安定相フィルタを適用する(63-65 行):

$$\text{採用} \iff E_{\mathrm{hull}} \le 0.05\ \mathrm{eV/atom}$$

ここで $E_{\mathrm{hull}}$ はコード中の `doc.energy_above_hull`、すなわち [[energy above hull]](その組成系の熱力学的凸包からのエネルギー差。0 なら最安定相)である。`doc.energy_above_hull` が `None` の行は条件式の第 1 項が偽になるため**除外されず採用される**(63 行)。採用行は 9 項目の dict にして `records` に蓄積し、DataFrame で返す。

引数の影響: `formulas` に組成を追加すれば行数が増える。フィルタ閾値 0.05 はハードコードであり引数化されていない。計算量は $O\!\left(\sum_f |{\rm docs}_f|\right)$ で、実行時間は API 往復(組成ごとに 1 リクエスト)が支配的。ローカル処理は数百行の走査で無視できる。

**`main()`**(get_data.py:91-115)

取得結果を `formula_pretty`、`band_gap_eV` の昇順でソートして CSV 保存し(100-104 行)、参考表示として組成ごとの最小バンドギャップを出力する(108-115 行):

$$E_g^{\min}(c) = \min\{\, E_g(m) \mid m \in c,\ E_g(m) > 0 \,\}$$

ここで $c$ は組成(`formula_pretty` でグループ化)、$m$ はその組成に属する各材料、$E_g$ は `band_gap_eV`。$E_g > 0$ の条件(110 行)は金属的なエントリ($E_g = 0$)を集計から外すためのもので、CSV 本体には $E_g = 0$ の行も残る。

### 4. なぜこの処理が必要か

**物理側**: 同一組成でも原子配列が異なる[[多形]]が MP に複数登録されており(8 組成で 114 行になるのはこのため)、バンドギャップが構造に依存することをデータで確認できる。また $E_{\mathrm{hull}}$ による不安定構造の除外は、実在しにくい仮想構造を統計に混ぜないための前処理で、この基準がステージ2・3(`transport/get_transport_data.py:43`)に引き継がれる。

**機械学習側**: このファイルに学習は無い。「データベースから物性値を取得し、フィルタし、表形式に整える」というステージ2・3 と同型の最小工程を、行数が目視確認できる規模(114 行)で先に確立する位置づけである。

### 5. この処理を外したらどうなるか

後段への定量的影響はゼロである。`semiconductor_band_gaps.csv` を読むコードは存在しないため、このファイルと出力 CSV を削除しても `transport_dataset.csv`(15,479 行)、`features_dataset.csv`(151 列)、`metrics.json` の全数値、ダッシュボードの表示内容はいずれも 1 バイトも変わらない。失われるのは (1) ステージ1というプロジェクトの説明単位、(2) E_hull ≤ 0.05 という基準を最初に導入した出所、の 2 点で、いずれもコードではなく説明・文書上の損失である。
