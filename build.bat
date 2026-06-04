@echo off
setlocal EnableDelayedExpansion
:: ============================================================
:: OtterForge — Build script
:: Generates a standalone distributable in dist\OtterForge\
:: Includes Playwright/Chromium — no user setup required.
::
:: Prerequisites (one-time):
::   pip install pyinstaller playwright
::   playwright install chromium
::   pip install svglib reportlab   (optional — official mana symbols in +Forge)
::   pip install cairosvg            (alternative, better quality but needs cairo DLL)
:: ============================================================

echo.
echo  OtterForge Build Script
echo  ============================================================

:: ── Step 1: Build the exe with PyInstaller ───────────────────
echo.
echo  [1/4] Building exe with PyInstaller...
echo.

pyinstaller --noconfirm OtterForge.spec

if not exist "dist\OtterForge\OtterForge.exe" (
  echo.
  echo  ERROR: PyInstaller build failed. See output above.
  pause
  exit /b 1
)

echo.
echo  [1/4] Exe built successfully.

:: ── Step 2: Copy Playwright's Chromium browsers ─────────────
echo.
echo  [2/4] Copying Playwright browsers (Chromium)...
echo         This may take a moment — Chromium is ~150 MB.
echo.

python _copy_playwright_browsers.py

if errorlevel 1 (
  echo.
  echo  WARNING: Could not copy Playwright browsers automatically.
  echo  MPC upload will require Playwright installed on the target machine.
  echo  To fix: run  playwright install chromium  then rebuild.
) else (
  echo.
  echo  [2/4] Browsers copied successfully.
)

:: ── Step 3: Copy card_backs ──────────────────────────────────
echo.
echo  [3/5] Copying card_backs (MPCFILL + user backs)...
if not exist "dist\OtterForge\card_backs" mkdir "dist\OtterForge\card_backs"
xcopy /E /I /Y "card_backs" "dist\OtterForge\card_backs\" >nul
echo  [3/5] Done.

:: ── Step 4: Copy README ──────────────────────────────────────
echo.
echo  [4/5] Copying README...
copy /Y "README.md" "dist\OtterForge\README.md" >nul
echo  [4/5] Done.

:: ── Step 5: Summary ─────────────────────────────────────────
echo.
echo  [5/5] Done.
echo.
echo  ============================================================
echo   Output folder : dist\OtterForge\
echo   To distribute : zip the entire dist\OtterForge\ folder
echo                   (~200-300 MB with Chromium included)
echo   Includes      : card_backs\ (MPCFILL.png, MPCFILL PG.png + all)
echo  ============================================================
echo.
pause
