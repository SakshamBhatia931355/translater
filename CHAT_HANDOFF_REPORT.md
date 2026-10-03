# Japanese Practice / Translating Project — Chat Handoff Report

**Report date:** 2026-10-03  
**Project folder:** `C:\Users\sam93\Downloads\translater`  
**GitHub:** https://github.com/SakshamBhatia931355/translater  
**Feature commit:** `0692da8` — `Add voice practice and secure remote phone access`

## 1. User’s overall goal

Build a Japanese handwriting and translation application from the initial `kanadetector` work and the supplied README reference. The user wants to read Japanese kana from webcam/photos/drawings, correct the recognized text, translate meaningful Japanese to English, speak translations, and use the application from Windows, Android, and iPhone. They also requested leveled vocabulary practice and access from a phone even when it is not on the PC’s Wi-Fi.

The user asked for a lightweight white interface inspired by the practice flows of Pingo AI and SakuraSpeak, without keeping the Sakura Kana flower/logo. The request was for interface inspiration, not copied branding or assets.

## 2. Conversation history and decisions

- Started with the `kanadetector` project in Downloads and a supplied README for project structure and references. The work grew into the `translater` project.
- The user asked to keep the Python environment while removing project files, then requested the project be rebuilt with ETL8G under a datasets folder. ETL8G preparation/training scripts are present. The ETL8G archive and prepared images are excluded from GitHub because AIST restricts redistribution.
- The user repeatedly tested handwritten images and reported wrong readings (including O vs. PI and a photo that was interpreted as `たす`) and incorrect English translations. The UI supports alternatives and manual correction, but the underlying image model remains fallible.
- The user requested working image upload, webcam/Camo use, English translation and speech, Android support, drawing in both apps, phrase-building fixes, and Windows scrolling fixes.
- The user requested progressive vocabulary learning. The app has N5–N1 starter vocabulary decks.
- The user requested GitHub hosting and an APK for use on another computer/phone. The source and latest APK are committed and pushed. The Windows `dist` build is local and ignored by Git; clone the project and follow its setup instructions to use it elsewhere.
- Latest changes simplified the design to white, removed the Sakura Kana logo from the app UI, added voice input and improved drawing, and added protected internet access through a temporary Cloudflare Quick Tunnel.

## 3. Current project components

- `src/desktop_app.py` — Windows desktop app: image recognition, manual text correction, phrase/translation workflow, vocabulary cards, English speech, drawing, local phone server, and a **Start anywhere link** control.
- `src/mobile_server.py` — Flask web/API server for recognition and Japanese-to-English translation; includes access-code login for public-tunnel use.
- `src/templates/mobile.html`, `src/static/mobile.css`, `src/static/mobile.js` — responsive white web app with Speak / Write / Learn sections, image upload, drawing canvas with ink trimming, browser speech recognition and speech synthesis, translation, and vocabulary practice.
- `src/start_public_server.py` — Windows launcher that starts the protected local server and a Cloudflare temporary HTTPS tunnel; downloads the official `cloudflared` Windows binary if needed.
- `src/templates/login.html` — access-code sign-in page used for the public web link.
- `android-app/` — native Android Studio client. It accepts a server URL and PIN, remembers connection values, uploads photos/drawings to the PC, translates text, offers Japanese voice input through Android’s speech recognizer, and speaks English using Android TTS.
- `artifacts/SakuraKana-debug.apk` — latest Android debug APK (the app display name is now Japanese Practice; the artifact filename is retained for continuity).
- `src/prepare_etl8g.py`, `src/train.py` — ETL8G data conversion/training support.

## 4. Recognition and translation behavior / known limits

- The image classifier recognizes handwritten **hiragana** classes. It is not full Japanese OCR and does not read kanji or katakana from images. For kanji, katakana, and mixed Japanese, edit or type the recognized text before translating.
- Recognition displays alternatives/confidence and supports correction. Low-confidence predictions should be checked. The earlier incorrect `たす` result illustrates this limitation; the new UI does not make the image model infallible.
- A single kana usually has a pronunciation, not an English word. Translation quality improves when the phrase contains a meaningful Japanese word or sentence.
- English translation runs on the PC with the local Japanese-to-English model. The Android and browser clients depend on the PC for model inference.
- Japanese speech input is implemented in the browser and Android client. Browser speech recognition requires a supported browser and typically HTTPS; iOS/Safari behavior depends on the installed OS/browser speech support. Android uses a phone-installed Japanese speech-recognition service. English speech output uses browser or Android TTS; desktop has its existing English speech feature.
- The user previously reported Windows scrolling problems. The desktop has mouse-wheel/scrollbar bindings, but this handoff’s final build did not include a dedicated physical-device retest of that earlier report.
- No live physical Android/iPhone installation test is recorded here. The APK compiled, and the public web page/API were checked remotely.

## 5. Cross-network phone access

- In the Windows app, **Start anywhere link** starts the remote HTTPS tunnel. The Android client can use the shown URL and PIN; the browser asks for the PIN at sign-in. A phone browser can open the same URL.
- The phone and PC do not need the same Wi-Fi. Both need internet access, and the PC must stay powered on with the local app/server running.
- It uses Cloudflare Quick Tunnels. The link and PIN are temporary; restarting the tunnel can generate new values. It is suitable for testing, not a permanent hosted service. The previously issued PIN is intentionally omitted from this report/repository; obtain it from the live desktop dialog or restart the tunnel to issue a new one.
- At report time, the most recently issued link responded to `/health` with HTTP 200 and reported that access-code protection was enabled. The tunnel URL may expire, so prefer the desktop app’s **Start anywhere link** button for a fresh link.
- Local same-Wi-Fi use remains available through **Start phone server** and the PC’s LAN URL.

## 6. Verification recorded for the latest feature commit

- Python syntax compilation passed for `src/desktop_app.py`, `src/mobile_server.py`, and `src/start_public_server.py`.
- `node --check src/static/mobile.js` passed.
- Android `assembleDebug` completed successfully. Only Android system-bar API deprecation warnings were reported.
- PyInstaller completed successfully. The resulting local executable is `dist/KanaReader/KanaReader.exe` (about 78.8 MB); the full `dist` package is ignored by Git.
- Flask smoke checks passed for health, PIN login, denied unauthenticated API access, and allowed authenticated API access.
- Public-tunnel checks confirmed the web login page loaded, unauthenticated API requests returned 401, and PIN-authenticated requests passed the gate.
- A real remote translation request for `こんにちは` returned `Hello.`.
- Git reported a clean `main` branch synchronized with `origin/main` at feature commit `0692da8` before this report was created.

## 7. Useful paths and commands

From PowerShell:

```powershell
Set-Location C:\Users\sam93\Downloads\translater
.\.venv\Scripts\python.exe src\desktop_app.py
```

Build Android APK:

```powershell
Set-Location C:\Users\sam93\Downloads\translater\android-app
.\gradlew.bat assembleDebug
```

APK output:

```text
C:\Users\sam93\Downloads\translater\artifacts\SakuraKana-debug.apk
```

Android Studio project:

```text
C:\Users\sam93\Downloads\translater\android-app
```

Windows built executable (local build; use with the project/runtime files as configured):

```text
C:\Users\sam93\Downloads\translater\dist\KanaReader\KanaReader.exe
```

## 8. Repository and distribution

- Repository: https://github.com/SakshamBhatia931355/translater
- Feature commit pushed to `main`: `0692da8`.
- The source and Android APK are committed. The `.venv`, ETL8G archive/prepared images, and PyInstaller `dist` output are excluded. On another Windows PC, clone the repository, install Git LFS/Python dependencies as described in `README.md`, and build/run locally.
