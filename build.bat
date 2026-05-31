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
:: ============================================================

echo.
echo  OtterForge Build Script
echo  ============================================================

:: ── Step 1: Build the exe with PyInstaller ───────────────────
echo.
echo  [1/4] Building exe with PyInstaller...
echo.

pyinstaller ^
  --name "OtterForge" ^
  --windowed ^
  --icon "assets\otterforge_icon.ico" ^
  --add-data "assets\OtterForge_Image.jpg;assets" ^
  --add-data "assets\otterforge_icon.ico;assets" ^
  --add-data "assets\otterforge_theme.json;assets" ^
  --add-data "ui\dialogs;ui\dialogs" ^
  --hidden-import customtkinter ^
  --hidden-import PIL ^
  --hidden-import PIL._imagingtk ^
  --hidden-import PIL._tkinter_finder ^
  --hidden-import requests ^
  --hidden-import tkinterdnd2 ^
  --collect-all customtkinter ^
  --collect-all playwright ^
  --noconfirm ^
  main.py

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

:: ── Step 3: Copy README ──────────────────────────────────────
echo.
echo  [3/4] Copying README...
copy /Y "README.md" "dist\OtterForge\README.md" >nul
echo  [3/4] Done.

:: ── Step 4: Summary ─────────────────────────────────────────
echo.
echo  [4/4] Done.
echo.
echo  ============================================================
echo   Output folder : dist\OtterForge\
echo   To distribute : zip the entire dist\OtterForge\ folder
echo                   (~200-300 MB with Chromium included)
echo  ============================================================
echo.
pause
