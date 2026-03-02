const gridEl = document.getElementById("grid");
const metaEl = document.getElementById("meta");
const seqEl = document.getElementById("seq");

const playBtn = document.getElementById("playBtn");
const pauseBtn = document.getElementById("pauseBtn");
const resetBtn = document.getElementById("resetBtn");
const speedSel = document.getElementById("speed");

let board = null;
let coups = [];
let idx = 0;
let timer = null;

function pieceClass(v){
  if (v === "R") return "red";
  if (v === "J") return "yellow";
  return "";
}

function createEmpty(rows, cols){
  return Array.from({length: rows}, () => Array.from({length: cols}, () => "."));
}

function drop(col, joueur){
  const rows = board.length;
  for (let r = rows - 1; r >= 0; r--){
    if (board[r][col] === "."){
      board[r][col] = joueur;
      return;
    }
  }
}

function render(){
  const rows = board.length;
  const cols = board[0].length;
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
}

function stop(){
  if (timer) clearInterval(timer);
  timer = null;
}

function step(){
  if (idx >= coups.length){
    stop();
    return;
  }
  const m = coups[idx];
  drop(m.col, m.joueur);
  idx++;
  render();
}

function play(){
  stop();
  const ms = Number(speedSel.value || 250);
  timer = setInterval(step, ms);
}

function reset(rows, cols){
  stop();
  idx = 0;
  board = createEmpty(rows, cols);
  render();
}

async function load(){
  const path = window.location.pathname; // /replay/48
  const id = Number(path.split("/").pop());

  const res = await fetch(`/api/replay/${id}`);
  const data = await res.json();

  if (!data.ok){
    metaEl.textContent = data.error || "Erreur";
    return;
  }

  const p = data.partie;
  coups = data.coups || [];

  metaEl.textContent =
    `Partie #${p.id_partie} — ${p.created_at ? new Date(p.created_at).toLocaleString() : ""} — Statut: ${p.statut} — Gagnant: ${p.gagnant || "—"}`;
  seqEl.textContent = p.sequence || "—";

  reset(p.nb_lignes || 9, p.nb_colonnes || 9);
}

playBtn.addEventListener("click", play);
pauseBtn.addEventListener("click", stop);
resetBtn.addEventListener("click", () => {
  const cols = board?.[0]?.length || 9;
  const rows = board?.length || 9;
  reset(rows, cols);
});

load();
