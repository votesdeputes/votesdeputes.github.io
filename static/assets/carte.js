// Carte des circonscriptions : chaque circonscription prend la couleur du groupe de son député.
// Pas de fond de carte externe : seuls les contours sont dessinés, aucune requête vers un service tiers.
(() => {
  const el = document.getElementById("carte");
  if (!el || !window.L) return;
  const { deputes, departements } = JSON.parse(document.getElementById("data").textContent);
  const info = document.getElementById("carte-info");
  const esc = s => s.replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
  const ord = n => n + (n === 1 ? "re" : "e");
  const css = name => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  const VUES = {
    metropole: [[41.3, -5.2], [51.1, 9.6]],
    paris: [[48.80, 2.20], [48.92, 2.47]],
    "971": [[15.8, -61.9], [16.55, -61.0]],
    "972": [[14.38, -61.25], [14.9, -60.8]],
    "973": [[2.1, -54.6], [5.8, -51.6]],
    "974": [[-21.4, 55.2], [-20.85, 55.85]],
    "976": [[-13.02, 45.0], [-12.63, 45.32]],
    "975": [[46.74, -56.45], [47.15, -56.1]],
  };

  const map = L.map(el, { preferCanvas: true, zoomSnap: 0.25, minZoom: 2, maxZoom: 13, attributionControl: true });
  map.attributionControl.setPrefix(false).addAttribution('Contours : <a href="https://www.data.gouv.fr/fr/datasets/contours-geographiques-des-circonscriptions-legislatives/" target="_blank" rel="noopener">data.gouv.fr</a>, Licence Ouverte');
  map.fitBounds(VUES.metropole);

  const depute = p => deputes[`${p.dep}-${p.circo}`];
  const style = f => {
    const d = depute(f.properties);
    return { color: css("--bg"), weight: 0.5, fillColor: d ? d[2] : css("--abs-bg"), fillOpacity: d ? 0.9 : 1 };
  };
  let selection = null, couche = null;

  function montre(f, layer) {
    if (selection) couche.resetStyle(selection);
    selection = layer;
    layer.setStyle({ weight: 2.5, color: css("--fg") });
    layer.bringToFront();
    const p = f.properties, d = depute(p);
    const lieu = `${ord(p.circo)} circonscription · ${esc(departements[p.dep] || "")}`;
    const href = `${p.dep.toLowerCase()}/${String(p.circo).padStart(2, "0")}/index.html`;
    info.innerHTML = d
      ? `<a class="match" href="${href}"><span class="mono">${lieu}</span><b>${esc(d[0])}</b><span class="grp"><i style="background:${d[2]}"></i>${esc(d[1])}</span><span>Voir ses votes →</span></a>`
      : `<div class="match"><span class="mono">${lieu}</span><b>Siège vacant</b><span>En attente d'une élection partielle</span></div>`;
  }

  fetch(`data/carte.json?v=${document.body.dataset.v}`).then(r => r.json()).then(geo => {
    couche = L.geoJSON(geo, {
      style,
      onEachFeature: (f, layer) => {
        const d = depute(f.properties);
        layer.bindTooltip(`${d ? esc(d[0]) + " · " + esc(d[1]) : "Siège vacant"}<br>${ord(f.properties.circo)} circ. · ${esc(departements[f.properties.dep] || "")}`, { sticky: true });
        layer.on({
          click: () => montre(f, layer),
          mouseover: () => layer !== selection && layer.setStyle({ weight: 1.5, color: css("--fg") }),
          mouseout: () => layer !== selection && couche.resetStyle(layer),
        });
      },
    }).addTo(map);
  }).catch(() => { el.innerHTML = `<p class="sub">La carte n'a pas pu être chargée. Rechargez la page.</p>`; });

  document.getElementById("vues").addEventListener("click", e => {
    const b = e.target.closest("button[data-vue]"); if (!b) return;
    document.querySelectorAll("#vues button").forEach(x => x.setAttribute("aria-pressed", x === b));
    map.fitBounds(VUES[b.dataset.vue]);
  });

  // Les couleurs de la carte suivent le thème clair ou sombre.
  matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => couche && couche.setStyle(style));
})();
