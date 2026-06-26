"""
Cliente de datos del SECOP (Colombia Compra Eficiente) vía Socrata (datos.gov.co).

Fuente principal: SECOP Integrado (rpmr-utcd) — trae SECOP I + II juntos.
No requiere autenticación; un App Token opcional (env SOCRATA_APP_TOKEN) sube el rate limit.
"""
import os
import requests

BASE = "https://www.datos.gov.co/resource/{dataset}.json"

# Datasets confirmados (ver BANCO_DE_PRUEBAS.md)
INTEGRADO = "rpmr-utcd"   # SECOP I + II (campo `origen`)  -> fuente principal
SECOP_II = "jbjy-vk9h"    # detalle rico (rep. legal, adiciones, ordenador del gasto)

APP_TOKEN = os.environ.get("SOCRATA_APP_TOKEN")

# Campos de SECOP Integrado que usamos
SEL_CONTRATO = (
    "numero_del_contrato,fecha_de_firma_del_contrato,modalidad_de_contrataci_n,"
    "tipo_de_contrato,valor_contrato,nom_raz_social_contratista,documento_proveedor,"
    "objeto_del_proceso,origen,url_contrato"
)


def _get(dataset, params, timeout=60):
    headers = {"X-App-Token": APP_TOKEN} if APP_TOKEN else {}
    url = BASE.format(dataset=dataset)
    r = requests.get(url, params=params, headers=headers, timeout=timeout)
    r.raise_for_status()
    return r.json()


def _paginate(dataset, where, select=None, order=None, cap=12000, page=2000):
    rows, offset = [], 0
    while offset < cap:
        params = {"$where": where, "$limit": page, "$offset": offset}
        if select:
            params["$select"] = select
        if order:
            params["$order"] = order
        batch = _get(dataset, params)
        rows += batch
        if len(batch) < page:
            break
        offset += page
    return rows


def _esc(s):
    """Escapa comillas simples para SoQL."""
    return (s or "").replace("'", "''")


def buscar_entidades(nombre, limit=15):
    """Busca entidades por nombre. Devuelve NIT, municipio y nº de contratos."""
    where = f"upper(nombre_de_la_entidad) like '%{_esc(nombre.upper())}%'"
    params = {
        "$where": where,
        "$select": ("nombre_de_la_entidad,nit_de_la_entidad,municipio_entidad,"
                    "departamento_entidad,count(numero_del_contrato) as n"),
        "$group": "nombre_de_la_entidad,nit_de_la_entidad,municipio_entidad,departamento_entidad",
        "$order": "n desc",
        "$limit": limit,
    }
    return _get(INTEGRADO, params)


def contratos_entidad(nit, desde=None, hasta=None, cap=12000):
    """Todos los contratos de una entidad (por NIT), opcionalmente en un rango de fechas."""
    where = f"nit_de_la_entidad='{_esc(nit)}'"
    if desde:
        where += f" AND fecha_de_firma_del_contrato >= '{desde}'"
    if hasta:
        where += f" AND fecha_de_firma_del_contrato <= '{hasta}'"
    return _paginate(INTEGRADO, where, select=SEL_CONTRATO, cap=cap)


def contratos_contratista(documento, cap=6000):
    """Todos los contratos de un proveedor (por documento) en cualquier entidad del país."""
    where = f"documento_proveedor='{_esc(documento)}'"
    sel = ("nombre_de_la_entidad,nit_de_la_entidad,fecha_de_firma_del_contrato,"
           "modalidad_de_contrataci_n,valor_contrato,nom_raz_social_contratista,"
           "documento_proveedor,objeto_del_proceso,origen")
    return _paginate(INTEGRADO, where, select=sel, cap=cap)
