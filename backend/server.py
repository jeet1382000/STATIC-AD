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
     "scaffold": "A bold headline advertisement for [BRAND NAME]. The headline reads: \"[HEADLINE TEXT]\" set in very large [HEADLINE FONT] type, centered. Beneath the headline, a concise subhead: \"[SUBHEAD COPY]\". The product is centered in the lower third on a flat [BRAND BACKGROUND COLOR] background. Use [BRAND PRIMARY COLOR] for the CTA button at the bottom: \"[CTA TEXT]\". Crisp studio lighting, clean composition, packaging visible and legible."},
    {"number": 2, "name": "Offer Promotion", "aspect": "1:1", "needs_product": True, "category": "offer", "enabled": False,
     "scaffold": "A square promotional ad for [BRAND NAME]. A large starburst or percent-off badge reading \"[OFFER %]\" dominates the top-right corner in [ACCENT COLOR]. Secondary copy below it: \"[OFFER COPY]\". The product sits hero-center against a [BRAND BACKGROUND COLOR] stage. Include small expiry text: \"[EXPIRY/TERMS]\". Energetic but still brand-consistent."},
    {"number": 3, "name": "Testimonial Card", "aspect": "4:5", "needs_product": False, "category": "social_proof", "enabled": True,
     "scaffold": "A vertical testimonial card for [BRAND NAME]. A large, elegant quotation: \"[QUOTE]\" in [BRAND HEADLINE FONT]. Beneath the quote: 5 filled stars in [ACCENT COLOR], then the attribution: \"[CUSTOMER NAME], [CUSTOMER CITY]\". Soft-focus lifestyle photo bleeds into a [BRAND BACKGROUND COLOR] panel. Minimal, premium, editorial tone."},
    {"number": 4, "name": "Feature Callout", "aspect": "4:5", "needs_product": True, "category": "product_feature", "enabled": True,
     "scaffold": "An annotated product diagram ad for [BRAND NAME]. The product is centered on a clean [BRAND BACKGROUND COLOR] surface. Four numbered pin-callouts (1-4) point to key parts of the product, each with a short label: [FEATURE 1], [FEATURE 2], [FEATURE 3], [FEATURE 4]. Thin connector lines in [ACCENT COLOR], numbers in circles. Small brand wordmark bottom-center."},
    {"number": 5, "name": "Us vs Them Comparison", "aspect": "1:1", "needs_product": True, "category": "comparison", "enabled": True,
     "scaffold": "A two-column comparison ad for [BRAND NAME]. Left column header: \"[BRAND NAME]\" in [BRAND PRIMARY COLOR] with the branded product shown crisply. Right column header: \"The Other Guys\" in a muted grey with a generic, uninspired competitor stand-in. Below each, four rows: [ATTRIBUTE 1], [ATTRIBUTE 2], [ATTRIBUTE 3], [ATTRIBUTE 4]. Brand column has green checkmarks; competitor column has grey X marks. Clean, Swiss grid layout."},
    {"number": 6, "name": "Before and After UGC", "aspect": "9:16", "needs_product": False, "category": "ugc", "enabled": True,
     "scaffold": "A vertical phone-shot split-screen for [BRAND NAME] showing before/after results. Left label: \"Before\" over a dim, flat lifestyle photo. Right label: \"After\" over a brighter, vivid lifestyle photo showing the [BRAND BENEFIT]. Authentic iPhone grain, slight natural imperfection. Small sticker-style brand logo bottom-right. Text overlay at top: \"[HEADLINE CLAIM]\"."},
    {"number": 7, "name": "Negative Marketing Bait-and-Switch", "aspect": "4:5", "needs_product": True, "category": "provocation", "enabled": True,
     "scaffold": "A provocative bait-and-switch ad for [BRAND NAME]. Top half, huge type on a [BRAND BACKGROUND COLOR] field: \"[PROVOCATIVE HEADLINE]\". Below it, smaller reveal copy: \"[BENEFIT TWIST]\". The product sits at the bottom, centered. Typography-driven, punchy, a bit cheeky. No stock imagery, just type and packaging."},
    {"number": 8, "name": "Press Editorial Layout", "aspect": "1:1", "needs_product": True, "category": "press", "enabled": True,
     "scaffold": "A faux magazine editorial page for [BRAND NAME]. Top masthead: \"[PUBLICATION NAME]\" in a classic serif with an issue date. A two-column layout: left column is a moody editorial photograph featuring the product, right column has the article headline \"[ARTICLE HEADLINE]\", a deck: \"[ARTICLE DECK]\", and body copy lorem-ipsum styled as a feature. A pull quote: \"[PULL QUOTE]\". Print texture, subtle paper grain."},
    {"number": 9, "name": "Review Card", "aspect": "1:1", "needs_product": False, "category": "social_proof", "enabled": True,
     "scaffold": "A faux app-review screenshot card for [BRAND NAME]. Square, light background. Five gold stars at the top. Review title: \"[REVIEW TITLE]\". Reviewer handle: \"[REVIEWER HANDLE]\" with a small avatar circle. Two-line review body: \"[REVIEW BODY]\". Tiny \"Verified Purchase\" badge. UI styled like a trustworthy review source, not screenshotted."},
    {"number": 10, "name": "Stat Surround Callout Radial", "aspect": "1:1", "needs_product": True, "category": "proof", "enabled": True,
     "scaffold": "A radial stat-surround ad for [BRAND NAME]. Product centered on a [BRAND BACKGROUND COLOR] backdrop. Four bold stat callouts radiate outward at 45-degree angles, each with a big number and short label: \"[STAT 1]\", \"[STAT 2]\", \"[STAT 3]\", \"[STAT 4]\". Thin connecting lines in [ACCENT COLOR]. Editorial, infographic feel."},
    {"number": 11, "name": "Manifesto Ad", "aspect": "4:5", "needs_product": False, "category": "brand_voice", "enabled": True,
     "scaffold": "A typographic manifesto ad for [BRAND NAME]. No imagery. The entire frame is filled with a manifesto in [BRAND HEADLINE FONT] set large and justified: \"[MANIFESTO COPY, 4-6 LINES]\". [BRAND BACKGROUND COLOR] background, [BRAND PRIMARY COLOR] text. Small brand wordmark bottom-right. Stark, confident, all attitude."},
    {"number": 12, "name": "Faux iPhone Screenshot", "aspect": "9:16", "needs_product": True, "category": "native_ugc", "enabled": True,
     "scaffold": (
         "Ultra-realistic faux-iOS 17 iMessage screenshot. Pure white #FFFFFF background, portrait 9:16. "
         "STATUS BAR (top): left — cellular signal bars + '5G' label; center — time e.g. '2:47 PM' in black SF Pro Medium; right — battery percentage + icon e.g. '87% 🔋'. "
         "CONTACT HEADER ROW: '‹' back chevron far-left; center — two circular avatar portrait headshots with first names underneath (e.g. 'Sarah' on left, 'Alex' on right) and a '↔' icon between them; blue FaceTime camera icon far-right. Thin #E5E5EA separator below. "
         "CHAT THREAD (top to bottom, generous white space between bubbles): "
         "(1) LEFT bubble #E9E9EB rounded-rect tail-left: Person A mentions [BRAND NAME] by name with genuine enthusiasm and a specific benefit, ends with emoji. 2–3 casual sentences. "
         "(2) RIGHT bubble #147EFB rounded-rect tail-right: Person B short enthusiastic reply endorsing [BRAND NAME]. 1–2 sentences. "
         "Directly below the blue bubble, still in the right column: large PRODUCT PHOTO displayed as a rounded-corner image card (~65% screen width) — the product shown clearly in a clean bright shot. "
         "(3) LEFT bubble #E9E9EB: Person A short reaction to seeing the photo, hype emoji. 1 sentence. "
         "BOTTOM: standard rounded-rect gray input field — circle '+' icon left, light-gray 'iMessage' placeholder text, microphone icon right. "
         "FOOTER: tiny #8E8E93 SF Pro text centered below input field — 'Paid partnership / [BRAND NAME]'. "
         "Every element must be indistinguishable from a real iPhone screenshot: exact SF Pro font weights, #147EFB iOS blue, #E9E9EB bubble gray, correct iOS 17 bubble corner radii and tail geometry, correct avatar circle crop style."
     )},
    {"number": 13, "name": "Post-it Note Style", "aspect": "1:1", "needs_product": False, "category": "handwritten", "enabled": True,
     "scaffold": "A hand-written post-it note ad for [BRAND NAME]. A single yellow post-it in the center of a plain desk surface, softly lit. Scrawled in casual black marker: \"[HANDWRITTEN INSIGHT]\". A small doodle of [DOODLE ELEMENT] in the corner. Tiny printed brand URL at the bottom of the frame: \"[BRAND URL]\"."},
    {"number": 14, "name": "Lifestyle UGC Selfie", "aspect": "9:16", "needs_product": True, "category": "ugc", "enabled": True,
     "scaffold": "A vertical phone-shot selfie of a [CUSTOMER PERSONA] holding the [BRAND NAME] product in natural light, in [LOCATION]. Authentic iPhone look, slight grain, candid expression. Short caption overlay at the bottom: \"[CAPTION]\". No text on product (keep packaging real). Small brand sticker bottom-right corner."},
    {"number": 15, "name": "Ingredient Hero / What's Inside", "aspect": "4:5", "needs_product": True, "category": "ingredient", "enabled": True,
     "scaffold": "An overhead flat-lay ingredient hero ad for [BRAND NAME]. The [BRAND NAME] product is centered on a [BRAND BACKGROUND COLOR] surface. Surrounding it in a neat radial pattern are the raw ingredients: [INGREDIENT 1], [INGREDIENT 2], [INGREDIENT 3], [INGREDIENT 4]. Each ingredient is labeled with a thin line and a small, elegant caption. Studio lighting, editorial flat-lay photography."},
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
    """
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }

    try:
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True, headers=headers) as hc:
            resp = await hc.get(url)
            resp.raise_for_status()
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

            # ── 3. External stylesheets (first 3, ~20KB each) ──
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
                if len(css_links) >= 3:
                    break

            external_css = ""
            for href in css_links:
                try:
                    r = await hc.get(href)
                    if r.status_code == 200 and "css" in r.headers.get("content-type", "").lower():
                        external_css += "\n/* " + href + " */\n" + r.text[:20000]
                except Exception:
                    continue
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

            # ── 6. Crawl a secondary brand page if obvious ──
            secondary_text = ""
            candidate_paths = ["/about", "/about-us", "/our-story", "/story", "/press"]
            for path in candidate_paths:
                try:
                    r2 = await hc.get(urljoin(base_url, path))
                    if r2.status_code == 200 and "text/html" in r2.headers.get("content-type", ""):
                        s2 = BeautifulSoup(r2.text, "html.parser")
                        for tag in s2(["script", "style", "noscript"]):
                            tag.decompose()
                        secondary_text = re.sub(r"\s+", " ", s2.get_text(" ", strip=True))[:3000]
                        secondary_text = f"\n{path} EXCERPT: {secondary_text}"
                        break
                except Exception:
                    continue

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
    text = text.strip()
    # Strip code fences if present
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1)
    else:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            text = m.group(0)
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


async def _openai_edit(openai_key: str, product_image_data_url: str, prompt: str, size: str = "1024x1024", quality: str = "medium") -> dict:
    """Call OpenAI gpt-image-2 /images/edits — composites the real uploaded product image into the scene.

    Falls back to _openai_generate if the image data URL is invalid or the edit call fails.
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
    files = [("image", (f"product.{ext}", image_bytes, media_type))]
    # GLOBAL GUARDRAILS — applied to every /images/edits call regardless of template.
    # The uploaded product image is the SOURCE OF TRUTH. We force the model to
    # preserve it exactly and only generate the surrounding scene described by Claude.
    preservation_prefix = (
        "STRICT PRODUCT PRESERVATION (highest priority, overrides any conflicting instruction below): "
        "The input reference image IS the product. Reproduce the product PIXEL-FAITHFUL — keep its "
        "exact shape, silhouette, proportions, colors, materials, label, typography, packaging, "
        "logos, text, finish, and orientation completely unchanged. Do NOT redraw, restyle, "
        "redesign, recolor, relabel, replace, regenerate, or reinterpret the product. Do NOT add "
        "or remove product features, ingredients, accessories, or variants. Treat the product as "
        "a fixed photographic element to be composited as-is into the new scene. "
        "SCOPE LOCK: Generate ONLY what the scene description below explicitly asks for — "
        "background, surface, props, lighting, composition. No extra people, animals, text, "
        "logos, badges, watermarks, UI chrome, browser/website elements, or decorative additions "
        "beyond the prompt. "
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
        "Always reply with a single valid JSON object — no prose, no markdown."
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
\"\"\""""
    raw = await _claude_call(api_key, system, user, max_tokens=3500)
    try:
        identity = BrandIdentity(**_extract_json(raw))
    except Exception as e:
        logger.error("Identity parse failed: %s | raw=%s", e, raw[:300])
        raise HTTPException(status_code=502, detail="Failed to parse brand identity from Claude")

    await db.brands.update_one(
        {"id": brand_id},
        {"$set": {"identity": identity.model_dump(), "cover_color": identity.palette.accent}},
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
        await _generate_images_background(
            run_id, creatives, o_key, quality, brand.product_images or None
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
    modifier_line = (
        f"\n\nIMPORTANT: prepend this exact paragraph to every prompt as the first sentences "
        f"(verbatim, then your scene):\n\"\"\"{modifier}\"\"\"\n"
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
                "  • Single paragraph, 40-80 words. "
                "  • Describe ONLY scene + staging + lighting + composition + mood around 'the product'. "
                "  • NEVER describe the product's appearance (shape, colors, label, packaging, materials, "
                "    ingredients, typography). Treat the product as an opaque fixed object. "
                "  • NEVER use words that imply altering the product: 'redesign', 'restyle', 'recolor', "
                "    'rebrand', 'redrawn', 'new packaging', 'variant', 'reimagined', 'stylised version'. "
                "  • NEVER request rendered text, headlines, copy, badges, logos, or watermarks unless the "
                "    template scaffold explicitly demands it — and even then, keep wording minimal. "
                "  • STAY IN SCOPE of the template scaffold. Do not invent extra subjects, characters, "
                "    or narrative elements that the scaffold does not call for. "
                "Adapt each scaffold to the brand palette, photography style, and tone. "
                "Reply with ONLY a JSON object: {\"prompts\": [\"...\", \"...\", ...]} preserving template order."
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
                "Reply with ONLY a JSON object: {\"prompts\": [\"...\", \"...\", ...]} preserving template order."
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
            "Reply with ONLY a JSON object: {\"prompts\": [\"...\", \"...\", ...]}."
        )
        user = f"""Brand: {brand.name}
Product: {brand.product_name or "(brand-level campaign)"}
{angle_line}
{photos_line}

Brand identity:
{identity_json}

Return 15 prompts."""
        target_count = 15

    raw = await _claude_call(a_key, system, user, max_tokens=4000)
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

    Updates each creative in MongoDB as it completes.
    """
    # Use the first uploaded product image as the primary reference
    primary_product_image = (product_images[0] if product_images else None)
    mode = "edit" if primary_product_image else "generate"
    logger.info("Run %s: image mode=%s, %d creatives", run_id, mode, len(creatives))

    sem = asyncio.Semaphore(4)

    async def worker(creative: AdCreative):
        size = _aspect_to_openai_size(creative.aspect)
        async with sem:
            if primary_product_image:
                res = await _openai_edit(o_key, primary_product_image, creative.prompt, size=size, quality=quality)
            else:
                res = await _openai_generate(o_key, creative.prompt, size=size, quality=quality)
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
