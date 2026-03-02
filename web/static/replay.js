const gridEl = document.getElementById("grid");
const metaEl = document.getElementById("meta");
const stepInfoEl = document.getElementById("stepInfo");

const prevBtn = document.getElementById("prevBtn");
const nextBtn = document.getElementById("nextBtn");
const endBtn = document.getElementById("endBtn");

function pieceClass(v){
  if (v === "R") return "red";
  if (v === "J") return "yellow";
  return "";
}

function createBoard(rows, cols){
  return Array.from({length: rows}, () => Array.from({length: cols}, () => "."));
}

function drop(board, col, player){
  for (let r = board.length - 1; r >= 0; r--){
    if (board[r][col] === "."){
      board[r][col] = player;
      return {row:r, col};
    }
  }
  return null;
}

function checkWin(board, player){
  const R = board.length;
  const C = board[0].length;
  const dirs = [[0,1],[1,0],[1,1],[-1,1]];
  for (let r=0;r<R;r++){
    for (let c=0;c<C;c++){
      if (board[r][c] !== player) continue;
      for (const [dr,dc] of dirs){
        const pos = [[r,c]];
        for (let k=1;k<4;k++){
          const nr=r+dr*k, nc=c+dc*k;
          if (nr<0||nr>=R||nc<0||nc>=C) break;
          if (board[nr][nc] !== player) break;
          pos.push([nr,nc]);
        }
        if (pos.length===4) return pos;
      }
    }
  }
  return null;
}

function render(board, winPos, lastMove){
  document.documentElement.style.setProperty("--cols", board[0].length);
  gridEl.innerHTML = "";
  for (let r=0;r<board.length;r++){
    for (let c=0;c<board[0].length;c++){
      const cell = document.createElement("div");
      cell.className = "cell";

      if (winPos && winPos.some(([rr,cc])=>rr===r && cc===c)){
        cell.classList.add("win");
      }

      const piece = document.createElement("div");
      piece.className = "piece " + pieceClass(board[r][c]);

      if (lastMove && lastMove.row===r && lastMove.col===c){
        piece.classList.add("drop");
      }

      cell.appendChild(piece);
      gridEl.appendChild(cell);
    }
  }
}

function getPartieId(){
  const m = window.location.pathname.match(/\/replay\/(\d+)/);
  return m ? Number(m[1]) : null;
}

let coups = [];
let rows = 9, cols = 9;
let idx = 0;

async function load(){
  const id = getPartieId();
  const res = await fetch(`/api/replay/${id}`);
  const data = await res.json();
  if (!data.ok){
    metaEl.textContent = data.error || "Erreur";
    return;
  }

  rows = data.partie.nb_lignes;
  cols = data.partie.nb_colonnes;
  coups = data.coups || [];

  metaEl.textContent = `Partie #${data.partie.id_partie} • ${data.partie.statut} • gagnant: ${data.partie.gagnant ?? "nul"} • coups: ${coups.length}`;
  idx = 0;
  apply();
}

function apply(){
  const board = createBoard(rows, cols);
  let lastMove = null;
  let winPos = null;

  for (let i=0;i<idx;i++){
    const m = coups[i];
    lastMove = drop(board, m.col, m.joueur);
    winPos = checkWin(board, m.joueur);
    if (winPos) break;
  }

  render(board, (idx===coups.length ? winPos : null), lastMove);
  stepInfoEl.textContent = `Coup ${idx}/${coups.length}`;
}

prevBtn.addEventListener("click", () => { idx = Math.max(0, idx-1); apply(); });
nextBtn.addEventListener("click", () => { idx = Math.min(coups.length, idx+1); apply(); });
endBtn.addEventListener("click", () => { idx = coups.length; apply(); });

load();
