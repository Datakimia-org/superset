# Buenas Practicas (Datakimia en Superset)

## Regla de oro de documentacion

- Documentar decisiones de Datakimia, no internals del core de Superset.
- Cada decision debe incluir: motivo, impacto, y rollback.

## Usuarios y permisos

- Aplicar minimo privilegio por perfil.
- Evitar usar cuentas admin para validacion funcional.
- Revisar permisos por dashboard y por dataset antes de publicar.

## Dashboards

- Definir owner funcional y owner tecnico.
- Mantener nomenclatura consistente (area, dominio, KPI).
- Validar filtros, acceso y performance con rol final.

## Operacion

- Cambios en auth/permisos deben salir con checklist de verificacion.
- Cambios en flags deben documentar estado por ambiente.
- Cambios en release deben contrastarse con `UPDATING.md`.

## Minimo de entrega para cambios Datakimia

1. Nota corta de cambio.
2. Impacto en usuarios/roles/dashboards.
3. Evidencia de prueba (al menos smoke).
4. Plan de rollback.
