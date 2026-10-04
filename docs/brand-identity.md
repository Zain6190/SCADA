# IBCP-SCADA brand identity

The river-confluence mark connects the Indus Basin river network with its operational telemetry. Three station nodes feed one downstream channel, representing a shared view across water, flood, agriculture, and geography. This is a symbolic river network, not a geographic map.

The design uses the existing Indus Slate tokens: river green #24675C, navigation green #183E38, paper #F1F4F3, and inverse mint #C3E1D1. No new theme colors or fonts are required.

## Assets

- `packages/dashboard/public/brand/logo.svg`: transparent primary wordmark for light surfaces.
- `packages/dashboard/public/brand/logo-dark.svg`: transparent inverse wordmark for dark surfaces.
- `packages/dashboard/public/brand/logo.png` and `logo-dark.png`: transparent high-resolution exports. SVG wordmarks use IBM Plex Sans with Segoe UI/sans-serif fallbacks; exported PNGs freeze the renderer's available font.
- `packages/dashboard/public/brand/mark.svg`: standalone square mark.
- `packages/dashboard/public/brand/preview.png`: light/dark logo and small-size overview.
- `packages/dashboard/public/favicon.svg` and `favicon.ico`: scalable favicon and 16/32/48-pixel fallback.
- `packages/dashboard/public/favicon-16.png` and `favicon-32.png`: small PNG exports.
- `packages/dashboard/public/apple-touch-icon.png`: 180-pixel Apple icon.
- `packages/dashboard/public/icon-192.png` and `icon-512.png`: application icon exports.

## Integration

`BrandMark` is a decorative inline SVG that inherits currentColor and shares the asset geometry. Landing, login, console preview, sidebar (including the mobile drawer), and shared navigation use it. Keep the visible product name beside the mark. The root Next.js metadata declares browser and Apple icons.

Keep at least one station-node diameter of clear space around the mark. Use the symbol alone for favicons; keep the full wordmark at least 220 pixels wide.

Authored directly as SVG to match the repository's existing vector graphics; PNG exports use Sharp. No image-generation tool or external service was used.
