let gameId = null;
let board = null;
let winPos = null;
let lastMove = null;
let busy = false;

let currentUIMode = "pvp";
let editorEnabled = false;
let iaiaRunning = false;

const gridEl = document.getElementById("grid");
const boardTopEl = document.getElementById("boardTop");
const newGameBtn = document.getElementById("newGameBtn");
const statusEl = document.getElementById("status");
const seqEl = document.getElementById("seq");
const globalStatsEl = document.getElementById("globalStats");
const optionsEl = document.getElementById("options");
const modeSummaryEl = document.getElementById("modeSummary");
const boardHintEl = document.getElementById("boardHint");

const verdictEl = document.getElementById("verdict");
const bestMoveEl = document.getElementById("bestMove");
const pvLineEl = document.getElementById("pvLine");
const analysisDepthEl = document.getElementById("analysisDepth");
const assistHumanEl = document.getElementById("assistHuman");

const seqInputEl = document.getElementById("seqInput");

if (seqInputEl && !seqInputEl.value) {
  seqInputEl.value = "7,7,3,3,3,4,2,4,4,2,2,6";
}

const seqPlayerEl = document.getElementById("seqPlayer");
const analyzeSeqBtn = document.getElementById("analyzeSeqBtn");

const toggleEditorBtn = document.getElementById("toggleEditorBtn");
const analyzeBoardBtn = document.getElementById("analyzeBoardBtn");
const clearBoardBtn = document.getElementById("clearBoardBtn");
const resumeBoardBtn = document.getElementById("resumeBoardBtn");
const resumeNextPlayerEl = document.getElementById("resumeNextPlayer");
const resumeModeEl = document.getElementById("resumeMode");

let lastAnalysis = null;

function escapeHtml(s){
  return String(s ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function statCard(label, value, hint = ""){
  return `
    <div class="statBox">
      <div class="statLabel">${escapeHtml(label)}</div>
      <div class="statValue">${escapeHtml(value)}</div>
      <div class="statHint">${escapeHtml(hint)}</div>
    </div>
  `;
}

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

function setAnalysisUIEmpty(){
  verdictEl.textContent = "—";
  bestMoveEl.textContent = "—";
  pvLineEl.textContent = "";
  lastAnalysis = null;
  applyAnalysisToUI();
}

function updateModeSummary(data = null){
  if (data?.mode_summary){
    const m = data.mode_summary;
    modeSummaryEl.textContent = `Mode actuel : ${m.mode} — ${m.detail} — Tour : ${m.turn}`;
    return;
  }

  if (currentUIMode === "pvp"){
    modeSummaryEl.textContent = "Mode actuel : Joueur contre joueur";
  } else if (currentUIMode === "vsai"){
    const humanColor = document.getElementById("humanColor")?.value || "R";
    const aiType = document.getElementById("aiType")?.value || "minimax";
    const aiColor = humanColor === "R" ? "J" : "R";
    modeSummaryEl.textContent = `Mode actuel : Joueur contre ordinateur — Tu joues : ${humanColor} — IA : ${aiColor} (${aiType})`;
  } else {
    const aiR = document.getElementById("aiR")?.value || "minimax";
    const aiJ = document.getElementById("aiJ")?.value || "minimax";
    modeSummaryEl.textContent = `Mode actuel : Demonstration Auto — Rouge contre Jaune`;
  }
}

function normalizeScore(v){
  if (v === null || v === undefined) return {h:0, neg:false};
  const x = Math.max(-100000, Math.min(100000, Number(v)));
  const h = Math.round((Math.abs(x) / 100000) * 100);
  return {h, neg: x < 0};
}

function applyAnalysisToUI(){
  document.querySelectorAll(".colWrap").forEach(w => w.classList.remove("best"));

  if (!lastAnalysis || !lastAnalysis.scores) return;

  const scores = lastAnalysis.scores;
  const bestCol = lastAnalysis.best_col;

  for (let c = 0; c < scores.length; c++){
    const wrap = boardTopEl.querySelector(`.colWrap[data-col="${c}"]`);
    if (!wrap) continue;
    const bar = wrap.querySelector(".weightBar");
    if (!bar) continue;

    const val = scores[c];
    if (val === null){
      bar.style.height = "0%";
      bar.classList.remove("neg");
      continue;
    }

    const {h, neg} = normalizeScore(val);
    bar.style.height = `${Math.max(8, h)}%`;
    bar.classList.toggle("neg", neg);
  }

  if (bestCol !== null && bestCol !== undefined){
    const bw = boardTopEl.querySelector(`.colWrap[data-col="${bestCol}"]`);
    if (bw) bw.classList.add("best");
  }

  const predictedWinner = lastAnalysis.predicted_winner;
  const movesToWin = lastAnalysis.moves_to_win;

  verdictEl.textContent = lastAnalysis.verdict || "—";

  if (predictedWinner && movesToWin !== null && movesToWin !== undefined) {
    verdictEl.textContent += ` — Gagnant prédit : ${predictedWinner} — Victoire estimée en ${movesToWin} coup(s)`;
  } else if (predictedWinner) {
    verdictEl.textContent += ` — Gagnant prédit : ${predictedWinner}`;
  }

  bestMoveEl.textContent = (bestCol === null || bestCol === undefined) ? "—" : String(bestCol);

  if (lastAnalysis.existing_winner){
    pvLineEl.textContent = `Victoire déjà présente pour ${lastAnalysis.existing_winner}`;
  } else if (lastAnalysis.pv && lastAnalysis.pv.length){
    const pvText = lastAnalysis.pv
      .map(step => typeof step === "object" ? `${step.joueur}:${step.col}` : String(step))
      .join(" → ");
    pvLineEl.textContent = `Ligne proposée : ${pvText}`;
  } else {
    pvLineEl.textContent = "";
  }
}

async function fetchAnalysis(){
  if (!gameId || !board) return;

  const depth = Number(analysisDepthEl?.value || 4);

  let forPlayer = "R";
  if (currentUIMode === "vsai" && assistHumanEl?.checked){
    forPlayer = document.getElementById("humanColor")?.value || "R";
  }

  try{
    const res = await fetch(`/api/analyze/${gameId}?for_player=${encodeURIComponent(forPlayer)}&depth=${encodeURIComponent(depth)}`);
    const data = await res.json();
    if (!data.ok) return;

    lastAnalysis = data;
    if (data.winning_cells){
      winPos = data.winning_cells;
    }
    applyAnalysisToUI();
  }catch{}
}

function renderTopButtons(){
  boardTopEl.innerHTML = "";
  if (!board) return;
  const { cols } = dims();
  document.documentElement.style.setProperty("--cols", cols);

  for (let c = 0; c < cols; c++){
    const wrap = document.createElement("div");
    wrap.className = "colWrap";
    wrap.dataset.col = String(c);

    const btn = document.createElement("button");
    btn.className = "dropBtn";
    btn.textContent = "↓";
    btn.disabled = busy || (currentUIMode === "iaia") || !gameId || editorEnabled;
    btn.addEventListener("click", () => playMove(c));

    const barWrap = document.createElement("div");
    barWrap.className = "weightBarWrap";

    const bar = document.createElement("div");
    bar.className = "weightBar";
    bar.style.height = "0%";
    barWrap.appendChild(bar);

    wrap.appendChild(btn);
    wrap.appendChild(barWrap);
    boardTopEl.appendChild(wrap);
  }

  applyAnalysisToUI();
}

function cellCycleValue(v){
  if (v === ".") return "R";
  if (v === "R") return "J";
  return ".";
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
      cell.dataset.r = String(r);
      cell.dataset.c = String(c);

      const isWin = winPos && winPos.some(([lr, lc]) => lr === r && lc === c);
      if (isWin) cell.classList.add("win");

      const piece = document.createElement("div");
      piece.className = "piece " + pieceClass(board[r][c]);

      if (lastMove && lastMove.row === r && lastMove.col === c) {
        piece.classList.add("drop");
      }

      cell.appendChild(piece);

      cell.addEventListener("click", async () => {
        if (editorEnabled){
          board[r][c] = cellCycleValue(board[r][c]);
          lastMove = null;
          winPos = null;
          renderBoard();
          return;
        }
        await playMove(c);
      });

      gridEl.appendChild(cell);
    }
  }

  renderTopButtons();
}

async function loadStats(){
  const el = document.getElementById("globalStats");
  if (!el) return;

  el.innerHTML = "Chargement...";

  try{
    const res = await fetch("/api/stats");
    const data = await res.json();

    if (!data.ok){
      el.textContent = data.error || "Erreur de chargement";
      return;
    }

    el.innerHTML = `
      ${statCard("Parties totales", String(data.total ?? 0), "Toutes les parties enregistrées")}
      ${statCard("Victoires Rouge", String(data.rouge ?? 0), "Parties gagnées par Rouge")}
      ${statCard("Victoires Jaune", String(data.jaune ?? 0), "Parties gagnées par Jaune")}
      ${statCard("Matchs nuls", String(data.nuls ?? 0), "Parties terminées sans gagnant")}
      ${statCard("En cours", String(data.en_cours ?? 0), "Parties non terminées")}
    `;
  } catch (e){
    el.textContent = "Erreur de chargement des statistiques";
  }
}

function renderOptions(){
  if (currentUIMode === "pvp"){
    optionsEl.innerHTML = `
      <div class="settingsGrid">
        <div class="settingCard">
          <div class="settingTitle">Mode</div>
          <div class="muted">Deux joueurs humains, Rouge commence.</div>
        </div>
      </div>
    `;
    updateModeSummary();
    return;
  }

  if (currentUIMode === "vsai"){
    optionsEl.innerHTML = `
      <div class="settingsGrid">
        <div class="settingCard">
          <label class="muted">Tu joues
            <select id="humanColor" class="sel">
              <option value="R" selected>Rouge</option>
              <option value="J">Jaune</option>
            </select>
          </label>
        </div>
        <div class="settingCard">
          <label class="muted"> Adversaire
            <select id="aiType" class="sel">
              <option value="random">Aléatoire</option>
              <option value="minimax" selected>Minimax</option>
              <option value="bga">BGA</option>
            </select>
          </label>
        </div>
        <div class="settingCard">
          <label class="muted">Profondeur
            <input id="depth" class="sel" type="number" min="1" max="9" value="4" />
          </label>
        </div>
      </div>
    `;
    optionsEl.querySelectorAll("select,input").forEach(el => {
      el.addEventListener("change", () => updateModeSummary());
    });
    updateModeSummary();
    return;
  }

  optionsEl.innerHTML = `
    <div class="settingsGrid">
      <div class="settingCard">
        <label class="muted">Rouge
          <select id="aiR" class="sel">
            <option value="random">Aléatoire</option>
            <option value="minimax" selected>Minimax</option>
            <option value="bga">BGA</option>
          </select>
        </label>
      </div>
      <div class="settingCard">
        <label class="muted">Jaune
          <select id="aiJ" class="sel">
            <option value="random">Aléatoire</option>
            <option value="minimax" selected>Minimax</option>
            <option value="bga">BGA</option>
          </select>
        </label>
      </div>
      <div class="settingCard">
        <label class="muted">Profondeur
          <input id="depth" class="sel" type="number" min="1" max="9" value="4" />
        </label>
      </div>
      <div class="settingCard settingActions">
        <button id="runBtn" class="btn">▶ Lancer la demonstration</button>
        <button id="stopBtn" class="btn secondary">⏹ Stop</button>
      </div>
    </div>
  `;

  document.getElementById("runBtn").addEventListener("click", runIAIA);
  document.getElementById("stopBtn").addEventListener("click", () => { iaiaRunning = false; });
  optionsEl.querySelectorAll("select,input").forEach(el => {
    el.addEventListener("change", () => updateModeSummary());
  });
  updateModeSummary();
}

async function newGame(){
  if (busy) return;
  setBusy(true);

  try{
    editorEnabled = false;
    toggleEditorBtn.textContent = "Activer l’éditeur";

    winPos = null;
    lastMove = null;
    board = null;
    gameId = null;
    setAnalysisUIEmpty();
    renderTopButtons();

    let url = "/new-game?";
    if (currentUIMode === "pvp"){
      url += "mode=pvp";
    } else if (currentUIMode === "vsai"){
        const humanColor = document.getElementById("humanColor")?.value || "R";
        const aiType = document.getElementById("aiType")?.value || "minimax";
        const depth = document.getElementById("depth")?.value || "4";
        url += `mode=vsai&human_color=${encodeURIComponent(humanColor)}&ai_type=${encodeURIComponent(aiType)}&depth=${encodeURIComponent(depth)}&delay_ms=0`;
    } else {
      const aiR = document.getElementById("aiR")?.value || "minimax";
      const aiJ = document.getElementById("aiJ")?.value || "minimax";
      const depth = document.getElementById("depth")?.value || "4";
      url += `mode=iaia&ai_r=${encodeURIComponent(aiR)}&ai_j=${encodeURIComponent(aiJ)}&depth=${encodeURIComponent(depth)}&delay_ms=0`;
    }

    const res = await fetch(url, { method: "POST" });
    const data = await res.json();
    if (!data.ok){
      statusEl.textContent = data.error || "Erreur nouvelle partie";
      return;
    }

    gameId = data.game_id;
    board = data.plateau;
    setSequence(data.sequence || "");
    updateModeSummary(data);
    boardHintEl.textContent = "Tu peux jouer";
    if (currentUIMode === "vsai"){
      const humanColor = document.getElementById("humanColor")?.value || "R";
      if (data.auto?.ia_move !== undefined){
        statusEl.textContent = "L’Ia a joué. À toi";
      } else if (humanColor === "R"){
        statusEl.textContent = "À toi de jouer";
      } else {
        statusEl.textContent = "L’Ia réfléchit...";
      }
    } else {
      statusEl.textContent = "Partie prête.";
    }

    renderBoard();
    await loadStats();
    await fetchAnalysis();
  } finally {
    setBusy(false);
  }
}

async function maybeRunAIAfterHuman(){
  if (!gameId || currentUIMode !== "vsai") return;

  const humanColor = document.getElementById("humanColor")?.value || "R";
  const aiColor = humanColor === "R" ? "J" : "R";

  if (statusEl.textContent.includes(`À ${aiColor} de jouer`) || statusEl.textContent.includes("L’Ia réfléchit")){
    statusEl.textContent = "L’Ia réfléchit...";
    setBusy(true);
    try{
      
      
      const res = await fetch(`/ai-move/${gameId}`, { method: "POST" });
      const data = await res.json();

      if (!data.ok){
        statusEl.textContent = data.error || "Erreur Ia";
        return;
      }

      board = data.plateau;
      winPos = data.win_pos || null;
      lastMove = data.last_move || null;
      setSequence(data.sequence || "");
      updateModeSummary(data);

      renderBoard();
      await fetchAnalysis();

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

      statusEl.textContent = "À toi de jouer";
    } finally {
      setBusy(false);
    }
  }
}

async function playMove(col){
  if (!gameId || busy) return;
  if (currentUIMode === "iaia") return;
  if (editorEnabled) return;

  setBusy(true);
  try{
    const res = await fetch(`/move/${gameId}?col=${col}`, { method: "POST" });
    const data = await res.json();

    if (!data.ok){
      statusEl.textContent = data.error || "Erreur coup";
      return;
    }

    board = data.plateau;
    winPos = data.win_pos || null;
    lastMove = data.last_move || null;
    setSequence(data.sequence || "");
    updateModeSummary(data);

    renderBoard();
    await fetchAnalysis();

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

    if (currentUIMode === "vsai"){
      const humanColor = document.getElementById("humanColor")?.value || "R";
      const aiColor = humanColor === "R" ? "J" : "R";

      if (data.next_player === aiColor){
        statusEl.textContent = "L’Ia réfléchit...";
      } else if (data.next_player === humanColor){
        statusEl.textContent = "À toi de jouer";
      } else {
        statusEl.textContent = "—";
      }
    } else {
      if (data.next_player){
        statusEl.textContent = `À ${data.next_player} de jouer`;
      } else {
        statusEl.textContent = "—";
      }
    }
  } finally {
    setBusy(false);
  }

  await maybeRunAIAfterHuman();
}

async function runIAIA(){
  if (!gameId || currentUIMode !== "iaia") return;

  iaiaRunning = true;
  statusEl.textContent = "Démonstration en cours...";

  while (iaiaRunning){
    const res = await fetch(`/step/${gameId}`, { method: "POST" });
    const data = await res.json();

    if (!data.ok){
      statusEl.textContent = data.error || "Erreur";
      iaiaRunning = false;
      break;
    }

    board = data.plateau;
    winPos = data.win_pos || null;
    lastMove = data.last_move || null;
    setSequence(data.sequence || "");
    updateModeSummary(data);

    renderBoard();
    await fetchAnalysis();

    if (data.winner){
      statusEl.textContent = data.winner === "R"
        ? "🎉 Victoire du joueur Rouge"
        : "🎉 Victoire du joueur Jaune";
      iaiaRunning = false;
      await loadStats();
      break;
    }

    if (data.draw){
      statusEl.textContent = "🤝 Match nul";
      iaiaRunning = false;
      await loadStats();
      break;
    }

    await new Promise(requestAnimationFrame);
  }
}

async function switchModeKeepBoard(mode){
  currentUIMode = mode;
  document.querySelectorAll("button.modeBtn").forEach(b => {
    b.classList.toggle("active", b.dataset.mode === mode);
  });

  renderOptions();

  if (!gameId || !board || editorEnabled){
    updateModeSummary();
    return;
  }

  let url = `/switch-mode/${gameId}?`;
  if (mode === "pvp"){
    url += `mode=pvp&depth=4&delay_ms=0`;
  } else if (mode === "vsai"){
    const humanColor = document.getElementById("humanColor")?.value || "R";
    const aiType = document.getElementById("aiType")?.value || "minimax";
    const depth = document.getElementById("depth")?.value || "4";
    url += `mode=vsai&human_color=${encodeURIComponent(humanColor)}&ai_type=${encodeURIComponent(aiType)}&depth=${encodeURIComponent(depth)}&delay_ms=0`;
  } else {
    const aiR = document.getElementById("aiR")?.value || "minimax";
    const aiJ = document.getElementById("aiJ")?.value || "minimax";
    const depth = document.getElementById("depth")?.value || "4";
    url += `mode=iaia&ai_r=${encodeURIComponent(aiR)}&ai_j=${encodeURIComponent(aiJ)}&depth=${encodeURIComponent(depth)}&delay_ms=0`;
  }

  setBusy(true);
  try{
    const res = await fetch(url, { method: "POST" });
    const data = await res.json();

    if (!data.ok){
      statusEl.textContent = data.error || "Erreur changement de mode";
      return;
    }

    board = data.plateau;
    winPos = data.win_pos || null;
    lastMove = data.last_move || null;
    setSequence(data.sequence || "");
    updateModeSummary(data);
    renderBoard();
    await fetchAnalysis();

    statusEl.textContent = `Mode changé : ${mode === "pvp" ? "Humain vs Humain" : mode === "vsai" ? "Humain vs IA" : "IA vs IA"} (plateau conservé)`;

    if (mode === "vsai"){
      const humanColor = document.getElementById("humanColor")?.value || "R";
      const aiColor = humanColor === "R" ? "J" : "R";
      if (data.next_player === aiColor){
        await maybeRunAIAfterHuman();
      }
    }
  } finally {
    setBusy(false);
  }
}

async function analyzeSequence(){
  const seq = (seqInputEl?.value || "").trim();
  const p = seqPlayerEl?.value || "R";
  const depth = Number(analysisDepthEl?.value || 5);

  try{
    const res = await fetch(`/api/analyze_sequence?sequence=${encodeURIComponent(seq)}&for_player=${encodeURIComponent(p)}&depth=${encodeURIComponent(depth)}`);
    const data = await res.json();
    if (!data.ok){
      statusEl.textContent = data.error || "Erreur analyse séquence";
      return;
    }

    gameId = null;
    editorEnabled = false;
    toggleEditorBtn.textContent = "Activer l’éditeur";

    board = data.plateau;
    winPos = data.winning_cells || null;
    lastMove = null;
    lastAnalysis = data;

    setSequence(data.sequence_applied || "");
    updateModeSummary();
    let extraPrediction = "";
    if (data.predicted_winner && data.moves_to_win !== null && data.moves_to_win !== undefined) {
      extraPrediction = ` — Gagnant prédit : ${data.predicted_winner} — Victoire estimée en ${data.moves_to_win} coup(s)`;
    } else if (data.predicted_winner) {
      extraPrediction = ` — Gagnant prédit : ${data.predicted_winner}`;
    }

    statusEl.textContent = `Analyse OK — Verdict : ${data.verdict}${extraPrediction}${data.best_col !== null && data.best_col !== undefined ? ` — Meilleur coup : ${data.best_col}` : ""}`;
    
    
    boardHintEl.textContent = "Position chargée depuis une séquence.";
    renderBoard();
  }catch{
    statusEl.textContent = "Erreur réseau";
  }
}

function emptyBoard(rows, cols){
  return Array.from({length: rows}, () => Array.from({length: cols}, () => "."));
}

async function analyzeBoard(){
  if (!board) return;
  const p = seqPlayerEl?.value || "R";
  const depth = Number(analysisDepthEl?.value || 5);

  try{
    const res = await fetch(`/api/analyze_board?for_player=${encodeURIComponent(p)}&depth=${encodeURIComponent(depth)}`, {
      method: "POST",
      headers: {"Content-Type":"application/json"},
      body: JSON.stringify(board),
    });
    const data = await res.json();
    if (!data.ok){
      statusEl.textContent = data.error || "Erreur analyse plateau";
      return;
    }

    lastAnalysis = data;
    winPos = data.winning_cells || null;
    let extraPrediction = "";
    if (data.predicted_winner && data.moves_to_win !== null && data.moves_to_win !== undefined) {
      extraPrediction = ` — Gagnant prédit : ${data.predicted_winner} — Victoire estimée en ${data.moves_to_win} coup(s)`;
    } else if (data.predicted_winner) {
      extraPrediction = ` — Gagnant prédit : ${data.predicted_winner}`;
    }

    statusEl.textContent = `Analyse plateau — Verdict : ${data.verdict}${extraPrediction}${data.best_col !== null && data.best_col !== undefined ? ` — Meilleur coup : ${data.best_col}` : ""}`;
    
    boardHintEl.textContent = "Plateau édité analysé.";
    renderBoard();
  }catch{
    statusEl.textContent = "Erreur réseau";
  }
}

function toggleEditor(){
  if (!board){
    board = emptyBoard(9, 9);
  }

  editorEnabled = !editorEnabled;
  toggleEditorBtn.textContent = editorEnabled ? "Désactiver l’éditeur" : "Activer l’éditeur";
  statusEl.textContent = editorEnabled
    ? "Éditeur actif : clique les cases (R → J → vide), puis analyse ou reprends la position."
    : "Éditeur désactivé.";
  boardHintEl.textContent = editorEnabled
    ? "Mode édition du plateau."
    : "Mode jeu normal.";
  renderTopButtons();
}

function clearBoard(){
  const {rows, cols} = dims();
  board = emptyBoard(rows || 9, cols || 9);
  winPos = null;
  lastMove = null;
  setSequence("");
  setAnalysisUIEmpty();
  boardHintEl.textContent = "Plateau vidé.";
  renderBoard();
}

async function resumeBoard(){
  if (!board) return;

  const mode = resumeModeEl.value || "pvp";
  const nextPlayer = resumeNextPlayerEl.value || "R";

  let url = `/start-from-board?mode=${encodeURIComponent(mode)}&next_player=${encodeURIComponent(nextPlayer)}`;

  if (mode === "pvp"){
    url += `&depth=4&delay_ms=0`;
  } else if (mode === "vsai"){
    const humanColor = document.getElementById("humanColor")?.value || "R";
    const aiType = document.getElementById("aiType")?.value || "minimax";
    const depth = document.getElementById("depth")?.value || "4";
    url += `&human_color=${encodeURIComponent(humanColor)}&ai_type=${encodeURIComponent(aiType)}&depth=${encodeURIComponent(depth)}&delay_ms=0`;
  } else if (mode === "iaia"){
    const aiR = document.getElementById("aiR")?.value || "minimax";
    const aiJ = document.getElementById("aiJ")?.value || "minimax";
    const depth = document.getElementById("depth")?.value || "4";
    url += `&ai_r=${encodeURIComponent(aiR)}&ai_j=${encodeURIComponent(aiJ)}&depth=${encodeURIComponent(depth)}&delay_ms=0`;
  }

  setBusy(true);
  try{
    const res = await fetch(url, {
      method: "POST",
      headers: {"Content-Type":"application/json"},
      body: JSON.stringify(board),
    });
    const data = await res.json();

    if (!data.ok){
      statusEl.textContent = data.error || "Impossible de reprendre cette position";
      return;
    }

    currentUIMode = mode;
    document.querySelectorAll("button.modeBtn").forEach(b => {
      b.classList.toggle("active", b.dataset.mode === mode);
    });
    renderOptions();

    gameId = data.game_id;
    board = data.plateau;
    editorEnabled = false;
    toggleEditorBtn.textContent = "Activer l’éditeur";
    updateModeSummary(data);
    boardHintEl.textContent = "Partie reprise depuis l’éditeur.";
    statusEl.textContent = "Position reprise avec succès.";
    renderBoard();
    await fetchAnalysis();

    if (mode === "vsai"){
      const humanColor = document.getElementById("humanColor")?.value || "R";
      const aiColor = humanColor === "R" ? "J" : "R";
      if (data.mode_summary?.turn === aiColor){
        await maybeRunAIAfterHuman();
      }
    }
  } finally {
    setBusy(false);
  }
}

document.querySelectorAll("button.modeBtn").forEach(b => {
  b.addEventListener("click", () => switchModeKeepBoard(b.dataset.mode));
});

newGameBtn.addEventListener("click", newGame);
analyzeSeqBtn.addEventListener("click", analyzeSequence);

toggleEditorBtn.addEventListener("click", toggleEditor);
analyzeBoardBtn.addEventListener("click", analyzeBoard);
clearBoardBtn.addEventListener("click", clearBoard);
resumeBoardBtn.addEventListener("click", resumeBoard);

analysisDepthEl.addEventListener("change", () => { if (gameId) fetchAnalysis(); });
assistHumanEl.addEventListener("change", () => { if (gameId) fetchAnalysis(); });

renderOptions();
updateModeSummary();
loadStats();
