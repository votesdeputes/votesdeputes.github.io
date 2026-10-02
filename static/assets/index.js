// Recherche par commune ou code postal. La table des communes est chargée à la première frappe.
(() => {
  const { deputes, departements } = JSON.parse(document.getElementById("data").textContent);
  const ord = n => n + (n === 1 ? "re" : "e");
  const esc = s => s.replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
  const nq = s => s.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase().replace(/[-'’]/g, " ").replace(/\s+/g, " ").trim();
  const input = document.getElementById("commune"), out = document.getElementById("resultats");
  let communes = null, loading = null;

  const load = () => loading || (loading = fetch(`data/communes.json?v=${document.body.dataset.v}`).then(r => r.json()).then(d => {
    communes = d.communes.map(c => ({ code: c[0], nom: c[1], dep: c[2], circos: c[3], cps: c[4], q: nq(c[1]) }));
  }));

  function depute(dep, circo) {
    const d = deputes[`${dep}-${circo}`], href = `${dep.toLowerCase()}/${String(circo).padStart(2, "0")}/index.html`;
    return d
      ? `<a class="pick" href="${href}"><span class="mono">${ord(circo)} circ.</span><b>${esc(d[0])}</b><span class="grp"><i style="background:${d[2]}"></i>${esc(d[1])}</span></a>`
      : `<div class="pick"><span class="mono">${ord(circo)} circ.</span><b>Siège vacant</b></div>`;
  }

  function search() {
    const raw = input.value.trim();
    if (raw.length < 2) { out.innerHTML = ""; return; }
    if (!communes) { out.innerHTML = `<p class="sub">Chargement des communes…</p>`; load().then(search); return; }
    const q = nq(raw), digits = /^\d+$/.test(raw);
    let hits = digits
      ? communes.filter(c => c.cps.some(cp => cp.startsWith(raw)))
      : communes.filter(c => c.q.startsWith(q)).concat(communes.filter(c => !c.q.startsWith(q) && c.q.includes(q)));
    if (!digits) hits.sort((a, b) => (a.q !== q) - (b.q !== q) || b.circos.length - a.circos.length);
    const total = hits.length;
    hits = hits.slice(0, 12);
    out.innerHTML = total ? hits.map(c => {
      const plusieurs = c.circos.length > 1;
      const note = c.dep === "75" ? `Paris est partagée entre 18 circonscriptions : <a href="75/index.html">choisissez votre arrondissement</a>.`
        : plusieurs ? `${c.nom} est partagée entre ${c.circos.length} circonscriptions. En cas de doute, vérifiez votre adresse sur le site de l'Assemblée.` : "";
      const picks = c.dep === "75" ? "" : `<div class="picks">${c.circos.map(n => depute(c.dep, n)).join("")}</div>`;
      return `<div class="commune"><div class="cname"><b>${esc(c.nom)}</b><span>${esc(departements[c.dep] || "")}${c.cps.length ? " · " + c.cps.slice(0, 3).join(", ") + (c.cps.length > 3 ? "…" : "") : ""}</span></div>${note ? `<p class="sub">${note}</p>` : ""}${picks}</div>`;
    }).join("") + (total > 12 ? `<p class="sub">${total - 12} autres communes. Précisez votre recherche.</p>` : "")
      : `<p class="sub">Aucune commune ne correspond. Vérifiez l'orthographe ou essayez le code postal.</p>`;
  }

  let t;
  input.addEventListener("focus", load, { once: true });
  input.addEventListener("input", () => { clearTimeout(t); t = setTimeout(search, 120); });
})();
