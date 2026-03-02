let gameId = null;
let board = null;
let winPos = null;
let busy = false;

let currentUIMode = "pvp"; // pvp|vsai|iaia

const gridEl = document.getElementById("grid");
const boardTopEl = document.getElementById("boardTop");
const newGameBtn = document.getElementById("newGameBtn");

const statusEl = document.getElementById("status");
const seqEl = document.getElementById("seq");
const predEl = document.getElementById("pred");
const hintEl = document.getElementById("hint");
const hintDetailsEl = document.getElementById("hintDetails");
const globalStatsEl = document.getElementById("globalStats");
const optionsEl = document.getElementById("options");

// Analyse situation
const seqInput = document.getElementById("seqInput");
const anDepth = document.getElementById("anDepth");
const anBtn = document.getElementById("anBtn");
const anRes = document.getElementById("anRes");
const pvEl = document.getElementById("pv");

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

function renderTopButtons(){
  boardTopEl.innerHTML = "";
  if (!board) return;
  const { cols } = dims();
  for (let c = 0; c < cols; c++){
    const btn = document.createElement("button");
    btn.className = "dropBtn";
    btn.textContent = "↓";
    btn.disabled = busy || (currentUIMode === "iaia");
    btn.addEventListener("click", () => playMove(c));
    boardTopEl.appendChild(btn);
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
      cell.appendChild(piece);
      cell.addEventListener("click", () => playMove(c));
      gridEl.appendChild(cell);
    }
  }
  renderTopButtons();
}

function setSequence(seq){
  seqEl.textContent = (seq && seq.length) ? seq : "—";
}

function labelToEmoji(l){
  if (l === "victoire") return "✅ victoire";
  if (l === "defaite") return "❌ défaite";
  if (l === "nul_ou_equilibre") return "🤝 nul/équilibré";
  return "❓ incertaine";
}

function renderPrediction(pred){
  if (!pred){ predEl.textContent = "—"; return; }
  predEl.textContent = `${labelToEmoji(pred.label)} (score ${pred.score}) — meilleur coup IA: ${pred.best_col}`;
}

function clearHint(){
  hintEl.textContent = "—";
  hintDetailsEl.innerHTML = "";
}

function renderHint(human_hint){
  clearHint();
  if (!human_hint) return;

  hintEl.textContent = `Meilleur coup conseillé: colonne ${human_hint.best_col}`;

  if (human_hint.type === "minimax"){
    const scores = human_hint.scores || {};
    const keys = Object.keys(scores).filter(k => scores[k] !== null).sort((a,b)=>Number(a)-Number(b));
    if (!keys.length) return;

    hintDetailsEl.innerHTML = `<div class="muted">Minimax (${labelToEmoji(human_hint.label)})</div>`;
    keys.forEach(k=>{
      const v = scores[k];
      const line = document.createElement("div");
      line.className = "weightLine";
      line.textContent = `Col ${k} : ${v}`;
      hintDetailsEl.appendChild(line);
    });
  } else if (human_hint.type === "bga"){
    const w = human_hint.weights || {};
    const keys = Object.keys(w).sort((a,b)=>Number(a)-Number(b));
    hintDetailsEl.innerHTML = `<div class="muted">BGA weights (matches=${human_hint.matches ?? 0})</div>`;
    if (!keys.length){
      const div = document.createElement("div");
      div.className = "muted";
      div.textContent = "Pas assez de données BGA, conseil fallback minimax faible.";
      hintDetailsEl.appendChild(div);
      return;
    }
    keys.forEach(k=>{
      const line = document.createElement("div");
      line.className = "weightLine";
      line.textContent = `Col ${k} : ${Number(w[k]).toFixed(2)}`;
      hintDetailsEl.appendChild(line);
    });
  }
}

async function loadStats(){
  try{
    const res = await fetch("/api/stats");
    const data = await res.json();
    if (!data.ok) throw new Error();
    globalStatsEl.textContent =
      `Parties: ${data.total} | Victoires R: ${data.rouge} | Victoires J: ${data.jaune} | Nuls: ${data.nuls}`;
  }catch{
    globalStatsEl.textContent = "Stats indisponibles";
  }
}

function renderOptions(){
  if (currentUIMode === "pvp"){
    optionsEl.innerHTML = `<div class="muted">PvP (humain vs humain) — ROUGE commence.</div>`;
    return;
  }

  if (currentUIMode === "vsai"){
    optionsEl.innerHTML = `
      <div class="optGrid">
        <label>Tu joues
          <select id="humanColor" class="sel">
            <option value="R" selected>Rouge</option>
            <option value="J">Jaune</option>
          </select>
        </label>
        <label>IA
          <select id="aiType" class="sel">
            <option value="random">Aléatoire</option>
            <option value="minimax" selected>Minimax</option>
            <option value="bga">BGA</option>
          </select>
        </label>
        <label>Profondeur minimax
          <input id="depth" class="inpSmall" type="number" min="1" max="9" value="4"/>
        </label>
        <label>Délai IA (ms)
          <input id="delay" class="inpSmall" type="number" min="0" max="2000" value="350"/>
        </label>
      </div>
    `;
    return;
  }

  // ia/ia
  optionsEl.innerHTML = `
    <div class="optGrid">
      <label>IA ROUGE
        <select id="aiR" class="sel">
          <option value="random">Aléatoire</option>
          <option value="minimax" selected>Minimax</option>
          <option value="bga">BGA</option>
        </select>
      </label>
      <label>IA JAUNE
        <select id="aiJ" class="sel">
          <option value="random">Aléatoire</option>
          <option value="minimax">Minimax</option>
          <option value="bga" selected>BGA</option>
        </select>
      </label>
      <label>Profondeur minimax
        <input id="depth" class="inpSmall" type="number" min="1" max="9" value="4"/>
      </label>
      <label>Délai (ms)
        <input id="delay" class="inpSmall" type="number" min="0" max="2000" value="250"/>
      </label>
      <button id="runBtn" class="btn">▶ Lancer IA/IA</button>
      <button id="stopBtn" class="btn">⏹ Stop</button>
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
    winPos = null;

    statusEl.textContent = `Partie ${gameId} — prête`;
    setSequence(data.sequence || "");
    renderPrediction(null);

    if (data.auto?.ia_move !== undefined){
      statusEl.textContent = `L’IA commence (col ${data.auto.ia_move}) — à toi de jouer`;
    }

    renderHint(data.human_hint);
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

    setSequence(data.sequence || "");
    renderPrediction(data.prediction_ai || null);
    renderHint(data.human_hint || null);
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

    if (data.ia_move !== undefined){
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
  setSequence(data.sequence || "");
  renderPrediction(null);
  clearHint();
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
  statusEl.textContent = `IA/IA — coup ${data.ai_move} — à ${data.next_player}`;
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

async function analyzeSituation(){
  const seq = (seqInput.value || "").trim();
  const d = Number(anDepth.value || 6);

  const res = await fetch(`/api/analyze?sequence=${encodeURIComponent(seq)}&depth=${encodeURIComponent(d)}`);
  const data = await res.json();
  if (!data.ok){
    anRes.textContent = data.error || "Erreur";
    pvEl.innerHTML = "";
    return;
  }

  anRes.textContent = `Joueur à jouer: ${data.joueur_a_jouer} — meilleur coup: ${data.best_col} — ${labelToEmoji(data.label)} (score ${data.score_best})`;
  pvEl.innerHTML = "";

  const pv = data.pv || [];
  if (!pv.length){
    pvEl.innerHTML = `<div class="muted">Pas de ligne trouvée (augmente la profondeur).</div>`;
    return;
  }

  pv.forEach((m,i)=>{
    const line = document.createElement("div");
    line.className = "weightLine";
    line.textContent = `#${i+1} ${m.joueur} -> col ${m.col} (score ${m.score})`;
    pvEl.appendChild(line);
  });
}

anBtn.addEventListener("click", analyzeSituation);

function setMode(mode){
  currentUIMode = mode;
  document.querySelectorAll("button.modeBtn").forEach(b => {
    b.classList.toggle("active", b.dataset.mode === mode);
  });
  renderOptions();
}

document.querySelectorAll("button.modeBtn").forEach(b => {
  b.addEventListener("click", () => setMode(b.dataset.mode));
});

newGameBtn.addEventListener("click", newGame);

// init
renderOptions();
loadStats();
newGame();
