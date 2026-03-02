const tbody = document.getElementById("tbody");
const refreshBtn = document.getElementById("refreshBtn");
const countEl = document.getElementById("count");
const filterEl = document.getElementById("filter");

function fmtDate(iso){
  if (!iso) return "—";
  return new Date(iso).toLocaleString();
}

function gagnantLabel(g){
  if (g === "R") return "Rouge";
  if (g === "J") return "Jaune";
  return "—";
}

function escapeHtml(s){
  return (s || "").replaceAll("&","&amp;").replaceAll("<","&lt;").replaceAll(">","&gt;");
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
  const f = filterEl.value;

  const filtered = (f === "all") ? items : items.filter(it => (it.statut || "") === f);
  countEl.textContent = `${filtered.length} parties affichées (sur ${items.length})`;

  for (const it of filtered){
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${it.id_partie}</td>
      <td>${fmtDate(it.created_at)}</td>
      <td>${it.nb_coups}</td>
      <td>${gagnantLabel(it.gagnant)}</td>
      <td>${it.statut || "—"}</td>
      <td>${escapeHtml(it.sequence || "")}</td>
      <td><a class="linkBtn" href="/replay/${it.id_partie}">Voir</a></td>
    `;
    tbody.appendChild(tr);
  }
}

refreshBtn.addEventListener("click", loadHistory);
filterEl.addEventListener("change", loadHistory);
loadHistory();
