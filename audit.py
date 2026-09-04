#!/usr/bin/env python3
"""InSync Motion Standards — pre-delivery compliance audit.

Usage:
  python3 audit.py NEW.html                       # static checks only
  python3 audit.py OLD.html NEW.html              # + copy diff and balance deltas vs the previous build
  python3 audit.py OLD.html NEW.html --allow-removed "Candidate Pipeline" "Live"

Exit code 1 on any failure so it can gate a delivery.
"""
import re, sys, os, subprocess, argparse, tempfile

PALETTE = {'#0f1830','#16223f','#1b2746','#20335a','#2c4474','#3c4350','#6b7280',
           '#d54a1c','#e7eaef','#ef5a28','#f5f7fa','#ff7a4d'}
BANNED = [':root', 'position:sticky', 'position: sticky', 'overflow-x:hidden', 'overflow-x: hidden', 'LLC']

def texts(s):
    s = re.sub(r'<script.*?</script>', '', s, flags=re.S)
    s = re.sub(r'<style.*?</style>', '', s, flags=re.S)
    return [t.strip() for t in re.sub(r'<[^>]+>', '\n', s).split('\n') if t.strip()]

def balances(s):
    return {
        'div':   s.count('<div')  - s.count('</div>'),
        'span':  s.count('<span') - s.count('</span>'),
        'svg':   s.count('<svg')  - s.count('</svg>'),
        'brace': s.count('{')     - s.count('}'),
    }

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('files', nargs='+')
    ap.add_argument('--allow-removed', nargs='*', default=[])
    a = ap.parse_args()
    old = open(a.files[0]).read() if len(a.files) == 2 else None
    new = open(a.files[-1]).read()
    fails = []

    # --- balances
    b = balances(new)
    for k, v in b.items():
        if v != 0: fails.append(f'{k} balance {v:+d}')
    print('balances:', b)

    # --- banned patterns
    for p in BANNED:
        if p in new: fails.append(f'banned pattern present: {p!r}')
    print('banned:', {p: (p in new) for p in BANNED})

    # --- media URLs in attributes / CSS.
    # GHL corrupts VIDEO src/poster attributes and any RAW CDN url() — those must be JS runtime constants.
    # Images served through the images.leadconnectorhq.com WebP proxy are the sanctioned pattern (parent SOP)
    # and are allowed in <img src> and CSS url().
    video_attr = re.findall(r'(?:src|poster)\s*=\s*["\']https?://[^"\']+\.(?:mp4|mov|webm|m4v)', new)
    raw_css    = [u for u in re.findall(r'url\(\s*["\']?(https?://[^"\')\s]+)', new)
                  if 'assets.cdn.filesafe.space' in u and 'images.leadconnectorhq.com' not in u]
    raw_img    = [u for u in re.findall(r'<img[^>]+src\s*=\s*["\'](https?://[^"\']+)', new)
                  if 'assets.cdn.filesafe.space' in u and 'images.leadconnectorhq.com' not in u]
    if video_attr: fails.append(f'video URL in attribute (must be a JS constant): {video_attr[:3]}')
    if raw_css:    fails.append(f'raw CDN URL in CSS url() (use the WebP proxy or a JS constant): {raw_css[:3]}')
    if raw_img:    print(f'WARN raw CDN <img src> (prefer the WebP proxy; body images especially): {raw_img[:3]}')
    mov = re.findall(r'https?://[^"\')\s]+\.mov\b', new)
    if mov: fails.append(f'.mov video referenced (Chrome refuses the container; re-encode to H.264 .mp4): {mov[:3]}')

    # --- hexes
    hexes = set(h.lower() for h in re.findall(r'#[0-9a-fA-F]{6}\b', new))
    off = sorted(hexes - PALETTE)
    if off: fails.append(f'off-palette hex: {off}')
    print('hexes:', sorted(hexes), '| off-palette:', off)

    # --- border-radius:50% inventory (report; justify each)
    rounds = [m.group(0)[:90] for m in re.finditer(r'[^\n]*border-radius:\s*50%[^\n]*', new)]
    print(f'border-radius:50% occurrences: {len(rounds)}')
    for r in rounds: print('   ', r.strip())

    # --- JS syntax
    scripts = re.findall(r'<script>(.*?)</script>', new, re.S)
    bad = 0
    with tempfile.TemporaryDirectory() as d:
        for i, js in enumerate(scripts):
            p = os.path.join(d, f's{i}.js'); open(p, 'w').write(js)
            r = subprocess.run(['node', '--check', p], capture_output=True, text=True)
            if r.returncode:
                bad += 1; print(f'JS FAIL block {i}:', r.stderr.strip()[:200])
    if bad: fails.append(f'{bad} script block(s) fail node --check')
    print(f'{len(scripts)} script blocks, {bad} failures')

    # --- copy diff vs previous build
    if old is not None:
        ta, tb = texts(old), texts(new)
        removed = [t for t in ta if t not in tb]
        added   = [t for t in tb if t not in ta]
        unexpected = [t for t in removed if t not in a.allow_removed]
        print('copy removed:', removed)
        print('copy added  :', added)
        if unexpected: fails.append(f'copy removed without approval: {unexpected}')
        if added:      fails.append(f'copy added: {added}')
        ob = balances(old)
        for k in b:
            if b[k] != ob[k]: print(f'note: {k} balance changed {ob[k]} -> {b[k]}')

    print('\nRESULT:', 'PASS' if not fails else 'FAIL')
    for f in fails: print('  -', f)
    sys.exit(1 if fails else 0)

if __name__ == '__main__':
    main()
