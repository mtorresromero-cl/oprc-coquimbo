# Notas sobre el catálogo de autoridades (142 registros)

Datos investigados el 24 de agosto de 2026 a partir de fuentes oficiales/primarias
cuando fue posible. Detalle de confianza y fuente por registro en `autoridades_fuentes.csv`.

## Correcciones a supuestos iniciales de los docs

- **Diputados**: la Región de Coquimbo es un solo distrito electoral, el **Distrito 5**
  (no existe un "Distrito 6" en la región — ese corresponde a Valparaíso).
- **Senadores**: la circunscripción correcta es la **5ª Circunscripción Senatorial**
  (no la 4ª, que es Atacama). Coquimbo no tuvo elección senatorial en noviembre 2025;
  los 3 senadores actuales fueron electos en 2021 y su período va hasta 2030.
- **Concejales de Ovalle**: son 8, no 6 como las demás comunas de Limarí.

## Fuente principal usada para concejales y alcaldes

Las sentencias de calificación electoral del **Tribunal Electoral Regional de
Coquimbo** (tercoquimbo.cl) — el fallo judicial que declara "elegidos" a los
concejales de cada comuna — resultó ser más autoritativa que SERVEL o la prensa,
y fue la fuente principal para los 100 concejales (confianza alta en la gran
mayoría de los casos).

## Puntos de confianza media/baja a revisar

- **Los Vilos (alcalde)**: fuentes contradictorias sobre si Christian Gross Hidalgo
  milita en el PS (pacto Contigo Chile Mejor) o fue electo sin militancia. No resuelto.
- **Combarbalá (concejal Nelson Pizarro Cortés)**: la propia sentencia del TER tiene
  una inconsistencia interna entre el texto de fundamentos y la tabla de votos sobre
  qué lista/subpacto le corresponde. Se usó la tabla de votos.
- **Varios alcaldes independientes** (Ovalle, Combarbalá, Punitaqui, Canela,
  Salamanca, Río Hurtado): no se confirmó oficialmente si corrieron dentro de un
  pacto formal o completamente fuera de pacto.
- **Pactos de diputados/senadores**: BCN no lista el pacto electoral (solo partido);
  los pactos vienen de prensa regional, no de una fuente oficial primaria.
- El campo `pacto` queda vacío para gobernador y CORE — no se confirmó con SERVEL.

## Pendiente de verificación futura

Reconfirmar contra servel.cl directamente (no se pudo acceder en varias búsquedas)
para subir a confianza alta los registros marcados como "media" o "baja" en
`autoridades_fuentes.csv`.
