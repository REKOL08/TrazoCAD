"""Visor de imágenes del programa: ver el resultado, el escaneo y las fotos sin salir de la ventana.

Rueda del mouse = acercar o alejar (hacia el puntero), arrastrar = mover, doble clic = ajustar a la ventana.
"""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import ttk

from PIL import Image, ImageTk

BG = "#1b2230"
BAR = "#0d3b8e"
MAX_ZOOM_FACTOR = 12.0


class ImageViewer(tk.Toplevel):
    def __init__(self, master: tk.Misc, items: list[tuple[str, Path]], start: int = 0) -> None:
        super().__init__(master)
        self.title("Vista previa")
        self.geometry("1100x760+120+30")
        self.minsize(520, 380)
        self.configure(bg=BG)
        self.items = items
        self.image: Image.Image | None = None
        self.photo: ImageTk.PhotoImage | None = None
        self.scale = 1.0
        self.fit_scale = 1.0
        self.origin = [0.0, 0.0]  # esquina superior izquierda de lo visible, en píxeles de la imagen
        self._drag: tuple[int, int, float, float] | None = None
        self._cache: dict[Path, Image.Image] = {}

        bar = tk.Frame(self, bg=BAR)
        bar.pack(fill="x")
        tk.Label(bar, text="Ver:", bg=BAR, fg="white", font=("Segoe UI", 10)).pack(side="left", padx=(14, 6), pady=8)
        self.choice = tk.StringVar()
        names = [name for name, _ in items]
        box = ttk.Combobox(bar, textvariable=self.choice, values=names, state="readonly", width=54, font=("Segoe UI", 10))
        box.pack(side="left", pady=8)
        box.bind("<<ComboboxSelected>>", lambda _e: self._show(names.index(self.choice.get())))
        for text, command in (("＋", lambda: self._zoom_at(1.3, None)), ("－", lambda: self._zoom_at(1 / 1.3, None)), ("Ajustar", self._fit)):
            tk.Button(bar, text=text, command=command, bd=0, bg="#2a58b5", fg="white", activebackground="#1f4a9c",
                      activeforeground="white", font=("Segoe UI", 10, "bold"), padx=10, cursor="hand2").pack(side="left", padx=(8, 0), pady=8)
        self.hint = tk.Label(bar, text="Rueda: zoom · Arrastrar: mover · Doble clic: ajustar", bg=BAR, fg="#b9cdf5", font=("Segoe UI", 9))
        self.hint.pack(side="right", padx=14)

        self.canvas = tk.Canvas(self, bg=BG, highlightthickness=0, cursor="fleur")
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda _e: self._redraw())
        self.canvas.bind("<MouseWheel>", self._on_wheel)
        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_motion)
        self.canvas.bind("<Double-Button-1>", lambda _e: self._fit())
        self.after(60, lambda: self._show(max(0, min(start, len(items) - 1))))

    # ---------- carga ----------

    def _show(self, index: int) -> None:
        if not self.items:
            return
        name, path = self.items[index]
        self.choice.set(name)
        if path not in self._cache:
            image = Image.open(path)
            image.load()
            self._cache[path] = image.convert("RGB")
        self.image = self._cache[path]
        self._fit()

    def _fit(self) -> None:
        if self.image is None:
            return
        cw, ch = max(self.canvas.winfo_width(), 50), max(self.canvas.winfo_height(), 50)
        self.fit_scale = min(cw / self.image.width, ch / self.image.height)
        self.scale = self.fit_scale
        self.origin = [(self.image.width - cw / self.scale) / 2, (self.image.height - ch / self.scale) / 2]
        self._redraw()

    # ---------- dibujo ----------

    def _redraw(self) -> None:
        if self.image is None:
            return
        cw, ch = max(self.canvas.winfo_width(), 1), max(self.canvas.winfo_height(), 1)
        view_w, view_h = cw / self.scale, ch / self.scale
        x0, y0 = self.origin
        # no dejar que la imagen se escape de la ventana
        if view_w >= self.image.width:
            x0 = (self.image.width - view_w) / 2
        else:
            x0 = min(max(x0, 0), self.image.width - view_w)
        if view_h >= self.image.height:
            y0 = (self.image.height - view_h) / 2
        else:
            y0 = min(max(y0, 0), self.image.height - view_h)
        self.origin = [x0, y0]

        left, top = max(int(x0), 0), max(int(y0), 0)
        right, bottom = min(int(x0 + view_w) + 1, self.image.width), min(int(y0 + view_h) + 1, self.image.height)
        crop = self.image.crop((left, top, right, bottom))
        size = (max(int(crop.width * self.scale), 1), max(int(crop.height * self.scale), 1))
        resample = Image.LANCZOS if self.scale < 1 else Image.NEAREST if self.scale > 3 else Image.BILINEAR
        self.photo = ImageTk.PhotoImage(crop.resize(size, resample))
        self.canvas.delete("all")
        self.canvas.create_image((left - x0) * self.scale, (top - y0) * self.scale, anchor="nw", image=self.photo)

    # ---------- interacción ----------

    def _zoom_at(self, factor: float, point: tuple[int, int] | None) -> None:
        if self.image is None:
            return
        cw, ch = self.canvas.winfo_width(), self.canvas.winfo_height()
        px, py = point if point else (cw / 2, ch / 2)
        before_x, before_y = self.origin[0] + px / self.scale, self.origin[1] + py / self.scale
        self.scale = min(max(self.scale * factor, self.fit_scale * 0.5), self.fit_scale * MAX_ZOOM_FACTOR)
        self.origin = [before_x - px / self.scale, before_y - py / self.scale]
        self._redraw()

    def _on_wheel(self, event) -> None:
        self._zoom_at(1.2 if event.delta > 0 else 1 / 1.2, (event.x, event.y))

    def _on_press(self, event) -> None:
        self._drag = (event.x, event.y, self.origin[0], self.origin[1])

    def _on_motion(self, event) -> None:
        if self._drag is None:
            return
        x, y, ox, oy = self._drag
        self.origin = [ox - (event.x - x) / self.scale, oy - (event.y - y) / self.scale]
        self._redraw()
