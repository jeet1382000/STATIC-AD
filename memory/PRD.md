# Static Ad Studio — PRD

## Original Problem Statement
> https://ad-gen-workspace.preview.emergentagent.com/ — can you build an app similar to above

## Architecture
- **Backend**: FastAPI + MongoDB (motor). All routes prefixed `/api`. Per-request BYOK headers `X-Anthropic-Key`, `X-FAL-Key` (never persisted).
- **Frontend**: React + Tailwind + Shadcn (rounded-none overrides). Sidebar layout, cream background, coral/red accents, Khand display + IBM Plex Sans + JetBrains Mono.
- **Integrations**: Anthropic Claude Sonnet 4.5 (`claude-sonnet-4-5-20250929`) for brand research + prompt generation; fal.ai (`fal-ai/flux/schnell`) for image generation. BYOK pattern (localStorage `sas.fal_key` / `sas.llm_key`).
- **Persistence**: `brands` and `ad_runs` collections in MongoDB.

## User Personas
- Performance marketers / growth teams who need to ship 15+ ad variations/day per brand.
- Indie founders evaluating brand identity quickly from competitor URLs.

## Core Requirements (static)
1. Bring-Your-Own-Keys flow with Test + Save (FAL + Anthropic).
2. Workspace dashboard with brand cards, status pills, color palette previews.
3. Drop-URL pipeline that creates brand → research → generate 15 ads automatically.
4. 3-step wizard for full brand+product+angle creation.
5. Brand detail page: identity card (palette, fonts, tone, photography style, keywords) + 15-image grid with downloads.

## Implemented (2026-04-29)
- Backend endpoints: `/api/keys/test-anthropic`, `/api/keys/test-fal`, `/api/brands` CRUD, `/api/brands/{id}/research`, `/api/brands/{id}/generate`, `/api/brands/{id}/runs`.
- BYOK pipeline using direct httpx → fal.run (sync) with concurrency=6.
- Sidebar layout, cream theme, big Khand headline, status pills (PENDING/DONE), coral CTA.
- Keys modal auto-opens on first visit; status reflected in sidebar.

## Backlog
- **P0**: Templates page (15 toggleable scaffolds shown in reference).
- **P1**: Global Gallery view across all brands with aspect-ratio filter.
- **P2**: Per-prompt regenerate; download-all ZIP; cost-cap & spend tracking; settings page for defaults.
- **P2**: Multiple ad runs history view in BrandDetail.
