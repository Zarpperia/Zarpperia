#!/usr/bin/env python3
"""Generate a responsive SVG of the last 31 days of public GitHub contributions."""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from datetime import date, datetime, time, timedelta, timezone
from html import escape
from pathlib import Path

USERNAME = os.environ.get("GITHUB_USERNAME", "Zarpperia")
TOKEN = os.environ.get("GITHUB_TOKEN")
OUT = Path("assets/contribution-activity.svg")
API_URL = "https://api.github.com/graphql"

QUERY = """
query ContributionCalendar($login: String!, $from: DateTime!, $to: DateTime!) {
  user(login: $login) {
    contributionsCollection(from: $from, to: $to) {
      contributionCalendar {
        totalContributions
        weeks {
          contributionDays {
            date
            contributionCount
          }
        }
      }
    }
  }
}
"""


def fetch_days(today: date) -> tuple[list[dict[str, int | str]], int]:
    if not TOKEN:
        raise RuntimeError("GITHUB_TOKEN não foi definido. Execute pelo workflow do GitHub Actions.")

    start = datetime.combine(today - timedelta(days=30), time.min, tzinfo=timezone.utc)
    end = datetime.combine(today + timedelta(days=1), time.min, tzinfo=timezone.utc)
    payload = {
        "query": QUERY,
        "variables": {
            "login": USERNAME,
            "from": start.isoformat().replace("+00:00", "Z"),
            "to": end.isoformat().replace("+00:00", "Z"),
        },
    }
    request = urllib.request.Request(
        API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "Zarpperia-Profile-Activity-Graph",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = json.load(response)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:600]
        raise RuntimeError(f"GitHub GraphQL respondeu HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Não foi possível acessar a API do GitHub: {exc.reason}") from exc

    if body.get("errors"):
        messages = "; ".join(str(item.get("message", "erro GraphQL")) for item in body["errors"])
        raise RuntimeError(f"A consulta de contribuições falhou: {messages}")

    user = (body.get("data") or {}).get("user")
    if not user:
        raise RuntimeError(f"O GitHub não retornou o usuário {USERNAME!r}.")
    calendar = user["contributionsCollection"]["contributionCalendar"]
    days = [day for week in calendar["weeks"] for day in week["contributionDays"]]
    by_date = {str(item["date"]): int(item["contributionCount"]) for item in days}
    rows = [
        {"date": (today - timedelta(days=offset)).isoformat(),
         "count": by_date.get((today - timedelta(days=offset)).isoformat(), 0)}
        for offset in range(30, -1, -1)
    ]
    return rows, int(calendar.get("totalContributions", sum(int(r["count"]) for r in rows)))


def make_svg(rows: list[dict[str, int | str]], total: int, today: date) -> str:
    width, height = 1200, 340
    left, right = 76, 1144
    chart_top, chart_bottom = 112, 257
    counts = [int(row["count"]) for row in rows]
    max_count = max(counts, default=0)
    scale_max = max(4, ((max_count + 3) // 4) * 4)
    dx = (right - left) / max(1, len(rows) - 1)

    pts: list[tuple[float, float]] = []
    for index, count in enumerate(counts):
        x = left + index * dx
        y = chart_bottom - (count / scale_max) * (chart_bottom - chart_top)
        pts.append((x, y))
    line_path = "M " + " L ".join(f"{x:.2f},{y:.2f}" for x, y in pts)
    area_path = f"{line_path} L {right:.2f},{chart_bottom} L {left:.2f},{chart_bottom} Z"

    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<svg xmlns="http://www.w3.org/2000/svg" width="100%" viewBox="0 0 1200 340" role="img" aria-labelledby="graph-title graph-desc">',
        '<title id="graph-title">Atividade de contribuições do GitHub — Zarpperia</title>',
        f'<desc id="graph-desc">{total} contribuições no período consultado; gráfico diário dos últimos 31 dias exibidos no perfil público.</desc>',
        '<defs>',
        '<linearGradient id="area" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="#44E0A1" stop-opacity="0.34"/><stop offset="100%" stop-color="#55D6FF" stop-opacity="0.015"/></linearGradient>',
        '<linearGradient id="line" x1="0" y1="0" x2="1" y2="0"><stop offset="0%" stop-color="#55D6FF"/><stop offset="100%" stop-color="#44E0A1"/></linearGradient>',
        '<filter id="glow" x="-30%" y="-30%" width="160%" height="160%"><feGaussianBlur stdDeviation="3.2" result="blur"/><feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge></filter>',
        '</defs>',
        '<rect width="1200" height="340" rx="20" fill="#0B1020"/>',
        '<rect x="1" y="1" width="1198" height="338" rx="19" fill="none" stroke="#1C3554" stroke-width="2"/>',
        '<circle cx="30" cy="31" r="5" fill="#44E0A1"/><circle cx="48" cy="31" r="5" fill="#55D6FF"/>',
        '<text x="68" y="38" font-family="Segoe UI,Arial,sans-serif" font-size="18" font-weight="700" letter-spacing="1.2" fill="#E6F1FF">ATIVIDADE DE CONTRIBUIÇÕES</text>',
        '<text x="68" y="62" font-family="Segoe UI,Arial,sans-serif" font-size="12" fill="#91A4BE">ÚLTIMOS 31 DIAS · DADOS DO GITHUB</text>',
        f'<text x="1142" y="39" text-anchor="end" font-family="Segoe UI,Arial,sans-serif" font-size="25" font-weight="700" fill="#55D6FF">{total}</text>',
        '<text x="1142" y="61" text-anchor="end" font-family="Segoe UI,Arial,sans-serif" font-size="11" fill="#91A4BE">TOTAL NO PERÍODO CONSULTADO</text>',
    ]

    for tick in (0, scale_max / 2, scale_max):
        y = chart_bottom - (tick / scale_max) * (chart_bottom - chart_top)
        label = str(int(tick))
        parts.append(f'<line x1="{left}" y1="{y:.2f}" x2="{right}" y2="{y:.2f}" stroke="#20304A" stroke-width="1" stroke-dasharray="4 7"/>')
        parts.append(f'<text x="{left-16}" y="{y+4:.2f}" text-anchor="end" font-family="Segoe UI,Arial,sans-serif" font-size="11" fill="#7186A4">{label}</text>')

    parts.append(f'<path d="{area_path}" fill="url(#area)"/>')
    parts.append(f'<path d="{line_path}" fill="none" stroke="url(#line)" stroke-width="3.5" stroke-linecap="round" stroke-linejoin="round" filter="url(#glow)"/>')
    for index, (x, y) in enumerate(pts):
        r = 4.0 if index == len(pts) - 1 else 2.1
        fill = "#44E0A1" if index == len(pts) - 1 else "#55D6FF"
        opacity = "1" if index == len(pts) - 1 else "0.76"
        parts.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{r}" fill="{fill}" opacity="{opacity}"/>')

    label_indices = sorted(set(list(range(0, len(rows), 5)) + [len(rows) - 1]))
    for index in label_indices:
        x = pts[index][0]
        day = date.fromisoformat(str(rows[index]["date"]))
        label = day.strftime("%d/%m")
        parts.append(f'<text x="{x:.2f}" y="286" text-anchor="middle" font-family="Segoe UI,Arial,sans-serif" font-size="11" fill="#91A4BE">{escape(label)}</text>')

    parts += [
        '<line x1="68" y1="304" x2="1132" y2="304" stroke="#1C3554"/>',
        f'<text x="68" y="324" font-family="Segoe UI,Arial,sans-serif" font-size="11" fill="#7186A4">@{escape(USERNAME)} · ATUALIZADO {today.strftime("%d/%m/%Y")}</text>',
        '<text x="1132" y="324" text-anchor="end" font-family="Segoe UI,Arial,sans-serif" font-size="11" fill="#44E0A1">ZARPPERRIA / ACTIVITY MONITOR</text>',
        '</svg>',
    ]
    return "\n".join(parts) + "\n"


def main() -> int:
    today = datetime.now(timezone.utc).date()
    rows, total = fetch_days(today)
    svg = make_svg(rows, total, today)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(svg, encoding="utf-8", newline="\n")
    print(f"Gráfico gerado: {OUT} ({len(rows)} dias; total consultado={total}).")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # helpful CI error, never disclose token
        print(f"ERRO ao gerar gráfico de contribuições: {exc}", file=sys.stderr)
        raise SystemExit(1)
