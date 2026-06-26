"""
Servidor MCP de OjoAlContrato.

Expone herramientas para que un agente (Claude Code / Codex / OpenCode) ayude a un
ciudadano a hacer control político sobre la contratación pública (SECOP).

REGLA LEGAL: la herramienta NUNCA afirma que alguien es corrupto. Marca señales/anomalías
y ayuda a formular un derecho de petición. "Esto es atípico, pregunta esto" ≠ "esto es un robo".

Ejecutar:  python -m ojoalcontrato.server
"""
from mcp.server.fastmcp import FastMCP

from . import secop, deteccion

mcp = FastMCP("ojoalcontrato")

_DISCLAIMER = (
    "\n\n⚠️ Esto NO prueba corrupción: son señales que ameritan preguntar. "
    "Verifícalas y, si persiste la duda, radica un derecho de petición."
)


def _money(x):
    try:
        return "$" + format(int(float(x)), ",d")
    except (TypeError, ValueError):
        return str(x)


@mcp.tool()
def buscar_entidad(nombre: str) -> str:
    """Busca entidades públicas por nombre (alcaldía, gobernación, ministerio, etc.).
    Devuelve el NIT (necesario para las demás herramientas), el municipio y cuántos
    contratos tiene cada una. Ejemplo: buscar_entidad("alcaldía de cartago")."""
    ents = secop.buscar_entidades(nombre)
    if not ents:
        return f"No encontré entidades con '{nombre}'. Prueba con otro término."
    out = [f"Entidades que coinciden con '{nombre}':\n"]
    for e in ents:
        out.append(
            f"• {e.get('nombre_de_la_entidad')} — NIT {e.get('nit_de_la_entidad')} "
            f"| {e.get('municipio_entidad','?')}, {e.get('departamento_entidad','?')} "
            f"| {e.get('n','?')} contratos"
        )
    out.append("\nUsa el NIT con escanear_entidad para auditarla.")
    return "\n".join(out)


@mcp.tool()
def escanear_entidad(nit: str, desde: str = "", hasta: str = "") -> str:
    """Audita TODA la contratación de una entidad (por NIT) y devuelve las banderas rojas
    ordenadas por severidad. Fechas opcionales en formato YYYY-MM-DD (ej. desde="2024-01-01").
    Los convenios entre entidades públicas se muestran MARCADOS aparte (suelen ser legítimos)."""
    rows = secop.contratos_entidad(nit, desde or None, hasta or None)
    if not rows:
        return f"No encontré contratos para el NIT {nit} en ese rango."
    r = deteccion.analizar(rows)
    ctx = r["contexto"]

    out = [f"AUDITORÍA — NIT {nit}", f"{r['n']} contratos | total {_money(ctx.get('total'))}"]
    if ctx.get("rango"):
        out.append(f"Periodo: {ctx['rango'][0]} a {ctx['rango'][1]} | Origen: {ctx.get('origen')}")
    out.append(
        f"Contexto: {ctx.get('directa_pct_n',0):.0f}% de los contratos son contratación directa "
        f"({ctx.get('directa_pct_val',0):.0f}% del valor). "
        "OJO: un % alto no es delito por sí solo; es contexto."
    )

    if r["hallazgos"]:
        top = r["hallazgos"][:12]
        out.append(f"\n🚩 BANDERAS ROJAS (ordenadas por severidad): {len(r['hallazgos'])}"
                   + (f" — muestro las {len(top)} más fuertes" if len(r["hallazgos"]) > len(top) else ""))
        for i, h in enumerate(top, 1):
            out.append(f"\n{i}. [{h['sev']}] {h['tipo']}\n   {h['detalle']}\n   → {h['guia']}")
    else:
        out.append("\nSin banderas fuertes con los datos disponibles del SECOP.")

    if r["convenios"]:
        out.append("\n🔵 CONVENIOS / TRANSFERENCIAS ENTRE ENTIDADES PÚBLICAS (revisar, no concluir):")
        for c in r["convenios"]:
            out.append(f"   • {c['nombre']} — {_money(c['val'])} ({c['share']:.0f}%), {c['n']} contrato(s)")
        out.append("   Normalmente legítimos. Riesgo a vigilar: que la entidad receptora "
                    "subcontrate a privados cercanos (triangulación).")

    return "\n".join(out) + _DISCLAIMER


@mcp.tool()
def historial_contratista(documento: str) -> str:
    """Muestra TODOS los contratos de un proveedor (por su NIT o cédula) en cualquier entidad
    del país. Sirve para detectar multicontratistas que contratan con varias entidades a la vez."""
    rows = secop.contratos_contratista(documento)
    if not rows:
        return f"No encontré contratos para el documento {documento}."
    total = sum(deteccion._num(c.get("valor_contrato")) for c in rows)
    ents = {}
    for c in rows:
        k = c.get("nombre_de_la_entidad") or "?"
        ents.setdefault(k, [0, 0.0])
        ents[k][0] += 1
        ents[k][1] += deteccion._num(c.get("valor_contrato"))
    nombre = rows[0].get("nom_raz_social_contratista")
    out = [f"HISTORIAL — {nombre} (doc {documento})",
           f"{len(rows)} contratos | {_money(total)} | en {len(ents)} entidad(es)"]
    if len(ents) >= 3:
        out.append("⚠️ Contrata con VARIAS entidades — revisar patrón de multicontratista.")
    out.append("\nPor entidad:")
    for k, (n, v) in sorted(ents.items(), key=lambda x: -x[1][1]):
        out.append(f"   • {k}: {n} contrato(s), {_money(v)}")
    return "\n".join(out) + _DISCLAIMER


@mcp.tool()
def benford(nit: str) -> str:
    """Corre la Ley de Benford sobre los montos de los contratos de una entidad.
    Una desviación grande del primer dígito sugiere montos posiblemente fabricados/manipulados."""
    rows = secop.contratos_entidad(nit)
    b = deteccion.benford_primer_digito(rows)
    if not b.get("suficiente"):
        return f"Datos insuficientes para Benford (solo {b.get('n',0)} montos válidos; se necesitan ≥50)."
    out = [f"LEY DE BENFORD — NIT {nit} ({b['n']} montos)",
           "Dígito | Esperado | Observado"]
    for d in range(1, 10):
        out.append(f"   {d}   |  {b['esperado'][d]:5.1f}% | {b['observado'][d]:5.1f}%")
    out.append(f"\nDesviación máxima: {b['desviacion_max']:.1f} puntos.")
    out.append("Desviación >8 puntos = vale la pena mirar con lupa (no es prueba por sí sola)." )
    return "\n".join(out) + _DISCLAIMER


@mcp.tool()
def contratos_riesgo(nit: str, desde: str = "", hasta: str = "", top: int = 20) -> str:
    """Lista los contratos individuales más atípicos de una entidad, UNO POR UNO y ordenados por
    nivel de riesgo (a diferencia de escanear_entidad, que da el resumen agregado). Úsala cuando
    el usuario quiera el detalle contrato a contrato ("los N contratos más raros"). Excluye los
    convenios entre entidades públicas. Fechas opcionales en formato YYYY-MM-DD."""
    rows = secop.contratos_entidad(nit, desde or None, hasta or None)
    if not rows:
        return f"No encontré contratos para el NIT {nit} en ese rango."
    r = deteccion.rankear_contratos(rows, top=top)
    if not r["top"]:
        return (f"Analicé {r['total']} contratos (sin duplicar, {r['privados']} a privados); "
                "ninguno disparó banderas individuales fuertes.")
    out = [f"CONTRATOS CON MAYOR RIESGO — NIT {nit}",
           f"{r['total']} contratos sin duplicar | {r['marcados']} marcados | top {min(top, len(r['top']))}"]
    for i, c in enumerate(r["top"], 1):
        out.append(f"\n{i}. {_money(c['valor'])} | {c['fecha']} | {c['modalidad']}")
        out.append(f"   {c['proveedor']} (doc {c['documento']})")
        out.append(f"   {c['objeto']}")
        out.append(f"   🚩 {' | '.join(c['razones'])}")
        if c.get("url"):
            out.append(f"   {c['url']}")
    return "\n".join(out) + _DISCLAIMER


@mcp.tool()
def generar_derecho_peticion(entidad: str, hallazgos: str, solicitante: str = "[Tu nombre]") -> str:
    """Redacta un borrador de derecho de petición formal (Art. 23 C.P.) dirigido a una entidad,
    pidiendo los soportes de los hallazgos detectados. 'hallazgos' es un texto con lo que se quiere preguntar."""
    return f"""DERECHO DE PETICIÓN

Señores
{entidad}
E. S. D.

Asunto: Solicitud de información — contratación pública (Art. 23 C.P.; Ley 1755 de 2015)

Yo, {solicitante}, identificado(a) como aparece al pie de mi firma, en ejercicio del
derecho fundamental de petición y del control social a la gestión pública (Ley 850 de 2003),
respetuosamente solicito la siguiente información:

{hallazgos}

De cada contrato referido, solicito: estudios previos, análisis del sector, certificado de
disponibilidad y registro presupuestal, propuesta del contratista, acta de inicio, informes
de supervisión y soportes de pago.

Fundamento mi solicitud en el principio de transparencia y publicidad de la función
administrativa. Agradezco respuesta dentro de los términos legales (10 días hábiles para
documentos; 15 días hábiles en general).

Notificaciones: [correo / dirección]
Atentamente,

{solicitante}
C.C. __________________
""" + "\n(Borrador generado por OjoAlContrato — revísalo y ajústalo antes de radicar.)"


def main():
    mcp.run()


if __name__ == "__main__":
    main()
