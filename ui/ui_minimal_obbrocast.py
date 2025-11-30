"""
Interfaz "OBBroadcast" en Tkinter
 - Requiere Python 3
 - Coloca el icono (input_line.png) en la misma carpeta o cambia ICON_PATH
 - Ejecuta: python ui_minimal_obbrocast.py
"""

import tkinter as tk
from tkinter import ttk, messagebox
import math
import random
import os

# Intentar usar PIL (mejor para redimensionar PNG); si no está, usar PhotoImage directo
try:
    from PIL import Image, ImageTk
    PIL_AVAILABLE = True
except Exception:
    PIL_AVAILABLE = False

ICON_PATH = "input_line.png"  # Cambia aquí si tu icon está en otro path

WIDTH, HEIGHT = 1000, 640
CENTER_X, CENTER_Y = WIDTH // 2, HEIGHT // 2 - 30

class OBBroadcastApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("OBBroadcast")
        self.geometry(f"{WIDTH}x{HEIGHT}")
        self.configure(bg="#f6f6f6")
        self.resizable(False, False)

        self.canvas = tk.Canvas(self, width=WIDTH, height=HEIGHT, bg="#ffffff", highlightthickness=0)
        self.canvas.place(x=20, y=10)  # pequeño margen

        # Cargar icono (si existe)
        self.icon_img = None
        if os.path.exists(ICON_PATH):
            try:
                if PIL_AVAILABLE:
                    img = Image.open(ICON_PATH).convert("RGBA")
                    # tamaño relativo a la ventana
                    icon_size = 150
                    img = img.resize((icon_size, icon_size), Image.LANCZOS)
                    self.icon_img = ImageTk.PhotoImage(img)
                else:
                    self.icon_img = tk.PhotoImage(file=ICON_PATH)
            except Exception as e:
                print("Error cargando icono:", e)
        else:
            print(f"Icono no encontrado en {ICON_PATH}. Se usará dibujo por defecto.")

        # Texto superior
        self.canvas.create_text(CENTER_X, 40, text="OBBroadcast", font=("Inter", 28, "bold"), fill="#111111")
        self.canvas.create_text(CENTER_X, 92, text="Transmitting", font=("Inter", 44, "bold"), fill="#111111")

        # Parametros VU / Stereo
        self.outer_radius = 150         # radio fondo plomo
        self.green_ring_width = 18      # grosor de las líneas de nivel
        self.red_center_radius = 110    # radio del centro rojo (dentro del anillo)
        # niveles estéreo (0..1) - input izquierdo/derecho (para mostrar (((( o )))) )
        self.vu_left = 0.25
        self.vu_right = 0.25
        # receptor (barra centrada) - nivel combinado (0..1)
        self.receiver_level = 0.4

        # Dibujar elementos estáticos
        self.draw_static_elements()

        # Iniciar animacion
        self.animate()

    def draw_static_elements(self):
        # Fondo circular plomo
        ox, oy = CENTER_X, CENTER_Y + 10
        r_plomo = self.outer_radius
        self.canvas.create_oval(ox - r_plomo, oy - r_plomo, ox + r_plomo, oy + r_plomo,
                                fill="#d0d3d6", outline="")  # fondo plomo

        # Círculo rojo central (dentro)
        r_red = self.red_center_radius
        self.red_circle = self.canvas.create_oval(ox - r_red, oy - r_red, ox + r_red, oy + r_red,
                                                 fill="#d9534f", outline="")  # rojo centro

        # Si hay icono, colocarlo centrado sobre el rojo:
        if self.icon_img:
            # centrar la imagen
            self.icon_id = self.canvas.create_image(ox, oy, image=self.icon_img)
        else:
            # dibujar un micrófono simple si no hay icono
            mic_h = 70
            self.canvas.create_rectangle(ox - 18, oy - mic_h//2, ox + 18, oy + mic_h//2, fill="#ffffff", outline="")
            self.canvas.create_oval(ox-30, oy+mic_h//2-10, ox+30, oy+mic_h//2+20, fill="#ffffff", outline="")

        # Barra horizontal de fondo (plo) para receptor
        bar_w = 520
        bar_h = 18
        bx1 = CENTER_X - bar_w // 2
        by = oy + self.outer_radius + 32
        bx2 = CENTER_X + bar_w // 2
        # Fondo de la barra de receptor con borde sutil
        self.bar_bg = self.canvas.create_rectangle(bx1, by, bx2, by + bar_h, fill="#dbe0e3", outline="#c9cfd3", width=1)
        # Linea central vertical que indica el centro (separador stereo)
        self.canvas.create_line(CENTER_X, by - 8, CENTER_X, by + bar_h + 8, fill="#b9b9b9")
        # Ticks y marcas de extremo (definen el maximo)
        ticks = 8
        tick_h = 6
        for i in range(ticks + 1):
            tx = bx1 + (bar_w) * (i / ticks)
            # dibujar ticks encima
            self.canvas.create_line(tx, by - tick_h, tx, by + bar_h + tick_h, fill="#e8e8e8")
        # extremos (marcadores para maximo)
        self.canvas.create_line(bx1, by - 8, bx1, by + bar_h + 8, fill="#b9b9b9", width=1)
        self.canvas.create_line(bx2, by - 8, bx2, by + bar_h + 8, fill="#b9b9b9", width=1)

        # stop button (colocado debajo de la barra de receptor)
        btn_x = CENTER_X
        btn_y = by + bar_h + 40
        # Estilizar el botón Stop para que coincida con Settings
        style = ttk.Style(self)
        style.configure('Stop.TButton', font=("Inter", 18), padding=(8, 6))
        self.stop_btn = ttk.Button(self, text="Stop", command=self.on_stop, style='Stop.TButton')
        # place button using window on canvas
        self.canvas.create_window(btn_x, btn_y, window=self.stop_btn, width=140, height=48)

        # Settings button — alinear a la derecha y dentro del canvas para que siempre sea visible
        style.configure('Settings.TButton', font=("Inter", 18), padding=(4, 2))
        self.settings_btn = ttk.Button(self, text="⚙ Settings", command=self.on_settings, style='Settings.TButton')
        self.canvas.create_window(WIDTH - 40, HEIGHT - 80, window=self.settings_btn, anchor='e')

        # VU level segments (stereo) - crear solo pequeños arcos laterales de 20° por anillo
        # Para efecto '((((((o)))))))' tendremos un arco en el hemisferio izquierdo
        # y otro en el derecho por cada anillo, cada uno con 20 grados de extensión.
        self.segment_ids = []  # list of dicts: {'id': canvas_id, 'side': 'left'|'right', 'ring': idx}
        rings = 6
        ring_spacing = 14
        base_outer = r_red + 6
        inactive_color = "#cfcfcf"
        arc_extent = 50
        for ring in range(rings):
            r = base_outer + ring * ring_spacing
            width_val = max(4, 10 - ring)
            # Left arc centered at 180° (face left) -> start = 180 - arc_extent/2
            left_start = 180 - arc_extent / 2
            cid_l = self.canvas.create_arc(ox - r, oy - r, ox + r, oy + r,
                                           start=left_start, extent=arc_extent,
                                           style=tk.ARC, width=width_val, outline=inactive_color)
            self.segment_ids.append({'id': cid_l, 'side': 'left', 'ring': ring})
            # Right arc centered at 0° (face right) -> start = 0 - arc_extent/2
            right_start = (360 - arc_extent / 2) % 360
            cid_r = self.canvas.create_arc(ox - r, oy - r, ox + r, oy + r,
                                           start=right_start, extent=arc_extent,
                                           style=tk.ARC, width=width_val, outline=inactive_color)
            self.segment_ids.append({'id': cid_r, 'side': 'right', 'ring': ring})

        # VU receptor (barra) - representamos 2 barras (izq y der) que parten del centro
        # izquierda
        self.receiver_left = self.canvas.create_rectangle(CENTER_X, by, CENTER_X, by + bar_h, fill="#3fbf5f", outline="")
        # derecha
        self.receiver_right = self.canvas.create_rectangle(CENTER_X, by, CENTER_X, by + bar_h, fill="#3fbf5f", outline="")
        # Caps para dar apariencia redondeada
        cap_pad = bar_h // 2
        self.receiver_left_cap = self.canvas.create_oval(CENTER_X - cap_pad, by, CENTER_X + cap_pad, by + bar_h, fill="#3fbf5f", outline="")
        self.receiver_right_cap = self.canvas.create_oval(CENTER_X - cap_pad, by, CENTER_X + cap_pad, by + bar_h, fill="#3fbf5f", outline="")

        # Texto labels (small) - centrar encima de la barra del VU receptor
        # Actual: 'Receiver Audio' en el centro de la barra
        self.canvas.create_text(CENTER_X, by - 6, text="Receiver Audio", anchor="center", font=("Inter", 12, "bold"), fill="#333333")
        # Texto label para el input de audio (encima del VU input)
        # Centrado por encima del anillo del mic / arcs
        self.canvas.create_text(CENTER_X, oy - r_red - 18, text="Audio Input", anchor="s", font=("Inter", 12, "bold"), fill="#333333")
        # No numeric level text: UI uses visual bars only

    def on_settings(self):
        # Placeholder settings handler; expand to open real settings pane
        messagebox.showinfo("Settings", "Settings dialog placeholder")

    def on_stop(self):
        # Función mock del botón Stop
        self.vu_left = 0
        self.vu_right = 0
        self.receiver_level = 0

    def animate(self):
        # Simular niveles: aquí se podría tomar del mic real si se integra con audio
        # Simulación: mezcla de random y suavizado
        # Simular niveles stereo: left/right independientes
        target_left = abs(math.sin(random.random() * 3.14 * 2)) * 0.95
        target_right = abs(math.cos(random.random() * 3.14 * 2)) * 0.95
        target_recv = (target_left + target_right) / 2 * 0.95

        # suavizado simple
        self.vu_left = 0.82 * self.vu_left + 0.18 * target_left
        self.vu_right = 0.82 * self.vu_right + 0.18 * target_right
        self.receiver_level = 0.85 * self.receiver_level + 0.15 * target_recv

        self.update_vu_ring()
        self.update_receiver_bar()

        # Llamar de nuevo en 80 ms
        self.after(80, self.animate)

    def update_vu_ring(self):
        # Actualizar las líneas tipo paréntesis para left/right según self.vu_left / self.vu_right
        ox, oy = CENTER_X, CENTER_Y + 10
        # cada anillo (ring) tiene un umbral para iluminar sus segmentos
        thresholds = [0.06, 0.18, 0.32, 0.46, 0.6, 0.74]
        active_color = "#3fbf5f"
        inactive_color = "#cfcfcf"

        # recorrer todos los segmentos y colorear según side y ring threshold
        for seg in self.segment_ids:
            ring = seg['ring']
            side = seg['side']
            cid = seg['id']
            thr = thresholds[ring]
            if side == 'left':
                col = active_color if self.vu_left >= thr else inactive_color
            else:
                col = active_color if self.vu_right >= thr else inactive_color
            self.canvas.itemconfigure(cid, outline=col)

    def update_receiver_bar(self):
        # Actualizar barras izquierda y derecha partiendo del centro
        # bar background coords
        bar_w = 520
        bar_h = 18
        bx1 = CENTER_X - bar_w // 2
        by = CENTER_Y + 10 + self.outer_radius + 32
        bx2 = CENTER_X + bar_w // 2
        # la longitud máxima desde el centro a un extremo
        half_len = (bx2 - bx1) // 2
        # longitud actual en px según level
        # asegurar cur dentro de 0..half_len
        if self.receiver_level <= 0:
            cur = 0
        else:
            cur = int(max(0, min(1.0, self.receiver_level)) * half_len)
        # izquierda: from CENTER_X - cur to CENTER_X
        self.canvas.coords(self.receiver_left, CENTER_X - cur, by, CENTER_X, by + bar_h)
        # derecha: from CENTER_X to CENTER_X + cur
        self.canvas.coords(self.receiver_right, CENTER_X, by, CENTER_X + cur, by + bar_h)
        # cap left (círculo en el extremo izquierdo del tramo)
        cap_pad = bar_h // 2
        left_cap_x = CENTER_X - cur
        right_cap_x = CENTER_X + cur
        # mantener caps dentro del bar area (si cur==0, esconder caps moviéndolos fuera)
        # ocultar caps si cur == 0
        if cur <= 0:
            # mover las caps fuera del área visible
            self.canvas.coords(self.receiver_left_cap, -10, -10, -5, -5)
            self.canvas.coords(self.receiver_right_cap, -10, -10, -5, -5)
        else:
            # caps dentro del área, 'clamp' en límites de la barra
            left_cap_x = max(left_cap_x, bx1 + cap_pad)
            right_cap_x = min(right_cap_x, bx2 - cap_pad)
            self.canvas.coords(self.receiver_left_cap, left_cap_x - cap_pad, by, left_cap_x + cap_pad, by + bar_h)
            self.canvas.coords(self.receiver_right_cap, right_cap_x - cap_pad, by, right_cap_x + cap_pad, by + bar_h)

        # color transitions for the receiver bars: green -> yellow -> red near the end
        level_norm = cur / float(half_len) if half_len else 0
        if level_norm >= 0.9:
            color = "#e04b4b"  # red
        elif level_norm >= 0.65:
            color = "#f2c94c"  # yellow
        else:
            color = "#3fbf5f"  # green

        # update bar colors
        self.canvas.itemconfigure(self.receiver_left, fill=color)
        self.canvas.itemconfigure(self.receiver_right, fill=color)
        # Don't show any numeric percentage; VU is visual only

    

if __name__ == "__main__":
    app = OBBroadcastApp()
    app.mainloop()
