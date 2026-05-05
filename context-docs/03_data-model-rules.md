# Reglas de Modelo de Datos (Datakimia)

## Alcance

Estas reglas cubren solo convenciones de Datakimia para modelar y exponer datos en Superset.

## Principios

- Los datasets publicados deben representar entidades de negocio estables.
- Evitar logica de negocio compleja incrustada por dashboard; preferir capas de datos previas.
- Convenciones de naming consistentes para datasets, metricas y dashboards.

## Reglas practicas

- Definir owners de dataset (funcional + tecnico).
- Marcar claramente datasets certificados para consumo de negocio.
- Versionar cambios rompientes en definiciones de metrica o columnas.

## Checklist antes de publicar dashboards

1. Dataset con nombre y descripcion de negocio.
2. Metricas criticas validadas con stakeholders.
3. Permisos revisados por rol objetivo.
4. Dashboard testeado con cuenta no-admin.

## Fuera de alcance

- Explicacion del modelo interno del metadata DB de Superset.
- Mecanica interna de migraciones core sin customizacion Datakimia.
