# Approved HERO-CAD launcher artwork

The approved direction is the bronze armillary sphere surrounding a gear with
HERO-CAD branding. **There is no final approved image file in this checkout.**
No generated replacement, test image or placeholder is bundled.

Use the owner's final approved artwork for launcher setup:

```bash
.venv/bin/hero-cad-install-launcher --icon "/absolute/path/to/approved-hero-cad.png"
```

Export a square PNG (512×512 recommended; 32–4096 supported) or a self-contained
SVG with a square positive viewBox. PNG transparency is supported. You may keep
the approved file here as `hero-cad.png` or `hero-cad.svg` once available; setup
still requires its explicit `--icon` path. Do not substitute repository screenshots
or unrelated artwork. See [desktop integration](../../docs/DESKTOP_LAUNCHER.md).
