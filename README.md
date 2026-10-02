# Planos2DWG

Herramienta de línea de comandos que convierte planos escaneados en PDF (blanco
y negro, de arquitectura o ingeniería) en archivos **DXF editables**, con
conversión opcional a **DWG real** si tienes instalado el conversor gratuito
de Autodesk/ODA. Pensada para que un arquitecto o ingeniero sin experiencia en
programación pueda instalarla y usarla en pocos minutos, arrastrando archivos.

## ⚠️ Qué hace y qué NO hace esta herramienta (leer antes de usar)

- Detecta **líneas rectas** en el escaneo (muros, ejes, contornos) usando
  visión por computador y las convierte en geometría vectorial editable.
- **No reconoce símbolos, bloques, achurados ni texto** automáticamente. El
  resultado es una base de líneas en una capa (`LINEAS_DETECTADAS`) que un
  dibujante debe revisar y completar: cotas, textos, símbolos eléctricos,
  achurados, etc. no se generan solos.
- La fidelidad depende directamente de la calidad del escaneo: líneas finas,
  manchas o escaneos torcidos producen más ruido y segmentos de más que hay
  que limpiar a mano en AutoCAD.
- **No genera un archivo `.dwg` binario por sí sola.** Ninguna librería libre
  de Python puede escribir `.dwg` (es un formato propietario de Autodesk). Lo
  que el script genera de forma nativa es **DXF**, que AutoCAD abre
  exactamente igual que un DWG (`Archivo > Abrir`, sin pasos extra). Si
  necesitas el archivo con extensión `.dwg` literal, instala el conversor
  gratuito **ODA File Converter** (ver [sección dedicada](#convertir-a-dwg-real-opcional))
  y el script lo usará automáticamente.
- Si ya tienes el **DWG original** del plano o un dibujante que te lo pueda
  redibujar a mano con buena calidad, eso siempre dará mejor resultado que
  una conversión automática desde un escaneo.

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

Arrastra uno o varios archivos PDF — o una carpeta completa con PDF dentro —
sobre el ícono de **`convertir.bat`**. Se abrirá una consola mostrando el
progreso y, al terminar, los archivos `.dxf` (y `.dwg` si corresponde)
quedarán organizados dentro de una subcarpeta **`Convertidos_DWG`**, creada
automáticamente junto a cada PDF original. El nombre de esa subcarpeta es
fijo: el programa nunca pregunta cómo llamarla.

### Opción 2: Sin arrastrar nada

Haz doble clic en `convertir.bat` sin soltar ningún archivo encima. Se abrirá
una ventana para que selecciones la carpeta donde están tus planos PDF.

### Opción 3: Desde una terminal (usuarios avanzados)

```bash
.venv\Scripts\activate
python main.py "C:\Planos\Edificio A\planta1.pdf"
python main.py "C:\Planos\Edificio A"          # convierte todos los PDF de la carpeta
python main.py planta1.pdf --dpi 400            # usar más resolución
python main.py planta1.pdf --no-dwg             # generar solo .dxf, sin intentar .dwg
python main.py planta1.pdf --verbose            # ver más detalle en consola/log
```

## Ejemplo de entrada/salida

```
Antes:
  Planos/
    planta-primer-piso.pdf

Después de ejecutar convertir.bat:
  Planos/
    planta-primer-piso.pdf
    Convertidos_DWG/
      planta-primer-piso.dxf   <- siempre se genera
      planta-primer-piso.dwg   <- solo si está instalado ODA File Converter
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
├── instalar.bat            # Instalador de un clic
├── requirements.txt        # Dependencias de producción
├── requirements-dev.txt    # Dependencias + pytest para desarrollo
├── setup.py                # Instalación opcional vía pip (pip install -e .)
├── src/
│   ├── pdf_processor.py    # PDF -> imágenes (PyMuPDF)
│   ├── line_detector.py    # Imagen -> segmentos de línea (OpenCV)
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
- No reconoce texto, cotas, símbolos ni bloques; solo geometría lineal.
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
