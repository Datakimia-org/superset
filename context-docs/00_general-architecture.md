# General Product Architecture

## Alcance de esta carpeta

Esta carpeta `context-docs/` documenta solo:

- Decisiones y convenciones de **Datakimia** sobre Superset.
- Integraciones y flujos operativos agregados para el producto.
- Setup inicial para operar ambientes (usuarios, roles/permisos, dashboards).

No busca re-documentar el core de Apache Superset.

## High-Level View

Datakimia opera Superset como capa BI conectada al Product Portal.  
La autenticacion centralizada (Google/Microsoft/Auth0 Datakimia) habilita acceso a Portal y BI con control de permisos por rol.

## Architecture Diagram

![General architecture](./img/general-architecture.svg)

## Notas

- El diagrama es de contexto de producto (no de implementacion interna de Superset).
- Las guias operativas de Datakimia estan en `01` a `06`.
- La migracion 4.1.1 → 6.1 esta en `migration/` (`00` stakeholders, `01` fork, `02` changelogs, `03` notas tecnicas).
