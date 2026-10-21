"""docs/explain/*.md を 1 枚の HTML (docs/explain/index.html) に変換する。

    python docs/explain/build_html.py                 # -> docs/explain/index.html
    python docs/explain/build_html.py --fragment PATH # 殻(doctype/head/body)無しの断片も出力

数式は MathJax (cdnjs)、mermaid 図は mermaid.js (cdnjs) をブラウザ側で読み込んで描画する。
[[用語]] は 90_glossary の見出しへ、ファイル名:行番号 は GitHub の該当行へリンクする。
"""
import datetime
import html
import re
import sys
from pathlib import Path

import markdown

HERE = Path(__file__).resolve().parent
OUT = HERE / "index.html"
GH = "https://github.com/Kaimon0726/Kaimon-s-Materials-Project/blob/main/"
FRAGMENT = None
if "--fragment" in sys.argv:
    i = sys.argv.index("--fragment")
    if i + 1 >= len(sys.argv):
        sys.exit("--fragment には出力パスが必要です")
    FRAGMENT = Path(sys.argv[i + 1]).expanduser()

GROUPS = [
    ("検証", ["00_verify"]),
    ("ファイル解説(実行順)", ["01_get_data", "02_get_transport_data", "03_featurize",
                       "04_train", "05_build_data", "06_build_single", "07_app"]),
    ("付録", ["90_glossary", "91_design_decisions", "92_audit"]),
]
SOURCE = {
    "01_get_data": "get_data.py",
    "02_get_transport_data": "transport/get_transport_data.py",
    "03_featurize": "transport/featurize.py",
    "04_train": "transport/train.py",
    "05_build_data": "web/build_data.py",
    "06_build_single": "web/build_single.py",
    "07_app": "web/app.js",
}
# ファイル名:行番号 → リポジトリ内パス
PATHMAP = {
    "get_data.py": "get_data.py",
    "get_transport_data.py": "transport/get_transport_data.py",
    "featurize.py": "transport/featurize.py",
    "train.py": "transport/train.py",
    "build_data.py": "web/build_data.py",
    "build_single.py": "web/build_single.py",
    "app.js": "web/app.js",
    "index.html": "web/index.html",
    "style.css": "web/style.css",
    "README.md": "README.md",
    "DATA_SOURCES.md": "docs/DATA_SOURCES.md",
    "REPO_GUIDE.md": "docs/REPO_GUIDE.md",
    ".gitignore": ".gitignore",
}
REF_RE = re.compile(
    r"(?<![\w/#-])((?:[\w.-]+/)*)(" + "|".join(re.escape(k) for k in PATHMAP) + r"):(\d+)(?:[-–](\d+))?"
)


def slug(term: str) -> str:
    return "g-" + re.sub(r"[\s/]+", "-", term.strip())


def protect(text: str, store: list) -> str:
    """数式と [[wikilink]] を placeholder に退避する(markdown 変換で壊れないように)。"""
    def keep(payload):
        store.append(payload)
        return f"PHX{len(store) - 1}XPH"
    text = re.sub(r"\$\$(.+?)\$\$", lambda m: keep(html.escape("$$" + m.group(1) + "$$")), text, flags=re.S)
    text = re.sub(r"\$([^$\n]+?)\$", lambda m: keep(html.escape("$" + m.group(1) + "$")), text)
    text = re.sub(r"\[\[([^\]]+)\]\]",
                  lambda m: keep(f'<a class="wl" href="#{slug(m.group(1))}">{html.escape(m.group(1))}</a>'),
                  text)
    return text


def restore(htmltext: str, store: list) -> str:
    return re.sub(r"PHX(\d+)XPH", lambda m: store[int(m.group(1))], htmltext)


def linkify_refs(htmltext: str) -> str:
    def rep(m):
        prefix, name, a, b = m.groups()
        path = PATHMAP[name]
        # 明示パスがリポジトリ内パスと矛盾する場合はそのまま(リンクしない)
        if prefix and not path.endswith(prefix + name):
            return m.group(0)
        frag = f"#L{a}" + (f"-L{b}" if b else "")
        return f'<a class="ref" href="{GH}{path}{frag}" target="_blank" rel="noopener">{m.group(0)}</a>'
    return REF_RE.sub(rep, htmltext)


VERDICT = {
    "一致": "ok", "相違": "diff",
    "図にあるがコードに無い": "fig", "コードにあるが図に無い": "code",
    "コードにあるが図に無い(範囲外)": "code",
}


def badge_cells(htmltext: str) -> str:
    def rep(m):
        inner = re.sub(r"</?strong>", "", m.group(1)).strip()
        cls = VERDICT.get(inner)
        return f'<td><span class="v v-{cls}">{inner}</span></td>' if cls else m.group(0)
    return re.sub(r"<td>((?:<strong>)?[^<]{1,20}(?:</strong>)?)</td>", rep, htmltext)


def callouts(htmltext: str) -> str:
    def rep(m):
        lead = m.group(1)
        cls = "warn" if lead.startswith("指摘あり") else "ok" if lead.startswith("該当なし") else "note"
        return f'<p class="callout {cls}"><strong>{lead}</strong>'
    return re.sub(r"<p><strong>([^<]+)</strong>", rep, htmltext)


def build_doc(key: str):
    src = (HERE / f"{key}.md").read_text(encoding="utf-8")
    lines = src.split("\n")
    assert lines[0].startswith("# "), key
    m = re.match(r"# (\d\d)(?:_\w+)? — (.*)", lines[0])
    num, title = m.group(1), m.group(2)
    body = "\n".join(lines[1:])
    body = re.sub(r"\]\((\d\d_[\w]+)\.md\)", r"](#doc-\1)", body)  # 相互リンク

    store = []
    md = markdown.Markdown(extensions=["tables", "fenced_code", "sane_lists"])
    out = md.convert(protect(body, store))
    out = restore(out, store)

    # 見出しに id を付与し、サイドバー用に収集
    heads = []
    counter = [0]
    def head_rep(mm):
        level, inner = mm.group(1), mm.group(2)
        text = re.sub(r"<[^>]+>", "", inner)
        if key == "90_glossary" and level == "3":
            hid = slug(html.unescape(text))
        else:
            counter[0] += 1
            hid = f"{key}-h{counter[0]}"
        heads.append((int(level), text, hid))
        return f'<h{level} id="{hid}">{inner}</h{level}>'
    out = re.sub(r"<h([23])>(.*?)</h\1>", head_rep, out, flags=re.S)

    out = re.sub(r'<pre><code class="language-mermaid">(.*?)</code></pre>',
                 r'<pre class="mermaid">\1</pre>', out, flags=re.S)
    out = out.replace("<table>", '<div class="tbl"><table>').replace("</table>", "</table></div>")
    out = badge_cells(out)
    if key == "92_audit":
        out = callouts(out)
    out = linkify_refs(out)

    short = re.split(r"[(（]", title)[0].strip()
    src_path = SOURCE.get(key)
    chip = (f'<a class="src" href="{GH}{src_path}" target="_blank" rel="noopener">{src_path}</a>'
            if src_path else "")
    article = (
        f'<article class="doc" id="doc-{key}">\n'
        f'<header class="doc-head"><span class="doc-num">{num}</span>'
        f'<h1>{html.escape(title)}</h1>{chip}</header>\n'
        f'{out}\n</article>\n'
    )
    return {"key": key, "num": num, "title": title, "short": short, "heads": heads, "html": article}


docs = {k: build_doc(k) for _, keys in GROUPS for k in keys}

# ---- サイドバー ----
nav = []
for label, keys in GROUPS:
    nav.append(f'<div class="nav-group"><div class="nav-label">{label}</div><ol class="nav-docs">')
    for k in keys:
        d = docs[k]
        sub = "".join(
            f'<li class="l{lv}"><a href="#{hid}">{html.escape(html.unescape(t))}</a></li>'
            for lv, t, hid in d["heads"]
        )
        nav.append(
            f'<li data-doc="doc-{k}"><a href="#doc-{k}"><span class="n">{d["num"]}</span>'
            f'<span>{html.escape(d["short"])}</span></a>'
            f'{f"<ol class=\"nav-sub\">{sub}</ol>" if sub else ""}</li>'
        )
    nav.append("</ol></div>")
NAV = "\n".join(nav)
BODY = "\n".join(docs[k]["html"] for _, keys in GROUPS for k in keys)
TODAY = datetime.date.today().isoformat()

CSS = r"""
:root{
  --ground:#F3F7F8; --panel:#FFFFFF; --panel-2:#EAF2F4; --line:#CFDFE4; --line-soft:#E3EDF0;
  --ink:#0B1F26; --ink-2:#3E5A64; --ink-3:#6C8791;
  --accent:#0075A6; --accent-wash:rgba(0,117,166,.10); --accent-line:rgba(0,117,166,.38);
  --ok:#1B7F4A; --ok-wash:rgba(27,127,74,.12);
  --bad:#B23A2E; --bad-wash:rgba(178,58,46,.12);
  --warn:#8A5A00; --warn-wash:rgba(138,90,0,.13);
  --code-bg:#EAF1F3;
  --sans:"BIZ UDPGothic","Hiragino Sans","Hiragino Kaku Gothic ProN","Yu Gothic","Noto Sans JP",sans-serif;
  --head:"Zen Kaku Gothic New","Hiragino Sans","Hiragino Kaku Gothic ProN","Noto Sans JP",sans-serif;
  --mono:"IBM Plex Mono",ui-monospace,"SF Mono",Menlo,Consolas,monospace;
  color-scheme:light;
}
@media (prefers-color-scheme:dark){
  :root:not([data-theme="light"]){
    --ground:#0C171B; --panel:#12222A; --panel-2:#182D36; --line:#274550; --line-soft:#1E3841;
    --ink:#E4EEF1; --ink-2:#A9C0C8; --ink-3:#7E97A0;
    --accent:#5CC6F0; --accent-wash:rgba(92,198,240,.14); --accent-line:rgba(92,198,240,.45);
    --ok:#5FCB8E; --ok-wash:rgba(95,203,142,.16);
    --bad:#F08A7E; --bad-wash:rgba(240,138,126,.16);
    --warn:#E6B34D; --warn-wash:rgba(230,179,77,.16);
    --code-bg:#182D36; color-scheme:dark;
  }
}
:root[data-theme="dark"]{
  --ground:#0C171B; --panel:#12222A; --panel-2:#182D36; --line:#274550; --line-soft:#1E3841;
  --ink:#E4EEF1; --ink-2:#A9C0C8; --ink-3:#7E97A0;
  --accent:#5CC6F0; --accent-wash:rgba(92,198,240,.14); --accent-line:rgba(92,198,240,.45);
  --ok:#5FCB8E; --ok-wash:rgba(95,203,142,.16);
  --bad:#F08A7E; --bad-wash:rgba(240,138,126,.16);
  --warn:#E6B34D; --warn-wash:rgba(230,179,77,.16);
  --code-bg:#182D36; color-scheme:dark;
}
*{box-sizing:border-box}
html{scroll-behavior:smooth;scroll-padding-top:24px}
@media (prefers-reduced-motion:reduce){html{scroll-behavior:auto}}
body{margin:0;background:var(--ground);color:var(--ink);font:16px/1.9 var(--sans);
  -webkit-font-smoothing:antialiased;font-feature-settings:"palt";}
a{color:var(--accent);text-decoration:underline;text-decoration-color:var(--accent-line);text-underline-offset:3px}
a:hover{text-decoration-color:currentColor}
a:focus-visible,summary:focus-visible{outline:2px solid var(--accent);outline-offset:2px;border-radius:3px}
.shell{display:grid;grid-template-columns:276px minmax(0,1fr);max-width:1220px;margin:0 auto;padding-inline:16px}

/* ---- sidebar ---- */
.side{position:sticky;top:env(safe-area-inset-top,0px);align-self:start;height:100vh;overflow:auto;
  padding-block:28px 40px;padding-right:22px;border-right:1px solid var(--line);font-size:13.5px;line-height:1.5;
  scrollbar-width:thin}
.side summary{display:none}
.brand{font-family:var(--head);font-weight:700;font-size:17px;letter-spacing:.01em;color:var(--ink);margin:0 0 4px}
.brand-sub{font-family:var(--mono);font-size:11px;color:var(--ink-3);margin:0 0 22px;line-height:1.5}
.nav-group{margin-bottom:18px}
.nav-label{font-family:var(--mono);font-size:10.5px;letter-spacing:.09em;text-transform:uppercase;color:var(--ink-3);
  padding:0 8px;margin-bottom:6px}
.nav-docs,.nav-sub{list-style:none;margin:0;padding:0}
.nav-docs>li>a{display:flex;gap:10px;align-items:baseline;padding:5px 8px;border-radius:5px;color:var(--ink-2);text-decoration:none}
.nav-docs>li>a:hover{background:var(--panel-2);color:var(--ink)}
.nav-docs>li.active>a{background:var(--accent-wash);color:var(--accent);font-weight:700}
.nav-docs .n{font-family:var(--mono);font-size:11.5px;color:var(--ink-3);min-width:1.7em;font-variant-numeric:tabular-nums}
.nav-docs>li.active>a .n{color:var(--accent)}
.nav-sub{display:none;margin:2px 0 8px 0;padding-left:8px;border-left:1px solid var(--line-soft);margin-left:14px}
.nav-docs>li.active>.nav-sub{display:block}
.nav-sub li a{display:block;padding:3px 10px;color:var(--ink-3);text-decoration:none;font-size:12.5px;line-height:1.45;
  overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.nav-sub li.l3 a{padding-left:20px}
.nav-sub li a:hover{color:var(--ink)}
.nav-sub li.active a{color:var(--accent);font-weight:700}
.side-foot{margin-top:26px;padding-top:14px;border-top:1px solid var(--line-soft);font-size:12px;color:var(--ink-3);line-height:1.7}

/* ---- main ---- */
main{padding-block:28px 120px;padding-left:44px;max-width:860px;min-width:0}
.page-head{padding-bottom:22px;border-bottom:1px solid var(--line);margin-bottom:6px}
.page-head h1{font:700 30px/1.3 var(--head);margin:0 0 8px;text-wrap:balance;letter-spacing:.005em}
.page-head p{margin:0;color:var(--ink-2);max-width:62ch}
.page-head .meta{font-family:var(--mono);font-size:12px;color:var(--ink-3);margin-top:10px}

.doc{padding-block:56px 12px;border-top:1px solid var(--line)}
.doc:first-of-type{border-top:0;padding-top:40px}
.doc-head{display:flex;flex-wrap:wrap;align-items:baseline;gap:8px 14px;margin-bottom:22px}
.doc-num{font-family:var(--mono);font-size:13px;color:var(--accent);letter-spacing:.06em;font-variant-numeric:tabular-nums}
.doc-head h1{font:700 25px/1.35 var(--head);margin:0;flex:1 1 100%;text-wrap:balance;letter-spacing:.005em}
.src{font-family:var(--mono);font-size:12.5px;text-decoration:none;color:var(--ink-2);background:var(--panel-2);
  border:1px solid var(--line);border-radius:5px;padding:3px 9px}
.src:hover{color:var(--accent);border-color:var(--accent-line)}
.doc h2{font:700 20px/1.4 var(--head);margin:2.4em 0 .7em;text-wrap:balance}
.doc h3{font:700 17px/1.45 var(--head);margin:2.1em 0 .6em;padding-left:12px;border-left:3px solid var(--accent-line);text-wrap:balance}
.doc h2+h3{margin-top:1.2em}
.doc p{margin:0 0 1.1em;max-width:72ch}
.doc ul,.doc ol{padding-left:1.5em;margin:0 0 1.1em;max-width:72ch}
.doc li{margin-bottom:.35em}
.doc li>p{margin-bottom:.4em}
.doc strong{font-weight:700}
code{font-family:var(--mono);font-size:.86em;background:var(--code-bg);padding:.12em .38em;border-radius:4px;word-break:break-all}
pre{margin:1.2em 0;background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:14px 16px;overflow-x:auto;
  font-family:var(--mono);font-size:13px;line-height:1.6}
pre code{background:none;padding:0;font-size:inherit}
pre.mermaid{text-align:center;padding:20px 12px;line-height:1.4}
pre.mermaid svg{max-width:100%;height:auto}
.wl{color:inherit;text-decoration:none;border-bottom:1px dashed var(--accent-line)}
.wl:hover{color:var(--accent);border-bottom-style:solid}
.ref{font-family:var(--mono);font-size:.9em;text-decoration:none;border-bottom:1px dotted var(--accent-line)}
.ref:hover{border-bottom-style:solid}
code .ref{font-size:inherit}
.tbl{overflow-x:auto;margin:1.2em 0 1.5em;border:1px solid var(--line);border-radius:7px;background:var(--panel)}
table{border-collapse:collapse;width:100%;font-size:14px;line-height:1.65}
th{text-align:left;font-weight:700;background:var(--panel-2);padding:9px 12px;border-bottom:1px solid var(--line);
  white-space:nowrap;color:var(--ink-2);font-size:13px}
td{padding:9px 12px;border-bottom:1px solid var(--line-soft);vertical-align:top;min-width:7em}
tr:last-child td{border-bottom:0}
td:first-child{font-weight:700;color:var(--ink-2)}
.v{display:inline-block;font:700 12px/1 var(--sans);padding:5px 8px;border-radius:4px;white-space:nowrap;letter-spacing:.02em}
.v-ok{color:var(--ok);background:var(--ok-wash)}
.v-diff{color:var(--bad);background:var(--bad-wash)}
.v-fig{color:var(--warn);background:var(--warn-wash)}
.v-code{color:var(--accent);background:var(--accent-wash)}
.callout{border-left:3px solid var(--accent);background:var(--accent-wash);padding:10px 14px;border-radius:0 6px 6px 0}
.callout.warn{border-color:var(--bad);background:var(--bad-wash)}
.callout.ok{border-color:var(--ok);background:var(--ok-wash)}
mjx-container[display="true"]{overflow-x:auto;overflow-y:hidden;margin:1em 0 !important;padding:2px 0}
hr{border:0;border-top:1px solid var(--line);margin:2em 0}

@media (max-width:900px){
  .shell{grid-template-columns:1fr}
  .side{position:static;height:auto;border-right:0;border-bottom:1px solid var(--line);padding:16px 0 12px}
  .side summary{display:block;cursor:pointer;font-family:var(--head);font-weight:700;font-size:15px;list-style:none;padding:6px 0}
  .side summary::before{content:"目次 ";}
  .side summary::-webkit-details-marker{display:none}
  .side details[open] summary{margin-bottom:12px}
  .brand,.brand-sub{display:none}
  main{padding-left:0;padding-top:12px}
  .page-head h1{font-size:25px}
  .doc-head h1{font-size:22px}
  body{font-size:15.5px}
}
@media print{
  .side{display:none}.shell{display:block}main{max-width:none;padding:0}
  .doc{break-before:page}.doc:first-of-type{break-before:auto}
  a{color:inherit}
}
"""

HEAD_LINKS = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">\n'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n'
    '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=BIZ+UDPGothic:wght@400;700'
    '&family=Zen+Kaku+Gothic+New:wght@500;700&family=IBM+Plex+Mono:wght@400;500&display=swap">\n'
)

MATHJAX = """<script>
window.MathJax={tex:{inlineMath:[['$','$']],displayMath:[['$$','$$']],processEscapes:true},
  svg:{fontCache:'global'},options:{skipHtmlTags:['script','noscript','style','textarea','pre','code']}};
</script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/mathjax/3.2.2/es5/tex-svg.js" async></script>
"""
MERMAID = """<script src="https://cdnjs.cloudflare.com/ajax/libs/mermaid/10.9.1/mermaid.min.js"></script>
<script>
mermaid.initialize({startOnLoad:true,securityLevel:'loose',
  theme:matchMedia('(prefers-color-scheme: dark)').matches?'dark':'neutral',
  flowchart:{htmlLabels:true,curve:'basis'}});
</script>
"""
APP_JS = """<script>
(function(){
  var side=document.querySelector('.side details');
  var mq=matchMedia('(min-width:901px)');
  function sync(){ if(mq.matches) side.open=true; }
  sync(); mq.addEventListener('change',sync);

  var docs=[].slice.call(document.querySelectorAll('article.doc'));
  var heads=[].slice.call(document.querySelectorAll('article.doc h2[id],article.doc h3[id]'));
  var navDoc={}, navHead={};
  document.querySelectorAll('.nav-docs>li').forEach(function(li){navDoc[li.dataset.doc]=li;});
  document.querySelectorAll('.nav-sub li a').forEach(function(a){navHead[a.getAttribute('href').slice(1)]=a.parentNode;});
  var ticking=false;
  function update(){
    ticking=false;
    var y=120, curDoc=docs[0], curHead=null;
    for(var i=0;i<docs.length;i++){ if(docs[i].getBoundingClientRect().top<=y) curDoc=docs[i]; }
    for(var j=0;j<heads.length;j++){ var h=heads[j]; if(h.getBoundingClientRect().top<=y && curDoc.contains(h)) curHead=h; }
    Object.keys(navDoc).forEach(function(k){navDoc[k].classList.toggle('active',k===curDoc.id);});
    Object.keys(navHead).forEach(function(k){navHead[k].classList.toggle('active',!!curHead&&k===curHead.id);});
    if(curHead&&navHead[curHead.id]&&mq.matches){
      var el=navHead[curHead.id], box=el.closest('.side'), r=el.getBoundingClientRect(), b=box.getBoundingClientRect();
      if(r.top<b.top+40||r.bottom>b.bottom-40) el.scrollIntoView({block:'center'});
    }
  }
  function onScroll(){ if(!ticking){ ticking=true; requestAnimationFrame(update);} }
  addEventListener('scroll',onScroll,{passive:true}); addEventListener('resize',onScroll);
  update();
  // 同一ページ内リンクは閲覧中のドキュメントを開いてから移動
  if(!mq.matches) document.querySelectorAll('.side a').forEach(function(a){a.addEventListener('click',function(){side.open=false;});});
})();
</script>
"""

TITLE = "mi-project 解説書"
DESC = ("バンドギャップ → ゼーベック係数 → 電気伝導率 予測パイプラインの引き継ぎ資料。"
        "アーキテクチャ図の検証、ソースファイルごとの解説、用語集、設計判断、実装監査。")

PAGE = (
    HEAD_LINKS + f"<style>{CSS}</style>\n"
    '<div class="shell">\n'
    '<nav class="side" aria-label="目次"><details>\n<summary></summary>\n'
    f'<p class="brand">{TITLE}</p>\n'
    '<p class="brand-sub">docs/explain/*.md<br>生成 __TODAY__</p>\n'
    f"{NAV}\n"
    '<div class="side-foot">'
    f'<a href="{GH.replace("/blob/main/", "")}" target="_blank" rel="noopener">GitHub リポジトリ</a><br>'
    '数式: MathJax / 図: mermaid(要ネット接続)</div>\n'
    "</details></nav>\n"
    "<main>\n"
    f'<header class="page-head"><h1>{TITLE}</h1><p>{DESC}</p>'
    '<p class="meta">作業ツリー commit 8a6c36a 基準 · 行番号リンクは GitHub main ブランチの該当行を開く</p></header>\n'
    f"{BODY}\n"
    "</main>\n</div>\n"
    + MATHJAX + APP_JS
).replace("__TODAY__", TODAY)

full = (
    "<!DOCTYPE html>\n<html lang=\"ja\">\n<head>\n<meta charset=\"utf-8\">\n"
    '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
    f"<title>{TITLE}</title>\n</head>\n<body>\n"
    + PAGE.replace(APP_JS, MERMAID + APP_JS)
    + "</body>\n</html>\n"
)
OUT.write_text(full, encoding="utf-8")
print(f"{OUT.relative_to(HERE.parent.parent)} — {OUT.stat().st_size / 1e3:.0f} kB")

if FRAGMENT:
    FRAGMENT.write_text(f"<title>{TITLE}</title>\n" + PAGE, encoding="utf-8")
    print(f"{FRAGMENT} — {FRAGMENT.stat().st_size / 1e3:.0f} kB")
