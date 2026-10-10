// YouTube Downloader Controller

let pollInterval = null;
let lastLogId = 0;
let isTerminalExpanded = false;
let currentAnalysis = null;

document.addEventListener('DOMContentLoaded', () => {
  initSystem();
  setupEventListeners();
  startStatusPolling();
});

// 1. Initial System Setup
async function initSystem() {
  try {
    const res = await fetch('/api/system');
    if (res.ok) {
      const data = await res.json();
      if (data.default_dest && !document.getElementById('input-dest').value) {
        document.getElementById('input-dest').value = data.default_dest;
      }
      if (data.free_gb !== undefined) {
        document.getElementById('side-free-gb').textContent = `${data.free_gb} GB Free`;
        document.getElementById('sb-free-space').textContent = `Free: ${data.free_gb} GB`;
      }
      if (data.ffmpeg_ok) {
        document.getElementById('side-ffmpeg').textContent = 'FFmpeg 7.1 Ready';
        document.getElementById('sb-ffmpeg').textContent = 'FFmpeg: Ready';
      }
    }
  } catch (e) {
    console.error("System init check failed:", e);
  }
}

// 2. Setup Event Listeners
function setupEventListeners() {
  const urlInput = document.getElementById('yt-url');
  const btnAnalyze = document.getElementById('btn-analyze');
  const btnDownload = document.getElementById('btn-download');
  const btnStop = document.getElementById('btn-stop');
  const selType = document.getElementById('sel-download-type');
  const btnClearLogs = document.getElementById('btn-clear-logs');
  const actionClearTerm = document.getElementById('action-clear-term');
  const actionToggleTerm = document.getElementById('action-toggle-term');

  // Format selection change
  selType.addEventListener('change', () => {
    const val = selType.value;
    const destInput = document.getElementById('input-dest');
    const badge = document.getElementById('sb-format-badge');

    if (val.startsWith('video_')) {
      if (destInput.value === 'e:\\deleteme\\songs') {
        destInput.value = 'e:\\deleteme\\videos';
      }
      const label = val.replace('video_', '').toUpperCase();
      badge.textContent = `🎬 Video (${label})`;
      appendTerminalLine('term-info', `[SELECTION] Option set to: Video (${label} MP4)`);
    } else {
      if (destInput.value === 'e:\\deleteme\\videos') {
        destInput.value = 'e:\\deleteme\\songs';
      }
      if (val === 'mp3_speaker') {
        badge.textContent = '📻 MP3 (Old Speaker Mode)';
        appendTerminalLine('term-info', '[SELECTION] Option set to: MP3 Old Speaker Mode (128k CBR, 44.1kHz).');
      } else {
        badge.textContent = `🎵 Audio (${val.toUpperCase()})`;
        appendTerminalLine('term-info', `[SELECTION] Option set to: Audio (${val.toUpperCase()})`);
      }
    }

    if (currentAnalysis) {
      updateEstimateDisplay(currentAnalysis);
    }
  });

  // Auto-analyze on paste
  urlInput.addEventListener('paste', () => {
    setTimeout(() => {
      if (urlInput.value.trim().length > 10) {
        triggerAnalyze();
      }
    }, 150);
  });

  // Analyze button
  btnAnalyze.addEventListener('click', triggerAnalyze);

  // Download & Stop buttons
  btnDownload.addEventListener('click', startDownload);
  btnStop.addEventListener('click', stopDownload);

  // Terminal actions
  btnClearLogs.addEventListener('click', clearTerminal);
  actionClearTerm.addEventListener('click', clearTerminal);
  actionToggleTerm.addEventListener('click', () => {
    const term = document.getElementById('terminal-panel');
    isTerminalExpanded = !isTerminalExpanded;
    term.style.height = isTerminalExpanded ? '400px' : '240px';
  });
}

// 3. Analyze Function
async function triggerAnalyze() {
  const url = document.getElementById('yt-url').value.trim();
  if (!url) {
    appendTerminalLine('term-error', '[ERROR] Please enter a YouTube link first.');
    return;
  }

  appendTerminalLine('term-info', `[ANALYSIS] Inspecting YouTube link: ${url} ...`);
  const btnAnalyze = document.getElementById('btn-analyze');
  btnAnalyze.disabled = true;
  btnAnalyze.textContent = 'Inspecting...';

  try {
    const res = await fetch('/api/analyze', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url })
    });
    if (!res.ok) {
      const err = await res.json();
      appendTerminalLine('term-error', `[ERROR] ${err.error || 'Failed to inspect link'}`);
    }
  } catch (e) {
    appendTerminalLine('term-error', `[ERROR] Network error: ${e.message}`);
  } finally {
    setTimeout(() => {
      btnAnalyze.disabled = false;
      btnAnalyze.textContent = 'Analyze';
    }, 1500);
  }
}

function updateEstimateDisplay(analysis) {
  const selVal = document.getElementById('sel-download-type').value;
  const anSize = document.getElementById('an-size');
  
  if (selVal.startsWith('video_')) {
    const est = (selVal === 'video_720' || selVal === 'video_480') ? analysis.estimates.video_720p : analysis.estimates.video_1080p;
    anSize.textContent = `${est} (Video MP4)`;
  } else if (selVal === 'mp3_192') {
    anSize.textContent = `${analysis.estimates.mp3_192k} (MP3 192k)`;
  } else if (selVal === 'mp3_320') {
    anSize.textContent = `${analysis.estimates.mp3_320k || analysis.estimates.mp3_192k} (MP3 320k)`;
  } else {
    anSize.textContent = `${analysis.estimates.mp3_128k} (MP3 128k)`;
  }
}

// 4. Start Download Function
async function startDownload() {
  const url = document.getElementById('yt-url').value.trim();
  if (!url) {
    appendTerminalLine('term-error', '[ERROR] Please paste a YouTube link before starting download.');
    document.getElementById('yt-url').focus();
    return;
  }

  const downloadType = document.getElementById('sel-download-type').value;
  const destDir = document.getElementById('input-dest').value.trim() || 'e:\\deleteme\\songs';
  const maxTracks = parseInt(document.getElementById('input-max-tracks').value) || 0;
  const ignoreDuplicates = document.getElementById('chk-ignore-dups').checked;

  const payload = {
    url,
    destDir,
    downloadType,
    maxTracks,
    maxSizeMb: 0,
    ignoreDuplicates
  };

  appendTerminalLine('term-system', `[DISPATCH] Starting download process...`);

  try {
    const res = await fetch('/api/download', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    if (res.ok) {
      setDownloadingUI(true);
    } else {
      const data = await res.json();
      appendTerminalLine('term-error', `[ERROR] ${data.error || 'Could not start download'}`);
    }
  } catch (e) {
    appendTerminalLine('term-error', `[ERROR] Failed: ${e.message}`);
  }
}

// 5. Stop Download Function
async function stopDownload() {
  appendTerminalLine('term-warn', `[USER] Sending stop command...`);
  try {
    await fetch('/api/stop', { method: 'POST' });
  } catch (e) {
    console.error("Stop error:", e);
  }
}

// 6. Polling Status & Logs
function startStatusPolling() {
  if (pollInterval) clearInterval(pollInterval);
  pollInterval = setInterval(async () => {
    try {
      const res = await fetch('/api/status');
      if (!res.ok) return;
      const data = await res.json();
      updateUI(data);
    } catch (e) {
      // Ignore polling errors
    }
  }, 750);
}

function updateUI(data) {
  const { state, status_message, progress, analysis, logs } = data;

  if (status_message) {
    document.getElementById('status-text').textContent = status_message;
    document.getElementById('sb-status-msg').textContent = status_message.length > 40 ? status_message.substring(0, 37) + '...' : status_message;
  }

  // Progress Bar
  const pct = progress.percent || 0;
  document.getElementById('progress-fill').style.width = `${Math.min(pct, 100)}%`;
  document.getElementById('stat-percent').textContent = `${Math.round(pct)}%`;
  document.getElementById('stat-speed').textContent = progress.speed || '';
  document.getElementById('stat-eta').textContent = progress.eta ? `ETA: ${progress.eta}` : '';

  // Analysis Bar display
  if (analysis) {
    currentAnalysis = analysis;
    const anBar = document.getElementById('analysis-bar');
    anBar.classList.remove('hidden');
    document.getElementById('an-title').textContent = analysis.title;
    document.getElementById('an-tracks').textContent = `${analysis.track_count} Items`;
    document.getElementById('an-time').textContent = analysis.duration_str;
    updateEstimateDisplay(analysis);
  }

  // UI state
  setDownloadingUI(state === 'downloading');

  // Logs stream
  if (logs && logs.length > 0) {
    logs.forEach(log => {
      if (log.id > lastLogId) {
        lastLogId = log.id;
        const clsMap = {
          info: 'term-info',
          download: 'term-download',
          success: 'term-success',
          warn: 'term-warn',
          error: 'term-error'
        };
        appendTerminalLine(clsMap[log.level] || 'term-info', `[${log.time}] [${log.level.toUpperCase()}] ${log.message}`);
      }
    });
  }
}

function setDownloadingUI(isDownloading) {
  const btnDownload = document.getElementById('btn-download');
  const btnStop = document.getElementById('btn-stop');
  if (isDownloading) {
    btnDownload.classList.add('hidden');
    btnStop.classList.remove('hidden');
  } else {
    btnDownload.classList.remove('hidden');
    btnStop.classList.add('hidden');
  }
}

function appendTerminalLine(className, text) {
  const screen = document.getElementById('terminal-screen');
  const div = document.createElement('div');
  div.className = `term-line ${className}`;
  div.textContent = text;
  screen.appendChild(div);
  screen.scrollTop = screen.scrollHeight;
}

function clearTerminal() {
  const screen = document.getElementById('terminal-screen');
  screen.innerHTML = `
    <div class="term-line term-system">[SYSTEM] Terminal logs cleared. Ready.</div>
  `;
}

function setDest(path) {
  document.getElementById('input-dest').value = path;
  appendTerminalLine('term-info', `[DESTINATION] Target folder set to: ${path}`);
}

function toggleSection(id) {
  const sec = document.getElementById(id);
  const chev = id === 'tree-folders' ? document.getElementById('chev-folders') : document.getElementById('chev-sys');
  if (sec.style.display === 'none') {
    sec.style.display = 'flex';
    chev.innerHTML = '&#9660;';
  } else {
    sec.style.display = 'none';
    chev.innerHTML = '&#9654;';
  }
}
