const photo = document.querySelector('#photo');
const preview = document.querySelector('#preview');
const recognizeButton = document.querySelector('#recognize');
const addButton = document.querySelector('#add');
const statusEl = document.querySelector('#status');
const japanese = document.querySelector('#japanese');
const readings = document.querySelector('#readings');
const phraseEl = document.querySelector('#phrase');
const english = document.querySelector('#english');
let phrase = '';

function status(message, kind = '') { statusEl.textContent = message; statusEl.className = `status ${kind}`; }
function updatePhrase() { phraseEl.textContent = phrase || '(empty)'; }

photo.addEventListener('change', () => {
  const file = photo.files?.[0];
  if (!file) return;
  preview.src = URL.createObjectURL(file);
  preview.hidden = false;
  recognizeButton.disabled = false;
  status('Photo ready. Tap “Read the kana”.');
});

recognizeButton.addEventListener('click', async () => {
  const file = photo.files?.[0];
  if (!file) return;
  recognizeButton.disabled = true;
  status('Reading handwriting…');
  try {
    const data = new FormData(); data.append('image', file);
    const response = await fetch('/api/recognize', {method: 'POST', body: data});
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || 'Could not read this image.');
    japanese.value = result.kana;
    readings.innerHTML = result.readings.length ? result.readings.map((r, i) =>
      `<div class="reading"><strong>${i + 1}. ${escapeHtml(r.kana)}</strong> · ${escapeHtml(r.pronunciation)} · ${Math.round(r.confidence * 100)}%<br><span class="hint">Other guesses: ${r.alternatives.slice(1).map(a => `${escapeHtml(a.kana)} ${Math.round(a.confidence * 100)}%`).join(' · ')}</span></div>`
    ).join('') : 'No kana found. Try a closer, brighter photo.';
    addButton.disabled = !japanese.value.trim();
    status(result.kana ? `Read ${result.readings.length} character(s). Check or edit the result.` : 'No kana found.', result.kana ? 'success' : '');
  } catch (error) { status(error.message, 'error'); }
  finally { recognizeButton.disabled = false; }
});

function escapeHtml(value) { return String(value).replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char])); }

japanese.addEventListener('input', () => { addButton.disabled = !japanese.value.trim(); });
addButton.addEventListener('click', () => {
  phrase += japanese.value.trim(); updatePhrase(); addButton.disabled = true;
  status('Added to your phrase.', 'success');
});
document.querySelector('#undo').addEventListener('click', () => { phrase = Array.from(phrase).slice(0, -1).join(''); updatePhrase(); });
document.querySelector('#clear').addEventListener('click', () => { phrase = ''; updatePhrase(); english.textContent = 'Translation will appear here.'; });

async function translate(text) {
  if (!text.trim()) { status('Enter or capture some Japanese first.', 'error'); return; }
  status('Translating…');
  try {
    const response = await fetch('/api/translate', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({text})});
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || 'Translation failed.');
    english.textContent = result.translation || '(No translation returned)';
    status('Translation ready.', 'success');
  } catch (error) { status(error.message, 'error'); }
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

let vocabulary = {};
let vocabIndex = 0;
let knownCount = Number(localStorage.getItem('sakura-vocab-known') || 0);
const vocabLevel = document.querySelector('#vocab-level');
const vocabWord = document.querySelector('#vocab-word');
const vocabReading = document.querySelector('#vocab-reading');
const vocabMeaning = document.querySelector('#vocab-meaning');
function showVocabCard() {
  const level = vocabLevel.value;
  const deck = vocabulary[level] || [];
  if (!deck.length) return;
  vocabIndex = ((vocabIndex % deck.length) + deck.length) % deck.length;
  const card = deck[vocabIndex];
  document.querySelector('#vocab-level-label').textContent = level;
  vocabWord.textContent = card.word;
  vocabReading.textContent = card.reading;
  vocabMeaning.textContent = card.meaning;
  vocabMeaning.hidden = true;
  document.querySelector('#vocab-reveal').textContent = 'Show meaning';
  document.querySelector('#vocab-progress').textContent = `Card ${vocabIndex + 1} of ${deck.length} · Known: ${knownCount}`;
}
fetch('/static/vocabulary.json').then(response => {
  if (!response.ok) throw new Error('Vocabulary list unavailable');
  return response.json();
}).then(data => { vocabulary = data; showVocabCard(); }).catch(() => {
  document.querySelector('#vocab-word').textContent = 'Vocabulary could not load.';
});
vocabLevel.addEventListener('change', () => { vocabIndex = 0; showVocabCard(); });
document.querySelector('#vocab-reveal').addEventListener('click', () => {
  vocabMeaning.hidden = false;
  document.querySelector('#vocab-reveal').textContent = 'Meaning shown';
});
document.querySelector('#vocab-next').addEventListener('click', () => { vocabIndex++; showVocabCard(); });
document.querySelector('#vocab-known').addEventListener('click', () => {
  knownCount++;
  localStorage.setItem('sakura-vocab-known', String(knownCount));
  vocabIndex++;
  showVocabCard();
});
document.querySelector('#speak').addEventListener('click', () => {
  const text = english.textContent;
  if (!text || text === 'Translation will appear here.' || !('speechSynthesis' in window)) {
    status('Speech is unavailable in this browser, or there is no translation yet.', 'error'); return;
  }
  window.speechSynthesis.cancel();
  const utterance = new SpeechSynthesisUtterance(text);
  utterance.lang = 'en-US';
  window.speechSynthesis.speak(utterance);
  status('Speaking English.', 'success');
});
