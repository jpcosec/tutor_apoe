# Notas para incrustar visualizaciones GeoGebra en LAETEC

## Matriz 2×2 por vector 2×1

Archivo: `Matriz_vector_GeoGebra.html`.

Una vez publicado en un servidor HTTPS, sustituye `TU-DOMINIO` por la dirección
real del archivo:

```html
<iframe
  src="https://TU-DOMINIO/geogebra/Matriz_vector_GeoGebra.html"
  width="100%"
  height="700"
  title="Matriz 2×2 por vector 2×1"
  loading="lazy">
</iframe>
```

No uses `http://127.0.0.1:8000` ni una ruta `file:///`: ambas solo funcionan
en el computador local. El HTML requiere conexión a internet para cargar la
aplicación de GeoGebra.

## Convención para recursos futuros

Cuando se prepare una visualización para LAETEC, agrega una sección con:

1. Nombre del archivo HTML.
2. URL pública definitiva.
3. Bloque `iframe` con título y altura apropiados.
4. Una nota de dependencias externas, si las tiene.
