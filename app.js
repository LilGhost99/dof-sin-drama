(() => {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const ED = { MAT: "Matutina", VES: "Vespertina", EXT: "Extraordinaria" };
  const estado = { temas: [], idx: null, dia: null, fecha: null, tema: "todos", ed: "todas", avisos: false, q: "", busq: null };

  const store = {
    get(k) { try { return localStorage.getItem(k); } catch { return null; } },
    set(k, v) { try { localStorage.setItem(k, v); } catch { /* sin almacenamiento */ } },
  };

  // Tema claro/oscuro
  const raiz = document.documentElement;
  const guardado = store.get("dof-tema");
  if (guardado) raiz.dataset.theme = guardado;
  $("tema").addEventListener("click", () => {
    const oscuro = raiz.dataset.theme ? raiz.dataset.theme === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
    raiz.dataset.theme = oscuro ? "light" : "dark";
    store.set("dof-tema", raiz.dataset.theme);
    pintar();
  });
  const esOscuro = () => raiz.dataset.theme ? raiz.dataset.theme === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;

  const json = async (ruta) => { const r = await fetch(ruta, { cache: "no-cache" }); if (!r.ok) throw new Error(ruta + " " + r.status); return r.json(); };
  const el = (tag, props = {}, ...hijos) => {
    const n = Object.assign(document.createElement(tag), props);
    hijos.forEach((h) => n.append(h));
    return n;
  };
  const sinAcentos = (t) => (t || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
  const temaPorId = (id) => estado.temas.find((t) => t.id === id) || { id, label: id, color: "#6B7280", color_dark: "#A7B0BD" };
  const col = (t) => (esOscuro() ? t.color_dark : t.color);
  const fmtFecha = (iso) => new Date(iso + "T12:00:00").toLocaleDateString("es-MX", { weekday: "long", day: "numeric", month: "long", year: "numeric" });
  const urlNota = (id, iso) => `https://www.dof.gob.mx/nota_detalle.php?codigo=${id}&fecha=${iso.slice(8)}/${iso.slice(5, 7)}/${iso.slice(0, 4)}`;

  async function cargarDia(iso) {
    estado.fecha = iso;
    estado.dia = null;
    $("fecha").value = iso;
    try { estado.dia = await json(`data/${iso}.json`); } catch { estado.dia = null; }
    estado.ed = "todas";
    pintar();
  }

  function filtrarDia() {
    const d = estado.dia;
    if (!d) return [];
    return d.notas.filter((n) =>
      (estado.avisos || !n.aviso) &&
      (estado.ed === "todas" || n.edicion === estado.ed) &&
      (estado.tema === "todos" || n.temas.includes(estado.tema)));
  }

  function pintarControles() {
    const d = estado.dia;
    const visibles = d ? d.notas.filter((n) => (estado.avisos || !n.aviso) && (estado.ed === "todas" || n.edicion === estado.ed)) : [];
    const conteo = {};
    visibles.forEach((n) => n.temas.forEach((t) => { conteo[t] = (conteo[t] || 0) + 1; }));

    const chips = $("chips");
    chips.replaceChildren();
    const mk = (id, label, c, n) => {
      const b = el("button", { type: "button", className: "chip" }, el("i"), label, el("b", { textContent: n }));
      b.style.setProperty("--c", c);
      b.setAttribute("aria-pressed", String(estado.tema === id));
      b.addEventListener("click", () => { estado.tema = id; pintar(); });
      return b;
    };
    chips.append(mk("todos", "Todo", "var(--ink)", visibles.length));
    estado.temas.filter((t) => !t.oculto && conteo[t.id]).forEach((t) => chips.append(mk(t.id, t.label, col(t), conteo[t.id])));

    const eds = $("ediciones");
    eds.replaceChildren();
    if (d) {
      const disponibles = Object.keys(ED).filter((k) => d.ed[k]);
      if (disponibles.length > 1) {
        [["todas", "Todas"], ...disponibles.map((k) => [k, ED[k]])].forEach(([k, label]) => {
          const b = el("button", { type: "button", textContent: label });
          b.setAttribute("aria-pressed", String(estado.ed === k));
          b.addEventListener("click", () => { estado.ed = k; pintar(); });
          eds.append(b);
        });
      }
    }
    const av = d ? d.notas.filter((n) => n.aviso).length : 0;
    $("avn").textContent = av ? `(${av})` : "";
  }

  function tarjeta(n, iso) {
    const t = temaPorId(n.temas[0]);
    const li = el("li", { className: "nota" });
    li.style.setProperty("--c", col(t));
    li.style.setProperty("--ct", col(t));
    li.append(el("h2", { textContent: n.titulo }));
    const meta = el("div", { className: "meta" });
    n.temas.filter((x) => x !== "otros" && x !== "avisos").forEach((x) => {
      const tt = temaPorId(x);
      const s = el("span", { className: "tag", textContent: tt.label });
      s.style.setProperty("--c", col(tt)); s.style.setProperty("--ct", "var(--ink)");
      meta.append(s);
    });
    if (n.dep) meta.append(el("span", { textContent: n.dep }));
    if (n.pagina) meta.append(el("span", { textContent: `pág. ${n.pagina}` }));
    if (ED[n.edicion]) meta.append(el("span", { textContent: ED[n.edicion] }));
    li.append(meta);
    if (n.resumen) {
      li.append(el("div", { className: "resumen" },
        el("div", {}, el("strong", { textContent: "Lo que dice" }), n.resumen.dice || ""),
        el("div", {}, el("strong", { textContent: "Lo que significa" }), n.resumen.significa || "")));
    }
    li.append(el("a", { className: "leer", href: n.url || urlNota(n.id, iso), target: "_blank", rel: "noopener noreferrer", textContent: "Leer en el DOF ↗" }));
    return li;
  }

  async function pintarBusqueda() {
    const lista = $("lista");
    lista.replaceChildren();
    if (!estado.busq) {
      try { estado.busq = await json("data/search.json"); } catch { estado.busq = []; }
    }
    const palabras = sinAcentos(estado.q).split(/\s+/).filter(Boolean);
    const hits = estado.busq.filter((n) => {
      const txt = sinAcentos(n.t + " " + n.d);
      return palabras.every((p) => txt.includes(p)) && (estado.tema === "todos" || n.tm.includes(estado.tema));
    }).sort((a, b) => (a.f < b.f ? 1 : -1));
    $("estado").textContent = hits.length ? `${hits.length} resultado${hits.length === 1 ? "" : "s"} en las últimas publicaciones${hits.length > 100 ? " (se muestran 100)" : ""}.` : "Sin resultados. Prueba con otra palabra.";
    hits.slice(0, 100).forEach((h) => {
      const li = tarjeta({ id: h.i, titulo: h.t, dep: h.d, temas: h.tm }, h.f);
      li.querySelector(".meta").prepend(el("span", { className: "fecha-hit", textContent: h.f }));
      lista.append(li);
    });
  }

  function pintar() {
    pintarControles();
    if (estado.q.trim().length >= 2) { pintarBusqueda(); return; }
    const lista = $("lista");
    lista.replaceChildren();
    const notas = filtrarDia();
    if (!estado.dia) {
      $("estado").textContent = `${fmtFecha(estado.fecha)}: no hay publicaciones guardadas. Puede ser fin de semana, día inhábil, o que todavía no sale el diario.`;
      return;
    }
    $("estado").textContent = `${fmtFecha(estado.fecha)} · ${notas.length} ${notas.length === 1 ? "publicación" : "publicaciones"}`;
    notas.forEach((n) => lista.append(tarjeta(n, estado.fecha)));
  }

  const mover = (delta) => {
    const d = new Date(estado.fecha + "T12:00:00"); d.setDate(d.getDate() + delta);
    cargarDia(d.toISOString().slice(0, 10));
  };
  const hoyCDMX = () => new Intl.DateTimeFormat("sv-SE", { timeZone: "America/Mexico_City" }).format(new Date());

  $("prev").addEventListener("click", () => mover(-1));
  $("next").addEventListener("click", () => mover(1));
  $("hoy").addEventListener("click", () => cargarDia(hoyCDMX()));
  $("fecha").addEventListener("change", (e) => e.target.value && cargarDia(e.target.value));
  $("avisos").addEventListener("change", (e) => { estado.avisos = e.target.checked; pintar(); });
  let t0;
  $("q").addEventListener("input", (e) => { clearTimeout(t0); t0 = setTimeout(() => { estado.q = e.target.value; pintar(); }, 200); });

  (async () => {
    try { estado.temas = await json("data/temas.json"); } catch { estado.temas = []; }
    try {
      estado.idx = await json("data/index.json");
      const ult = estado.idx.dias.length ? estado.idx.dias[estado.idx.dias.length - 1].f : hoyCDMX();
      const hoy = hoyCDMX();
      const inicial = estado.idx.dias.some((d) => d.f === hoy) ? hoy : ult;
      const act = new Date(estado.idx.actualizado);
      $("act").textContent = "Última actualización: " + act.toLocaleString("es-MX", { timeZone: "America/Mexico_City", dateStyle: "medium", timeStyle: "short" }) + " (CDMX).";
      await cargarDia(inicial);
    } catch {
      $("estado").textContent = "Aún no hay datos. Ejecuta el workflow “Actualizar DOF” en GitHub (pestaña Actions).";
    }
  })();
})();
