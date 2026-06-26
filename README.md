# OjoAlContrato 👁️

MCP de control político ciudadano sobre la contratación pública colombiana (SECOP).
Permite que cualquier persona, conversando con su agente (Claude Code, Codex, OpenCode),
audite a alcaldes, gobernadores, ministerios y cualquier ordenador del gasto.

> ⚖️ **OjoAlContrato no acusa a nadie.** Detecta señales y anomalías que ameritan
> preguntar, y ayuda a redactar un derecho de petición. "Esto es atípico, pregunta
> esto" ≠ "esto es un robo".

## Qué hace (V1)

- **`buscar_entidad(nombre)`** — encuentra entidades y su NIT.
- **`escanear_entidad(nit, desde, hasta)`** — audita toda la contratación y devuelve
  banderas rojas ordenadas por severidad (concentración en privados, proveedor
  recurrente, fraccionamiento, valores atípicos). Los convenios entre entidades
  públicas se muestran **marcados aparte** (suelen ser legítimos).
- **`historial_contratista(documento)`** — todos los contratos de un proveedor en el
  país (caza multicontratistas).
- **`benford(nit)`** — Ley de Benford sobre los montos (señal de cifras fabricadas).
- **`generar_derecho_peticion(...)`** — borrador formal de derecho de petición.

Fuente: **SECOP Integrado** (`rpmr-utcd`) en datos.gov.co — SECOP I + II, sin autenticación.

## Instalación

```bash
cd ojoalcontrato
pip install -r requirements.txt
```

(Opcional) sube el límite de tasa con un App Token gratuito de Socrata:
```bash
export SOCRATA_APP_TOKEN="tu_token"
```

## Conectarlo a tu agente

**Claude Code:**
```bash
claude mcp add ojoalcontrato -- python -m ojoalcontrato.server
```

**Config manual (Codex / OpenCode / Claude Desktop)** — añade a tu archivo de MCP:
```json
{
  "mcpServers": {
    "ojoalcontrato": {
      "command": "python",
      "args": ["-m", "ojoalcontrato.server"],
      "cwd": "/ruta/a/SECOP/ojoalcontrato"
    }
  }
}
```

## Ejemplo de uso (conversando con el agente)

> "Busca la alcaldía de Cartago"
> "Escanea el NIT 891900493"
> "Revisa el historial del contratista 830036940"
> "Genérame un derecho de petición con esos hallazgos"

## Estado

V1 — banderas heurísticas + Benford sobre datos del SECOP. Verificado contra casos
probados (Cartago alumbrado, UNGRD/MODERLINE). Ver `../DISEÑO.md` y `../BANCO_DE_PRUEBAS.md`.

Pendiente (V2): cruces guiados con RUES (juntas, fecha de creación), análisis de redes,
serie temporal, monitoreo por ventana, integración de viáticos/SINERGIA/obras inconclusas.
