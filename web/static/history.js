const tbody = document.getElementById("tbody");
const refreshBtn = document.getElementById("refreshBtn");
const countEl = document.getElementById("count");
const filterEl = document.getElementById("filter");

const HISTORY_LIMIT = 200;

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
  return (s || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function shortSeq(seq, maxLen = 70){
  const s = seq || "";
  if (s.length <= maxLen) return s;
  return s.slice(0, maxLen) + "…";
}

async function loadHistory(){
  tbody.innerHTML = "";
  countEl.textContent = "Chargement...";

  try {
    const res = await fetch(`/api/history?limit=${HISTORY_LIMIT}`);
    const data = await res.json();

    if (!data.ok){
      countEl.textContent = data.error || "Erreur";
      return;
    }

    const items = data.items || [];
    const total = data.total || items.length;
    const f = filterEl.value;

    const filtered = (f === "all")
      ? items
      : items.filter(it => (it.statut || "") === f);

    countEl.textContent =
      `${filtered.length} parties affichées — Total inséré en base : ${total}`;

    if (!filtered.length){
      tbody.innerHTML = `<tr><td colspan="7">Aucune partie à afficher.</td></tr>`;
      return;
    }

    for (const it of filtered){
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td>${it.id_partie}</td>
        <td>${fmtDate(it.created_at)}</td>
        <td>${it.nb_coups}</td>
        <td>${gagnantLabel(it.gagnant)}</td>
        <td>${it.statut || "—"}</td>
        <td title="${escapeHtml(it.sequence || "")}">${escapeHtml(shortSeq(it.sequence || ""))}</td>
        <td><a class="linkBtn" href="/replay/${it.id_partie}">Voir</a></td>
      `;
      tbody.appendChild(tr);
    }
  } catch (e) {
    countEl.textContent = "Erreur de chargement de l'historique";
  }
}

refreshBtn.addEventListener("click", loadHistory);
filterEl.addEventListener("change", loadHistory);
loadHistory();
