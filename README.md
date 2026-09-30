# Kana Reader and English Translator

This Windows desktop app recognizes handwritten hiragana from a webcam or an uploaded image. Uploads can contain a spaced line of kana; the app separates characters, shows alternatives and confidence, and lets you edit the Japanese line before adding it. It can speak the English translation, which runs locally with the offline Japanese-to-English model.

This is handwritten Japanese character recognition, not sign-language recognition. The camera classifier predicts one hiragana at a time. A single kana such as お has a sound (o) rather than a standalone English word; English translation needs a meaningful captured word or phrase.

## Setup

Open PowerShell:

    cd C:\Users\sam93\Downloads\translater
    .\.venv\Scripts\Activate.ps1
    python -m pip install -r requirements.txt
    python src\setup_translation.py

The first translation setup downloads the Helsinki-NLP OPUS-MT ja→en model once. Translation runs locally after installation, on the NVIDIA GPU when PyTorch can use CUDA.

## App with image upload and webcam

Start the desktop interface:

    python src\desktop_app.py

Choose image opens a file picker and tries to separate a spaced line of kana from the photo. It translates the detected line automatically; edit the Japanese text and select Translate this line to retry the translation. Use Add to phrase when you want to collect kana before translating a longer phrase. The webcam still reads one kana at a time; enter the Camo camera index if needed.

## Webcam

    python src\webcam_app.py

Place one handwritten kana inside the guide box, use dark ink on light paper, and keep it still. If Camo is not camera 0, choose its index:

    python src\webcam_app.py --camera 1

Controls:

- Space: add the best current reading to the phrase
- 1, 2, 3: choose one of the displayed alternatives and add it
- T: translate the captured kana line to English and speak the result
- Backspace: remove the last character
- C: clear the phrase
- R: freeze or resume the camera
- Q or Esc: quit

The result is temporally smoothed across camera frames. The ranked alternatives make ambiguous predictions such as O vs. PI correctable before translation.

## Test from an Android phone

The mobile page runs in Chrome on Android while this PC runs the recognition and translation models (including GPU inference when CUDA is available). Connect the phone and PC to the same Wi-Fi, then start the local server in PowerShell:

    cd C:\Users\sam93\Downloads\translater
    .\.venv\Scripts\Activate.ps1
    python src\mobile_server.py

Find the PC's Wi-Fi IPv4 address with `ipconfig`, then open `http://<PC-IPv4-address>:5055` on the phone, for example `http://192.168.1.24:5055`. Tap **Take photo / choose image** to use the Android camera or gallery. Keep the server window open while using the page. The page can recognize a line, lets you correct it, translates the line or built phrase, and uses Android browser speech for **Speak English**.

This is a phone-friendly browser app; the PyTorch model stays on the PC. If Windows asks, allow Python access on the private network so the phone can connect.

### Native Android app

The Android Studio project is `android-app`. Open that folder in Android Studio, or build the debug APK from PowerShell:

    cd C:\Users\sam93\Downloads\translater\android-app
    .\gradlew.bat assembleDebug

The APK is written to `android-app\app\build\outputs\apk\debug\app-debug.apk`. The app can take or choose a photo, draw one kana with blue or black ink, crop the drawing to its ink bounds, send it to the PC recognizer, let you correct the Japanese, add it to a phrase, translate it, and speak the English result. The model still runs on the PC. Start it from the desktop app's **Start phone server** button, then enter the shown PC URL in the Android app and tap **Connect**. Both devices must be on the same local network. This debug app allows HTTP because the local PC server does not use HTTPS; use it only with your own trusted LAN.

## Upload and single-image recognition

The CLI accepts a single-character image and returns the kana, pronunciation, confidence, and alternatives:

    python src\predict.py path\to\handwritten-kana.jpg

Images are read locally. For best results, use dark ink on light paper and keep kana separated. The handwriting classifier has 66 hiragana labels; it does not recognize kanji or katakana in photos and is not full-sentence OCR. The separate Japanese-to-English translator accepts typed text containing hiragana, katakana, kanji, and mixtures of those scripts. Check short or uncertain readings before translating because isolated fragments can produce misleading English.

## ETL8G handwriting dataset

The ETL Character Database ETL8G archive is stored at datasets\ETL8G\ETL8G.zip. The preparation script checks the published MD5 before converting its official binary records. ETL8G includes 956 classes (881 educational kanji and 75 hiragana), with 152,960 listed samples. This project keeps the hiragana records supported by its reading map; kanji records are not passed to the kana classifier.

After the verified archive is present, prepare the additional kana images and train:

    python src\prepare_etl8g.py
    python src\train.py

train.py combines the original image dataset (when present) with prepared ETL8G hiragana samples. ETL8G is a handwritten character dataset; it does not contain English translations or Japanese word-level labels.

The five-fold score is a random record-level estimate. Samples from the same ETL8G writers may appear in both training and validation, so the score does not guarantee accuracy on your handwriting. The live view shows alternatives so you can correct uncertain characters.

The database is copyrighted by AIST and may be used for free under its Terms of Use. Do not redistribute the dataset files. Cite: Electrotechnical Laboratory, Japanese Technical Committee for Optical Character Recognition, ETL Character Database, 1973-1984. See the official [ETL Character Database](https://etlcdb.db.aist.go.jp/?lang=en).

## Project files

    datasets/ETL8G/             local ETL8G archive and prepared kana samples
    data/raw/                   original 50-class hiragana image data, if installed
    checkpoints/                trained PyTorch models
    src/prepare_etl8g.py        convert ETL8G records to project kana images
    src/train.py                cross-validation and final-model training
    src/predict.py              file-based single-character inference
    src/desktop_app.py          image-picker and phrase translation desktop UI
    src/webcam_app.py           live camera, pronunciation, and phrase translation
    src/translation.py          GPU-capable local Japanese-to-English model
    src/setup_translation.py    download offline Japanese-to-English weights

## Windows executable

The desktop application executable is at dist\KanaReader\KanaReader.exe after building. Rebuild after updating source, checkpoint, or translation weights:

    python -m PyInstaller --noconfirm --clean --onedir --windowed --name KanaReader --add-data "checkpoints\best_model.pt;checkpoints" --add-data "models\opus-mt-ja-en;models\opus-mt-ja-en" --collect-all transformers --collect-all tokenizers --collect-all sentencepiece --hidden-import pyttsx3.drivers.sapi5 --hidden-import comtypes.gen.SpeechLib --hidden-import webcam_app src\desktop_app.py

Keep the _internal folder beside the executable. Run python src\setup_translation.py before building so the translation weights are available.
