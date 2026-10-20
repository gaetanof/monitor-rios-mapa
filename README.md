# ¿Llega el agua?

Mapa de los barrios populares a orillas del Paraná, el Paraguay y el Uruguay donde la crecida podría llegar a las casas, día por día. Es parte de [Monitor de Ríos](https://x.com/MonitorDeRios).

**Ver el mapa:** https://gaetanof.github.io/monitor-rios-mapa/

## Cómo se calcula

1. **Altura del barrio sobre el río.** Se toman los píxeles del modelo de elevación SRTM (NASA, ~30 m) dentro del contorno de cada barrio del RENABAP y el nivel del agua más cercano en el mismo modelo. Se usa la cuarta parte más baja del barrio.
2. **Anclado a la escala.** El SRTM se tomó entre el 11 y el 22 de febrero de 2000, así que el agua que muestra es la de esos días. Se busca qué marcaba cada escala de Prefectura en esa fecha. El agua llega al barrio cuando la escala marca esa lectura más la altura del barrio.
3. **El río día por día.** Para los días pasados se usa la lectura de Prefectura. Para los futuros, el pronóstico oficial del INA y, donde no hay, el caudal de GloFAS convertido a altura con la relación altura–caudal de cada puerto en los últimos 3 años.
4. **Estado.** Agua probable si el río supera la parte baja del barrio. Posible si le falta menos de 1 m.

**Qué no tiene en cuenta:**
- El SRTM puede errar varios metros.
- No conoce defensas, terraplenes ni desagües, ni la lluvia local.
- No se estima en el embalse de Yacyretá ni en el Delta.

Es una estimación, no un aviso oficial.

## Fuentes

- Barrios: Registro Nacional de Barrios Populares (RENABAP), Secretaría de Integración Socio Urbana, CC BY 4.0.
- Elevación: SRTM (NASA) vía Terrain Tiles de AWS Open Data.
- Alturas y pronósticos: Prefectura Naval Argentina e INA (API alerta5).
- Caudal: GloFAS, Copernicus Emergency Management Service, vía Open-Meteo.
- Cartografía: Natural Earth. Imagen satelital: Esri World Imagery.

La idea de cruzar la crecida con los barrios populares es de [caudal](https://github.com/3-ppp/caudal), de Pedro ([@pppp_edro](https://x.com/pppp_edro)). El método y la interfaz de este mapa son propios.

## Correr localmente

```
pip install numpy pillow matplotlib
python -m mapa.puertos      # escalas, ancla SRTM e historial (API del INA)
python -m mapa.niveles      # alturas y pronósticos
python -m mapa.barrios      # barrios y elevación (opcional: ya están en mapa/datos)
python -m mapa.armar         # portada, datos y tramos en mapa/dist/
python -m mapa.paginas       # páginas de ríos, puertos y contenido + sitemap
python -m mapa.og            # imágenes para compartir
cd mapa/dist && python -m http.server
```

Código bajo licencia MIT.
