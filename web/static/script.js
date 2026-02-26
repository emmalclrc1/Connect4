let gameId = null;
let board = null;
let winPos = null;

const statusEl = document.getElementById("status");
const gridEl = document.getElementById("grid");
const boardTopEl = document.getElementById("boardTop");
const newGameBtn = document.getElementById("newGameBtn");
const modeSelect = document.getElementById("modeSelect");
const footerHint = document.getElementById("footerHint");

let hoveredCol = null;

function pieceClass(v){
  if (v === "R") return "red";
  if (v === "J") return "yellow";
  return "";
}

function setStatus({text, currentPlayer=null, winner=null, draw=false}){
  // petite pastille
  let dotClass = "";
  if (winner === "R" || currentPlayer === "R") dotClass = "red";
  else if (winner === "J" || currentPlayer === "J") dotClass = "yellow";

  let label = "—";
  if (winner) label = `Victoire: ${winner}`;
  else if (draw) label = "Match nul";
  else if (currentPlayer) label = `À ${currentPlayer} de jouer`;

  const dot = `<span class="dot ${dotClass}"></span>`;
  const pill = `<span class="pill">${dot} ${winner ? "FIN" : (currentPlayer || "")}</span>`;
  const msg = `<span class="sub">${text || label}</span>`;
  statusEl.innerHTML = `${pill}${msg}`;
}

function renderTopButtons(){
  boardTopEl.innerHTML = "";
  for (let c = 0; c < 9; c++){
    const btn = document.createElement("button");
    btn.className = "dropBtn";
    btn.textContent = "↓";
    btn.title = `Jouer colonne ${c}`;
    btn.addEventListener("mouseenter", () => { hoveredCol = c; renderBoard(); });
    btn.addEventListener("mouseleave", () => { hoveredCol = null; renderBoard(); });
    btn.addEventListener("click", () => playMove(c));
    boardTopEl.appendChild(btn);
  }
}

function renderBoard(){
  if (!board) return;

  gridEl.innerHTML = "";

  for (let r = 0; r < 9; r++){
    for (let c = 0; c < 9; c++){
      const cell = document.createElement("div");
      cell.className = "cell";
      
      const isWinCell =
        winPos &&
        winPos.some(([lr, lc]) => lr === r && lc === c);

      if (isWinCell) cell.classList.add("win");

      if (hoveredCol === c) cell.classList.add("hintCol");

      const piece = document.createElement("div");
      piece.className = "piece " + pieceClass(board[r][c]);
      cell.appendChild(piece);

      // clic direct sur la grille = jouer dans la colonne
      cell.addEventListener("mouseenter", () => { hoveredCol = c; renderBoard(); });
      cell.addEventListener("mouseleave", () => { hoveredCol = null; renderBoard(); });
      cell.addEventListener("click", () => playMove(c));

      gridEl.appendChild(cell);
    }
  }
}

async function newGame(){
  const mode = modeSelect.value;

  const res = await fetch(`/new-game?mode=${encodeURIComponent(mode)}`, { method: "POST" });
  const data = await res.json();

  if (data.error){
    setStatus({text: data.error});
    return;
  }

  gameId = data.game_id;
  board = data.plateau;

  winPos = null;
  setStatus({text: `Partie #${gameId} — Mode: ${mode}`, currentPlayer: "R"});
  footerHint.textContent = "Clique sur une colonne pour jouer.";
  renderTopButtons();
  renderBoard();
}

async function playMove(col){
  if (!gameId) return;

  const res = await fetch(`/move/${gameId}?col=${col}`, { method: "POST" });
  const data = await res.json();
  winPos = data.win_pos || null;

  if (data.error){
    setStatus({text: data.error});
    return;
  }

  board = data.plateau;
  renderBoard();

  if (data.winner){
    setStatus({text: `🎉 Victoire: ${data.winner}`, winner: data.winner});
    footerHint.textContent = "Partie terminée — relance une nouvelle partie.";
    return;
  }
  if (data.draw){
    setStatus({text: "🤝 Match nul", draw: true});
    footerHint.textContent = "Match nul — relance une nouvelle partie.";
    return;
  }

  // Tour suivant
  setStatus({text: `À ${data.next_player} de jouer`, currentPlayer: data.next_player});

  if (data.ia_move !== undefined){
    footerHint.textContent = `L’IA a joué colonne ${data.ia_move}.`;
  } else {
    footerHint.textContent = "Clique sur une colonne pour jouer.";
  }
}

newGameBtn.addEventListener("click", newGame);
modeSelect.addEventListener("change", () => {
  // option: auto new game on mode change
  // newGame();
});

// start
renderTopButtons();
newGame();
