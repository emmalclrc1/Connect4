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
    const res = await fetch(`/api/bga/import?table_id=${encodeURIComponent(tableId)}`, { method: "POST" });
    const data = await res.json();

    if (!data.ok){
      setStatus("Erreur : " + (data.error || "import échoué"));
      return;
    }

    setStatus(`✅ Import OK — partie #${data.id_partie} — coups: ${data.moves} — gagnant: ${data.winner ?? "nul"}`);
  }catch(e){
    setStatus("Erreur réseau / serveur.");
  }finally{
    importBtn.disabled = false;
  }
}

importBtn.addEventListener("click", doImport);
