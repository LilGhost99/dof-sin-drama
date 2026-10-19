#!/usr/bin/env python3
"""
DOF sin drama: descarga el sumario del Diario Oficial de la Federación desde el
servicio abierto SIDOF (Secretaría de Gobernación), clasifica cada publicación
por tema y guarda archivos JSON que lee la página web.

Solo usa la librería estándar de Python (no hay nada que instalar).

Uso:
  python scripts/fetch_dof.py                    hoy y ayer (hora de CDMX)
  python scripts/fetch_dof.py --dias-atras 14    hoy y los 14 días anteriores
  python scripts/fetch_dof.py --fecha 2026-10-16 un día específico
"""
import argparse
import html
from html.parser import HTMLParser
import json
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

BASE = "https://sidof.segob.gob.mx/dof/sidof"
UA = "dof-sin-drama/1.0 (proyecto estudiantil; lectura diaria del sumario)"
TZ = ZoneInfo("America/Mexico_City")
MAX_TEXTOS_POR_CORRIDA = 400
_textos_pedidos = 0
DIAS_EN_INDICE = 400
DIAS_EN_BUSCADOR = 180
DIAS_CON_TEXTO = 365  # los textos más viejos se borran para que el sitio no crezca sin límite

EDICIONES = [("NotasMatutinas", "MAT"), ("NotasVespertinas", "VES"), ("NotasExtraordinarias", "EXT")]

# ---------------------------------------------------------------------------
# Temas. El orden es la prioridad: el primer tema que coincide es el principal.
# "titulo" y "dep" son expresiones regulares sobre texto sin acentos y en minúsculas.
# ---------------------------------------------------------------------------
TEMAS = [
    {"id": "comercio", "label": "Comercio exterior", "color": "#1B5FD1", "color_dark": "#7FA8FF",
     "titulo": [r"\barancel", r"\btigie\b", r"impuestos? generales? de importacion", r"\bimportacion",
                r"\bexportacion", r"comercio exterior", r"cuotas? compensatorias?", r"\bdumping\b",
                r"\bprosec\b", r"\baduan", r"\bimmex\b", r"padron de importadores",
                r"tratado de libre comercio|\bt-?mec\b|\btlc", r"reglas? de origen|certificado de origen",
                r"fraccion(es)? arancelaria", r"\bsalvaguarda", r"mercancias? (de procedencia )?extranjera",
                r"\bpedimento", r"regimen(es)? aduanero", r"recinto (portuario|fiscal)"],
     "dep": [r"agencia nacional de aduanas"]},
    {"id": "compras", "label": "Compras de gobierno", "color": "#B24A12", "color_dark": "#FF9A62",
     "titulo": [r"adquisiciones", r"licitacion", r"convocatoria", r"abstenerse de aceptar propuestas",
                r"inhabilit", r"\bproveedor", r"contrataciones? publicas?", r"compras? publicas?", r"obra publica"],
     "dep": [r"convocatorias para concursos"]},
    {"id": "normas", "label": "Normas oficiales (NOM)", "color": "#6B46C1", "color_dark": "#B79CFF",
     "titulo": [r"norma oficial mexicana", r"\bnom-\d", r"proyecto de norma", r"\bnmx-"], "dep": []},
    {"id": "fiscal", "label": "Impuestos", "color": "#8A6A00", "color_dark": "#E8C34E",
     "titulo": [r"\bimpuesto", r"\bisr\b", r"\biva\b", r"\bieps\b", r"estimulos? fiscal", r"miscelanea fiscal",
                r"codigo fiscal", r"contribuciones", r"\brecargos\b", r"\bsat\b", r"administracion tributaria",
                r"ley de ingresos", r"comprobantes? fiscales?|\bcfdi\b"],
     "dep": [r"servicio de administracion tributaria"]},
    {"id": "agro", "label": "Campo", "color": "#2E7D32", "color_dark": "#7AD07F",
     "titulo": [r"agricultur", r"ganader", r"\bpesca\b|acuacultur|pesquer", r"\bproductores?\b", r"fertilizante",
                r"desarrollo rural", r"senasica", r"sanidad (vegetal|animal)|inocuidad", r"\bcampo\b|campesin",
                r"agroalimentari", r"\bsader\b"],
     "dep": [r"agricultura y desarrollo rural"]},
    {"id": "economia", "label": "Indicadores y finanzas", "color": "#0F766E", "color_dark": "#5CD6C8",
     "titulo": [r"tipo de cambio", r"tasas? de interes", r"\btiie\b", r"\budis?\b|unidades? de inversion",
                r"indice nacional de precios", r"\binpc\b", r"banco de mexico", r"inflacion", r"\bpib\b"],
     "dep": [r"banco de mexico", r"instituto nacional de estadistica"]},
    {"id": "trabajo", "label": "Trabajo y seguridad social", "color": "#B0357A", "color_dark": "#F58AC0",
     "titulo": [r"salarios? minimos?", r"\bstps\b|trabajo y prevision social", r"reforma laboral|\bsindic",
                r"seguridad social", r"\binfonavit\b", r"\bpension|\bjubilacion", r"\btrabajadores?\b",
                r"\bissste\b"],
     "dep": [r"trabajo y prevision social"]},
    {"id": "salud", "label": "Salud", "color": "#C0392B", "color_dark": "#FF8A7A",
     "titulo": [r"\bsalud\b", r"medicament|medicin", r"cofepris", r"hospital", r"sanitari", r"epidemi", r"vacun"],
     "dep": [r"secretaria de salud", r"proteccion contra riesgos sanitarios"]},
    {"id": "educacion", "label": "Educación y ciencia", "color": "#3949AB", "color_dark": "#9DA8FF",
     "titulo": [r"educacion", r"universidad", r"escolar", r"\bbecas?\b", r"\bsep\b",
                r"ciencia|tecnologia e innovacion|secihti|conahcyt", r"\bestudiantes?\b"],
     "dep": [r"educacion publica", r"ciencia, humanidades"]},
    {"id": "energia", "label": "Energía y combustibles", "color": "#9A5B00", "color_dark": "#F0B866",
     "titulo": [r"energia", r"\bcfe\b|comision federal de electricidad", r"\bpemex\b|petroleos mexicanos",
                r"hidrocarburo", r"electric", r"\bgas\b|gasolina|combustible|diesel|petroleo|litio"],
     "dep": [r"secretaria de energia", r"comision nacional de energia"]},
    {"id": "ambiente", "label": "Medio ambiente y agua", "color": "#3F7D58", "color_dark": "#8FD6AC",
     "titulo": [r"medio ambiente", r"semarnat", r"ambiental", r"\bagua\b|conagua", r"forestal|bosque",
                r"residuos", r"emisiones", r"areas? naturales? protegidas?", r"cambio climatico"],
     "dep": [r"medio ambiente y recursos naturales", r"comision nacional del agua"]},
    {"id": "justicia", "label": "Justicia y tribunales", "color": "#5C6370", "color_dark": "#B4BCC9",
     "titulo": [r"suprema corte", r"controversia constitucional|accion de inconstitucionalidad", r"\btribunal\b|\bsentencia",
                r"poder judicial", r"juzgado|\bjueces\b|magistrad"],
     "dep": [r"suprema corte|tribunal|judicial|judicatura"]},
    {"id": "electoral", "label": "Elecciones", "color": "#A33A3A", "color_dark": "#F29A9A",
     "titulo": [r"instituto nacional electoral|\bine\b", r"proceso electoral|precampanas|campanas electorales",
                r"partidos? politicos?"],
     "dep": [r"instituto nacional electoral"]},
    {"id": "otros", "label": "Otras publicaciones", "color": "#6B7280", "color_dark": "#A7B0BD",
     "titulo": [], "dep": []},
    {"id": "avisos", "label": "Avisos judiciales y generales", "color": "#6B7280", "color_dark": "#A7B0BD",
     "titulo": [], "dep": [], "oculto": True},
]
for _t in TEMAS:
    _t["_titulo"] = [re.compile(p) for p in _t["titulo"]]
    _t["_dep"] = [re.compile(p) for p in _t["dep"]]

NOMBRES_CORTOS = {
    "SECRETARIA DE GOBERNACION": "Gobernación",
    "SECRETARIA DE RELACIONES EXTERIORES": "Relaciones Exteriores",
    "SECRETARIA DE LA DEFENSA NACIONAL": "Defensa",
    "SECRETARIA DE MARINA": "Marina",
    "SECRETARIA DE SEGURIDAD Y PROTECCION CIUDADANA": "Seguridad",
    "SECRETARIA DE HACIENDA Y CREDITO PUBLICO": "Hacienda",
    "SECRETARIA DE ECONOMIA": "Economía",
    "SECRETARIA DE AGRICULTURA Y DESARROLLO RURAL": "Agricultura",
    "SECRETARIA DE INFRAESTRUCTURA, COMUNICACIONES Y TRANSPORTES": "SICT",
    "SECRETARIA ANTICORRUPCION Y BUEN GOBIERNO": "Anticorrupción",
    "SECRETARIA DE EDUCACION PUBLICA": "SEP",
    "SECRETARIA DE SALUD": "Salud",
    "SECRETARIA DEL TRABAJO Y PREVISION SOCIAL": "Trabajo",
    "SECRETARIA DE MEDIO AMBIENTE Y RECURSOS NATURALES": "Medio Ambiente",
    "SECRETARIA DE ENERGIA": "Energía",
    "SECRETARIA DE TURISMO": "Turismo",
    "SECRETARIA DE LAS MUJERES": "Mujeres",
    "SECRETARIA DE CULTURA": "Cultura",
    "INSTITUTO MEXICANO DEL SEGURO SOCIAL": "IMSS",
    "BANCO DE MEXICO": "Banxico",
    "INSTITUTO NACIONAL DE ESTADISTICA Y GEOGRAFIA": "INEGI",
    "INSTITUTO NACIONAL ELECTORAL": "INE",
    "SUPREMA CORTE DE JUSTICIA DE LA NACION": "SCJN",
    "TRIBUNAL FEDERAL DE JUSTICIA ADMINISTRATIVA": "TFJA",
    "AGENCIA NACIONAL DE ADUANAS DE MEXICO": "ANAM",
}
MINUSCULAS = {"de", "del", "la", "las", "los", "el", "y", "e", "en", "para", "por", "a"}


def norm(texto):
    """Minúsculas y sin acentos, para comparar."""
    t = unicodedata.normalize("NFKD", texto or "")
    return "".join(c for c in t if not unicodedata.combining(c)).lower()


def nombre_bonito(mayusculas):
    if not mayusculas or mayusculas == "null":
        return ""
    if mayusculas in NOMBRES_CORTOS:
        return NOMBRES_CORTOS[mayusculas]
    palabras = mayusculas.lower().split()
    return " ".join(p if (i and p in MINUSCULAS) else p.capitalize() for i, p in enumerate(palabras))


def clasificar(titulo, dependencia_texto, es_aviso=False):
    """Devuelve la lista de ids de tema (el primero es el principal)."""
    if es_aviso:
        return ["avisos"]
    t, d = norm(titulo), norm(dependencia_texto)
    encontrados = []
    for tema in TEMAS:
        if tema["id"] in ("otros", "avisos"):
            continue
        if any(r.search(t) for r in tema["_titulo"]) or any(r.search(d) for r in tema["_dep"]):
            encontrados.append(tema["id"])
    return encontrados or ["otros"]


def pedir_json(url, intentos=3):
    """Lee un JSON de SIDOF. Prueba varias combinaciones de cabeceras porque
    el servicio responde 406 si no le gusta alguna."""
    variantes = [
        {"User-Agent": UA},
        {"User-Agent": UA, "Accept": "*/*"},
        {"User-Agent": "Mozilla/5.0 (compatible; dof-sin-drama/1.0)", "Accept": "application/json, text/plain, */*"},
    ]
    ultimo = None
    for i in range(intentos):
        for cab in variantes:
            try:
                req = urllib.request.Request(url, headers=cab)
                with urllib.request.urlopen(req, timeout=30) as r:
                    return json.loads(r.read().decode("utf-8"))
            except urllib.error.HTTPError as e:
                ultimo = e
                if e.code in (404,):
                    raise RuntimeError(f"No encontrado: {url}")
            except Exception as e:  # noqa: BLE001
                ultimo = e
        time.sleep(3 * (i + 1))
    raise RuntimeError(f"No se pudo leer {url}: {ultimo}")


def limpiar_html(fragmento):
    texto = re.sub(r"<[^>]+>", " ", fragmento or "")
    return re.sub(r"\s+", " ", html.unescape(texto)).strip()


class _Limpiador(HTMLParser):
    """Deja solo etiquetas seguras de texto y tablas; quita estilos, scripts e imágenes."""
    PERMITIDAS = {"p", "br", "b", "strong", "i", "em", "u", "sup", "sub", "ul", "ol", "li",
                  "table", "thead", "tbody", "tfoot", "tr", "td", "th", "caption", "h1", "h2", "h3", "h4", "h5", "h6"}
    RENOMBRAR = {"h1": "h3", "h2": "h3", "h3": "h4", "h4": "h4", "h5": "h4", "h6": "h4"}
    VACIAS = {"br"}
    IGNORAR = {"head", "title", "style", "script", "noscript"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out, self.ignorar, self.imagenes, self.abiertas = [], 0, False, []

    def handle_starttag(self, tag, attrs):
        if tag in self.IGNORAR:
            self.ignorar += 1
            return
        if self.ignorar:
            return
        if tag == "img":
            self.imagenes = True
            return
        nuevo = self.RENOMBRAR.get(tag, tag)
        if nuevo not in self.PERMITIDAS:
            return
        extra = ""
        if nuevo in ("td", "th"):
            for k, v in attrs:
                if k in ("colspan", "rowspan") and v and v.isdigit() and int(v) < 100:
                    extra += f' {k}="{v}"'
        self.out.append(f"<{nuevo}{extra}>")
        if nuevo not in self.VACIAS:
            self.abiertas.append((tag, nuevo))

    def handle_endtag(self, tag):
        if tag in self.IGNORAR:
            self.ignorar = max(0, self.ignorar - 1)
            return
        if self.ignorar:
            return
        for i in range(len(self.abiertas) - 1, -1, -1):
            if self.abiertas[i][0] == tag:
                for _, n in reversed(self.abiertas[i:]):
                    self.out.append(f"</{n}>")
                del self.abiertas[i:]
                return

    def handle_data(self, data):
        if not self.ignorar:
            self.out.append(html.escape(data, quote=False))

    def resultado(self):
        for _, n in reversed(self.abiertas):
            self.out.append(f"</{n}>")
        h = "".join(self.out)
        h = re.sub(r"[ \t\r\n ]+", " ", h)
        h = re.sub(r"<p>\s*</p>", "", h)
        h = re.sub(r"<p>\s*<p>", "<p>", h)
        h = re.sub(r"</p>\s*</p>", "</p>", h)
        return h.strip()


def limpiar_contenido(contenido):
    lim = _Limpiador()
    lim.feed(contenido or "")
    lim.close()
    return lim.resultado(), lim.imagenes


def detalle(cod):
    """Pide el detalle de una nota. Devuelve (titulo, html_limpio, tiene_imagenes)."""
    det = pedir_json(f"{BASE}/notas/nota/{cod}")
    nota = det.get("Nota") or {}
    contenido = nota.get("cadenaContenido") or ""
    titulo = (nota.get("titulo") or "").strip()
    if not titulo or titulo == "null":
        m = re.search(r"<title[^>]*>(.*?)</title>", contenido, re.S | re.I)
        titulo = limpiar_html(m.group(1)) if m else ""
    cuerpo, imagenes = limpiar_contenido(contenido)
    return titulo, cuerpo, imagenes


def notas_del_dia(respuesta):
    """Une las ediciones del día en una lista de (edicion, nota_cruda)."""
    salida = []
    for clave, codigo in EDICIONES:
        for crudo in sorted(respuesta.get(clave) or [], key=lambda n: n.get("orden") or 0):
            salida.append((codigo, crudo))
    return salida


def construir_notas(crudas, fecha, carpeta=None, usar_detalles=True):
    global _textos_pedidos
    notas = []
    textos = carpeta / "notas" if carpeta else None
    if textos:
        textos.mkdir(parents=True, exist_ok=True)
    for edicion, c in crudas:
        cod = c.get("codNota")
        es_aviso = c.get("tipoNota") == "AVISO" or c.get("codOrgaUno") == "AV"
        titulo = (c.get("titulo") or "").strip()
        if titulo == "null":
            titulo = ""
        # Las entradas sin título y sin documento son encabezados de sección (nombre de la dependencia).
        if not titulo and not es_aviso and c.get("existeDoc") == "N":
            continue
        ruta_texto = textos / f"{cod}.json" if textos else None
        tiene_texto = bool(ruta_texto and ruta_texto.exists())
        if not es_aviso and usar_detalles and textos and (not tiene_texto or not titulo) and _textos_pedidos < MAX_TEXTOS_POR_CORRIDA:
            _textos_pedidos += 1
            time.sleep(0.4)
            try:
                t2, cuerpo, imagenes = detalle(cod)
                titulo = titulo or t2
                if cuerpo and len(re.sub(r"<[^>]+>", "", cuerpo)) > 40:
                    ruta_texto.write_text(json.dumps({"id": cod, "html": cuerpo, "imagenes": imagenes},
                                                     ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
                    tiene_texto = True
            except RuntimeError as e:
                print(f"  aviso: sin detalle de {cod}: {e}", file=sys.stderr)
        if not titulo and not es_aviso:
            continue
        dep_largo = c.get("codOrgaDos") if c.get("codOrgaDos") not in (None, "null") else ""
        poder = c.get("nombreCodOrgaUno") or ""
        dep_texto = f"{poder} {dep_largo}"
        nota = {
            "id": cod,
            "titulo": titulo or "Aviso",
            "dep": nombre_bonito(dep_largo) or nombre_bonito(poder),
            "edicion": edicion,
            "pagina": c.get("pagina") or 0,
            "temas": clasificar(titulo, dep_texto, es_aviso),
            "url": f"https://dof.gob.mx/nota_detalle.php?codigo={cod}&fecha={fecha:%d/%m/%Y}",
        }
        if tiene_texto:
            nota["texto"] = True
        if es_aviso:
            nota["aviso"] = True
        notas.append(nota)
    return notas


def guardar_dia(carpeta, fecha, notas, ediciones):
    ruta = carpeta / f"{fecha:%Y-%m-%d}.json"
    if ruta.exists():  # conserva resúmenes ya escritos (etapa 2) y evita cambios inútiles
        previo = json.loads(ruta.read_text(encoding="utf-8"))
        resumenes = {n["id"]: n["resumen"] for n in previo.get("notas", []) if "resumen" in n}
        for n in notas:
            if n["id"] in resumenes:
                n["resumen"] = resumenes[n["id"]]
        if previo.get("notas") == notas and previo.get("ed") == ediciones:
            return False
    contenido = {
        "fecha": f"{fecha:%Y-%m-%d}",
        "actualizado": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "ed": ediciones,
        "notas": notas,
    }
    ruta.write_text(json.dumps(contenido, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return True


def limpiar_textos_viejos(carpeta, hoy):
    """Borra los textos de notas con más de DIAS_CON_TEXTO días y quita su marca "texto"."""
    textos = carpeta / "notas"
    if not textos.exists():
        return
    limite = hoy - timedelta(days=DIAS_CON_TEXTO)
    conservar, borrados = set(), 0
    for ruta in sorted(carpeta.glob("*.json")):
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}\.json", ruta.name):
            continue
        dia = json.loads(ruta.read_text(encoding="utf-8"))
        if date.fromisoformat(dia["fecha"]) >= limite:
            conservar.update(n["id"] for n in dia["notas"])
        elif any(n.get("texto") for n in dia["notas"]):
            for n in dia["notas"]:
                n.pop("texto", None)
            ruta.write_text(json.dumps(dia, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    for ruta in textos.glob("*.json"):
        if ruta.stem.isdigit() and int(ruta.stem) not in conservar:
            ruta.unlink()
            borrados += 1
    if borrados:
        print(f"Se borraron {borrados} textos de más de {DIAS_CON_TEXTO} días.")


def reconstruir_indices(carpeta):
    archivos = sorted(p for p in carpeta.glob("*.json") if re.fullmatch(r"\d{4}-\d{2}-\d{2}\.json", p.name))
    archivos = archivos[-DIAS_EN_INDICE:]
    dias, buscador = [], []
    for ruta in archivos:
        dia = json.loads(ruta.read_text(encoding="utf-8"))
        conteo, avisos, total = {}, 0, 0
        for n in dia["notas"]:
            if n.get("aviso"):
                avisos += 1
                continue
            total += 1
            for t in n["temas"]:
                conteo[t] = conteo.get(t, 0) + 1
        dias.append({"f": dia["fecha"], "n": total, "av": avisos, "t": conteo,
                     "ed": [k for k, v in dia["ed"].items() if v]})
    for ruta in archivos[-DIAS_EN_BUSCADOR:]:
        dia = json.loads(ruta.read_text(encoding="utf-8"))
        for n in dia["notas"]:
            if not n.get("aviso"):
                buscador.append({"f": dia["fecha"], "i": n["id"], "t": n["titulo"], "d": n["dep"], "tm": n["temas"]}
                                | ({"x": 1} if n.get("texto") else {}))
    ahora = datetime.now(timezone.utc).isoformat(timespec="seconds")
    (carpeta / "index.json").write_text(
        json.dumps({"actualizado": ahora, "dias": dias}, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    (carpeta / "search.json").write_text(json.dumps(buscador, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    temas_publicos = [{k: t[k] for k in ("id", "label", "color", "color_dark")} | ({"oculto": True} if t.get("oculto") else {})
                      for t in TEMAS]
    (carpeta / "temas.json").write_text(json.dumps(temas_publicos, ensure_ascii=False, indent=1), encoding="utf-8")


def procesar_dia(carpeta, fecha, respuesta, usar_detalles):
    crudas = notas_del_dia(respuesta)
    if not crudas:
        print(f"{fecha}: sin publicaciones (fin de semana o aún no sale)")
        return False
    ediciones = {codigo: bool(respuesta.get(clave)) for clave, codigo in EDICIONES}
    notas = construir_notas(crudas, fecha, carpeta, usar_detalles)
    cambio = guardar_dia(carpeta, fecha, notas, ediciones)
    print(f"{fecha}: {len(notas)} publicaciones ({'actualizado' if cambio else 'sin cambios'})")
    return cambio


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fecha", help="AAAA-MM-DD (por defecto, hoy en CDMX)")
    ap.add_argument("--dias-atras", type=int, default=1, help="cuántos días anteriores revisar también (por defecto 1)")
    ap.add_argument("--out", default="data", help="carpeta de salida (por defecto data)")
    ap.add_argument("--desde-archivo", help="usa un JSON ya descargado en vez de la red (pruebas)")
    ap.add_argument("--sin-detalles", action="store_true", help="no pide el detalle de notas sin título")
    args = ap.parse_args()

    carpeta = Path(args.out)
    carpeta.mkdir(parents=True, exist_ok=True)
    fin = date.fromisoformat(args.fecha) if args.fecha else datetime.now(TZ).date()

    if args.desde_archivo:
        respuesta = json.loads(Path(args.desde_archivo).read_text(encoding="utf-8"))
        procesar_dia(carpeta, fin, respuesta, usar_detalles=not args.sin_detalles)
        reconstruir_indices(carpeta)
        return 0

    errores = 0
    for atras in range(args.dias_atras, -1, -1):
        dia = fin - timedelta(days=atras)
        if dia > datetime.now(TZ).date():
            continue
        try:
            respuesta = pedir_json(f"{BASE}/notas/{dia:%d-%m-%Y}")
            procesar_dia(carpeta, dia, respuesta, usar_detalles=not args.sin_detalles)
        except RuntimeError as e:
            errores += 1
            print(f"{dia}: ERROR {e}", file=sys.stderr)
            if errores >= 3 and not any(carpeta.glob("20*.json")):
                print("Demasiados errores seguidos: se detiene para no gastar minutos.", file=sys.stderr)
                break
        time.sleep(0.5)
    reconstruir_indices(carpeta)
    return 1 if errores else 0


if __name__ == "__main__":
    sys.exit(main())
