"""Bundle the dashboard into one self-contained HTML file (web/dist/).

CSS, JS, data, and parity images are all inlined, so the output runs from a
double-click, an email attachment, or any static host with zero dependencies.
Run `python web/build_data.py` first if the datasets changed.
"""
import base64
import re
from pathlib import Path

WEB = Path(__file__).resolve().parent
OUT = WEB / "dist" / "milab-dashboard.html"
OUT.parent.mkdir(exist_ok=True)

html = (WEB / "index.html").read_text()
css = (WEB / "style.css").read_text()
app = (WEB / "app.js").read_text()
dataset = (WEB / "data/dataset.js").read_text()
results = (WEB / "data/results.js").read_text()

parity = {}
for key, png in {
    "seebeck_p_uV_K": "parity_seebeck_p_uV_K.png",
    "seebeck_n_uV_K": "parity_seebeck_n_uV_K.png",
    "sigma_p_S_m": "parity_sigma_p_S_m.png",
    "sigma_n_S_m": "parity_sigma_n_S_m.png",
}.items():
    b64 = base64.b64encode((WEB / "assets" / png).read_bytes()).decode()
    parity[key] = f"data:image/png;base64,{b64}"
parity_js = "window.MILAB_PARITY=" + \
    "{" + ",".join(f'"{k}":"{v}"' for k, v in parity.items()) + "};"

for name, blob in [("app.js", app), ("dataset.js", dataset), ("results.js", results)]:
    assert "</script" not in blob.lower(), f"unsafe </script> in {name}"

head, body_rest = html.split("<body>", 1)
body = body_rest.rsplit("</body>", 1)[0]
body = re.sub(r'<script src="[^"]+"></script>\n?', "", body)
head = re.sub(r'<link rel="stylesheet"[^>]*>', f"<style>\n{css}</style>", head)

OUT.write_text(
    head + "<body>" + body +
    f"<script>{dataset}</script>\n"
    f"<script>{results}</script>\n"
    f"<script>{parity_js}</script>\n"
    f"<script>\n{app}</script>\n"
    "</body>\n</html>\n"
)
print(f"{OUT.relative_to(WEB.parent)} — {OUT.stat().st_size / 1e6:.2f} MB")
