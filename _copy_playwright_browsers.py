"""
_copy_playwright_browsers.py
Used by build.bat to copy Playwright's Chromium into the dist folder.
"""
import os
import sys
import shutil

DEST = os.path.join("dist", "OtterForge", "playwright_browsers")

def find_chromium_dir() -> str | None:
    """Find the Playwright-managed Chromium directory."""
    # Method 1: ask Playwright directly
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            exe = pw.chromium.executable_path
        # exe is e.g. C:\Users\...\ms-playwright\chromium-1134\chrome-win\chrome.exe
        # We want the ms-playwright\ root (two levels up from chrome-win)
        chromium_dir = os.path.dirname(os.path.dirname(exe))  # chromium-XXXX
        ms_playwright_dir = os.path.dirname(chromium_dir)       # ms-playwright
        return ms_playwright_dir
    except Exception as e:
        print(f"  Method 1 failed: {e}")

    # Method 2: check default location
    local_app = os.environ.get("LOCALAPPDATA", "")
    candidate = os.path.join(local_app, "ms-playwright")
    if os.path.isdir(candidate):
        return candidate

    return None


def main() -> int:
    print(f"  Looking for Playwright browsers...")
    src = find_chromium_dir()

    if not src or not os.path.isdir(src):
        print("  ERROR: Playwright browsers not found.")
        print("  Run: playwright install chromium")
        return 1

    print(f"  Found: {src}")

    if os.path.exists(DEST):
        print(f"  Removing old: {DEST}")
        shutil.rmtree(DEST)

    print(f"  Copying to: {DEST}")
    print("  (this may take 30-60 seconds...)")

    shutil.copytree(src, DEST)

    size_mb = sum(
        os.path.getsize(os.path.join(r, f))
        for r, _, files in os.walk(DEST)
        for f in files
    ) / 1_048_576

    print(f"  Copied {size_mb:.0f} MB of browser files.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
