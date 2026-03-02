const summaryEl = document.getElementById("summary");
const activityEl = document.getElementById("activity");

async function load(){
  const res = await fetch("/api/about/details");
  const data = await res.json();
  if (!data.ok){
    summaryEl.textContent = data.error || "Erreur";
    return;
  }

  const s = data.summary;
  summaryEl.innerHTML = `
    <div class="weightLine">Auteur : <b>${data.author}</b></div>
    <div class="weightLine">Parties : <b>${s.total}</b></div>
    <div class="weightLine">Victoires Rouge : <b>${s.rouge}</b> • Victoires Jaune : <b>${s.jaune}</b> • Nuls : <b>${s.nuls}</b></div>
  `;

  activityEl.innerHTML = "";
  for (const a of (data.activity || [])){
    const div = document.createElement("div");
    div.className = "weightLine";
    div.textContent = `${a.day} : ${a.n} partie(s)`;
    activityEl.appendChild(div);
  }
}

load();
