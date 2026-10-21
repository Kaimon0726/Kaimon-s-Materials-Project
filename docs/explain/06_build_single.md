# 06 — web/build_single.py(単一ファイルバンドル)

### 0. 図中の対応箇所

図のノード `build_data / build_single` の後半と、エッジ `→ milab-dashboard.html(1ファイルに合体)` に対応。図に無い入力として `web/index.html`・`style.css`・`app.js`(手書きソース)と `web/assets/parity_*.png`、図に無い第 2 出力として `--fragment` がある([00_verify.md](00_verify.md) の欠落 4・5・6)。作者回答(2026-09-15)により、これは副次的な配布形態であり、正は `web/index.html` の直接オープンである。

### 1. このファイルの役割

`web/` 配下に分かれている HTML・CSS・JS・データ JS・パリティ画像 4 枚を、外部参照ゼロの単一 HTML ファイルに合成する。出力 `web/dist/milab-dashboard.html` は依存ファイル無しで開けるため、メール添付や単独ファイルでの配布に使う。

### 2. 入力と出力

**入力**(すべて `web/` 相対、24-38 行)
- `index.html`(骨格)、`style.css`、`app.js`
- `data/dataset.js`、`data/results.js`([05_build_data.md](05_build_data.md) の出力)
- `assets/parity_*.png` × 4 — **transport/results/ から作者が手動でコピーしたファイル**(コピー処理はコードに存在しない。2026-09-15 作者確認)
- CLI 引数 `--fragment PATH`(任意、20-22 行)

**出力**
- `web/dist/milab-dashboard.html` — 自己完結の 1 ファイル(実測 2.15 MB)
- `--fragment` 指定時のみ: doctype/html/head/body の殻を持たない埋め込み用断片を指定パスへ追加出力(60-68 行)

### 3. 関数ごとの解説

関数定義は無く、スクリプト直書きの逐次処理である。

**(1) 画像の data URI 化**(30-40 行): PNG のバイト列 $b$ を Base64 符号化し、`data:image/png;base64,...` 形式の文字列にして `window.MILAB_PARITY = {target: dataURI}` という JS 代入文を組み立てる。Base64 は 3 バイトを 4 文字に写像するため、埋め込み後のサイズは元の $\lceil 4/3 \rceil$ 倍(約 +33%)になる。app.js 側は `MILAB_PARITY` が定義されていればそれを優先し、無ければ `assets/` への相対パスを使う(app.js:620-622)ので、同じ app.js が分離版・バンドル版の両方で動く。

**(2) スクリプト終端タグの検査**(42-43 行): インライン化する各 JS 文字列に `</script` が含まれないことを assert で確認する。含まれているとブラウザがそこで `<script>` ブロックを打ち切り、以降が HTML として解釈されるため、破損した(かつ潜在的に任意コードが混入し得る)ページになる。データ由来の文字列を HTML に埋め込む際の防御である。

**(3) HTML の組み替え**(45-57 行): `index.html` を `<body>` で 2 分割し、(a) body 内の `<script src="...">` 3 行を正規表現で除去、(b) head 内の `<link rel="stylesheet">` を `<style>` インライン化で置換、(c) body 末尾に dataset.js → results.js → parity → app.js の順で `<script>` ブロックを連結する。この順序は依存関係そのもので、app.js の boot が実行される時点で 3 つのグローバル(`MILAB_DATA`、`MILAB_RESULTS`、`MILAB_PARITY`)が定義済みであることを保証する。

**(4) フラグメント出力**(60-68 行): `<title>` を正規表現で抜き出し、殻タグ抜きで title + meta + style + body + scripts を並べたファイルを書く。ホスト側が独自の HTML 骨格を持つ環境(ブログ等)への埋め込み用。

計算量: 文字列連結と Base64 のみで $O(\text{総バイト数})$、1 秒未満。

### 4. なぜこの処理が必要か

**物理側**: 物理計算は無い。

**機械学習側/配布側**: 分離版(`web/index.html` + 5 ファイル)はディレクトリ構造ごと渡す必要があり、単独の HTML だけ送ると画像とデータが欠ける。成果を 1 ファイルで受け渡すには全アセットのインライン化が必要で、これは学習成果(データ・指標・SHAP・パリティ図)を欠損なく同梱する唯一の経路である。

### 5. この処理を外したらどうなるか

正の配布形態(`web/index.html` 直接)は build_single 無しで完結するため、**外してもダッシュボードの機能・表示内容は失われない**。失われるのは単一ファイル配布の選択肢のみ。逆依存も無く、他のスクリプトは `dist/` を読まない。部分的な劣化モードとして、(1) `build_data.py` を再実行した後に build_single を再実行しないと `dist/` だけ旧データのまま残る、(2) `web/assets/` の PNG を手動更新し忘れると、分離版・バンドル版ともパリティ図だけ旧学習結果を表示する(データと図の不整合はエラーにならず気づきにくい)、の 2 つがある。
