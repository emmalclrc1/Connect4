const tbody = document.getElementById("tbody");
const refreshBtn = document.getElementById("refreshBtn");
const countEl = document.getElementById("count");

function fmtDate(iso){
  if (!iso) return "—";
  return new Date(iso).toLocaleString();
}

function gagnantLabel(g){
  if (g === "R") return "Rouge";
  if (g === "J") return "Jaune";
  return "—";
}

async function loadHistory(){
  tbody.innerHTML = "";
  countEl.textContent = "Chargement...";

  const res = await fetch("/api/history?limit=5000");
  const data = await res.json();

  if (!data.ok){
    countEl.textContent = data.error || "Erreur";
    return;
  }

  const items = data.items || [];
  countEl.textContent = `${items.length} parties affichées`;

  for (const it of items){
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${it.id_partie}</td>
      <td>${fmtDate(it.created_at)}</td>
      <td>${it.nb_coups}</td>
      <td>${gagnantLabel(it.gagnant)}</td>
      <td>${it.statut || "—"}</td>
      <td><a class="linkBtn" href="/replay/${it.id_partie}">Voir</a></td>
    `;
    tbody.appendChild(tr);
  }
}

refreshBtn.addEventListener("click", loadHistory);
loadHistory();
