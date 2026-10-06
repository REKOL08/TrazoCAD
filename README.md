# Planos2DWG

Convierte un plano escaneado en PDF en **un solo archivo de AutoCAD (`.dwg`)**,
con el dibujo separado en capas: muros, ejes, puertas, ventanas, sanitarios,
textos editables y un calco de referencia del escaneo. Pensada para que un
arquitecto o ingeniero sin experiencia en programación la instale en pocos
minutos y la use así:

> **Abre el programa «Planos a AutoCAD» (acceso directo del escritorio), arrastra el
> PDF a la zona azul, ponle nombre a la carpeta y toca «Convertir a AutoCAD».** O, sin
> ventana: arrastra el PDF sobre `convertir.bat`. El programa detecta solo si el plano
> está de lado y dónde está el cajetín.

## El programa de escritorio («Planos a AutoCAD»)

Una ventana normal de programa, con su logo, en cuatro pasos:

1. **Tu plano:** arrastra el PDF a la zona azul (o haz clic para buscarlo). Puedes soltar varios.
2. **Dónde guardarlo:** escribe el **nombre de la carpeta**; se **crea al tocar Convertir**, antes de
   generar nada, dentro de `Convertidos_DWG` (o la carpeta que elijas con «Cambiar…»). Por defecto
   lleva el nombre del PDF. Debajo ves la ruta exacta que se va a crear.
3. **Fotos para más precisión (opcional):** «Agregar fotos…» (o suéltalas en la ventana) con fotos de
   partes del mismo plano; ayudan a leer mejor las cotas y los textos pequeños. Las fotos de otro plano
   se ignoran solas.
4. **Opciones:** leer textos y cotas, guardar también un `.dxf`, mostrar el escaneo gris de fondo y giro
   del plano (automático, 90°, 180°, 270°).

Después **Convertir a AutoCAD**: aparece el avance paso a paso (con **Detener** si te equivocaste) y
al final **Abrir el plano** y **Abrir la carpeta**. Por dentro ejecuta el mismo `main.py` en un proceso
aparte, así que el resultado es idéntico al de la línea de comandos.

**Acceso directo con logo:** `crear_acceso_directo.bat` lo crea en tu escritorio («Planos a AutoCAD»).
También puedes abrir el programa con `abrir_app.bat`. El logo se regenera con `assets/hacer_logo.py`
(necesita Pillow, solo para eso).

## Requisitos del sistema

- Windows 10 u 11.
- [Python 3.10 o superior](https://www.python.org/downloads/) instalado
  (marca la casilla **"Add python.exe to PATH"** durante la instalación).
- 4 GB de RAM como mínimo (8 GB recomendado si vas a convertir planos muy
  grandes o en lote).
- Alrededor de 500 MB libres en disco para las dependencias.
- [ODA File Converter](https://www.opendesign.com/guestfiles/oda_file_converter)
  gratuito, para que el archivo salga como `.dwg` (sin él sale como `.dxf`).

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

## Lectura de textos (OCR, opcional)

`instalar.bat` instala también el OCR local **RapidOCR** (modelos ONNX, corre
en tu PC, sin internet ni programas aparte). Si prefieres instalarlo a mano:

```bash
pip install -r requirements-ocr.txt
```

Sin él todo funciona igual, pero los textos quedan solo como calco. Leer un
plano tarda unos 30-40 segundos extra; usa `--sin-texto` para omitirlo.
Los textos pequeños, borrosos o muy tramados se leen peor: por eso hay una
capa `TEXTOS_REVISAR`.

## Cómo usar

### Opción 1: Arrastrar y soltar (recomendada)

Arrastra uno o varios archivos PDF — o una carpeta completa con PDF dentro,
estén donde estén en tu PC — sobre el ícono de **`convertir.bat`**. Se
abrirá una consola mostrando el progreso (un plano tarda 1-2 minutos) y, al
terminar, se abre la carpeta **`Convertidos_DWG`** (dentro de esta misma carpeta
del programa, no junto al PDF) con **un archivo por plano**: `nombre-del-pdf.dwg`.
El programa nunca pregunta nada.

> Si conviertes de nuevo el mismo PDF, el archivo se **reemplaza**. Si ese
> archivo está abierto en AutoCAD (Windows no deja sobrescribirlo), el nuevo se
> guarda con la hora en el nombre en vez de fallar (por ejemplo
> `planta1_154715.dwg`). Dos PDF con el mismo nombre desde carpetas distintas se
> pisarían entre sí: renómbralos antes.

### Opción 2: Sin arrastrar nada

Haz doble clic en `convertir.bat` sin soltar ningún archivo encima. Se abrirá
una ventana para que selecciones la carpeta donde están tus planos PDF.

### Opción 3: Desde una terminal (usuarios avanzados)

```bash
.venv\Scripts\activate
python main.py "C:\Planos\Edificio A\planta1.pdf"
python main.py "C:\Planos\Edificio A"          # convierte todos los PDF de la carpeta
python main.py planta1.pdf --dpi 400            # usar más resolución
python main.py planta1.pdf --rotar 90           # forzar el giro (por defecto se detecta solo)
python main.py planta1.pdf --ignorar-inferior 0.17  # forzar el cajetín (por defecto se detecta solo)
python main.py planta1.pdf --conservar-dxf      # guardar también el .dxf junto al .dwg
python main.py planta1.pdf --sin-texto          # no leer textos (más rápido, ~30 s menos)
python main.py planta1.pdf --calco-visible      # encender el relleno gris del escaneo (por defecto va apagado)
python main.py planta1.pdf --fotos MIS_FOTOS    # carpeta con fotos de partes del plano (por defecto: planos_de_prueba)
python main.py planta1.pdf --sin-fotos          # ignorar las fotos aunque haya en la carpeta
python main.py planta1.pdf --foto a.jpg --foto b.jpg   # usar solo estas fotos
python main.py planta1.pdf --salida "C:\Planos\Casa 1"  # carpeta de resultados (se crea)
python main.py planta1.pdf --solo-limpio        # sin el relleno del escaneo en el archivo (más pequeño)
python main.py planta1.pdf --grosor-muro 1.0    # espesor de muro en mm sobre el papel (si no, se mide solo)
python main.py planta1.pdf --modo lineas        # solo líneas rectas (modo alterno)
python main.py planta1.pdf --no-dwg             # entregar .dxf en vez de .dwg
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
      planta-primer-piso.dwg         <- UN solo archivo con todo el plano en capas
                                        (.dxf si no está instalado ODA File Converter)
```

Un PDF de varias páginas genera un archivo por página, con el sufijo `_p1`,
`_p2`, etc. (por ejemplo `planta-primer-piso_p2.dwg`).

## Convertir a DWG real

1. Descarga **ODA File Converter** gratis desde el sitio oficial de la Open
   Design Alliance: https://www.opendesign.com/guestfiles/oda_file_converter
2. Instálalo con las opciones por defecto (archivo `.msi`, unos 32 MB). Verifica que el
   instalador esté firmado por *OPEN DESIGN ALLIANCE* (clic derecho > Propiedades >
   Firmas digitales). No uses `winget install ODA.ODAFileConverter`: a octubre de 2026 el
   paquete de winget apunta a un enlace que da error 404.
3. Vuelve a ejecutar `convertir.bat` normalmente: el script detecta la
   instalación automáticamente (busca en `C:\Program Files\ODA`) y entrega el `.dwg`.

> **Nota de licencia:** ODA File Converter es gratuito para uso personal y,
> según los términos publicados por Open Design Alliance, de uso libre salvo
> que seas miembro/no miembro en contextos específicamente restringidos;
> revisa los términos de uso en el sitio oficial si vas a usarlo en un
> contexto comercial y tienes dudas.

Si no instalas ODA File Converter, el script sigue funcionando normalmente y
entrega el plano como `.dxf`, que AutoCAD abre sin ningún problema adicional.

## Planos de prueba

La carpeta `planos_de_prueba/` es para dejar los planos con los que quieres afinar el programa
(escaneos a 300-400 dpi, planos distintos entre sí, y si existe el DWG original o un conteo hecho
a mano). **Su contenido no se sube a GitHub** (solo el `LEEME.txt`), porque los planos pueden ser
confidenciales. Detalles en `planos_de_prueba/LEEME.txt`.

### Fotos de partes del plano (mejoran la lectura de cotas y textos)

Si el escaneo es de baja resolución (150 dpi), las cotas pequeñas no se leen. Una **foto de celular
de un trozo del mismo plano** tiene mucha más resolución efectiva en esa zona. Déjalas en
`planos_de_prueba/` (o indica otra carpeta con `--fotos`) y el convertidor las usa solo:

1. Alinea cada foto con el plano (puntos SIFT sin sombras, homografía con RANSAC, prueba los 4
   giros). La foto puede estar girada, torcida o con sombras. Las fotos de **otro** plano o sin
   coincidencias se descartan solas, igual que las repetidas.
2. Lee sus textos con el mismo OCR, descarta el borde de la foto (desenfocado) y lleva cada texto al
   marco del plano. Las cotas que el OCR confundía (`RO.85`, `z.05`) se corrigen.
3. Suma lo que el escaneo no leyó y se queda con la mejor lectura cuando ambos leen lo mismo.

Con las 3 fotos del plano de prueba los textos pasaron de **64 a 129** (y las cotas de ~13 a ~55).
Cuesta unos 2-3 minutos extra por plano (OCR de cada foto). Limites: solo mejora las zonas que
cubren las fotos; no cambia la geometría (muros, arcos...), que sigue saliendo del escaneo; las
sombras fuertes o los dobleces del papel pueden dar lecturas erróneas, por eso hay que revisar
la capa `TEXTOS_REVISAR`.

## Estructura del proyecto

```
planos2dwg/
├── main.py                 # Punto de entrada (CLI + selector de carpeta)
├── abrir_app.bat           # Abre el programa de escritorio
├── app.py                  # El programa de escritorio (tkinter)
├── crear_acceso_directo.bat # Crea el acceso directo con logo en el escritorio
├── assets/                 # Logo (png, ico) y su generador
├── convertir.bat           # Arrastra tus PDF aquí (hace todo solo)
├── instalar.bat            # Instalador de un clic
├── requirements.txt        # Dependencias de producción
├── requirements-gui.txt    # Arrastrar y soltar para la ventana (opcional)
├── requirements-dev.txt    # Dependencias + pytest para desarrollo
├── setup.py                # Instalación opcional vía pip (pip install -e .)
├── src/
│   ├── pdf_processor.py    # PDF -> imágenes (PyMuPDF)
│   ├── muros.py            # Muros (pares de caras paralelas), remates y ejes (OpenCV LSD)
│   ├── arcos.py            # Arcos y círculos (RANSAC sobre trocitos de línea)
│   ├── texto.py            # Textos con OCR local (RapidOCR), tiles y vocabulario de planos
│   ├── muebles.py          # Sanitarios (inodoros, lavamanos) como elipses, guiados por la etiqueta BAÑO
│   ├── puertas.py          # Puertas: arco de giro de la hoja (Hough + aislamiento + bisagra en muro)
│   ├── ventanas.py         # Ventanas: huecos alineados en las dos caras de un muro con líneas dentro
│   ├── deskew.py           # Enderezado de escaneos inclinados
│   ├── orientacion.py      # Giro de página y cajetín detectados solos
│   ├── gui_logic.py        # Lógica de la ventana: comando, nombres de carpeta y mensajes (probada)
│   ├── fotos.py            # Alinea fotos de partes del plano y suma los textos/cotas que se leen mejor en ellas
│   ├── detalle.py          # Trazos de detalle de un solo trazo (esqueleto) de lo que no es muro/eje/arco/texto
│   ├── centerline.py       # Adelgazado de la tinta a su línea central y recorrido del grafo
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
- Si el archivo de salida está abierto en AutoCAD mientras vuelves a convertir, el
  nuevo se guarda con la hora en el nombre (Windows no deja sobrescribir un archivo
  abierto).
- La detección automática del giro necesita el OCR y texto legible; con un plano
  casi sin texto puede no concluir y lo deja como viene (se puede forzar con
  `--rotar`). El cajetín solo se detecta en la parte baja de la hoja.
- La **escala real** no se conoce: el dibujo sale en milímetros sobre el papel del
  escaneo, no a tamaño real. Para ponerlo a escala, mide una cota conocida en
  AutoCAD y usa el comando `SCALE` con referencia.
- Escaneos torcidos (sin enderezar) o de baja resolución (menos de ~200 DPI)
  producen resultados pobres; se recomienda escanear a 300–400 DPI.
- El `.dwg` requiere instalar ODA File Converter por separado (no se incluye en
  este repositorio por ser una herramienta de terceros); sin él se entrega `.dxf`.
- Cada página se procesa de forma independiente; no intenta alinear ni
  unir planos de varias hojas en un solo dibujo.

## Solución de problemas

- **"el escaneo del PDF tiene solo N dpi reales"**: el PDF contiene una imagen de
  poca resolución (por ejemplo, una hoja carta a 150 dpi). Convertir a más dpi
  solo interpola y no añade detalle: los textos pequeños y las cifras de las
  cotas miden unos 7 píxeles y no se pueden leer, y los trazos salen irregulares.
  **El factor que más mejora el resultado es escanear a 300-400 dpi.**

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
