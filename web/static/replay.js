const gridEl = document.getElementById("grid");
const metaEl = document.getElementById("meta");
const seqEl = document.getElementById("seq");
const progressEl = document.getElementById("progress");

const playBtn = document.getElementById("playBtn");
const pauseBtn = document.getElementById("pauseBtn");
const prevBtn = document.getElementById("prevBtn");
const nextBtn = document.getElementById("nextBtn");
const resetBtn = document.getElementById("resetBtn");
const speedSel = document.getElementById("speed");

let board = null;
let coups = [];
let idx = 0;
let timer = null;
let rows = 9;
let cols = 9;

function pieceClass(v){
  if (v === "R") return "red";
  if (v === "J") return "yellow";
  return "";
}

function createEmpty(r, c){
  return Array.from({length: r}, () => Array.from({length: c}, () => "."));
}

function drop(col, joueur){
  for (let r = rows - 1; r >= 0; r--){
    if (board[r][col] === "."){
      board[r][col] = joueur;
      return true;
    }
  }
  return false;
}

function render(){
  document.documentElement.style.setProperty("--cols", cols);
  gridEl.innerHTML = "";
  for (let r = 0; r < rows; r++){
    for (let c = 0; c < cols; c++){
      const cell = document.createElement("div");
      cell.className = "cell";
      const piece = document.createElement("div");
      piece.className = "piece " + pieceClass(board[r][c]);
      cell.appendChild(piece);
      gridEl.appendChild(cell);
    }
  }
  progressEl.textContent = `${idx}/${coups.length}`;
}

function stop(){
  if (timer) clearInterval(timer);
  timer = null;
}

function applyUpTo(k){
  board = createEmpty(rows, cols);
  for (let i = 0; i < k; i++){
    const m = coups[i];
    drop(m.col, m.joueur);
  }
  idx = k;
  render();
}

function stepForward(){
  if (idx >= coups.length) { stop(); return; }
  const m = coups[idx];
  drop(m.col, m.joueur);
  idx++;
  render();
}

function stepBack(){
  if (idx <= 0) return;
  applyUpTo(idx - 1);
}

function play(){
  stop();
  const ms = Number(speedSel.value || 250);
  timer = setInterval(stepForward, ms);
}

function reset(){
  stop();
  applyUpTo(0);
}

async function load(){
  const id = Number(window.location.pathname.split("/").pop());
  const res = await fetch(`/api/replay/${id}`);
  const data = await res.json();

  if (!data.ok){
    metaEl.textContent = data.error || "Erreur";
    return;
  }

  const p = data.partie;
  coups = data.coups || [];
  rows = p.nb_lignes || 9;
  cols = p.nb_colonnes || 9;

  metaEl.textContent =
    `Partie #${p.id_partie} — ${p.created_at ? new Date(p.created_at).toLocaleString() : ""} — Statut: ${p.statut} — Gagnant: ${p.gagnant || "—"}`;
  seqEl.textContent = p.sequence || "—";

  applyUpTo(0);
}

playBtn.addEventListener("click", play);
pauseBtn.addEventListener("click", stop);
resetBtn.addEventListener("click", reset);
nextBtn.addEventListener("click", () => { stop(); stepForward(); });
prevBtn.addEventListener("click", () => { stop(); stepBack(); });

load();
