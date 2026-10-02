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
<link rel="icon" href="data:image/png;base64,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" type="image/png">
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
        # '404' is special: Vercel serves /404.html for unmatched routes, so it is
        # written as a FILE at the output root, not as /404/index.html.
        if slug == '404':
            out = os.path.join(DIST, '404.html')
        else:
            out_dir = DIST if slug == 'index' else os.path.join(DIST, slug)
            os.makedirs(out_dir, exist_ok=True)
            out = os.path.join(out_dir, 'index.html')
        with open(out, 'w', encoding='utf-8') as f:
            f.write(html)
        built.append((slug, os.path.relpath(out, ROOT), len(html)))

    # a tiny index of what's live, for the reviewer
    links = '\n'.join(
        f'    <li><a href="/{"" if s == "index" else s + "/"}">{PAGE_META[s]["nav_label"]}</a>'
        f' <span>{PAGE_META[s]["status"]}</span></li>' for s, _, _ in built if s != '404')
    with open(os.path.join(DIST, 'preview.html'), 'w', encoding='utf-8') as f:
        f.write(PREVIEW.format(links=links))

    # 404: use the real branded page when pages/404.html exists (it is built above);
    # otherwise fall back to a plain index of what IS in the preview, so a reviewer
    # clicking an unbuilt nav link doesn't hit a bare server error.
    if not any(s == '404' for s, _, _ in built):
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
