"""TrazoCAD: programa de escritorio. Arrastra el PDF y se transforma en un .dwg.

Se abre con el acceso directo del escritorio o con `abrir_app.bat`. El trabajo lo hace `main.py` en
un proceso aparte, para poder detenerlo sin cerrar la ventana.
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
from tkinter import filedialog, messagebox, ttk

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.fotos import PHOTO_EXTENSIONS, unique_photos  # noqa: E402
from src.organizar import FOLDER_PDF, FOLDER_PHOTOS, FOLDER_PLAN, FOLDER_PREVIEW  # noqa: E402
from src.visor import ImageViewer  # noqa: E402
from src.gui_logic import Event, Options, build_command, clean_folder_name, collect_pdfs, friendly_event  # noqa: E402
from src.utils import OUTPUT_SUBFOLDER_NAME  # noqa: E402

try:  # arrastrar y soltar es opcional: sin esta librería queda el clic para buscar el archivo
    from tkinterdnd2 import DND_FILES, TkinterDnD

    _BaseWindow = TkinterDnD.Tk
    HAS_DND = True
except Exception:  # pragma: no cover - depende de la instalación
    _BaseWindow = tk.Tk
    HAS_DND = False

ASSETS = PROJECT_ROOT / "assets"
APP_ID = "TrazoCAD.Convertidor"

NAVY = "#0d3b8e"
BLUE = "#1f6feb"
BLUE_DARK = "#1658bf"
BG = "#f2f5fa"
CARD = "#ffffff"
LINE = "#d6deea"
INK = "#1f2a3a"
GRAY = "#6b7a90"
ZONE = "#eaf2ff"
ZONE_HOT = "#d3e5ff"
GREEN = "#1e9e55"
RED = "#d64545"
ROTATIONS = {"Automático": "auto", "Girar 90°": "90", "Girar 180°": "180", "Girar 270°": "270"}
FONT = ("Segoe UI", 10)
FONT_B = ("Segoe UI", 10, "bold")
FONT_S = ("Segoe UI", 9)


class App(_BaseWindow):
    def __init__(self) -> None:
        super().__init__()
        self.title("TrazoCAD")
        self.configure(bg=BG)
        self.minsize(820, 600)
        self.geometry(f"880x{min(700, max(600, self.winfo_screenheight() - 80))}+80+10")
        self._set_icon()

        self.pdfs: list[Path] = []
        self.photos: list[Path] = []
        self.base_dir = PROJECT_ROOT / OUTPUT_SUBFOLDER_NAME
        self.name_var = tk.StringVar()
        self.name_touched = False
        self.read_text = tk.BooleanVar(value=True)
        self.keep_dxf = tk.BooleanVar(value=False)
        self.show_fill = tk.BooleanVar(value=False)
        self.rotation = tk.StringVar(value="Automático")

        self.events: "queue.Queue[tuple[str, object]]" = queue.Queue()
        self.process: subprocess.Popen | None = None
        self.stop_requested = False
        self.busy = False
        self.started_at = 0.0
        self.jobs: list[Path] = []
        self.outputs: list[Path] = []
        self.summary = ""
        self.previews: list[Path] = []
        self.photos_used: list[Path] = []
        self.out_dir: Path | None = None

        self._build_header()
        self._build_bottom()
        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True, padx=20, pady=(14, 8))
        body.columnconfigure(0, weight=3, uniform="col")
        body.columnconfigure(1, weight=2, uniform="col")
        body.rowconfigure(0, weight=1)
        self._build_left(body)
        self._build_right(body)

        self.name_var.trace_add("write", lambda *_: self._on_name_edit())
        self._refresh_all()
        if HAS_DND:
            self.drop_target_register(DND_FILES)
            self.dnd_bind("<<Drop>>", self._on_drop)
        self.after(150, self._poll)
        self.after(1000, self._tick)

    # ---------- ventana ----------

    def _set_icon(self) -> None:
        try:  # que la barra de tareas muestre el logo y no el de Python
            import ctypes

            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
        except Exception:
            pass
        try:
            self.iconbitmap(default=str(ASSETS / "trazocad.ico"))
        except Exception:
            pass

    def _build_header(self) -> None:
        bar = tk.Frame(self, bg=NAVY)
        bar.pack(fill="x")
        try:
            self.logo = tk.PhotoImage(file=str(ASSETS / "logo_44.png"))
            tk.Label(bar, image=self.logo, bg=NAVY).pack(side="left", padx=(20, 12), pady=6)
        except Exception:
            self.logo = None
        titles = tk.Frame(bar, bg=NAVY)
        titles.pack(side="left", pady=6)
        tk.Label(titles, text="TrazoCAD", bg=NAVY, fg="white", font=("Segoe UI", 15, "bold")).pack(anchor="w")
        tk.Label(
            titles, text="Del papel al DWG: convierte un plano escaneado (PDF) en un archivo de AutoCAD editable", bg=NAVY, fg="#b9cdf5", font=FONT_S
        ).pack(anchor="w")

    def _card(self, parent: tk.Widget, number: str, title: str) -> tk.Frame:
        frame = tk.Frame(parent, bg=CARD, highlightbackground=LINE, highlightthickness=1)
        head = tk.Frame(frame, bg=CARD)
        head.pack(fill="x", padx=14, pady=(8, 4))
        badge = tk.Canvas(head, width=24, height=24, bg=CARD, highlightthickness=0)
        badge.pack(side="left")
        badge.create_oval(1, 1, 23, 23, fill=BLUE, outline="")
        badge.create_text(12, 12, text=number, fill="white", font=("Segoe UI", 9, "bold"))
        tk.Label(head, text=title, bg=CARD, fg=INK, font=("Segoe UI", 11, "bold")).pack(side="left", padx=8)
        return frame

    def _build_left(self, body: tk.Frame) -> None:
        left = tk.Frame(body, bg=BG)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        left.rowconfigure(0, weight=3)
        left.rowconfigure(1, weight=2)
        left.columnconfigure(0, weight=1)

        # 1. el plano
        card = self._card(left, "1", "Tu plano")
        card.grid(row=0, column=0, sticky="nsew", pady=(0, 10))
        self.zone = tk.Canvas(card, bg=ZONE, highlightthickness=0, height=96, cursor="hand2")
        self.zone.pack(fill="both", expand=True, padx=14, pady=(0, 6))
        self.zone.bind("<Configure>", lambda _e: self._draw_zone())
        self.zone.bind("<Button-1>", lambda _e: self._choose_pdfs())
        self.zone.bind("<Enter>", lambda _e: self._draw_zone(hot=True))
        self.zone.bind("<Leave>", lambda _e: self._draw_zone())
        self.pdf_hint = tk.Label(card, text="", bg=CARD, fg=GRAY, font=FONT_S, anchor="w")
        self.pdf_hint.pack(fill="x", padx=14, pady=(0, 6))

        # 3. fotos
        card = self._card(left, "3", "Fotos para más precisión (opcional)")
        card.grid(row=1, column=0, sticky="nsew")
        tk.Label(
            card,
            text="Fotos de partes del mismo plano: se fusionan con el escaneo y dan más detalle: líneas más finas y cotas legibles.",
            bg=CARD, fg=GRAY, font=FONT_S, anchor="w", wraplength=430, justify="left",
        ).pack(fill="x", padx=14)
        row = tk.Frame(card, bg=CARD)
        row.pack(fill="both", expand=True, padx=14, pady=(6, 10))
        self.photo_list = tk.Listbox(
            row, height=3, activestyle="none", font=FONT_S, bd=0, highlightbackground=LINE, highlightthickness=1,
            selectbackground=ZONE_HOT, selectforeground=INK, selectmode="extended",
        )
        self.photo_list.pack(side="left", fill="both", expand=True)
        buttons = tk.Frame(row, bg=CARD)
        buttons.pack(side="left", padx=(10, 0), anchor="n")
        self._button(buttons, "➕  Agregar fotos…", self._choose_photos, primary=False).pack(fill="x")
        self._button(buttons, "Quitar", self._remove_photos, primary=False).pack(fill="x", pady=(6, 0))

    def _build_right(self, body: tk.Frame) -> None:
        right = tk.Frame(body, bg=BG)
        right.grid(row=0, column=1, sticky="nsew")
        right.columnconfigure(0, weight=1)

        # 2. carpeta
        card = self._card(right, "2", "Dónde guardarlo")
        card.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        tk.Label(card, text="Nombre de la carpeta", bg=CARD, fg=INK, font=FONT_B, anchor="w").pack(fill="x", padx=14)
        self.name_entry = tk.Entry(card, textvariable=self.name_var, font=FONT, bd=0, highlightbackground=LINE, highlightthickness=1, highlightcolor=BLUE)
        self.name_entry.pack(fill="x", padx=14, pady=(4, 8), ipady=5)
        tk.Label(card, text="Dentro de", bg=CARD, fg=INK, font=FONT_B, anchor="w").pack(fill="x", padx=14)
        place = tk.Frame(card, bg=CARD)
        place.pack(fill="x", padx=14, pady=(4, 4))
        self.base_label = tk.Label(place, text="", bg="#f6f8fb", fg=INK, font=FONT_S, anchor="w", padx=8, pady=5, bd=0, highlightbackground=LINE, highlightthickness=1)
        self.base_label.pack(side="left", fill="x", expand=True)
        self._button(place, "Cambiar…", self._choose_base, primary=False).pack(side="left", padx=(6, 0))
        self.create_label = tk.Label(card, text="", bg=CARD, fg=GREEN, font=FONT_S, anchor="w", wraplength=300, justify="left")
        self.create_label.pack(fill="x", padx=14, pady=(2, 8))

        # 4. opciones
        card = self._card(right, "4", "Opciones")
        card.grid(row=1, column=0, sticky="ew")
        for text, var in (
            ("Leer textos y cotas", self.read_text),
            ("Guardar también un .dxf", self.keep_dxf),
            ("Mostrar el escaneo gris de fondo", self.show_fill),
        ):
            tk.Checkbutton(
                card, text=text, variable=var, bg=CARD, activebackground=CARD, fg=INK, font=FONT, anchor="w",
                selectcolor="white", bd=0, highlightthickness=0,
            ).pack(fill="x", padx=14, pady=1)
        turn = tk.Frame(card, bg=CARD)
        turn.pack(fill="x", padx=14, pady=(4, 10))
        tk.Label(turn, text="Giro del plano", bg=CARD, fg=INK, font=FONT).pack(side="left")
        ttk.Combobox(turn, textvariable=self.rotation, values=list(ROTATIONS), state="readonly", width=14, font=FONT).pack(side="right")

    def _build_bottom(self) -> None:
        bottom = tk.Frame(self, bg=BG)
        bottom.pack(fill="x", side="bottom", padx=20, pady=(0, 16))

        self.go = self._button(bottom, "Convertir a AutoCAD", self._start, primary=True, big=True)
        self.go.pack(fill="x")
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("Thin.Horizontal.TProgressbar", thickness=6, troughcolor=LINE, background=BLUE, bordercolor=BG, lightcolor=BLUE, darkcolor=BLUE)

        self.progress = ttk.Progressbar(bottom, mode="indeterminate", style="Thin.Horizontal.TProgressbar")
        self.status = tk.Label(bottom, text="", bg=BG, fg=GRAY, font=FONT_S, anchor="w")
        self.status.pack(fill="x", pady=(4, 0))

        self.log = tk.Text(
            bottom, height=4, font=FONT_S, bd=0, bg=CARD, fg=INK, highlightbackground=LINE, highlightthickness=1,
            wrap="word", state="disabled", padx=10, pady=6,
        )
        self.log.tag_configure("ok", foreground=GREEN)
        self.log.tag_configure("warn", foreground="#b07a00")
        self.log.tag_configure("err", foreground=RED)
        self.log.tag_configure("big", font=FONT_B, foreground=INK)

        self.result = tk.Frame(bottom, bg=BG)
        top = tk.Frame(self.result, bg=BG)
        top.pack(fill="x")
        self._button(top, "Abrir el plano en AutoCAD", self._open_plan, primary=True).pack(side="left")
        self._button(top, "🔍  Ver el resultado aquí", self._open_viewer, primary=True).pack(side="left", padx=8)
        tk.Label(self.result, text="Abrir carpeta de…", bg=BG, fg=GRAY, font=FONT_S).pack(anchor="w", pady=(8, 2))
        self.folder_row = tk.Frame(self.result, bg=BG)
        self.folder_row.pack(fill="x")
        self.folder_buttons: dict[str, tk.Button] = {}
        for key, label, sub_folder in (
            ("plan", "📐 Plano AutoCAD", FOLDER_PLAN),
            ("preview", "🖼 Vistas previas", FOLDER_PREVIEW),
            ("photos", "📷 Fotos usadas", FOLDER_PHOTOS),
            ("pdf", "📄 PDF original", FOLDER_PDF),
            ("all", "📂 Todo", ""),
        ):
            button = self._button(self.folder_row, label, lambda f=sub_folder: self._open_subfolder(f), primary=False)
            button.pack(side="left", padx=(0, 6))
            self.folder_buttons[key] = button

    def _button(self, parent: tk.Widget, text: str, command, primary: bool, big: bool = False) -> tk.Button:
        return tk.Button(
            parent, text=text, command=command, font=("Segoe UI", 12 if big else 10, "bold" if primary else "normal"),
            bd=0, relief="flat", cursor="hand2", padx=16 if primary else 10, pady=8 if big else 5,
            bg=BLUE if primary else "#eef2f8", fg="white" if primary else INK,
            activebackground=BLUE_DARK if primary else LINE, activeforeground="white" if primary else INK,
            disabledforeground="#9fb0c8",
        )

    # ---------- plano ----------

    def _draw_zone(self, hot: bool = False) -> None:
        zone = self.zone
        zone.delete("all")
        w, h = max(zone.winfo_width(), 200), max(zone.winfo_height(), 120)
        zone.configure(bg=ZONE_HOT if hot and not self.busy else ZONE)
        zone.create_rectangle(8, 8, w - 8, h - 8, outline=BLUE, dash=(7, 5), width=2)
        if self.pdfs:
            names = "\n".join(f"📄  {p.name}" for p in self.pdfs[:4]) + (f"\n… y {len(self.pdfs) - 4} más" if len(self.pdfs) > 4 else "")
            zone.create_text(w / 2, h / 2 - 12, text=names, fill=INK, font=FONT_B, justify="center")
            zone.create_text(w / 2, h - 26, text="Haz clic para cambiar el plano", fill=GRAY, font=FONT_S)
        else:
            zone.create_text(w / 2, h / 2 - 22, text="📄", font=("Segoe UI Emoji", 28), fill=BLUE)
            zone.create_text(
                w / 2, h / 2 + 18, fill=INK, font=("Segoe UI", 12, "bold"),
                text="Arrastra aquí tu plano en PDF" if HAS_DND else "Haz clic para elegir tu plano en PDF",
            )
            if HAS_DND:
                zone.create_text(w / 2, h / 2 + 42, text="o haz clic para buscarlo", fill=GRAY, font=FONT_S)

    def _choose_pdfs(self) -> None:
        if self.busy:
            return
        files = filedialog.askopenfilenames(title="Elige tu plano en PDF", filetypes=[("Planos en PDF", "*.pdf")])
        if files:
            self._set_pdfs(list(files))

    def _set_pdfs(self, paths: list[str]) -> None:
        pdfs, ignored = collect_pdfs(paths)
        if not pdfs:
            messagebox.showinfo("TrazoCAD", "Eso no es un PDF. Arrastra tu plano escaneado en formato PDF.")
            return
        self.pdfs = pdfs
        if not self.name_touched:
            self.name_var.set(pdfs[0].stem)
        self._hide_result()
        self._refresh_all()

    # ---------- fotos ----------

    def _choose_photos(self) -> None:
        if self.busy:
            return
        patterns = " ".join(f"*{ext}" for ext in sorted(PHOTO_EXTENSIONS))
        files = filedialog.askopenfilenames(title="Elige fotos de partes del plano", filetypes=[("Fotos", patterns)])
        if files:
            self._add_photos([Path(f) for f in files])

    def _add_photos(self, paths: list[Path]) -> None:
        merged = unique_photos(self.photos + paths)
        self.photos = merged
        self._refresh_photos()

    def _remove_photos(self) -> None:
        if self.busy:
            return
        selected = set(self.photo_list.curselection())
        self.photos = [p for i, p in enumerate(self.photos) if selected and i not in selected] if selected else []
        self._refresh_photos()

    def _refresh_photos(self) -> None:
        self.photo_list.delete(0, "end")
        for photo in self.photos:
            self.photo_list.insert("end", "📷  " + photo.name)
        if not self.photos:
            self.photo_list.insert("end", "Aún no hay fotos. Es opcional.")
            self.photo_list.itemconfigure(0, foreground=GRAY)

    # ---------- carpeta ----------

    def _choose_base(self) -> None:
        if self.busy:
            return
        folder = filedialog.askdirectory(title="¿Dentro de qué carpeta lo guardo?", initialdir=str(self.base_dir if self.base_dir.exists() else PROJECT_ROOT))
        if folder:
            self.base_dir = Path(folder)
            self._refresh_all()

    def _on_name_edit(self) -> None:
        if self.focus_get() is self.name_entry:
            self.name_touched = True
        self._refresh_folder_label()

    def _folder_name(self) -> str:
        fallback = self.pdfs[0].stem if self.pdfs else "Plano"
        return clean_folder_name(self.name_var.get(), fallback)

    def _target_dir(self) -> Path:
        return self.base_dir / self._folder_name()

    def _refresh_folder_label(self) -> None:
        target = self._target_dir()
        verb = "Se usará la carpeta existente" if target.exists() else "Se creará la carpeta"
        self.create_label.configure(text=f"{verb}:\n{target}")

    def _refresh_all(self) -> None:
        self._draw_zone()
        self.base_label.configure(text=self._shorten(str(self.base_dir), 30))
        self._refresh_folder_label()
        self._refresh_photos()
        self.pdf_hint.configure(
            text=f"{len(self.pdfs)} plano(s) listo(s) para convertir." if self.pdfs
            else "Solo PDF escaneados. También puedes soltar varias fotos aquí para agregarlas."
        )
        self.go.configure(state="normal" if self.pdfs or not self.busy else "disabled")

    @staticmethod
    def _shorten(text: str, limit: int) -> str:
        return text if len(text) <= limit else "…" + text[-(limit - 1):]

    def _on_drop(self, event) -> None:
        if self.busy:
            return
        dropped = list(self.tk.splitlist(event.data))
        images = [Path(p) for p in dropped if Path(p).suffix.lower() in PHOTO_EXTENSIONS]
        others = [p for p in dropped if Path(p).suffix.lower() not in PHOTO_EXTENSIONS]
        if images:
            self._add_photos(images)
        if others:
            self._set_pdfs(others)

    # ---------- conversión ----------

    def _conversion_options(self, out_dir: Path) -> Options:
        return Options(
            photos=tuple(self.photos),
            output_dir=out_dir,
            read_text=self.read_text.get(),
            show_scan_fill=self.show_fill.get(),
            keep_dxf=self.keep_dxf.get(),
            rotation=ROTATIONS[self.rotation.get()],
        )

    def _start(self) -> None:
        if self.busy:
            self._stop()
            return
        if not self.pdfs:
            messagebox.showinfo("TrazoCAD", "Primero arrastra tu plano en PDF a la zona azul.")
            return
        out_dir = self._target_dir()
        existed = out_dir.exists()
        try:
            out_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            messagebox.showerror("TrazoCAD", f"No pude crear la carpeta:\n{out_dir}\n\n{exc}")
            return
        self.out_dir = out_dir
        self.outputs = []
        self.previews = []
        self.photos_used = []
        self.summary = ""
        self._hide_result()
        self._clear_log()
        self._log(("Se usará la carpeta existente: " if existed else "Carpeta creada: ") + str(out_dir), "ok")
        self.jobs = list(self.pdfs)
        self._set_busy(True)
        self._next_job()

    def _next_job(self) -> None:
        if not self.jobs:
            self._finish()
            return
        pdf = self.jobs.pop(0)
        assert self.out_dir is not None
        self.status.configure(text=f"Convirtiendo {pdf.name}… (puede tardar unos minutos)")
        self._log(f"Convirtiendo {pdf.name}", "big")
        command = build_command(sys.executable, PROJECT_ROOT / "main.py", pdf, self._conversion_options(self.out_dir))
        threading.Thread(target=self._run, args=(command, pdf), daemon=True).start()

    def _run(self, command: list[str], pdf: Path) -> None:
        env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
        seen: set[str] = set()
        ok = False
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
                    ok = True
                if event.kind == "error":
                    errors.append(event.text)
                    continue
                self.events.put(("event", event))
            self.process.wait()
        except Exception as exc:  # no tumbar la ventana por un fallo al lanzar
            errors.append(str(exc))
        finally:
            self.events.put(("end", (pdf, ok, errors, self.stop_requested)))

    def _stop(self) -> None:
        if self.process and self.process.poll() is None:
            self.stop_requested = True
            self.jobs.clear()
            self.process.terminate()
            self._log("Detenido.", "warn")

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
        if event.kind == "done":
            self.outputs.append(Path(event.text))
        elif event.kind == "preview":
            self.previews.append(Path(event.text))
        elif event.kind == "photo":
            self.photos_used.append(Path(event.text))
        elif event.kind == "summary":
            self.summary = event.text
            self._log("Contiene: " + event.text + ".")
        else:
            self._log(event.text, "warn" if event.kind == "warn" else None)

    def _on_end(self, pdf: Path, ok: bool, errors: list[str], stopped: bool) -> None:
        if ok:
            self._log(f"✔ Listo: {self.outputs[-1].name}", "ok")
        elif not stopped:
            self._log(f"✖ No pude convertir {pdf.name}: " + (errors[-1] if errors else "no se generó ningún archivo"), "err")
        self._next_job()

    def _finish(self) -> None:
        self._set_busy(False)
        if self.outputs:
            self.status.configure(text="¡Listo! " + (f"Contiene: {self.summary}." if self.summary else "Tu plano está en AutoCAD."), fg=GREEN)
            self.log.pack_forget()  # el registro cede su lugar a los botones de resultados
            assert self.out_dir is not None
            self.folder_buttons["photos"].configure(state="normal" if (self.out_dir / FOLDER_PHOTOS).is_dir() else "disabled")
            self.folder_buttons["preview"].configure(state="normal" if (self.out_dir / FOLDER_PREVIEW).is_dir() else "disabled")
            self.result.pack(fill="x", pady=(8, 0))
        else:
            self.status.configure(text="No se generó ningún plano.", fg=RED)

    def _set_busy(self, busy: bool) -> None:
        self.busy = busy
        if busy:
            self.stop_requested = False
            self.started_at = time.time()
            self.status.configure(fg=GRAY)
            self.progress.pack(fill="x", pady=(8, 0), before=self.status)
            self.progress.start(12)
            self.go.configure(text="Detener", bg=RED, activebackground="#b13333")
            self.log.pack(fill="x", pady=(4, 0))
            self.after(50, self._grow_to_fit)
        else:
            self.progress.stop()
            self.progress.pack_forget()
            self.go.configure(text="Convertir a AutoCAD", bg=BLUE, activebackground=BLUE_DARK)
        self._draw_zone()

    def _grow_to_fit(self) -> None:
        """Al empezar a convertir aparece el registro: se agranda la ventana para que quepa."""
        self.update_idletasks()
        needed = self.winfo_reqheight() + 10
        limit = self.winfo_screenheight() - 70
        if needed > self.winfo_height():
            self.geometry(f"{self.winfo_width()}x{min(needed, limit)}+{self.winfo_x()}+10")

    def _tick(self) -> None:
        if self.busy:
            seconds = int(time.time() - self.started_at)
            base = self.status.cget("text").split("  ·  ")[0]
            self.status.configure(text=f"{base}  ·  {seconds // 60}:{seconds % 60:02d}")
        self.after(1000, self._tick)

    # ---------- registro y resultado ----------

    def _log(self, text: str, tag: str | None = None) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", text + "\n", tag or ())
        self.log.configure(state="disabled")
        self.log.see("end")

    def _clear_log(self) -> None:
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")

    def _hide_result(self) -> None:
        self.result.pack_forget()
        self.status.configure(text="", fg=GRAY)

    def _open_plan(self) -> None:
        if self.outputs:
            os.startfile(self.outputs[-1])  # type: ignore[attr-defined]

    def _open_subfolder(self, name: str) -> None:
        """Abre en el Explorador una de las carpetas de resultados ('' = la carpeta completa)."""
        if self.out_dir is None:
            return
        target = self.out_dir / name if name else self.out_dir
        if target.is_dir():
            os.startfile(target)  # type: ignore[attr-defined]
        else:
            messagebox.showinfo("TrazoCAD", "Esa carpeta no se creó en esta conversión (por ejemplo, no había fotos que coincidieran).")

    def _open_viewer(self) -> None:
        items: list[tuple[str, Path]] = []
        for path in self.previews:
            kind = "Resultado (lo que contiene el .dwg)" if path.stem.endswith("_resultado") else "Escaneo original (enderezado)"
            items.append((f"{kind} — {path.stem.rsplit('_', 1)[0]}", path))
        items += [(f"Foto usada — {path.name}", path) for path in self.photos_used if path.exists()]
        if not items:
            messagebox.showinfo("TrazoCAD", "No hay vistas previas para mostrar.")
            return
        ImageViewer(self, items)


def main() -> None:
    App().mainloop()


if __name__ == "__main__":
    main()
