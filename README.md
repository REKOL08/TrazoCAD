# Planos2DWG

Herramienta de línea de comandos que convierte planos escaneados en PDF (blanco
y negro, de arquitectura o ingeniería) en archivos **DXF editables**, con
conversión opcional a **DWG real** si tienes instalado el conversor gratuito
de Autodesk/ODA. Pensada para que un arquitecto o ingeniero sin experiencia en
programación pueda instalarla y usarla en pocos minutos, arrastrando archivos.

## ⚠️ Qué hace y qué NO hace esta herramienta (leer antes de usar)

El DXF que se genera tiene **capas**, para poder ver solo lo limpio o todo:

| Capa | Qué contiene | Calidad |
|---|---|---|
| `MUROS` | Caras de muros como líneas **rectas, paralelas y enderezadas** (horizontal/vertical exactas), con esquinas prolongadas hasta cruzarse y los extremos libres cerrados con un remate | Limpia, pero **parcial**: faltan tramos. Se descartan las filas de cotas (otra separación entre líneas) y los contornos cortos aislados como muebles |
| `ARCOS` | Arcos y círculos reales (`ARC`/`CIRCLE`): muros curvos, puertas batientes, escaleras circulares | Buena en curvas grandes; puede haber algún arco falso o faltar uno |
| `EJES` | Ejes de trazo y punto (tipo de línea `CENTER`): la cuadrícula de letras y números y algunos radiales | Buena en la cuadrícula; puede faltar algún eje radial y no toma como eje las líneas de corte continuas |
| `CALCADO_REFERENCIA` | Calco fiel de toda la tinta del escaneo (textos, símbolos, cotas, curvas) como polilíneas, con las líneas largas suavizadas y enderezadas | Se ve como el PDF; es una **referencia para calcar encima**, apágala (`LAYER OFF`) para ver solo lo limpio |

- **No son objetos CAD "inteligentes"**: los textos no son `TEXT` editable
  (están calcados en `CALCADO_REFERENCIA`), no hay puertas, ventanas ni
  símbolos como bloques, y los muros no tienen relleno ni espesor como objeto.
  La salida es una **base para que un dibujante redibuje**, no un plano
  terminado.
- Modo `lineas` (`--modo lineas`): solo líneas rectas sueltas, sin muros ni
  textos. Más limpio pero muy incompleto; no se recomienda.
- **Si el plano sale de lado, usa `--rotar 90`** o arrastra los PDF sobre
  `convertir_girado_90.bat`. El escaneo también se **endereza** solo si viene
  ligeramente inclinado.
- **Rótulo del plano:** el recuadro de datos del plano (cajetín) se confunde
  con muros. Usa `--ignorar-inferior 0.17` para ignorar el 17 % inferior de la
  hoja al buscar muros y ejes (`convertir_girado_90.bat` ya lo incluye).
- La fidelidad depende de la calidad del escaneo. Escanea a 300-400 DPI en
  blanco y negro o gris.
- **No genera un archivo `.dwg` binario por sí sola.** Ninguna librería libre
  de Python puede escribir `.dwg` (es un formato propietario de Autodesk). Lo
  que el script genera de forma nativa es **DXF**, que AutoCAD abre
  exactamente igual que un DWG (`Archivo > Abrir`). Si necesitas el archivo
  con extensión `.dwg` literal, instala el conversor gratuito **ODA File
  Converter** (ver [sección dedicada](#convertir-a-dwg-real-opcional)) y el
  script lo usará automáticamente.
- Si ya tienes el **DWG original** del plano, eso siempre dará mejor
  resultado que cualquier conversión desde un escaneo.

## Requisitos del sistema

- Windows 10 u 11.
- [Python 3.10 o superior](https://www.python.org/downloads/) instalado
  (marca la casilla **"Add python.exe to PATH"** durante la instalación).
- 4 GB de RAM como mínimo (8 GB recomendado si vas a convertir planos muy
  grandes o en lote).
- Alrededor de 500 MB libres en disco para las dependencias.
- (Opcional) [ODA File Converter](https://www.opendesign.com/guestfiles/oda_file_converter)
  gratuito, solo si quieres archivos `.dwg` reales además de `.dxf`.

## Instalación (menos de 5 minutos)

1. **Clona o descarga este repositorio.**

   ```bash
   git clone https://github.com/REKOL08/planos2dwg.git
   cd planos2dwg
   ```

   Si no usas Git, también puedes descargar el repositorio como ZIP desde
   GitHub (botón verde **Code > Download ZIP**) y descomprimirlo.

2. **Ejecuta el instalador** haciendo doble clic en `instalar.bat`.

   Este script crea automáticamente un entorno virtual (`.venv`) e instala
   todas las dependencias (`pymupdf`, `opencv-python`, `numpy`, `ezdxf`). No
   necesitas escribir ningún comando.

   Si prefieres instalarlo manualmente desde una terminal:

   ```bash
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. Listo. Ya puedes convertir planos arrastrándolos sobre `convertir.bat`.

## Cómo usar

### Opción 1: Arrastrar y soltar (recomendada)

Arrastra uno o varios archivos PDF — o una carpeta completa con PDF dentro,
estén donde estén en tu PC — sobre el ícono de **`convertir.bat`**. Se
abrirá una consola mostrando el progreso y, al terminar, los archivos
`.dxf` (y `.dwg` si corresponde) quedarán organizados dentro de la
subcarpeta **`Convertidos_DWG`**, creada automáticamente **dentro de esta
misma carpeta del programa** (no junto al PDF original). El nombre de esa
subcarpeta es fijo: el programa nunca pregunta cómo llamarla.

> Cada conversión genera un archivo **nuevo con la fecha y hora en el nombre**
> (por ejemplo `planta1_20261002_154715.dxf`). Así nunca se sobrescribe un
> DXF que AutoCAD, OneDrive o el antivirus tengan abierto o bloqueado (si no,
> AutoCAD avisa que el archivo "está en uso o es de solo lectura"). Borra a
> mano las versiones viejas que ya no necesites.

### Opción 2: Sin arrastrar nada

Haz doble clic en `convertir.bat` sin soltar ningún archivo encima. Se abrirá
una ventana para que selecciones la carpeta donde están tus planos PDF.

### Opción 3: Desde una terminal (usuarios avanzados)

```bash
.venv\Scripts\activate
python main.py "C:\Planos\Edificio A\planta1.pdf"
python main.py "C:\Planos\Edificio A"          # convierte todos los PDF de la carpeta
python main.py planta1.pdf --dpi 400            # usar más resolución
python main.py planta1.pdf --rotar 90           # el escaneo está de lado
python main.py planta1.pdf --ignorar-inferior 0.17  # no confundir el rótulo con muros
python main.py planta1.pdf --solo-limpio        # solo MUROS y EJES, sin el calcado de referencia
python main.py planta1.pdf --grosor-muro 1.0    # espesor de muro en mm sobre el papel (si no, se mide solo)
python main.py planta1.pdf --modo lineas        # solo líneas rectas (modo alterno)
python main.py planta1.pdf --no-dwg             # generar solo .dxf, sin intentar .dwg
python main.py planta1.pdf --verbose            # ver más detalle en consola/log
```

## Ejemplo de entrada/salida

```
Antes:
  Planos/
    planta-primer-piso.pdf           <- tu PDF, en cualquier carpeta

  planos2dwg/                        <- la carpeta de este programa
    convertir.bat
    main.py
    ...

Después de arrastrar planta-primer-piso.pdf sobre convertir.bat:
  Planos/
    planta-primer-piso.pdf           <- no se toca ni se mueve

  planos2dwg/
    convertir.bat
    main.py
    Convertidos_DWG/                 <- se crea aquí, no junto al PDF
      planta-primer-piso.dxf         <- siempre se genera
      planta-primer-piso.dwg         <- solo si está instalado ODA File Converter
```

Un PDF de varias páginas genera un `.dxf`/`.dwg` por cada página, con el
sufijo `_p1`, `_p2`, etc. (por ejemplo `planta-primer-piso_p2.dxf`).

## Convertir a DWG real (opcional)

1. Descarga **ODA File Converter** gratis desde el sitio oficial de la Open
   Design Alliance: https://www.opendesign.com/guestfiles/oda_file_converter
2. Instálalo con las opciones por defecto.
3. Vuelve a ejecutar `convertir.bat` normalmente: el script detecta la
   instalación automáticamente y, además del `.dxf`, dejará un `.dwg`.

> **Nota de licencia:** ODA File Converter es gratuito para uso personal y,
> según los términos publicados por Open Design Alliance, de uso libre salvo
> que seas miembro/no miembro en contextos específicamente restringidos;
> revisa los términos de uso en el sitio oficial si vas a usarlo en un
> contexto comercial y tienes dudas.

Si no instalas ODA File Converter, el script sigue funcionando normalmente y
entrega solo archivos `.dxf`, que AutoCAD abre sin ningún problema adicional.

## Estructura del proyecto

```
planos2dwg/
├── main.py                 # Punto de entrada (CLI + selector de carpeta)
├── convertir.bat           # Arrastra tus PDF aquí
├── convertir_girado_90.bat # Igual, para escaneos que salen de lado
├── instalar.bat            # Instalador de un clic
├── requirements.txt        # Dependencias de producción
├── requirements-dev.txt    # Dependencias + pytest para desarrollo
├── setup.py                # Instalación opcional vía pip (pip install -e .)
├── src/
│   ├── pdf_processor.py    # PDF -> imágenes (PyMuPDF)
│   ├── muros.py            # Muros (pares de caras paralelas), remates y ejes (OpenCV LSD)
│   ├── arcos.py            # Arcos y círculos (RANSAC sobre trocitos de línea)
│   ├── deskew.py           # Enderezado de escaneos inclinados
│   ├── vectorizer.py       # Imagen -> calcado fiel de la tinta (OpenCV)
│   ├── line_detector.py    # Modo alterno: imagen -> líneas rectas
│   ├── dxf_writer.py       # Segmentos -> archivo DXF (ezdxf)
│   ├── dwg_converter.py    # DXF -> DWG real (ODA File Converter, opcional)
│   ├── converter.py        # Orquesta el pipeline completo
│   └── utils.py            # Logging y validaciones
├── tests/                  # Pruebas unitarias (pytest)
└── logs/                   # Se crea automáticamente; registro de cada ejecución
```

## Limitaciones conocidas

- Pensado para planos **en blanco y negro o escala de grises**; planos a
  color con fondos o tramas complejas generan más ruido.
- No reconoce texto, cotas, símbolos ni bloques como objetos CAD: los calca
  como dibujo (se ven, pero no se pueden editar como texto o bloque).
- Si abres un `.dxf` mientras lo vuelves a convertir, el nuevo se guarda con
  la hora en el nombre (Windows no deja sobrescribir un archivo abierto).
- Escaneos torcidos (sin enderezar) o de baja resolución (menos de ~200 DPI)
  producen resultados pobres; se recomienda escanear a 300–400 DPI.
- El `.dwg` real requiere instalar ODA File Converter por separado (no se
  incluye en este repositorio por ser una herramienta de terceros).
- Cada página se procesa de forma independiente; no intenta alinear ni
  unir planos de varias hojas en un solo dibujo.

## Solución de problemas

- **"No se encontró Python"**: reinstala Python marcando "Add to PATH", o usa
  `instalar.bat`, que valida esto automáticamente.
- **"No se detectó ninguna línea en el PDF"**: el escaneo puede ser muy claro,
  estar en color o tener muy baja resolución. Prueba escaneando de nuevo en
  blanco y negro a 300 DPI o más.
- Revisa `logs/conversion.log` para el detalle completo de cualquier error.

## Contacto / soporte

Para reportar problemas o proponer mejoras, abre un *issue* en este
repositorio de GitHub.

## Créditos y licencia

Desarrollado como herramienta interna de apoyo a procesos de digitalización
de planos. Distribuido bajo licencia [MIT](LICENSE): puedes usarlo, copiarlo
y modificarlo libremente.
