(() => {
  const D = JSON.parse(document.getElementById("depute").textContent);
  const S = D.stats;
  const root = document.body.dataset.root;
  const VL = {p:["Pour","v-p"], c:["Contre","v-c"], a:["Abstention","v-a"], n:["Non-votant","v-n"], "":["Absent","v-x"]};
  const fmt = n => n.toLocaleString("fr-FR");
  const pct = n => String(n).replace(".", ",") + " %";
  const fdate = s => new Date(s + "T12:00:00").toLocaleDateString("fr-FR", {day:"numeric", month:"short", year:"numeric"});
  const esc = s => s.replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
  const nq = s => s.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
  const $ = id => document.getElementById(id);

  let rows = [], groupes = [], infos = {}, dates = [], votes = {}, cat = "e", shown = 60;
  const sigle = g => (infos[g] && infos[g].sigle) || g;
  const NOTES = {
    e: "Le vote final sur un projet ou une proposition de loi : c'est le vote qui dit le plus de sa position.",
    m: "Une motion de censure adoptée renverse le gouvernement. Seuls les votes « pour » sont comptés.",
    r: "", all: "Tous les scrutins auxquels ce député a pris part, amendements compris."
  };

  function bars() {
    $("bars").innerHTML = Object.entries(S.accord).sort((a, b) => b[1] - a[1]).map(([g, v]) =>
      `<div class="bar${g === D.groupe ? " own" : ""}"><span class="lab"><i style="background:${(infos[g] || {}).couleur || "#8D949A"}"></i>${esc(sigle(g))}</span><div class="track"><div class="fill" style="width:${v}%"></div></div><span class="val mono">${pct(v)}</span></div>`).join("");
  }

  function filtered() {
    const q = nq($("q").value.trim());
    return rows.filter(r => {
      if (!D.periodes.some(([a, b]) => a <= r[1] && r[1] <= b)) return false;
      if (cat === "e" && r[2] !== "e") return false;
      if (cat === "m" && r[2] !== "m") return false;
      if (cat === "r" && !dates.includes(r[1])) return false;
      if (cat === "all" && !votes[r[0]]) return false;
      return !q || nq(r[3]).includes(q);
    }).sort((a, b) => b[0] - a[0]);
  }

  function render() {
    const list = filtered();
    $("count").textContent = `${fmt(list.length)} scrutin${list.length > 1 ? "s" : ""}`;
    $("tabnote").textContent = NOTES[cat];
    $("list").innerHTML = list.length ? list.slice(0, shown).map(r => {
      const v = votes[r[0]] || "";
      let [lab, cls] = VL[v];
      if (r[2] === "m" && !v) lab = "N'a pas censuré";
      const gp = r[7].split("").map((p, i) => p === "-" ? "" :
        `<span class="chip ${VL[p][1]}">${esc(sigle(groupes[i]))} · ${VL[p][0].toLowerCase()}</span>`).join("");
      return `<li class="row"><span class="chip vote ${cls}">${lab}</span><div class="t">${esc(r[3])}</div>
        <div class="meta"><span>${fdate(r[1])}</span><span class="res-${r[4]}">${r[4] ? "Adopté" : "Rejeté"}</span><span class="mono">${fmt(r[5][0])} pour · ${fmt(r[5][1])} contre · ${fmt(r[5][2])} abst.</span>${r[6] ? "<span>Scrutin solennel</span>" : ""}<a href="https://www.assemblee-nationale.fr/dyn/17/scrutins/${r[0]}" target="_blank" rel="noopener">Scrutin n° ${r[0]}</a></div>
        ${r[2] !== "m" ? `<details class="groups"><summary>Position des groupes</summary><div class="gp">${gp}</div></details>` : ""}</li>`;
    }).join("") : `<li class="empty">Aucun scrutin ne correspond à cette recherche.</li>`;
    $("more").hidden = list.length <= shown;
  }

  $("tabs").addEventListener("click", e => {
    const b = e.target.closest("button"); if (!b) return;
    cat = b.dataset.cat; shown = 60;
    document.querySelectorAll("#tabs button").forEach(x => x.setAttribute("aria-selected", x === b));
    render();
  });
  $("q").addEventListener("input", () => { shown = 60; render(); });
  $("more").addEventListener("click", () => { shown += 60; render(); });
  bars();

  Promise.all([
    fetch(`${root}data/scrutins.json`).then(r => r.json()),
    fetch(`${root}data/votes/${D.id}.txt`).then(r => r.text())
  ]).then(([s, v]) => {
    rows = s.rows; groupes = s.groupes; infos = s.infos; dates = s.derniersJours;
    for (const [, n, code] of v.matchAll(/(\d+)([pcan])/g)) votes[n] = code;
    NOTES.r = "Les scrutins des trois derniers jours de séance : " + dates.slice().reverse().map(fdate).join(", ") + ".";
    bars();
    render();
  }).catch(() => { $("list").innerHTML = `<li class="empty">Les scrutins n'ont pas pu être chargés. Rechargez la page.</li>`; });
})();
