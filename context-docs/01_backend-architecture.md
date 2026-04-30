# Arquitectura Datakimia sobre Superset

## Objetivo

Describir solo la capa de adaptacion de Datakimia alrededor de Superset:

- Integracion de autenticacion corporativa.
- Convenciones de permisos y ownership para dashboards.
- Flujo de consumo desde Product Portal hacia Superset.

## Diagrama de capas

![Superset layered architecture](./img/backend-layered-architecture.svg)

## Capas (solo Datakimia)

- **Identidad corporativa**
  - Login federado (Google/Microsoft/Auth0 Datakimia).
  - Mapeo de identidad a usuarios/roles en Superset.
- **Autorizacion funcional**
  - Definicion de roles por perfil de negocio.
  - Asignacion de permisos sobre dashboards/datasets por dominio.
- **Publicacion BI**
  - Convenciones de ownership, nomenclatura y ciclo de vida de dashboards.
  - Reglas para promocion entre ambientes.

## Fuera de alcance

- Internals del core de Superset (ORM, engine specs, SQL Lab internals, etc.).
- Detalle de implementacion de funcionalidades nativas no modificadas por Datakimia.

## Evidencia en commits (Datakimia)

- **Roles/permisos base**
  - `8ddf33960f` crea rol Guest y default role inicial.
  - `2486cc209b` cambia default de Alpha a Guest.
  - `153f4cd40f` agrega rol publico Datakimia.
  - `1b9bb41ae1` ajusta rol default.
  - `a798317cac` crea rol `Client_Admin`.
- **Permisos sobre dashboards y acceso publico**
  - `f18c6ce6c0` agrega permisos de permalink a Guest.
  - `29fe7fc6cb` agrega `can_dashboard_permalink`.
  - `18eaeb6698` agrega `Can_explore_json` para Guest.
  - `d381177849` agrega permiso para descargar charts embebidos.
- **Auth/usuarios**
  - `4b143c499b` y `e4d8d684c3` introducen OAuth.
  - `59d3bee812` y `51329dc686` config/fix de provider Auth0.
  - `6f4fb210fe` y `4d3e592782` ajustes de identificación de Guest user.
