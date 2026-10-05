# Planos2DWG

Convierte un plano escaneado en PDF en **un solo archivo de AutoCAD (`.dwg`)**,
con el dibujo separado en capas: muros, ejes, puertas, ventanas, sanitarios,
textos editables y un calco de referencia del escaneo. Pensada para que un
arquitecto o ingeniero sin experiencia en programación la instale en pocos
minutos y la use así:

> **Arrastra el PDF sobre `convertir.bat` y recoge el `.dwg` en la carpeta
> `Convertidos_DWG`.** Sin elegir nada: el programa detecta solo si el plano
> está de lado y dónde está el cajetín.

## ⚠️ Qué hace y qué NO hace esta herramienta (leer antes de usar)

Cada plano se entrega como **un solo archivo** (`nombre-del-pdf.dwg`) con estas **capas**. Lo reconstruido va en capas propias, con líneas rectas y de un solo trazo (sin el temblor del escaneo) y una jerarquía de grosores de línea (muros 0,35 mm, detalle 0,09 mm...). El calco del escaneo va **dentro del mismo archivo pero apagado**. El archivo se abre ya centrado en el dibujo:

| Capa | Qué contiene | Calidad |
|---|---|---|
| `MUROS` | Caras de muros como líneas **rectas, paralelas y enderezadas** (horizontal/vertical exactas), con esquinas prolongadas hasta cruzarse y los extremos libres cerrados con un remate | Limpia, pero **parcial**: faltan tramos. Se descartan las filas de cotas (otra separación entre líneas) y los contornos cortos aislados como muebles |
| `PUERTAS` | El arco de giro de cada puerta y su hoja (si está dibujada), en amarillo | Detecta las puertas de arco fino con bisagra sobre un muro; en un plano real encontró 4 de ~10, así que **faltan puertas**. La hoja solo aparece si se ve en el escaneo |
| `SANITARIOS` | Inodoros y lavamanos como **elipses limpias** de CAD (magenta), buscadas solo dentro de los baños | Aproximada: solo en cuartos etiquetados BAÑO, elipses con tamaño razonable respecto al muro; sin catálogo de bloques ni forma real de la taza, y no reconoce camas, sofás ni cocinas |
| `VENTANAS` | Huecos en un muro con líneas finas dentro: las tres líneas (cara, centro, cara) y sus jambas, en celeste | **Muy incompleta**: si el plano dibuja la ventana sobre las líneas de las caras del muro, en el escaneo el muro parece continuo y no se ve el hueco; en el plano de prueba solo se encontró 1 |
| `ARCOS` | Arcos y círculos reales (`ARC`/`CIRCLE`): muros curvos, puertas batientes, escaleras circulares | Buena en curvas grandes; puede haber algún arco falso o faltar uno |
| `EJES` | Ejes de trazo y punto (tipo de línea `CENTER`): la cuadrícula de letras y números y algunos radiales | Buena en la cuadrícula; puede faltar algún eje radial y no toma como eje las líneas de corte continuas |
| `TEXTOS` | Los nombres de espacios y las cifras leídos con OCR, como **texto de AutoCAD editable** (se pueden corregir con doble clic), en azul | Buena en nombres (SALON SOCIAL, COCINA, ACCESO...); se corrigen confusiones típicas con un vocabulario de planos (BARO -> BAÑO) |
| `COTAS` | Solo las **cifras** de las cotas (2.05, 0.90...) que el OCR leyó con seguridad, en verde, separadas de los nombres de los espacios | **Incompleta**: con un escaneo de 150 dpi se leen pocas cifras. No se generan cotas de AutoCAD (`DIMENSION`), solo el texto |
| `TEXTOS_REVISAR` | Lecturas dudosas (poca confianza, no reconocidas en el vocabulario) en naranja | Hay que revisarlas a mano; su dibujo original sigue en `CALCADO_REFERENCIA` para comparar |
| `DETALLE` | Lo que no es muro, eje, arco, puerta ni texto (cotas, contornos de muebles, rayados) rehecho como **líneas rectas limpias**: se funden los dos bordes de cada trazo, se unen los tramos colineales y se enderezan a horizontal/vertical | Limpia pero **incompleta y fragmentada**: solo tramos rectos de más de 2 mm; las curvas pequeñas, los símbolos y las letras que el OCR no leyó no aparecen aquí (están en el calco apagado) |
| `CALCADO_REFERENCIA` | Calco fiel de toda la tinta del escaneo (textos, símbolos, cotas, curvas) como polilíneas, con las líneas largas suavizadas y enderezadas | Se ve como el PDF pero con los trazos irregulares del escaneo. Va **apagada**: enciéndela (administrador de capas, o `--calco-visible` al convertir) para comparar o para calcar encima lo que falte |

- **No son objetos CAD "inteligentes"**: no hay cotas (`DIMENSION`) ni muebles como bloques (solo sanitarios como elipses),
  y las puertas y ventanas son solo geometría (no bloques con sus atributos), y los muros no tienen relleno ni espesor como objeto.
  Los textos sí son `TEXT` editable si instalaste el OCR (ver abajo); sin él
  quedan solo como calco.
  La salida es una **base para que un dibujante redibuje**, no un plano
  terminado.
- Modo `lineas` (`--modo lineas`): solo líneas rectas sueltas, sin muros ni
  textos. Más limpio pero muy incompleto; no se recomienda.
- **El giro y el cajetín se detectan solos.** Si el escaneo viene de lado (como el
  del plano de prueba), se lee el texto en las cuatro orientaciones y se elige la
  que reconoce más palabras de plano (necesita el OCR; sin él no se gira). El
  recuadro de datos del plano (cajetín) se localiza como una pila de líneas largas
  en la parte baja y se ignora al buscar muros. Si se equivoca, puedes forzarlo con
  `--rotar 0|90|180|270` y `--ignorar-inferior 0.17`. Un escaneo ligeramente
  inclinado también se **endereza** solo.
- La fidelidad depende de la calidad del escaneo. Escanea a 300-400 DPI en
  blanco y negro o gris.
- **El `.dwg` lo escribe ODA File Converter.** Ninguna librería libre de Python
  escribe `.dwg` (es un formato propietario de Autodesk): el programa construye un
  DXF y lo convierte con ODA File Converter (ver
  [instalación](#convertir-a-dwg-real)). **Sin ODA instalado se entrega el mismo
  plano como `.dxf`**, que AutoCAD abre igual. En ambos casos el archivo es único.
- Si ya tienes el **DWG original** del plano, eso siempre dará mejor
  resultado que cualquier conversión desde un escaneo.

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
python main.py planta1.pdf --calco-visible      # dejar encendida la capa del calco de referencia
python main.py planta1.pdf --solo-limpio        # sin calco: archivo más pequeño, sin la capa de referencia
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

## Estructura del proyecto

```
planos2dwg/
├── main.py                 # Punto de entrada (CLI + selector de carpeta)
├── convertir.bat           # Arrastra tus PDF aquí (hace todo solo)
├── instalar.bat            # Instalador de un clic
├── requirements.txt        # Dependencias de producción
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
│   ├── detalle.py          # Líneas de detalle rectas y limpias (lo que no es muro/eje/arco/texto)
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
