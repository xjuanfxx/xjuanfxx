"""Render the profile's stat cards (assets/activity.svg, assets/languages.svg).

Reads public data from the GitHub GraphQL API, so the cards never depend on a
third-party image service. Needs a token in GITHUB_TOKEN (the workflow's own
token is enough). Usage: python scripts/cards.py [username]
"""

import datetime as dt
import json
import os
import sys
import urllib.request
from html import escape
from pathlib import Path

USER = sys.argv[1] if len(sys.argv) > 1 else "xjuanfxx"
OUT = Path(__file__).resolve().parent.parent / "assets"

BG, PANEL, LINE = "#14151D", "#1A1B26", "#262838"
INK, MUTED = "#F5F2EA", "#8C8FA6"
LIME, VIOLET = "#B8FF2E", "#7B5CFF"
SANS = "'Segoe UI', Ubuntu, 'Helvetica Neue', Arial, sans-serif"
MONO = "'JetBrains Mono', 'Cascadia Code', Consolas, 'Courier New', monospace"


def gql(query, **variables):
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query, "variables": variables}).encode(),
        headers={"Authorization": f"bearer {os.environ['GITHUB_TOKEN']}",
                 "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as res:
        body = json.load(res)
    if "errors" in body:
        raise SystemExit(json.dumps(body["errors"], indent=2))
    return body["data"]


def fetch():
    info = gql("""
      query($login: String!) {
        user(login: $login) {
          createdAt
          followers { totalCount }
          repositories(first: 100, ownerAffiliations: OWNER, privacy: PUBLIC, isFork: false) {
            totalCount
            nodes {
              stargazerCount
              languages(first: 10, orderBy: {field: SIZE, direction: DESC}) {
                edges { size node { name color } }
              }
            }
          }
        }
      }""", login=USER)["user"]

    # The calendar API returns at most one year per call: walk from the
    # account's creation year to today.
    days = {}
    today = dt.datetime.now(dt.timezone.utc).date()
    year = int(info["createdAt"][:4])
    while year <= today.year:
        start = dt.datetime(year, 1, 1, tzinfo=dt.timezone.utc)
        end = min(dt.datetime(year, 12, 31, 23, 59, 59, tzinfo=dt.timezone.utc),
                  dt.datetime.now(dt.timezone.utc))
        cal = gql("""
          query($login: String!, $from: DateTime!, $to: DateTime!) {
            user(login: $login) {
              contributionsCollection(from: $from, to: $to) {
                contributionCalendar { weeks { contributionDays { date contributionCount } } }
              }
            }
          }""", login=USER, **{"from": start.isoformat(), "to": end.isoformat()})
        for week in cal["user"]["contributionsCollection"]["contributionCalendar"]["weeks"]:
            for d in week["contributionDays"]:
                days[dt.date.fromisoformat(d["date"])] = d["contributionCount"]
        year += 1
    return info, dict(sorted(days.items())), today


def streaks(days, today):
    longest = run = 0
    for count in days.values():
        run = run + 1 if count else 0
        longest = max(longest, run)
    # Today without contributions yet doesn't break the current streak.
    current, day = 0, today if days.get(today) else today - dt.timedelta(days=1)
    while days.get(day):
        current += 1
        day -= dt.timedelta(days=1)
    return current, longest


def svg(width, height, body, title):
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="{escape(title)}">
<title>{escape(title)}</title>
<style>
  .h {{ font: 700 13px {MONO}; letter-spacing: 2.5px; fill: {MUTED}; }}
  .n {{ font: italic 900 34px {SANS}; fill: {INK}; }}
  .l {{ font: 600 12px {MONO}; letter-spacing: 1px; fill: {MUTED}; }}
  .s {{ font: 600 13px {SANS}; fill: {INK}; }}
  .bar {{ transform-box: fill-box; transform-origin: bottom; animation: grow .9s cubic-bezier(.2,.8,.2,1) both; }}
  @keyframes grow {{ from {{ transform: scaleY(0); }} }}
  .fade {{ animation: fade .8s ease-out both; }}
  @keyframes fade {{ from {{ opacity: 0; }} }}
</style>
<rect x="0.5" y="0.5" width="{width - 1}" height="{height - 1}" rx="14" fill="{BG}" stroke="{LINE}"/>
{body}
</svg>
"""


def activity(info, days, today):
    current, longest = streaks(days, today)
    total = sum(days.values())
    stars = sum(r["stargazerCount"] for r in info["repositories"]["nodes"])
    width, height = 840, 230

    stats = [
        (f"{total:,}", "CONTRIBUTIONS"),
        (f"{current}", "CURRENT STREAK"),
        (f"{longest}", "LONGEST STREAK"),
        (f"{info['repositories']['totalCount']}", "PUBLIC REPOS"),
        (f"{stars}", "STARS"),
    ]
    parts = [f'<text x="28" y="40" class="h">ACTIVITY</text>',
             f'<text x="{width - 28}" y="40" class="l" text-anchor="end">'
             f'on GitHub since {info["createdAt"][:4]}</text>']
    col = (width - 56) / len(stats)
    for i, (value, label) in enumerate(stats):
        x = 28 + i * col
        color = LIME if i == 1 else INK
        parts.append(f'<g class="fade" style="animation-delay:{i * 80}ms">'
                     f'<text x="{x:.0f}" y="88" class="n" fill="{color}" style="fill:{color}">{value}</text>'
                     f'<text x="{x:.0f}" y="110" class="l">{label}</text></g>')

    # Last 52 weeks as bars; the latest week is highlighted.
    weeks = []
    start = today - dt.timedelta(days=today.weekday() + 7 * 51)
    for w in range(52):
        first = start + dt.timedelta(weeks=w)
        weeks.append(sum(days.get(first + dt.timedelta(days=d), 0) for d in range(7)))
    peak = max(weeks) or 1
    x0, base, h, gap = 28, height - 28, 78, 3
    bw = (width - 56 - gap * 51) / 52
    parts.append(f'<line x1="{x0}" y1="{base + .5}" x2="{width - 28}" y2="{base + .5}" stroke="{LINE}"/>')
    for i, count in enumerate(weeks):
        bh = max(3, h * count / peak) if count else 3
        fill = LIME if i == 51 else (VIOLET if count else LINE)
        parts.append(f'<rect class="bar" style="animation-delay:{300 + i * 12}ms" x="{x0 + i * (bw + gap):.1f}" '
                     f'y="{base - bh:.1f}" width="{bw:.1f}" height="{bh:.1f}" rx="2" fill="{fill}">'
                     f'<title>{count} contributions</title></rect>')
    return svg(width, height, "\n".join(parts), f"{USER}'s GitHub activity")


def languages(info):
    sizes, colors = {}, {}
    for repo in info["repositories"]["nodes"]:
        for edge in repo["languages"]["edges"]:
            name = edge["node"]["name"]
            sizes[name] = sizes.get(name, 0) + edge["size"]
            colors[name] = edge["node"]["color"] or MUTED
    top = sorted(sizes.items(), key=lambda kv: -kv[1])[:6]
    total = sum(size for _, size in top) or 1
    width, height = 840, 150

    parts = ['<text x="28" y="40" class="h">LANGUAGES</text>',
             f'<text x="{width - 28}" y="40" class="l" text-anchor="end">public repos · by code size</text>',
             f'<clipPath id="track"><rect x="28" y="60" width="{width - 56}" height="12" rx="6"/></clipPath>',
             '<g clip-path="url(#track)">']
    x = 28.0
    for i, (name, size) in enumerate(top):
        w = (width - 56) * size / total
        parts.append(f'<rect class="fade" style="animation-delay:{i * 90}ms" x="{x:.1f}" y="60" '
                     f'width="{w + 1:.1f}" height="12" fill="{colors[name]}"/>')
        x += w
    parts.append("</g>")
    col = (width - 56) / 3
    for i, (name, size) in enumerate(top):
        cx, cy = 28 + (i % 3) * col, 100 + (i // 3) * 26
        parts.append(f'<g class="fade" style="animation-delay:{300 + i * 60}ms">'
                     f'<circle cx="{cx + 6:.0f}" cy="{cy - 4}" r="6" fill="{colors[name]}"/>'
                     f'<text x="{cx + 20:.0f}" y="{cy}" class="s">{escape(name)}</text>'
                     f'<text x="{cx + col - 24:.0f}" y="{cy}" class="l" text-anchor="end">'
                     f'{100 * size / total:.1f}%</text></g>')
    return svg(width, height, "\n".join(parts), f"{USER}'s top languages")


def main():
    info, days, today = fetch()
    OUT.mkdir(exist_ok=True)
    (OUT / "activity.svg").write_text(activity(info, days, today), encoding="utf-8")
    (OUT / "languages.svg").write_text(languages(info), encoding="utf-8")
    print(f"cards written to {OUT}")


if __name__ == "__main__":
    main()
