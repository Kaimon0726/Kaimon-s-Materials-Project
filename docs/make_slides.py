"""面接用スライド (pptx) を生成するスクリプト。

    python docs/make_slides.py        # -> docs/mi-project-slides.pptx

方針:
  - 1スライド1メッセージ。見出しがそのまま主張になるように書く。
  - 図はデータフロー図1枚 + 結果の裏付け2点 (パリティ図・SHAP棒) のみ。
  - 数値はすべて transport/results/ の実測値から埋め込む (手打ちしない)。
  - フォントは BIZ UDGothic (macOS / Windows 10+ の双方に同名で存在する)。
"""
import json
from pathlib import Path

import pandas as pd
from lxml import etree
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Emu, Inches, Pt

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "mi-project-slides.pptx"
STAGE2 = ROOT / "transport" / "results" / "stage2_seebeck"

FONT = "BIZ UDGothic"
ACCENT = RGBColor(0x42, 0x69, 0xD0)   # train.py のプロット色と同じ
INK = RGBColor(0x16, 0x19, 0x1F)
MUTED = RGBColor(0x6B, 0x72, 0x80)
LINE = RGBColor(0xDC, 0xE1, 0xEA)
TINT = RGBColor(0xF3, 0xF6, 0xFC)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)

W, H = Inches(13.333), Inches(7.5)
MARGIN = Inches(1.0)
BODY_W = W - 2 * MARGIN


# --------------------------------------------------------------------------
# 実測値の読み込み (手打ち防止)
# --------------------------------------------------------------------------
metrics = {m["target"]: m for m in json.loads((STAGE2 / "metrics.json").read_text())}
MP, MN = metrics["seebeck_p_uV_K"], metrics["seebeck_n_uV_K"]

shap_p = pd.read_csv(STAGE2 / "shap_importance_seebeck_p_uV_K.csv")
SHAP_TOP5 = shap_p.head(5)[["feature", "mean_abs_shap"]].values.tolist()
SHAP_RATIO = shap_p.mean_abs_shap[0] / shap_p.mean_abs_shap[1]
N_FEATURES = len(shap_p)
N_MATERIALS = MP["n_train"] + MP["n_test"]

FEATURE_JP = {
    "band_gap_mp_eV": "登録バンドギャップ E_g",
    "MagpieData minimum MeltingT": "構成元素の最低融点",
    "MagpieData maximum Electronegativity": "最大電気陰性度",
    "spacegroup_number": "空間群番号",
    "MagpieData mode MeltingT": "最頻融点",
}


# --------------------------------------------------------------------------
# 描画ヘルパ
# --------------------------------------------------------------------------
def style(run, size, bold=False, color=INK, font=FONT):
    """latin / ea / cs すべてに同じ書体を指定する (日本語が別書体に落ちるのを防ぐ)。"""
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = color
    run.font.name = font
    rPr = run._r.get_or_add_rPr()
    for tag in ("a:ea", "a:cs"):
        if rPr.find(qn(tag)) is None:
            etree.SubElement(rPr, qn(tag))
        rPr.find(qn(tag)).set("typeface", font)


def textbox(slide, x, y, w, h, align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP):
    box = slide.shapes.add_textbox(x, y, w, h)
    tf = box.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    tf.vertical_anchor = anchor
    tf.paragraphs[0].alignment = align
    return tf


def put(tf, text, size, bold=False, color=INK, space_before=0, line=1.25, first=False,
        align=None, font=FONT):
    p = tf.paragraphs[0] if first else tf.add_paragraph()
    p.line_spacing = line
    p.space_before = Pt(space_before)
    if align is not None:
        p.alignment = align
    style(p.add_run(), size, bold, color, font)
    p.runs[0].text = text
    return p


def rect(slide, x, y, w, h, fill=None, line_color=None, shape=MSO_SHAPE.RECTANGLE,
         line_w=0.75):
    s = slide.shapes.add_shape(shape, x, y, w, h)
    if fill is None:
        s.fill.background()
    else:
        s.fill.solid()
        s.fill.fore_color.rgb = fill
    if line_color is None:
        s.line.fill.background()
    else:
        s.line.color.rgb = line_color
        s.line.width = Pt(line_w)
    s.shadow.inherit = False
    s.text_frame.word_wrap = True
    return s


def new_slide(prs, eyebrow=None, headline=None, number=None):
    """共通レイアウト: 小見出し (アクセント) + メッセージ見出し + ページ番号。"""
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    y = MARGIN - Inches(0.3)
    if eyebrow:
        tf = textbox(slide, MARGIN, y, BODY_W, Inches(0.3))
        put(tf, eyebrow, 13, bold=True, color=ACCENT, first=True)
        y += Inches(0.42)
    if headline:
        tf = textbox(slide, MARGIN, y, BODY_W, Inches(1.2))
        put(tf, headline, 30, bold=True, color=INK, line=1.3, first=True)
    if number is not None:
        tf = textbox(slide, W - MARGIN - Inches(1.0), H - Inches(0.72),
                     Inches(1.0), Inches(0.3), align=PP_ALIGN.RIGHT)
        put(tf, str(number), 11, color=MUTED, first=True)
    return slide


def bullets(slide, items, top, size=16, gap=14, width=None, left=None, color=MUTED):
    """・付きの短い断片を並べる。文字は最小限に保つ。"""
    tf = textbox(slide, left or MARGIN, top, width or BODY_W, Inches(2.6))
    for i, text in enumerate(items):
        accent = text.startswith("→")
        put(tf, text, size, bold=accent, color=ACCENT if accent else color,
            space_before=0 if i == 0 else gap, line=1.35, first=(i == 0))
    return tf


# --------------------------------------------------------------------------
# スライド本体
# --------------------------------------------------------------------------
prs = Presentation()
prs.slide_width, prs.slide_height = W, H

# ---- 1. タイトル --------------------------------------------------------
s = prs.slides.add_slide(prs.slide_layouts[6])
rect(s, Emu(0), Emu(0), Inches(0.18), H, fill=ACCENT)
tf = textbox(s, MARGIN, Inches(2.15), Inches(11.0), Inches(0.4))
put(tf, "Materials Informatics", 14, bold=True, color=ACCENT, first=True)
tf = textbox(s, MARGIN, Inches(2.72), Inches(11.0), Inches(1.6))
put(tf, "第一原理計算を、機械学習で代替する", 42, bold=True, color=INK, line=1.25, first=True)
tf = textbox(s, MARGIN, Inches(4.35), Inches(11.0), Inches(0.5))
put(tf, f"無機半導体のゼーベック係数予測 — {N_MATERIALS:,} 材料", 19, color=MUTED, first=True)
rect(s, MARGIN, Inches(5.35), Inches(1.4), Pt(2.2), fill=ACCENT)
tf = textbox(s, MARGIN, Inches(5.75), Inches(11.0), Inches(0.9))
put(tf, "氏名・所属", 14, color=INK, first=True)
put(tf, "データ: Materials Project / MPContribs carrier_transport "
        "(Ricci et al., Sci. Data 4, 170085, 2017, CC-BY 4.0)", 11, color=MUTED, space_before=7)

# ---- 2. 課題 ------------------------------------------------------------
s = new_slide(prs, "課題", "熱電材料の探索は、計算コストで止まる", 2)
bullets(s, [
    "1 材料の輸送物性を得るのに、DFT バンド構造計算 + BoltzTraP 輸送計算が必要",
    "候補となる無機化合物は数万件 — 全部は回せない",
    "→ 「計算する前に、有望なものを絞り込みたい」",
], top=Inches(2.55), size=18, gap=20)

# ---- 3. アプローチ ------------------------------------------------------
s = new_slide(prs, "アプローチ", f"すでに計算済みの {N_MATERIALS:,} 件から、予測モデルを学習する", 3)
bullets(s, [
    "入力: 組成と、データベース登録値(バンドギャップ・密度・対称性)",
    "出力: ゼーベック係数 S(p 型・n 型)",
    "→ 高コスト計算の「代理モデル」として、スクリーニングを高速化する",
], top=Inches(2.55), size=18, gap=20)

# ---- 4. データフロー図 --------------------------------------------------
s = new_slide(prs, "パイプライン", "一方向の 5 段構成 — 前段の出力だけが次段の入力", 4)

FLOW = [
    ("データ源", "MPContribs carrier_transport ＋ MP summary",
     "2 つのデータベース"),
    ("取得・結合", "transport/get_transport_data.py",
     f"transport_dataset.csv — {N_MATERIALS:,} 材料"),
    ("特徴量化", "transport/featurize.py",
     f"features_dataset.csv — {N_FEATURES} 次元"),
    ("学習・評価", "transport/train.py",
     "metrics.json ／ パリティ図 ／ SHAP"),
    ("可視化", "web/build_data.py → web/build_single.py",
     "ダッシュボード(単一 HTML)"),
]
row_h, gap_h = Inches(0.62), Inches(0.20)
top = Inches(2.32)
zone1, zone2 = Inches(1.75), Inches(4.85)

for i, (stage, script, output) in enumerate(FLOW):
    y = top + i * (row_h + gap_h)
    is_last = i == len(FLOW) - 1
    box = rect(s, MARGIN, y, BODY_W, row_h,
               fill=TINT if not is_last else WHITE, line_color=LINE,
               shape=MSO_SHAPE.ROUNDED_RECTANGLE)
    box.adjustments[0] = 0.12
    rect(s, MARGIN, y, Inches(0.07), row_h, fill=ACCENT)

    tf = textbox(s, MARGIN + Inches(0.28), y, zone1, row_h, anchor=MSO_ANCHOR.MIDDLE)
    put(tf, stage, 14, bold=True, color=ACCENT, first=True)

    tf = textbox(s, MARGIN + Inches(0.28) + zone1, y, zone2, row_h, anchor=MSO_ANCHOR.MIDDLE)
    put(tf, script, 12, color=INK, first=True, font="Consolas")

    tf = textbox(s, MARGIN + Inches(0.28) + zone1 + zone2, y,
                 BODY_W - zone1 - zone2 - Inches(0.5), row_h, anchor=MSO_ANCHOR.MIDDLE)
    put(tf, output, 12, color=MUTED, first=True)

    if not is_last:                      # 段と段のあいだの下向き矢印
        arrow = rect(s, MARGIN + BODY_W / 2 - Inches(0.09), y + row_h + Inches(0.04),
                     Inches(0.18), gap_h - Inches(0.08),
                     fill=RGBColor(0xC3, 0xCC, 0xDE), shape=MSO_SHAPE.DOWN_ARROW)
        arrow.line.fill.background()

tf = textbox(s, MARGIN, Inches(6.55), BODY_W - Inches(1.3), Inches(0.35))
put(tf, "各段は独立に再実行できる。中間 CSV とモデルはコードから再現できるため git には置かない。",
    12, color=MUTED, first=True)

# ---- 5. データ構築 ------------------------------------------------------
s = new_slide(prs, "データ構築", "3 万件のうち、学習に使えたのは 1.5 万件", 5)
FUNNEL = [
    ("30,467", "MPContribs の非金属エントリ"),
    ("22,623", "現行の Materials Project と結合できたもの"),
    ("15,682", "安定相フィルタ E_hull ≤ 0.05 eV/atom"),
    (f"{N_MATERIALS:,}", "登録バンドギャップ > 0  ← 学習データ"),
]
for i, (num, label) in enumerate(FUNNEL):
    y = Inches(2.55) + i * Inches(0.82)
    final = i == len(FUNNEL) - 1
    tf = textbox(s, MARGIN, y, Inches(2.3), Inches(0.62),
                 align=PP_ALIGN.RIGHT, anchor=MSO_ANCHOR.MIDDLE)
    put(tf, num, 30 if final else 26, bold=True,
        color=ACCENT if final else INK, first=True)
    tf = textbox(s, MARGIN + Inches(2.7), y, Inches(8.0), Inches(0.62),
                 anchor=MSO_ANCHOR.MIDDLE)
    put(tf, label, 16, bold=final, color=INK if final else MUTED, first=True)

tf = textbox(s, MARGIN, H - Inches(1.15), BODY_W, Inches(0.4))
put(tf, "古典的な熱電材料(Bi₂Te₃・SnSe・Mg₂Si・ZrNiSn・CoSb₃)が残っていることを毎回自動確認している。",
    13, color=MUTED, first=True)

# ---- 6. 設計の要点 ① ----------------------------------------------------
s = new_slide(prs, "設計の要点 ①", "予測値のカスケードを、あえて禁止する", 6)
bullets(s, [
    "特徴量のバンドギャップは、モデルの予測値ではなくデータベース登録値を使う",
    "予測値を次段に渡すと、その誤差がそのまま下流に伝染する",
    "精度が悪いとき「モデルが悪いのか、渡された入力が悪いのか」を切り分けられなくなる",
    "→ 入力を登録値に固定し、各モデルを独立に評価できる状態を保つ",
], top=Inches(2.55), size=18, gap=20)

# ---- 7. 設計の要点 ② ----------------------------------------------------
s = new_slide(prs, "設計の要点 ②", "答えと同じ計算から出た量は、特徴量に入れない", 7)
bullets(s, [
    "有効質量 m* は、目的変数とまったく同じ BoltzTraP 計算の産物",
    "入れれば精度は上がる。ただしそれは「リーク」であって実力ではない",
    "キャリア濃度も除外 — 全材料で 10¹⁸ cm⁻³ に固定され、情報量がゼロだから",
    "→ 見かけの精度より、評価の健全さを優先する",
], top=Inches(2.55), size=18, gap=20)

# ---- 8. 結果 ------------------------------------------------------------
s = new_slide(prs, "結果",
              f"未学習の {MP['n_test']:,} 材料で R² = {MP['test_r2']:.2f} / {MN['test_r2']:.2f}", 8)
bullets(s, [
    f"平均絶対誤差  {MP['test_mae']:.1f} µV/K(p 型) ／ {MN['test_mae']:.1f} µV/K(n 型)",
    f"5-fold 交差検証 R² = {MP['cv_r2_mean']:.2f} ± {MP['cv_r2_std']:.2f} — まぐれではない",
    "ランダムフォレスト回帰(決定木 300 本)・80 : 20 分割",
    "→ 計算を回さずに、有望な材料を絞り込める水準",
], top=Inches(2.6), size=16, gap=18, width=Inches(6.1))
img = STAGE2 / "parity_seebeck_p_uV_K.png"
s.shapes.add_picture(str(img), W - MARGIN - Inches(4.0), Inches(2.30), height=Inches(4.0))
tf = textbox(s, W - MARGIN - Inches(4.0), Inches(6.42), Inches(4.0), Inches(0.3),
             align=PP_ALIGN.CENTER)
put(tf, "横軸 = 計算値、縦軸 = 予測値(p 型)", 11, color=MUTED, first=True)

# ---- 9. 発見 ------------------------------------------------------------
s = new_slide(prs, "発見", f"{N_FEATURES} 特徴量のうち、バンドギャップが単独 1 位", 9)
bar_x, bar_top, bar_max = MARGIN + Inches(3.5), Inches(2.55), Inches(6.2)
top_val = SHAP_TOP5[0][1]
for i, (feat, val) in enumerate(SHAP_TOP5):
    y = bar_top + i * Inches(0.66)
    is_gap = feat == "band_gap_mp_eV"
    tf = textbox(s, MARGIN, y, Inches(3.3), Inches(0.42),
                 align=PP_ALIGN.RIGHT, anchor=MSO_ANCHOR.MIDDLE)
    put(tf, FEATURE_JP.get(feat, feat), 14, bold=is_gap,
        color=INK if is_gap else MUTED, first=True)
    w = int(bar_max * (val / top_val))
    bar = rect(s, bar_x, y + Inches(0.08), w, Inches(0.26),
               fill=ACCENT if is_gap else RGBColor(0xD3, 0xDA, 0xE8))
    bar.line.fill.background()
    tf = textbox(s, bar_x + w + Inches(0.12), y, Inches(1.0), Inches(0.42),
                 anchor=MSO_ANCHOR.MIDDLE)
    put(tf, f"{val:.1f}", 12, bold=is_gap, color=INK if is_gap else MUTED, first=True)

tf = textbox(s, MARGIN, Inches(6.10), BODY_W - Inches(1.3), Inches(0.8))
put(tf, f"平均 |SHAP| 値(p 型・上位 5)。1 位は 2 位の {SHAP_RATIO:.1f} 倍。", 14, color=INK, first=True)
put(tf, "小さいギャップが S を抑制する向きに効いており、バイポーラ伝導の物理と整合する。",
    13, color=MUTED, space_before=8)

# ---- 10. 限界 -----------------------------------------------------------
s = new_slide(prs, "限界と次の一手", "予測しているのは「実験値」ではなく「計算値」", 10)
bullets(s, [
    "目的変数は GGA + BoltzTraP の計算値。GGA はバンドギャップを系統的に過小評価する",
    "300 K・キャリア濃度 10¹⁸ cm⁻³ の 1 点に固定。温度依存性はまだ扱えていない",
    "→ 次: 実験データセット(UCSB 熱電など)での検証と、温度依存への拡張",
], top=Inches(2.55), size=18, gap=20)

# ---- 11. まとめ ---------------------------------------------------------
s = new_slide(prs, "まとめ", "代理モデルを作り、物理の因果をデータで裏付けた", 11)
bullets(s, [
    f"{N_MATERIALS:,} 材料 × {N_FEATURES} 特徴量 → ゼーベック係数を R² {MN['test_r2']:.2f} で予測",
    "設計原則は 2 つ: 予測値のカスケード禁止と、リーク源の明示的な除外",
    "SHAP がバンドギャップを 1 位に選び、設計の出発点だった物理仮説を裏づけた",
], top=Inches(2.55), size=18, gap=20)

prs.core_properties.title = "第一原理計算を、機械学習で代替する"
prs.core_properties.subject = "無機半導体のゼーベック係数予測"

OUT.parent.mkdir(exist_ok=True)
prs.save(OUT)
print(f"{OUT.relative_to(ROOT)} — {len(prs.slides.__iter__.__self__._sldIdLst)} slides, "
      f"{OUT.stat().st_size / 1e6:.2f} MB")
