const tableIdEl = document.getElementById("tableId");
const importBtn = document.getElementById("importBtn");
const statusEl = document.getElementById("importStatus");

function setStatus(msg){
  statusEl.textContent = msg;
}

async function doImport(){
  const v = (tableIdEl.value || "").trim();
  if (!v){
    setStatus("Entre un table_id.");
    return;
  }

  const tableId = Number(v);
  if (!Number.isFinite(tableId) || tableId <= 0){
    setStatus("table_id invalide.");
    return;
  }

  importBtn.disabled = true;
  setStatus("Import en cours...");

  try{
    const res = await fetch("http://127.0.0.1:5001/import-bga-table", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ table: tableId })
    });

    const data = await res.json();

    if (!data.ok){
      setStatus("Erreur : " + (data.error || "import échoué"));
      return;
    }

    const api = data.api || {};

    setStatus(
      `✅ Import OK — partie #${api.id_partie ?? "?"} — coups: ${api.moves ?? "?"} — gagnant: ${api.winner ?? "nul"}`
    );

  }catch(e){
    setStatus("Impossible de joindre le scraper local. Lance : py -3.10 scrape_bga_edge.py --serve");
  }finally{
    importBtn.disabled = false;
  }
}

importBtn.addEventListener("click", doImport);
