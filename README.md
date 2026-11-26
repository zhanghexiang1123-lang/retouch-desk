# Retouch Desk 0.5.0

Retouch Desk edits one line of text in a raster image. Select the text with a rectangle or freehand outline, check the locally recognized source text, enter a replacement, and inspect the preview before adopting or exporting it.

The Windows app runs OCR and image reconstruction locally on the CPU. It does not require a graphics card, cloud account, API key, or network access while editing. Images and edit history remain in memory until the app closes, unless you export an image.

## Install

Download `RetouchDesk-0.5.0-Setup-x64.exe` from the project's GitHub Releases and run the installer. It installs for the current Windows user, lets you choose an install folder, and can create a desktop shortcut. The app is also available from the Start menu and Windows' installed apps list.

Windows 10 version 1809 or newer and Windows 11 are supported on x64. The native desktop window uses Microsoft Edge WebView2 Runtime. If it is unavailable, the app attempts to open its local interface in the default browser.

To use the portable build, run `release/RetouchDesk/RetouchDesk.exe`. Keep the full `RetouchDesk` folder together. The existing `一键启动.bat` also starts the portable app.

## Use

1. Open one or more PNG, JPEG, or WebP images. Switch between images with the tabs.
2. Choose rectangle selection or freehand selection and include the full line of text with a little surrounding background. Press Escape or select **取消框选** to clear a selection.
3. Review and correct the OCR result, then enter the replacement text. The two text fields preserve leading zeros and decimal points.
4. Generate a preview. Compare the original crop, reconstructed source text, and result, then adjust the font or fine controls when needed.
5. Adopt a result, undo or redo recent changes, and export the current image as PNG. The original file is not overwritten.

## Editing limits

The local engine supports a single line of printed text on light or dark backgrounds. It searches a finite set of fonts installed on the current Windows computer and estimates character width, height, position, shear, rotation, blur, and ink color. Unknown fonts and different computers can produce different matches.

Complex textures, gradients, perspective, curved text, outlines, colored lettering, handwriting, and transparency are not fully reconstructed. Background repair uses OpenCV Telea inpainting and local color fitting. Preview metrics help inspect the result but do not predict whether a change is visually undetectable. Inspect the result before adopting it.

The editor leaves decoded pixels outside its change area unchanged. PNG export does not preserve the input file's original compression bytes, EXIF, or other metadata.

## Develop

Use Python 3.12 and Node.js 24 on Windows.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
npm ci
npm run build
npm start
```

`npm run start:browser` opens the local interface in a browser. `npm run test:workspace` runs workspace-state tests. `npm run test:engine` runs the Python OCR and image-edit tests.

The browser-based UI checks in `scripts/ui-workspace-check.mjs`, `scripts/ui-async-check.mjs`, and `scripts/ui-appearance-check.mjs` use Playwright and Microsoft Edge. Install Playwright in the project's Node environment or set `PLAYWRIGHT_PACKAGE_JSON` to the package manifest that provides it. Set `PLAYWRIGHT_EXECUTABLE_PATH` when Edge is not available through Playwright's default `msedge` channel. Start the local server separately, then pass its URL to a check script. The browser tests use only the synthetic images in `tests/fixtures/`.

## Build Windows packages

`npm run package:windows` builds the portable folder and executable. `npm run package:installer` builds the portable app and then creates the per-user installer. `scripts/package-installer.ps1` expects Inno Setup 6 and can also compile an existing portable build with `-SkipAppBuild`.

The installer is written to `release/installer/RetouchDesk-0.5.0-Setup-x64.exe`. The build also writes a SHA-256 checksum beside the installer. The installer is not code-signed.

The Chinese Inno Setup translation is from the Inno Setup project's `is-6_7_4` source tag. Its contributor attribution is retained in `installer/ChineseSimplified.isl`; the translation is licensed under MIT. See `installer/THIRD-PARTY-NOTICES.md`.

## Project layout

- `src/` contains the React workspace and editor interface.
- `backend/` contains the local image editor, OCR pipeline, and loopback server.
- `tests/` contains engine, OCR, and workspace-state tests with small synthetic image fixtures.
- `scripts/` contains build, launch, and acceptance scripts.
- `assets/` and `public/` contain the application icon.
- `installer/` contains the Inno Setup definition and installer notices.
