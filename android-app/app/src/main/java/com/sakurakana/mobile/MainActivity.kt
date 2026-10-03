package com.sakurakana.mobile

import android.app.Activity
import android.content.ContentValues
import android.content.Intent
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.Path
import android.graphics.Rect
import android.graphics.RectF
import android.net.Uri
import android.os.Bundle
import android.provider.MediaStore
import android.speech.tts.TextToSpeech
import android.view.Gravity
import android.view.MotionEvent
import android.view.View
import android.view.ViewGroup
import android.view.inputmethod.InputMethodManager
import android.content.Context
import android.widget.Button
import android.widget.EditText
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.Spinner
import android.widget.ArrayAdapter
import android.widget.TextView
import org.json.JSONObject
import java.io.ByteArrayOutputStream
import java.io.InputStream
import java.net.HttpURLConnection
import java.net.URL
import java.util.Locale
import java.util.concurrent.Executors
import kotlin.math.max
import kotlin.math.min

private data class InkStroke(val path: Path, val color: Int, val width: Float)
private data class VocabularyCard(val word: String, val reading: String, val meaning: String)

class MainActivity : Activity(), TextToSpeech.OnInitListener {
    private val pink = Color.rgb(53, 89, 168)
    private val softPink = Color.rgb(237, 242, 252)
    private val ink = Color.rgb(32, 33, 36)
    private val muted = Color.rgb(95, 99, 104)
    private val worker = Executors.newSingleThreadExecutor()
    private lateinit var serverField: EditText
    private lateinit var accessCodeField: EditText
    private lateinit var status: TextView
    private lateinit var preview: ImageView
    private lateinit var reading: TextView
    private lateinit var japaneseField: EditText
    private lateinit var addPhraseButton: Button
    private lateinit var phraseView: TextView
    private lateinit var englishView: TextView
    private lateinit var translationTypePicker: Spinner
    private lateinit var vocabLevelPicker: Spinner
    private lateinit var vocabWordView: TextView
    private lateinit var vocabReadingView: TextView
    private lateinit var vocabMeaningView: TextView
    private lateinit var vocabProgressView: TextView
    private lateinit var vocabLevelLabel: TextView
    private var vocabDecks: Map<String, List<VocabularyCard>> = emptyMap()
    private var vocabIndex = 0
    private var vocabKnown = 0
    private var vocabRevealed = false
    private lateinit var pad: DrawingPad
    private var photoBitmap: Bitmap? = null
    private var phrase = ""
    private var autoPhraseStart: Int? = null
    private var autoPhraseText: String? = null
    private var pendingCameraUri: Uri? = null
    private var tts: TextToSpeech? = null
    private var isTranslating = false
    private var drawingEraser = false
    @Volatile private var requestAccessCode = ""

    companion object {
        private const val PICK_IMAGE = 1001
        private const val TAKE_PHOTO = 1002
        private const val VOICE_INPUT = 1003
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.statusBarColor = Color.WHITE
        window.navigationBarColor = Color.WHITE
        window.decorView.systemUiVisibility = View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR or View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR
        tts = TextToSpeech(this, this)
        buildScreen()
    }

    private fun buildScreen() {
        val page = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            background = android.graphics.drawable.GradientDrawable().apply { setColor(Color.WHITE) }
            setPadding(dp(18), dp(12), dp(18), dp(24))
        }
        val scroll = ScrollView(this).apply { isFillViewport = true; addView(page) }
        setContentView(scroll)

        page.addView(text("Japanese Practice", 27, ink, true))
        page.addView(text("Read, speak, draw, and translate Japanese.", 15, muted))

        val connectCard = card()
        connectCard.addView(text("Connect to your PC", 19, ink, true))
        connectCard.addView(text("Enter the address and PIN shown by the PC app. Use its temporary link to connect from any network.", 14, muted))
        serverField = EditText(this).apply {
            setSingleLine(true)
            textSize = 15f
            setText(getSharedPreferences("connection", MODE_PRIVATE).getString("server_url", "").orEmpty())
            hint = "https://...trycloudflare.com or http://PC-IP:5055"
            setPadding(dp(12), dp(8), dp(12), dp(8))
            background = rounded(Color.WHITE, Color.rgb(217, 222, 232))
            inputType = android.text.InputType.TYPE_CLASS_TEXT or android.text.InputType.TYPE_TEXT_VARIATION_URI
        }
        connectCard.addView(serverField, matchWrap(top = 9))
        accessCodeField = EditText(this).apply {
            setSingleLine(true); textSize = 15f; hint = "Remote access PIN (leave blank for local Wi-Fi)"
            setPadding(dp(12), dp(8), dp(12), dp(8)); background = rounded(Color.WHITE, Color.rgb(217, 222, 232))
            inputType = android.text.InputType.TYPE_CLASS_NUMBER or android.text.InputType.TYPE_NUMBER_VARIATION_PASSWORD
            val saved = getSharedPreferences("connection", MODE_PRIVATE).getString("access_code", "").orEmpty(); setText(saved)
        }
        connectCard.addView(accessCodeField, matchWrap(top = 8))
        connectCard.addView(button("Connect", true) { connectToPc() }, matchWrap(top = 9))
        status = text("Enter the PC server address and connect.", 13, muted)
        connectCard.addView(status, matchWrap(top = 7))
        page.addView(connectCard, matchWrap(top = 16))

        val drawCard = card()
        drawCard.addView(text("1 · Draw a kana", 19, ink, true))
        drawCard.addView(text("Draw one hiragana character using blue or black ink. Recognition trims to the ink area.", 14, muted))
        pad = DrawingPad(this)
        drawCard.addView(pad, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(290)).apply { topMargin = dp(10) })
        val drawActions = horizontal()
        drawActions.addView(button("Blue / black", false) { pad.toggleColor() }, weightParams())
        drawActions.addView(button("Eraser", false) { drawingEraser = !drawingEraser; pad.setEraser(drawingEraser); showStatus(if (drawingEraser) "Eraser selected." else "Pen selected.") }, weightParams(start = 5))
        drawActions.addView(button("Undo", false) { pad.undo() }, weightParams(start = 5))
        drawActions.addView(button("Clear", false) { pad.clear() }, weightParams(start = 5))
        drawCard.addView(drawActions, matchWrap(top = 8))
        drawCard.addView(button("Read drawing", true) {
            val crop = pad.inkCrop()
            if (crop == null) showStatus("Draw a kana in the box first.", true) else recognize(crop)
        }, matchWrap(top = 8))
        page.addView(drawCard, matchWrap(top = 14))

        val photoCard = card()
        photoCard.addView(text("Or use your camera or gallery", 18, ink, true))
        val photoActions = horizontal()
        photoActions.addView(button("Take photo", false) { takePhoto() }, weightParams())
        photoActions.addView(button("Choose photo", false) { choosePhoto() }, weightParams(start = 8))
        photoCard.addView(photoActions, matchWrap(top = 8))
        preview = ImageView(this).apply {
            visibility = View.GONE
            adjustViewBounds = true
            maxHeight = dp(300)
            scaleType = ImageView.ScaleType.FIT_CENTER
            setBackgroundColor(Color.rgb(255, 250, 253))
        }
        photoCard.addView(preview, matchWrap(top = 8))
        photoCard.addView(button("Read selected photo", true) {
            val image = photoBitmap
            if (image == null) showStatus("Take or choose a photo first.", true) else recognize(image)
        }, matchWrap(top = 8))
        page.addView(photoCard, matchWrap(top = 14))

        val readCard = card()
        readCard.addView(text("2 · Check the reading", 19, ink, true))
        readCard.addView(text("Image recognition is trained for hiragana. You can type or correct kanji, katakana, and mixed Japanese below for translation.", 13, muted))
        reading = text("Kana guesses will appear here.", 14, muted)
        readCard.addView(reading, matchWrap(top = 6))
        japaneseField = EditText(this).apply {
            textSize = 23f
            hint = "Recognized kana — tap to correct"
            setSingleLine(true)
            setPadding(dp(12), dp(10), dp(12), dp(10))
            background = rounded(Color.WHITE, Color.rgb(217, 222, 232))
            inputType = android.text.InputType.TYPE_CLASS_TEXT or android.text.InputType.TYPE_TEXT_FLAG_CAP_SENTENCES
        }
        readCard.addView(japaneseField, matchWrap(top = 8))
        addPhraseButton = button("Add to phrase", true) { addToPhrase() }
        readCard.addView(addPhraseButton, matchWrap(top = 8))
        readCard.addView(button("Speak Japanese", false) { startVoiceInput() }, matchWrap(top = 8))
        readCard.addView(button("Translate this line", false) { translate(japaneseField.text.toString()) }, matchWrap(top = 8))
        page.addView(readCard, matchWrap(top = 14))

        val phraseCard = card()
        phraseCard.addView(text("3 · Build a word or phrase", 19, ink, true))
        phraseCard.addView(text("Translation type", 13, muted), matchWrap(top = 6))
        translationTypePicker = Spinner(this)
        translationTypePicker.adapter = ArrayAdapter(this, android.R.layout.simple_spinner_dropdown_item,
            listOf("Word from reading", "Phrase builder", "Sentence from reading", "Recognized line"))
        phraseCard.addView(translationTypePicker, matchWrap(top = 4))
        phraseView = text("(empty)", 25, ink)
        phraseCard.addView(phraseView, matchWrap(top = 4))
        val phraseActions = horizontal()
        phraseActions.addView(button("Translate selection", true) { translateSelected() }, weightParams())
        phraseActions.addView(button("Undo", false) { undoPhrase() }, weightParams(start = 7))
        phraseActions.addView(button("Clear", false) { clearPhrase() }, weightParams(start = 7))
        phraseCard.addView(phraseActions, matchWrap(top = 10))
        val divider = View(this).apply { setBackgroundColor(Color.rgb(232, 220, 226)) }
        phraseCard.addView(divider, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(1)).apply { topMargin = dp(15); bottomMargin = dp(9) })
        phraseCard.addView(text("English meaning", 13, muted))
        englishView = text("Translation will appear here.", 24, pink, true)
        phraseCard.addView(englishView, matchWrap(top = 4))
        phraseCard.addView(button("Speak English", false) { speakEnglish() }, matchWrap(top = 8))
        page.addView(phraseCard, matchWrap(top = 14))

        val vocabCard = card()
        vocabCard.addView(text("4 · Learn vocabulary by level", 19, ink, true))
        vocabCard.addView(text("A starter deck of common words from N5 to N1. Your known-word count stays on this phone.", 13, muted))
        vocabLevelPicker = Spinner(this)
        vocabLevelPicker.adapter = ArrayAdapter(this, android.R.layout.simple_spinner_dropdown_item,
            listOf("N5 · Beginner", "N4 · Elementary", "N3 · Intermediate", "N2 · Upper intermediate", "N1 · Advanced"))
        vocabCard.addView(vocabLevelPicker, matchWrap(top = 8))
        val flash = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER
            setPadding(dp(16), dp(16), dp(16), dp(16))
            background = rounded(Color.rgb(247, 249, 252), Color.rgb(225, 228, 234), dp(14).toFloat())
        }
        vocabWordView = text("水", 34, ink, true).apply { gravity = Gravity.CENTER }
        vocabReadingView = text("みず", 18, muted).apply { gravity = Gravity.CENTER }
        vocabMeaningView = text("water", 20, pink, true).apply { gravity = Gravity.CENTER; visibility = View.GONE }
        vocabLevelLabel = text("N5", 12, pink, true).apply { gravity = Gravity.CENTER }
        flash.addView(vocabLevelLabel)
        flash.addView(vocabWordView)
        flash.addView(vocabReadingView)
        flash.addView(vocabMeaningView)
        vocabCard.addView(flash, matchWrap(top = 10))
        vocabProgressView = text("Card 1 · Known: 0", 13, muted)
        vocabCard.addView(vocabProgressView, matchWrap(top = 6))
        val vocabActions = horizontal()
        vocabActions.addView(button("Show meaning", true) { revealVocabulary() }, weightParams())
        vocabActions.addView(button("I knew it", false) { markVocabularyKnown() }, weightParams(start = 6))
        vocabActions.addView(button("Next word", false) { nextVocabulary() }, weightParams(start = 6))
        vocabCard.addView(vocabActions, matchWrap(top = 8))
        vocabLevelPicker.onItemSelectedListener = object : android.widget.AdapterView.OnItemSelectedListener {
            override fun onNothingSelected(parent: android.widget.AdapterView<*>?) = Unit
            override fun onItemSelected(parent: android.widget.AdapterView<*>?, view: View?, position: Int, id: Long) {
                vocabIndex = 0
                vocabRevealed = false
                showVocabularyCard()
            }
        }
        loadVocabulary()
        page.addView(vocabCard, matchWrap(top = 14))
    }

    private fun connectToPc() {
        val base = baseUrl()
        requestAccessCode = accessCodeField.text.toString().trim()
        getSharedPreferences("connection", MODE_PRIVATE).edit()
            .putString("access_code", requestAccessCode).putString("server_url", base.orEmpty()).apply()
        if (base == null) { showStatus("Enter the PC address shown by the running server, such as http://192.168.1.24:5055", true); return }
        showStatus("Connecting to the PC…")
        worker.execute {
            try {
                val connection = URL("$base/").openConnection() as HttpURLConnection
                connection.connectTimeout = 5000
                connection.readTimeout = 5000
                connection.requestMethod = "GET"
                connection.instanceFollowRedirects = false
                addAccessHeader(connection)
                val ok = connection.responseCode in 200..299
                connection.disconnect()
                if (ok) runOnUiThread { showStatus("Connected. Draw a kana or take a photo.") }
                else runOnUiThread { showStatus("PC responded, but the app page was unavailable.", true) }
            } catch (error: Exception) {
                runOnUiThread { showStatus("Could not connect. Check the URL, PIN, and that the PC remote link is running.", true) }
            }
        }
    }

    private fun startVoiceInput() {
        val intent = Intent(android.speech.RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
            putExtra(android.speech.RecognizerIntent.EXTRA_LANGUAGE_MODEL, android.speech.RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
            putExtra(android.speech.RecognizerIntent.EXTRA_LANGUAGE, "ja-JP")
            putExtra(android.speech.RecognizerIntent.EXTRA_PROMPT, "Speak Japanese")
        }
        try { startActivityForResult(intent, VOICE_INPUT) }
        catch (_: Exception) { showStatus("No Japanese voice-recognition service is available on this phone.", true) }
    }

    private fun takePhoto() {
        try {
            val values = ContentValues().apply {
                put(MediaStore.Images.Media.DISPLAY_NAME, "sakura-kana-${System.currentTimeMillis()}.jpg")
                put(MediaStore.Images.Media.MIME_TYPE, "image/jpeg")
                put(MediaStore.Images.Media.RELATIVE_PATH, "Pictures/Sakura Kana")
                put(MediaStore.Images.Media.IS_PENDING, 1)
            }
            val uri = contentResolver.insert(MediaStore.Images.Media.EXTERNAL_CONTENT_URI, values)
                ?: throw IllegalStateException("Could not create a photo file")
            pendingCameraUri = uri
            val intent = Intent(MediaStore.ACTION_IMAGE_CAPTURE).apply {
                putExtra(MediaStore.EXTRA_OUTPUT, uri)
                addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_GRANT_WRITE_URI_PERMISSION)
            }
            startActivityForResult(intent, TAKE_PHOTO)
        } catch (error: Exception) { showStatus("Could not open the camera: ${error.message}", true) }
    }

    private fun choosePhoto() {
        val intent = Intent(Intent.ACTION_GET_CONTENT).apply { type = "image/*" }
        startActivityForResult(Intent.createChooser(intent, "Choose handwriting photo"), PICK_IMAGE)
    }

    @Deprecated("Legacy callback keeps this app dependency-free")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode == VOICE_INPUT) {
            if (resultCode == RESULT_OK) {
                val spoken = data?.getStringArrayListExtra(android.speech.RecognizerIntent.EXTRA_RESULTS)?.firstOrNull().orEmpty()
                if (spoken.isNotBlank()) { japaneseField.setText(spoken); reading.text = "Voice input · review or edit the recognized Japanese."; showStatus("Japanese speech recognized. Translate it or add it to your phrase.") }
                else showStatus("No speech was recognized. Try again.", true)
            } else showStatus("Voice input was cancelled.")
            return
        }
        val uri = if (requestCode == TAKE_PHOTO) pendingCameraUri else data?.data
        if (requestCode == TAKE_PHOTO) {
            pendingCameraUri?.let { imageUri ->
                val values = ContentValues().apply { put(MediaStore.Images.Media.IS_PENDING, 0) }
                contentResolver.update(imageUri, values, null, null)
            }
        }
        if (resultCode != RESULT_OK || uri == null) {
            if (requestCode == TAKE_PHOTO) pendingCameraUri?.let { contentResolver.delete(it, null, null) }
            showStatus("Photo selection cancelled.")
            return
        }
        try {
            contentResolver.openInputStream(uri).use { input ->
                if (input == null) throw IllegalStateException("Could not read the selected photo")
                photoBitmap = decodeScaled(input)
            }
            preview.setImageBitmap(photoBitmap)
            preview.visibility = View.VISIBLE
            showStatus("Photo ready. Tap “Read selected photo”.")
        } catch (error: Exception) { showStatus("Could not load photo: ${error.message}", true) }
    }

    private fun decodeScaled(input: InputStream): Bitmap {
        val bytes = input.readBytes()
        val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
        BitmapFactory.decodeByteArray(bytes, 0, bytes.size, bounds)
        var sample = 1
        while (max(bounds.outWidth, bounds.outHeight) / sample > 1800) sample *= 2
        return BitmapFactory.decodeByteArray(bytes, 0, bytes.size, BitmapFactory.Options().apply { inSampleSize = sample })
            ?: throw IllegalArgumentException("Unsupported image format")
    }

    private fun recognize(bitmap: Bitmap) {
        val base = baseUrl() ?: run { showStatus("Enter the PC server address and connect first.", true); return }
        autoPhraseStart = null
        autoPhraseText = null
        addPhraseButton.text = "Add to phrase"
        setBusy(true)
        showStatus("Reading handwriting on the PC…")
        worker.execute {
            try {
                val response = multipart("$base/api/recognize", bitmap)
                val kana = response.getString("kana")
                val guesses = response.getJSONArray("readings")
                var certain = guesses.length() > 0
                val summary = buildString {
                    if (guesses.length() == 0) append("No kana found. Try a closer, brighter image.")
                    for (i in 0 until guesses.length()) {
                        val item = guesses.getJSONObject(i)
                        if (item.optDouble("confidence") < 0.70) certain = false
                        if (isNotEmpty()) append("\n")
                        append("${i + 1}. ${item.optString("kana")} · ${item.optString("pronunciation")} · ${"%.0f".format(Locale.US, item.optDouble("confidence") * 100)}%")
                        val alternatives = item.optJSONArray("alternatives")
                        if (alternatives != null && alternatives.length() > 1) {
                            append("\nOther: ")
                            for (j in 1 until alternatives.length()) {
                                if (j > 1) append(" · ")
                                val alternative = alternatives.getJSONObject(j)
                                append("${alternative.optString("kana")} ${"%.0f".format(Locale.US, alternative.optDouble("confidence") * 100)}%")
                            }
                        }
                    }
                }
                runOnUiThread {
                    japaneseField.setText(kana)
                    reading.text = summary
                    if (kana.isNotBlank()) {
                        autoPhraseStart = phrase.length
                        autoPhraseText = kana
                        phrase += kana
                        phraseView.text = phrase
                        addPhraseButton.text = "Update phrase"
                        showStatus(if (certain) "Reading added to your phrase. Correct it if needed, then translate." else "Candidate added to your phrase. Review the uncertain characters before translating.")
                    } else {
                        showStatus(if (kana.isBlank()) "No ink was recognized. Try a clearer photo/drawing." else "Check this uncertain reading, then add it to your phrase.")
                    }
                    setBusy(false)
                }
            } catch (error: Exception) {
                runOnUiThread { showStatus("Recognition failed: ${error.message ?: "Check the server connection."}", true); setBusy(false) }
            }
        }
    }

    private fun multipart(endpoint: String, bitmap: Bitmap): JSONObject {
        val boundary = "----SakuraKana${System.currentTimeMillis()}"
        val imageBytes = ByteArrayOutputStream().use { out -> bitmap.compress(Bitmap.CompressFormat.PNG, 100, out); out.toByteArray() }
        val connection = URL(endpoint).openConnection() as HttpURLConnection
        connection.connectTimeout = 10000
        connection.readTimeout = 90000
        connection.requestMethod = "POST"
        connection.doOutput = true
        connection.setRequestProperty("Content-Type", "multipart/form-data; boundary=$boundary")
        addAccessHeader(connection)
        connection.outputStream.use { out ->
            out.write("--$boundary\r\nContent-Disposition: form-data; name=\"image\"; filename=\"handwriting.png\"\r\nContent-Type: image/png\r\n\r\n".toByteArray())
            out.write(imageBytes)
            out.write("\r\n--$boundary--\r\n".toByteArray())
        }
        val code = connection.responseCode
        val stream = if (code in 200..299) connection.inputStream else connection.errorStream
        val body = stream?.bufferedReader()?.use { it.readText() }.orEmpty()
        connection.disconnect()
        val json = JSONObject(body.ifBlank { "{}" })
        if (code !in 200..299) throw IllegalStateException(json.optString("error", "Server returned HTTP $code"))
        return json
    }

    private fun addToPhrase() {
        val text = japaneseField.text.toString().trim()
        if (text.isEmpty()) { showStatus("Read or type some Japanese first.", true); return }
        val start = autoPhraseStart
        val oldText = autoPhraseText
        if (start != null && oldText != null && phrase.substring(start, (start + oldText.length).coerceAtMost(phrase.length)) == oldText) {
            if (text == oldText) {
                showStatus("This reading is already in your phrase.")
                return
            }
            phrase = phrase.removeRange(start, start + oldText.length).let { before ->
                before.substring(0, start) + text + before.substring(start)
            }
            autoPhraseText = text
            showStatus("Updated the reading in your phrase.")
        } else {
            phrase += text
            showStatus("Added to phrase.")
        }
        phraseView.text = phrase
        addPhraseButton.text = if (autoPhraseStart != null) "Update phrase" else "Add to phrase"
        hideKeyboard()
    }

    private fun undoPhrase() {
        autoPhraseStart = null
        autoPhraseText = null
        addPhraseButton.text = "Add to phrase"
        if (phrase.isNotEmpty()) phrase = phrase.dropLast(1)
        phraseView.text = phrase.ifEmpty { "(empty)" }
    }

    private fun clearPhrase() {
        phrase = ""
        autoPhraseStart = null
        autoPhraseText = null
        addPhraseButton.text = "Add to phrase"
        phraseView.text = "(empty)"
        englishView.text = "Translation will appear here."
        showStatus("Phrase cleared.")
    }

    private fun translate(text: String) {
        val base = baseUrl() ?: run { showStatus("Enter the PC server address first.", true); return }
        if (text.isBlank()) { showStatus("Enter or capture some Japanese first.", true); return }
        if (isTranslating) return
        isTranslating = true
        showStatus("Translating on the PC…")
        worker.execute {
            try {
                val connection = URL("$base/api/translate").openConnection() as HttpURLConnection
                connection.connectTimeout = 10000
                connection.readTimeout = 120000
                connection.requestMethod = "POST"
                connection.doOutput = true
                connection.setRequestProperty("Content-Type", "application/json; charset=utf-8")
                addAccessHeader(connection)
                connection.outputStream.use { it.write(JSONObject().put("text", text).toString().toByteArray(Charsets.UTF_8)) }
                val code = connection.responseCode
                val body = (if (code in 200..299) connection.inputStream else connection.errorStream)?.bufferedReader()?.use { it.readText() }.orEmpty()
                connection.disconnect()
                val json = JSONObject(body.ifBlank { "{}" })
                if (code !in 200..299) throw IllegalStateException(json.optString("error", "Server returned HTTP $code"))
                runOnUiThread { englishView.text = json.optString("translation").ifBlank { "(No translation returned)" }; showStatus("Translation ready."); isTranslating = false }
            } catch (error: Exception) {
                runOnUiThread { showStatus("Translation failed: ${error.message ?: "Check the PC server."}", true); isTranslating = false }
            }
        }
    }

    private fun translateSelected() {
        val source = when (translationTypePicker.selectedItemPosition) {
            0, 2, 3 -> japaneseField.text.toString()
            else -> phrase
        }
        translate(source)
    }

    private fun speakEnglish() {
        val text = englishView.text.toString()
        if (text == "Translation will appear here." || text.isBlank()) { showStatus("Translate Japanese before using speech.", true); return }
        tts?.language = Locale.US
        tts?.speak(text, TextToSpeech.QUEUE_FLUSH, null, "sakura-english")
        showStatus("Speaking English.")
    }

    private fun loadVocabulary() {
        try {
            val json = JSONObject(assets.open("vocabulary.json").bufferedReader().use { it.readText() })
            val levels = mutableMapOf<String, List<VocabularyCard>>()
            for (levelName in listOf("N5", "N4", "N3", "N2", "N1")) {
                val words = json.getJSONArray(levelName)
                levels[levelName] = (0 until words.length()).map { n ->
                    val item = words.getJSONObject(n)
                    VocabularyCard(item.getString("word"), item.getString("reading"), item.getString("meaning"))
                }
            }
            vocabDecks = levels
            vocabKnown = getSharedPreferences("sakura-vocabulary", MODE_PRIVATE).getInt("known", 0)
            showVocabularyCard()
        } catch (_: Exception) { showStatus("Could not load the built-in vocabulary deck.", true) }
    }

    private fun currentVocabularyLevel() = listOf("N5", "N4", "N3", "N2", "N1").getOrElse(vocabLevelPicker.selectedItemPosition) { "N5" }
    private fun showVocabularyCard() {
        if (!::vocabWordView.isInitialized) return
        val level = currentVocabularyLevel()
        val deck = vocabDecks[level].orEmpty()
        if (deck.isEmpty()) return
        vocabIndex = ((vocabIndex % deck.size) + deck.size) % deck.size
        val card = deck[vocabIndex]
        vocabLevelLabel.text = level
        vocabWordView.text = card.word
        vocabReadingView.text = card.reading
        vocabMeaningView.text = card.meaning
        vocabMeaningView.visibility = if (vocabRevealed) View.VISIBLE else View.GONE
        vocabProgressView.text = "$level · Card ${vocabIndex + 1} of ${deck.size} · Known: $vocabKnown"
    }
    private fun revealVocabulary() { vocabRevealed = true; showVocabularyCard() }
    private fun nextVocabulary() { vocabIndex++; vocabRevealed = false; showVocabularyCard() }
    private fun markVocabularyKnown() {
        vocabKnown++
        getSharedPreferences("sakura-vocabulary", MODE_PRIVATE).edit().putInt("known", vocabKnown).apply()
        nextVocabulary()
    }

    private fun addAccessHeader(connection: HttpURLConnection) {
        val code = requestAccessCode
        if (code.isNotEmpty()) connection.setRequestProperty("X-Sakura-Access-Code", code)
    }

    private fun baseUrl(): String? {
        val raw = serverField.text.toString().trim().trimEnd('/')
        return raw.takeIf { it.startsWith("http://") || it.startsWith("https://") }
    }

    private fun setBusy(busy: Boolean) {
        // The status remains visible while image inference runs off the UI thread.
    }

    private fun showStatus(message: String, error: Boolean = false) {
        if (!::status.isInitialized) return
        status.text = message
        status.setTextColor(if (error) Color.rgb(174, 39, 76) else muted)
    }

    private fun hideKeyboard() {
        (getSystemService(Context.INPUT_METHOD_SERVICE) as InputMethodManager).hideSoftInputFromWindow(japaneseField.windowToken, 0)
    }

    private fun text(value: String, size: Int, color: Int, bold: Boolean = false) = TextView(this).apply {
        text = value
        textSize = size.toFloat()
        setTextColor(color)
        if (bold) setTypeface(typeface, android.graphics.Typeface.BOLD)
        setPadding(0, dp(3), 0, dp(3))
    }

    private fun card() = LinearLayout(this).apply {
        orientation = LinearLayout.VERTICAL
        setPadding(dp(15), dp(14), dp(15), dp(14))
        background = android.graphics.drawable.GradientDrawable(
            android.graphics.drawable.GradientDrawable.Orientation.TL_BR,
            intArrayOf(Color.WHITE, Color.WHITE)
        ).apply { cornerRadius = dp(15).toFloat(); setStroke(dp(1), Color.rgb(225, 228, 234)) }
        elevation = dp(7).toFloat()
        translationZ = dp(2).toFloat()
    }

    private fun horizontal() = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL }

    private fun button(label: String, primary: Boolean, action: () -> Unit) = Button(this).apply {
        text = label
        textSize = 14f
        isAllCaps = false
        setTextColor(if (primary) Color.WHITE else pink)
        background = android.graphics.drawable.GradientDrawable(
            android.graphics.drawable.GradientDrawable.Orientation.TOP_BOTTOM,
            if (primary) intArrayOf(Color.rgb(61, 96, 174), Color.rgb(42, 70, 139))
            else intArrayOf(Color.WHITE, Color.rgb(243, 246, 251))
        ).apply {
            cornerRadius = dp(10).toFloat()
            setStroke(dp(1), if (primary) Color.rgb(61, 96, 174) else Color.rgb(217, 222, 232))
        }
        minHeight = dp(48)
        setPadding(dp(8), dp(4), dp(8), dp(4))
        elevation = dp(5).toFloat()
        translationZ = dp(2).toFloat()
        setOnTouchListener { view, event ->
            when (event.action) {
                MotionEvent.ACTION_DOWN -> view.translationZ = dp(1).toFloat()
                MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL -> view.translationZ = dp(3).toFloat()
            }
            false
        }
        setOnClickListener { action() }
    }

    private fun rounded(fill: Int, stroke: Int, radius: Float = dp(10).toFloat()) = android.graphics.drawable.GradientDrawable().apply {
        setColor(fill)
        cornerRadius = radius
        setStroke(dp(1), stroke)
    }

    private fun matchWrap(top: Int = 0) = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT).apply { topMargin = dp(top) }
    private fun weightParams(start: Int = 0) = LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f).apply { marginStart = dp(start) }
    private fun dp(value: Int) = (value * resources.displayMetrics.density).toInt()

    override fun onInit(statusCode: Int) {
        tts?.language = Locale.US
    }

    override fun onDestroy() {
        worker.shutdownNow()
        tts?.stop()
        tts?.shutdown()
        super.onDestroy()
    }

    private inner class DrawingPad(context: Context) : View(context) {
        private val strokes = mutableListOf<InkStroke>()
        private var activePath: Path? = null
        private var penColor = Color.rgb(42, 59, 145)
        private var isErasing = false
        private var lastX = 0f
        private var lastY = 0f
        private val backgroundPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.WHITE; style = Paint.Style.FILL }
        private val strokePaint = Paint(Paint.ANTI_ALIAS_FLAG).apply { style = Paint.Style.STROKE; strokeCap = Paint.Cap.ROUND; strokeJoin = Paint.Join.ROUND }
        private val borderPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.rgb(240, 214, 225); style = Paint.Style.STROKE; strokeWidth = dp(1).toFloat() }

        init { setLayerType(View.LAYER_TYPE_SOFTWARE, null); elevation = dp(3).toFloat(); translationZ = dp(1).toFloat() }

        override fun onDraw(canvas: Canvas) {
            super.onDraw(canvas)
            canvas.drawRoundRect(RectF(0f, 0f, width.toFloat(), height.toFloat()), dp(10).toFloat(), dp(10).toFloat(), backgroundPaint)
            for (stroke in strokes) { strokePaint.color = stroke.color; strokePaint.strokeWidth = stroke.width; canvas.drawPath(stroke.path, strokePaint) }
            activePath?.let { strokePaint.color = if (isErasing) Color.WHITE else penColor; strokePaint.strokeWidth = dp(if (isErasing) 28 else 15).toFloat(); canvas.drawPath(it, strokePaint) }
            canvas.drawRoundRect(RectF(1f, 1f, width - 1f, height - 1f), dp(10).toFloat(), dp(10).toFloat(), borderPaint)
        }

        override fun onTouchEvent(event: MotionEvent): Boolean {
            when (event.action) {
                MotionEvent.ACTION_DOWN -> { lastX = event.x; lastY = event.y; activePath = Path().apply { moveTo(lastX, lastY) }; invalidate(); return true }
                MotionEvent.ACTION_MOVE -> {
                    for (i in 0 until event.historySize) { val x = event.getHistoricalX(i); val y = event.getHistoricalY(i); activePath?.quadTo(lastX, lastY, (lastX + x) / 2f, (lastY + y) / 2f); lastX = x; lastY = y }
                    activePath?.quadTo(lastX, lastY, (lastX + event.x) / 2f, (lastY + event.y) / 2f); lastX = event.x; lastY = event.y; invalidate(); return true
                }
                MotionEvent.ACTION_UP -> {
                    activePath?.lineTo(event.x, event.y)
                    activePath?.let { path -> strokes.add(InkStroke(Path(path), if (isErasing) Color.WHITE else penColor, if (isErasing) dp(28).toFloat() else dp(15).toFloat())) }
                    activePath = null
                    invalidate()
                    performClick()
                    return true
                }
            }
            return true
        }

        override fun performClick(): Boolean { super.performClick(); return true }

        fun setEraser(enabled: Boolean) { isErasing = enabled; invalidate() }
        fun toggleColor() { isErasing = false; penColor = if (penColor == Color.BLACK) Color.rgb(42, 59, 145) else Color.BLACK; showStatus(if (penColor == Color.BLACK) "Pen: black." else "Pen: blue."); invalidate() }
        fun undo() { if (strokes.isNotEmpty()) strokes.removeAt(strokes.lastIndex); invalidate() }
        fun clear() { strokes.clear(); activePath = null; invalidate() }

        fun inkCrop(): Bitmap? {
            if (width <= 0 || height <= 0 || strokes.isEmpty()) return null
            val full = Bitmap.createBitmap(width, height, Bitmap.Config.ARGB_8888)
            val canvas = Canvas(full)
            draw(canvas)
            var left = width; var top = height; var right = -1; var bottom = -1
            val pixels = IntArray(width)
            for (y in 0 until height) {
                full.getPixels(pixels, 0, width, 0, y, width, 1)
                for (x in 0 until width) {
                    val color = pixels[x]
                    val red = Color.red(color); val green = Color.green(color); val blue = Color.blue(color)
                    val inkPixel = (red < 190 && green < 190 && blue < 210) || (blue - red > 35 && blue - green > 20)
                    if (inkPixel) { left = min(left, x); right = max(right, x); top = min(top, y); bottom = max(bottom, y) }
                }
            }
            if (right < left || bottom < top) { full.recycle(); return null }
            val margin = max(dp(14), max(right - left, bottom - top) / 8)
            val bounds = Rect(max(0, left - margin), max(0, top - margin), min(width, right + margin + 1), min(height, bottom + margin + 1))
            val cropped = Bitmap.createBitmap(full, bounds.left, bounds.top, bounds.width(), bounds.height())
            full.recycle()
            return cropped
        }
    }
}
