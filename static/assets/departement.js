// Choix par arrondissement (Paris) : affiche la ou les circonscriptions de l'arrondissement choisi.
(() => {
  const { deputes, decoupage } = JSON.parse(document.getElementById("data").textContent);
  const ord = n => n + (n === 1 ? "re" : "e");
  const esc = s => s.replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
  const arr = document.getElementById("arr"), result = document.getElementById("result");

  function show(a) {
    arr.querySelectorAll("button").forEach(b => b.setAttribute("aria-pressed", b.dataset.arr === a));
    const zones = decoupage[a] || [];
    const intro = zones.length > 1
      ? `<p class="sub">Le ${a}${a === "1" ? "er" : "e"} arrondissement est partagé entre ${zones.length} circonscriptions. Repérez votre quartier :</p>` : "";
    result.innerHTML = intro + zones.map(z => {
      const d = deputes[z.circo], circo = String(z.circo).padStart(2, "0");
      return d
        ? `<a class="match" href="${circo}/index.html"><span class="mono">${ord(z.circo)} circonscription · ${esc(z.zone)}</span><b>${esc(d.nom)}</b><span class="grp"><i style="background:${d.groupe.couleur}"></i>${esc(d.groupe.nom)}</span></a>`
        : `<div class="match"><span class="mono">${ord(z.circo)} circonscription · ${esc(z.zone)}</span><b>Siège vacant</b></div>`;
    }).join("");
    try { localStorage.setItem("arr", a); } catch (_) {}
  }

  arr.addEventListener("click", e => { const b = e.target.closest("button"); if (b) show(b.dataset.arr); });
  try { const a = localStorage.getItem("arr"); if (a && decoupage[a]) show(a); } catch (_) {}
})();
