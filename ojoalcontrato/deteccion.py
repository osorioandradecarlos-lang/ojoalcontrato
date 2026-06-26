"""
Motor de detección de banderas rojas de OjoAlContrato.

Filosofía (decisión de diseño): MARCAR + GUIAR, sin baseline estadístico.
- Se marca todo lo que esté alto según las reglas tipo Briceño.
- Se ordena por SEVERIDAD (las señales que discriminan más van arriba).
- Los convenios interadministrativos NO se ocultan: se muestran MARCADOS para que
  el usuario juzgue (y para cazar la triangulación).
- El "% a dedo" es CONTEXTO, no veredicto.
La herramienta señala y explica; el ciudadano, con la guía, dictamina.
"""
import statistics
import collections

# Pistas de que el "proveedor" es en realidad otra entidad pública
# (convenio/transferencia Estado-Estado, normalmente legítimo).
PUBLICO_HINTS = [
    "MUNICIPIO", "ALCALD", "GOBERNACI", "DEPARTAMENTO", "NACION", "NACIONAL",
    "E.S.P", "ESP ", "E.S.E", "ESE ", "EMPRESA DE SERVICIOS", "EMPRESAS MUNICIPALES",
    "UNIVERSIDAD", "INSTITUTO", "FONDO", "SECRETARIA", "AREA METROPOLITANA",
    "CORPORACION AUTONOMA", "HOSPITAL", "INSTITUCION EDUCATIVA", "UNIDAD ADMINISTRATIVA",
    "FEDERACION DE MUNICIPIOS", "MINISTERIO", "AGENCIA NACIONAL",
    # Institutos descentralizados y empresas industriales y comerciales del Estado
    "E.I.C.E", "EICE", "EMPRESA INDUSTRIAL Y COMERCIAL", "BOMBEROS",
    "INFITULUA", "INFIVALLE", "INFI", "BENEFICENCIA", "LOTERIA", "IMDER",
    "INSTITUTO MUNICIPAL", "EMPRESA SOCIAL DEL ESTADO", "CUERPO DE BOMBEROS",
]


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def _es_publico(nombre, tipo_contrato="", objeto=""):
    n = (nombre or "").upper()
    if any(h in n for h in PUBLICO_HINTS):
        return True
    # El campo tipo a veces no lo dice, pero el objeto sí ("CONTRATO INTERADMINISTRATIVO")
    txt = (tipo_contrato or "").upper() + " " + (objeto or "").upper()
    return "INTERADMINISTRATIV" in txt or "CONVENIO" in txt


# Marcadores de razón social de EMPRESA (vs persona natural)
EMPRESA_HINTS = [
    "S.A.S", "SAS", "S.A", "LTDA", "LIMITADA", "E.U", "& CIA", "Y CIA", "COMPAÑIA",
    "FUNDACION", "ASOCIACION", "CORPORACION", "COOPERATIVA", "UNION TEMPORAL",
    "CONSORCIO", "GRUPO", "SOCIEDAD", "EMPRESA", "ESP", "S A S",
]

_JUNK_DOCS = {"NO DEFINIDO", "NODEFINIDO", "NO_DEFINIDO", "?", "", "0"}


def _es_junk(doc, nombre):
    return (str(doc).strip().upper() in _JUNK_DOCS) or ((nombre or "").strip().upper() in _JUNK_DOCS)


def _es_empresa(nombre, doc):
    n = (nombre or "").upper()
    if any(h in n for h in EMPRESA_HINTS):
        return True
    # NIT de empresa: 9 dígitos que suelen empezar en 8 o 9
    d = str(doc).strip()
    return d.isdigit() and len(d) == 9 and d[0] in "89"


def _dedupe(rows):
    """SECOP Integrado trae filas repetidas (la misma de SECOP I y II). Las quitamos."""
    seen, out = set(), []
    for c in rows:
        k = (c.get("numero_del_contrato"), c.get("valor_contrato"),
             c.get("documento_proveedor"), c.get("fecha_de_firma_del_contrato"))
        if k in seen:
            continue
        seen.add(k)
        out.append(c)
    return out


def analizar(rows):
    """Analiza los contratos de una entidad. Devuelve dict con contexto + hallazgos."""
    rows = _dedupe(rows)
    res = {"n": len(rows), "contexto": {}, "hallazgos": [], "convenios": []}
    if not rows:
        return res

    total = sum(_num(c.get("valor_contrato")) for c in rows)
    res["contexto"]["total"] = total
    res["contexto"]["origen"] = dict(collections.Counter(c.get("origen") for c in rows))
    fechas = sorted(f[:10] for c in rows if (f := c.get("fecha_de_firma_del_contrato")))
    if fechas:
        res["contexto"]["rango"] = (fechas[0], fechas[-1])

    # --- CONTEXTO: % contratación directa (no es veredicto) ---
    directa = [c for c in rows if "directa" in (c.get("modalidad_de_contrataci_n") or "").lower()]
    valdir = sum(_num(c.get("valor_contrato")) for c in directa)
    res["contexto"]["directa_pct_n"] = 100 * len(directa) / len(rows)
    res["contexto"]["directa_pct_val"] = (100 * valdir / total) if total else 0

    # --- Agrupar por proveedor (separando públicos de privados) ---
    prov = collections.defaultdict(lambda: {"n": 0, "val": 0.0, "nombre": "", "publico": False})
    for c in rows:
        doc = c.get("documento_proveedor") or "?"
        p = prov[doc]
        p["n"] += 1
        p["val"] += _num(c.get("valor_contrato"))
        p["nombre"] = c.get("nom_raz_social_contratista") or p["nombre"]
        if _es_publico(c.get("nom_raz_social_contratista"), c.get("tipo_de_contrato"),
                       c.get("objeto_del_proceso")):
            p["publico"] = True

    privados = [(d, p) for d, p in prov.items()
                if not p["publico"] and not _es_junk(d, p["nombre"])]
    publicos = [(d, p) for d, p in prov.items() if p["publico"]]

    # Convenios / transferencias Estado-Estado: se MUESTRAN marcados
    for d, p in sorted(publicos, key=lambda x: -x[1]["val"])[:5]:
        share = (100 * p["val"] / total) if total else 0
        res["convenios"].append({
            "nombre": p["nombre"], "doc": d, "n": p["n"], "val": p["val"], "share": share,
        })

    # --- HALLAZGO: concentración en un proveedor PRIVADO ---
    for d, p in sorted(privados, key=lambda x: -x[1]["val"])[:3]:
        share = (100 * p["val"] / total) if total else 0
        if share >= 10:
            res["hallazgos"].append({
                "sev": 90 if share >= 30 else (78 if share >= 15 else 66),
                "tipo": "Concentración en un proveedor privado",
                "detalle": f"{p['nombre']} (doc {d}) concentra ${p['val']:,.0f} "
                           f"({share:.0f}% del total) en {p['n']} contrato(s).",
                "guia": "Revisa: ¿qué objetos contrató? ¿cuándo se creó la empresa (RUES)? "
                        "¿quiénes son los socios? ¿tienen vínculo con la entidad o el mandatario?",
            })

    # --- HALLAZGO: proveedor recurrente (muchos contratos con la misma entidad) ---
    for d, p in sorted(privados, key=lambda x: -x[1]["n"])[:3]:
        if p["n"] >= 15:
            res["hallazgos"].append({
                "sev": 68,
                "tipo": "Proveedor recurrente (muchos contratos con la misma entidad)",
                "detalle": f"{p['nombre']} (doc {d}): {p['n']} contratos por ${p['val']:,.0f}.",
                "guia": "Usa historial_contratista con su documento para ver si también "
                        "contrata con OTRAS entidades (patrón de multicontratista nacional).",
            })

    # --- HALLAZGO: posible fraccionamiento (solo EMPRESAS, no personas naturales) ---
    fracc = []
    for d, p in privados:
        if not _es_empresa(p["nombre"], d):
            continue
        chicos = [c for c in rows
                  if c.get("documento_proveedor") == d and 0 < _num(c.get("valor_contrato")) < 50_000_000]
        if len(chicos) >= 8:
            fracc.append((len(chicos), p["nombre"], d))
    for cnt, nombre, d in sorted(fracc, reverse=True)[:3]:
        res["hallazgos"].append({
            "sev": 70,
            "tipo": "Posible fraccionamiento (empresa con muchos contratos pequeños)",
            "detalle": f"{nombre} (doc {d}): {cnt} contratos por debajo de $50M. "
                       "Partir un contrato grande en varios chicos evita la licitación.",
            "guia": "Revisa si los objetos son iguales/complementarios y las fechas cercanas.",
        })

    # --- HALLAZGO: valores atípicos (privados) ---
    vals = [v for c in rows if (v := _num(c.get("valor_contrato"))) > 0]
    if vals:
        med = statistics.median(vals)
        outs = [c for c in rows
                if _num(c.get("valor_contrato")) > med * 10
                and not _es_publico(c.get("nom_raz_social_contratista"), c.get("tipo_de_contrato"),
                                    c.get("objeto_del_proceso"))]
        for c in sorted(outs, key=lambda c: -_num(c.get("valor_contrato")))[:3]:
            res["hallazgos"].append({
                "sev": 64,
                "tipo": "Valor atípico (>10× la mediana de la entidad)",
                "detalle": f"${_num(c.get('valor_contrato')):,.0f} — "
                           f"{(c.get('objeto_del_proceso') or '')[:75]} — {c.get('nom_raz_social_contratista')}",
                "guia": "Compara el precio con contratos del mismo objeto en otras entidades.",
            })

    res["hallazgos"].sort(key=lambda h: -h["sev"])
    return res


def benford_primer_digito(rows):
    """Test de Ley de Benford sobre los valores de los contratos (señal de montos fabricados)."""
    esperado = {1: 30.1, 2: 17.6, 3: 12.5, 4: 9.7, 5: 7.9, 6: 6.7, 7: 5.8, 8: 5.1, 9: 4.6}
    digs = []
    for c in rows:
        v = _num(c.get("valor_contrato"))
        if v > 0:
            d = int(str(int(v))[0])
            if d:
                digs.append(d)
    n = len(digs)
    if n < 50:
        return {"n": n, "suficiente": False}
    cont = collections.Counter(digs)
    obs = {d: 100 * cont.get(d, 0) / n for d in range(1, 10)}
    desv = max(abs(obs[d] - esperado[d]) for d in range(1, 10))
    return {"n": n, "suficiente": True, "esperado": esperado, "observado": obs, "desviacion_max": desv}


def rankear_contratos(rows, top=20):
    """Lista CONTRATO POR CONTRATO los más atípicos, ordenados por nivel de riesgo.
    Complementa a `analizar` (que da el agregado de la entidad). Excluye convenios y basura."""
    rows = _dedupe(rows)
    privados = [c for c in rows
                if not _es_publico(c.get("nom_raz_social_contratista"), c.get("tipo_de_contrato"),
                                   c.get("objeto_del_proceso"))
                and not _es_junk(c.get("documento_proveedor"), c.get("nom_raz_social_contratista"))]
    vals = [v for c in privados if (v := _num(c.get("valor_contrato"))) > 0]
    med = statistics.median(vals) if vals else 0
    cnt = collections.Counter(c.get("documento_proveedor") for c in privados)

    marcados = []
    for c in privados:
        v = _num(c.get("valor_contrato"))
        modal = (c.get("modalidad_de_contrataci_n") or "").lower()
        razones, score = [], 0
        if med and v > med * 10:
            razones.append("valor atípico (>10× la mediana de la entidad)"); score += 3
        if "directa" in modal and med and v > med * 3:
            razones.append("contratación directa de monto alto"); score += 2
        if cnt.get(c.get("documento_proveedor"), 0) >= 5:
            razones.append(f"proveedor recurrente ({cnt[c.get('documento_proveedor')]} contratos)"); score += 2
        if razones:
            marcados.append({
                "score": score, "valor": v, "razones": razones,
                "proveedor": c.get("nom_raz_social_contratista"),
                "documento": c.get("documento_proveedor"),
                "fecha": (c.get("fecha_de_firma_del_contrato") or "")[:10],
                "modalidad": c.get("modalidad_de_contrataci_n"),
                "objeto": (c.get("objeto_del_proceso") or "")[:150],
                "url": c.get("url_contrato"),
            })
    marcados.sort(key=lambda x: (-x["score"], -x["valor"]))
    return {"total": len(rows), "privados": len(privados), "marcados": len(marcados), "top": marcados[:top]}
