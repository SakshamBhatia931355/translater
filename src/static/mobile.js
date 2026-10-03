const photo = document.querySelector('#photo');
const preview = document.querySelector('#preview');
const recognizeButton = document.querySelector('#recognize');
const addButton = document.querySelector('#add');
const statusEl = document.querySelector('#status');
const japanese = document.querySelector('#japanese');
const readings = document.querySelector('#readings');
const phraseEl = document.querySelector('#phrase');
const english = document.querySelector('#english');
const voiceStatus = document.querySelector('#voice-status');
let phrase = '';
let lastVoiceTranscript = '';

function status(message, kind = '') { statusEl.textContent = message; statusEl.className = `status ${kind}`; }
function updatePhrase() { phraseEl.textContent = phrase || '(empty)'; }
function escapeHtml(value) { return String(value).replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char])); }

function addBubble(text, kind, label) {
  const bubble = document.createElement('div');
  bubble.className = `bubble ${kind}`;
  const content = document.createElement('p');
  content.textContent = text;
  const caption = document.createElement('span');
  caption.textContent = label;
  bubble.append(content, caption);
  const conversation = document.querySelector('#conversation');
  conversation.appendChild(bubble);
  bubble.scrollIntoView({block: 'nearest', behavior: 'smooth'});
}

async function recognizeImage(file) {
  recognizeButton.disabled = true;
  status('Reading handwriting…');
  try {
    const data = new FormData(); data.append('image', file);
    const response = await fetch('/api/recognize', {method: 'POST', body: data});
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || 'Could not read this image.');
    japanese.value = result.kana || '';
    readings.innerHTML = result.readings.length ? result.readings.map((r, i) =>
      `<div class="reading"><strong>${i + 1}. ${escapeHtml(r.kana)}</strong> · ${escapeHtml(r.pronunciation)} · ${Math.round(r.confidence * 100)}%<br><span class="hint">Other guesses: ${r.alternatives.slice(1).map(a => `${escapeHtml(a.kana)} ${Math.round(a.confidence * 100)}%`).join(' · ')}</span></div>`
    ).join('') : 'No kana found. Try a closer, brighter image.';
    addButton.disabled = !japanese.value.trim();
    status(result.kana ? `Read ${result.readings.length} character(s). Check or edit the result.` : 'No kana found.', result.kana ? 'success' : '');
  } catch (error) { status(error.message, 'error'); }
  finally { recognizeButton.disabled = !photo.files?.[0]; }
}

photo.addEventListener('change', () => {
  const file = photo.files?.[0];
  if (!file) return;
  if (preview.dataset.url) URL.revokeObjectURL(preview.dataset.url);
  preview.dataset.url = URL.createObjectURL(file);
  preview.src = preview.dataset.url;
  preview.hidden = false;
  recognizeButton.disabled = false;
  status('Photo ready. Tap “Read photo”.');
});
recognizeButton.addEventListener('click', () => {
  const file = photo.files?.[0];
  if (file) recognizeImage(file);
});

const pad = document.querySelector('#drawing-pad');
const pen = pad.getContext('2d');
let strokes = [];
let activeStroke = null;
let inkColor = '#16181d';
let erasing = false;
function padSize() { const rect = pad.getBoundingClientRect(); return {width: rect.width, height: rect.height}; }
function redrawPad() {
  const {width, height} = padSize();
  const ratio = window.devicePixelRatio || 1;
  if (pad.width !== Math.round(width * ratio) || pad.height !== Math.round(height * ratio)) {
    pad.width = Math.max(1, Math.round(width * ratio));
    pad.height = Math.max(1, Math.round(height * ratio));
  }
  pen.setTransform(ratio, 0, 0, ratio, 0, 0);
  pen.clearRect(0, 0, width, height);
  pen.fillStyle = '#fff'; pen.fillRect(0, 0, width, height);
  [...strokes, ...(activeStroke ? [activeStroke] : [])].forEach(stroke => {
    const points = stroke.points;
    if (!points.length) return;
    const xy = p => [p.x * width, p.y * height];
    pen.beginPath(); pen.lineCap = 'round'; pen.lineJoin = 'round';
    pen.strokeStyle = stroke.color; pen.fillStyle = stroke.color; pen.lineWidth = stroke.width;
    const [sx, sy] = xy(points[0]); pen.moveTo(sx, sy);
    if (points.length === 1) { pen.arc(sx, sy, stroke.width / 2, 0, Math.PI * 2); pen.fill(); return; }
    for (let i = 1; i < points.length; i++) {
      const [x0, y0] = xy(points[i - 1]); const [x1, y1] = xy(points[i]);
      pen.quadraticCurveTo(x0, y0, (x0 + x1) / 2, (y0 + y1) / 2);
    }
    const [lastX, lastY] = xy(points[points.length - 1]); pen.lineTo(lastX, lastY); pen.stroke();
  });
}
function canvasPoint(event) {
  const rect = pad.getBoundingClientRect();
  return {x: Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width)), y: Math.max(0, Math.min(1, (event.clientY - rect.top) / rect.height))};
}
pad.addEventListener('pointerdown', event => {
  event.preventDefault(); pad.setPointerCapture(event.pointerId);
  activeStroke = {points:[canvasPoint(event)], color: erasing ? '#ffffff' : inkColor, width: erasing ? 24 : 8}; redrawPad();
});
pad.addEventListener('pointermove', event => { if (activeStroke && event.buttons) { activeStroke.points.push(canvasPoint(event)); redrawPad(); } });
function finishStroke() { if (activeStroke) strokes.push(activeStroke); activeStroke = null; redrawPad(); }
pad.addEventListener('pointerup', finishStroke); pad.addEventListener('pointercancel', finishStroke);
window.addEventListener('resize', redrawPad);
document.querySelector('#draw-color').addEventListener('click', event => {
  inkColor = inkColor === '#16181d' ? '#315fd4' : '#16181d'; erasing = false;
  event.currentTarget.textContent = inkColor === '#16181d' ? 'Ink: black' : 'Ink: blue';
  document.querySelector('#draw-eraser').setAttribute('aria-pressed', 'false');
});
document.querySelector('#draw-eraser').addEventListener('click', event => {
  erasing = !erasing; event.currentTarget.setAttribute('aria-pressed', String(erasing));
  event.currentTarget.textContent = erasing ? 'Eraser: on' : 'Eraser';
});
document.querySelector('#draw-undo').addEventListener('click', () => { strokes.pop(); redrawPad(); });
document.querySelector('#draw-clear').addEventListener('click', () => { strokes = []; activeStroke = null; redrawPad(); });
document.querySelector('#read-drawing').addEventListener('click', () => {
  finishStroke();
  if (!strokes.length) { status('Draw one Japanese character in the box first.', 'error'); return; }
  pad.toBlob(blob => {
    if (!blob) { status('Could not prepare that drawing.', 'error'); return; }
    recognizeImage(new File([blob], 'japanese-drawing.png', {type:'image/png'}));
  }, 'image/png');
});
redrawPad();

japanese.addEventListener('input', () => { addButton.disabled = !japanese.value.trim(); });
addButton.addEventListener('click', () => {
  phrase += japanese.value.trim(); updatePhrase(); addButton.disabled = true;
  status('Added to your phrase.', 'success');
});
document.querySelector('#undo').addEventListener('click', () => { phrase = Array.from(phrase).slice(0, -1).join(''); updatePhrase(); });
document.querySelector('#clear').addEventListener('click', () => { phrase = ''; updatePhrase(); english.textContent = 'Your translation will appear here.'; });

async function translate(text) {
  if (!text.trim()) { status('Say, type, or recognize some Japanese first.', 'error'); return null; }
  status('Translating…');
  try {
    const response = await fetch('/api/translate', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({text})});
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || 'Translation failed.');
    english.textContent = result.translation || '(No translation returned)';
    status('Translation ready.', 'success');
    return english.textContent;
  } catch (error) { status(error.message, 'error'); return null; }
}
document.querySelector('#translate-line').addEventListener('click', () => {
  document.querySelector('#translation-type').value = 'line';
  translate(japanese.value);
});
document.querySelector('#translate-phrase').addEventListener('click', () => {
  const type = document.querySelector('#translation-type').value;
  if (type === 'line') translate(japanese.value);
  else if (type === 'word') translate(japanese.value || phrase);
  else translate(phrase);
});

const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
const listenButton = document.querySelector('#voice-listen');
let recognizer = null;
listenButton.addEventListener('click', () => {
  if (!SpeechRecognition) { voiceStatus.textContent = 'Voice input is not available here. Try Chrome on Android, or type Japanese below.'; return; }
  try {
    recognizer = new SpeechRecognition();
    recognizer.lang = 'ja-JP'; recognizer.continuous = false; recognizer.interimResults = false; recognizer.maxAlternatives = 1;
    listenButton.disabled = true; voiceStatus.textContent = 'Listening… say a short Japanese phrase.';
    recognizer.onresult = event => {
      lastVoiceTranscript = event.results?.[0]?.[0]?.transcript?.trim() || '';
      if (lastVoiceTranscript) {
        japanese.value = lastVoiceTranscript; addButton.disabled = false;
        addBubble(lastVoiceTranscript, 'user-bubble', 'You said · Japanese');
        voiceStatus.textContent = 'Got it. Translate the phrase or edit the text first.';
      } else voiceStatus.textContent = 'I could not make out those words. Try once more.';
    };
    recognizer.onerror = event => { voiceStatus.textContent = event.error === 'not-allowed' ? 'Microphone access was blocked. Allow it in browser settings and try again.' : `Voice input ended (${event.error || 'no match'}). You can type instead.`; };
    recognizer.onend = () => { listenButton.disabled = false; };
    recognizer.start();
  } catch (error) { listenButton.disabled = false; voiceStatus.textContent = `Could not start voice input: ${error.message}`; }
});
document.querySelector('#voice-translate').addEventListener('click', async () => {
  const spoken = lastVoiceTranscript || japanese.value.trim();
  if (!spoken) { voiceStatus.textContent = 'Tap Speak Japanese or type a phrase first.'; return; }
  const translation = await translate(spoken);
  if (translation) addBubble(translation, 'translation-bubble', 'English meaning');
});

function speak(text, lang, message) {
  if (!text || !('speechSynthesis' in window)) { voiceStatus.textContent = 'Speech playback is not available in this browser.'; return; }
  window.speechSynthesis.cancel();
  const utterance = new SpeechSynthesisUtterance(text); utterance.lang = lang;
  window.speechSynthesis.speak(utterance); voiceStatus.textContent = message;
}
document.querySelector('#voice-hear-japanese').addEventListener('click', () => speak(japanese.value.trim(), 'ja-JP', 'Playing Japanese speech.'));
document.querySelector('#speak').addEventListener('click', () => {
  const text = english.textContent === 'Your translation will appear here.' ? '' : english.textContent;
  speak(text, 'en-US', 'Playing English speech.');
});

let vocabulary = {};
let vocabIndex = 0;
let knownCount = Number(localStorage.getItem('sakura-vocab-known') || 0);
const vocabLevel = document.querySelector('#vocab-level');
const vocabWord = document.querySelector('#vocab-word');
const vocabReading = document.querySelector('#vocab-reading');
const vocabMeaning = document.querySelector('#vocab-meaning');
function showVocabCard() {
  const level = vocabLevel.value; const deck = vocabulary[level] || [];
  if (!deck.length) return;
  vocabIndex = ((vocabIndex % deck.length) + deck.length) % deck.length;
  const card = deck[vocabIndex];
  document.querySelector('#vocab-level-label').textContent = level;
  vocabWord.textContent = card.word; vocabReading.textContent = card.reading; vocabMeaning.textContent = card.meaning;
  vocabMeaning.hidden = true; document.querySelector('#vocab-reveal').textContent = 'Show meaning';
  document.querySelector('#vocab-progress').textContent = `Card ${vocabIndex + 1} of ${deck.length} · Known: ${knownCount}`;
}
fetch('/static/vocabulary.json').then(response => {
  if (!response.ok) throw new Error('Vocabulary list unavailable');
  return response.json();
}).then(data => { vocabulary = data; showVocabCard(); }).catch(() => { vocabWord.textContent = 'Vocabulary could not load.'; });
vocabLevel.addEventListener('change', () => { vocabIndex = 0; showVocabCard(); });
document.querySelector('#vocab-reveal').addEventListener('click', () => { vocabMeaning.hidden = false; document.querySelector('#vocab-reveal').textContent = 'Meaning shown'; });
document.querySelector('#vocab-next').addEventListener('click', () => { vocabIndex++; showVocabCard(); });
document.querySelector('#vocab-known').addEventListener('click', () => {
  knownCount++; localStorage.setItem('sakura-vocab-known', String(knownCount)); vocabIndex++; showVocabCard();
});
