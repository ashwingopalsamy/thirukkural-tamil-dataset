import html
import json
import re
from urllib.parse import urlsplit

import pytest

from tkcore import ROOT
from tkcore.site import BASE, REPO, faq_page, generate
from tkcore.validate import RESOLVED, load_tables

from .helpers import dumps_jsonl, skeleton_tables, synthetic_line

RELEASE = json.loads((ROOT / "release" / "release.json").read_text(encoding="utf-8"))
FAQ_MD = (ROOT / "docs" / "faq.md").read_text(encoding="utf-8")
CC0 = "https://creativecommons.org/publicdomain/zero/1.0/"
BOTS = ("GPTBot", "OAI-SearchBot", "ClaudeBot", "PerplexityBot", "Google-Extended", "Applebot-Extended", "CCBot")
HAND_WRITTEN = "# Kept\n\nThis file is not the generator's.\n"


def _core(tmp_path, tables):
    core = tmp_path / "core"
    core.mkdir()
    for name, rows in tables.items():
        (core / f"{name}.jsonl").write_text(dumps_jsonl(rows), encoding="utf-8")
    return core


def _read(p):
    return p.read_text(encoding="utf-8")


def _graph(page):
    doc = json.loads(re.search(r'<script type="application/ld\+json">(.*?)</script>', page, re.S).group(1))
    return doc.get("@graph", [doc])


def _node(page, kind):
    return next(n for n in _graph(page) if n["@type"] == kind)


def _meta(page, key):
    m = re.search(rf'<meta (?:name|property)="{re.escape(key)}" content="([^"]*)">', page)
    return html.unescape(m.group(1)) if m else None


def _canonical(page):
    return re.search(r'<link rel="canonical" href="([^"]*)">', page).group(1)


def _locs(out):
    return re.findall(r"<loc>([^<]*)</loc>", _read(out / "sitemap.xml"))


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    """The site from the committed data, generated once into a directory that already holds a hand-written .md file
    and a stale page in a directory the generator owns."""
    out = tmp_path_factory.mktemp("docs")
    (out / "faq.md").write_text(HAND_WRITTEN, encoding="utf-8")
    (out / "kural" / "9999").mkdir(parents=True)
    (out / "kural" / "9999" / "index.html").write_text("stale", encoding="utf-8")
    return out, generate(out)


@pytest.fixture(scope="module")
def pages(site):
    out, _ = site
    return {p.relative_to(out).as_posix(): _read(p) for p in sorted(out.rglob("*.html"))}


def test_stats_and_page_set(site, pages):
    out, stats = site
    core = load_tables()
    indexable = sum(k["text_status"] in RESOLVED and k["lines_ta"] is not None for k in core["kurals"])
    assert stats == {"pages": 3 + 133 + 1330, "chapters": 133, "kurals": 1330, "indexable_kurals": indexable,
                     "faq_questions": len(re.findall(r"^## ", FAQ_MD, re.M)), "sitemap_urls": 2 + 133 + indexable}
    assert len(pages) == stats["pages"]
    assert {"index.html", "404.html", "faq/index.html", "chapter/133/index.html", "kural/1330/index.html"} <= set(pages)


def test_hand_written_md_survives_and_stale_pages_go(site):
    out, _ = site
    assert _read(out / "faq.md") == HAND_WRITTEN
    assert not (out / "kural" / "9999").exists()


def test_titles_and_descriptions_unique(pages):
    titles = [html.unescape(re.search(r"<title>(.*?)</title>", p).group(1)) for p in pages.values()]
    descs = [_meta(p, "description") for p in pages.values()]
    assert all(titles) and all(descs)
    assert len(set(titles)) == len(titles)
    assert len(set(descs)) == len(descs)
    assert max(len(d) for d in descs) <= 160


@pytest.mark.parametrize("path,url", [("index.html", "/"), ("faq/index.html", "/faq/"),
                                      ("chapter/7/index.html", "/chapter/7/"), ("kural/7/index.html", "/kural/7/")])
def test_canonical_on_base(pages, path, url):
    assert _canonical(pages[path]) == BASE + url
    assert _meta(pages[path], "og:url") == BASE + url


def test_every_page_has_head_metadata(pages):
    for path, p in pages.items():
        assert p.startswith("<!doctype html>\n<html lang="), path
        assert '<meta charset="utf-8">' in p and '<meta name="viewport"' in p, path
        assert _canonical(p).startswith(BASE + "/"), path
        assert _meta(p, "robots") in ("index,follow", "noindex,follow", "noindex"), path
        for key in ("og:title", "og:description", "og:url", "og:type", "og:locale", "og:image:alt",
                    "twitter:title", "twitter:description"):
            assert _meta(p, key), (path, key)
        assert _meta(p, "og:site_name") == "Thirukkural Tamil Dataset"
        assert _meta(p, "og:image") == _meta(p, "twitter:image") == f"{BASE}/social-preview.png"
        assert (_meta(p, "og:image:width"), _meta(p, "og:image:height")) == ("1280", "640")
        assert _meta(p, "twitter:card") == "summary_large_image"
        assert 'rel="icon"' in p and 'rel="stylesheet"' in p, path
        _graph(p)  # parses


def test_html_lang(pages):
    lang = lambda path: re.search(r'<html lang="([^"]+)">', pages[path]).group(1)  # noqa: E731
    for path in pages:
        want = "ta" if path.startswith(("kural/", "chapter/")) else "en"
        assert lang(path) == want, path
    assert _meta(pages["kural/1/index.html"], "og:locale") == "ta_IN"
    assert _meta(pages["index.html"], "og:locale") == "en_US"


def test_home_page_and_dataset_jsonld(pages):
    page = pages["index.html"]
    assert '<h1>Thirukkural Tamil Dataset <span lang="ta">· திருக்குறள்</span></h1>' in page
    ds = _node(page, "Dataset")
    assert ds["name"] == "Thirukkural Tamil Dataset" and "Thirukkural dataset" in ds["alternateName"]
    assert ds["license"] == CC0 and ds["isAccessibleForFree"] is True
    assert ds["version"] == RELEASE["version"] and ds["datePublished"] == RELEASE["date"]
    assert ds["inLanguage"] == ["ta", "en"] and ds["url"] == BASE + "/" and REPO in ds["sameAs"]
    assert ds["creator"]["name"] == "Ashwin Gopalsamy"
    assert ds["creator"]["sameAs"] == f"https://orcid.org/{RELEASE['orcid']}"
    assert {"Thirukkural", "திருக்குறள்", "Tamil dataset"} <= set(ds["keywords"])
    assert ds["isBasedOn"]["sameAs"] == "https://www.wikidata.org/wiki/Q2167085"
    urls = {d["contentUrl"]: d["encodingFormat"] for d in ds["distribution"]}
    raw = "https://raw.githubusercontent.com/ashwingopalsamy/thirukkural-tamil-dataset/main/"
    assert urls[raw + "data/core/kurals.jsonl"] == "application/jsonl"
    assert urls[raw + "release/croissant.json"] == "application/ld+json"
    assert urls[f"{REPO}/archive/refs/heads/main.zip"] == "application/zip"
    site = _node(page, "WebSite")
    assert site["name"] == "Thirukkural Tamil Dataset" and site["url"] == BASE + "/"
    for n in (1, 133):
        assert f'<a href="chapter/{n}/">' in page


def test_faq_jsonld_matches_faq_md(pages):
    page = pages["faq/index.html"]
    faq = _node(page, "FAQPage")
    questions = [q for q in faq["mainEntity"] if q["@type"] == "Question"]
    assert len(questions) == len(re.findall(r"^## ", FAQ_MD, re.M)) == page.count("<h2 id=")
    for q in questions:
        text = q["acceptedAnswer"]["text"]
        assert q["acceptedAnswer"]["@type"] == "Answer" and text
        assert "`" not in text and "**" not in text and "](" not in text


def test_faq_markdown_rendering():
    md = ("# Questions\n\n## What is **it**?\n\nSee [the `data`](../data) and [rules](licensing.md#cc0) or "
          "[home](https://example.org/x).\n\n- one `a`\n- two\n\n```python\n## not a question\nx = 1 < 2\n```\n\n"
          "## Second?\n\nதிருக்குறள் text.\n")
    page, n = faq_page(md)
    assert n == 2
    assert f'<a href="{REPO}/tree/main/data">the <code>data</code></a>' in page
    assert f'<a href="{REPO}/blob/main/docs/licensing.md#cc0">rules</a>' in page
    assert '<a href="https://example.org/x">home</a>' in page
    assert "<ul><li>one <code>a</code></li><li>two</li></ul>" in page
    assert '<pre><code class="language-python">## not a question\nx = 1 &lt; 2</code></pre>' in page
    assert '<h2 id="what-is-it">What is <strong>it</strong>?</h2>' in page
    assert '<span lang="ta">திருக்குறள்</span>' in page
    q = _node(page, "FAQPage")["mainEntity"]
    assert q[0]["name"] == "What is it?"
    assert q[0]["acceptedAnswer"]["text"] == "See the data and rules or home.\n\none a\ntwo\n\n## not a question\nx = 1 < 2"


def test_kural_page(pages):
    core = {k["number"]: k for k in load_tables()["kurals"]}
    page = pages["kural/2/index.html"]
    q = _node(page, "Quotation")
    assert q["inLanguage"] == "ta" and q["identifier"] == "tk:0002" and q["url"] == f"{BASE}/kural/2/"
    assert q["text"] == "\n".join(core[2]["lines_ta"])
    assert q["license"] == CC0 and q["author"]["name"] == "Thiruvalluvar"
    assert q["isBasedOn"] == sorted({p["source_id"] for p in core[2]["provenance"] if p["field"] == "lines_ta"})
    crumbs = [i["item"] for i in _node(page, "BreadcrumbList")["itemListElement"]]
    assert crumbs == [f"{BASE}/", f"{BASE}/chapter/1/", f"{BASE}/kural/2/"]
    for href in ("../../chapter/1/", "../1/", "../3/", REPO):
        assert f'href="{href}"' in page
    assert '<a href="../../">Thirukkural Tamil dataset</a>' in page
    assert '<blockquote lang="ta">' in page and "G. U. Pope" in page
    assert 'rel="prev"' not in pages["kural/1/index.html"] and 'rel="next"' not in pages["kural/1330/index.html"]


def test_kural_page_layout(pages):
    core = {k["number"]: k for k in load_tables()["kurals"]}
    page = pages["kural/2/index.html"]
    assert '<nav class="crumb" lang="en" aria-label="Breadcrumb"><ol><li><a href="../../">Home</a></li>' in page
    assert '<li aria-current="page">Kural 2</li>' in page
    lines = core[2]["lines_ta"]
    assert '<blockquote lang="ta"><p>' + " ".join(f"<span>{html.escape(l, quote=False)}</span>" for l in lines) in page
    assert page.count('<figure class="hero card">') == 1 and "Digital sources agree" in page
    assert 'data-tools' in page
    anchors = re.findall(r'<figure class="card" id="(tr-[a-z0-9-]+)"', page)
    assert anchors == ["tr-pope1886", "tr-drew-lazarus", "tr-aiyar1916"]
    nxt = core[3]["lines_ta"][0]
    assert f'<a class="card n" rel="next" href="../3/"><span class="dir">Kural 3 →</span><span class="snip" lang="ta">{nxt}</span>' in page
    assert '<a class="up" href="../../chapter/1/">Chapter 1</a>' in page
    assert 'class="card p"' not in pages["kural/1/index.html"] and 'class="card n"' not in pages["kural/1330/index.html"]
    assert page.count('class="rows"') == 1 and "text_sha256" in page


def test_chapter_page(pages):
    page = pages["chapter/2/index.html"]
    crumbs = [i["item"] for i in _node(page, "BreadcrumbList")["itemListElement"]]
    assert crumbs == [f"{BASE}/", f"{BASE}/chapter/2/"]
    for n in range(11, 21):
        assert f'href="../../kural/{n}/"' in page
    for href in ("../1/", "../3/", REPO):
        assert f'href="{href}"' in page
    assert '<a href="../../">Thirukkural Tamil dataset</a>' in page
    core = {k["number"]: k for k in load_tables()["kurals"]}
    first = core[11]["lines_ta"]
    assert f'<a class="card" href="../../kural/11/"><span class="no" lang="en">11</span><span class="cp"><span>{first[0]}</span><span>{first[1]}</span>' in page
    items = _node(page, "ItemList")
    assert items["numberOfItems"] == 10 == len(items["itemListElement"]) == page.count('class="card" href=')
    assert items["itemListElement"][0] == {"@type": "ListItem", "position": 1, "url": f"{BASE}/kural/11/", "name": first[0]}
    assert '<a class="up" href="../../#chapters">All chapters</a>' in page and 'rel="prev"' in page
    assert 'rel="prev"' not in pages["chapter/1/index.html"] and 'rel="next"' not in pages["chapter/133/index.html"]


def test_sitemap_lists_exactly_the_indexable_pages(site, pages):
    out, _ = site
    xml = _read(out / "sitemap.xml")
    locs = _locs(out)
    assert re.findall(r"<lastmod>([^<]*)</lastmod>", xml) == [RELEASE["date"]] * len(locs)
    indexed = {_canonical(p) for p in pages.values() if _meta(p, "robots") == "index,follow"}
    assert len(locs) == len(set(locs)) and set(locs) == indexed
    assert f"{BASE}/404.html" not in locs and _meta(pages["404.html"], "robots") == "noindex"


def test_robots(site):
    out, _ = site
    robots = _read(out / "robots.txt")
    assert robots.startswith("User-agent: *\nAllow: /\n")
    for bot in BOTS:
        assert f"User-agent: {bot}\nAllow: /\n" in robots
    assert "Disallow" not in robots and "#" not in robots
    assert f"Sitemap: {BASE}/sitemap.xml" in robots


def _header_rules(out):
    rules, cur = {}, None
    for line in _read(out / "_headers").splitlines():
        if line.startswith("/"):
            cur = rules.setdefault(line, [])
        elif line.strip():
            cur.append(line.strip())
    return rules


def test_headers_file(site):
    out, _ = site
    rules = _header_rules(out)
    everything = " ".join(rules["/*"])
    assert "X-Content-Type-Options: nosniff" in everything and "Referrer-Policy:" in everything
    assert "Permissions-Policy:" in everything and "Cross-Origin-Opener-Policy: same-origin" in everything
    csp = next(h for h in rules["/*"] if h.startswith("Content-Security-Policy:"))
    assert "unsafe-inline" not in csp and "http" not in csp and "default-src 'none'" in csp
    for path in ("/style.css", "/app.js", "/icons.svg", "/search.json"):
        assert "Cache-Control: public, max-age=31536000, immutable" in rules[path]
    assert "Cache-Control: public, max-age=0, must-revalidate" in rules["/kural/*"]
    assert any(h.startswith("Link: </llms.txt>") for h in rules["/"])
    assert "X-Robots-Tag: noindex" in rules["/404.html"]
    assert "Content-Type: text/plain; charset=utf-8" in rules["/llms.txt"]
    assert "Content-Type: application/xml; charset=utf-8" in rules["/sitemap.xml"]
    assert any(h.startswith("Content-Type: application/manifest+json") for h in rules["/site.webmanifest"])
    assert "Strict-Transport-Security" not in _read(out / "_headers")


def test_redirects_file(site):
    out, _ = site
    rules = [line.split() for line in _read(out / "_redirects").splitlines()]
    assert ["/kural", "/kural/1/", "302"] in rules and ["/chapter", "/chapter/1/", "302"] in rules
    assert ["/llms", "/llms.txt", "301"] in rules
    assert all(len(r) == 3 and r[1].startswith("/") for r in rules)


def test_wrangler_config():
    cfg = json.loads(_read(ROOT / "wrangler.jsonc"))
    assert cfg["name"] == "thirukkural-tamil-dataset" and "build" not in cfg
    assert cfg["routes"] == [{"pattern": urlsplit(BASE).netloc, "custom_domain": True}]
    assert cfg["assets"] == {"directory": "./docs", "not_found_handling": "404-page",
                             "html_handling": "auto-trailing-slash"}


def test_static_files(site):
    out, _ = site
    assert (out / ".nojekyll").read_bytes() == b""
    css = (out / "style.css").read_bytes()
    assert len(css) <= 14336 and b"color-scheme" in css and b"prefers-color-scheme" in css and b"light-dark(" in css
    assert (out / "social-preview.png").read_bytes() == (ROOT / ".github" / "assets" / "social-preview.png").read_bytes()
    assert (out / "favicon.png").exists()
    for name in ("llms.txt", "llms-full.txt"):
        src = ROOT / name
        assert (out / name).exists() == src.exists()
        if src.exists():
            assert (out / name).read_bytes() == src.read_bytes()


def test_landmarks_on_every_page(pages):
    for path, p in pages.items():
        assert p.count('<a class="skip"') == 1 and 'href="#main"' in p, path
        assert p.count("<header ") == 1 and p.count('<main id="main">') == 1 and p.count("<footer ") == 1, path
        assert p.index("<header ") < p.index("<main ") < p.index("<footer "), path
        assert p.count("<h1") == 1, path
        assert p.count('<meta name="theme-color"') == 2 and '<meta property="og:locale:alternate"' in p, path


def test_no_external_assets(pages):
    for path, p in pages.items():
        for tag, attrib in re.findall(r"<(link|script|img|use|source|iframe)\b[^>]*?\b(?:src|href)=\"([^\"]*)\"", p):
            if tag == "link" and 'rel="canonical"' in p and attrib == _canonical(p):
                continue
            assert not urlsplit(attrib).netloc or attrib.startswith(BASE + "/"), (path, tag, attrib)
        assert "style=" not in re.sub(r'<script type="application/ld\+json">.*?</script>', "", p, flags=re.S), path


def test_sprite_symbols_exist(site, pages):
    out, _ = site
    sprite = _read(out / "icons.svg")
    ids = set(re.findall(r'<symbol id="([^"]+)"', sprite))
    assert len(ids) == 15 and "ISC License" in sprite
    used = {i for p in pages.values() for i in re.findall(r'icons\.svg\?v=[0-9a-f]{8}#([a-z0-9-]+)', p)}
    assert used and used <= ids
    assert (out / "mark.svg").read_bytes() == (ROOT / ".github" / "assets" / "logo.svg").read_bytes()


def test_no_root_relative_hrefs_except_404(pages):
    for path, p in pages.items():
        if path != "404.html":
            assert not re.search(r'(?:href|src)="/[^/]', p), path
    assert "icons.svg" not in pages["404.html"]


def test_relative_links_resolve(site, pages):
    out, _ = site
    for path, page in pages.items():
        for ref in re.findall(r'(?:href|src)="([^"]*)"', page):
            if urlsplit(ref).scheme or ref.startswith(("#", "//")):
                continue
            assert path != "404.html", f"404.html must use absolute links: {ref}"
            target = (out / path).parent / urlsplit(ref).path
            if ref.endswith("/") or target.is_dir():
                target = target / "index.html"
            assert target.resolve().is_relative_to(out.resolve()) and target.is_file(), (path, ref)


def test_deterministic(site, tmp_path):
    out, _ = site
    again = tmp_path / "again"
    generate(again)
    files = lambda d: {p.relative_to(d).as_posix() for p in d.rglob("*") if p.is_file()}  # noqa: E731
    assert files(out) - files(again) == {"faq.md"} and files(again) <= files(out)
    for f in sorted(files(again)):
        assert (out / f).read_bytes() == (again / f).read_bytes(), f


def test_pending_kurals_are_noindex_and_absent_from_sitemap(tmp_path, a_hash):
    sid, sha = a_hash
    t = skeleton_tables()
    lines = [synthetic_line(4), synthetic_line(3)]
    t["kurals"][0].update(lines_ta=lines, text_status="verified_scan", provenance=[
        {"field": "lines_ta", "source_id": sid, "locator": "x", "source_sha256": sha, "license": "CC0-1.0"}])
    out = tmp_path / "docs"
    stats = generate(out, _core(tmp_path, t))
    assert stats["indexable_kurals"] == 1 and stats["sitemap_urls"] == 3
    assert _locs(out) == [f"{BASE}/", f"{BASE}/faq/", f"{BASE}/kural/1/"]
    done = _read(out / "kural" / "1" / "index.html")
    assert _meta(done, "robots") == "index,follow"
    q = _node(done, "Quotation")
    assert q["text"] == "\n".join(lines) and q["isBasedOn"] == [sid]
    pending = _read(out / "kural" / "2" / "index.html")
    assert _meta(pending, "robots") == "noindex,follow"
    assert "text" not in _node(pending, "Quotation") and "isBasedOn" not in _node(pending, "Quotation")
    assert _meta(_read(out / "chapter" / "1" / "index.html"), "robots") == "noindex,follow"
