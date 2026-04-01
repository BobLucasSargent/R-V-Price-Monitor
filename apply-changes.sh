#!/bin/bash
# ═══════════════════════════════════════════════════════════════════
# R&V IPC — Apply collector rewrite changes
# Run this script from the root of your R-V-Price-Monitor repo
# ═══════════════════════════════════════════════════════════════════
set -e

echo "🔧 R&V IPC — Applying collector rewrite..."
echo ""

# Verify we're in the right directory
if [ ! -f "api/main.py" ] || [ ! -d "collectors" ]; then
    echo "❌ Error: Run this from the root of R-V-Price-Monitor repo"
    exit 1
fi

# ─── 1. Remove old broken collector files ────────────────────────
echo "1/6 Removing old collector files..."
rm -f collectors/supermercados/jumbo.py
rm -f collectors/supermercados/coto.py
rm -f collectors/medicamentos/farmacity.py
rm -f collectors/electronica/fravega.py
rm -f collectors/delivery/pedidosya.py
rm -f collectors/alquileres/zonaprop.py
rm -f collectors/comunicacion/planes.py
rm -f collectors/tarifas/servicios.py
rm -f collectors/financieros/dolar.py
rm -f collectors/combustibles/combustibles.py
rm -f collectors/base.py

# ─── 2. Copy new files from the update folder ───────────────────
echo "2/6 Copying new collector files..."
# This assumes the R-V-Price-Monitor-updated folder is in the same parent dir
# If you downloaded it elsewhere, adjust the path
UPDATE_DIR="$(dirname "$0")"
if [ "$UPDATE_DIR" = "." ]; then
    # Script is being run from within the update folder
    UPDATE_DIR=".."
fi

# Check if update files exist alongside this script
if [ -f "$(dirname "$0")/collectors/base.py" ]; then
    SRC="$(dirname "$0")"
else
    echo "   Looking for update files..."
    echo "   Please copy the R-V-Price-Monitor-updated folder contents into your repo manually"
    echo "   Or run: cp -r /path/to/R-V-Price-Monitor-updated/* ."
    exit 1
fi

cp -r "$SRC/collectors/" ./collectors/
cp -r "$SRC/config/" ./config/
cp -r "$SRC/engine/" ./engine/
cp "$SRC/Dockerfile" ./Dockerfile
cp "$SRC/requirements.txt" ./requirements.txt

echo "   ✅ Files copied"

# ─── 3. Verify imports ──────────────────────────────────────────
echo "3/6 Verifying Python imports..."
python3 -c "
from collectors.registry import list_collectors
collectors = list_collectors()
print(f'   ✅ {len(collectors)} collectors registered: {collectors}')
" 2>&1 || echo "   ⚠️  Import check failed (may need dependencies installed)"

# ─── 4. Run tests ───────────────────────────────────────────────
echo "4/6 Running tests..."
python3 -m pytest tests/ -q 2>&1 || echo "   ⚠️  Some tests failed"

# ─── 5. Install Playwright (for local testing) ──────────────────
echo "5/6 Installing Playwright..."
pip install playwright 2>/dev/null && playwright install chromium 2>/dev/null \
    || echo "   ⚠️  Playwright install skipped (will install in Docker)"

# ─── 6. Git status ──────────────────────────────────────────────
echo "6/6 Git status:"
echo ""
git status --short
echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "✅ Changes applied! Next steps:"
echo ""
echo "   git add -A"
echo "   git commit -m 'feat: rewrite collectors — Precios Claros API + Playwright'"
echo "   git push origin main"
echo ""
echo "After push, Railway will auto-deploy. Then test with:"
echo "   curl -X POST https://r-v-price-monitor-production.up.railway.app/api/v1/index/run"
echo "═══════════════════════════════════════════════════════════════"
