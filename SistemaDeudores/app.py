import tkinter as tk
from tkinter import ttk, messagebox
import sqlite3
from datetime import datetime
import os 

# ==========================================
# CONFIGURACIÓN DE COLORES Y ESTILOS
# ==========================================
COLORS = {
    'primary': '#2980b9',       # Azul fuerte
    'secondary': '#2c3e50',     # Gris oscuro (Sidebar)
    'success': '#27ae60',       # Verde (Pagos/Guardar)
    'warning': '#f39c12',       # Naranja (Agregar Deuda)
    'danger': '#c0392b',        # Rojo (Eliminar)
    'light': '#ecf0f1',         # Gris muy claro (Fondos)
    'white': '#ffffff',
    'text': '#2c3e50',
    'text_light': '#ecf0f1',    # Texto claro sobre fondo oscuro
    'input_border': '#bdc3c7',  # Gris borde inputs
    'tooltip_bg': '#ffffe0',    # Amarillo suave para tooltip
    'tooltip_border': '#000000' # Borde negro fino
}

FONTS = {
    'h1': ('Segoe UI', 18, 'bold'),
    'h2': ('Segoe UI', 14, 'bold'),
    'body': ('Segoe UI', 10),
    'body_bold': ('Segoe UI', 10, 'bold'),
    'small': ('Segoe UI', 8)
}

# --- PARTE 1: LA BASE DE DATOS ---
class BaseDeDatos:
    def __init__(self, db_name="taller_repuestos_final.db"):
        self.conn = sqlite3.connect(db_name)
        self.cursor = self.conn.cursor()
        self.crear_tablas()

    def crear_tablas(self):
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS clientes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                dni TEXT,
                nombre TEXT NOT NULL,
                telefono TEXT,
                localidad TEXT
            )
        """)
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS deudas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cliente_id INTEGER,
                monto_total REAL NOT NULL,
                monto_pagado REAL DEFAULT 0,
                descripcion TEXT,
                estado TEXT DEFAULT 'PENDIENTE',
                fecha_creacion TEXT,
                fecha_pago TEXT,
                metodo_pago TEXT, 
                FOREIGN KEY(cliente_id) REFERENCES clientes(id)
            )
        """)
        self.conn.commit()

    def existe_cliente(self, dni):
        self.cursor.execute("SELECT id FROM clientes WHERE dni = ?", (dni,))
        row = self.cursor.fetchone()
        return row is not None

    def agregar_cliente(self, dni, nombre, localidad):
        self.cursor.execute("INSERT INTO clientes (dni, nombre, telefono, localidad) VALUES (?, ?, ?, ?)", 
                            (dni, nombre, "", localidad))
        self.conn.commit()

    def agregar_deuda(self, cliente_id, monto, descripcion, fecha_manual=None):
        if fecha_manual:
            fecha_final = fecha_manual
        else:
            fecha_final = datetime.now().strftime("%Y-%m-%d %H:%M")
            
        self.cursor.execute("""
            INSERT INTO deudas (cliente_id, monto_total, monto_pagado, descripcion, estado, fecha_creacion) 
            VALUES (?, ?, 0, ?, 'PENDIENTE', ?)
        """, (cliente_id, monto, descripcion, fecha_final))
        self.conn.commit()

    def registrar_pago_parcial(self, deuda_id, nuevo_pago, metodo):
        self.cursor.execute("SELECT monto_total, monto_pagado FROM deudas WHERE id = ?", (deuda_id,))
        resultado = self.cursor.fetchone()
        if not resultado: return
        
        total, pagado_actual = resultado
        pagado_nuevo = pagado_actual + nuevo_pago
        
        if pagado_nuevo >= total:
            nuevo_estado = "PAGADA"
        else:
            nuevo_estado = "PARCIAL"

        ahora = datetime.now().strftime("%Y-%m-%d %H:%M")
        
        self.cursor.execute("""
            UPDATE deudas 
            SET monto_pagado = ?, estado = ?, fecha_pago = ?, metodo_pago = ?
            WHERE id = ?
        """, (pagado_nuevo, nuevo_estado, ahora, metodo, deuda_id))
        self.conn.commit()

    def obtener_clientes_con_saldo(self, filtro=""):
        query = """
            SELECT c.id, c.dni, c.nombre, c.localidad, 
                   COALESCE(SUM(CASE WHEN (d.monto_total - d.monto_pagado) < 0 THEN 0 ELSE (d.monto_total - d.monto_pagado) END), 0) as saldo_restante
            FROM clientes c
            LEFT JOIN deudas d ON c.id = d.cliente_id
            WHERE c.nombre LIKE ? OR c.dni LIKE ? OR c.localidad LIKE ?
            GROUP BY c.id
            ORDER BY c.nombre ASC
        """
        filtro_sql = '%' + filtro + '%'
        self.cursor.execute(query, (filtro_sql, filtro_sql, filtro_sql))
        return self.cursor.fetchall()

    def obtener_historial_cliente(self, cliente_id):
        # Indices: 0:id, 1:desc, 2:total, 3:pagado, 4:resta, 5:fecha_creacion, 6:fecha_pago, 7:estado, 8:metodo
        query = """
            SELECT id, descripcion, monto_total, monto_pagado, 
                   CASE WHEN (monto_total - monto_pagado) < 0 THEN 0 ELSE (monto_total - monto_pagado) END as resta, 
                   fecha_creacion, fecha_pago, estado, metodo_pago
            FROM deudas 
            WHERE cliente_id = ?
        """
        self.cursor.execute(query, (cliente_id,))
        return self.cursor.fetchall()

    def obtener_total_individual(self, cliente_id):
        query = """
            SELECT COALESCE(SUM(CASE WHEN (monto_total - monto_pagado) < 0 THEN 0 ELSE (monto_total - monto_pagado) END), 0) 
            FROM deudas WHERE cliente_id = ?
        """
        self.cursor.execute(query, (cliente_id,))
        resultado = self.cursor.fetchone()
        return resultado[0] if resultado else 0

    def borrar_deuda_permanentemente(self, deuda_id):
        self.cursor.execute("DELETE FROM deudas WHERE id = ?", (deuda_id,))
        self.conn.commit()

# --- PARTE 2: INTERFAZ GRÁFICA MEJORADA ---
class Aplicacion(tk.Tk):
    def __init__(self):
        super().__init__()
        self.db = BaseDeDatos()
        self.title("Gestión de Repuestos - Sistema de Cobranzas")
        self.geometry("1350x780")
        self.configure(bg=COLORS['light'])
        
        self.cliente_seleccionado_id = None
        
        # Variables para Tooltip
        self.tooltip_window = None
        self.last_tooltip_row = None
        self.last_tooltip_col = None 

        # --- ESTILOS TTK ---
        self.style = ttk.Style()
        self.style.theme_use("clam")
        
        # Configurar Treeview (Tablas)
        self.style.configure("Treeview", 
                             background="white", 
                             foreground=COLORS['text'], 
                             fieldbackground="white",
                             font=FONTS['body'],
                             rowheight=30)
        
        self.style.configure("Treeview.Heading", 
                             font=FONTS['body_bold'], 
                             background=COLORS['light'], 
                             foreground=COLORS['text'])
        
        self.style.map('Treeview', background=[('selected', COLORS['primary'])])

        # Layout Principal
        panel_izquierdo = tk.Frame(self, width=380, bg=COLORS['secondary'])
        panel_izquierdo.pack(side="left", fill="both", expand=False)
        
        self.panel_derecho = tk.Frame(self, bg=COLORS['light'])
        self.panel_derecho.pack(side="right", fill="both", expand=True)

        self.construir_panel_clientes(panel_izquierdo)
        self.construir_panel_detalle(self.panel_derecho)
        
        self.cargar_lista_clientes()

    def construir_panel_clientes(self, parent):
        tk.Label(parent, text="📂 LISTA DE CLIENTES", font=FONTS['h2'], 
                 bg=COLORS['secondary'], fg=COLORS['text_light']).pack(pady=(25, 15))
        
        btn_nuevo = tk.Button(parent, text="+ NUEVO CLIENTE", 
                              bg=COLORS['success'], fg='white', 
                              font=FONTS['body_bold'], 
                              relief="flat", cursor="hand2",
                              command=self.modal_nuevo_cliente)
        btn_nuevo.pack(fill="x", padx=20, pady=10, ipady=10)

        frame_search = tk.Frame(parent, bg=COLORS['secondary'])
        frame_search.pack(fill="x", padx=20, pady=5)
        
        tk.Label(frame_search, text="🔍 Buscar:", bg=COLORS['secondary'], fg="#bdc3c7", font=FONTS['small']).pack(anchor="w")
        
        self.entry_buscar = tk.Entry(frame_search, font=FONTS['body'], relief="solid", bd=1, bg="white")
        self.entry_buscar.pack(fill="x", ipady=5) 
        self.entry_buscar.bind("<KeyRelease>", self.filtrar_clientes)

        frame_tabla = tk.Frame(parent, bg=COLORS['secondary'])
        frame_tabla.pack(fill="both", expand=True, padx=20, pady=15)

        scrollbar = ttk.Scrollbar(frame_tabla)
        scrollbar.pack(side="right", fill="y")

        columns = ("DNI", "Nombre", "Loc", "Saldo")
        self.tree_clientes = ttk.Treeview(frame_tabla, columns=columns, show="headings", yscrollcommand=scrollbar.set)
        
        scrollbar.config(command=self.tree_clientes.yview)

        self.tree_clientes.heading("DNI", text="DNI / ID")
        self.tree_clientes.heading("Nombre", text="Nombre")
        self.tree_clientes.heading("Loc", text="Loc")
        self.tree_clientes.heading("Saldo", text="Debe ($)")
        
        self.tree_clientes.column("DNI", width=70)
        self.tree_clientes.column("Nombre", width=130)
        self.tree_clientes.column("Loc", width=70)
        self.tree_clientes.column("Saldo", width=80)
        
        self.tree_clientes.pack(side="left", fill="both", expand=True)
        self.tree_clientes.bind("<<TreeviewSelect>>", self.seleccionar_cliente)

    def construir_panel_detalle(self, parent):
        # 1. BOTONES DE ACCIÓN (AL FONDO)
        frame_acciones = tk.Frame(parent, bg=COLORS['light'], height=80)
        frame_acciones.pack(side="bottom", fill="x", padx=30, pady=20) 

        btn_eliminar = tk.Button(frame_acciones, text="🗑️ Eliminar Registro", 
                                 bg="#95a5a6", fg="white", 
                                 font=FONTS['body_bold'], relief="flat", cursor="hand2",
                                 padx=15, pady=8,
                                 command=self.eliminar_error)
        btn_eliminar.pack(side="left") 

        btn_pagar = tk.Button(frame_acciones, text="💵  INGRESAR PAGO", 
                              bg=COLORS['success'], fg="white", 
                              font=('Segoe UI', 12, 'bold'), 
                              relief="flat", cursor="hand2",
                              padx=30, pady=10, 
                              command=self.abrir_ventana_pago)
        btn_pagar.pack(side="right")

        # 2. ENCABEZADO (ARRIBA)
        frame_encabezado = tk.Frame(parent, bg=COLORS['light'])
        frame_encabezado.pack(side="top", pady=15, fill="x", padx=30) 

        # Logo
        carpeta_actual = os.path.dirname(os.path.abspath(__file__))
        ruta_completa_imagen = os.path.join(carpeta_actual, "Logo_Sbrolla.png")
        if os.path.exists(ruta_completa_imagen):
            try:
                self.img_logo = tk.PhotoImage(file=ruta_completa_imagen)
                self.img_logo = self.img_logo.subsample(4, 4) 
                lbl_img = tk.Label(frame_encabezado, image=self.img_logo, bg=COLORS['light'])
                lbl_img.pack(side="left", padx=(0, 15)) 
            except: pass

        # ETIQUETA CLIENTE
        self.lbl_cliente_nombre = tk.Label(frame_encabezado, 
                                           text="Seleccione un cliente...", 
                                           font=('Segoe UI', 22, 'bold'), 
                                           bg=COLORS['primary'], 
                                           fg='white',           
                                           padx=20, pady=10)     
        self.lbl_cliente_nombre.pack(side="left", expand=True, fill="x")

        # 3. TOTAL
        self.lbl_cliente_total = tk.Label(parent, text="", font=('Segoe UI', 24, 'bold'), fg=COLORS['danger'], bg=COLORS['light'])
        self.lbl_cliente_total.pack(side="top", pady=5)

        # 4. HEADER Y PANEL DE CARGA
        frame_title_add = tk.Frame(parent, bg=COLORS['light'])
        frame_title_add.pack(side="top", fill="x", padx=30, pady=(15, 0))
        tk.Label(frame_title_add, text="Agendar nueva deuda", font=FONTS['h2'], bg=COLORS['light'], fg=COLORS['text']).pack(side="left")

        frame_add = tk.Frame(parent, bg="white", padx=20, pady=20, relief="solid", bd=1)
        frame_add.pack(side="top", fill="x", padx=30, pady=(5, 10))

        frame_add.columnconfigure(1, weight=2) 
        frame_add.columnconfigure(3, weight=1)
        frame_add.columnconfigure(5, weight=1)
        frame_add.columnconfigure(6, weight=10) 

        # --- CAMBIO: CAJA DE TEXTO SIMPLE ---
        tk.Label(frame_add, text="Concepto / Repuesto:", bg="white", font=FONTS['body']).grid(row=0, column=0, sticky="w")
        
        self.entry_desc = tk.Entry(frame_add, width=25, font=FONTS['body'], bg="white", relief="solid", bd=1)
        self.entry_desc.grid(row=0, column=1, sticky="ew", padx=(5, 15), ipady=5)
        self.entry_desc.insert(0, "Factura") # Pre-llenar con "Factura"

        tk.Label(frame_add, text="Monto ($):", bg="white", font=FONTS['body']).grid(row=0, column=2, sticky="w")
        self.entry_monto = tk.Entry(frame_add, width=10, font=FONTS['body'], bg="white", relief="solid", bd=1)
        self.entry_monto.grid(row=0, column=3, sticky="ew", padx=(5, 15), ipady=5)

        # --- SECCION FECHA CON 3 BOXES ---
        frame_fecha = tk.Frame(frame_add, bg="white")
        frame_fecha.grid(row=0, column=4, columnspan=2, sticky="w")
        
        tk.Label(frame_fecha, text="Fecha:", bg="white", font=FONTS['body']).pack(side="left", padx=(0,5))
        
        # Box DIA
        self.entry_dia = tk.Entry(frame_fecha, width=3, font=FONTS['body'], justify="center", bg="white", relief="solid", bd=1)
        self.entry_dia.pack(side="left", ipady=5)
        tk.Label(frame_fecha, text="/", bg="white", font=FONTS['body_bold']).pack(side="left", padx=2)
        
        # Box MES
        self.entry_mes = tk.Entry(frame_fecha, width=3, font=FONTS['body'], justify="center", bg="white", relief="solid", bd=1)
        self.entry_mes.pack(side="left", ipady=5)
        tk.Label(frame_fecha, text="/", bg="white", font=FONTS['body_bold']).pack(side="left", padx=2)
        
        # Box AÑO
        self.entry_anio = tk.Entry(frame_fecha, width=5, font=FONTS['body'], justify="center", bg="white", relief="solid", bd=1)
        self.entry_anio.pack(side="left", ipady=5)

        # SE INICIAN VACÍAS POR DEFECTO

        btn_add_deuda = tk.Button(frame_add, text="AGREGAR", 
                                  bg=COLORS['warning'], fg="white", 
                                  font=FONTS['body_bold'], 
                                  cursor="hand2", relief="flat",
                                  width=15, height=1,
                                  command=self.guardar_nueva_deuda)
        btn_add_deuda.grid(row=0, column=7, padx=10, sticky="e")
        
        # 5. FILTROS Y TABLA
        frame_head = tk.Frame(parent, bg=COLORS['light'])
        frame_head.pack(side="top", fill="x", padx=30, pady=(20, 5))
        
        tk.Label(frame_head, text="Historial de Movimientos", bg=COLORS['light'], font=FONTS['h2'], fg=COLORS['text']).pack(side="left")
        
        self.combo_filtro = ttk.Combobox(frame_head, values=["Más Recientes", "Más Antiguas", "Por Estado"], state="readonly", width=20)
        self.combo_filtro.current(0)
        self.combo_filtro.pack(side="right")
        self.combo_filtro.bind("<<ComboboxSelected>>", self.aplicar_filtro)
        tk.Label(frame_head, text="Ordenar:", bg=COLORS['light'], font=FONTS['small']).pack(side="right", padx=5)

        frame_tabla_det = tk.Frame(parent, bg="white")
        frame_tabla_det.pack(side="top", fill="both", expand=True, padx=30, pady=5)

        scrollbar_d = ttk.Scrollbar(frame_tabla_det)
        scrollbar_d.pack(side="right", fill="y")

        cols_d = ("Desc", "Original", "Pagado", "Resta", "Fecha Ingreso", "Ultimo Pago", "Estado", "Metodo")
        self.tree_detalle = ttk.Treeview(frame_tabla_det, columns=cols_d, show="headings", yscrollcommand=scrollbar_d.set)
        scrollbar_d.config(command=self.tree_detalle.yview)

        headers = ["Concepto", "Original ($)", "Pagado ($)", "Debe ($)", "Fecha Creación", "Fecha Pago", "Estado", "Método"]
        widths = [200, 80, 80, 80, 100, 100, 80, 80]
        
        for i, col in enumerate(cols_d):
            self.tree_detalle.heading(col, text=headers[i])
            self.tree_detalle.column(col, width=widths[i], anchor="center")
        
        self.tree_detalle.column("Desc", anchor="w") 

        self.tree_detalle.tag_configure('PENDIENTE', background='#ffebee', foreground=COLORS['danger']) 
        self.tree_detalle.tag_configure('PARCIAL', background='#fff3e0', foreground=COLORS['text'])    
        self.tree_detalle.tag_configure('PAGADA', background='#e8f5e9', foreground=COLORS['success'])  
        
        self.tree_detalle.pack(side="left", fill="both", expand=True)

        # Eventos Tooltip
        self.tree_detalle.bind("<Motion>", self.verificar_tooltip)
        self.tree_detalle.bind("<Leave>", self.ocultar_tooltip)

    # --- LÓGICA DE TOOLTIPS (Concepto Y Método) ---
    def verificar_tooltip(self, event):
        try:
            region = self.tree_detalle.identify("region", event.x, event.y)
            if region == "cell":
                col_id = self.tree_detalle.identify_column(event.x)
                
                if col_id in ("#1", "#8"):
                    row_id = self.tree_detalle.identify_row(event.y)
                    if row_id:
                        item = self.tree_detalle.item(row_id)
                        
                        texto = ""
                        if col_id == "#1":
                            texto = item['values'][0] # Concepto
                        elif col_id == "#8":
                            texto = item['values'][7] # Método 

                        if (row_id != self.last_tooltip_row) or (col_id != self.last_tooltip_col):
                            self.mostrar_tooltip(texto, event.x_root, event.y_root)
                            self.last_tooltip_row = row_id
                            self.last_tooltip_col = col_id
                        return
        except: pass
        
        self.ocultar_tooltip()
        self.last_tooltip_row = None
        self.last_tooltip_col = None

    def mostrar_tooltip(self, text, x, y):
        self.ocultar_tooltip(None) 
        if not text or text == "-" or text == "": return
        
        self.tooltip_window = tk.Toplevel(self)
        self.tooltip_window.wm_overrideredirect(True) 
        self.tooltip_window.wm_geometry(f"+{x+15}+{y+10}") 
        
        label = tk.Label(self.tooltip_window, text=text, justify='left',
                         background=COLORS['tooltip_bg'], relief='solid', borderwidth=1,
                         font=FONTS['small'])
        label.pack(ipadx=5, ipady=2)

    def ocultar_tooltip(self, event=None):
        if self.tooltip_window:
            self.tooltip_window.destroy()
            self.tooltip_window = None

    # --- LÓGICA GENERAL ---
    def modal_nuevo_cliente(self):
        top = tk.Toplevel(self)
        top.title("Nuevo Cliente")
        top.geometry("400x320")
        top.configure(bg="white")
        
        tk.Label(top, text="Registrar Nuevo Cliente", font=FONTS['h2'], bg="white", fg=COLORS['primary']).pack(pady=15)

        tk.Label(top, text="DNI / Código Único:", bg="white", font=FONTS['body_bold']).pack(anchor="w", padx=30)
        e_dni = tk.Entry(top, font=FONTS['body'], bg="white", relief="solid", bd=1)
        e_dni.pack(fill="x", padx=30, pady=(0, 10), ipady=3)
        e_dni.focus()

        tk.Label(top, text="Nombre Completo:", bg="white", font=FONTS['body_bold']).pack(anchor="w", padx=30)
        e_nombre = tk.Entry(top, font=FONTS['body'], bg="white", relief="solid", bd=1)
        e_nombre.pack(fill="x", padx=30, pady=(0, 10), ipady=3)
        
        tk.Label(top, text="Localidad:", bg="white", font=FONTS['body_bold']).pack(anchor="w", padx=30)
        valores_loc = ["Bombal", "Bigand", "Firmat", "Alcorta", "Rosario", "Venado Tuerto", "Otro"]
        e_localidad = ttk.Combobox(top, values=valores_loc, state="readonly", font=FONTS['body'])
        e_localidad.pack(fill="x", padx=30, pady=(0, 20), ipady=3)
        e_localidad.current(0)

        def guardar():
            dni = e_dni.get().strip()
            nombre = e_nombre.get().strip()

            if not dni or not nombre:
                messagebox.showwarning("Faltan datos", "El DNI/Código y el Nombre son obligatorios")
                return

            if self.db.existe_cliente(dni):
                messagebox.showerror("Error", f"Ya existe un cliente con el ID/DNI '{dni}'.")
                return

            self.db.agregar_cliente(dni, nombre, e_localidad.get())
            self.cargar_lista_clientes()
            top.destroy()
        
        tk.Button(top, text="GUARDAR CLIENTE", bg=COLORS['primary'], fg="white", 
                  font=FONTS['body_bold'], relief="flat", cursor="hand2",
                  command=guardar).pack(pady=10, ipadx=20, ipady=5)
        top.bind('<Return>', lambda event: guardar())

    def cargar_lista_clientes(self, filtro=""):
        for row in self.tree_clientes.get_children():
            self.tree_clientes.delete(row)
        
        clientes = self.db.obtener_clientes_con_saldo(filtro)
        for cli in clientes:
            self.tree_clientes.insert("", "end", values=(cli[1], cli[2], cli[3], cli[4]), tags=(cli[0],))

    def filtrar_clientes(self, event):
        self.cargar_lista_clientes(self.entry_buscar.get())

    def seleccionar_cliente(self, event):
        seleccion = self.tree_clientes.selection()
        if not seleccion: return
        
        tags = self.tree_clientes.item(seleccion, "tags")
        if tags:
            self.cliente_seleccionado_id = tags[0]
            nombre_cliente = self.tree_clientes.item(seleccion)['values'][1]
            self.lbl_cliente_nombre.config(text=f"👤 {nombre_cliente}")
            self.actualizar_info_completa()

    def aplicar_filtro(self, event):
        if self.cliente_seleccionado_id:
            self.actualizar_info_completa()

    def actualizar_info_completa(self):
        for row in self.tree_detalle.get_children():
            self.tree_detalle.delete(row)
            
        historial = self.db.obtener_historial_cliente(self.cliente_seleccionado_id)
        
        filtro_actual = self.combo_filtro.get()
        if filtro_actual == "Más Recientes":
            historial.sort(key=lambda x: x[5] if x[5] else "", reverse=True)
        elif filtro_actual == "Más Antiguas":
            historial.sort(key=lambda x: x[5] if x[5] else "", reverse=False)
        elif filtro_actual == "Por Estado":
            peso_estado = {'PENDIENTE': 0, 'PARCIAL': 1, 'PAGADA': 2}
            historial.sort(key=lambda x: peso_estado.get(x[7], 99))

        for h in historial:
            f_creacion = h[5] if h[5] else ""
            f_pago = h[6] if h[6] else "-"
            metodo = h[8] if h[8] else "-"
            
            valores_fila = (h[1], f"${h[2]:,.2f}", f"${h[3]:,.2f}", f"${h[4]:,.2f}", f_creacion, f_pago, h[7], metodo)
            self.tree_detalle.insert("", "end", values=valores_fila, tags=(h[7], h[0])) 

        total = self.db.obtener_total_individual(self.cliente_seleccionado_id)
        self.lbl_cliente_total.config(text=f"TOTAL ADEUDADO: ${total:,.2f}")

    def guardar_nueva_deuda(self):
        if not self.cliente_seleccionado_id:
            messagebox.showwarning("Error", "Selecciona un cliente primero")
            return
        
        monto_txt = self.entry_monto.get()
        desc = self.entry_desc.get()
        
        # --- NUEVA LOGICA DE FECHA DESDE 3 BOXES ---
        dia = self.entry_dia.get().strip()
        mes = self.entry_mes.get().strip()
        anio = self.entry_anio.get().strip()

        if not monto_txt: return

        fecha_final = None
        
        if dia and mes and anio:
            try:
                fecha_str = f"{dia}/{mes}/{anio}"
                fecha_obj = datetime.strptime(fecha_str, "%d/%m/%Y")
                if fecha_obj.date() > datetime.now().date():
                    messagebox.showerror("Error de Fecha", "No puedes registrar deudas con fecha futura.")
                    return 
                fecha_final = fecha_obj.strftime("%Y-%m-%d 00:00")
            except ValueError:
                messagebox.showerror("Error de Fecha", "Fecha inválida (ej: 30/02 no existe).")
                return
        else:
            fecha_final = datetime.now().strftime("%Y-%m-%d %H:%M")

        try:
            monto = float(monto_txt)
            self.db.agregar_deuda(self.cliente_seleccionado_id, monto, desc, fecha_final)
            
            self.entry_monto.delete(0, tk.END)
            self.entry_desc.delete(0, tk.END)
            self.entry_desc.insert(0, "Factura") # RESETEA A "Factura"
            
            # Limpiar campos de fecha
            self.entry_dia.delete(0, tk.END)
            self.entry_mes.delete(0, tk.END)
            self.entry_anio.delete(0, tk.END)
            
            self.actualizar_info_completa()
            self.cargar_lista_clientes(self.entry_buscar.get())
        except ValueError:
            messagebox.showerror("Error", "El monto debe ser un número")

    def abrir_ventana_pago(self):
        seleccion = self.tree_detalle.selection()
        if not seleccion:
            messagebox.showinfo("Atención", "Selecciona qué deuda quiere pagar el cliente (clic en la lista).")
            return
            
        tags = self.tree_detalle.item(seleccion, "tags")
        deuda_id = tags[1] 
        
        item = self.tree_detalle.item(seleccion)
        desc = item['values'][0]
        falta_pagar_str = str(item['values'][3]).replace('$', '').replace(',', '')
        
        fecha_creacion_str = item['values'][4]
        dias_atraso = 0
        porcentaje_sugerido = 0
        txt_sugerencia = "Al día"
        
        if fecha_creacion_str:
            try:
                f_creacion_obj = datetime.strptime(fecha_creacion_str[:10], "%Y-%m-%d")
                f_hoy = datetime.now()
                dias_atraso = (f_hoy - f_creacion_obj).days
                bloques_30_dias = dias_atraso // 30
                porcentaje_sugerido = bloques_30_dias * 10
                
                if porcentaje_sugerido > 0:
                    txt_sugerencia = f"⚠ Atraso: {dias_atraso} días (+{porcentaje_sugerido}% sug.)"
                else:
                    txt_sugerencia = f"Al día ({dias_atraso} días)"
            except: pass 

        try:
            val_falta = float(falta_pagar_str)
        except:
            val_falta = 0
            
        if val_falta <= 0:
            messagebox.showinfo("Bien", "Esta deuda ya está pagada.")
            return

        # POPUP PAGO AGREGADO (Más alto para que entre el botón)
        popup = tk.Toplevel(self)
        popup.title("Ingresar Pago")
        popup.geometry("450x650") # Agrandado de 600 a 650
        popup.configure(bg="white")
        
        tk.Label(popup, text="Registrar Pago", font=FONTS['h2'], bg="white", fg=COLORS['secondary']).pack(pady=(20, 5))
        tk.Label(popup, text=f"Item: {desc}", font=FONTS['body'], bg="white", fg="gray").pack()

        f_saldo = tk.Frame(popup, bg=COLORS['light'], padx=10, pady=10)
        f_saldo.pack(fill="x", padx=30, pady=15)
        tk.Label(f_saldo, text="Saldo Pendiente:", bg=COLORS['light'], font=FONTS['body']).pack(side="left")
        tk.Label(f_saldo, text=f"${val_falta:,.2f}", bg=COLORS['light'], font=FONTS['h2'], fg=COLORS['danger']).pack(side="right")
        
        tk.Label(popup, text=txt_sugerencia, bg="white", fg=COLORS['warning'], font=FONTS['body_bold']).pack()

        f_int = tk.LabelFrame(popup, text="Recargo / Interés %", bg="white", font=FONTS['small'])
        f_int.pack(fill="x", padx=30, pady=10)
        
        entry_pct = tk.Entry(f_int, justify="center", width=5, bg="white", relief="solid", bd=1)
        entry_pct.pack(side="left", padx=10, pady=10, ipady=3)
        entry_pct.insert(0, "0")

        lbl_total_cobrar = tk.Label(popup, text=f"Total: ${val_falta:,.2f}", font=FONTS['h2'], bg="white", fg=COLORS['primary'])
        lbl_total_cobrar.pack(pady=5)

        def calc_total(e=None):
            try:
                pct = float(entry_pct.get())
                total = val_falta * (1 + pct/100)
                lbl_total_cobrar.config(text=f"Total: ${total:,.2f}")
                return total
            except: return val_falta

        entry_pct.bind("<KeyRelease>", calc_total)
        
        f_btns = tk.Frame(f_int, bg="white")
        f_btns.pack(side="left")
        tk.Button(f_btns, text="+10%", command=lambda: [entry_pct.delete(0,tk.END), entry_pct.insert(0,"10"), calc_total()], bg=COLORS['light'], relief="flat").pack(side="left", padx=2)
        if porcentaje_sugerido > 0:
             tk.Button(f_btns, text=f"Sugerido", command=lambda: [entry_pct.delete(0,tk.END), entry_pct.insert(0,str(porcentaje_sugerido)), calc_total()], bg=COLORS['warning'], fg="white", relief="flat").pack(side="left", padx=2)

        tk.Label(popup, text="Monto a Pagar ($):", bg="white", font=FONTS['body_bold']).pack(anchor="w", padx=30)
        e_pago = tk.Entry(popup, font=('Segoe UI', 14), justify="center", bg="white", relief="solid", bd=1)
        e_pago.pack(fill="x", padx=30, pady=5, ipady=5)
        e_pago.focus()

        tk.Button(popup, text="▼ Pagar Totalidad", command=lambda: [e_pago.delete(0,tk.END), e_pago.insert(0, f"{calc_total():.2f}")], 
                  font=FONTS['small'], bg="white", fg=COLORS['primary'], relief="flat", cursor="hand2").pack()

        tk.Label(popup, text="Medio de Pago:", bg="white", font=FONTS['body_bold']).pack(anchor="w", padx=30, pady=(10,0))
        c_metodo = ttk.Combobox(popup, values=["Efectivo", "Transferencia", "Débito", "Crédito", "Cheque"], state="readonly")
        c_metodo.current(0)
        c_metodo.pack(fill="x", padx=30, pady=5)

        # CAMPO OBSERVACIONES
        tk.Label(popup, text="Observaciones (Nro Cheque / Nota):", bg="white", font=FONTS['body_bold']).pack(anchor="w", padx=30, pady=(10,0))
        e_obs = tk.Entry(popup, font=FONTS['body'], bg="white", relief="solid", bd=1)
        e_obs.pack(fill="x", padx=30, pady=5, ipady=3)

        def confirmar():
            try:
                monto = float(e_pago.get())
                if monto <= 0: return
                
                # Construir string del método
                metodo_final = c_metodo.get()
                obs = e_obs.get().strip()
                if obs:
                    metodo_final += f" ({obs})"

                self.db.registrar_pago_parcial(deuda_id, monto, metodo_final)
                self.actualizar_info_completa()
                self.cargar_lista_clientes(self.entry_buscar.get())
                popup.destroy()
            except: messagebox.showerror("Error", "Monto inválido")

        # BOTÓN PAGO ARREGLADO (Más espacio y estilo limpio)
        frame_btn_pago = tk.Frame(popup, bg="white")
        frame_btn_pago.pack(fill="x", pady=20, side="bottom") # Side bottom para que quede abajo
        
        tk.Button(frame_btn_pago, text="CONFIRMAR PAGO", bg=COLORS['success'], fg="white", 
                  font=FONTS['body_bold'], relief="raised", bd=2,
                  command=confirmar, cursor="hand2").pack(fill="x", padx=30, pady=10, ipady=10)
        
        popup.bind('<Return>', lambda e: confirmar())

    def eliminar_error(self):
        seleccion = self.tree_detalle.selection()
        if not seleccion: return
        if messagebox.askyesno("Confirmar", "¿Eliminar este registro permanentemente?\nEsto afectará el saldo total."):
            tags = self.tree_detalle.item(seleccion, "tags")
            self.db.borrar_deuda_permanentemente(tags[1])
            self.actualizar_info_completa()
            self.cargar_lista_clientes(self.entry_buscar.get())

if __name__ == "__main__":
    app = Aplicacion()
    app.mainloop()