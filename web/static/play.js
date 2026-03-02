let gameId = null;
let board = null;
let winPos = null;
let lastMove = null;
let busy = false;

let currentUIMode = "pvp"; // pvp|vsai|iaia

const gridEl = document.getElementById("grid");
const boardTopEl = document.getElementById("boardTop");
const newGameBtn = document.getElementById("newGameBtn");
const statusEl = document.getElementById("status");
const seqEl = document.getElementById("seq");
const globalStatsEl = document.getElementById("globalStats");
const optionsEl = document.getElementById("options");

function setBusy(v){
  busy = v;
  newGameBtn.disabled = v;
  document.querySelectorAll("button.modeBtn").forEach(b => b.disabled = v);
  document.querySelectorAll("button.dropBtn").forEach(b => b.disabled = v);
}

function pieceClass(v){
  if (v === "R") return "red";
  if (v === "J") return "yellow";
  return "";
}

function dims(){
  const rows = board ? board.length : 0;
  const cols = (board && board[0]) ? board[0].length : 0;
  return { rows, cols };
}

function setSequence(seq){
  seqEl.textContent = (seq && seq.length) ? seq : "—";
}

function renderTopButtons(){
  boardTopEl.innerHTML = "";
  if (!board) return;
  const { cols } = dims();
  document.documentElement.style.setProperty("--cols", cols);

  for (let c = 0; c < cols; c++){
    const wrap = document.createElement("div");
    wrap.className = "colWrap";

    const btn = document.createElement("button");
    btn.className = "dropBtn";
    btn.textContent = "↓";
    btn.disabled = busy || (currentUIMode === "iaia") || !gameId;
    btn.addEventListener("click", () => playMove(c));

    wrap.appendChild(btn);
    boardTopEl.appendChild(wrap);
  }
}

function renderBoard(){
  if (!board) return;
  const { rows, cols } = dims();
  document.documentElement.style.setProperty("--cols", cols);

  gridEl.innerHTML = "";
  for (let r = 0; r < rows; r++){
    for (let c = 0; c < cols; c++){
      const cell = document.createElement("div");
      cell.className = "cell";

      const isWin = winPos && winPos.some(([lr, lc]) => lr === r && lc === c);
      if (isWin) cell.classList.add("win");

      const piece = document.createElement("div");
      piece.className = "piece " + pieceClass(board[r][c]);

      // animation uniquement sur le dernier pion joué
      if (lastMove && lastMove.row === r && lastMove.col === c) {
        piece.classList.add("drop");
      }

      cell.appendChild(piece);
      cell.addEventListener("click", () => playMove(c));

      gridEl.appendChild(cell);
    }
  }

  renderTopButtons();
}

async function loadStats(){
  try{
    const res = await fetch("/api/stats");
    const data = await res.json();
    if (!data.ok) throw new Error();
    globalStatsEl.textContent =
      `Parties: ${data.total} • Rouge: ${data.rouge} • Jaune: ${data.jaune} • Nuls: ${data.nuls} • En cours: ${data.en_cours}`;
  }catch{
    globalStatsEl.textContent = "Stats indisponibles";
  }
}

function renderOptions(){
  if (currentUIMode === "pvp"){
    optionsEl.innerHTML = `<div class="muted">PvP — ROUGE commence.</div>`;
    return;
  }

  if (currentUIMode === "vsai"){
    optionsEl.innerHTML = `
      <div class="row mt">
        <label class="muted">Tu joues
          <select id="humanColor" class="sel">
            <option value="R" selected>Rouge</option>
            <option value="J">Jaune</option>
          </select>
        </label>
        <label class="muted">IA
          <select id="aiType" class="sel">
            <option value="random">Aléatoire</option>
            <option value="minimax" selected>Minimax</option>
            <option value="bga">BGA</option>
          </select>
        </label>
        <label class="muted">Profondeur
          <input id="depth" class="sel" type="number" min="1" max="9" value="4" />
        </label>
        <label class="muted">Délai IA (ms)
          <input id="delay" class="sel" type="number" min="0" max="2000" value="350" />
        </label>
      </div>
    `;
    return;
  }

  optionsEl.innerHTML = `
    <div class="row mt">
      <label class="muted">IA Rouge
        <select id="aiR" class="sel">
          <option value="random">Aléatoire</option>
          <option value="minimax" selected>Minimax</option>
          <option value="bga">BGA</option>
        </select>
      </label>
      <label class="muted">IA Jaune
        <select id="aiJ" class="sel">
          <option value="random">Aléatoire</option>
          <option value="minimax">Minimax</option>
          <option value="bga" selected>BGA</option>
        </select>
      </label>
      <label class="muted">Profondeur
        <input id="depth" class="sel" type="number" min="1" max="9" value="4" />
      </label>
      <label class="muted">Délai (ms)
        <input id="delay" class="sel" type="number" min="0" max="2000" value="250" />
      </label>
      <button id="runBtn" class="btn">▶ Lancer IA/IA</button>
      <button id="stopBtn" class="btn secondary">⏹ Stop</button>
    </div>
  `;
  document.getElementById("runBtn").addEventListener("click", runIAIA);
  document.getElementById("stopBtn").addEventListener("click", () => { iaiaRunning = false; });
}

let iaiaRunning = false;

async function newGame(){
  if (busy) return;
  setBusy(true);

  try{
    winPos = null;
    lastMove = null;
    board = null;
    gameId = null;
    renderTopButtons();

    let url = "/new-game?";
    if (currentUIMode === "pvp"){
      url += "mode=pvp";
    } else if (currentUIMode === "vsai"){
      const humanColor = document.getElementById("humanColor")?.value || "R";
      const aiType = document.getElementById("aiType")?.value || "minimax";
      const depth = document.getElementById("depth")?.value || "4";
      const delay = document.getElementById("delay")?.value || "350";
      url += `mode=vsai&human_color=${encodeURIComponent(humanColor)}&ai_type=${encodeURIComponent(aiType)}&depth=${encodeURIComponent(depth)}&delay_ms=${encodeURIComponent(delay)}`;
    } else {
      const aiR = document.getElementById("aiR")?.value || "minimax";
      const aiJ = document.getElementById("aiJ")?.value || "bga";
      const depth = document.getElementById("depth")?.value || "4";
      const delay = document.getElementById("delay")?.value || "250";
      url += `mode=iaia&ai_r=${encodeURIComponent(aiR)}&ai_j=${encodeURIComponent(aiJ)}&depth=${encodeURIComponent(depth)}&delay_ms=${encodeURIComponent(delay)}`;
    }

    const res = await fetch(url, { method: "POST" });
    const data = await res.json();
    if (!data.ok){
      statusEl.textContent = data.error || "Erreur new-game";
      return;
    }

    gameId = data.game_id;
    board = data.plateau;
    setSequence(data.sequence || "");
    statusEl.textContent = "Partie prête — joue une colonne";

    if (data.auto?.ia_move !== undefined){
      statusEl.textContent = `L’IA commence (col ${data.auto.ia_move}) — à toi`;
    }

    renderBoard();
    await loadStats();
  } finally {
    setBusy(false);
  }
}

async function playMove(col){
  if (!gameId || busy) return;
  if (currentUIMode === "iaia") return;

  setBusy(true);
  try{
    const res = await fetch(`/move/${gameId}?col=${col}`, { method: "POST" });
    const data = await res.json();

    if (!data.ok){
      statusEl.textContent = data.error || "Erreur move";
      return;
    }

    board = data.plateau;
    winPos = data.win_pos || null;
    lastMove = data.last_move || null;

    setSequence(data.sequence || "");
    renderBoard();

    if (data.winner){
      statusEl.textContent = `🎉 Victoire ${data.winner}`;
      await loadStats();
      return;
    }
    if (data.draw){
      statusEl.textContent = "🤝 Match nul";
      await loadStats();
      return;
    }

    if (data.ia_move !== undefined && data.ia_move !== null){
      statusEl.textContent = `IA a joué col ${data.ia_move} — à toi`;
    } else if (data.next_player){
      statusEl.textContent = `À ${data.next_player} de jouer`;
    } else {
      statusEl.textContent = "—";
    }
  } finally {
    setBusy(false);
  }
}

async function stepIAIA(){
  const res = await fetch(`/step/${gameId}`, { method: "POST" });
  const data = await res.json();
  if (!data.ok){
    statusEl.textContent = data.error || "Erreur step";
    return { done: true };
  }
  board = data.plateau;
  winPos = data.win_pos || null;
  lastMove = data.last_move || null;
  setSequence(data.sequence || "");
  renderBoard();

  if (data.winner){
    statusEl.textContent = `🎉 Victoire ${data.winner}`;
    await loadStats();
    return { done: true };
  }
  if (data.draw){
    statusEl.textContent = "🤝 Match nul";
    await loadStats();
    return { done: true };
  }
  statusEl.textContent = `IA/IA — dernier coup col ${data.ai_move} — à ${data.next_player}`;
  return { done: false };
}

async function runIAIA(){
  if (!gameId || iaiaRunning) return;
  iaiaRunning = true;
  statusEl.textContent = "IA/IA en cours...";
  while (iaiaRunning){
    const { done } = await stepIAIA();
    if (done) { iaiaRunning = false; break; }
    await new Promise(r => setTimeout(r, 0));
  }
}

function setMode(mode){
  currentUIMode = mode;
  document.querySelectorAll("button.modeBtn").forEach(b => {
    b.classList.toggle("active", b.dataset.mode === mode);
  });
  gameId = null;
  board = null;
  winPos = null;
  lastMove = null;
  setSequence("");
  statusEl.textContent = "Clique sur “Nouvelle partie”.";
  renderOptions();
  renderTopButtons();
  gridEl.innerHTML = "";
}

document.querySelectorAll("button.modeBtn").forEach(b => {
  b.addEventListener("click", () => setMode(b.dataset.mode));
});

newGameBtn.addEventListener("click", newGame);

// init
renderOptions();
renderTopButtons();
loadStats();
