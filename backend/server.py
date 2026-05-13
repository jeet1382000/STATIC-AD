"""Ads Studio backend.

BYOK: API keys for Anthropic + OpenAI are sent per-request in headers
(X-Anthropic-Key, X-OpenAI-Key). Never persisted on the server.
"""

import asyncio
import base64
import json
import logging
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional
from urllib.parse import urljoin

import anthropic
import httpx
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from fastapi import APIRouter, FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, ConfigDict, Field
from starlette.middleware.cors import CORSMiddleware

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

mongo_url = os.environ["MONGO_URL"]
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ["DB_NAME"]]

# Local directory for storing generated images
IMAGES_DIR = ROOT_DIR / "static" / "images"
IMAGES_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Ads Studio API")
api_router = APIRouter(prefix="/api")

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("ads-studio")

CLAUDE_MODEL = "claude-sonnet-4-6"
OPENAI_IMAGE_MODEL = "gpt-image-2"


# =============== Models ===============

class StatusCheck(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    client_name: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Palette(BaseModel):
    primary: str
    secondary: str
    accent: str
    neutral: str


class BrandOverview(BaseModel):
    model_config = ConfigDict(extra="ignore")
    tagline: str = ""
    design_agency: str = ""
    voice_adjectives: List[str] = []
    positioning: str = ""
    competitive_differentiation: str = ""


class VisualSystem(BaseModel):
    model_config = ConfigDict(extra="ignore")
    primary_font: str = ""
    secondary_font: str = ""
    primary_color: str = ""
    secondary_color: str = ""
    accent_color: str = ""
    background_colors: str = ""
    cta_color_and_style: str = ""


class PhotographyDirection(BaseModel):
    model_config = ConfigDict(extra="ignore")
    lighting: str = ""
    color_grading: str = ""
    composition: str = ""
    subject_matter: str = ""
    props_and_surfaces: str = ""
    mood: str = ""


class ProductDetails(BaseModel):
    model_config = ConfigDict(extra="ignore")
    physical_description: str = ""
    label_logo_placement: str = ""
    distinctive_features: str = ""
    packaging_system: str = ""


class AdCreativeStyle(BaseModel):
    model_config = ConfigDict(extra="ignore")
    typical_formats: str = ""
    text_overlay_style: str = ""
    photo_vs_illustration: str = ""
    ugc_usage: str = ""
    offer_presentation: str = ""


class BrandIdentity(BaseModel):
    model_config = ConfigDict(extra="ignore")
    palette: Palette
    fonts: List[str]
    tone: str
    photography_style: str
    brand_voice: str
    keywords: List[str]
    # Expanded brand DNA (optional for backward compat)
    brand_overview: Optional[BrandOverview] = None
    visual_system: Optional[VisualSystem] = None
    photography_direction: Optional[PhotographyDirection] = None
    product_details: Optional[ProductDetails] = None
    ad_creative_style: Optional[AdCreativeStyle] = None
    image_generation_modifier: str = ""


class BrandCreate(BaseModel):
    name: str
    url: str
    product_name: Optional[str] = None
    product_images: List[str] = []  # base64 data URLs, max 5


class Brand(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    url: str
    product_name: Optional[str] = None
    product_images: List[str] = []
    identity: Optional[BrandIdentity] = None
    logo_url: Optional[str] = None         # absolute URL where the logo was scraped from
    logo_data_url: Optional[str] = None    # base64 data URL of the scraped logo (passed to OpenAI as 2nd image)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    cover_color: Optional[str] = None
    # Derived fields populated by list_brands (defaults so single-brand fetch keeps working)
    total_ads: int = 0
    done_ads: int = 0
    thumb_urls: List[str] = []
    cost: float = 0.0


class AdCreative(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    prompt: str
    image_url: Optional[str] = None
    error: Optional[str] = None
    aspect: str = "1:1"
    template_name: Optional[str] = None
    template_number: Optional[int] = None


class AdRun(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    brand_id: str
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    creatives: List[AdCreative] = []
    status: str = "pending"   # pending | running | done | failed
    error: Optional[str] = None


class Template(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    number: int
    name: str
    aspect: str           # 1:1 | 4:5 | 9:16 | 16:9 | 4:3
    needs_product: bool
    category: str
    scaffold: str         # raw prompt scaffold for Claude
    enabled: bool = True


SEED_TEMPLATES: List[dict] = [
    {"number": 1, "name": "Headline Ad", "aspect": "4:5", "needs_product": True, "category": "headline", "enabled": False,
     "scaffold": "Editorial poster-style headline ad for [BRAND NAME] in the brand's signature visual language. Compositional anchor: the uploaded product sits in the lower third, sharply lit, hero-staged on a flat field of the brand's primary background color (cream / off-white / pale tonal — pick the most-used hero background from the brand identity). Top two-thirds reserved for a SINGLE confident headline (max 6 words, ~140pt) set in the brand's display typeface — extra-bold, tight tracking, all caps if that matches the brand. Tiny supporting subhead one line below at ~24pt, the brand voice paraphrased into one promise. Optional small wordmark top-left. Composition rules: generous negative space, headline left-aligned OR center-stacked (pick to match brand), product photographed with soft directional studio light and a clean drop-shadow. No badges, no rays, no decorative ornaments — pure type + product."},
    {"number": 2, "name": "Offer Promotion", "aspect": "1:1", "needs_product": True, "category": "offer", "enabled": False,
     "scaffold": "Promotional ad for [BRAND NAME] anchored by a single confident offer mark. The uploaded product is positioned hero-center on a brand-aligned background (warm tonal or pastel matching the brand palette). To the upper-right, a clean circular badge in the brand's accent hue containing a percent or value (e.g. '20% OFF', 'BUY 2 GET 1') in the brand's display type — no starbursts, no comic styling, kept editorial. Below the badge, a short one-line offer descriptor in the brand body type (~20pt). Tiny terms line at the very bottom (~12pt, 60% opacity). Lighting: bright, optimistic, gentle ambient highlights on the product. Composition stays minimal — badge sits as a tasteful seal, not as carnival signage."},
    {"number": 3, "name": "Testimonial Card", "aspect": "4:5", "needs_product": True, "category": "social_proof", "enabled": True,
     "scaffold": "Premium editorial testimonial poster for [BRAND NAME], inspired by Orbitkey-tier brand work. Layout: upper-left two-thirds carries a SINGLE customer quote set in the brand's display serif/sans, ~110pt, line-broken into 3–4 short lines, with curly opening quotation marks ('\u201c') and closing ('\u201d') in the same weight. Beneath the quote: five filled stars in the brand's accent color (small, ~22pt, left-aligned in a tight row). One line under the stars: attribution in tiny tracked caps — '— FIRST NAME L. | VERIFIED BUYER' in the brand mono/sans body font. Right-side third (or lower-third on portrait): the uploaded product photographed on a textured travertine slab or linen drape, soft north-window daylight, gentle shadow. Background pulled from the brand's neutral palette (pale cream/stone). The product is small and tucked, the typography commands the frame. Editorial, calm, premium."},
    {"number": 4, "name": "Feature Callout", "aspect": "4:5", "needs_product": True, "category": "product_feature", "enabled": True,
     "scaffold": "Annotated product anatomy ad for [BRAND NAME], styled like an Orbitkey product diagram. The uploaded product is centered, slightly larger than life, on a clean brand-background plane (cream/off-white/pale). Four numbered callouts — circles 1, 2, 3, 4 — placed at the cardinal-ish corners of the product, each connected by a thin elegant line (~1px, brand accent color) to a short two-line annotation: a small all-caps label in the brand sans (~14pt) and a single-sentence descriptor underneath in the brand body (~12pt, 70% opacity). Examples to seed Claude: 'AWARD-WINNING DESIGN — Crafted with intention.' / 'PREMIUM MATERIALS — Sustainable, made to last.' At the very bottom: the brand wordmark + tagline in small tracked type, centered. Photographic style: soft directional studio light, clean shadow under the product, no distracting props. Lines and labels must look like quiet engineering callouts, not infographic clutter."},
    {"number": 5, "name": "Us vs Them Comparison", "aspect": "1:1", "needs_product": True, "category": "comparison", "enabled": True,
     "scaffold": "Side-by-side comparison ad for [BRAND NAME] in a strict 50/50 vertical split, in the Orbitkey 'Orbitkey vs Bulky Key Ring' style. "
                 "LEFT HALF (the brand half): warm brand-tonal background (cream, blush, pale stone — pick the brand's signature). The uploaded product sits hero-staged on a tactile pedestal or surface (travertine, oak, linen) photographed in soft natural daylight with a gentle drop shadow — looks editorial, calm, premium. "
                 "Column HEADER at the top centered above the photo: '[BRAND NAME]' on line 1 + the product type on line 2 (e.g. 'KEY ORGANISER'), set in the brand display type, brand primary color, ~48pt, tight tracking. "
                 "RIGHT HALF (the alternative): a slightly cooler neutral grey-stone background (#B8B8B5 / #C8C5BE — picked to feel duller than the brand side). "
                 "MANDATORY: this side MUST contain a REAL editorial photograph of the brand's actual pain point / category competitor — never an abstract grey block, never an empty silhouette, never a vector illustration. Claude picks the concrete pain-point subject that maps to the product (e.g. for a key organiser → a chaotic bulky keychain of mismatched keys + key fob on a grey concrete surface; for a protein powder → a row of mass-market plastic tubs with loud branding on a sterile pharmacy-aisle shelf; for a skincare brand → a cluttered messy bathroom counter with half-empty drugstore bottles; for a meal kit → a microwave dinner tray on a tired beige table; for a productivity app → a desk piled with sticky notes, paper planners, and chaos). Photographed in flatter, cooler, lower-contrast light so it visibly feels less premium than the brand side. "
                 "Column HEADER above the right photo: 'BULKY [CATEGORY]' or 'CHEAP [CATEGORY]' or 'GENERIC [CATEGORY]' on line 1 + a one-word pain descriptor on line 2 (e.g. 'KEY RING' / 'PROTEIN BLEND'), set in the same display type but in mid-grey (#7A7A7A), ~48pt, tight tracking. "
                 "BENEFIT TABLE BELOW (both columns aligned in a 4-row grid): the brand side has 4 short benefit phrases in tracked caps body type next to filled circular bullet marks in the brand accent color (orange / brand accent), e.g. 'QUIET, ORDERED KEYS', 'SLIM AND COMPACT', 'PREMIUM MATERIALS', 'BUILT TO LAST'. The alternative side has 4 matching pain phrases in mid-grey caps body type next to grey X marks, e.g. 'NOISY AND CLUTTERED', 'BULKY AND UNCOMFORTABLE', 'CHEAP, LOW-GRADE MATERIALS', 'WEARS OUT QUICKLY'. Claude writes these 4 paired benefit/pain rows verbatim, brand-adapted. "
                 "DIVIDER: a thin vertical hairline (~1.5px) in the brand accent color runs the full height between the two halves. "
                 "Swiss grid, no decorative noise, no badges, no extra text beyond the headers and the 4-row table."},
    {"number": 6, "name": "Before and After UGC", "aspect": "9:16", "needs_product": True, "category": "ugc", "enabled": True,
     "scaffold": (
         "Vertical 9:16 lifestyle split-screen for [BRAND NAME] in the Orbitkey 'Good Pockets Keep Quiet' style. "
         "The frame is divided into two stacked or side-by-side halves separated by a soft natural seam — both halves captured in the same warm naturalistic light so they feel like one continuous shot, NOT a desaturated copy of each other. "
         "LEFT / TOP HALF — labeled with a handwritten cursive 'Before' (white ink, ~80pt, lightly underlined) in the upper area: depict a believable life-WITHOUT-the-product scenario that visualizes the customer's actual pain point. The product MUST NOT appear on this side. The scene is concrete and lived-in — a real pocket overflowing with mess, a cluttered countertop, a tangled chaotic version of whatever the product solves. Slightly cooler/duller grading, lived-in textures (denim, fabric folds, scuffed surfaces), tells a story in one frame. "
         "RIGHT / BOTTOM HALF — labeled with the same handwritten cursive 'After': the same setting, now calm, ordered, with the uploaded product as the hero. Warmer highlights, the product photographed in clean detail. "
         "Top of the frame: a confident two-line editorial headline in the brand display type, all caps, tight tracking, e.g. 'GOOD POCKETS / KEEP QUIET' — adapt the words to the brand's value proposition. Below the headline: a single tracked-caps sub-line giving three brand promises separated by periods (e.g. 'ORGANISE. PROTECT. SIMPLIFY.'). "
         "Bottom of the frame: small pill-shaped brand wordmark on a soft white badge. "
         "Photography style: warm naturalistic daylight, real-world textures, editorial-realistic — premium lifestyle, not phone-grain UGC."
     )},
    {"number": 7, "name": "Negative Marketing Bait-and-Switch", "aspect": "4:5", "needs_product": True, "category": "provocation", "enabled": True,
     "scaffold": "Provocative typography-led ad for [BRAND NAME]. Top 70% of the frame is a flat brand-background field with a single deliberately combative headline in the brand display type set huge (~180pt), tightly leaded, e.g. 'STOP BUYING [CATEGORY].' or 'YOUR [CATEGORY] IS THE PROBLEM.' — adapt the provocation to the brand's actual category in a confident, cheeky, never mean voice. One line of resolution copy in body type underneath, half the size (~36pt): the punchline that flips the provocation into a brand promise. Bottom 30%: the uploaded product centered on the same background, sharply lit, tiny brand wordmark beneath. No imagery beyond product + type. Composition is mostly empty space — the typography carries the entire ad."},
    {"number": 8, "name": "Press Editorial Layout", "aspect": "1:1", "needs_product": True, "category": "press", "enabled": True,
     "scaffold": "Faux magazine editorial spread for [BRAND NAME] in a high-end print aesthetic. Layout: a thin top masthead bar with a fabricated publication name in a classic serif ('THE WEEKLY EDIT', 'COMMON DAILY', or similar appropriate to the brand) plus a fake issue date in tracked caps. The frame splits 60/40 — LEFT 60%: a moody editorial photograph featuring the uploaded product on a natural surface (linen, travertine, oak, kraft paper — pick what fits the brand) with soft cinematic side-light and a subtle paper grain overlay. RIGHT 40%: clean column with a single-line article headline in a heavy serif (~64pt), a one-line italic deck underneath (~22pt), three columns of greeked body copy at ~10pt with realistic line lengths and paragraph indents, and a centered pull-quote in larger italic serif that paraphrases a brand benefit (~28pt). Subtle paper-stock texture across the whole composition, gentle warm cast, looks like it was scanned from a real magazine page."},
    {"number": 9, "name": "Review Card", "aspect": "1:1", "needs_product": True, "category": "social_proof", "enabled": True,
     "scaffold": "Single-quote review card for [BRAND NAME] — a clean square poster, not a screenshotted UI. Background: brand neutral (cream/off-white). Left 55%: editorial product hero — the uploaded product on a textured slab (travertine, linen, oak) with soft natural daylight and a gentle drop shadow, framed loose with breathing room. Right 45%: typography stack — five small filled stars in the brand accent color at the top (tight row, ~22pt); below the stars, a short two-sentence customer quote in the brand display type (~40pt), the second sentence visually de-emphasized to ~28pt; below the quote, a single line in tracked caps body type: '— FIRST NAME L. | VERIFIED BUYER'. Tiny brand wordmark at the very bottom-right. No fake browser chrome, no app-screenshot UI — just a poster designed to feel like a premium testimonial card."},
    {"number": 10, "name": "Stat Surround Callout Radial", "aspect": "1:1", "needs_product": True, "category": "proof", "enabled": True,
     "scaffold": "Stat-anchored proof ad for [BRAND NAME]. The uploaded product is dead-centre on a calm brand-background plane, photographed cleanly with soft studio light. Around it, four stat callouts radiating outward at roughly 10 / 2 / 5 / 7 o'clock positions, each composed of: a LARGE numeric figure in the brand display type (~96pt — examples Claude should pick from category-relevant numbers: '4.9★', '98%', '10M+', '<2s', '500+'), a short two-or-three-word label in tracked caps body type beneath (~14pt, e.g. 'CUSTOMER RATING', 'WOULD REBUY', 'NIGHTS TESTED'). Each callout connected to the product by a thin (~1px) brand-accent hairline that gently bends. No boxes, no rays, no infographic clutter — feels editorial, not data-deck."},
    {"number": 11, "name": "Manifesto Ad", "aspect": "4:5", "needs_product": True, "category": "brand_voice", "enabled": True,
     "scaffold": "Manifesto poster for [BRAND NAME]. Background: a tonal field pulled directly from the brand palette (often deep / saturated / off-cream depending on brand). Foreground: a 4–6 line manifesto in the brand display type set huge (~80pt) and tightly leaded, left-aligned, line-broken for rhythm — each line a complete confident statement of brand belief (examples Claude should compose to match brand: 'WE BELIEVE THE EVERYDAY / DESERVES BETTER DESIGN. / NOT MORE STUFF. / LESS, BUT BETTER.'). The uploaded product sits as a small but visible anchor in the lower-right corner — about 20% of the frame — quietly lit so the typography stays the hero. Tiny brand wordmark bottom-left in tracked caps. Stark, confident, no decoration."},
    {"number": 12, "name": "Faux iPhone Screenshot", "aspect": "9:16", "needs_product": True, "category": "native_ugc", "enabled": True,
     "scaffold": (
         "Ultra-realistic faux-iOS 17 iMessage screenshot. Pure white #FFFFFF background, portrait 9:16. "
         "STATUS BAR (top): left — cellular signal bars + '5G' label; center — time e.g. '2:47 PM' in black SF Pro Medium; right — battery percentage + icon e.g. '87% \U0001F50B'. "
         "CONTACT HEADER ROW: '\u2039' back chevron far-left; center — two circular avatar portrait headshots with first names underneath (e.g. 'Sarah' on left, 'Alex' on right) and a '\u2194' icon between them; blue FaceTime camera icon far-right. Thin #E5E5EA separator below. "
         "CHAT THREAD (top to bottom, generous white space between bubbles): "
         "(1) LEFT bubble #E9E9EB rounded-rect tail-left: Person A mentions [BRAND NAME] by name with genuine enthusiasm and a specific benefit, ends with emoji. 2\u20133 casual sentences. "
         "(2) RIGHT bubble #147EFB rounded-rect tail-right: Person B short enthusiastic reply endorsing [BRAND NAME]. 1\u20132 sentences. "
         "Directly below the blue bubble, still in the right column: large PRODUCT PHOTO displayed as a rounded-corner image card (~65% screen width) \u2014 the uploaded product shown clearly in a clean bright shot. "
         "(3) LEFT bubble #E9E9EB: Person A short reaction to seeing the photo, hype emoji. 1 sentence. "
         "BOTTOM: standard rounded-rect gray input field \u2014 circle '+' icon left, light-gray 'iMessage' placeholder text, microphone icon right. "
         "FOOTER: tiny #8E8E93 SF Pro text centered below input field \u2014 'Paid partnership / [BRAND NAME]'. "
         "Every element must be indistinguishable from a real iPhone screenshot: exact SF Pro font weights, #147EFB iOS blue, #E9E9EB bubble gray, correct iOS 17 bubble corner radii and tail geometry, correct avatar circle crop style."
     )},
    {"number": 13, "name": "Post-it Note Style", "aspect": "1:1", "needs_product": True, "category": "handwritten", "enabled": True,
     "scaffold": "Hand-written post-it concept ad for [BRAND NAME]. A single yellow square post-it (warm canary, ~3:3 ratio, slightly off-axis ~5\u00b0) sits on a softly lit oak desk surface. On the post-it, scrawled by a fine black marker in casual but legible handwriting: a 3-line confessional insight about why the brand exists or solves the problem (example Claude should compose: 'why is everything so / loud? \u2014 made this / so it isn't.'). A tiny doodled icon in one corner of the post-it that visually riffs on the brand category. Beside the post-it on the desk: the uploaded product, photographed in soft window light, casting a gentle real-world shadow as if it were placed there with the note. Tiny printed brand URL in small mono type at the bottom edge of the frame. Feels personal and hand-made."},
    {"number": 14, "name": "Lifestyle UGC Selfie", "aspect": "9:16", "needs_product": True, "category": "ugc", "enabled": True,
     "scaffold": "Vertical 9:16 lifestyle moment featuring [BRAND NAME], shot in the photographic style of the brand (NOT phone-grain UGC unless the brand explicitly uses that). A real-feeling human moment that maps to the brand's target customer and category — examples Claude should adapt: a woman pouring an espresso at a sunlit kitchen counter with the product in the foreground; a runner stretching on a wooden deck at dawn; a creative at a desk holding the product to the camera. Soft natural daylight, warm grading, shallow depth of field, candid expression but composition is intentional. The uploaded product is prominent and clearly readable in the frame. Bottom of frame: a small handwritten-style caption overlay in white (~32pt) with a single line of brand-voice copy. Tiny brand wordmark pill bottom-right corner."},
    {"number": 15, "name": "Ingredient Hero / What's Inside", "aspect": "4:5", "needs_product": True, "category": "ingredient", "enabled": True,
     "scaffold": "Overhead 90\u00b0 top-down flat-lay 'what's inside' ad for [BRAND NAME]. The uploaded product is dead-centre on a tactile brand-aligned surface (oak board, linen, marble, terracotta tile — Claude picks the closest brand fit). Surrounding it in a deliberate compositional pattern: 4 raw constituent elements that connect to the product (whole ingredients, raw materials, key components — Claude picks brand-appropriate elements e.g. fresh fruit, herbs, beans, fabric swatches, brass parts). Each surrounding element is connected to the product by a thin elegant hairline in the brand accent color terminating in a small caption set in tracked caps body type — a 1\u20132 word ingredient/material name + a 4\u20136 word benefit sub-line beneath (e.g. 'OAT MILK \u2014 creamy without the dairy'). Studio overhead daylight, soft shadows, editorial flat-lay style. No clutter, generous negative space."},
]


# =============== Helpers ===============

def _require_anthropic_key(x_anthropic_key: Optional[str]) -> str:
    if not x_anthropic_key or not x_anthropic_key.strip():
        raise HTTPException(status_code=401, detail="Missing Anthropic API key")
    return x_anthropic_key.strip()


def _require_openai_key(x_openai_key: Optional[str]) -> str:
    if not x_openai_key or not x_openai_key.strip():
        raise HTTPException(status_code=401, detail="Missing OpenAI API key")
    return x_openai_key.strip()


async def _scrape_url(url: str) -> str:
    """Aggressive brand-DNA scraper.

    Pulls homepage + a couple of brand pages, inlines stylesheets, and surfaces
    concrete font-family / color evidence so Claude can ground its analysis.

    Rate-limit aware: small delays between secondary fetches and exponential
    backoff on 429 Too Many Requests so the research call survives sites
    that throttle aggressively.
    """
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": (
            "text/html,application/xhtml+xml,application/xml;q=0.9,"
            "image/avif,image/webp,image/apng,*/*;q=0.8"
        ),
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate",
        "Cache-Control": "max-age=0",
        "Sec-Ch-Ua": '"Chromium";v="124", "Not-A.Brand";v="99"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"macOS"',
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1",
    }

    async def _polite_get(hc: httpx.AsyncClient, target: str, *, retries: int = 2) -> Optional[httpx.Response]:
        """GET with backoff on 429. Returns None on permanent failure."""
        for attempt in range(retries + 1):
            try:
                r = await hc.get(target)
            except Exception:
                return None
            if r.status_code == 429:
                # Respect Retry-After when present, else exponential backoff
                ra = r.headers.get("Retry-After")
                try:
                    delay = float(ra) if ra is not None else 1.0 * (2 ** attempt)
                except ValueError:
                    delay = 1.0 * (2 ** attempt)
                delay = min(delay, 4.0)
                if attempt < retries:
                    await asyncio.sleep(delay)
                    continue
            return r
        return None

    try:
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True, headers=headers) as hc:
            resp = await _polite_get(hc, url)
            if resp is None or resp.status_code >= 400:
                code = resp.status_code if resp is not None else "no response"
                # Surface a friendlier error for 429 so the user knows it's the site, not the app
                if resp is not None and resp.status_code == 429:
                    raise HTTPException(
                        status_code=502,
                        detail="The brand site is rate-limiting our scraper (HTTP 429). Try again in a minute or use a different URL.",
                    )
                raise HTTPException(status_code=400, detail=f"Failed to fetch URL (HTTP {code})")
            base_url = str(resp.url)
            soup = BeautifulSoup(resp.text, "html.parser")

            # ── 1. Meta / title / og ──
            title = (soup.title.string if soup.title and soup.title.string else "").strip()
            def _meta(name=None, prop=None) -> str:
                if name:
                    el = soup.find("meta", attrs={"name": name})
                elif prop:
                    el = soup.find("meta", attrs={"property": prop})
                else:
                    el = None
                return (el.get("content") or "").strip() if el and el.get("content") else ""

            meta_desc = _meta(name="description") or _meta(prop="og:description")
            og_title = _meta(prop="og:title")
            og_image = _meta(prop="og:image")
            og_site = _meta(prop="og:site_name")
            twitter_desc = _meta(name="twitter:description")

            # ── 2. Inline <style> blocks BEFORE we strip them ──
            inline_styles = " ".join(s.get_text(" ", strip=True) for s in soup.find_all("style"))[:30000]

            # ── 3. External stylesheets (first 2 — fewer requests = less likely to trip rate limits) ──
            # Detect both rel=stylesheet AND rel=preload + as=style (Next.js / SPAs).
            css_links: list[str] = []
            for link in soup.find_all("link")[:80]:
                rel = " ".join(link.get("rel", [])).lower()
                as_attr = (link.get("as") or "").lower()
                href = link.get("href") or ""
                if not href:
                    continue
                is_stylesheet = "stylesheet" in rel or (rel == "preload" and as_attr == "style")
                # Fallback: any .css URL
                if not is_stylesheet and ".css" in href.split("?")[0]:
                    is_stylesheet = True
                if is_stylesheet:
                    css_links.append(urljoin(base_url, href))
                if len(css_links) >= 2:
                    break

            external_css = ""
            for href in css_links:
                await asyncio.sleep(0.3)  # be polite — small inter-request gap
                r = await _polite_get(hc, href, retries=1)
                if r is None or r.status_code != 200:
                    continue
                if "css" in r.headers.get("content-type", "").lower():
                    external_css += "\n/* " + href + " */\n" + r.text[:20000]
            external_css = external_css[:60000]

            # ── 4. Pull concrete font-family and color evidence from CSS ──
            css_blob = (inline_styles + "\n" + external_css)[:80000]
            # Both font-family declarations AND @font-face font-family names.
            font_family_decls = re.findall(r"font-family\s*:\s*([^;{}]+)", css_blob, re.IGNORECASE)
            font_face_names = re.findall(
                r"@font-face\s*\{[^}]*?font-family\s*:\s*['\"]?([^;'\"{}]+?)['\"]?\s*[;}]",
                css_blob, re.IGNORECASE | re.DOTALL,
            )
            font_families = sorted({f.strip().strip("'\"") for f in font_family_decls + font_face_names})[:25]
            google_fonts = sorted(set(
                m.group(1)
                for m in re.finditer(r"fonts\.googleapis\.com/css2?\?family=([^&\"'\s)]+)", css_blob)
            ))[:15]
            hex_colors = sorted(set(
                m.group(0).lower()
                for m in re.finditer(r"#(?:[0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b", css_blob)
            ))[:50]
            css_variables = re.findall(
                r"(--[a-z0-9-]+)\s*:\s*([^;]{1,80});", css_blob, re.IGNORECASE
            )[:60]
            css_vars_str = "; ".join(f"{k}: {v.strip()}" for k, v in css_variables)

            # ── 5. Strip scripts/styles for clean text content ──
            for tag in soup(["script", "style", "noscript"]):
                tag.decompose()
            text = re.sub(r"\s+", " ", soup.get_text(separator=" ", strip=True))[:6000]

            # ── 6. Crawl ONE secondary brand page (was 5 — now 2 max, with polite delay) ──
            # Sequential 5-page probes were a key cause of 429s on smaller stores.
            secondary_text = ""
            for path in ("/about", "/our-story"):
                await asyncio.sleep(0.4)
                r2 = await _polite_get(hc, urljoin(base_url, path), retries=1)
                if r2 is None:
                    continue
                if r2.status_code == 429:
                    break  # site is throttling — stop crawling, we have enough
                if r2.status_code == 200 and "text/html" in r2.headers.get("content-type", ""):
                    s2 = BeautifulSoup(r2.text, "html.parser")
                    for tag in s2(["script", "style", "noscript"]):
                        tag.decompose()
                    secondary_text = re.sub(r"\s+", " ", s2.get_text(" ", strip=True))[:3000]
                    secondary_text = f"\n{path} EXCERPT: {secondary_text}"
                    break

            return (
                f"TITLE: {title}\n"
                f"OG_SITE_NAME: {og_site}\n"
                f"OG_TITLE: {og_title}\n"
                f"DESCRIPTION: {meta_desc}\n"
                f"TWITTER_DESC: {twitter_desc}\n"
                f"OG_IMAGE: {og_image}\n"
                f"\n=== CSS EVIDENCE (use these to ground fonts and colors) ===\n"
                f"FONT_FAMILIES_FOUND: {font_families}\n"
                f"GOOGLE_FONTS_LOADED: {google_fonts}\n"
                f"HEX_COLORS_FOUND: {hex_colors}\n"
                f"CSS_VARIABLES: {css_vars_str}\n"
                f"\n=== HOMEPAGE TEXT ===\n{text}"
                f"{secondary_text}"
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to fetch URL: {str(e)[:120]}")


def _extract_json(text: str) -> dict:
    """Robust JSON extractor for Claude responses.

    Handles:
    - Plain JSON: {"prompts": [...]}
    - Fenced JSON: ```json\n{...}\n```
    - Fenced WITHOUT outer braces: ```json\n"prompts": [...]\n```  (Claude sometimes does this)
    - Bare body without braces: "prompts": [...]
    """
    text = text.strip()

    # 1. Strip code fences first — Claude often wraps output in ```json … ```
    fenced = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1).strip()

    # 2. Try direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 3. Try slicing to outer braces
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass

    # 4. Body without outer braces (e.g. '"prompts": [...]') — wrap and retry
    if re.match(r'^\s*"[^"]+"\s*:', text):
        try:
            return json.loads("{" + text.rstrip(", \n\t") + "}")
        except json.JSONDecodeError:
            pass

    # 5. Last resort: pull a bare prompts array if visible
    arr = re.search(r'"prompts"\s*:\s*(\[.*\])', text, re.DOTALL)
    if arr:
        try:
            return {"prompts": json.loads(arr.group(1))}
        except json.JSONDecodeError:
            pass

    # Re-raise the original error to surface clearly upstream
    return json.loads(text)


async def _claude_call(api_key: str, system: str, user: str, max_tokens: int = 1500) -> str:
    """Call Claude via the SDK in a thread (sync client — fewer deps)."""
    def _run():
        c = anthropic.Anthropic(api_key=api_key)
        msg = c.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return msg.content[0].text

    return await asyncio.to_thread(_run)


async def _scrape_logo(brand_url: str) -> tuple[Optional[str], Optional[str]]:
    """Try to discover and download the brand's logo from its homepage.

    Returns (absolute_logo_url, base64_data_url) or (None, None) if nothing
    suitable found. We prefer SVG / PNG / WEBP under ~600KB; skip oversized
    hero images and decorative banners.

    Detection priority:
      1. <link rel="icon"|"apple-touch-icon"|"mask-icon"> SVG/PNG entries
      2. <header>/nav <img> whose alt or src contains the word "logo"/"wordmark"
      3. og:image / og:logo / twitter:image as a last fallback
    """
    if not brand_url.startswith(("http://", "https://")):
        brand_url = "https://" + brand_url

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate",
    }

    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True, headers=headers) as hc:
            r = await hc.get(brand_url)
            if r.status_code >= 400:
                return None, None
            base_url = str(r.url)
            soup = BeautifulSoup(r.text, "html.parser")

            candidates: list[str] = []

            # Priority 1: <link rel="icon"|"mask-icon"|"apple-touch-icon">
            for link in soup.find_all("link", attrs={"rel": True}):
                rel = " ".join(link.get("rel", [])).lower()
                href = (link.get("href") or "").strip()
                if not href:
                    continue
                if any(k in rel for k in ("icon", "mask-icon", "apple-touch-icon")):
                    sizes = (link.get("sizes") or "").lower()
                    if sizes in ("16x16", "32x32"):
                        # skip tiny generic favicons
                        continue
                    candidates.append(urljoin(base_url, href))

            # Priority 2: <img> tags whose src or alt strongly suggests a logo
            for img in soup.find_all("img"):
                src = (img.get("src") or img.get("data-src") or "").strip()
                alt = (img.get("alt") or "").lower()
                if not src:
                    continue
                if src.startswith("data:") or src.startswith("javascript:"):
                    continue
                joined = urljoin(base_url, src)
                src_l = joined.lower()
                if "logo" in alt or "logo" in src_l or "wordmark" in src_l:
                    candidates.append(joined)

            # Priority 3: og:image / og:logo / twitter:image
            for prop in ("og:image", "og:logo", "twitter:image"):
                el = soup.find("meta", attrs={"property": prop}) or soup.find("meta", attrs={"name": prop})
                if el and el.get("content"):
                    candidates.append(urljoin(base_url, el["content"]))

            seen: set[str] = set()
            unique: list[str] = []
            for c in candidates:
                if c not in seen:
                    seen.add(c)
                    unique.append(c)

            for cand in unique[:10]:
                try:
                    ir = await hc.get(cand)
                except Exception:
                    continue
                if ir.status_code != 200:
                    continue
                ctype = (ir.headers.get("content-type") or "").lower().split(";")[0].strip()
                if not ctype.startswith("image/"):
                    ext = cand.rsplit(".", 1)[-1].lower().split("?")[0]
                    ctype = {
                        "svg": "image/svg+xml",
                        "png": "image/png",
                        "jpg": "image/jpeg",
                        "jpeg": "image/jpeg",
                        "webp": "image/webp",
                        "ico": "image/x-icon",
                    }.get(ext)
                    if not ctype:
                        continue
                body = ir.content
                if not body or len(body) > 600_000 or len(body) < 200:
                    continue
                # gpt-image-2 accepts PNG / JPG / WEBP. SVG must be rasterized first.
                if ctype == "image/svg+xml":
                    try:
                        from cairosvg import svg2png  # type: ignore
                        body = svg2png(bytestring=body, output_width=512)
                        ctype = "image/png"
                    except Exception:
                        continue
                # Skip ICO too — model accepts PNG/JPG/WEBP best
                if ctype == "image/x-icon":
                    continue
                b64 = base64.b64encode(body).decode("ascii")
                return cand, f"data:{ctype};base64,{b64}"

            return None, None
    except Exception as e:
        logger.warning("Logo scrape failed for %s: %s", brand_url, e)
        return None, None


async def _openai_edit(
    openai_key: str,
    product_image_data_url: str,
    prompt: str,
    size: str = "1024x1024",
    quality: str = "medium",
    logo_data_url: Optional[str] = None,
) -> dict:
    """Call OpenAI gpt-image-2 /images/edits — composites the real uploaded product image
    (and optionally the scraped brand logo) into the scene.

    When `logo_data_url` is provided, it is passed as a SECOND `image` form field.
    The preservation prefix is adjusted so the model knows:
      • image #1 = product (PIXEL-FAITHFUL preservation)
      • image #2 = brand logo (composite faithfully wherever the prompt asks for a wordmark / logo / brand mark)

    Falls back to _openai_generate if the product image data URL is invalid or the edit call fails.
    """
    match = re.match(r"data:([^;]+);base64,(.+)", product_image_data_url, re.DOTALL)
    if not match:
        logger.warning("Invalid product image data URL — falling back to generate")
        return await _openai_generate(openai_key, prompt, size=size, quality=quality)

    media_type = match.group(1)
    try:
        image_bytes = base64.b64decode(match.group(2).strip())
    except Exception as e:
        logger.warning("Failed to decode product image: %s — falling back to generate", e)
        return await _openai_generate(openai_key, prompt, size=size, quality=quality)

    ext = "png" if "png" in media_type else ("jpg" if "jpeg" in media_type else "webp" if "webp" in media_type else "png")

    headers = {"Authorization": f"Bearer {openai_key}"}
    files: list[tuple[str, tuple[str, bytes, str]]] = [
        ("image", (f"product.{ext}", image_bytes, media_type)),
    ]

    # Try to attach the scraped logo as a SECOND reference image.
    logo_attached = False
    if logo_data_url:
        lmatch = re.match(r"data:([^;]+);base64,(.+)", logo_data_url, re.DOTALL)
        if lmatch:
            l_media = lmatch.group(1)
            try:
                l_bytes = base64.b64decode(lmatch.group(2).strip())
                l_ext = "png" if "png" in l_media else ("jpg" if "jpeg" in l_media else "webp" if "webp" in l_media else "png")
                files.append(("image", (f"logo.{l_ext}", l_bytes, l_media)))
                logo_attached = True
            except Exception as e:
                logger.warning("Failed to decode logo data URL: %s — proceeding without logo", e)

    # GLOBAL GUARDRAILS — applied to every /images/edits call regardless of template.
    if logo_attached:
        preservation_prefix = (
            "TWO REFERENCE IMAGES are provided. "
            "IMAGE #1 = THE PRODUCT (STRICT PIXEL-FAITHFUL PRESERVATION, highest priority): "
            "Reproduce the product PIXEL-FAITHFUL — keep its exact shape, silhouette, proportions, colors, "
            "materials, label, typography, packaging, on-product logos, on-product text, finish, and "
            "orientation completely unchanged. Do NOT redraw, restyle, redesign, recolor, relabel, replace, "
            "regenerate, or reinterpret the product. Treat the product as a fixed photographic element. "
            "IMAGE #2 = THE OFFICIAL BRAND LOGO / WORDMARK: "
            "Wherever the scene description below asks for a brand wordmark, brand logo, brand pill, "
            "brand mark, masthead logo, sticker, or any reference to '[BRAND NAME]' as a graphic element, "
            "you MUST composite IMAGE #2 faithfully — keep its exact letterforms, colors, and proportions. "
            "Do NOT invent a substitute wordmark, do not approximate the lettering, do not transcribe the "
            "brand name in a different typeface. Resize and place the logo per the prompt's spec, but the "
            "logo artwork itself is fixed. Add a subtle white or brand-neutral background pill behind the "
            "logo only if the prompt explicitly asks for it. "
            "SCOPE LOCK: Render exactly the scene described below — including ALL HEADLINES, BODY COPY, "
            "BADGES, CALLOUTS, CTAs, AND OTHER TYPOGRAPHY the prompt specifies. Render every text string "
            "the prompt names in quotation marks, faithfully and legibly, using the type weights/sizes/"
            "colors the prompt calls for. Do NOT add any EXTRA people, animals, text, watermarks, "
            "UI chrome, browser/website elements, or decorative additions that the prompt does not "
            "explicitly request. (Note: 'no extra text' means do not invent additional words beyond what "
            "the prompt specifies — it does NOT mean omit the headlines/copy the prompt asks for, and "
            "it does NOT mean omit the brand logo from image #2.) "
            "CLEAN OUTPUT: no website navigation bars, no browser headers, no UI chrome, no dark "
            "header bands from the reference images. "
            "SCENE TO COMPOSITE THE PRODUCT AND LOGO INTO: "
        )
    else:
        preservation_prefix = (
            "STRICT PRODUCT PRESERVATION (highest priority, overrides any conflicting instruction below): "
            "The input reference image IS the product. Reproduce the product PIXEL-FAITHFUL — keep its "
            "exact shape, silhouette, proportions, colors, materials, label, typography, packaging, "
            "logos, text, finish, and orientation completely unchanged. Do NOT redraw, restyle, "
            "redesign, recolor, relabel, replace, regenerate, or reinterpret the product. Do NOT add "
            "or remove product features, ingredients, accessories, or variants. Treat the product as "
            "a fixed photographic element to be composited as-is into the new scene. "
            "SCOPE LOCK: Render exactly the scene described below — including ALL HEADLINES, BODY COPY, "
            "BADGES, CALLOUTS, CTAs, AND OTHER TYPOGRAPHY the prompt specifies. Render every text string "
            "the prompt names in quotation marks, faithfully and legibly, using the type weights/sizes/"
            "colors the prompt calls for. Do NOT add any EXTRA people, animals, text, logos, watermarks, "
            "UI chrome, browser/website elements, or decorative additions that the prompt does not "
            "explicitly request. (Note: 'no extra text' means do not invent additional words beyond what "
            "the prompt specifies — it does NOT mean omit the headlines/copy the prompt asks for.) "
            "CLEAN OUTPUT: no website navigation bars, no browser headers, no UI chrome, no dark "
            "header bands from the reference image. "
            "SCENE TO COMPOSITE THE PRODUCT INTO: "
        )
    clean_prompt = preservation_prefix + prompt
    data = {
        "model": OPENAI_IMAGE_MODEL,
        "prompt": clean_prompt,
        "size": size,
        "quality": quality,
        "n": "1",
    }

    try:
        async with httpx.AsyncClient(timeout=120.0) as hc:
            resp = await hc.post(
                "https://api.openai.com/v1/images/edits",
                headers=headers,
                files=files,
                data=data,
            )
            if resp.status_code != 200:
                try:
                    error_detail = resp.json().get("error", {}).get("message", resp.text[:200])
                except Exception:
                    error_detail = resp.text[:200]
                logger.warning("images/edits failed (%s): %s — falling back to generate", resp.status_code, error_detail)
                return await _openai_generate(openai_key, prompt, size=size, quality=quality)

            resp_data = resp.json()
            image_data = resp_data.get("data", [])
            if not image_data:
                return {"error": "no image returned from edit endpoint"}
            b64_data = image_data[0].get("b64_json")
            if not b64_data:
                return {"error": "no b64_json in edit response"}

            out_bytes = base64.b64decode(b64_data)
            image_id = str(uuid.uuid4()) + ".png"
            image_path = IMAGES_DIR / image_id
            await asyncio.to_thread(image_path.write_bytes, out_bytes)
            return {"url": f"/api/images/{image_id}"}
    except Exception as e:
        logger.error("OpenAI image edit exception: %s — falling back to generate", e)
        return await _openai_generate(openai_key, prompt, size=size, quality=quality)


async def _openai_generate(openai_key: str, prompt: str, size: str = "1024x1024", quality: str = "medium") -> dict:
    """Call OpenAI gpt-image-2 to generate one image. Saves PNG to IMAGES_DIR. Returns {url} or {error}."""
    headers = {
        "Authorization": f"Bearer {openai_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": OPENAI_IMAGE_MODEL,
        "prompt": prompt,
        "n": 1,
        "size": size,
        "quality": quality,
    }
    try:
        async with httpx.AsyncClient(timeout=120.0) as hc:
            resp = await hc.post("https://api.openai.com/v1/images/generations", headers=headers, json=payload)
            if resp.status_code != 200:
                try:
                    error_detail = resp.json().get("error", {}).get("message", resp.text[:200])
                except Exception:
                    error_detail = resp.text[:200]
                return {"error": f"OpenAI {resp.status_code}: {error_detail}"}
            data = resp.json()
            image_data = data.get("data", [])
            if not image_data:
                return {"error": "no image returned"}
            b64_data = image_data[0].get("b64_json")
            if not b64_data:
                return {"error": "no b64_json in response"}
            image_bytes = base64.b64decode(b64_data)
            image_id = str(uuid.uuid4()) + ".png"
            image_path = IMAGES_DIR / image_id
            await asyncio.to_thread(image_path.write_bytes, image_bytes)
            return {"url": f"/api/images/{image_id}"}
    except Exception as e:
        return {"error": f"OpenAI image generation failed: {str(e)[:200]}"}


def _aspect_to_openai_size(aspect: str) -> str:
    """Map human aspect string to gpt-image-2 supported size presets.
    Safe for both /images/generations and /images/edits endpoints.
    """
    a = (aspect or "1:1").strip()
    if a == "1:1":
        return "1024x1024"
    if a in ("4:5", "9:16"):
        return "1024x1536"   # portrait preset
    if a == "16:9":
        return "2048x1152"   # native 16:9 2K preset
    if a == "4:3":
        return "1536x1024"   # landscape 3:2 preset
    return "1024x1024"


async def _claude_vision_analyze(api_key: str, product_images: List[str]) -> str:
    """Use Claude Vision to analyze uploaded product images and return a detailed product description."""
    if not product_images:
        return ""
    content = []
    for img_data_url in product_images[:3]:  # max 3 images for context
        if img_data_url.startswith("data:"):
            match = re.match(r"data:([^;]+);base64,(.+)", img_data_url, re.DOTALL)
            if match:
                media_type = match.group(1)
                b64_data = match.group(2).strip()
                content.append({
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": media_type,
                        "data": b64_data,
                    },
                })
    if not content:
        return ""
    content.append({
        "type": "text",
        "text": (
            "You are a product photography and packaging expert. Analyze this product image (or images) "
            "and describe the product in precise, visual detail for use in AI image-generation prompts. "
            "Cover: exact colors and finishes, shape and silhouette, label/logo style and placement, "
            "packaging material and texture, distinctive visual features, and any visible text or graphics. "
            "Be specific and concrete — 3–4 sentences. This description will be embedded verbatim into "
            "ad creative generation prompts so every generated image accurately depicts this product."
        ),
    })

    def _run():
        c = anthropic.Anthropic(api_key=api_key)
        msg = c.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=400,
            messages=[{"role": "user", "content": content}],
        )
        return msg.content[0].text

    try:
        return await asyncio.to_thread(_run)
    except Exception as e:
        logger.warning("Product vision analysis failed: %s", e)
        return ""


# =============== Routes ===============

@api_router.get("/")
async def root():
    return {"service": "ads-studio", "status": "ok"}


@api_router.post("/keys/test-anthropic")
async def test_anthropic(x_anthropic_key: Optional[str] = Header(None)):
    key = _require_anthropic_key(x_anthropic_key)
    try:
        await _claude_call(key, "Reply with the single word OK.", "ping", max_tokens=10)
        return {"ok": True, "model": CLAUDE_MODEL}
    except anthropic.AuthenticationError:
        raise HTTPException(status_code=401, detail="Invalid Anthropic key")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Anthropic test failed: {str(e)[:160]}")


@api_router.post("/keys/test-openai")
async def test_openai(x_openai_key: Optional[str] = Header(None)):
    key = _require_openai_key(x_openai_key)
    headers = {"Authorization": f"Bearer {key}"}
    try:
        async with httpx.AsyncClient(timeout=15.0) as hc:
            resp = await hc.get("https://api.openai.com/v1/models", headers=headers)
        if resp.status_code in (401, 403):
            raise HTTPException(status_code=401, detail="Invalid OpenAI key")
        return {"ok": True, "model": OPENAI_IMAGE_MODEL}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"OpenAI test failed: {str(e)[:160]}")


@api_router.post("/brands", response_model=Brand)
async def create_brand(payload: BrandCreate):
    images = (payload.product_images or [])[:5]
    brand = Brand(
        name=payload.name.strip(),
        url=payload.url.strip(),
        product_name=payload.product_name,
        product_images=images,
    )
    await db.brands.insert_one(brand.model_dump())
    return brand


@api_router.get("/brands", response_model=List[Brand])
async def list_brands():
    docs = await db.brands.find({}, {"_id": 0}).sort("created_at", -1).to_list(500)
    brands: List[Brand] = []
    for d in docs:
        b = Brand(**d)
        latest = await db.ad_runs.find_one({"brand_id": b.id}, {"_id": 0}, sort=[("created_at", -1)])
        if latest:
            creatives = latest.get("creatives", [])
            done = [c for c in creatives if c.get("image_url")]
            b.total_ads = len(creatives)
            b.done_ads = len(done)
            b.thumb_urls = [c["image_url"] for c in done[:3]]
            b.cost = round(len(done) * 0.12, 2)  # display estimate
        brands.append(b)
    return brands


@api_router.get("/brands/{brand_id}", response_model=Brand)
async def get_brand(brand_id: str):
    doc = await db.brands.find_one({"id": brand_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Brand not found")
    return Brand(**doc)


@api_router.delete("/brands/{brand_id}")
async def delete_brand(brand_id: str):
    res = await db.brands.delete_one({"id": brand_id})
    await db.ad_runs.delete_many({"brand_id": brand_id})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Brand not found")
    return {"ok": True}


@api_router.post("/brands/{brand_id}/research", response_model=Brand)
async def brand_research(brand_id: str, x_anthropic_key: Optional[str] = Header(None)):
    api_key = _require_anthropic_key(x_anthropic_key)
    doc = await db.brands.find_one({"id": brand_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Brand not found")
    brand = Brand(**doc)

    site = await _scrape_url(brand.url)
    # Logo scrape runs in parallel with no fatal effect if it fails
    logo_url, logo_data_url = await _scrape_logo(brand.url)
    if logo_url:
        logger.info("Logo scraped for %s → %s (%d bytes data url)", brand.name, logo_url, len(logo_data_url or ""))
    else:
        logger.info("No logo found for %s", brand.name)

    # GLOBAL RULE — uploaded products are the only source of truth.
    # If the user has uploaded product images, run Claude Vision FIRST so the
    # product_details block in the Brand DNA is grounded in the actual photos
    # (not Claude's imagination from website copy). If no images, we tell Claude
    # to leave product_details empty rather than fabricate.
    has_uploaded_products = bool(brand.product_images)
    product_vision_summary = ""
    if has_uploaded_products:
        logger.info("Vision analysis on %d uploaded product image(s) for %s",
                    len(brand.product_images), brand.name)
        product_vision_summary = await _claude_vision_analyze(api_key, brand.product_images)
        if product_vision_summary:
            logger.info("Vision summary: %s", product_vision_summary[:120])

    system = (
        "You are a senior brand strategist + visual designer doing DEEP brand reverse-engineering. "
        "You will receive a website excerpt that includes CONCRETE CSS EVIDENCE: actual font-family "
        "declarations, Google Fonts loaded, hex colors found in CSS, and CSS variables. "
        "GROUNDING RULES (mandatory): "
        "  • Every hex value you output MUST come from the HEX_COLORS_FOUND list — never invent colors. "
        "  • Font names MUST come from FONT_FAMILIES_FOUND or GOOGLE_FONTS_LOADED — never guess. "
        "  • If evidence is missing for a field, set it to an honest empty string \"\" — never fabricate. "
        "  • Pick the PRIMARY color as the most brand-distinctive non-neutral hex; SECONDARY as the "
        "    next supporting hue; ACCENT as the call-to-action or highlight color (often the boldest); "
        "    NEUTRAL as the dominant near-white/near-black/cream. "
        "  • For fonts: pick the display/heading family used in hero/banner, then the body family. "
        "  • Strip generic fallbacks like 'sans-serif', '-apple-system', 'system-ui' when reporting. "
        "  • PRODUCT GROUNDING (global rule, no exceptions): the 'product_details' block must reflect "
        "    ONLY the actual product(s) the user has uploaded. If a UPLOADED_PRODUCT_VISION block is "
        "    provided in the user message, ground every product_details field strictly in that block — "
        "    do NOT invent SKUs, flavors, variants, ingredients, materials, or packaging that aren't "
        "    visible in the uploaded photos. If NO UPLOADED_PRODUCT_VISION block is provided, set "
        "    EVERY product_details field to empty string \"\" — do NOT fabricate product appearance from "
        "    the website copy. Same rule applies to product_name and any product references inside "
        "    brand_overview / ad_creative_style — never invent. "
        "Always reply with a single valid JSON object — no prose, no markdown."
    )

    product_vision_block = (
        f"\n\nUPLOADED_PRODUCT_VISION (the user has uploaded the actual product photos — ground every "
        f"product_details field strictly in this description, do not invent variants):\n\"\"\"\n"
        f"{product_vision_summary}\n\"\"\""
        if product_vision_summary
        else "\n\nNO UPLOADED_PRODUCT_VISION PROVIDED — leave EVERY product_details field as empty "
             "string \"\". Do not fabricate product appearance, packaging, or features from the "
             "website copy."
    )
    user = f"""Analyze this website and extract the full brand DNA for "{brand.name}".

Be thorough and SPECIFIC — every field must reflect this brand, not generic advice.
Use the CSS EVIDENCE block to ground colors and fonts. Use the homepage and secondary
page text to ground tone, voice, positioning, and competitive differentiation.

Output ONLY this JSON shape (use empty strings or arrays if a field is genuinely unknown — never null):
{{
  "palette": {{ "primary": "#hex", "secondary": "#hex", "accent": "#hex", "neutral": "#hex" }},
  "fonts": ["Display font (with weight)", "Body font (with weight)"],
  "tone": "2-3 sentence description of verbal tone with concrete examples from the copy",
  "photography_style": "2-3 sentence description of visual / photography direction with specifics on lighting, framing, subjects",
  "brand_voice": "1-2 sentences on how the brand sounds (e.g. 'warm, direct, no fluff — like a knowledgeable friend')",
  "keywords": ["six", "to", "ten", "evocative", "brand-specific", "keywords"],
  "brand_overview": {{
    "tagline": "their actual tagline pulled from the copy, or a representative one-liner",
    "design_agency": "agency name if discoverable, else 'Unknown'",
    "voice_adjectives": ["five", "to", "seven", "voice", "adjectives"],
    "positioning": "2-3 sentence positioning statement grounded in the site copy",
    "competitive_differentiation": "2-3 sentences on what genuinely sets them apart"
  }},
  "visual_system": {{
    "primary_font": "exact font name + weight notes (e.g. 'Inter, 700 for headlines')",
    "secondary_font": "exact font name + weight notes",
    "primary_color": "#hex (semantic description — e.g. 'deep terracotta, used on CTAs')",
    "secondary_color": "#hex (semantic description)",
    "accent_color": "#hex (semantic description)",
    "background_colors": "concrete description of background usage (cream, white, gradient, etc.)",
    "cta_color_and_style": "color + button style (pill, sharp, outlined, filled, hover behavior)"
  }},
  "photography_direction": {{
    "lighting": "specific lighting description (e.g. 'soft north-window daylight with gentle shadows')",
    "color_grading": "grading description (e.g. 'warm highlights, slightly desaturated greens')",
    "composition": "composition rules (e.g. 'centered hero shots, generous negative space, 4:5 framing')",
    "subject_matter": "what is photographed (product alone? lifestyle? hands-in-frame?)",
    "props_and_surfaces": "signature props and surface materials",
    "mood": "overall mood in 1 sentence"
  }},
  "product_details": {{
    "physical_description": "what the product looks like — be specific about shape, materials, packaging",
    "label_logo_placement": "where the label/logo sits on the product",
    "distinctive_features": "what is visually distinctive",
    "packaging_system": "describe the packaging system — bottles, boxes, color-coding"
  }},
  "ad_creative_style": {{
    "typical_formats": "typical ad formats observed (carousels, big headlines, lifestyle, testimonials)",
    "text_overlay_style": "how text overlays are treated (size, alignment, font, color)",
    "photo_vs_illustration": "balance of photo vs illustration",
    "ugc_usage": "how UGC is used (if at all)",
    "offer_presentation": "how offers/discounts are presented"
  }},
  "image_generation_modifier": "A single paragraph (~80 words) that will be PREPENDED to every ad-image prompt. Capture lighting, color grading, exact palette hexes, type style, mood, signature props. Concrete, sensory, image-gen ready — name the colors and the lighting setup explicitly."
}}

Website excerpt:
\"\"\"
{site}
\"\"\"{product_vision_block}"""
    raw = await _claude_call(api_key, system, user, max_tokens=3500)
    try:
        identity = BrandIdentity(**_extract_json(raw))
    except Exception as e:
        logger.error("Identity parse failed: %s | raw=%s", e, raw[:300])
        raise HTTPException(status_code=502, detail="Failed to parse brand identity from Claude")

    await db.brands.update_one(
        {"id": brand_id},
        {"$set": {
            "identity": identity.model_dump(),
            "cover_color": identity.palette.accent,
            "logo_url": logo_url,
            "logo_data_url": logo_data_url,
        }},
    )
    updated = await db.brands.find_one({"id": brand_id}, {"_id": 0})
    return Brand(**updated)


class GenerateRequest(BaseModel):
    angle: Optional[str] = None  # optional creative angle / brief from user


@api_router.post("/brands/{brand_id}/generate", response_model=AdRun)
async def generate_creatives(
    brand_id: str,
    payload: GenerateRequest,
    x_anthropic_key: Optional[str] = Header(None),
    x_openai_key: Optional[str] = Header(None),
):
    """Creates a pending AdRun and immediately returns (<1s).
    The full pipeline (vision → prompts → image gen) runs in the background.
    Poll GET /brands/{id}/runs to track progress.
    """
    a_key = _require_anthropic_key(x_anthropic_key)
    o_key = _require_openai_key(x_openai_key)

    doc = await db.brands.find_one({"id": brand_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Brand not found")
    brand = Brand(**doc)
    if not brand.identity:
        raise HTTPException(status_code=400, detail="Run brand research first")
    # GLOBAL RULE — uploaded products are the only source of truth.
    # Block generation outright when no product image is attached so we never
    # fall through to text-to-image (which would synthesize a fake product).
    if not brand.product_images:
        raise HTTPException(
            status_code=400,
            detail=(
                "No product image attached. Upload at least one product photo before generating "
                "creatives — this app only composites the user's actual product, it never invents "
                "or synthesizes products."
            ),
        )

    settings_doc = await db.settings.find_one({"id": "defaults"}, {"_id": 0})
    settings = Settings(**settings_doc) if settings_doc else Settings()
    oai_quality = QUALITY_TO_OAI.get(settings.quality, "medium")

    # Create a pending run — return this immediately, pipeline runs in background
    run = AdRun(brand_id=brand_id, status="pending")
    await db.ad_runs.insert_one(run.model_dump())

    asyncio.create_task(
        _full_pipeline_background(run.id, brand, payload.angle, a_key, o_key, oai_quality)
    )

    return run


@api_router.post("/runs/{run_id}/creatives/{creative_id}/regenerate", response_model=AdRun)
async def regenerate_single_creative(
    run_id: str,
    creative_id: str,
    x_anthropic_key: Optional[str] = Header(None),
    x_openai_key: Optional[str] = Header(None),
):
    """Re-renders ONE creative inside an existing run.

    Pulls the existing prompt + aspect for that creative and re-calls OpenAI
    images/edits with the brand's uploaded product image. Clears the existing
    image_url + error so the frontend tile shows 'rendering…' until done.
    """
    o_key = _require_openai_key(x_openai_key)
    _ = x_anthropic_key  # accepted for symmetry; not needed for image-only redo

    run_doc = await db.ad_runs.find_one({"id": run_id}, {"_id": 0})
    if not run_doc:
        raise HTTPException(status_code=404, detail="Run not found")
    run = AdRun(**run_doc)

    creative = next((c for c in run.creatives if c.id == creative_id), None)
    if not creative:
        raise HTTPException(status_code=404, detail="Creative not found in this run")

    brand_doc = await db.brands.find_one({"id": run.brand_id}, {"_id": 0})
    if not brand_doc:
        raise HTTPException(status_code=404, detail="Brand not found")
    brand = Brand(**brand_doc)
    # GLOBAL RULE — uploaded products are the only source of truth.
    if not brand.product_images:
        raise HTTPException(
            status_code=400,
            detail=(
                "No product image attached. Upload at least one product photo before regenerating — "
                "this app only composites the user's actual product, it never invents or synthesizes "
                "products."
            ),
        )

    settings_doc = await db.settings.find_one({"id": "defaults"}, {"_id": 0})
    settings = Settings(**settings_doc) if settings_doc else Settings()
    oai_quality = QUALITY_TO_OAI.get(settings.quality, "medium")

    brand_modifier = ""
    if brand.identity and brand.identity.image_generation_modifier:
        brand_modifier = brand.identity.image_generation_modifier

    # Clear existing image/error so UI shows 'rendering…' on this tile only
    await db.ad_runs.update_one(
        {"id": run_id, "creatives.id": creative_id},
        {"$set": {
            "creatives.$.image_url": None,
            "creatives.$.error": None,
        }},
    )

    asyncio.create_task(
        _generate_images_background(
            run_id, [creative], o_key, oai_quality,
            brand.product_images or None, brand_modifier, brand.logo_data_url,
        )
    )

    fresh = await db.ad_runs.find_one({"id": run_id}, {"_id": 0})
    return AdRun(**fresh)


async def _full_pipeline_background(
    run_id: str,
    brand: "Brand",
    angle: Optional[str],
    a_key: str,
    o_key: str,
    quality: str,
):
    """Full generation pipeline running entirely in background:
    Step 1 — Claude Vision: analyze uploaded product photos
    Step 2 — Claude Prompts: write scene-composition prompts per template
    Step 3 — GPT Image 2: composite product into each scene (images/edits)
    """
    try:
        # ── Step 1: Vision ──
        product_visual_description = ""
        if brand.product_images:
            logger.info("Run %s: vision analysis (%d images)", run_id, len(brand.product_images))
            product_visual_description = await _claude_vision_analyze(a_key, brand.product_images)
            if product_visual_description:
                logger.info("Run %s: vision done — %s", run_id, product_visual_description[:80])

        # ── Step 2: Prompts ──
        logger.info("Run %s: generating prompts", run_id)
        creatives = await _build_prompts(run_id, brand, angle, a_key, product_visual_description)
        if not creatives:
            await db.ad_runs.update_one(
                {"id": run_id},
                {"$set": {"status": "failed", "error": "Claude returned no prompts"}},
            )
            return

        # Save prompts; mark run as "running" so frontend shows phase 03 active
        await db.ad_runs.update_one(
            {"id": run_id},
            {"$set": {"creatives": [c.model_dump() for c in creatives], "status": "running"}},
        )
        logger.info("Run %s: %d prompts saved, starting image generation", run_id, len(creatives))

        # ── Step 3: Images ──
        brand_modifier = ""
        if brand.identity and brand.identity.image_generation_modifier:
            brand_modifier = brand.identity.image_generation_modifier
        await _generate_images_background(
            run_id, creatives, o_key, quality,
            brand.product_images or None, brand_modifier, brand.logo_data_url,
        )

    except Exception as e:
        logger.error("Run %s: pipeline error: %s", run_id, e, exc_info=True)
        await db.ad_runs.update_one(
            {"id": run_id},
            {"$set": {"status": "failed", "error": str(e)[:300]}},
        )


async def _build_prompts(
    run_id: str,
    brand: "Brand",
    angle: Optional[str],
    a_key: str,
    product_visual_description: str,
) -> List[AdCreative]:
    """Ask Claude to write image-generation prompts for each enabled template.
    Returns a list of AdCreative objects (no image_url yet).
    """
    identity_json = json.dumps(brand.identity.model_dump(), indent=2)
    angle_line = f"Creative angle: {angle}" if angle else "Creative angle: open / surprise the user"

    if product_visual_description:
        photos_line = (
            f"Product visual description (from uploaded photos):\n"
            f"\"\"\"{product_visual_description}\"\"\"\n"
            f"There are {len(brand.product_images)} reference photo(s)."
        )
    elif brand.product_images:
        photos_line = f"Reference photos: {len(brand.product_images)} product photo(s) provided."
    else:
        photos_line = "Reference photos: none."

    modifier = (brand.identity.image_generation_modifier or "").strip()
    # NOTE: the brand modifier is prepended programmatically before each OpenAI
    # call (see _generate_images_background → _openai_edit/_openai_generate),
    # NOT by Claude. Asking Claude to repeat the modifier verbatim in all 15
    # prompts inflated the response past max_tokens and truncated the JSON.
    modifier_line = (
        f"\n\nBRAND VISUAL STYLE (already enforced downstream — do NOT repeat in your prompts; "
        f"just write scenes that are stylistically consistent with it):\n\"\"\"{modifier}\"\"\"\n"
        if modifier else ""
    )

    # Scene-focused instruction when real product image will be passed to the model
    using_image_edit = bool(brand.product_images)
    if using_image_edit:
        image_mode_instruction = (
            "GLOBAL RULE — APPLIES TO EVERY TEMPLATE (current or future, built-in or custom): "
            "The user's uploaded product photo will be composited directly into every generated "
            "creative via OpenAI's images/edits endpoint and is the SOURCE OF TRUTH. "
            "DO NOT invent, substitute, or describe a replacement product. "
            "DO NOT describe the product's visual appearance (colors, shape, label, packaging, "
            "ingredients, materials) — the model already sees the real image. "
            "Every scene you write MUST naturally accommodate and prominently feature this exact "
            "product as-is, even if the template scaffold suggests it is optional or omits it. "
            "Refer to the product simply as 'the product' or 'this product'. "
            "Focus your prompt on SCENE, STAGING, and CONTEXT only: background environment, "
            "surface/props, lighting setup, composition, camera angle, and mood — designed to "
            "showcase the uploaded product."
        )
    else:
        image_mode_instruction = (
            "No product reference image is provided — describe the product visually in your prompt "
            "based on the brand identity and any product details available."
        )

    await _seed_templates_if_empty()
    tpl_docs = await db.templates.find({"enabled": True}, {"_id": 0}).sort("number", 1).to_list(20)
    enabled = [Template(**d) for d in tpl_docs][:15]

    if enabled:
        # When a product image is uploaded, the "needs product" per-template hint is
        # misleading — every template will composite the real product regardless. Suppress it.
        templates_block = "\n".join(
            f"  №{t.number:02d} [{t.aspect} · {t.category}"
            f"{'' if using_image_edit else (' · needs product' if t.needs_product else '')}] "
            f"{t.name}: {t.scaffold}"
            for t in enabled
        )
        if using_image_edit:
            system = (
                "You are a world-class art director writing image-generation prompts that will be "
                "sent to OpenAI's /images/edits endpoint together with the user's actual product photo. "
                f"{image_mode_instruction} "
                "OUTPUT CONSTRAINTS for every prompt you write: "
                "  • Single paragraph, 60-110 words (extend up to 130 when the scaffold requires multi-line copy). "
                "  • Describe scene + staging + lighting + composition + mood around 'the product'. "
                "  • NEVER describe the product's appearance (shape, colors, label, packaging, materials, "
                "    ingredients, typography). Treat the product as an opaque fixed object. "
                "  • NEVER invent, synthesize, or substitute a different product. The uploaded image IS "
                "    the only product. Do not mention alternate SKUs, additional flavors, variants, "
                "    a 'similar product', 'a product like this', or any other product object the user "
                "    did not upload. When a scaffold asks for multiple units (tower, bundle, cart), all "
                "    units MUST be identical pixel-faithful copies of the uploaded reference. "
                "  • NEVER use words that imply altering the product: 'redesign', 'restyle', 'recolor', "
                "    'rebrand', 'redrawn', 'new packaging', 'variant', 'reimagined', 'stylised version'. "
                "  • COPY IS MANDATORY when the scaffold names it. Most scaffolds explicitly require "
                "    rendered typography — headlines, sub-headlines, badges, callouts, CTAs, captions, "
                "    pull-quotes, star ratings, attribution lines, qualifier copy, manifesto blocks, etc. "
                "    For EVERY one of those elements, you must WRITE THE ACTUAL FINAL WORDS verbatim "
                "    inside double quotes in your prompt, adapted to this brand's voice (e.g. "
                "    render the headline \"STRONG. CLEAN. AUSTRALIAN.\" / render the CTA pill reading "
                "    \"SHOP THE STACK\" / render the qualifier \"Discount applied automatically at "
                "    checkout when you buy 2 or more.\"). Do not output bracketed placeholders like "
                "    [HEADLINE] or [CTA TEXT] — replace them with real copy. Do not leave the scaffold's "
                "    example text untouched if it doesn't fit the brand. "
                "  • CTA IS MANDATORY for every template that could plausibly carry one (Headline, Offer, "
                "    Bait-and-Switch, Stat Surround, Manifesto, Lifestyle UGC, Bundle, Tower, Curved-Type, "
                "    and any future user-created template that names an action/button/pill). When the "
                "    scaffold does NOT explicitly forbid a CTA, include a short verb-forward CTA pill at "
                "    the bottom of the composition — e.g. 'SHOP NOW', 'TRY IT TODAY', 'GET YOURS', "
                "    'ADD TO BAG', 'JOIN THE CLUB'. Specify its style: rounded-pill button, brand primary "
                "    or accent fill, white tracked-caps body type ~14pt. ONLY omit the CTA when the "
                "    template is a pure editorial/testimonial format that explicitly forbids commercial "
                "    elements (Press Editorial, Faux iPhone Screenshot, Review Card). "
                "  • LOGO IS THE SCRAPED ACTUAL LOGO — image #2 of the reference inputs. Whenever your "
                "    prompt references a brand wordmark, brand logo, brand pill, brand mark, masthead "
                "    sticker, or anything written as '[BRAND NAME]' as a graphic element, instruct the "
                "    model to composite IMAGE #2 (the brand's actual logo) — do NOT instruct the model "
                "    to typeset the brand name as if it were ordinary text. Write phrases like 'composite "
                "    the brand logo from image #2 onto a small rounded-pill background, bottom-right, "
                "    ~50px tall' instead of 'render the wordmark BOBBI in serif type'. "
                "  • Specify type weight + alignment for each rendered string (e.g. 'extra-bold display "
                "    sans, all caps, tight tracking, left-aligned'). "
                "  • STAY IN SCOPE of the template scaffold. Do not invent extra subjects, characters, "
                "    or narrative elements that the scaffold does not call for. "
                "Adapt each scaffold to the brand palette, photography style, and tone. "
                "OUTPUT FORMAT (strict): Reply with ONLY a single valid JSON object. The response "
                "MUST start with the character `{` and end with the character `}`. Do not wrap it "
                "in markdown fences, do not add any prose before or after. The exact shape is: "
                "{\"prompts\": [\"prompt 1\", \"prompt 2\", ...]}. Preserve template order."
            )
        else:
            system = (
                "You are a world-class art director specialising in performance ad creatives. "
                "For each provided template scaffold, write ONE vivid, production-ready image-generation "
                "prompt (40-80 words, single paragraph) that adapts the scaffold to the brand palette, "
                "photography style, and tone. "
                f"{image_mode_instruction} "
                "Describe a concrete scene: subject, composition, lighting, mood. Avoid rendered text. "
                "Stay strictly within the scope of each template scaffold — do not invent extra subjects "
                "or narrative elements not called for. "
                "OUTPUT FORMAT (strict): Reply with ONLY a single valid JSON object starting with `{` "
                "and ending with `}`. No markdown fences, no prose. Shape: "
                "{\"prompts\": [\"prompt 1\", \"prompt 2\", ...]}. Preserve template order."
            )
        user = f"""Brand: {brand.name}
Product: {brand.product_name or "(brand-level campaign)"}
{angle_line}
{photos_line}{modifier_line}

Brand identity:
{identity_json}

Templates ({len(enabled)}):
{templates_block}

Return exactly {len(enabled)} prompts, in the same order as the templates above."""
        target_count = len(enabled)
    else:
        system = (
            "You are a world-class art director specialising in performance ad creatives. "
            "Write 15 distinct, vivid, production-ready image-generation prompts for static social ad creatives. "
            "Every prompt must be a single paragraph (40-80 words), reference the brand palette, photography "
            "style, and tone, and describe a concrete scene with subject, composition, lighting, and mood. "
            f"{image_mode_instruction} "
            "Avoid text overlays. Vary scenes drastically across the 15. "
            "OUTPUT FORMAT (strict): Reply with ONLY a single valid JSON object starting with `{` "
            "and ending with `}`. No markdown fences, no prose. Shape: "
            "{\"prompts\": [\"prompt 1\", \"prompt 2\", ...]}."
        )
        user = f"""Brand: {brand.name}
Product: {brand.product_name or "(brand-level campaign)"}
{angle_line}
{photos_line}

Brand identity:
{identity_json}

Return 15 prompts."""
        target_count = 15

    raw = await _claude_call(a_key, system, user, max_tokens=8000)
    try:
        prompts = _extract_json(raw).get("prompts", [])
        prompts = [p.strip() for p in prompts if isinstance(p, str) and p.strip()][:target_count]
    except Exception as e:
        logger.error("Run %s: prompts parse failed: %s | raw=%s", run_id, e, raw[:300])
        return []

    creatives: List[AdCreative] = []
    for i, p in enumerate(prompts):
        if enabled and i < len(enabled):
            t = enabled[i]
            creatives.append(AdCreative(prompt=p, aspect=t.aspect, template_name=t.name, template_number=t.number))
        else:
            creatives.append(AdCreative(prompt=p, aspect="1:1"))
    return creatives


async def _generate_images_background(
    run_id: str,
    creatives: List[AdCreative],
    o_key: str,
    quality: str,
    product_images: Optional[List[str]] = None,
    brand_modifier: str = "",
    logo_data_url: Optional[str] = None,
):
    """Background task: for each creative, call gpt-image-2.

    GLOBAL RULE — uploaded product images are the source of truth:
    If the user has uploaded any product photo, EVERY creative (built-in or
    user-created template) is routed through OpenAI's /images/edits endpoint
    so the actual product image is composited into the final scene as-is.
    The template's `needs_product` flag is intentionally NOT consulted here —
    the rule applies uniformly across all current and future templates.
    Only when no product image was uploaded do we fall back to text-to-image
    generation via /images/generations.

    `brand_modifier` is the per-brand visual-style paragraph from research; it
    is prepended ONCE here (not by Claude) so every image is stylistically
    consistent without inflating the Claude response.

    `logo_data_url` is the scraped brand logo (base64 data URL). When provided,
    it's attached as a SECOND reference image so the model composites the
    real logo wherever the prompt asks for a wordmark / brand mark.

    Updates each creative in MongoDB as it completes.
    """
    # Use the first uploaded product image as the primary reference
    primary_product_image = (product_images[0] if product_images else None)
    mode = "edit+logo" if (primary_product_image and logo_data_url) else ("edit" if primary_product_image else "generate")
    logger.info("Run %s: image mode=%s, %d creatives", run_id, mode, len(creatives))

    sem = asyncio.Semaphore(4)
    style_prefix = (brand_modifier.strip() + " ") if brand_modifier and brand_modifier.strip() else ""

    async def worker(creative: AdCreative):
        size = _aspect_to_openai_size(creative.aspect)
        styled_prompt = style_prefix + creative.prompt
        async with sem:
            if primary_product_image:
                res = await _openai_edit(
                    o_key,
                    primary_product_image,
                    styled_prompt,
                    size=size,
                    quality=quality,
                    logo_data_url=logo_data_url,
                )
            else:
                res = await _openai_generate(o_key, styled_prompt, size=size, quality=quality)
        if "url" in res:
            await db.ad_runs.update_one(
                {"id": run_id, "creatives.id": creative.id},
                {"$set": {"creatives.$.image_url": res["url"]}},
            )
            logger.info("Image done: run=%s creative=%s mode=%s", run_id, creative.id, mode)
        else:
            err = res.get("error", "unknown")
            await db.ad_runs.update_one(
                {"id": run_id, "creatives.id": creative.id},
                {"$set": {"creatives.$.error": err}},
            )
            logger.warning("Image failed: run=%s creative=%s err=%s", run_id, creative.id, err)

    await asyncio.gather(*(worker(c) for c in creatives))

    updated = await db.ad_runs.find_one({"id": run_id}, {"_id": 0})
    if updated:
        done_count = sum(1 for c in updated.get("creatives", []) if c.get("image_url"))
        status = "done" if done_count > 0 else "failed"
        await db.ad_runs.update_one({"id": run_id}, {"$set": {"status": status}})
        logger.info("Run %s finished: %d/%d images, status=%s", run_id, done_count, len(creatives), status)


@api_router.get("/brands/{brand_id}/runs", response_model=List[AdRun])
async def list_runs(brand_id: str):
    docs = await db.ad_runs.find({"brand_id": brand_id}, {"_id": 0}).sort("created_at", -1).to_list(100)
    return [AdRun(**d) for d in docs]


@api_router.get("/brands/{brand_id}/download")
async def download_zip(brand_id: str):
    """Download all images from the latest ad run as a ZIP."""
    import io
    import zipfile
    from fastapi.responses import StreamingResponse

    brand = await db.brands.find_one({"id": brand_id}, {"_id": 0})
    if not brand:
        raise HTTPException(status_code=404, detail="Brand not found")
    run = await db.ad_runs.find_one({"brand_id": brand_id}, {"_id": 0}, sort=[("created_at", -1)])
    if not run:
        raise HTTPException(status_code=404, detail="No ad run found")

    creatives = [c for c in run.get("creatives", []) if c.get("image_url")]
    if not creatives:
        raise HTTPException(status_code=404, detail="No images available yet")

    buf = io.BytesIO()
    async with httpx.AsyncClient(timeout=60.0) as hc:
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for i, c in enumerate(creatives, start=1):
                try:
                    image_url = c.get("image_url", "")
                    if image_url.startswith("/api/images/"):
                        # Local file — read directly from disk
                        filename = image_url.split("/api/images/")[1]
                        local_path = IMAGES_DIR / filename
                        if not local_path.exists():
                            continue
                        img_content = await asyncio.to_thread(local_path.read_bytes)
                    else:
                        # External URL (legacy fal.ai)
                        r = await hc.get(image_url)
                        if r.status_code != 200:
                            continue
                        img_content = r.content
                    name = (c.get("template_name") or f"creative_{i}").replace("/", "-").replace(" ", "_")
                    fn = f"{i:02d}_{name}.png"
                    zf.writestr(fn, img_content)
                except Exception:
                    continue
            # also add a prompts.txt
            prompts_txt = "\n\n".join(
                f"#{i:02d} {c.get('template_name','')} [{c.get('aspect','')}]\n{c.get('prompt','')}"
                for i, c in enumerate(run.get("creatives", []), start=1)
            )
            zf.writestr("prompts.txt", prompts_txt)
    buf.seek(0)
    safe_name = (brand.get("name") or "brand").lower().replace(" ", "-")
    headers = {"Content-Disposition": f'attachment; filename="{safe_name}-ads.zip"'}
    return StreamingResponse(buf, media_type="application/zip", headers=headers)


@api_router.get("/images/{filename}")
async def serve_image(filename: str):
    """Serve a locally generated image by filename."""
    # Prevent path traversal
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")
    path = IMAGES_DIR / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="Image not found")
    return FileResponse(str(path), media_type="image/png")


# Legacy status routes preserved
@api_router.post("/status", response_model=StatusCheck)
async def create_status(input: StatusCheck):
    await db.status_checks.insert_one(input.model_dump())
    return input


@api_router.get("/status", response_model=List[StatusCheck])
async def get_status():
    docs = await db.status_checks.find({}, {"_id": 0}).to_list(1000)
    return [StatusCheck(**d) for d in docs]


# =============== Templates ===============

async def _seed_templates_if_empty():
    count = await db.templates.count_documents({})
    if count > 0:
        return
    docs = []
    for t in SEED_TEMPLATES:
        docs.append({"id": str(uuid.uuid4()), **t})
    if docs:
        await db.templates.insert_many(docs)
        logger.info("Seeded %d templates", len(docs))


@api_router.get("/templates", response_model=List[Template])
async def list_templates():
    await _seed_templates_if_empty()
    docs = await db.templates.find({}, {"_id": 0}).sort("number", 1).to_list(100)
    return [Template(**d) for d in docs]


class TemplatePatch(BaseModel):
    enabled: Optional[bool] = None
    scaffold: Optional[str] = None
    name: Optional[str] = None
    aspect: Optional[str] = None
    needs_product: Optional[bool] = None


class TemplateCreate(BaseModel):
    name: str
    scaffold: str
    aspect: str = "1:1"
    needs_product: bool = False
    category: str = "custom"
    enabled: bool = True


class Settings(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = "defaults"
    quality: str = "medium"           # low | medium | high
    variations_per_prompt: int = 1    # 1..4
    cost_cap_per_run_usd: float = 20.0


class SettingsPatch(BaseModel):
    quality: Optional[str] = None
    variations_per_prompt: Optional[int] = None
    cost_cap_per_run_usd: Optional[float] = None


QUALITY_TO_OAI = {"low": "low", "medium": "medium", "high": "high"}


@api_router.patch("/templates/{template_id}", response_model=Template)
async def update_template(template_id: str, patch: TemplatePatch):
    upd = {k: v for k, v in patch.model_dump().items() if v is not None}
    if not upd:
        raise HTTPException(status_code=400, detail="No fields to update")
    res = await db.templates.update_one({"id": template_id}, {"$set": upd})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Template not found")
    doc = await db.templates.find_one({"id": template_id}, {"_id": 0})
    return Template(**doc)


@api_router.post("/templates/reset", response_model=List[Template])
async def reset_templates():
    await db.templates.delete_many({})
    await _seed_templates_if_empty()
    docs = await db.templates.find({}, {"_id": 0}).sort("number", 1).to_list(100)
    return [Template(**d) for d in docs]


@api_router.post("/templates", response_model=Template, status_code=201)
async def create_template(payload: TemplateCreate):
    if not payload.name.strip() or not payload.scaffold.strip():
        raise HTTPException(status_code=400, detail="Name and scaffold are required")
    if payload.aspect not in {"1:1", "4:5", "9:16", "16:9", "4:3"}:
        raise HTTPException(status_code=400, detail="Invalid aspect ratio")
    last = await db.templates.find_one({}, {"_id": 0, "number": 1}, sort=[("number", -1)])
    next_number = (last["number"] + 1) if last and "number" in last else 1
    doc = {
        "id": str(uuid.uuid4()),
        "number": next_number,
        "name": payload.name.strip(),
        "scaffold": payload.scaffold.strip(),
        "aspect": payload.aspect,
        "needs_product": payload.needs_product,
        "category": payload.category.strip() or "custom",
        "enabled": payload.enabled,
    }
    await db.templates.insert_one(doc)
    return Template(**{k: v for k, v in doc.items() if k != "_id"})


@api_router.delete("/templates/{template_id}", status_code=204)
async def delete_template(template_id: str):
    res = await db.templates.delete_one({"id": template_id})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Template not found")
    return None


# =============== Settings ===============

@api_router.get("/settings", response_model=Settings)
async def get_settings():
    doc = await db.settings.find_one({"id": "defaults"}, {"_id": 0})
    if not doc:
        s = Settings()
        await db.settings.insert_one(s.model_dump())
        return s
    return Settings(**doc)


@api_router.patch("/settings", response_model=Settings)
async def update_settings(patch: SettingsPatch):
    upd = {k: v for k, v in patch.model_dump().items() if v is not None}
    if "quality" in upd and upd["quality"] not in QUALITY_TO_OAI:
        raise HTTPException(status_code=400, detail="quality must be low | medium | high")
    if "variations_per_prompt" in upd and not (1 <= int(upd["variations_per_prompt"]) <= 4):
        raise HTTPException(status_code=400, detail="variations_per_prompt must be 1..4")
    if "cost_cap_per_run_usd" in upd and float(upd["cost_cap_per_run_usd"]) < 0:
        raise HTTPException(status_code=400, detail="cost_cap_per_run_usd must be >= 0")
    await db.settings.update_one({"id": "defaults"}, {"$set": upd}, upsert=True)
    doc = await db.settings.find_one({"id": "defaults"}, {"_id": 0})
    return Settings(**doc)


app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup_db_client():
    """On startup, sync all template scaffolds/metadata from SEED_TEMPLATES to the DB.
    Preserves user-customised fields (enabled, aspect) while updating scaffold/name/category.
    """
    for seed in SEED_TEMPLATES:
        await db.templates.update_one(
            {"number": seed["number"]},
            {"$set": {
                "scaffold": seed["scaffold"],
                "name": seed["name"],
                "category": seed["category"],
                "needs_product": seed["needs_product"],
            }},
        )
    logger.info("Template scaffolds synced from SEED_TEMPLATES")


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
