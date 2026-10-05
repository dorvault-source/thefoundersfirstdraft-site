"""Builds the interior pages from one shared head/header/footer.
Run: python3 build.py   (index.html is hand-written; the header, footer, fonts,
stylesheet tag and analytics snippet are all copied from it, so edit them there).
404.html is hand-written too and is never touched: it needs root-absolute links."""
import datetime, html, json, os, pathlib, re, sys

ROOT = pathlib.Path(__file__).parent
SITE = "https://thefoundersfirstdraft.com"
# BUILD_DATE=YYYY-MM-DD previews the site as it will look on that day.
TODAY = datetime.date.fromisoformat(os.environ.get("BUILD_DATE") or datetime.date.today().isoformat())
index = (ROOT / "index.html").read_text()

# ---------- Episode data ----------
# One file per episode in episodes/data/<slug>.json. That folder is public (the repo
# and the site both serve it), so only recorded episodes belong there. Unrecorded
# guests go in episodes/data/drafts/, which git ignores. Files starting with _ are
# examples: they are checked but never built.
EPISODE_FIELDS = {
    "number": int, "slug": str, "guest": str, "company": str, "lesson": str,
    "summary": str, "lede": str, "date": str, "length_min": int, "youtube_id": (str, type(None)),
    "takeaways": list, "timestamps": list, "bio": str, "links": list, "transcript": list,
    "recorded": bool,
}

def check_episode(ep, name):
    """Returns a list of problems with one episode's data (empty if it's fine)."""
    errs = [f"missing field '{k}'" for k in EPISODE_FIELDS if k not in ep]
    errs += [f"unknown field '{k}' (typo?)" for k in ep if k not in EPISODE_FIELDS]
    for k, t in EPISODE_FIELDS.items():
        if k in ep and (not isinstance(ep[k], t) or (t is int and isinstance(ep[k], bool))):
            errs.append(f"'{k}' has the wrong type")
    if errs:
        return errs
    for k, t in EPISODE_FIELDS.items():
        if t is str and not ep[k].strip():
            errs.append(f"'{k}' is empty")
    if ep["recorded"] is not True:
        errs.append("'recorded' is false: unrecorded guests must stay in episodes/data/drafts/, never in a public file")
    if not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", ep["slug"]):
        errs.append("'slug' must be lowercase words joined by hyphens")
    elif not name.startswith("_") and ep["slug"] != name:
        errs.append(f"'slug' is '{ep['slug']}' but the file is named {name}.json")
    if ep["number"] < 1: errs.append("'number' must be 1 or more")
    if ep["length_min"] < 1: errs.append("'length_min' must be 1 or more")
    if len(ep["summary"]) > 160: errs.append(f"'summary' is {len(ep['summary'])} characters; keep it near 150")
    try:
        released = datetime.date.fromisoformat(ep["date"]) <= TODAY
    except ValueError:
        errs.append("'date' must be YYYY-MM-DD"); released = False
    if ep["youtube_id"] is None:
        if released: errs.append("'youtube_id' is required once the episode is out")
    elif not re.fullmatch(r"[A-Za-z0-9_-]{11}", ep["youtube_id"]):
        errs.append("'youtube_id' should be the 11-character ID from the video URL, not the whole URL")
    if not ep["takeaways"] or not all(isinstance(x, str) and x.strip() for x in ep["takeaways"]):
        errs.append("'takeaways' must be a list of non-empty sentences")
    if not ep["transcript"] or not all(isinstance(x, str) and x.strip() for x in ep["transcript"]):
        errs.append("'transcript' must be a list of non-empty paragraphs")
    for i, ts in enumerate(ep["timestamps"]):
        if not (isinstance(ts, dict) and set(ts) == {"t", "topic"} and isinstance(ts["topic"], str) and ts["topic"].strip()
                and isinstance(ts["t"], str) and re.fullmatch(r"(\d+:)?[0-5]?\d:[0-5]\d", ts["t"])):
            errs.append(f"timestamps[{i}] must look like {{\"t\": \"12:34\", \"topic\": \"...\"}}")
    for i, ln in enumerate(ep["links"]):
        if not (isinstance(ln, dict) and set(ln) == {"label", "url"} and isinstance(ln["label"], str) and ln["label"].strip()
                and isinstance(ln["url"], str) and re.fullmatch(r"https?://\S+", ln["url"])):
            errs.append(f"links[{i}] must look like {{\"label\": \"...\", \"url\": \"https://...\"}}")
    if "{{" in json.dumps(ep) or "}}" in json.dumps(ep):
        errs.append("contains a leftover {{ }} placeholder")
    return errs

def load_episodes(data_dir=ROOT / "episodes" / "data"):
    """Loads and checks every episode. Stops the build, listing every problem, if any file is bad."""
    episodes, errors = [], []
    for f in sorted(data_dir.glob("*.json")):
        try:
            ep = json.loads(f.read_text())
        except json.JSONDecodeError as e:
            errors.append(f"{f.name}: not valid JSON ({e})"); continue
        if not isinstance(ep, dict):
            errors.append(f"{f.name}: should be one {{...}} object"); continue
        errors += [f"{f.name}: {e}" for e in check_episode(ep, f.stem)]
        if not f.name.startswith("_"):
            episodes.append(ep)
    for k in ("number", "slug"):
        seen = [ep.get(k) for ep in episodes]
        errors += [f"two episodes share {k} {v!r}" for v in sorted({v for v in seen if seen.count(v) > 1}, key=str)]
    if errors:
        sys.exit("Build stopped; nothing was written. Fix these episode files first:\n  " + "\n  ".join(errors))
    return sorted(episodes, key=lambda ep: ep["number"])

EPISODES = load_episodes()

def absolutize(html):
    """index.html sits at the root, so its relative links become root-absolute ones."""
    return re.sub(r'(href|src)="(?![a-z]+:|/|#)([^"]*)"',
                  lambda m: f'{m.group(1)}="/{"" if m.group(2) == "index.html" else m.group(2)}"', html)

def relativize(html, out):
    """Turns root-absolute links into relative ones so pages work on any host."""
    pre = "../" * (len(pathlib.PurePosixPath(out).parts) - 1)
    def fix(m):
        attr, url = m.groups()
        if url == "/": url = "index.html"
        elif url.endswith("/"): url = url[1:] + "index.html"
        elif url == "/privacy": url = "privacy/index.html"
        else: url = url[1:]
        return f'{attr}="{pre}{url}"'
    return re.sub(r'(href|src)="(/(?!/)[^"]*)"', fix, html)

HEADER = absolutize(re.search(r'<a class="skip".*?</header>', index, re.S).group(0))
FOOTER = absolutize(re.search(r'<footer class="site-footer">.*?</footer>', index, re.S).group(0))
FONTS = re.search(r'<link href="https://fonts\.googleapis\.com/css2[^>]*>', index).group(0)
STYLESHEET = absolutize(re.search(r'<link rel="stylesheet"[^>]*>', index).group(0))
ANALYTICS = re.search(r'<script async src="https://www\.googletagmanager\.com.*?</script>\n<script>.*?</script>', index, re.S).group(0)

def head(title, desc, path, extra="", noindex=False):
    robots = '<meta name="robots" content="noindex">\n' if noindex else ""
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
{robots}<title>{title}</title>
<meta name="description" content="{desc}">
<link rel="canonical" href="{SITE}{path}">
<meta property="og:type" content="website">
<meta property="og:site_name" content="The Founder's First Draft">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{desc}">
<meta property="og:url" content="{SITE}{path}">
<meta property="og:image" content="{SITE}/img/og-image.jpg">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:site" content="@foundrsdraft">
<link rel="icon" href="/img/favicon.svg" type="image/svg+xml">
<link rel="apple-touch-icon" href="/img/apple-touch-icon.png">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
{FONTS}
{STYLESHEET}
{ANALYTICS}
{extra}</head>
<body>
"""

PAGES = {}  # out path -> finished HTML; nothing is written until every page has passed its checks

def page(out, title, desc, path, nav_href, body, extra="", noindex=False):
    h = HEADER.replace(f'href="{nav_href}"', f'href="{nav_href}" aria-current="page"') if nav_href else HEADER
    doc = head(title, desc, path, extra, noindex) + h + "\n<main id=\"main\">\n" + body + "\n</main>\n\n" + FOOTER + "\n</body>\n</html>\n"
    PAGES[out] = relativize(doc, out)

def esc(s):
    """Escapes text for HTML. Apostrophes stay as they are: every attribute uses double quotes."""
    return html.escape(s, quote=False).replace('"', "&quot;")

def ld_json(data):
    """JSON-LD that can't close its own <script> tag early."""
    return '<script type="application/ld+json">\n' + json.dumps(data, indent=2, ensure_ascii=False).replace("</", "<\\/") + "\n</script>\n"

def released(ep):
    return datetime.date.fromisoformat(ep["date"]) <= TODAY

LISTEN = """<ul class="listen">
          <li><a class="btn btn-primary" href="https://open.spotify.com/show/4vHqsm9LxcR3t2k3SPgh0b">Follow on Spotify</a></li>
          <li><a class="btn btn-ghost" href="https://podcasts.apple.com/us/podcast/the-founders-first-draft/id6808995737">Apple Podcasts</a></li>
          <li><a class="btn btn-ghost" href="https://www.youtube.com/@TheFoundersFirstDraft">YouTube</a></li>
        </ul>"""

# ---------- About ----------
page("about.html",
  "About Nick Dorvault | The Founder's First Draft",
  "Nick Dorvault spent 20 years as a firefighter paramedic and now works in a cardiac cath lab. He started The Founder's First Draft to learn how founders actually take the first step.",
  "/about.html", "/about.html", """
  <section class="page-head"><div class="wrap">
    <h1>About Nick</h1>
    <span class="rule short" aria-hidden="true"></span>
    <p class="lede">Twenty years running toward emergencies. Now learning how to start something of my own, out loud.</p>
  </div></section>
  <section class="prose"><div class="wrap about-grid">
    <div>
      <p>I'm Nick Dorvault. I spent 20 years as a firefighter paramedic. Today I work in a cardiac cath lab. I've always wanted to build a business, and like a lot of people, I've had ideas I never acted on.</p>
      <p>The Founder's First Draft is how I'm changing that. Every week I sit down with a founder who built a business from the ground up and ask the questions I actually have: How did you know what the first step was? Were you scared? What would you do differently?</p>
      <div class="callout">
        <p><strong>I'm not an expert, and the show doesn't pretend I am.</strong> I'm learning alongside you, including where AI helps someone starting out and where it leads you astray.</p>
      </div>
      <h2>Why I'm doing this</h2>
      <p>Most founder stories start after the hard part is over. I want the beginning: the nights after a shift, the first awkward conversations, the first dollar. That's the part people with jobs and responsibilities need to hear.</p>
      <h2>Get in touch</h2>
      <p>Email me at <a href="mailto:nicholas@thefoundersfirstdraft.com">nicholas@thefoundersfirstdraft.com</a>, or find the show on <a href="https://www.instagram.com/foundersfirstdraft/">Instagram</a>, <a href="https://x.com/foundrsdraft">X</a> and <a href="https://www.linkedin.com/in/nicholas-dorvault-586a56173">LinkedIn</a>.</p>
    </div>
    <img src="/img/nick.jpg" alt="Nick Dorvault" width="675" height="900">
  </div></section>""")

# ---------- Episodes (pre-launch) ----------
page("episodes/index.html",
  "Episodes | The Founder's First Draft",
  "Every episode of The Founder's First Draft: founders on how they actually started. New episodes every Thursday starting October 22, 2026.",
  "/episodes/", "/episodes/index.html", f"""
  <section class="page-head"><div class="wrap">
    <h1>Episodes</h1>
    <span class="rule short" aria-hidden="true"></span>
    <p class="lede">The first full conversation comes out Thursday, October 22. After that, a new founder every Thursday.</p>
  </div></section>
  <section class="prose"><div class="wrap">
    <h2>Don't miss the first one</h2>
    <p>Follow the show wherever you listen and new episodes show up on their own. Or join the newsletter for one lesson from each conversation.</p>
    <ul class="listen" style="margin-bottom:28px">
      <li><a class="btn btn-primary" href="https://open.spotify.com/show/4vHqsm9LxcR3t2k3SPgh0b">Follow on Spotify</a></li>
      <li><a class="btn btn-dark" href="https://podcasts.apple.com/us/podcast/the-founders-first-draft/id6808995737">Apple Podcasts</a></li>
      <li><a class="btn btn-dark" href="https://www.youtube.com/@TheFoundersFirstDraft">YouTube</a></li>
      <li><a class="btn btn-dark" href="/newsletter.html">Newsletter</a></li>
    </ul>
    <h2>Listen to the trailer</h2>
    <iframe class="player" title="The Founder's First Draft on Spotify" src="https://open.spotify.com/embed/show/4vHqsm9LxcR3t2k3SPgh0b?utm_source=generator" height="232" loading="lazy" allow="autoplay; clipboard-write; encrypted-media; fullscreen; picture-in-picture"></iframe>
  </div></section>""")

# ---------- Be a guest ----------
page("guest.html",
  "Be a guest | The Founder's First Draft",
  "Built a business from the ground up? Tell your real start story on The Founder's First Draft, a video interview podcast for aspiring founders.",
  "/guest.html", "/guest.html", """
  <section class="page-head"><div class="wrap">
    <h1>Be a guest</h1>
    <span class="rule short" aria-hidden="true"></span>
    <p class="lede">If you built a business from the ground up and remember what the first step felt like, I'd like to hear it.</p>
  </div></section>
  <section class="prose"><div class="wrap">
    <h2>Who fits</h2>
    <ul>
      <li>Founders who built a business from scratch, often while working another job.</li>
      <li>People with a real start story, including the mistakes. This isn't a product pitch.</li>
      <li>Businesses of any industry. Medium-sized companies are a sweet spot; larger ones are welcome.</li>
    </ul>
    <p>The show doesn't book guests through PR agencies. If you have an assistant who handles your calendar, that's no problem.</p>
    <h2>How it works</h2>
    <ol class="steps">
      <li><strong>Say hello.</strong> Email a few lines about you, your business and how it started.</li>
      <li><strong>Pick a time.</strong> I'll send a calendar invite, a short outline of where the conversation might go, and a simple guest release to sign.</li>
      <li><strong>Talk for 45 to 60 minutes.</strong> We record video on Riverside from your browser. Headphones and a quiet room are all you need.</li>
      <li><strong>Share it easily.</strong> On release day you get a guest kit: short clips, ready-to-post captions and links.</li>
    </ol>
    <h2>Get in touch</h2>
    <p>Send your name, your business, a link to your website or LinkedIn, and two or three sentences on how you got started.</p>
    <p><a class="btn btn-primary" href="mailto:nicholas@thefoundersfirstdraft.com?subject=Guest%20idea%20for%20The%20Founder%27s%20First%20Draft">Email Nick</a></p>
    <p class="note">Or copy the address: <strong>nicholas@thefoundersfirstdraft.com</strong></p>
  </div></section>""")

# ---------- Newsletter ----------
page("newsletter.html",
  "Newsletter | The Founder's First Draft",
  "One founder lesson a week from The Founder's First Draft podcast, in a short email.",
  "/newsletter.html", "/newsletter.html", """
  <section class="page-head"><div class="wrap">
    <h1>One founder lesson a week</h1>
    <span class="rule short" aria-hidden="true"></span>
    <p class="lede">The most useful thing from each conversation, written down so you can use it. Short enough to read on a break.</p>
  </div></section>
  <section class="prose"><div class="wrap">
    <h2>What you'll get</h2>
    <ul>
      <li>The one lesson from each episode that's most useful for someone who hasn't started yet.</li>
      <li>A link to the full conversation.</li>
      <li>Nothing else. No spam, and you can unsubscribe anytime.</li>
    </ul>
    <!-- NEWSLETTER FORM: when beehiiv is live, replace this block with the beehiiv embed. -->
    <div class="callout">
      <p><strong>The newsletter starts soon.</strong> Want the first issue? Tap the button below and send the email as is. You'll be on the list.</p>
    </div>
    <p><a class="btn btn-primary" href="mailto:nicholas@thefoundersfirstdraft.com?subject=Add%20me%20to%20the%20newsletter">Add me to the list</a></p>
    <p class="note">Or email <strong>nicholas@thefoundersfirstdraft.com</strong> with the subject "Add me."</p>
  </div></section>""")

# ---------- One page per episode, from episodes/data/<slug>.json ----------
# Pages for episodes whose date hasn't come yet are built for previewing, but carry
# noindex and aren't linked from anywhere.
def episode_page(ep):
    d = datetime.date.fromisoformat(ep["date"])
    title = f"{ep['guest']}, {ep['company']}: {ep['lesson']}"
    url = f"{SITE}/episodes/{ep['slug']}.html"
    ld = ld_json({
        "@context": "https://schema.org",
        "@type": "PodcastEpisode",
        "name": title,
        "episodeNumber": ep["number"],
        "datePublished": ep["date"],
        "description": ep["summary"],
        "url": url,
        "partOfSeries": {"@type": "PodcastSeries", "name": "The Founder's First Draft", "url": f"{SITE}/"},
    })
    video = (f'\n    <iframe class="player" style="aspect-ratio:16/9;height:auto" src="https://www.youtube-nocookie.com/embed/{esc(ep["youtube_id"])}" '
             f'title="{esc(ep["guest"])} on The Founder\'s First Draft" loading="lazy" allowfullscreen></iframe>') if ep["youtube_id"] else ""
    takeaways = "".join(f"<li>{esc(t)}</li>" for t in ep["takeaways"])
    sections = f"""
    <h2>What you'll learn</h2>
    <ul>{takeaways}</ul>"""
    if ep["timestamps"]:
        sections += "\n    <h2>Timestamps</h2>\n    <ul>" + "".join(f"<li>{esc(ts['t'])} {esc(ts['topic'])}</li>" for ts in ep["timestamps"]) + "</ul>"
    sections += f"\n    <h2>About {esc(ep['guest'])}</h2>\n    <p>{esc(ep['bio'])}</p>"
    if ep["links"]:
        sections += "\n    <h2>Links mentioned</h2>\n    <ul>" + "".join(f'<li><a href="{esc(ln["url"])}">{esc(ln["label"])}</a></li>' for ln in ep["links"]) + "</ul>"
    sections += "\n    <h2>Transcript</h2>\n" + "\n".join(f"    <p>{esc(p)}</p>" for p in ep["transcript"])
    page(f"episodes/{ep['slug']}.html",
      esc(f"{title} | The Founder's First Draft"), esc(ep["summary"]),
      f"/episodes/{ep['slug']}.html", "/episodes/index.html", f"""
  <section class="page-head"><div class="wrap">
    <p class="launch">Episode {ep['number']}, {d:%b} {d.day}, {d.year}, {ep['length_min']} min</p>
    <h1>{esc(title)}</h1>
    <span class="rule short" aria-hidden="true"></span>
    <p class="lede">{esc(ep['lede'])}</p>
    {LISTEN}
  </div></section>
  <section class="prose"><div class="wrap">{video}{sections}
  </div></section>""", extra=ld, noindex=not released(ep))

for ep in EPISODES:
    episode_page(ep)

# ---------- Privacy (same text as the live site) ----------
page("privacy/index.html",
  "Privacy | The Founder's First Draft",
  "How thefoundersfirstdraft.com uses website analytics.",
  "/privacy", None, """
  <section class="page-head"><div class="wrap"><h1>Privacy</h1><span class="rule short" aria-hidden="true"></span></div></section>
  <section class="prose"><div class="wrap">
    <h2>Website analytics</h2>
    <p>This website uses Google Analytics to understand how visitors find and use the site, including page visits, general traffic sources, scrolling, and clicks to services such as Spotify, Apple Podcasts, and Instagram.</p>
    <p>Google may use cookies or similar technologies to provide this measurement. The site does not ask you to submit personal information or sell your information.</p>
    <p><a href="https://policies.google.com/technologies/partner-sites">Learn more about how Google uses information from sites that use its services.</a></p>
    <p><a href="/">Return to the home page</a></p>
  </div></section>""")

# ---------- Check everything, then write ----------
leftovers = [f"{out}: {m.group(0)!r}" for out, doc in PAGES.items() for m in re.finditer(r".{0,30}(\{\{|\}\}).{0,30}", doc)]
if leftovers:
    sys.exit("Build stopped; nothing was written. Leftover {{ }} placeholders:\n  " + "\n  ".join(leftovers))
for out, doc in PAGES.items():
    (ROOT / out).write_text(doc)
    print("wrote", out)
# Every episodes/*.html except index.html comes from a data file; remove pages whose file is gone.
for f in sorted((ROOT / "episodes").glob("*.html")):
    if f.name != "index.html" and f"episodes/{f.name}" not in PAGES:
        f.unlink()
        print("removed", f"episodes/{f.name}", "(no data file for it)")
