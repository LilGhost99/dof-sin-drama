(() => {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const ED = { MAT: "Matutina", VES: "Vespertina", EXT: "Extraordinaria" };
  const estado = { temas: [], idx: null, dia: null, fecha: null, tema: "todos", ed: "todas", avisos: false, q: "", busq: null };

  const store = {
    get(k) { try { return localStorage.getItem(k); } catch { return null; } },
    set(k, v) { try { localStorage.setItem(k, v); } catch { /* sin almacenamiento */ } },
  };

  const raiz = document.documentElement;
  const esOscuro = () => (raiz.dataset.theme ? raiz.dataset.theme === "dark" : matchMedia("(prefers-color-scheme: dark)").matches);
  const metaTema = () => document.querySelector('meta[name="theme-color"]').setAttribute("content", esOscuro() ? "#11111C" : "#3A34C9");

  // ---- Ajustes: letra, tamaño y tema (se guardan en este celular) ----
  let ajustes = { letra: "clasica", tam: "m", tema: "auto" };
  try { ajustes = Object.assign(ajustes, JSON.parse(store.get("dof-ajustes") || "{}")); } catch { /* ajustes dañados */ }
  const viejo = store.get("dof-tema"); if (viejo && !store.get("dof-ajustes")) ajustes.tema = viejo;
  function aplicarAjustes() {
    raiz.dataset.letra = ajustes.letra; raiz.dataset.tam = ajustes.tam;
    if (ajustes.tema === "auto") delete raiz.dataset.theme; else raiz.dataset.theme = ajustes.tema;
    metaTema();
    document.querySelectorAll(".opciones").forEach((g) => g.querySelectorAll("button").forEach((b) => b.setAttribute("aria-pressed", String(ajustes[g.dataset.grupo] === b.dataset.v))));
  }
  aplicarAjustes();
  matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => { metaTema(); if (estado.dia) pintar(); });
  document.querySelectorAll(".opciones").forEach((g) => g.addEventListener("click", (e) => {
    const b = e.target.closest("button"); if (!b) return;
    ajustes[g.dataset.grupo] = b.dataset.v;
    store.set("dof-ajustes", JSON.stringify(ajustes));
    aplicarAjustes();
    if (g.dataset.grupo === "tema" && estado.dia) pintar();
  }));
  let focoAntes = null;
  const abrirAjustes = () => { focoAntes = document.activeElement; $("ajustes").hidden = false; $("aj-listo").focus(); };
  const cerrarAjustes = () => { $("ajustes").hidden = true; if (focoAntes) focoAntes.focus({ preventScroll: true }); };
  document.querySelectorAll("[data-ajustes]").forEach((b) => b.addEventListener("click", abrirAjustes));
  $("aj-listo").addEventListener("click", cerrarAjustes);
  $("ajustes").addEventListener("click", (e) => { if (e.target === e.currentTarget) cerrarAjustes(); });

  const json = async (ruta) => { const r = await fetch(ruta, { cache: "no-cache" }); if (!r.ok) throw new Error(ruta + " " + r.status); return r.json(); };
  const el = (tag, props = {}, ...hijos) => { const n = Object.assign(document.createElement(tag), props); hijos.forEach((h) => n.append(h)); return n; };
  const sinAcentos = (t) => (t || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
  const temaPorId = (id) => estado.temas.find((t) => t.id === id) || { id, label: id, color: "#6B7280", color_dark: "#A7B0BD" };
  const col = (t) => (esOscuro() ? t.color_dark : t.color);
  const plural = (n, a, b) => `${n} ${n === 1 ? a : b}`;
  const fechaDe = (iso) => new Date(iso + "T12:00:00");
  const urlNota = (id, iso) => `https://dof.gob.mx/nota_detalle.php?codigo=${id}&fecha=${iso.slice(8)}/${iso.slice(5, 7)}/${iso.slice(0, 4)}`;
  const flecha = '<svg viewBox="0 0 24 24" width="14" height="14" aria-hidden="true"><path d="M7 17L17 7M9 7h8v8" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg>';

  function pintarSello(total) {
    const d = fechaDe(estado.fecha);
    $("s-top").textContent = d.toLocaleDateString("es-MX", { weekday: "long" });
    $("s-dia").textContent = d.getDate();
    $("s-mes").textContent = d.toLocaleDateString("es-MX", { month: "long", year: "numeric" });
    $("s-n").textContent = total == null ? "" : total === 0 ? "sin publicaciones" : plural(total, "publicación", "publicaciones");
    const b = document.querySelector(".sello-borde");
    b.classList.remove("golpe"); void b.offsetWidth; b.classList.add("golpe");
  }

  async function cargarDia(iso) {
    estado.fecha = iso;
    estado.dia = null;
    $("fecha").value = iso;
    try { estado.dia = await json(`data/${iso}.json`); } catch { estado.dia = null; }
    estado.ed = "todas";
    estado.tema = "todos";
    $("next").disabled = iso >= hoyCDMX();
    pintarSello(estado.dia ? estado.dia.notas.filter((n) => !n.aviso).length : 0);
    pintar();
  }

  const baseDia = () => (estado.dia ? estado.dia.notas.filter((n) => estado.ed === "todas" || n.edicion === estado.ed) : []);

  function pintarControles() {
    const visibles = baseDia().filter((n) => !n.aviso);
    const conteo = {};
    visibles.forEach((n) => n.temas.forEach((t) => { conteo[t] = (conteo[t] || 0) + 1; }));
    if (estado.tema !== "todos" && !conteo[estado.tema]) estado.tema = "todos";

    const chips = $("chips");
    const scroll = chips.scrollLeft;
    chips.replaceChildren();
    const mk = (id, label, c, n) => {
      const b = el("button", { type: "button", className: "chip" });
      if (c) { const i = el("i"); i.style.setProperty("--c", c); b.append(i); }
      b.append(label, el("b", { textContent: n }));
      b.setAttribute("aria-pressed", String(estado.tema === id));
      b.addEventListener("click", () => { estado.tema = id; pintar(); scrollTo({ top: Math.max(0, document.querySelector(".herramientas").offsetTop - 60), behavior: "smooth" }); });
      return b;
    };
    chips.append(mk("todos", "Todo", null, visibles.length));
    estado.temas.filter((t) => !t.oculto && conteo[t.id]).forEach((t) => chips.append(mk(t.id, t.label, col(t), conteo[t.id])));
    chips.scrollLeft = scroll;

    const eds = $("ediciones");
    eds.replaceChildren();
    const d = estado.dia;
    if (d) {
      const disp = Object.keys(ED).filter((k) => d.ed[k]);
      if (disp.length > 1) {
        [["todas", "Todas"], ...disp.map((k) => [k, ED[k]])].forEach(([k, label]) => {
          const b = el("button", { type: "button", textContent: label });
          b.setAttribute("aria-pressed", String(estado.ed === k));
          b.addEventListener("click", () => { estado.ed = k; pintar(); });
          eds.append(b);
        });
      }
    }
  }

  function fila(n, iso, opciones = {}) {
    const art = el("article", { className: "fila" });
    const a = el("a", { textContent: n.titulo });
    if (n.texto) {
      a.href = `#n=${n.id}&f=${iso}`;
      a.addEventListener("click", () => { estado.desdeLista = true; });
    } else {
      Object.assign(a, { href: urlNota(n.id, iso), target: "_blank", rel: "noopener noreferrer" });
      a.setAttribute("aria-label", n.titulo + " (se abre el texto oficial en el DOF)");
    }
    art.append(el("h3", {}, a));
    const meta = el("p", { className: "meta" });
    if (opciones.fecha) meta.append(el("span", { className: "fecha-hit", textContent: fechaDe(iso).toLocaleDateString("es-MX", { day: "numeric", month: "short", year: "numeric" }) }));
    if (n.dep) meta.append(el("span", { textContent: n.dep }));
    if (n.pagina) meta.append(el("span", { textContent: `pág. ${n.pagina}` }));
    const extra = n.temas.filter((x) => x !== opciones.grupo && x !== "otros" && x !== "avisos");
    if (extra.length) {
      const o = el("span", { className: "otros" });
      extra.forEach((x) => o.append(el("span", { textContent: temaPorId(x).label })));
      meta.append(o);
    }
    const ext = el("span", { className: "ext" });
    if (n.texto) ext.textContent = "Leer"; else ext.innerHTML = "En el DOF " + flecha;
    meta.append(ext);
    art.append(meta);
    if (n.resumen) {
      art.append(el("div", { className: "resumen" },
        el("div", {}, el("strong", { textContent: "Lo que dice" }), n.resumen.dice || ""),
        el("div", {}, el("strong", { textContent: "Lo que significa" }), n.resumen.significa || "")));
    }
    return art;
  }

  function grupo(id, notas, iso) {
    const t = temaPorId(id);
    const sec = el("section", { className: "grupo" });
    const h = el("h2", {}, el("i"), t.label, el("span", { textContent: notas.length }));
    h.querySelector("i").style.setProperty("--c", col(t));
    sec.append(h);
    notas.forEach((n) => sec.append(fila(n, iso, { grupo: id })));
    return sec;
  }

  function botonAvisos() {
    const b = $("avisos");
    const av = estado.dia ? baseDia().filter((n) => n.aviso).length : 0;
    b.hidden = !av || estado.q.trim().length >= 2;
    b.textContent = estado.avisos ? "Ocultar avisos judiciales y generales" : `Mostrar ${plural(av, "aviso judicial o general", "avisos judiciales y generales")}`;
  }

  async function pintarBusqueda() {
    const lista = $("lista");
    lista.replaceChildren();
    if (!estado.busq) { try { estado.busq = await json("data/search.json"); } catch { estado.busq = []; } }
    const palabras = sinAcentos(estado.q).split(/\s+/).filter(Boolean);
    const hits = estado.busq.filter((n) => palabras.every((p) => sinAcentos(n.t + " " + n.d).includes(p)) && (estado.tema === "todos" || n.tm.includes(estado.tema)))
      .sort((a, b) => (a.f < b.f ? 1 : -1));
    $("estado").textContent = hits.length
      ? `${plural(hits.length, "resultado", "resultados")} en las últimas publicaciones${hits.length > 100 ? " (se muestran 100)" : ""}.`
      : "No hay resultados. Prueba con una sola palabra, por ejemplo “arancel”.";
    const sec = el("section", { className: "grupo" });
    hits.slice(0, 100).forEach((h) => sec.append(fila({ id: h.i, titulo: h.t, dep: h.d, temas: h.tm, texto: !!h.x }, h.f, { fecha: true })));
    lista.append(sec);
  }

  function pintar() {
    pintarControles();
    botonAvisos();
    if (estado.q.trim().length >= 2) { pintarBusqueda(); return; }
    const lista = $("lista");
    lista.replaceChildren();
    if (!estado.dia) {
      $("estado").textContent = "No hay publicaciones guardadas para este día. Puede ser fin de semana, día inhábil o que el diario aún no sale.";
      return;
    }
    const notas = baseDia().filter((n) => estado.avisos || !n.aviso);
    const principales = notas.filter((n) => !n.aviso);
    $("estado").textContent = "";
    if (estado.tema === "todos") {
      const porTema = {};
      principales.forEach((n) => { (porTema[n.temas[0]] = porTema[n.temas[0]] || []).push(n); });
      estado.temas.filter((t) => !t.oculto && porTema[t.id]).forEach((t) => lista.append(grupo(t.id, porTema[t.id], estado.fecha)));
    } else {
      lista.append(grupo(estado.tema, principales.filter((n) => n.temas.includes(estado.tema)), estado.fecha));
    }
    if (estado.avisos) {
      const av = notas.filter((n) => n.aviso);
      if (av.length) lista.append(grupo("avisos", av, estado.fecha));
    }
  }


  // ---- Vista de lectura ----
  function aviso(msg) {
    const t = el("div", { className: "toast", textContent: msg, role: "status" });
    document.body.append(t); setTimeout(() => t.remove(), 2200);
  }
  function buscarNota(id, iso) {
    if (estado.dia && estado.dia.fecha === iso) { const n = estado.dia.notas.find((x) => x.id === id); if (n) return n; }
    const h = (estado.busq || []).find((x) => x.i === id);
    return h ? { id, titulo: h.t, dep: h.d, temas: h.tm } : { id, titulo: "Publicación del DOF", dep: "", temas: [] };
  }
  async function abrirLector(id, iso) {
    if (iso && (!estado.dia || estado.dia.fecha !== iso)) await cargarDia(iso);
    const n = buscarNota(id, iso);
    const lec = $("lector");
    $("l-bar").textContent = n.dep || "Diario Oficial";
    $("l-meta").textContent = [fechaDe(iso).toLocaleDateString("es-MX", { day: "numeric", month: "long", year: "numeric" }), n.pagina ? `pág. ${n.pagina}` : "", ED[n.edicion] ? `edición ${ED[n.edicion].toLowerCase()}` : ""].filter(Boolean).join(", ");
    $("l-titulo").textContent = n.titulo;
    $("l-oficial").href = urlNota(id, iso);
    const caja = $("l-texto");
    caja.replaceChildren(el("p", { className: "l-aviso", textContent: "Cargando el texto…" }));
    lec.hidden = false; document.body.classList.add("leyendo"); lec.scrollTop = 0;
    $("cerrar").focus({ preventScroll: true });
    document.title = n.titulo.slice(0, 70) + " · El DOF sin drama";
    try {
      const t = await json(`data/notas/${id}.json`);
      const tpl = document.createElement("template");
      tpl.innerHTML = t.html; // HTML ya limpiado por el script (solo texto y tablas)
      tpl.content.querySelectorAll("table").forEach((tb) => {
        const w = el("div", { className: "tabla" }); tb.replaceWith(w); w.append(tb);
        if (tb.querySelector("tr") && tb.querySelector("tr").children.length > 3) w.before(el("p", { className: "pista", textContent: "Desliza la tabla hacia los lados para ver todas las columnas." }));
      });
      caja.replaceChildren(tpl.content);
      if (t.imagenes) caja.append(el("p", { className: "l-aviso", textContent: "Esta nota trae imágenes o gráficas que aquí no se muestran. Velas en el DOF oficial." }));
    } catch {
      caja.replaceChildren(el("p", { className: "l-aviso", textContent: "No tenemos el texto de esta nota. Ábrela en el DOF oficial." }));
    }
  }
  function cerrarLector() {
    $("lector").hidden = true; document.body.classList.remove("leyendo");
    document.title = "El DOF sin drama";
  }
  function leerHash() {
    const m = location.hash.match(/^#n=(\d+)&f=(\d{4}-\d{2}-\d{2})$/);
    if (m) abrirLector(Number(m[1]), m[2]); else cerrarLector();
  }
  window.addEventListener("hashchange", leerHash);
  $("cerrar").addEventListener("click", () => {
    if (estado.desdeLista) { estado.desdeLista = false; history.back(); }
    else { history.replaceState(null, "", location.pathname + location.search); cerrarLector(); }
  });
  document.addEventListener("keydown", (e) => {
    if (e.key !== "Escape") return;
    if (!$("ajustes").hidden) cerrarAjustes(); else if (!$("lector").hidden) $("cerrar").click();
  });
  $("compartir").addEventListener("click", async () => {
    const datos = { title: $("l-titulo").textContent, text: $("l-titulo").textContent + " (vía El DOF sin drama)", url: location.href };
    try {
      if (navigator.share) await navigator.share(datos);
      else { await navigator.clipboard.writeText(location.href); aviso("Enlace copiado"); }
    } catch { /* el usuario canceló */ }
  });

  const hoyCDMX = () => new Intl.DateTimeFormat("sv-SE", { timeZone: "America/Mexico_City" }).format(new Date());
  async function mover(delta) {
    const d = fechaDe(estado.fecha); d.setDate(d.getDate() + delta);
    const iso = d.toISOString().slice(0, 10);
    if (iso > hoyCDMX()) return;
    await cargarDia(iso);
    const l = $("lista"); l.classList.remove("entra-izq", "entra-der"); void l.offsetWidth;
    l.classList.add(delta < 0 ? "entra-izq" : "entra-der");
  }
  // Deslizar a los lados para cambiar de día (no en la barra de temas ni en tablas)
  let toque = null;
  document.addEventListener("touchstart", (e) => {
    const t = e.touches[0];
    if (e.touches.length !== 1 || !$("lector").hidden || !$("ajustes").hidden) { toque = null; return; }
    if (e.target.closest(".chips, .tabla, input, .abajo") || t.clientX < 28 || t.clientX > innerWidth - 28) { toque = null; return; }
    toque = { x: t.clientX, y: t.clientY, t: Date.now() };
  }, { passive: true });
  document.addEventListener("touchend", (e) => {
    if (!toque) return;
    const t = e.changedTouches[0], dx = t.clientX - toque.x, dy = t.clientY - toque.y;
    if (Math.abs(dx) > 70 && Math.abs(dy) < 45 && Date.now() - toque.t < 600) mover(dx > 0 ? -1 : 1);
    toque = null;
  }, { passive: true });

  $("prev").addEventListener("click", () => mover(-1));
  $("next").addEventListener("click", () => mover(1));
  $("hoy").addEventListener("click", async () => {
    const hoy = hoyCDMX();
    const dias = (estado.idx && estado.idx.dias) || [];
    const hay = dias.some((d) => d.f === hoy);
    const destino = hay || !dias.length ? hoy : dias[dias.length - 1].f;
    await cargarDia(destino);
    if (!hay && destino !== hoy) aviso("El diario de hoy aún no sale. Te muestro el último publicado.");
    scrollTo({ top: 0, behavior: "smooth" });
  });
  $("ir-buscar").addEventListener("click", () => {
    const q = $("q"); q.focus({ preventScroll: true });
    scrollTo({ top: Math.max(0, document.querySelector(".herramientas").offsetTop - 70), behavior: "smooth" });
  });
  $("fecha").addEventListener("change", (e) => e.target.value && cargarDia(e.target.value));
  $("avisos").addEventListener("click", () => { estado.avisos = !estado.avisos; pintar(); });
  let t0;
  $("q").addEventListener("input", (e) => { clearTimeout(t0); t0 = setTimeout(() => { estado.q = e.target.value; pintar(); }, 200); });

  (async () => {
    try { estado.temas = await json("data/temas.json"); } catch { estado.temas = []; }
    try {
      estado.idx = await json("data/index.json");
      const hoy = hoyCDMX();
      const dias = estado.idx.dias;
      const inicial = dias.some((d) => d.f === hoy) ? hoy : (dias.length ? dias[dias.length - 1].f : hoy);
      $("act").textContent = "Última actualización: " + new Date(estado.idx.actualizado).toLocaleString("es-MX", { timeZone: "America/Mexico_City", dateStyle: "medium", timeStyle: "short" }) + " (CDMX).";
      await cargarDia(inicial);
      if (location.hash.startsWith("#n=")) leerHash();
    } catch {
      estado.fecha = hoyCDMX(); pintarSello(null);
      $("estado").textContent = "Todavía no hay datos. En GitHub abre Actions y ejecuta “Actualizar DOF”.";
    }
  })();
})();
