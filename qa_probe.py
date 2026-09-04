#!/usr/bin/env python3
"""InSync Motion Standards — Playwright probes.

Prepares a QA copy of the page with the CDN video swapped for a local pure-red stub, serves it with a
Range-capable server, and runs the probe(s) requested. Every probe measures COMPUTED results (pixels,
computed transforms, scrollLeft) — never just class names or inline strings.

Usage:
  python3 qa_probe.py PAGE.html all
  python3 qa_probe.py PAGE.html pixel-row handoff tilt hover-grid swipe arrows gate pin-measure topbar contexts
  python3 qa_probe.py PAGE.html tilt --sel ".tl .step"        # any card family
  python3 qa_probe.py PAGE.html pixel-row --y 500 --xs .05 .25 .5 .75 .95

Requires: playwright (PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers), ffmpeg, RangeHTTPServer, Pillow.
Screenshots land in ./qa_out/.
"""
import asyncio, os, re, sys, io, statistics, subprocess, argparse, time, signal
os.environ.setdefault('PLAYWRIGHT_BROWSERS_PATH', '/opt/pw-browsers')
from playwright.async_api import async_playwright
from PIL import Image

PORT = 8100
OUT = 'qa_out'
VIDEO_RE = re.compile(r'https://assets\.cdn\.filesafe\.space/[^\'"]+\.(?:mp4|mov)')

# ------------------------------------------------------------------ setup
def prepare(page_path):
    os.makedirs(OUT, exist_ok=True)
    stub = os.path.join(OUT, 'stub-red.webm')
    if not os.path.exists(stub):
        subprocess.run(['ffmpeg', '-loglevel', 'error', '-y', '-f', 'lavfi', '-i',
                        'color=c=red:s=640x360:d=4:r=24', '-c:v', 'libvpx-vp9', '-b:v', '200k', '-g', '12', stub],
                       check=True)
    s = open(page_path).read()
    s = VIDEO_RE.sub(f'http://127.0.0.1:{PORT}/stub-red.webm', s)
    open(os.path.join(OUT, 'qa_page.html'), 'w').write(s)

def serve():
    p = subprocess.Popen([sys.executable, '-m', 'RangeHTTPServer', str(PORT)], cwd=OUT,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    time.sleep(1.2)
    return p

URL = f'http://127.0.0.1:{PORT}/qa_page.html'

def bg_median(im, fx, y0=150, y1=None, step=6):
    """median R of pure-red (background-only) pixels in a vertical strip at fx."""
    w, h = im.size; x = int(w * fx); y1 = y1 or h - 40; vals = []
    for y in range(y0, y1, step):
        r, g, b = im.getpixel((x, y))
        if g < 10 and b < 10: vals.append(r)
    return statistics.median(vals) if vals else None

async def wheel_until(pg, js_cond, step=220, max_steps=300, wait=38):
    for _ in range(max_steps):
        if await pg.evaluate(js_cond): return True
        await pg.mouse.wheel(0, step); await pg.wait_for_timeout(wait)
    return False

# ------------------------------------------------------------------ probes
async def probe_pixel_row(pw, a):
    b = await pw.chromium.launch(); pg = await b.new_page(viewport={'width': 1440, 'height': 900})
    await pg.goto(URL); await pg.wait_for_timeout(3000)
    im = Image.open(io.BytesIO(await pg.screenshot())).convert('RGB')
    y = a.y
    print(f'pixel-row @y={y} (R of pure-red bg; lower = darker; * = text/UI pixel):')
    for fx in a.xs:
        px = im.getpixel((int(im.size[0] * fx), y))
        print(f'  {int(fx*100):3d}%: R={px[0]:3d}' + (' *' if px[1] > 10 or px[2] > 10 else ''))
    im.save(f'{OUT}/pixel_row.png'); await b.close()

async def probe_handoff(pw, a):
    b = await pw.chromium.launch(); pg = await b.new_page(viewport={'width': 1440, 'height': 900})
    await pg.goto(URL); await pg.wait_for_timeout(2500)
    print(' scrollY | grad shade |  L(8%)  M(50%)  R(94%)')
    prev = None; rev = []
    for _ in range(28):
        v = await pg.evaluate("""()=>{const g=document.querySelector('.ins-scrub__grad'),s=document.querySelector('.ins-scrub__shade');
          return {y:Math.round(scrollY), g:+getComputedStyle(g).opacity, s:+getComputedStyle(s).opacity};}""")
        im = Image.open(io.BytesIO(await pg.screenshot())).convert('RGB')
        s = [bg_median(im, f) for f in (.08, .50, .94)]
        print(f"{v['y']:8d} | {v['g']:.2f} {v['s']:.2f} | {str(s[0]):>6} {str(s[1]):>7} {str(s[2]):>7}")
        if prev:
            for k in range(3):
                if s[k] is not None and prev[k] is not None and s[k] - prev[k] > 8:
                    rev.append((v['y'], 'LMR'[k], prev[k], s[k]))
        prev = s
        await pg.mouse.wheel(0, 60); await pg.wait_for_timeout(170)
    print('lightening steps >8/255:', rev if rev else 'NONE — monotonic')
    await b.close()

async def probe_tilt(pw, a):
    b = await pw.chromium.launch(); pg = await b.new_page(viewport={'width': a.width, 'height': a.height})
    await pg.goto(URL); await pg.wait_for_timeout(2500)
    n = await pg.evaluate(f"()=>document.querySelectorAll('{a.sel}').length")
    print(f'tilt on {a.sel!r}: {n} elements')
    # wheel into the region first so the scroll-driven engines (hero morph, pins) have painted;
    # a bare scrollBy from page top can leave a fixed layer over the first card for one frame
    await wheel_until(pg, f"()=>{{const e=document.querySelector('{a.sel}');return e&&e.getBoundingClientRect().top<innerHeight}}")
    await pg.wait_for_timeout(600)
    for i in range(n):
        m = None
        for attempt in range(2):
            await pg.evaluate(f"""()=>{{const s=document.querySelectorAll('{a.sel}')[{i}];
              const r=s.getBoundingClientRect(); window.scrollBy(0, r.top + r.height/2 - innerHeight/2);}}""")
            await pg.wait_for_timeout(500)
            el = (await pg.query_selector_all(a.sel))[i]; box = await el.bounding_box()
            if not box: break
            await pg.mouse.move(5, 5); await pg.wait_for_timeout(200)
            await pg.mouse.move(box['x'] + box['width'] * .85, box['y'] + box['height'] * .5); await pg.wait_for_timeout(400)
            glow = await pg.evaluate(f"()=>document.querySelectorAll('{a.sel}')[{i}].classList.contains('is-glow')")
            if glow: break
        if not box: print(f'  #{i+1}: no box'); continue
        m = await pg.evaluate(f"""()=>{{const s=document.querySelectorAll('{a.sel}')[{i}]; const cs=getComputedStyle(s);
          let ry='n/a'; if(cs.transform.startsWith('matrix3d')){{const v=cs.transform.slice(9,-1).split(',').map(Number);
            ry=(Math.asin(Math.max(-1,Math.min(1,v[8])))*180/Math.PI).toFixed(2)+'deg';}}
          return {{ry, trans:cs.transitionProperty+' / '+cs.transitionDelay, inlineDelay:s.style.transitionDelay||'(none)',
                   glow:s.classList.contains('is-glow')}};}}""")
        ok = m['ry'] != 'n/a' and abs(float(m['ry'][:-3])) > 2
        print(f"  #{i+1}: computed rotateY {m['ry']:>8} {'OK ' if ok else 'FAIL'} | transition {m['trans']} | inline delay {m['inlineDelay']} | glow {m['glow']}")
    await b.close()

async def probe_hover_grid(pw, a):
    b = await pw.chromium.launch(); pg = await b.new_page(viewport={'width': a.width, 'height': a.height})
    await pg.goto(URL); await pg.wait_for_timeout(2500)
    n = await pg.evaluate(f"()=>document.querySelectorAll('{a.sel}').length")
    for i in range(n):
        await pg.evaluate(f"""()=>{{const s=document.querySelectorAll('{a.sel}')[{i}];
          const r=s.getBoundingClientRect(); window.scrollBy(0, r.top + r.height/2 - innerHeight/2);}}""")
        await pg.wait_for_timeout(450)
        el = (await pg.query_selector_all(a.sel))[i]; box = await el.bounding_box(); fails = []
        for fx, fy in [(.15,.2),(.5,.2),(.85,.2),(.15,.5),(.5,.5),(.85,.5),(.15,.85),(.5,.85),(.85,.85)]:
            cx, cy = box['x'] + box['width'] * fx, box['y'] + box['height'] * fy
            await pg.mouse.move(5, 5); await pg.wait_for_timeout(100)
            await pg.mouse.move(cx, cy); await pg.wait_for_timeout(250)
            ok = await pg.evaluate(f"()=>document.querySelectorAll('{a.sel}')[{i}].classList.contains('is-glow')")
            if not ok:
                hit = await pg.evaluate(f"""()=>{{const e=document.elementFromPoint({cx},{cy});
                  return e?e.tagName+'.'+(e.className.baseVal!==undefined?e.className.baseVal:e.className):'none';}}""")
                fails.append(f'({fx},{fy})->{hit[:40]}')
        print(f'  #{i+1}: ' + ('all 9 points OK' if not fails else 'FAIL at ' + ', '.join(fails)))
    await b.close()

async def cdp_swipe(cdp, x0, y0, x1, y1, steps=12):
    await cdp.send('Input.dispatchTouchEvent', {'type': 'touchStart', 'touchPoints': [{'x': x0, 'y': y0}]})
    for i in range(1, steps + 1):
        await cdp.send('Input.dispatchTouchEvent', {'type': 'touchMove', 'touchPoints': [{'x': x0 + (x1-x0)*i/steps, 'y': y0 + (y1-y0)*i/steps}]})
        await asyncio.sleep(0.016)
    await cdp.send('Input.dispatchTouchEvent', {'type': 'touchEnd', 'touchPoints': []})

async def probe_swipe(pw, a):
    b = await pw.chromium.launch(); pg = await b.new_page(viewport={'width': 390, 'height': 844}, has_touch=True, is_mobile=True)
    await pg.goto(URL); await pg.wait_for_timeout(2500); cdp = await pg.context.new_cdp_session(pg)
    roots = await pg.evaluate("()=>[...document.querySelectorAll('.pcx')].map(r=>r.id||r.className)")
    for idx, name in enumerate(roots):
        R = f"document.querySelectorAll('.pcx')[{idx}]"
        await pg.evaluate(f"()=>{{const r={R}.querySelector('.pcx__viewport').getBoundingClientRect(); window.scrollBy(0, r.top + r.height/2 - innerHeight/2);}}")
        await pg.wait_for_timeout(700)
        box = await pg.evaluate(f"()=>{{const r={R}.querySelector('.pcx__viewport').getBoundingClientRect(); return {{x:r.left+r.width*.8,y:r.top+r.height*.5,x2:r.left+r.width*.2}};}}")
        before = await pg.evaluate(f"()=>{R}.querySelector('.pcx__viewport').scrollLeft")
        await cdp_swipe(cdp, box['x'], box['y'], box['x2'], box['y'] + 18); await pg.wait_for_timeout(900)
        after = await pg.evaluate(f"()=>{R}.querySelector('.pcx__viewport').scrollLeft")
        act = await pg.evaluate(f"()=>[...{R}.querySelectorAll('.pcx__card')].findIndex(c=>c.classList.contains('is-active'))")
        snap = await pg.evaluate(f"()=>getComputedStyle({R}.querySelector('.pcx__viewport')).scrollSnapType")
        print(f'  {name}: scrollLeft {before} -> {after} {"OK" if after>before+50 else "FAIL"} | active {act} | snap-type {snap} (must be none in native)')
    await b.close()

async def probe_arrows(pw, a):
    b = await pw.chromium.launch(); pg = await b.new_page(viewport={'width': 390, 'height': 844}, has_touch=True, is_mobile=True)
    await pg.goto(URL); await pg.wait_for_timeout(2500)
    n = await pg.evaluate("()=>document.querySelectorAll('.pcx').length")
    for idx in range(n):
        R = f"document.querySelectorAll('.pcx')[{idx}]"
        await pg.evaluate(f"()=>{{const r={R}.querySelector('.pcx__viewport').getBoundingClientRect(); window.scrollBy(0, r.top + r.height/2 - innerHeight/2);}}")
        await pg.wait_for_timeout(600)
        info = await pg.evaluate(f"""()=>{{const R={R}; const vp=R.querySelector('.pcx__viewport'), p=R.querySelector('.pcx__arrow--prev'), nx=R.querySelector('.pcx__arrow--next');
          if(!p||!nx) return null; const vr=vp.getBoundingClientRect(), pr=p.getBoundingClientRect(), nr=nx.getBoundingClientRect();
          return {{centred: Math.abs((pr.top+pr.height/2)-(vr.top+vr.height/2))<4 && Math.abs((nr.top+nr.height/2)-(vr.top+vr.height/2))<4,
                   prevDisabledAtStart:p.disabled}};}}""")
        if not info: print(f'  track {idx}: no arrows (pinned mode?)'); continue
        for _ in range(2): await pg.evaluate(f"()=>{R}.querySelector('.pcx__arrow--next').click()"); await pg.wait_for_timeout(700)
        a2 = await pg.evaluate(f"()=>[...{R}.querySelectorAll('.pcx__card')].findIndex(c=>c.classList.contains('is-active'))")
        await pg.evaluate(f"()=>{R}.querySelector('.pcx__arrow--prev').click()"); await pg.wait_for_timeout(700)
        a1 = await pg.evaluate(f"()=>[...{R}.querySelectorAll('.pcx__card')].findIndex(c=>c.classList.contains('is-active'))")
        print(f'  track {idx}: centred {info["centred"]} | prev disabled at start {info["prevDisabledAtStart"]} | next×2→{a2} prev×1→{a1} {"OK" if (a2,a1)==(2,1) else "FAIL"}')
    await b.close()

async def probe_gate(pw, a):
    b = await pw.chromium.launch(); pg = await b.new_page(viewport={'width': 1440, 'height': 900})
    await pg.goto(URL); await pg.wait_for_timeout(2500)
    pre = await pg.evaluate("""()=>[...document.querySelectorAll('.tl .step')].map((s,i)=>{const el=s.querySelector('.step__viz [class*="sv-a"]');
      return {step:i+1,on:s.classList.contains('on'),play:el?getComputedStyle(el).animationPlayState:'n/a'};})""")
    print('at load:'); [print('  ', r, '' if (r['on'] or r['play']=='paused') else '<-- FAIL (running before activation)') for r in pre]
    await wheel_until(pg, "()=>{const e=document.getElementById('process');return e&&e.getBoundingClientRect().top<120}")
    for _ in range(16): await pg.mouse.wheel(0, 150); await pg.wait_for_timeout(110)
    await pg.wait_for_timeout(1200)
    post = await pg.evaluate("""()=>[...document.querySelectorAll('.tl .step')].map((s,i)=>{const parts=[...s.querySelectorAll('.step__viz [class*="sv-a"]')];
      return {step:i+1,on:s.classList.contains('on'),running:parts.filter(p=>getComputedStyle(p).animationPlayState==='running').length+'/'+parts.length};})""")
    print('after scroll:'); [print('  ', r) for r in post]
    await b.close()

async def probe_pin_measure(pw, a):
    for w, h in ((1440, 900), (1366, 768)):
        b = await pw.chromium.launch(); pg = await b.new_page(viewport={'width': w, 'height': h})
        await pg.goto(URL); await pg.wait_for_timeout(2200)
        pinned = await wheel_until(pg, "()=>{const s=document.getElementById('psxStage');return s&&getComputedStyle(s).position==='fixed'}", step=140, wait=55)
        await pg.mouse.wheel(0, 140); await pg.wait_for_timeout(600)
        m = await pg.evaluate("""()=>{const c=document.querySelector('#psxTrack .pcx__card'),eb=document.querySelector('#specialties .eyebrow'),
          nav=document.querySelector('.ins-nav'),hint=document.getElementById('psxHint'); const r=e=>e.getBoundingClientRect();
          return {clear:Math.round(r(eb).top-r(nav).bottom),cardB:Math.round(r(c).bottom),hintB:hint?Math.round(r(hint).bottom):0};}""")
        print(f'  {w}x{h}: pinned={pinned} | eyebrow clearance {m["clear"]}px | card bottom {m["cardB"]}/{h} fits={m["cardB"]<=h} | hint bottom {m["hintB"]}')
        await b.close()

async def probe_topbar(pw, a):
    b = await pw.chromium.launch(); pg = await b.new_page(viewport={'width': 1440, 'height': 900})
    await pg.goto(URL); await pg.wait_for_timeout(2200)
    P = """()=>{const h=document.getElementById('insHeader'),tb=document.querySelector('.ins-topbar'),sp=document.getElementById('insSpacer');
      if(!h) return 'no header in this file'; return {y:Math.round(pageYOffset),scrolled:h.classList.contains('ins-scrolled'),
      barH:Math.round(tb.getBoundingClientRect().height),headerH:h.offsetHeight,spacerH:Math.round(parseFloat(sp.style.height||0))};}"""
    print('  top     :', await pg.evaluate(P))
    for _ in range(6): await pg.mouse.wheel(0, 120); await pg.wait_for_timeout(60)
    await pg.wait_for_timeout(900); print('  scrolled:', await pg.evaluate(P))
    await pg.evaluate("()=>scrollTo(0,0)"); await pg.wait_for_timeout(900); print('  back    :', await pg.evaluate(P))
    await b.close()

async def probe_contexts(pw, a):
    ctxs = [('desktop 1440', dict(viewport={'width':1440,'height':900})),
            ('short 1366  ', dict(viewport={'width':1366,'height':768})),
            ('tablet 768  ', dict(viewport={'width':768,'height':1024}, has_touch=True)),
            ('mobile 390  ', dict(viewport={'width':390,'height':844}, has_touch=True, is_mobile=True)),
            ('reduced     ', dict(viewport={'width':1440,'height':900}, reduced_motion='reduce'))]
    for tag, kw in ctxs:
        b = await pw.chromium.launch(); pg = await b.new_page(**kw); errs = []
        pg.on('pageerror', lambda e: errs.append(str(e)))
        await pg.goto(URL); await pg.wait_for_timeout(2200)
        for _ in range(120): await pg.mouse.wheel(0, 300); await pg.wait_for_timeout(25)
        await pg.wait_for_timeout(1200)
        m = await pg.evaluate("""()=>({modes:[...document.querySelectorAll('.pcx')].map(r=>r.classList.contains('pcx--pinned')?'pinned':r.classList.contains('pcx--native')?'native':'?'),
          arrows:document.querySelectorAll('.pcx__arrow').length, revealed:document.querySelectorAll('.reveal.in').length+'/'+document.querySelectorAll('.reveal').length,
          stepsOn:document.querySelectorAll('.tl .step.on').length, spot:(()=>{const s=document.querySelector('.step__spot');return s?getComputedStyle(s).display:'n/a'})()})""")
        print(f'  {tag}: modes {m["modes"]} | arrows {m["arrows"]} | revealed {m["revealed"]} | steps on {m["stepsOn"]} | spotlight {m["spot"]} | JS errors {len(errs)}')
        await b.close()

PROBES = {'pixel-row': probe_pixel_row, 'handoff': probe_handoff, 'tilt': probe_tilt, 'hover-grid': probe_hover_grid,
          'swipe': probe_swipe, 'arrows': probe_arrows, 'gate': probe_gate, 'pin-measure': probe_pin_measure,
          'topbar': probe_topbar, 'contexts': probe_contexts}

async def main(a):
    prepare(a.page); srv = serve()
    try:
        async with async_playwright() as pw:
            for name in (PROBES.keys() if 'all' in a.probes else a.probes):
                print(f'\n=== {name} ==='); await PROBES[name](pw, a)
    finally:
        os.killpg(os.getpgid(srv.pid), signal.SIGTERM)

if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('page'); ap.add_argument('probes', nargs='+')
    ap.add_argument('--sel', default='.tl .step'); ap.add_argument('--width', type=int, default=1440); ap.add_argument('--height', type=int, default=900)
    ap.add_argument('--y', type=int, default=200); ap.add_argument('--xs', type=float, nargs='*', default=[.05,.25,.5,.75,.95])
    asyncio.run(main(ap.parse_args()))
