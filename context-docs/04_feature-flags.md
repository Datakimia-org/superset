# Feature Flags (foco Datakimia)

## Regla principal

- Documentar solo flags que Datakimia activa/desactiva explicitamente.
- No listar todo el catalogo de flags de Superset.

## Plantilla de documentacion por flag

- **Flag**: nombre exacto
- **Decision Datakimia**: ON/OFF por ambiente
- **Motivo**: problema de producto/operacion que resuelve
- **Impacto**: usuarios, permisos o dashboards afectados
- **Rollback**: como volver al estado anterior

## Flags de interes operativo

- `EMBEDDED_SUPERSET` (si aplica a integracion portal)
- `DASHBOARD_RBAC` (si se usa control fino por dashboard)
- Cualquier flag no-default que Datakimia decida operar

## Evidencia de uso en commits Datakimia

- `7f3958f6aa`: agrega flag para guardar filtros en dashboard.
- `3c7b532b64`: habilita Save Filters Set por defecto.
- `255629119a`: deshabilita Save Filters por defecto.
- `37ffad21a6` y `ebcf7a6ef1`: habilitan `HORIZONTAL_FILTER_BAR`.

Nota: confirmar estado final por ambiente en configuracion activa, no solo por historial.

## Referencia

Catalogo completo de estado/madurez: `RESOURCES/FEATURE_FLAGS.md`.
