const state = { videoId: null, lines: [], drawing: null, pollTimer: null };
const $ = (selector) => document.querySelector(selector);
const videoInput = $('#videoInput');
const video = $('#video');
const canvas = $('#drawingCanvas');
const context = canvas.getContext('2d');

function toast(message) {
  const element = $('#toast'); element.textContent = message; element.classList.remove('hidden');
  window.setTimeout(() => element.classList.add('hidden'), 4500);
}

function stagePoint(event) {
  const rect = canvas.getBoundingClientRect();
  const clamp = value => Math.min(1, Math.max(0, value));
  return { x: clamp((event.clientX - rect.left) / rect.width), y: clamp((event.clientY - rect.top) / rect.height) };
}

function drawDirectionalArrow(origin, tip, color, label) {
  const angle = Math.atan2(tip.y - origin.y, tip.x - origin.x);
  context.strokeStyle = color; context.fillStyle = color; context.lineWidth = 3;
  context.beginPath(); context.moveTo(origin.x, origin.y); context.lineTo(tip.x, tip.y); context.stroke();
  context.beginPath(); context.moveTo(tip.x, tip.y);
  context.lineTo(tip.x - 11 * Math.cos(angle - Math.PI / 6), tip.y - 11 * Math.sin(angle - Math.PI / 6));
  context.lineTo(tip.x - 11 * Math.cos(angle + Math.PI / 6), tip.y - 11 * Math.sin(angle + Math.PI / 6));
  context.closePath(); context.fill();
  context.font = 'bold 14px system-ui'; context.fillText(label, tip.x + 6, tip.y - 5);
}

function drawArrow(line, color = '#00d49c') {
  const width = canvas.width, height = canvas.height;
  const a = { x: line.x1 * width, y: line.y1 * height };
  const b = { x: line.x2 * width, y: line.y2 * height };
  context.strokeStyle = color; context.lineWidth = Math.max(3, width / 350); context.lineCap = 'round';
  context.beginPath(); context.moveTo(a.x, a.y); context.lineTo(b.x, b.y); context.stroke();
  const dx = b.x - a.x, dy = b.y - a.y, length = Math.hypot(dx, dy) || 1;
  const mid = { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 };
  const normal = { x: -dy / length, y: dx / length };
  const positiveIsEntry = line.positive_direction === 'entrada';
  const positiveTip = { x: mid.x + normal.x * 42, y: mid.y + normal.y * 42 };
  const negativeTip = { x: mid.x - normal.x * 42, y: mid.y - normal.y * 42 };
  drawDirectionalArrow(mid, positiveTip, positiveIsEntry ? '#20d5a0' : '#ff922e', positiveIsEntry ? 'E' : 'S');
  drawDirectionalArrow(mid, negativeTip, positiveIsEntry ? '#ff922e' : '#20d5a0', positiveIsEntry ? 'S' : 'E');
}

function redraw() {
  context.clearRect(0, 0, canvas.width, canvas.height);
  state.lines.forEach(line => drawArrow(line));
  if (state.drawing) drawArrow({ ...state.drawing, positive_direction: 'entrada' }, '#ffffff');
}

function resizeCanvas() {
  if (!video.videoWidth) return;
  const rect = video.getBoundingClientRect();
  canvas.width = video.videoWidth; canvas.height = video.videoHeight;
  canvas.style.width = `${rect.width}px`; canvas.style.height = `${rect.height}px`;
  redraw();
}

function renderLines() {
  $('#lineCount').textContent = state.lines.length;
  $('#processButton').disabled = !state.videoId || state.lines.length === 0;
  const list = $('#lineList');
  if (!state.lines.length) { list.innerHTML = '<p class="empty-state">Aún no hay trazos.<br>Dibuja sobre el video.</p>'; redraw(); return; }
  list.innerHTML = state.lines.map((line, index) => `
    <div class="line-card" data-id="${line.id}">
      <div class="line-card-top"><i class="swatch"></i><input class="line-name" value="${escapeHtml(line.name)}" aria-label="Nombre del trazo"><button class="icon-button delete-line" title="Eliminar">×</button></div>
      <div class="direction-row"><span class="direction-badges"><b>→ E</b><b>← S</b></span><button type="button" class="swap-direction" title="Intercambiar entrada y salida">⇄ Invertir</button></div>
    </div>`).join('');
  list.querySelectorAll('.line-card').forEach(card => {
    const line = state.lines.find(item => item.id === card.dataset.id);
    card.querySelector('.line-name').addEventListener('input', e => { line.name = e.target.value; });
    card.querySelector('.swap-direction').addEventListener('click', () => { line.positive_direction = line.positive_direction === 'entrada' ? 'salida' : 'entrada'; redraw(); });
    card.querySelector('.delete-line').addEventListener('click', () => { state.lines = state.lines.filter(item => item.id !== line.id); renderLines(); });
  });
  redraw();
}

function escapeHtml(value) { const div = document.createElement('div'); div.textContent = value; return div.innerHTML; }

function apiError(data, fallback) {
  if (typeof data?.detail === 'string') return data.detail;
  if (Array.isArray(data?.detail)) {
    return data.detail.map(error => `${(error.loc || []).slice(1).join('.')}: ${error.msg}`).join(' · ');
  }
  return fallback;
}

fetch('/api/system').then(response => response.json()).then(system => {
  const labels = {mps:'GPU Apple Metal', cuda:'GPU CUDA', cpu:'CPU'};
  $('#systemStatus').textContent = `${labels[system.recommended_device]} disponible`;
  if (system.recommended_device === 'mps') $('#device').value = 'auto';
}).catch(() => { $('#systemStatus').textContent = 'Procesamiento local'; });

videoInput.addEventListener('change', async () => {
  const file = videoInput.files[0]; if (!file) return;
  $('#uploadTitle').textContent = 'Subiendo…'; $('#uploadHint').textContent = file.name;
  const body = new FormData(); body.append('video', file);
  try {
    const response = await fetch('/api/videos', { method: 'POST', body });
    const data = await response.json(); if (!response.ok) throw new Error(apiError(data, 'No fue posible subir el video'));
    state.videoId = data.video_id; state.lines = [];
    video.src = data.url; $('#workspace').classList.remove('hidden');
    $('#uploadTitle').textContent = file.name;
    $('#uploadHint').textContent = `${data.width}×${data.height} · ${data.fps} FPS · ${data.duration ?? '?'} s`;
    $('#workspace').scrollIntoView({ behavior: 'smooth', block: 'start' }); renderLines();
  } catch (error) { $('#uploadTitle').textContent = 'Seleccionar video'; toast(error.message); }
});

video.addEventListener('loadedmetadata', resizeCanvas); window.addEventListener('resize', resizeCanvas);
function formatTime(seconds) { const safe = Number.isFinite(seconds) ? seconds : 0; return `${String(Math.floor(safe/60)).padStart(2,'0')}:${String(Math.floor(safe%60)).padStart(2,'0')}`; }
video.addEventListener('loadedmetadata', () => { $('#videoTime').textContent = `00:00 / ${formatTime(video.duration)}`; });
video.addEventListener('timeupdate', () => { $('#timeline').value = video.duration ? Math.round(video.currentTime/video.duration*1000) : 0; $('#videoTime').textContent = `${formatTime(video.currentTime)} / ${formatTime(video.duration)}`; });
video.addEventListener('play', () => $('#playPause').textContent='❚❚'); video.addEventListener('pause', () => $('#playPause').textContent='▶');
$('#playPause').addEventListener('click', () => video.paused ? video.play() : video.pause());
$('#timeline').addEventListener('input', event => { if (video.duration) video.currentTime = Number(event.target.value)/1000*video.duration; });
canvas.addEventListener('pointerdown', event => { canvas.setPointerCapture(event.pointerId); const p = stagePoint(event); state.drawing = { x1:p.x, y1:p.y, x2:p.x, y2:p.y }; });
canvas.addEventListener('pointermove', event => { if (!state.drawing) return; const p = stagePoint(event); state.drawing.x2=p.x; state.drawing.y2=p.y; redraw(); });
canvas.addEventListener('pointerup', event => {
  if (!state.drawing) return; const p = stagePoint(event); state.drawing.x2=p.x; state.drawing.y2=p.y;
  if (Math.hypot(state.drawing.x2-state.drawing.x1, state.drawing.y2-state.drawing.y1) > .025) {
    state.lines.push({ ...state.drawing, id: crypto.randomUUID(), name:`Carretera ${state.lines.length+1}`, positive_direction:'entrada' });
    $('#canvasHelp').classList.add('hidden');
  }
  state.drawing=null; renderLines();
});
$('#clearLines').addEventListener('click', () => { state.lines=[]; renderLines(); });
$('#confidence').addEventListener('input', event => $('#confidenceOutput').value = event.target.value);
const presets = {
  aerial:{model:'best.pt', confidence:'0.10', imageSize:'1280', note:'Usa best.pt, entrenado con categorías de tráfico aéreo.'},
  balanced:{model:'yolo26n.pt', confidence:'0.10', imageSize:'1280', note:'Más rápido, pero puede omitir algunos vehículos pequeños.'},
  fast:{model:'yolo26n.pt', confidence:'0.20', imageSize:'640', note:'Solo para cámaras cercanas; no recomendado para este vuelo.'},
};
$('#preset').addEventListener('change', event => {
  const preset=presets[event.target.value]; $('#model').value=preset.model;
  $('#confidence').value=preset.confidence; $('#confidenceOutput').value=preset.confidence;
  $('#imageSize').value=preset.imageSize; $('#profileNote').textContent=preset.note;
});

$('#processButton').addEventListener('click', async () => {
  const processButton = $('#processButton');
  const classes = [...document.querySelectorAll('#classGrid input:checked')].map(input => input.value);
  if (!classes.length) return toast('Selecciona al menos una clase');
  if (state.lines.some(line => !line.name.trim())) return toast('Todos los trazos necesitan un nombre');
  const payload = {
    video_id:state.videoId,
    lines:state.lines.map(line => ({
      ...line,
      x1:Math.min(1, Math.max(0, line.x1)), y1:Math.min(1, Math.max(0, line.y1)),
      x2:Math.min(1, Math.max(0, line.x2)), y2:Math.min(1, Math.max(0, line.y2)),
    })),
    classes, model:$('#model').value,
    device:$('#device').value, confidence:Number($('#confidence').value),
    image_size:Number($('#imageSize').value), save_annotated_video:$('#saveVideo').checked,
  };
  try {
    processButton.disabled = true; processButton.innerHTML = 'Iniciando…';
    const response = await fetch('/api/jobs', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload) });
    const data = await response.json(); if (!response.ok) throw new Error(apiError(data, 'No fue posible iniciar'));
    processButton.innerHTML = 'Procesando…';
    $('#processing').classList.remove('hidden'); $('#results').classList.add('hidden');
    $('#processing').scrollIntoView({ behavior:'smooth' }); pollJob(data.job_id);
  } catch(error) {
    toast(error.message); processButton.disabled = false; processButton.innerHTML = 'Iniciar conteo <span>→</span>';
  }
});

async function pollJob(jobId) {
  window.clearTimeout(state.pollTimer);
  try {
    const response = await fetch(`/api/jobs/${jobId}`); const job = await response.json();
    if (!response.ok) throw new Error(job.detail || 'No se encontró el proceso');
    $('#processingMessage').textContent = job.message; $('#progressText').textContent = `${job.progress || 0}%`;
    $('#progressBar').style.width = `${job.progress || 0}%`;
    const speed = job.processing_fps ? ` · ${job.processing_fps} FPS en ${String(job.device).toUpperCase()}` : '';
    const tracking = job.unique_tracks !== undefined ? ` · ${job.active_tracks || 0} activos / ${job.unique_tracks} IDs` : '';
    $('#eventCount').textContent = `${job.events_count || 0} cruces${tracking}${speed}`;
    if (job.status === 'completado') return renderResults(job);
    if (job.status === 'error') throw new Error(job.message || 'Falló el procesamiento');
    state.pollTimer = window.setTimeout(() => pollJob(jobId), 1200);
  } catch(error) {
    toast(error.message); $('#processingMessage').textContent='El procesamiento se detuvo';
    $('#processButton').disabled=false; $('#processButton').innerHTML='Reintentar conteo <span>→</span>';
  }
}

function renderResults(job) {
  $('#processButton').disabled=false; $('#processButton').innerHTML='Procesar nuevamente <span>→</span>';
  $('#downloadCsv').href=job.csv; $('#downloadJson').href=job.json;
  const videoDownload = $('#downloadVideo');
  if (job.output_video) { videoDownload.href=job.output_video; videoDownload.classList.remove('hidden'); }
  else { videoDownload.removeAttribute('href'); videoDownload.classList.add('hidden'); }
  $('#resultCards').innerHTML = job.summary.map(line => `
    <article class="result-card"><header><strong>${escapeHtml(line.linea)}</strong><strong>${line.total} cruces</strong></header>
      <div class="result-columns">${['entrada','salida'].map(direction => `<div class="result-column"><h4>${direction}</h4>${Object.entries(line[direction]).map(([name,value]) => `<div class="metric"><span>${escapeHtml(name)}</span><b>${value}</b></div>`).join('')}</div>`).join('')}</div>
    </article>`).join('');
  $('#results').classList.remove('hidden'); $('#results').scrollIntoView({behavior:'smooth'});
}
