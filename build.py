#!/usr/bin/env python3
"""InSync preview site builder.

Wraps each body-only page in `pages/` with the shared nav + footer partials and writes a complete
HTML document to `dist/`. This mirrors GoHighLevel exactly: in GHL the nav and footer are separate
global blocks and each page holds only its body block, so `pages/*.html` are paste-ready for GHL
without any edit.

Usage:
    python3 build.py            # build everything into dist/
    python3 build.py --serve    # build, then serve dist/ on http://localhost:8000
"""
import os, re, json, shutil, argparse, http.server, socketserver, functools

ROOT = os.path.dirname(os.path.abspath(__file__))
PAGES, PARTIALS, DIST = (os.path.join(ROOT, d) for d in ('pages', 'partials', 'dist'))

# slug -> (output path, <title>, meta description)
# Output paths are directories with an index.html so URLs match GHL slugs exactly
# (/healthcare-staffing/ not /healthcare-staffing.html).
with open(os.path.join(ROOT, 'pages.json')) as f:
    PAGE_META = json.load(f)

SHELL = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<meta name="description" content="{description}">
<link rel="icon" href="https://assets.cdn.filesafe.space/lAvsV54bgyIkgTbpk5QX/media/691ce4ae0eb06d4bb0525b2a.png" type="image/png">
<style>html,body{{margin:0;padding:0;background:#fff}}</style>
</head>
<body>
{nav}

{body}

{footer}
</body>
</html>
"""

def read(p):
    with open(p, encoding='utf-8') as f:
        return f.read()

def build():
    nav, footer = read(os.path.join(PARTIALS, 'nav.html')), read(os.path.join(PARTIALS, 'footer.html'))
    if os.path.isdir(DIST):
        shutil.rmtree(DIST)
    os.makedirs(DIST, exist_ok=True)

    built, missing = [], []
    for slug, meta in PAGE_META.items():
        src = os.path.join(PAGES, meta['file'])
        if not os.path.exists(src):
            missing.append(meta['file']); continue
        html = SHELL.format(title=meta['title'], description=meta['description'],
                            nav=nav, body=read(src), footer=footer)
        out_dir = DIST if slug == 'index' else os.path.join(DIST, slug)
        os.makedirs(out_dir, exist_ok=True)
        out = os.path.join(out_dir, 'index.html')
        with open(out, 'w', encoding='utf-8') as f:
            f.write(html)
        built.append((slug, os.path.relpath(out, ROOT), len(html)))

    # a tiny index of what's live, for the reviewer
    links = '\n'.join(
        f'    <li><a href="/{"" if s == "index" else s + "/"}">{PAGE_META[s]["nav_label"]}</a>'
        f' <span>{PAGE_META[s]["status"]}</span></li>' for s, _, _ in built)
    with open(os.path.join(DIST, 'preview.html'), 'w', encoding='utf-8') as f:
        f.write(PREVIEW.format(links=links))

    # 404: the nav links to pages that aren't in this preview yet (About, Contact,
    # Apply Now, Employee Hub...). Without this a reviewer clicking one gets a bare
    # server error and thinks the build is broken.
    with open(os.path.join(DIST, '404.html'), 'w', encoding='utf-8') as f:
        f.write(NOT_FOUND.format(links=links))

    print(f'built {len(built)} page(s):')
    for slug, path, size in built:
        print(f'  {slug:24s} -> {path:44s} {size/1024:7.1f} KB')
    if missing:
        print('\nnot built (body file not in pages/):')
        for m in missing:
            print('  -', m)
    print(f'\nreviewer index: dist/preview.html')
    return built

PREVIEW = """<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>InSync — preview index</title>
<link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;600;700;800&display=swap" rel="stylesheet">
<style>
body{{margin:0;background:#f5f7fa;font:16px/1.7 'Plus Jakarta Sans',system-ui,sans-serif;color:#3c4350}}
.w{{max-width:760px;margin:0 auto;padding:64px 24px}}
h1{{font-size:2rem;font-weight:800;color:#1b2746;letter-spacing:-.02em;margin:0 0 6px}}
p.lead{{color:#6b7280;margin:0 0 32px}}
ul{{list-style:none;padding:0;margin:0}}
li{{background:#fff;border:1px solid #e7eaef;border-radius:16px;margin-bottom:12px;
   box-shadow:0 2px 14px rgba(22,34,63,.06);transition:box-shadow .25s cubic-bezier(.22,1,.36,1)}}
li:hover{{box-shadow:0 18px 48px rgba(22,34,63,.12)}}
li a{{display:flex;justify-content:space-between;align-items:center;gap:16px;
     padding:18px 22px;text-decoration:none;color:#1b2746;font-weight:700}}
li span{{font-size:.74rem;font-weight:700;letter-spacing:.14em;text-transform:uppercase;color:#ef5a28}}
</style></head><body><div class="w">
<h1>InSync — preview build</h1>
<p class="lead">Body blocks wrapped with the live nav and footer. Test on desktop and a real phone.</p>
<ul>
{links}
</ul>
</div></body></html>
"""

NOT_FOUND = """<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Not in this preview yet — InSync</title>
<link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;600;700;800&display=swap" rel="stylesheet">
<style>
body{{margin:0;background:#f5f7fa;font:16px/1.7 'Plus Jakarta Sans',system-ui,sans-serif;color:#3c4350}}
.w{{max-width:640px;margin:0 auto;padding:88px 24px;text-align:center}}
h1{{font-size:2rem;font-weight:800;color:#1b2746;letter-spacing:-.02em;margin:0 0 10px}}
p{{color:#6b7280;margin:0 0 30px}}
ul{{list-style:none;padding:0;margin:0;text-align:left}}
li{{background:#fff;border:1px solid #e7eaef;border-radius:16px;margin-bottom:10px}}
li a{{display:flex;justify-content:space-between;padding:15px 20px;text-decoration:none;color:#1b2746;font-weight:700}}
li span{{font-size:.72rem;letter-spacing:.14em;text-transform:uppercase;color:#ef5a28}}
</style></head><body><div class="w">
<h1>Not in this preview yet</h1>
<p>That page exists on the live site but hasn&rsquo;t been added to this preview build. Here&rsquo;s what is:</p>
<ul>
{links}
</ul>
</div></body></html>
"""

def serve():
    os.chdir(DIST)
    handler = functools.partial(http.server.SimpleHTTPRequestHandler)
    with socketserver.TCPServer(('', 8000), handler) as httpd:
        print('serving dist/ at http://localhost:8000  (Ctrl-C to stop)')
        httpd.serve_forever()

if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--serve', action='store_true')
    a = ap.parse_args()
    build()
    if a.serve:
        serve()
