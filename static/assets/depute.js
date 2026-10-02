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

  let rows = [], groupes = [], infos = {}, dates = [], votes = {}, themes = [], cat = "e", shown = 60;
  const enMandat = r => D.periodes.some(([a, b]) => a <= r[1] && r[1] <= b);
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

  // Résumé par sujet : ses positions sur les votes finaux (ensemble d'un texte) de chaque sujet.
  function sujets() {
    const stats = themes.map((th, i) => {
      const c = { p: 0, c: 0, a: 0, x: 0, i };
      rows.forEach(r => { if (r[2] === "e" && r[8].includes(i) && enMandat(r)) c[{ p: "p", c: "c", a: "a" }[votes[r[0]]] || "x"]++; });
      c.total = c.p + c.c + c.a + c.x;
      return c;
    }).sort((a, b) => b.total - a.total);
    $("sujets").innerHTML = stats.map(c => {
      const w = k => c.total ? (100 * c[k] / c.total).toFixed(1) : 0;
      const detail = c.total
        ? `${c.p} pour · ${c.c} contre · ${c.a} abst. · ${c.x} absent${c.x > 1 ? "s" : ""}`
        : "Pas de vote final sur ce sujet pendant son mandat";
      return `<button class="sujet" data-theme="${c.i}"><span class="snom">${esc(themes[c.i].nom)}</span>
        <span class="stack" aria-hidden="true">${c.total ? `<i class="s-p" style="width:${w("p")}%"></i><i class="s-c" style="width:${w("c")}%"></i><i class="s-a" style="width:${w("a")}%"></i><i class="s-x" style="width:${w("x")}%"></i>` : ""}</span>
        <span class="sdet mono">${detail}</span></button>`;
    }).join("");
  }

  function filtered() {
    const q = nq($("q").value.trim()), theme = $("theme").value;
    return rows.filter(r => {
      if (!enMandat(r)) return false;
      if (theme !== "" && !r[8].includes(+theme)) return false;
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
      const tags = r[8].map(i => `<span class="tag">${esc(themes[i].nom)}</span>`).join("");
      const gp = r[7].split("").map((p, i) => p === "-" ? "" :
        `<span class="chip ${VL[p][1]}">${esc(sigle(groupes[i]))} · ${VL[p][0].toLowerCase()}</span>`).join("");
      return `<li class="row"><span class="chip vote ${cls}">${lab}</span><div class="t">${esc(r[3])}</div>
        <div class="meta"><span>${fdate(r[1])}</span><span class="res-${r[4]}">${r[4] ? "Adopté" : "Rejeté"}</span><span class="mono">${fmt(r[5][0])} pour · ${fmt(r[5][1])} contre · ${fmt(r[5][2])} abst.</span>${r[6] ? "<span>Scrutin solennel</span>" : ""}${tags}<a href="https://www.assemblee-nationale.fr/dyn/17/scrutins/${r[0]}" target="_blank" rel="noopener">Scrutin n° ${r[0]}</a></div>
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
  $("theme").addEventListener("change", () => { shown = 60; render(); });
  $("sujets").addEventListener("click", e => {
    const b = e.target.closest("button[data-theme]"); if (!b) return;
    $("theme").value = b.dataset.theme;
    cat = "all"; shown = 60;
    document.querySelectorAll("#tabs button").forEach(x => x.setAttribute("aria-selected", x.dataset.cat === "all"));
    render();
    $("registre").scrollIntoView({ behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
  });
  $("more").addEventListener("click", () => { shown += 60; render(); });
  bars();

  Promise.all([
    fetch(`${root}data/scrutins.json`).then(r => r.json()),
    fetch(`${root}data/votes/${D.id}.txt`).then(r => r.text())
  ]).then(([s, v]) => {
    rows = s.rows; groupes = s.groupes; infos = s.infos; dates = s.derniersJours; themes = s.themes;
    $("theme").insertAdjacentHTML("beforeend", themes.map((th, i) => `<option value="${i}">${esc(th.nom)}</option>`).join(""));
    for (const [, n, code] of v.matchAll(/(\d+)([pcan])/g)) votes[n] = code;
    NOTES.r = "Les scrutins des trois derniers jours de séance : " + dates.slice().reverse().map(fdate).join(", ") + ".";
    bars();
    sujets();
    render();
  }).catch(() => { $("list").innerHTML = `<li class="empty">Les scrutins n'ont pas pu être chargés. Rechargez la page.</li>`; });
})();
