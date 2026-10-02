(() => {
  const { deputes, decoupage } = JSON.parse(document.getElementById("data").textContent);
  const byCirco = Object.fromEntries(deputes.map(d => [d.circo, d]));
  const esc = s => s.replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
  const arr = document.getElementById("arr"), result = document.getElementById("result");

  function show(a) {
    arr.querySelectorAll("button").forEach(b => b.setAttribute("aria-pressed", b.dataset.arr === a));
    const zones = decoupage[a] || [];
    const intro = zones.length > 1
      ? `<p class="sub">Le ${a}${a === "1" ? "er" : "e"} arrondissement est partagé entre ${zones.length} circonscriptions. Repérez votre quartier :</p>` : "";
    result.innerHTML = intro + zones.map(z => {
      const d = byCirco[z.circo];
      return d ? `<a class="match" href="${d.slug}/index.html"><span class="mono">${z.circo}e circonscription · ${esc(z.zone)}</span><b>${esc(d.nom)}</b><span>${esc(d.groupe.nom)}</span></a>` : "";
    }).join("");
    try { localStorage.setItem("arr", a); } catch (_) {}
  }

  arr.addEventListener("click", e => { const b = e.target.closest("button"); if (b) show(b.dataset.arr); });
  try { const a = localStorage.getItem("arr"); if (a && decoupage[a]) show(a); } catch (_) {}
})();
