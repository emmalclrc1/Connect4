const el = document.getElementById("aboutStats");

async function load(){
  try{
    const res = await fetch("/api/about");
    const data = await res.json();
    if (!data.ok) throw new Error();
    el.innerHTML = `
      <div class="muted">Parties en DB : <b>${data.total_parties}</b></div>
      <div class="muted">Coups en DB : <b>${data.total_coups}</b></div>
      <div class="muted mt">Astuce soutenance : ouvre /history et clique “Voir” pour montrer un replay live.</div>
    `;
  }catch{
    el.textContent = "Impossible de charger les stats.";
  }
}
load();
