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
MAX_DETALLES_POR_DIA = 60
DIAS_EN_INDICE = 400
DIAS_EN_BUSCADOR = 180

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
                r"\bpedimento", r"regimen(es)? aduanero"],
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


def titulo_desde_detalle(cod):
    """Para notas sin título en el índice: lo busca en el detalle de la nota."""
    det = pedir_json(f"{BASE}/notas/nota/{cod}")
    nota = det.get("Nota") or {}
    titulo = (nota.get("titulo") or "").strip()
    if titulo and titulo != "null":
        return titulo
    contenido = nota.get("cadenaContenido") or ""
    m = re.search(r"<h1[^>]*>(.*?)</h1>", contenido, re.S | re.I)
    if m and limpiar_html(m.group(1)):
        return limpiar_html(m.group(1))
    return ""


def notas_del_dia(respuesta):
    """Une las ediciones del día en una lista de (edicion, nota_cruda)."""
    salida = []
    for clave, codigo in EDICIONES:
        for crudo in sorted(respuesta.get(clave) or [], key=lambda n: n.get("orden") or 0):
            salida.append((codigo, crudo))
    return salida


def construir_notas(crudas, fecha, usar_detalles=True):
    notas, detalles = [], 0
    for edicion, c in crudas:
        cod = c.get("codNota")
        es_aviso = c.get("tipoNota") == "AVISO" or c.get("codOrgaUno") == "AV"
        titulo = (c.get("titulo") or "").strip()
        if titulo == "null":
            titulo = ""
        if not titulo and not es_aviso and usar_detalles and detalles < MAX_DETALLES_POR_DIA:
            detalles += 1
            time.sleep(0.4)
            try:
                titulo = titulo_desde_detalle(cod)
            except RuntimeError as e:
                print(f"  aviso: sin detalle de {cod}: {e}", file=sys.stderr)
        dep_largo = c.get("codOrgaDos") if c.get("codOrgaDos") not in (None, "null") else ""
        poder = c.get("nombreCodOrgaUno") or ""
        dep_texto = f"{poder} {dep_largo}"
        nota = {
            "id": cod,
            "titulo": titulo or "Publicación sin título en el índice (ábrela para ver el texto)",
            "dep": nombre_bonito(dep_largo) or nombre_bonito(poder),
            "edicion": edicion,
            "pagina": c.get("pagina") or 0,
            "temas": clasificar(titulo, dep_texto, es_aviso),
            "url": f"https://www.dof.gob.mx/nota_detalle.php?codigo={cod}&fecha={fecha:%d/%m/%Y}",
        }
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
                buscador.append({"f": dia["fecha"], "i": n["id"], "t": n["titulo"], "d": n["dep"], "tm": n["temas"]})
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
    notas = construir_notas(crudas, fecha, usar_detalles)
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
