"""Planos a AutoCAD: ventana de chat. Arrastra un PDF y te devuelve el .dwg.

Se abre con `abrir_app.bat` (doble clic). Las opciones son fichas rápidas sobre la barra de abajo.
El trabajo lo hace `main.py` en un proceso aparte, para poder detenerlo sin cerrar la ventana.
"""

from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, font as tkfont, ttk

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.gui_logic import ROTATIONS, Event, Options, build_command, collect_pdfs, friendly_event  # noqa: E402
from src.utils import OUTPUT_SUBFOLDER_NAME, PHOTOS_SUBFOLDER_NAME  # noqa: E402

try:  # arrastrar y soltar es opcional: sin esta librería queda el botón del clip
    from tkinterdnd2 import DND_FILES, TkinterDnD

    _BaseWindow = TkinterDnD.Tk
    HAS_DND = True
except Exception:  # pragma: no cover - depende de la instalación
    _BaseWindow = tk.Tk
    HAS_DND = False

# Colores al estilo de los primeros chats: barra azul, fondo claro, burbujas simples.
BLUE = "#3b78d8"
BLUE_DARK = "#2d62b8"
BG = "#e8edf3"
BUBBLE_BOT = "#ffffff"
BUBBLE_BOT_LINE = "#d3dae3"
BUBBLE_ME = "#4a8cf0"
TEXT_DARK = "#26313d"
TEXT_GRAY = "#8794a3"
CHIP_ON = "#dbe9ff"
CHIP_OFF = "#f4f6f9"
GREEN = "#3fbf5f"
WIDTH = 440
MAX_BUBBLE = 300


class ChatApp(_BaseWindow):
    def __init__(self) -> None:
        super().__init__()
        self.title("Planos a AutoCAD")
        height = max(520, min(720, self.winfo_screenheight() - 120))
        self.geometry(f"{WIDTH}x{height}+60+20")
        self.minsize(WIDTH, 520)
        self.maxsize(WIDTH + 140, 1200)
        self.configure(bg=BG)

        self.font = tkfont.Font(family="Segoe UI", size=10)
        self.font_bold = tkfont.Font(family="Segoe UI", size=10, weight="bold")
        self.font_small = tkfont.Font(family="Segoe UI", size=8)

        self.options = {
            "photos": tk.BooleanVar(value=True),
            "text": tk.BooleanVar(value=True),
            "fill": tk.BooleanVar(value=False),
            "dxf": tk.BooleanVar(value=False),
        }
        self.rotation = "auto"
        self.photos_dir = PROJECT_ROOT / PHOTOS_SUBFOLDER_NAME
        self.events: "queue.Queue[tuple[str, object]]" = queue.Queue()
        self.pending: list[Path] = []
        self.process: subprocess.Popen | None = None
        self.stop_requested = False
        self.busy = False
        self.typing_widget: tk.Widget | None = None
        self.typing_step = 0
        self.last_output: Path | None = None
        self._summary = ""
        self.chips: dict[str, tk.Label] = {}

        self._build_header()
        self._build_chat()
        self._build_footer()
        self._refresh_chips()

        if HAS_DND:
            self.drop_target_register(DND_FILES)
            self.dnd_bind("<<Drop>>", self._on_drop)

        self.after(120, self._poll)
        self.after(400, self._welcome)

    # ---------- construcción de la ventana ----------

    def _build_header(self) -> None:
        bar = tk.Frame(self, bg=BLUE, height=58)
        bar.pack(fill="x")
        bar.pack_propagate(False)
        avatar = tk.Canvas(bar, width=40, height=40, bg=BLUE, highlightthickness=0)
        avatar.pack(side="left", padx=(14, 10), pady=9)
        avatar.create_oval(2, 2, 38, 38, fill="white", outline="")
        avatar.create_text(20, 20, text="P", font=("Segoe UI", 15, "bold"), fill=BLUE)
        names = tk.Frame(bar, bg=BLUE)
        names.pack(side="left", pady=8)
        tk.Label(names, text="Planos a AutoCAD", bg=BLUE, fg="white", font=("Segoe UI", 12, "bold")).pack(anchor="w")
        status = tk.Frame(names, bg=BLUE)
        status.pack(anchor="w")
        dot = tk.Canvas(status, width=10, height=10, bg=BLUE, highlightthickness=0)
        dot.pack(side="left", pady=2)
        dot.create_oval(1, 1, 9, 9, fill=GREEN, outline="")
        self.status_label = tk.Label(status, text="en línea", bg=BLUE, fg="#dce8ff", font=self.font_small)
        self.status_label.pack(side="left", padx=4)

    def _build_chat(self) -> None:
        holder = tk.Frame(self, bg=BG)
        holder.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(holder, bg=BG, highlightthickness=0)
        scroll = ttk.Scrollbar(holder, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.inner = tk.Frame(self.canvas, bg=BG)
        self.window_id = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.inner.bind("<Configure>", lambda _e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(self.window_id, width=e.width))
        self.bind_all("<MouseWheel>", lambda e: self.canvas.yview_scroll(int(-e.delta / 120), "units"))

    def _build_footer(self) -> None:
        footer = tk.Frame(self, bg="#f7f9fc", highlightbackground="#d3dae3", highlightthickness=1)
        footer.pack(fill="x", side="bottom")

        self.chip_row = tk.Frame(footer, bg="#f7f9fc")
        self.chip_row.pack(fill="x", padx=8, pady=(8, 2))
        for column in range(3):
            self.chip_row.columnconfigure(column, weight=1, uniform="chips")
        for key, command in (
            ("photos", lambda: self._toggle("photos")),
            ("text", lambda: self._toggle("text")),
            ("fill", lambda: self._toggle("fill")),
            ("dxf", lambda: self._toggle("dxf")),
            ("rotation", self._cycle_rotation),
        ):
            chip = tk.Label(self.chip_row, font=self.font_small, padx=9, pady=4, cursor="hand2", bd=1, relief="solid")
            chip.grid(row=len(self.chips) // 3, column=len(self.chips) % 3, padx=3, pady=2, sticky="ew")
            chip.bind("<Button-1>", lambda _e, c=command: c())
            self.chips[key] = chip
        folder = tk.Label(
            self.chip_row, text="📂 Carpeta de fotos", font=self.font_small, padx=9, pady=4, cursor="hand2",
            bd=1, relief="solid", bg=CHIP_OFF, fg=TEXT_DARK,
        )
        folder.grid(row=1, column=2, padx=3, pady=2, sticky="ew")
        folder.bind("<Button-1>", lambda _e: self._choose_photos_folder())

        composer = tk.Frame(footer, bg="#f7f9fc")
        composer.pack(fill="x", padx=8, pady=(2, 10))
        self.clip = tk.Button(
            composer, text="📎", font=("Segoe UI", 14), bd=0, bg="#f7f9fc", activebackground="#e1e8f2",
            cursor="hand2", command=self._choose_pdfs,
        )
        self.clip.pack(side="left", padx=(0, 6))
        hint = "Arrastra tu plano PDF aquí o toca el clip" if HAS_DND else "Toca el clip para elegir tu plano PDF"
        self.hint = tk.Label(
            composer, text=hint, anchor="w", bg="white", fg=TEXT_GRAY, font=self.font, padx=12, pady=8,
            bd=1, relief="solid", cursor="hand2",
        )
        self.hint.pack(side="left", fill="x", expand=True)
        self.hint.bind("<Button-1>", lambda _e: self._choose_pdfs())
        self.send = tk.Button(
            composer, text="Elegir", font=self.font_bold, bd=0, bg=BLUE, fg="white", activebackground=BLUE_DARK,
            activeforeground="white", padx=14, pady=6, cursor="hand2", command=self._choose_pdfs,
        )
        self.send.pack(side="left", padx=(6, 0))

        self.progress = ttk.Progressbar(footer, mode="indeterminate", length=WIDTH)

    # ---------- fichas (opciones) ----------

    def _chip_texts(self) -> dict[str, str]:
        mark = lambda on: "✔" if on else "✖"  # noqa: E731
        return {
            "photos": f"{mark(self.options['photos'].get())} Usar fotos",
            "text": f"{mark(self.options['text'].get())} Leer textos",
            "fill": f"{mark(self.options['fill'].get())} Relleno gris",
            "dxf": f"{mark(self.options['dxf'].get())} Guardar DXF",
            "rotation": "↻ Giro: " + ("auto" if self.rotation == "auto" else f"{self.rotation}°"),
        }

    def _refresh_chips(self) -> None:
        texts = self._chip_texts()
        for key, chip in self.chips.items():
            on = self.options[key].get() if key in self.options else self.rotation != "auto"
            chip.configure(text=texts[key], bg=CHIP_ON if on else CHIP_OFF, fg=BLUE_DARK if on else TEXT_GRAY)

    def _toggle(self, key: str) -> None:
        self.options[key].set(not self.options[key].get())
        self._refresh_chips()
        explain = {
            "photos": ("Voy a usar tus fotos del plano para leer mejor las cotas.", "No voy a usar las fotos."),
            "text": ("Voy a leer los textos y las cotas.", "No voy a leer textos: queda más rápido, pero sin letras."),
            "fill": ("Dejo el escaneo gris encendido para que compares.", "Dejo el escaneo gris apagado (solo líneas)."),
            "dxf": ("Además del .dwg guardo un .dxf.", "Solo guardo el .dwg."),
        }
        on_text, off_text = explain[key]
        self._say_bot(on_text if self.options[key].get() else off_text, small=True)

    def _cycle_rotation(self) -> None:
        self.rotation = ROTATIONS[(ROTATIONS.index(self.rotation) + 1) % len(ROTATIONS)]
        self._refresh_chips()
        self._say_bot(
            "Detecto solo si el plano está de lado." if self.rotation == "auto"
            else f"Giro el plano {self.rotation}° antes de convertirlo.",
            small=True,
        )

    def _choose_photos_folder(self) -> None:
        folder = filedialog.askdirectory(title="Carpeta con fotos de partes del plano", initialdir=str(self.photos_dir))
        if folder:
            self.photos_dir = Path(folder)
            self.options["photos"].set(True)
            self._refresh_chips()
            self._say_bot(f"Listo, buscaré fotos en: {self.photos_dir.name}", small=True)

    # ---------- burbujas ----------

    def _rounded(self, canvas: tk.Canvas, x0: float, y0: float, x1: float, y1: float, r: float, **kw) -> None:
        points = [
            x0 + r, y0, x1 - r, y0, x1, y0, x1, y0 + r, x1, y1 - r, x1, y1, x1 - r, y1,
            x0 + r, y1, x0, y1, x0, y1 - r, x0, y0 + r, x0, y0,
        ]
        canvas.create_polygon(points, smooth=True, **kw)

    def _bubble(self, text: str, mine: bool, small: bool = False) -> tk.Frame:
        font = self.font_small if small else self.font
        pad_x, pad_y = 12, 8
        # se mide con un Message oculto, que ajusta las líneas igual que el texto de la burbuja
        meter = tk.Message(self, text=text, font=font, width=MAX_BUBBLE)
        height = meter.winfo_reqheight()
        width = min(max(meter.winfo_reqwidth(), 30), MAX_BUBBLE + 10)
        meter.destroy()

        row = tk.Frame(self.inner, bg=BG)
        row.pack(fill="x", padx=12, pady=3)
        cell = tk.Frame(row, bg=BG)
        cell.pack(side="right" if mine else "left")
        if not mine:
            tk.Label(cell, text="Planos a AutoCAD", font=self.font_small, bg=BG, fg=TEXT_GRAY).pack(anchor="w", padx=6)
        canvas = tk.Canvas(cell, width=width + 2 * pad_x, height=height + 2 * pad_y, bg=BG, highlightthickness=0)
        canvas.pack(anchor="e" if mine else "w")
        fill, line, ink = (BUBBLE_ME, BUBBLE_ME, "white") if mine else (BUBBLE_BOT, BUBBLE_BOT_LINE, TEXT_DARK)
        self._rounded(canvas, 1, 1, width + 2 * pad_x - 1, height + 2 * pad_y - 1, 14, fill=fill, outline=line)
        canvas.create_text(pad_x, pad_y, anchor="nw", text=text, font=font, fill=ink, width=MAX_BUBBLE)
        stamp = tk.Label(cell, text=time.strftime("%H:%M"), font=self.font_small, bg=BG, fg=TEXT_GRAY)
        stamp.pack(anchor="e" if mine else "w", padx=6)
        self._scroll_down()
        return cell

    def _say_bot(self, text: str, small: bool = False) -> tk.Frame:
        return self._bubble(text, mine=False, small=small)

    def _say_me(self, text: str) -> tk.Frame:
        return self._bubble(text, mine=True)

    def _buttons(self, cell: tk.Frame, actions: list[tuple[str, object]]) -> None:
        row = tk.Frame(cell, bg=BG)
        row.pack(anchor="w", pady=(2, 0))
        for label, command in actions:
            tk.Button(
                row, text=label, font=self.font_bold, bd=1, relief="solid", bg="white", fg=BLUE_DARK,
                activebackground=CHIP_ON, padx=10, pady=4, cursor="hand2", command=command,
            ).pack(side="left", padx=(0, 6))
        self._scroll_down()

    def _scroll_down(self) -> None:
        self.update_idletasks()
        self.canvas.yview_moveto(1.0)

    def _welcome(self) -> None:
        self._say_bot("¡Hola! 👋 Soy tu convertidor de planos.")
        extra = "Arrastra un plano PDF a esta ventana" if HAS_DND else "Toca el clip 📎 de abajo"
        self._say_bot(f"{extra} y te lo devuelvo como archivo de AutoCAD (.dwg), con muros, puertas, textos y cotas.")
        self._say_bot("Abajo puedes encender o apagar opciones tocando las fichas. Si no sabes cuál, déjalas como están.", small=True)

    # ---------- elegir y soltar archivos ----------

    def _choose_pdfs(self) -> None:
        if self.busy:
            return
        files = filedialog.askopenfilenames(title="Elige tu plano en PDF", filetypes=[("Planos en PDF", "*.pdf")])
        if files:
            self._queue_files(list(files))

    def _on_drop(self, event) -> None:
        self._queue_files(list(self.tk.splitlist(event.data)))

    def _queue_files(self, paths: list[str]) -> None:
        pdfs, ignored = collect_pdfs(paths)
        if ignored and not pdfs:
            self._say_bot("Eso no lo puedo convertir 🤔 Solo entiendo planos en PDF.")
            return
        if ignored:
            self._say_bot(f"Dejé por fuera {len(ignored)} archivo(s) que no son PDF.", small=True)
        for pdf in pdfs:
            self._say_me(f"📄 {pdf.name}")
        self.pending.extend(pdfs)
        if not self.busy:
            self._next_job()
        elif pdfs:
            self._say_bot(f"Los dejo en fila ({len(self.pending)} esperando).", small=True)

    # ---------- ejecución ----------

    def _current_options(self) -> Options:
        return Options(
            use_photos=self.options["photos"].get(),
            photos_dir=self.photos_dir,
            read_text=self.options["text"].get(),
            show_scan_fill=self.options["fill"].get(),
            keep_dxf=self.options["dxf"].get(),
            rotation=self.rotation,
        )

    def _next_job(self) -> None:
        if not self.pending:
            self._set_busy(False)
            return
        pdf = self.pending.pop(0)
        self._set_busy(True)
        self._say_bot(f"Recibido: {pdf.name}. Empiezo ahora; puede tardar unos minutos ⏳")
        self.show_typing()
        command = build_command(sys.executable, PROJECT_ROOT / "main.py", pdf, self._current_options())
        threading.Thread(target=self._run, args=(command, pdf), daemon=True).start()

    def _run(self, command: list[str], pdf: Path) -> None:
        env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
        seen: set[str] = set()
        got_done = False
        errors: list[str] = []
        try:
            self.process = subprocess.Popen(
                command, cwd=PROJECT_ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), text=True, encoding="utf-8", errors="replace",
            )
            assert self.process.stdout is not None
            for line in self.process.stdout:
                event = friendly_event(line, seen)
                if event is None:
                    continue
                if event.kind == "done":
                    got_done = True
                if event.kind == "error":
                    errors.append(event.text)
                    continue
                self.events.put(("event", event))
            self.process.wait()
        except Exception as exc:  # no tumbar la ventana por un fallo al lanzar
            errors.append(str(exc))
        finally:
            self.events.put(("end", (pdf, got_done, errors, self.stop_requested)))

    def stop(self) -> None:
        if self.process and self.process.poll() is None:
            self.stop_requested = True
            self.process.terminate()
            self._say_bot("Detenido ✋", small=True)

    def _set_busy(self, busy: bool) -> None:
        self.busy = busy
        if busy:
            self.stop_requested = False
            self.status_label.configure(text="trabajando…")
            self.progress.pack(fill="x")
            self.progress.start(14)
            self.hint.configure(text="Convirtiendo… toca Detener si te equivocaste")
            self.send.configure(text="Detener", command=self.stop, bg="#d9534f", activebackground="#b9403d")
            self.clip.configure(state="disabled")
        else:
            self.status_label.configure(text="en línea")
            self.progress.stop()
            self.progress.pack_forget()
            self.hint.configure(text="Arrastra tu plano PDF aquí o toca el clip" if HAS_DND else "Toca el clip para elegir tu plano PDF")
            self.send.configure(text="Elegir", command=self._choose_pdfs, bg=BLUE, activebackground=BLUE_DARK)
            self.clip.configure(state="normal")

    # ---------- indicador "escribiendo…" ----------

    def show_typing(self) -> None:
        self.hide_typing()
        self.typing_widget = self._say_bot("•  •  •")
        self.typing_step = 0

    def hide_typing(self) -> None:
        if self.typing_widget is not None:
            self.typing_widget.master.destroy()
            self.typing_widget = None

    def _poll(self) -> None:
        try:
            while True:
                kind, payload = self.events.get_nowait()
                if kind == "event":
                    self._on_event(payload)  # type: ignore[arg-type]
                else:
                    self._on_end(*payload)  # type: ignore[misc]
        except queue.Empty:
            pass
        self.after(150, self._poll)

    def _on_event(self, event: Event) -> None:
        self.hide_typing()
        if event.kind == "done":
            self.last_output = Path(event.text)
            return  # el mensaje final se arma al terminar, junto con el resumen
        if event.kind == "summary":
            self._summary = event.text
            return
        self._say_bot(event.text, small=event.kind == "info")
        self.show_typing()

    def _on_end(self, pdf: Path, ok: bool, errors: list[str], stopped: bool) -> None:
        self.hide_typing()
        if ok and self.last_output:
            output = self.last_output
            cell = self._say_bot(f"¡Listo! 🎉 Tu plano quedó en AutoCAD:\n{output.name}")
            if self._summary:
                self._say_bot("Contiene: " + self._summary + ".", small=True)
            self._buttons(cell, [
                ("Abrir plano", lambda p=output: os.startfile(p)),  # type: ignore[attr-defined]
                ("Abrir carpeta", lambda p=output: os.startfile(p.parent)),  # type: ignore[attr-defined]
            ])
        elif not stopped:
            detail = errors[-1] if errors else "no se generó ningún archivo"
            self._say_bot(f"Uy, no pude con ese plano 😕\n{detail}")
            self._say_bot("Prueba con otro PDF, o revisa que sea un escaneo legible.", small=True)
        self._summary = ""
        self.last_output = None
        if stopped:
            self.pending.clear()
        self._next_job()


def main() -> None:
    app = ChatApp()
    app.mainloop()


if __name__ == "__main__":
    main()
