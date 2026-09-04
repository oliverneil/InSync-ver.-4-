# InSync — preview site

Static preview build of the InSync Consulting Services site, for review before pasting into GoHighLevel.

## Why it's structured this way

In GHL the navigation and footer are **separate global blocks**, and each page holds only its own body
block. This repo mirrors that exactly:

```
partials/nav.html        the global nav block   (paste once into the GHL global nav)
partials/footer.html     the global footer block (paste once into the GHL global footer)
pages/<page>.html        body-only blocks       (paste one per page into a Custom Code element)
build.py                 wraps body + nav + footer into a complete page in dist/
pages.json               slug -> file, title, meta description, review status
```

Because `pages/*.html` are body-only, **the same file that builds the preview is the file you paste into
GHL** — no editing, no stripping, nothing to forget.

## Build

```bash
python3 build.py            # writes dist/
python3 build.py --serve    # builds, then serves on http://localhost:8000
```

Output URLs match the GHL slugs (`/healthcare-staffing/`, not `/healthcare-staffing.html`), so any
root-relative link that works here works there.

`dist/preview.html` is a reviewer index listing every built page and its status.

## Vercel

`vercel.json` is set up already:

- Build command `python3 build.py`, output directory `dist`
- `cleanUrls` + `trailingSlash` so the preview URLs match GHL

Steps: push this repo to GitHub → Vercel → **Add New Project** → import the repo → framework preset
**Other** (the JSON supplies the rest) → Deploy. Every push rebuilds.

## Adding a page

1. Drop the body-only block in `pages/` (e.g. `pages/healthcare-staffing.html`).
2. Add or update its entry in `pages.json` (`file`, `nav_label`, `status`, `title`, `description`).
3. `python3 build.py`.

Pages listed in `pages.json` whose body file is missing are skipped with a notice, so the manifest can run
ahead of the work.

## Design system

Every page follows the **InSync Motion Standards** skill (light Website Standards v1.0 skin + the
homepage's motion layer). Before editing any page, load that skill — it carries the tokens, the section
recipes, the motion engines, the GHL failure modes, and the audit/QA scripts.

Two checks before anything ships:

```bash
python3 audit.py OLD.html NEW.html        # copy diff, balances, banned patterns, palette, JS syntax
python3 qa_probe.py NEW.html all          # computed-value probes across 5 contexts
```

## Preview caveats

- The scroll-scrubbed hero video streams from the client CDN. It needs H.264 `.mp4`; `.mov` files are
  refused by Chrome. Band videos on Healthcare / Educational / Continuing Education are still `.mov` and
  need re-encoding.
- Contact form webhook URLs are placeholders until the GHL wiring is provided.
- This preview is for **layout, motion and copy review**. GHL adds its own wrappers, so a pinned section
  that behaves here can still fall back to native mode there — always confirm on the published GHL page,
  in an incognito window (GHL caches on publish).
