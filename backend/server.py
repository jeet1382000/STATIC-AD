"""Ads Studio backend.

BYOK: API keys for Anthropic + fal.ai are sent per-request in headers
(X-Anthropic-Key, X-FAL-Key). Never persisted on the server.
"""

import asyncio
import json
import logging
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

import anthropic
import httpx
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from fastapi import APIRouter, FastAPI, Header, HTTPException
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, ConfigDict, Field
from starlette.middleware.cors import CORSMiddleware

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

mongo_url = os.environ["MONGO_URL"]
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ["DB_NAME"]]

app = FastAPI(title="Ads Studio API")
api_router = APIRouter(prefix="/api")

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("ads-studio")

CLAUDE_MODEL = "claude-sonnet-4-5-20250929"
FAL_MODEL = "fal-ai/flux/schnell"  # fast 4-step model, ~2s per image


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
    status: str = "running"  # running | done | failed


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
    {"number": 12, "name": "Faux iPhone Screenshot", "aspect": "9:16", "needs_product": False, "category": "native_ugc", "enabled": True,
     "scaffold": "A vertical faux-iOS text-thread screenshot for [BRAND NAME]. Three message bubbles between two contacts titled \"[CONTACT A] ↔ [CONTACT B]\". The conversation organically mentions [BRAND NAME] and the benefit: \"[BENEFIT LINE]\". Native iOS status bar, time, and battery up top. Realistic, not obviously branded. Tiny footer disclaimer: \"Paid partnership / [BRAND NAME]\"."},
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


def _require_fal_key(x_fal_key: Optional[str]) -> str:
    if not x_fal_key or not x_fal_key.strip():
        raise HTTPException(status_code=401, detail="Missing FAL API key")
    return x_fal_key.strip()


async def _scrape_url(url: str) -> str:
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as hc:
            resp = await hc.get(url, headers={"User-Agent": "Mozilla/5.0 AdsStudio/1.0"})
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
            for tag in soup(["script", "style", "noscript"]):
                tag.decompose()

            title = (soup.title.string if soup.title and soup.title.string else "").strip()
            meta_desc = ""
            md = soup.find("meta", attrs={"name": "description"})
            if md and md.get("content"):
                meta_desc = md["content"]
            og_desc = soup.find("meta", attrs={"property": "og:description"})
            if og_desc and og_desc.get("content") and not meta_desc:
                meta_desc = og_desc["content"]

            text = soup.get_text(separator=" ", strip=True)
            text = re.sub(r"\s+", " ", text)[:5000]
            return f"TITLE: {title}\nDESCRIPTION: {meta_desc}\nCONTENT: {text}"
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


async def _fal_generate(fal_key: str, prompt: str, image_size=None, num_inference_steps: int = 4) -> dict:
    """Call fal.ai sync endpoint to generate one image. Returns dict {url} or {error}.

    image_size: either a string enum (e.g. "square_hd") or a dict {"width": int, "height": int}.
    """
    headers = {
        "Authorization": f"Key {fal_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "prompt": prompt,
        "image_size": image_size or "square_hd",
        "num_inference_steps": max(1, min(int(num_inference_steps), 12)),
        "num_images": 1,
        "enable_safety_checker": True,
    }
    try:
        async with httpx.AsyncClient(timeout=90.0) as hc:
            resp = await hc.post(f"https://fal.run/{FAL_MODEL}", headers=headers, json=payload)
            if resp.status_code != 200:
                return {"error": f"fal {resp.status_code}: {resp.text[:160]}"}
            data = resp.json()
            images = data.get("images") or []
            if not images:
                return {"error": "no image returned"}
            return {"url": images[0]["url"]}
    except Exception as e:
        return {"error": f"fal request failed: {str(e)[:160]}"}


def _aspect_to_image_size(aspect: str):
    """Map a human aspect string to fal flux/schnell image_size."""
    a = (aspect or "1:1").strip()
    if a == "1:1":
        return "square_hd"
    if a == "9:16":
        return "portrait_16_9"
    if a == "16:9":
        return "landscape_16_9"
    if a == "4:3":
        return "landscape_4_3"
    if a == "4:5":
        # custom — flux requires width/height divisible by 16 (832/1040 ≈ 4:5)
        return {"width": 832, "height": 1040}
    return "square_hd"


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


@api_router.post("/keys/test-fal")
async def test_fal(x_fal_key: Optional[str] = Header(None)):
    key = _require_fal_key(x_fal_key)
    # Submit an empty body to the queue endpoint. fal validates auth before body schema,
    # so an invalid key returns 401 while a valid key returns 422 (validation error).
    headers = {"Authorization": f"Key {key}", "Content-Type": "application/json"}
    try:
        async with httpx.AsyncClient(timeout=15.0) as hc:
            resp = await hc.post(f"https://queue.fal.run/{FAL_MODEL}", headers=headers, json={})
        if resp.status_code in (401, 403):
            raise HTTPException(status_code=401, detail="Invalid FAL key")
        # Anything else (200, 422, 400) means auth was accepted.
        return {"ok": True, "model": FAL_MODEL}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"FAL test failed: {str(e)[:160]}")


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
    return [Brand(**d) for d in docs]


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
        "You are a senior brand strategist and visual designer. "
        "Reverse-engineer a brand's full DNA — visual & verbal identity — from a website excerpt. "
        "Always reply with a single valid JSON object — no prose, no markdown."
    )
    user = f"""Analyze this website and extract the full brand DNA. Brand name: "{brand.name}".

Output ONLY this JSON shape (use empty strings or arrays if a field is unknown — never null):
{{
  "palette": {{ "primary": "#hex", "secondary": "#hex", "accent": "#hex", "neutral": "#hex" }},
  "fonts": ["Display font", "Body font"],
  "tone": "1-2 sentence description of the verbal tone",
  "photography_style": "1-2 sentence description of the visual / photography direction",
  "brand_voice": "1 sentence on how the brand sounds",
  "keywords": ["five", "to", "eight", "evocative", "keywords"],
  "brand_overview": {{
    "tagline": "their tagline or a representative one-liner",
    "design_agency": "agency name or 'Unknown'",
    "voice_adjectives": ["five", "voice", "adjectives"],
    "positioning": "1-2 sentence positioning statement",
    "competitive_differentiation": "1-2 sentence on what sets them apart"
  }},
  "visual_system": {{
    "primary_font": "primary font name + weight notes",
    "secondary_font": "secondary font name + weight notes",
    "primary_color": "#hex (description)",
    "secondary_color": "#hex (description)",
    "accent_color": "#hex (description)",
    "background_colors": "description of background usage",
    "cta_color_and_style": "color + button style notes"
  }},
  "photography_direction": {{
    "lighting": "lighting description",
    "color_grading": "grading description",
    "composition": "composition rules",
    "subject_matter": "what is photographed",
    "props_and_surfaces": "common props and surfaces",
    "mood": "overall mood"
  }},
  "product_details": {{
    "physical_description": "what the product looks like",
    "label_logo_placement": "label and logo placement",
    "distinctive_features": "distinctive product features",
    "packaging_system": "packaging system description"
  }},
  "ad_creative_style": {{
    "typical_formats": "typical ad formats",
    "text_overlay_style": "text overlay treatment",
    "photo_vs_illustration": "balance of photo vs illustration",
    "ugc_usage": "how UGC is used",
    "offer_presentation": "how offers are presented"
  }},
  "image_generation_modifier": "A single paragraph (~80 words) prompt-modifier to PREPEND to every ad-image prompt. Capture lighting, color grading, palette, type style, mood, and any signature props. Concrete, sensory, image-gen ready."
}}

Website excerpt:
\"\"\"
{site}
\"\"\""""
    raw = await _claude_call(api_key, system, user, max_tokens=2400)
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
    x_fal_key: Optional[str] = Header(None),
):
    a_key = _require_anthropic_key(x_anthropic_key)
    f_key = _require_fal_key(x_fal_key)

    doc = await db.brands.find_one({"id": brand_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Brand not found")
    brand = Brand(**doc)
    if not brand.identity:
        raise HTTPException(status_code=400, detail="Run brand research first")

    identity_json = json.dumps(brand.identity.model_dump(), indent=2)
    angle_line = f"Creative angle: {payload.angle}" if payload.angle else "Creative angle: open / surprise the user"
    photos_line = (
        f"Reference photos: {len(brand.product_images)} product photo(s) provided by the user. "
        "Generate prompts that describe the same product type and feel as those photos."
        if brand.product_images else "Reference photos: none."
    )
    modifier = (brand.identity.image_generation_modifier or "").strip()
    modifier_line = (
        f"\n\nIMPORTANT: prepend this exact paragraph to every prompt as the first sentences (verbatim, then your scene):\n\"\"\"{modifier}\"\"\"\n"
        if modifier else ""
    )

    # Enabled templates drive prompt generation. Fallback: free-form 15.
    await _seed_templates_if_empty()
    tpl_docs = await db.templates.find({"enabled": True}, {"_id": 0}).sort("number", 1).to_list(20)
    enabled = [Template(**d) for d in tpl_docs][:15]

    if enabled:
        templates_block = "\n".join(
            f"  №{t.number:02d} [{t.aspect} · {t.category}{' · needs product' if t.needs_product else ''}] "
            f"{t.name}: {t.scaffold}"
            for t in enabled
        )
        system = (
            "You are a world-class art director. For each provided template scaffold, write ONE vivid, "
            "production-ready image-generation prompt (40-80 words, single paragraph) that adapts the scaffold "
            "to the brand's palette, photography style, and tone. Describe a concrete scene: subject, composition, "
            "lighting, mood. Avoid any rendered text in the image. "
            "Reply with ONLY a JSON object: {\"prompts\": [\"...\", \"...\", ...]} preserving the order of templates."
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
            "You are a world-class art director. Write 15 distinct, vivid, production-ready "
            "image-generation prompts for static social ad creatives. Every prompt must be a "
            "single paragraph (40-80 words), reference the brand's palette, photography style, "
            "and tone, and describe a concrete scene with subject, composition, lighting, and mood. "
            "Avoid text overlays in the image. Vary scenes drastically across the 15. "
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
        logger.error("Prompts parse failed: %s | raw=%s", e, raw[:300])
        raise HTTPException(status_code=502, detail="Failed to parse prompts from Claude")
    if not prompts:
        raise HTTPException(status_code=502, detail="Claude returned no prompts")

    # Pair each prompt with the originating template (or default 1:1)
    creatives: List[AdCreative] = []
    for i, p in enumerate(prompts):
        if enabled and i < len(enabled):
            t = enabled[i]
            creatives.append(AdCreative(prompt=p, aspect=t.aspect, template_name=t.name, template_number=t.number, needs_product=t.needs_product))
        else:
            creatives.append(AdCreative(prompt=p, aspect="1:1"))

    run = AdRun(brand_id=brand_id, creatives=creatives)
    await db.ad_runs.insert_one(run.model_dump())

    # Read default quality from settings
    settings_doc = await db.settings.find_one({"id": "defaults"}, {"_id": 0})
    settings = Settings(**settings_doc) if settings_doc else Settings()
    steps = QUALITY_TO_STEPS.get(settings.quality, 4)

    # Generate images concurrently with cap
    sem = asyncio.Semaphore(6)

    async def worker(creative: AdCreative):
        size = _aspect_to_image_size(creative.aspect)
        async with sem:
            res = await _fal_generate(f_key, creative.prompt, image_size=size, num_inference_steps=steps)
        if "url" in res:
            creative.image_url = res["url"]
        else:
            creative.error = res.get("error", "unknown")
        return creative

    run.creatives = await asyncio.gather(*(worker(c) for c in run.creatives))
    run.status = "done" if any(c.image_url for c in run.creatives) else "failed"

    await db.ad_runs.update_one(
        {"id": run.id},
        {"$set": {"creatives": [c.model_dump() for c in run.creatives], "status": run.status}},
    )
    return run


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
                    r = await hc.get(c["image_url"])
                    if r.status_code != 200:
                        continue
                    name = (c.get("template_name") or f"creative_{i}").replace("/", "-").replace(" ", "_")
                    fn = f"{i:02d}_{name}.png"
                    zf.writestr(fn, r.content)
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


QUALITY_TO_STEPS = {"low": 2, "medium": 4, "high": 8}


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
    if "quality" in upd and upd["quality"] not in QUALITY_TO_STEPS:
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


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
