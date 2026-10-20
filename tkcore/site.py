"""Static site for GitHub Pages, written into docs/.

  python -m tkcore.site [--out DIR]

Writes the home page, one page per chapter (chapter/<n>/) and per kural (kural/<n>/), the FAQ page built from
docs/faq.md, 404.html, style.css, sitemap.xml, robots.txt and .nojekyll, and copies llms.txt, llms-full.txt, the social
preview image and the favicon. Plain HTML and one stylesheet; no scripts.

Kural and chapter pages are in Tamil, with their English parts marked lang="en". Links between pages are relative, so
the site works under any path prefix. Canonical URLs, Open Graph tags, JSON-LD and the sitemap use the absolute base URL
in tkcore/site_templates/config.json; 404.html uses it for every link, since it is served at any depth. Version and
date come from release/release.json.

Tamil text comes from data/core. English text comes from the layer rows tkcore.release ships, so a row the release
withholds never appears. A kural whose text is not resolved gets a placeholder page that is noindex and left out of
the sitemap.

The output is byte-for-byte the same on every run. The generator replaces its own files and the kural/, chapter/ and
faq/ directories, and leaves every other file in the output directory alone.
"""
import argparse
import hashlib
import html
import json
import posixpath
import re
import shutil
from pathlib import Path

from . import DATA_CORE, REGISTRY, ROOT
from .release import CANONICAL_IYAL_SCHEME, CONFIGS, META, layer_rows, text_sha256
from .validate import RESOLVED, load_tables

TEMPLATES = Path(__file__).resolve().parent / "site_templates"
CONFIG = json.loads((TEMPLATES / "config.json").read_text(encoding="utf-8"))
BASE = CONFIG["base_url"].rstrip("/")
REPO = CONFIG["repo"].rstrip("/")
NAME = CONFIG["site_name"]
WIKIDATA = CONFIG["work_wikidata"]
CC0 = CONFIG["core_license_url"]
MAINTAINER = CONFIG["maintainer"]
RAW = REPO.replace("https://github.com/", "https://raw.githubusercontent.com/") + "/main"
DOCS = ROOT / "docs"
FAQ_MD = DOCS / "faq.md"
ASSETS = ROOT / ".github" / "assets"
# output name -> source; copied byte for byte
COPIES = {"style.css": TEMPLATES / "style.css", "icons.svg": TEMPLATES / "icons.svg", "mark.svg": ASSETS / "logo.svg",
          "social-preview.png": ASSETS / "social-preview.png", "favicon.png": ASSETS / "favicon-32.png"}
# assets linked with ?v=<first 8 hex of sha256 of the file>, so a changed file gets a new URL
VERSION = {n: hashlib.sha256(COPIES[n].read_bytes()).hexdigest()[:8] for n in ("style.css", "icons.svg", "mark.svg")}
ROOT_TEXTS = ("llms.txt", "llms-full.txt")  # copied when present at the repository root
OWN_DIRS = ("kural", "chapter", "faq")
IMAGE = {"path": "social-preview.png", "width": 1280, "height": 640,
         "alt": "Thirukkural · திருக்குறள்: a palm-leaf book beside the first kural as a JSON record"}
TRANSLATIONS = {"pope1886-en": " (1886)", "drew-lazarus-en": "", "aiyar1916-en": " (1916)"}  # layer -> year label
TAB_LABEL = {"pope1886-en": "Pope", "drew-lazarus-en": "Drew & Lazarus", "aiyar1916-en": "Aiyar"}
STATUS_SHORT = {"verified_scan": "Verified against print", "adjudicated": "Settled by a ledger decision",
                "verified_digital_only": "Digital sources agree"}
STATUS = {"verified_scan": "settled against the printed editions",
          "adjudicated": "settled by a recorded decision in the ledger; see adjudication_ids",
          "verified_digital_only": "every digital source has the same letters"}
THIRUVALLUVAR = {"@type": "Person", "name": "Thiruvalluvar"}
BOOK = {"@type": "Book", "name": "Tirukkuṟaḷ", "alternateName": ["Thirukkural", "திருக்குறள்"], "sameAs": WIKIDATA,
        "author": THIRUVALLUVAR}
HOME_LINK = "Thirukkural Tamil dataset"
LICENCE_LINE = "Tamil text and English translations: CC0-1.0."
LIGHT_CANVAS, DARK_CANVAS = "#fbfaf6", "#121212"


# ---------------------------------------------------------------- shared pieces

def esc(s) -> str:
    return html.escape(str(s), quote=False)


def attr(s) -> str:
    return html.escape(str(s), quote=True)


def ta(s) -> str:
    return f'<span lang="ta">{esc(s)}</span>'


def named(name_ta, fallback: str) -> str:
    """A Tamil name marked lang="ta", or the English fallback where the name is missing."""
    return ta(name_ta) if name_ta else esc(fallback)


def blob(path: str) -> str:
    return f"{REPO}/blob/main/{path}"


def is_indexable(k: dict) -> bool:
    return k["text_status"] in RESOLVED and k["lines_ta"] is not None


def kural_url(n: int) -> str:
    return f"{BASE}/kural/{n}/"


def chapter_url(n: int) -> str:
    return f"{BASE}/chapter/{n}/"


def jsonld(doc: dict) -> str:
    text = json.dumps(doc, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    return f'<script type="application/ld+json">{text}</script>'


def breadcrumbs(*items) -> dict:
    return {"@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": i, "name": name, "item": url} for i, (name, url) in enumerate(items, 1)]}


def asset(root: str, name: str) -> str:
    return f"{root}{name}?v={VERSION[name]}"


def icon(root: str, name: str) -> str:
    return f'<svg class="i" aria-hidden="true"><use href="{asset(root, "icons.svg")}#{name}"/></svg>'


def page(*, lang, title, desc, url, robots, og_type, root, ld, main, icons=True) -> str:
    """One HTML page. root is the path from the page to the site root ('', '../', '../../'), or BASE + '/'.
    main is the content of <main>; the skip link, header and footer are the same on every page."""
    locale, other = ("ta_IN", "en_US") if lang == "ta" else ("en_US", "ta_IN")
    image = f"{BASE}/{IMAGE['path']}"
    t, d = attr(title), attr(desc)
    head = [
        '<meta charset="utf-8">', '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f"<title>{esc(title)}</title>", f'<meta name="description" content="{d}">',
        f'<meta name="robots" content="{robots}">', f'<link rel="canonical" href="{attr(url)}">',
        f'<meta name="theme-color" content="{LIGHT_CANVAS}" media="(prefers-color-scheme: light)">',
        f'<meta name="theme-color" content="{DARK_CANVAS}" media="(prefers-color-scheme: dark)">',
        f'<link rel="icon" type="image/png" href="{root}favicon.png">',
        f'<link rel="stylesheet" href="{asset(root, "style.css")}">',
        f'<meta property="og:site_name" content="{attr(NAME)}">', f'<meta property="og:type" content="{og_type}">',
        f'<meta property="og:title" content="{t}">', f'<meta property="og:description" content="{d}">',
        f'<meta property="og:url" content="{attr(url)}">', f'<meta property="og:locale" content="{locale}">',
        f'<meta property="og:locale:alternate" content="{other}">',
        f'<meta property="og:image" content="{image}">',
        f'<meta property="og:image:width" content="{IMAGE["width"]}">',
        f'<meta property="og:image:height" content="{IMAGE["height"]}">',
        f'<meta property="og:image:alt" content="{attr(IMAGE["alt"])}">',
        '<meta name="twitter:card" content="summary_large_image">', f'<meta name="twitter:title" content="{t}">',
        f'<meta name="twitter:description" content="{d}">', f'<meta name="twitter:image" content="{image}">',
        jsonld({"@context": "https://schema.org", **ld})]
    body = [f'<a class="skip" lang="en" href="#main">Skip to content</a>', site_header(root, icons),
            f'<div class="page"><main id="main">\n{main}\n</main>\n{site_footer(root)}</div>']
    return (f'<!doctype html>\n<html lang="{lang}">\n<head>\n' + "\n".join(head) + "\n</head>\n<body>\n"
            + "\n".join(body) + "\n</body>\n</html>\n")


def site_header(root: str, icons: bool = True) -> str:
    home = root or "./"
    search = (icon(root, "search") if icons else "") + "<span>Search</span>"
    mark = (f'<img src="{asset(root, "mark.svg")}" width="32" height="32" alt="">' if icons else "")
    return (f'<header class="top" lang="en"><a class="brand" href="{home}" aria-label="{NAME}, home">{mark}'
            f"<span>Thirukkural</span></a><span class=\"gap\"></span>"
            f'<a class="chip" href="{root}#chapters" data-search>{search}</a><a class="nav" href="{root}faq/">FAQ</a>'
            f'<a class="nav gh" href="{REPO}">GitHub</a><span data-theme-slot></span></header>')


def page_nav(label, prev, here, nxt) -> str:
    """Previous and next links ((href, text) or None) and a link up."""
    parts = [f'<a rel="prev" href="{prev[0]}">{prev[1]}</a>' if prev else "",
             f'<a href="{here[0]}">{here[1]}</a>' if here else "",
             f'<a rel="next" href="{nxt[0]}">{nxt[1]}</a>' if nxt else ""]
    return f'<nav lang="en" aria-label="{label}"><p>' + " · ".join(p for p in parts if p) + "</p></nav>"


def site_footer(root: str) -> str:
    return (f'<footer lang="en"><nav aria-label="Site"><a href="{root or "./"}">{HOME_LINK}</a> · '
            f'<a href="{root}faq/">FAQ</a> · <a href="{REPO}">GitHub repository</a> · <a href="{root}#docs">'
            f'Documentation</a></nav><p>{LICENCE_LINE} Version {esc(META["version"])}, {esc(META["date"])}. '
            f'Maintained by <a href="{MAINTAINER["url"]}">{esc(MAINTAINER["name"])}</a>.</p></footer>')


# ---------------------------------------------------------------- structure

class Book:
    """The core tables arranged for the pages: chapters, book (paal) and section (iyal) names, English translations."""

    def __init__(self, core_dir: Path):
        t = load_tables(core_dir)
        self.kurals = t["kurals"]
        self.by_number = {k["number"]: k for k in self.kurals}
        self.chapters = {a["number"]: a for a in t["adhikarams"]}
        self.paals = [d for d in t["divisions"] if d["level"] == "paal"]
        self.iyals = [d for d in t["divisions"] if d["level"] == "iyal" and d["scheme"] == CANONICAL_IYAL_SCHEME]
        self.paal = {d["number"]: d for d in self.paals}
        self.iyal = {d["number"]: d for d in self.iyals}
        self.english = translations(self.kurals)
        self.source_url = {s["source_id"]: s["url"] for s in json.loads(REGISTRY.read_text(encoding="utf-8"))["sources"]}

    def chapter_name(self, a: dict) -> str:
        return a["name_ta"] or f"Chapter {a['number']}"


def translations(kurals: list[dict]) -> dict[str, list[dict]]:
    """kural_id -> the shipped English rows that carry text, in TRANSLATIONS order."""
    ids = [k["id"] for k in kurals]
    licence = {s["source_id"]: s["declared_license"] for s in json.loads(REGISTRY.read_text(encoding="utf-8"))["sources"]}
    out: dict[str, list[dict]] = {}
    for lid in TRANSLATIONS:
        for r in layer_rows(lid, ids, licence):
            if r["text"]:
                out.setdefault(r["kural_id"], []).append({**r, "layer_id": lid})
    return out


def and_list(names: list[str]) -> str:
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


# ---------------------------------------------------------------- kural pages

def crumbs_html(items) -> str:
    """Breadcrumb as an ordered list; items are (html, href or None), the last one is the current page."""
    li = "".join(f'<li><a href="{h}">{t}</a></li>' if h else f'<li aria-current="page">{t}</li>' for t, h in items)
    return f'<nav class="crumb" lang="en" aria-label="Breadcrumb"><ol>{li}</ol></nav>'


def pager(label, prev, up, nxt) -> str:
    """Cards to the neighbouring pages: prev and nxt are (href, text, tamil snippet or '') or None, up is (href, text).
    On narrow screens the three links become a fixed track."""
    def card(cls, rel, item, arrow):
        if not item:
            return ""
        href, text, snip = item
        label_html = f"{arrow} {text}" if rel == "prev" else f"{text} {arrow}"
        return (f'<a class="card {cls}" rel="{rel}" href="{href}"><span class="dir">{label_html}</span>'
                + (f'<span class="snip" lang="ta">{esc(snip)}</span>' if snip else "") + "</a>")
    return (f'<nav class="pager" lang="en" aria-label="{label}">' + card("p", "prev", prev, "←")
            + f'<a class="up" href="{up[0]}">{up[1]}</a>' + card("n", "next", nxt, "→") + "</nav>")


def kural_page(b: Book, k: dict) -> str:
    n, a = k["number"], b.chapters[k["adhikaram_number"]]
    an, root = a["number"], "../../"
    paal, iyal = b.paal[k["paal_number"]], b.iyal[a["iyal_number"]]
    chapter_href, url = f"{root}chapter/{an}/", kural_url(n)
    chname = b.chapter_name(a)
    english = b.english.get(k["id"], []) if is_indexable(k) else []
    if is_indexable(k):
        lines = k["lines_ta"]
        title = f"Thirukkural {n}: {lines[0]} | {NAME}"
        tail = f" Thirukkural {n} in Tamil, chapter {chname}" + (
            f", with English translations by {and_list([r['author'].split()[-1] for r in english])}." if english else ".")
        full = " ".join(lines) + tail
        desc = full if len(full) <= 160 else lines[0] + "…" + tail
        robots = "index,follow"
        text = (f'<blockquote lang="ta"><p>{" ".join(f"<span>{esc(l)}</span>" for l in lines)}</p></blockquote>')
        mark = "ok" if k["text_status"] in STATUS else "wait"
    else:
        title, robots = f"Thirukkural {n} | {NAME}", "noindex,follow"
        desc = f"Kural {n} of the Thirukkural, chapter {an}. The Tamil text is pending."
        text = f'<p lang="en">The Tamil text of this kural is pending (<code>{esc(k["text_status"])}</code>).</p>'
        mark = "wait"
    status = (f'<figcaption lang="en"><span class="{mark}">{icon(root, "check") if mark == "ok" else ""}'
              f"{STATUS_SHORT.get(k['text_status'], 'Text pending')}</span></figcaption>")

    en_title = f", {esc(a['name_en'])}" if a["name_en"] else ""
    pn, yn = paal["number"], iyal["number"]
    facts = [("id", f"<code>{k['id']}</code>"),
             ("chapter", f'<a href="{chapter_href}">{named(a["name_ta"], chname)}</a>{en_title} (chapter {an})'),
             ("book", f"{named(paal['name_ta'], f'Book {pn}')} (book {pn}), section "
                      f"{named(iyal['name_ta'], f'Section {yn}')} ({yn})"),
             ("text_status", f"<code>{esc(k['text_status'])}</code>"
                             + (f": {STATUS[k['text_status']]}" if k["text_status"] in STATUS else ""))]
    if k["adjudication_ids"]:
        facts.append(("adjudication_ids", ", ".join(f"<code>{esc(i)}</code>" for i in k["adjudication_ids"])))
    if is_indexable(k):
        facts.append(("text_sha256", f"<code>{text_sha256(k['lines_ta'])}</code>"))
    body = [crumbs_html([("Home", root), (f"Chapter {an}: {named(a['name_ta'], chname)}", chapter_href),
                         (f"Kural {n}", None)]),
            f'<h1 class="eyebrow">குறள் {n} <span lang="en">· Thirukkural {n}</span></h1>',
            f'<figure class="hero card">{text}{status}</figure>', '<div class="tools" data-tools></div>']
    if english:
        body.append('<section class="tr" lang="en" aria-label="English translations"><h2>English translations</h2>'
                    + "".join(
            f'<figure class="card" id="tr-{r["layer_id"][:-3]}" data-t="{attr(TAB_LABEL[r["layer_id"]])}">'
            f'<blockquote><p>{"<br>".join(esc(l) for l in r["text"].splitlines())}</p></blockquote>'
            f'<figcaption>{esc(r["author"])}{TRANSLATIONS[r["layer_id"]]}, <cite>{esc(r["work_title"])}</cite>'
            "</figcaption></figure>" for r in english) + "</section>")
    body.append('<section class="card facts" lang="en"><h2>Details</h2><dl>'
                + "".join(f"<dt>{t}</dt><dd>{v}</dd>" for t, v in facts) + "</dl></section>")
    if is_indexable(k) and k["provenance"]:
        cited = list(dict.fromkeys((p["source_id"], p["field"]) for p in k["provenance"]))
        body.append('<section lang="en"><h2>Sources</h2><ul class="rows">' + "".join(
            f'<li><a href="{attr(b.source_url[sid])}"><code>{esc(sid)}</code>'
            f"{'' if field == 'lines_ta' else ' <span>(' + esc(field) + ')</span>'}</a></li>"
            for sid, field in cited) + "</ul></section>")

    def around(m):
        if m not in b.by_number:
            return None
        o = b.by_number[m]
        return (f"../{m}/", f"Kural {m}", o["lines_ta"][0] if is_indexable(o) else "")
    body.append(pager("Kurals", around(n - 1), (chapter_href, f"Chapter {an}"), around(n + 1)))

    quote = {"@type": "Quotation", "name": f"Thirukkural {n}", "identifier": k["id"], "url": url, "position": n,
             "inLanguage": "ta", "author": THIRUVALLUVAR,
             "isPartOf": {"@type": "Chapter", "name": chname, "position": an, "url": chapter_url(an), "isPartOf": BOOK},
             "license": CC0}
    if is_indexable(k):
        quote["text"] = "\n".join(k["lines_ta"])
        quote["isBasedOn"] = sorted({p["source_id"] for p in k["provenance"] if p["field"] == "lines_ta"})
    ld = {"@graph": [breadcrumbs((NAME, f"{BASE}/"), (f"Chapter {an}: {chname}", chapter_url(an)), (f"Kural {n}", url)),
                     quote]}
    return page(lang="ta", title=title, desc=desc, url=url, robots=robots, og_type="article", root=root, ld=ld,
                main="\n".join(body))


# ---------------------------------------------------------------- chapter pages

def chapter_page(b: Book, a: dict) -> str:
    n, root = a["number"], "../../"
    url, name = chapter_url(n), b.chapter_name(a)
    paal, iyal = b.paal[a["paal_number"]], b.iyal[a["iyal_number"]]
    if a["name_ta"]:
        title = f"{name} – Thirukkural chapter {n} | {NAME}"
        h1 = f'<h1>{esc(name)} <span lang="en">· Chapter {n}</span></h1>'
        robots = "index,follow"
    else:
        title, h1, robots = f"Thirukkural chapter {n} | {NAME}", f'<h1 lang="en">Chapter {n}</h1>', "noindex,follow"
    en = f" ({a['name_en']})" if a["name_en"] else ""
    desc = (f"Chapter {n} of the Thirukkural, {name}{en}: kurals {a['first_kural']} to {a['last_kural']} in Tamil, "
            "each with English translations.")
    about = [f"Book {paal['number']}" + (f": {ta(paal['name_ta'])}" if paal["name_ta"] else ""),
             f"Section {iyal['number']}" + (f": {ta(iyal['name_ta'])}" if iyal["name_ta"] else "")]
    if a["name_en"]:
        about.append(f"English title (Pope 1886): {esc(a['name_en'])}")
    items, listed = [], []
    for kn in range(a["first_kural"], a["last_kural"] + 1):
        k = b.by_number[kn]
        if is_indexable(k):
            couplet = "".join(f"<span>{esc(l)}</span>" for l in k["lines_ta"])
            listed.append({"@type": "ListItem", "position": kn - a["first_kural"] + 1, "url": kural_url(kn),
                           "name": k["lines_ta"][0]})
        else:
            couplet = '<span lang="en">text pending</span>'
        items.append(f'<li><a class="card" href="{root}kural/{kn}/"><span class="no" lang="en">{kn}</span>'
                     f'<span class="cp">{couplet}</span></a></li>')

    def around(m):
        if m not in b.chapters:
            return None
        o = b.chapters[m]
        return (f"../{m}/", f"Chapter {m}", o["name_ta"] or "")
    body = [crumbs_html([("Home", root), (f"Chapter {n}", None)]), h1,
            '<p class="meta" lang="en">' + ". ".join(about) + ".</p>", '<ol class="kl">' + "".join(items) + "</ol>",
            pager("Chapters", around(n - 1), (f"{root}#chapters", "All chapters"), around(n + 1))]
    ld = {"@graph": [breadcrumbs((NAME, f"{BASE}/"), (f"Chapter {n}: {name}", url)),
                     {"@type": "ItemList", "name": f"Kurals of chapter {n}: {name}", "numberOfItems": len(listed),
                      "itemListElement": listed}]}
    return page(lang="ta", title=title, desc=desc, url=url, robots=robots, og_type="website", root=root, ld=ld,
                main="\n".join(body))


# ---------------------------------------------------------------- home page

def home_page(b: Book, copied: list[str]) -> str:
    nk, nc = len(b.kurals), len(b.chapters)
    first, last = b.kurals[0]["id"], b.kurals[-1]["id"]
    title = f"{NAME} · திருக்குறள் – {nk:,} kurals in Tamil"
    desc = (f"Thirukkural Tamil dataset: all {nk:,} kurals in Tamil with English translations, Parimelazhagar's "
            "commentary and metre. JSONL and Parquet, CC0-1.0.")
    lead = (f"<p>The Tamil text of all {nk:,} kurals of the Thirukkural ({ta('திருக்குறள்')}), in {nc} chapters and "
            f"three books, with ids <code>{first}</code> to <code>{last}</code>. Each kural was compared letter by "
            "letter across six digital sources and checked against three 19th-century printed editions where they "
            "differ. Each kural lists its sources and a sha256 of its text. Joined to every kural: English "
            "translations by G. U. Pope (1886), W. H. Drew and John Lazarus, and V. V. S. Aiyar (1916); "
            "Parimelazhagar's Tamil commentary; and a metre analysis of every foot. The core text is licensed "
            "CC0-1.0.</p>")
    formats = [
        ("JSONL", f'<a href="{REPO}/tree/main/data"><code>data/</code></a> in the repository', "Every table's rows."),
        ("Parquet", "<code>dist/hf/data/</code>, built by <code>python -m tkcore.release</code>",
         f"{len(CONFIGS)} tables."),
        ("SQLite", "built by <code>python -m tkcore.agent_tools build-db</code>", "Lookup database for the agent tools."),
        ("NumPy .npy", f'<a href="{blob("data/embeddings/bge_m3_ta.npy")}"><code>data/embeddings/bge_m3_ta.npy</code></a>',
         "BGE-M3 vectors, one per kural. Model-generated."),
        ("Croissant JSON-LD", f'<a href="{blob("release/croissant.json")}"><code>release/croissant.json</code></a>',
         "Machine-readable description of the dataset.")]
    table = ("<table><thead><tr><th>Format</th><th>Where</th><th>What</th></tr></thead><tbody>"
             + "".join(f"<tr><td>{f}</td><td>{w}</td><td>{d}</td></tr>" for f, w, d in formats) + "</tbody></table>")
    code = esc(f'import pandas as pd\n\nbase = "{RAW}"\nkurals = pd.read_json(f"{{base}}/data/core/kurals.jsonl", '
               "lines=True)")
    books = []
    for p in b.paals:
        chs = [a for a in b.chapters.values() if a["paal_number"] == p["number"]]
        name = f"{ta(p['name_ta'])} · " if p["name_ta"] else ""
        books.append(f"<h3>{name}Book {p['number']}, chapters {chs[0]['number']} to {chs[-1]['number']}</h3>")
        for i in (i for i in b.iyals if i["paal_number"] == p["number"]):
            iname = f"{ta(i['name_ta'])} · " if i["name_ta"] else ""
            books.append(f"<h4>{iname}Section {i['number']}</h4>")
            ichs = [a for a in chs if a["iyal_number"] == i["number"]]
            books.append(f'<ol start="{ichs[0]["number"]}">' + "".join(
                f'<li><a href="chapter/{a["number"]}/">{named(a["name_ta"], b.chapter_name(a))}</a>'
                + (f" · {esc(a['name_en'])}" if a["name_en"] else "") + "</li>" for a in ichs) + "</ol>")
    docs = [("faq/", "Frequently asked questions"), (blob("docs/data-dictionary.md"), "Data dictionary"),
            (blob("docs/sources.md"), "Sources"), (blob("docs/licensing.md"), "Licensing"),
            (blob("README.md"), "README"), (blob("CHANGELOG.md"), "Changelog"), (blob("ROADMAP.md"), "Roadmap"),
            (blob("CITATION.cff"), "How to cite (CITATION.cff)"), (blob("CONTRIBUTING.md"), "Contributing"),
            (REPO, "GitHub repository")] + [(f, f) for f in copied]
    body = [f'<h1>{NAME} <span lang="ta">· திருக்குறள்</span></h1>', lead,
            "<p>Also known as: Tirukkural, Thirukural, Thiruvalluvar's Kural.</p>",
            '<h2 id="formats">Formats</h2>', table,
            '<h2 id="quick-start">Quick start</h2>', f'<pre><code class="language-python">{code}</code></pre>',
            '<h2 id="chapters">Books and chapters</h2>', *books,
            '<h2 id="docs">Documentation</h2>',
            "<ul>" + "".join(f'<li><a href="{attr(h)}">{esc(t)}</a></li>' for h, t in docs) + "</ul>"]
    person = {"@type": "Person", "name": MAINTAINER["name"], "url": MAINTAINER["url"],
              "sameAs": f"https://orcid.org/{META['orcid']}"}
    files = [("data/core/kurals.jsonl", "application/jsonl"), ("data/core/adhikarams.jsonl", "application/jsonl"),
             ("data/core/divisions.jsonl", "application/jsonl"), ("data/layers/pope1886-en.jsonl", "application/jsonl"),
             ("data/layers/drew-lazarus-en.jsonl", "application/jsonl"),
             ("data/layers/aiyar1916-en.jsonl", "application/jsonl"),
             ("data/layers/parimelazhagar-ta.jsonl", "application/jsonl"), ("release/croissant.json", "application/ld+json")]
    distribution = [{"@type": "DataDownload", "name": f.rsplit("/", 1)[-1], "contentUrl": f"{RAW}/{f}",
                     "encodingFormat": fmt} for f, fmt in files]
    distribution.append({"@type": "DataDownload", "name": "Repository archive (main)",
                         "contentUrl": f"{REPO}/archive/refs/heads/main.zip", "encodingFormat": "application/zip"})
    dataset = {
        "@type": "Dataset", "name": NAME,
        "alternateName": ["Thirukkural dataset", "Tirukkural dataset", "Thirukural dataset", "Thiruvalluvar's Kural dataset",
                          "திருக்குறள் தரவுத்தொகுப்பு"],
        "description": (f"The Tamil text of all {nk:,} kurals of the Thirukkural, in {nc} chapters and three books, with "
                        "a stable id, its sources and a sha256 for each kural. Joined to every kural: English "
                        "translations by G. U. Pope (1886), W. H. Drew and John Lazarus, and V. V. S. Aiyar (1916), "
                        "Parimelazhagar's Tamil commentary and a metre analysis of every foot. JSONL in the "
                        "repository; Parquet built from it."),
        "url": f"{BASE}/", "sameAs": [REPO],
        "identifier": f"https://doi.org/{META['doi']}" if META.get("doi") else REPO,
        "version": META["version"], "datePublished": META["date"], "inLanguage": ["ta", "en"], "license": CC0,
        "isAccessibleForFree": True, "creator": person,
        "keywords": ["Thirukkural", "Tirukkural", "Thirukural", "Kural", "திருக்குறள்", "Thiruvalluvar", "Tamil",
                     "Tamil dataset", "classical Tamil", "Tamil literature", "Tamil poetry", "kural venba", "Tamil NLP",
                     "Parimelazhagar", "G. U. Pope", "English translation"],
        "isBasedOn": BOOK,
        "citation": {"@type": "CreativeWork", "name": f"{NAME}, version {META['version']}", "author": person,
                     "datePublished": META["date"], "url": blob("CITATION.cff")},
        "distribution": distribution}
    website = {"@type": "WebSite", "name": NAME, "url": f"{BASE}/", "inLanguage": ["en", "ta"]}
    return page(lang="en", title=title, desc=desc, url=f"{BASE}/", robots="index,follow", og_type="website", root="",
                ld={"@graph": [dataset, website]}, main="\n".join(body))


# ---------------------------------------------------------------- FAQ (docs/faq.md)

INLINE = re.compile(r"`([^`]+)`|\[((?:[^\[\]`]|`[^`]*`)+)\]\(([^()\s]+)\)|\*\*(.+?)\*\*")
TAMIL = re.compile(r"[஀-௿]+(?: [஀-௿]+)*")


def faq_href(url: str) -> str:
    """A link in docs/faq.md as the FAQ page uses it: relative paths become GitHub URLs, others stay as they are."""
    if url.startswith("#") or re.match(r"[a-zA-Z][a-zA-Z0-9+.-]*:", url):
        return url
    path, _, frag = url.partition("#")
    p = posixpath.normpath(path[1:] if path.startswith("/") else posixpath.join("docs", path))
    if p == ".." or p.startswith("../"):
        raise SystemExit(f"docs/faq.md: link {url} points outside the repository")
    target = REPO if p == "." else f"{REPO}/{'tree' if (ROOT / p).is_dir() else 'blob'}/main/{p}"
    return target + (f"#{frag}" if frag else "")


def _text_html(s: str) -> str:
    return TAMIL.sub(lambda m: f'<span lang="ta">{m.group(0)}</span>', esc(s))


def inline_html(s: str) -> str:
    out, pos = [], 0
    for m in INLINE.finditer(s):
        out.append(_text_html(s[pos:m.start()]))
        code, label, url, bold = m.groups()
        if code is not None:
            out.append(f"<code>{esc(code)}</code>")
        elif label is not None:
            out.append(f'<a href="{attr(faq_href(url))}">{inline_html(label)}</a>')
        else:
            out.append(f"<strong>{inline_html(bold)}</strong>")
        pos = m.end()
    return "".join(out) + _text_html(s[pos:])


def inline_text(s: str) -> str:
    """Markdown inline markup removed: code without backticks, links as their text, bold without asterisks."""
    out, pos = [], 0
    for m in INLINE.finditer(s):
        code, label, _, bold = m.groups()
        out.append(s[pos:m.start()] + (code if code is not None else inline_text(label if label is not None else bold)))
        pos = m.end()
    return "".join(out) + s[pos:]


def md_blocks(lines: list[str]) -> list[tuple]:
    """Paragraphs ('p', text), bullet lists ('ul', [items]) and fenced code ('code', lang, text)."""
    out, i = [], 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("```"):
            j = i + 1
            while j < len(lines) and not lines[j].startswith("```"):
                j += 1
            out.append(("code", line[3:].strip(), "\n".join(lines[i + 1:j])))
            i = j + 1
        elif line.startswith("- "):
            items = []
            while i < len(lines) and (lines[i].startswith("- ") or (items and lines[i].startswith("  ") and lines[i].strip())):
                if lines[i].startswith("- "):
                    items.append(lines[i][2:].strip())
                else:
                    items[-1] += " " + lines[i].strip()
                i += 1
            out.append(("ul", items))
        elif not line.strip():
            i += 1
        else:
            para = []
            while i < len(lines) and lines[i].strip() and not lines[i].startswith(("```", "- ")):
                para.append(lines[i].strip())
                i += 1
            out.append(("p", " ".join(para)))
    return out


def parse_faq(text: str) -> tuple[str, list[tuple[str, list[tuple]]]]:
    """docs/faq.md -> (title, [(question, blocks)]). The file is '# title', then '## question' sections."""
    lines = text.splitlines()
    if not lines or not lines[0].startswith("# "):
        raise SystemExit("docs/faq.md: the first line must be '# <title>'")
    sections, fenced = [], False
    for line in lines[1:]:
        if line.startswith("```"):
            fenced = not fenced
        if line.startswith("## ") and not fenced:
            sections.append((line[3:].strip(), []))
        elif sections:
            sections[-1][1].append(line)
    return lines[0][2:].strip(), [(q, md_blocks(body)) for q, body in sections]


def block_html(blk: tuple) -> str:
    if blk[0] == "code":
        cls = f' class="language-{attr(blk[1])}"' if blk[1] else ""
        return f"<pre><code{cls}>{esc(blk[2])}</code></pre>"
    if blk[0] == "ul":
        return "<ul>" + "".join(f"<li>{inline_html(x)}</li>" for x in blk[1]) + "</ul>"
    return f"<p>{inline_html(blk[1])}</p>"


def block_text(blk: tuple) -> str:
    if blk[0] == "code":
        return blk[2]
    if blk[0] == "ul":
        return "\n".join(inline_text(x) for x in blk[1])
    return inline_text(blk[1])


def slug(s: str, used: set) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-") or "question"
    out, i = base, 2
    while out in used:
        out, i = f"{base}-{i}", i + 1
    used.add(out)
    return out


def faq_page(text: str) -> tuple[str, int]:
    title, qa = parse_faq(text)
    root, url, used = "../", f"{BASE}/faq/", set()
    body = [f"<h1>{inline_html(title)}</h1>"]
    entities = []
    for q, blocks in qa:
        plain = inline_text(q)
        body.append(f'<h2 id="{slug(plain, used)}">{inline_html(q)}</h2>')
        body += [block_html(x) for x in blocks]
        entities.append({"@type": "Question", "name": plain,
                         "acceptedAnswer": {"@type": "Answer", "text": "\n\n".join(block_text(x) for x in blocks)}})
    desc = (f"Frequently asked questions about the Thirukkural Tamil dataset of 1,330 kurals: what it holds, how to load "
            "it, translations, licences and citation.")
    ld = {"@type": "FAQPage", "name": inline_text(title), "url": url, "inLanguage": "en", "mainEntity": entities}
    return page(lang="en", title=f"{inline_text(title)} | {NAME}", desc=desc, url=url, robots="index,follow",
                og_type="website", root=root, ld=ld, main="\n".join(body)), len(entities)


# ---------------------------------------------------------------- 404, sitemap, robots

def not_found_page() -> str:
    root = f"{BASE}/"
    body = ["<h1>Page not found</h1>",
            "<p>There is no page at this address. Each kural has a page numbered 1 to 1,330, for example "
            f'<a href="{root}kural/1/">kural/1/</a>, and each chapter a page numbered 1 to 133, for example '
            f'<a href="{root}chapter/1/">chapter/1/</a>.</p>',
            f'<p><a href="{root}">{HOME_LINK}</a> · <a href="{root}faq/">FAQ</a></p>']
    ld = {"@type": "WebPage", "name": "Page not found", "url": f"{BASE}/404.html",
          "isPartOf": {"@type": "WebSite", "name": NAME, "url": f"{BASE}/"}}
    return page(lang="en", title=f"Page not found | {NAME}", desc="There is no page at this address.",
                url=f"{BASE}/404.html", robots="noindex", og_type="website", root=root, ld=ld, main="\n".join(body),
                icons=False)


def sitemap(urls: list[str]) -> str:
    return ('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            + "".join(f"<url><loc>{u}</loc><lastmod>{META['date']}</lastmod></url>\n" for u in urls) + "</urlset>\n")


BOTS = ("GPTBot", "OAI-SearchBot", "ClaudeBot", "PerplexityBot", "Google-Extended", "Applebot-Extended", "CCBot")


def robots_txt() -> str:
    return ("User-agent: *\nAllow: /\n\n" + "".join(f"User-agent: {b}\nAllow: /\n\n" for b in BOTS)
            + f"Sitemap: {BASE}/sitemap.xml\n")


# ---------------------------------------------------------------- Cloudflare headers and redirects

LONG_CACHE = "public, max-age=31536000, immutable"
SHORT_CACHE = "public, max-age=3600"
REVALIDATE = "public, max-age=0, must-revalidate"
VERSIONED = ("/style.css", "/app.js", "/icons.svg", "/mark.svg", "/search.json")  # linked with ?v=<sha8>
HTML_PATHS = ("/", "/kural/*", "/chapter/*", "/faq/*", "/404.html")
TEXT_TYPES = {"/llms.txt": "text/plain; charset=utf-8", "/llms-full.txt": "text/plain; charset=utf-8",
              "/robots.txt": "text/plain; charset=utf-8", "/*.md": "text/markdown; charset=utf-8",
              "/sitemap.xml": "application/xml; charset=utf-8",
              "/site.webmanifest": "application/manifest+json; charset=utf-8"}


def csp(script_hashes=()) -> str:
    scripts = " ".join(["'self'"] + [f"'sha256-{h}'" for h in script_hashes])
    return (f"default-src 'none'; script-src {scripts}; style-src 'self'; img-src 'self'; font-src 'self'; "
            "connect-src 'self'; manifest-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'; "
            "object-src 'none'")


def headers_txt(script_hashes=()) -> str:
    """Cloudflare _headers. Matching rules add their values together, so each path gets one Cache-Control rule."""
    rules = [("/*", ["X-Content-Type-Options: nosniff", "Referrer-Policy: strict-origin-when-cross-origin",
                     "Permissions-Policy: camera=(), microphone=(), geolocation=(), interest-cohort=()",
                     "Cross-Origin-Opener-Policy: same-origin", f"Content-Security-Policy: {csp(script_hashes)}"])]
    rules += [(p, [f"Cache-Control: {REVALIDATE}"]) for p in HTML_PATHS]
    rules[1][1].append("Link: </llms.txt>; rel=\"alternate\"; type=\"text/plain\"")
    rules[-1][1].append("X-Robots-Tag: noindex")
    rules += [(p, [f"Cache-Control: {LONG_CACHE}"]) for p in VERSIONED]
    rules += [(p, [f"Content-Type: {t}", f"Cache-Control: {SHORT_CACHE}"]) for p, t in TEXT_TYPES.items()]
    return "\n".join(path + "\n" + "".join(f"  {h}\n" for h in hs) for path, hs in rules)


def redirects_txt() -> str:
    return "".join(f"{a} {b} {code}\n" for a, b, code in (
        ("/kural", "/kural/1/", 302), ("/kural/", "/kural/1/", 302), ("/chapter", "/chapter/1/", 302),
        ("/chapter/", "/chapter/1/", 302), ("/llms", "/llms.txt", 301)))


# ---------------------------------------------------------------- generate

def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))


def generate(out: Path = DOCS, core_dir: Path = DATA_CORE) -> dict:
    b = Book(core_dir)
    out.mkdir(parents=True, exist_ok=True)
    for d in OWN_DIRS:
        if (out / d).exists():
            shutil.rmtree(out / d)
    for name, src in COPIES.items():
        shutil.copyfile(src, out / name)
    copied = []
    for name in ROOT_TEXTS:
        if (ROOT / name).exists():
            shutil.copyfile(ROOT / name, out / name)
            copied.append(name)
        elif (out / name).exists():
            (out / name).unlink()
    (out / ".nojekyll").write_bytes(b"")

    urls = [f"{BASE}/", f"{BASE}/faq/"]
    _write(out / "index.html", home_page(b, copied))
    faq, questions = faq_page(FAQ_MD.read_text(encoding="utf-8"))
    _write(out / "faq" / "index.html", faq)
    _write(out / "404.html", not_found_page())
    for a in b.chapters.values():
        _write(out / "chapter" / str(a["number"]) / "index.html", chapter_page(b, a))
        if a["name_ta"]:
            urls.append(chapter_url(a["number"]))
    indexable = 0
    for k in b.kurals:
        _write(out / "kural" / str(k["number"]) / "index.html", kural_page(b, k))
        if is_indexable(k):
            urls.append(kural_url(k["number"]))
            indexable += 1
    _write(out / "sitemap.xml", sitemap(urls))
    _write(out / "robots.txt", robots_txt())
    _write(out / "_headers", headers_txt())
    _write(out / "_redirects", redirects_txt())
    return {"pages": 3 + len(b.chapters) + len(b.kurals), "chapters": len(b.chapters), "kurals": len(b.kurals),
            "indexable_kurals": indexable, "faq_questions": questions, "sitemap_urls": len(urls)}


def main(argv=None):
    ap = argparse.ArgumentParser(description="Write the static site.")
    ap.add_argument("--out", type=Path, default=DOCS)
    args = ap.parse_args(argv)
    print(generate(args.out))


if __name__ == "__main__":
    main()
