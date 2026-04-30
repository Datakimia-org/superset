# Runbook de Agentes (Datakimia + Superset)

## Objetivo

Checklist operativo para cambios de Datakimia sobre Superset.

## Flujo estandar

1. Install dependencies
   - seguir setup del repo
2. Levantar entorno local
   - `docker compose up -d`
3. Validar que la configuracion Datakimia de auth/permisos cargue correctamente
4. Ejecutar pruebas puntuales sobre cambios tocados
5. Verificar smoke de acceso a dashboards segun rol

## Comandos utiles

- `docker compose up -d`
- `docker compose logs -f`
- `pytest` (cuando aplique)

## Checklist de setup inicial (usuarios, permisos, dashboards)

1. **Usuarios**
   - crear usuario admin tecnico
   - crear usuarios por perfil (viewer/editor/admin BI)
2. **Roles y permisos**
   - basarse en roles estandar de Superset
   - agregar solo permisos minimos necesarios
   - validar acceso por rol en UI
3. **Dashboards**
   - asignar owner funcional y owner tecnico
   - publicar en carpeta/espacio convenido
   - probar visibilidad por rol antes de release

## Criterio de documentacion

- Si un cambio es core de Superset y no fue modificado por Datakimia, no documentarlo aqui.
- Documentar solo decision local, impacto operativo y pasos de configuracion.

## Validacion basada en historial del repo

Antes de asumir una regla operativa, validar evidencia en commits Datakimia:

- **Roles y defaults**: `8ddf33960f`, `2486cc209b`, `153f4cd40f`, `1b9bb41ae1`.
- **Permisos Guest/Public**: `f18c6ce6c0`, `29fe7fc6cb`, `18eaeb6698`, `d550b5cf04`.
- **Auth providers**: `4b143c499b`, `e4d8d684c3`, `59d3bee812`, `51329dc686`.
- **Acceso dashboard/permalink**: `aaf7e4f878`, `4ff79c237a`.

Si un comportamiento no aparece en este tipo de commits, tratarlo como supuesto y no como regla.
