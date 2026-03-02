const tableIdEl = document.getElementById("tableId");
const confEl = document.getElementById("conf");
const importBtn = document.getElementById("importBtn");
const statusEl = document.getElementById("importStatus");

function setStatus(txt, ok=null){
  statusEl.textContent = txt;
  if (ok === true) statusEl.style.color = "var(--good)";
  else if (ok === false) statusEl.style.color = "var(--bad)";
  else statusEl.style.color = "";
}

async function doImport(){
  const tableId = Number((tableIdEl.value || "").trim());
  const conf = Number((confEl.value || "1").trim());

  if (!Number.isFinite(tableId) || tableId <= 0){
    setStatus("Table ID invalide.", false);
    return;
  }

  importBtn.disabled = true;
  setStatus("Import en cours… (Selenium peut prendre quelques secondes)");

  try{
    const res = await fetch(`/api/bga/import?table_id=${encodeURIComponent(tableId)}&confiance=${encodeURIComponent(conf)}&headless=true`, {
      method: "POST"
    });
    const data = await res.json();
    if (!data.ok){
      setStatus(data.error || "Erreur import", false);
      return;
    }

    const win = data.gagnant ? (data.gagnant === "R" ? "Rouge" : "Jaune") : "—";
    setStatus(`✅ Import OK — Partie #${data.id_partie} — coups: ${data.nb_coups} — gagnant: ${win}`, true);
  }catch(e){
    setStatus("Erreur réseau / serveur", false);
  }finally{
    importBtn.disabled = false;
  }
}

importBtn.addEventListener("click", doImport);
