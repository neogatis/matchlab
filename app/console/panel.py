from __future__ import annotations

import html
from typing import Any

from .service import CONSOLE_SECTIONS


def esc(value: Any) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def render_rows(rows: list[Any]) -> str:
    if not rows:
        return '<div class="empty">Нет данных</div>'
    if not isinstance(rows[0], dict):
        return "<ul>" + "".join(f"<li>{esc(x)}</li>" for x in rows) + "</ul>"
    keys = list(rows[0].keys())
    head = "".join(f"<th>{esc(key)}</th>" for key in keys)
    body = "".join(
        "<tr>" + "".join(f"<td>{esc(row.get(key))}</td>" for key in keys) + "</tr>"
        for row in rows
    )
    return f'<div class="scroll"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


def render_data(data: Any) -> str:
    if isinstance(data, list):
        return render_rows(data)
    if not isinstance(data, dict):
        return f"<p>{esc(data)}</p>"

    chunks: list[str] = []
    metrics = data.get("metrics")
    if isinstance(metrics, dict):
        cards = "".join(
            f'<div class="metric"><span>{esc(key)}</span><b>{esc(value)}</b></div>'
            for key, value in metrics.items()
        )
        chunks.append(f'<div class="metrics">{cards}</div>')

    for key, value in data.items():
        if key == "metrics":
            continue
        chunks.append(f"<h3>{esc(key)}</h3>")
        if isinstance(value, list):
            chunks.append(render_rows(value))
        elif isinstance(value, dict):
            rows = [{"Показатель": k, "Значение": v} for k, v in value.items()]
            chunks.append(render_rows(rows))
        else:
            chunks.append(f"<p>{esc(value)}</p>")
    return "".join(chunks)


def render_console_page(*, active_section: str, data: Any) -> str:
    if active_section not in CONSOLE_SECTIONS:
        active_section = "Dashboard"

    nav = "".join(
        f'<a class="nav{" active" if section == active_section else ""}" '
        f'href="?section={esc(section)}">{esc(section)}</a>'
        for section in CONSOLE_SECTIONS
    )
    content = render_data(data)

    return f"""<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>MatchLab Console · {esc(active_section)}</title>
<style>
:root{{--bg:#171514;--side:#1c1918;--card:#24201f;--soft:#2c2725;--line:#4a403c;--text:#f6f0e9;--muted:#b9aaa1;--accent:#a98aee}}
*{{box-sizing:border-box}} body{{margin:0;background:var(--bg);color:var(--text);font-family:Inter,system-ui,sans-serif}}
.shell{{min-height:100vh;display:grid;grid-template-columns:260px minmax(0,1fr)}}
aside{{background:var(--side);border-right:1px solid var(--line);padding:22px 14px;position:sticky;top:0;height:100vh;overflow:auto}}
.brand{{font-size:22px;font-weight:800;padding:6px 10px 20px}} .brand em{{color:var(--accent);font-style:normal}}
nav{{display:grid;gap:6px}} .nav{{padding:11px 12px;border-radius:12px;color:var(--muted);text-decoration:none}}
.nav:hover,.nav.active{{background:var(--soft);color:var(--text)}}
main{{padding:28px;min-width:0}} h1{{margin:0 0 20px;font-size:28px}} h3{{margin:28px 0 10px}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:20px;padding:20px;overflow:hidden}}
.metrics{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px}}
.metric{{background:var(--soft);border:1px solid #514641;border-radius:15px;padding:14px}}
.metric span{{display:block;color:var(--muted);font-size:12px;overflow-wrap:anywhere}}
.metric b{{display:block;font-size:26px;margin-top:7px}}
.scroll{{overflow:auto}} table{{width:100%;border-collapse:collapse;font-size:14px}}
th,td{{padding:10px 12px;border-bottom:1px solid #403735;text-align:left;white-space:nowrap}}
th{{color:#d8cbc3}} .empty{{color:var(--muted);padding:25px;text-align:center}}
@media(max-width:900px){{.shell{{grid-template-columns:1fr}}aside{{position:static;height:auto;border-right:0;border-bottom:1px solid var(--line)}}nav{{grid-template-columns:repeat(2,minmax(0,1fr))}}.metrics{{grid-template-columns:repeat(2,minmax(0,1fr))}}}}
@media(max-width:560px){{main{{padding:16px}}nav,.metrics{{grid-template-columns:1fr}}}}
</style>
</head>
<body>
<div class="shell">
<aside><div class="brand">Match<em>Lab</em> Console</div><nav>{nav}</nav></aside>
<main><h1>{esc(active_section)}</h1><section class="card">{content}</section></main>
</div>
</body>
</html>"""
