import tkinter as tk
from tkinter import ttk, messagebox, Menu
import sqlite3
from datetime import datetime
import os 
import sys 

# ==========================================
# CONFIGURACIÓN DE COLORES Y ESTILOS
# ==========================================
COLORS = {
    'primary': '#2980b9',       # Azul fuerte
    'secondary': '#2c3e50',     # Gris oscuro (Sidebar)
    'success': '#27ae60',       # Verde (Pagos/Guardar/Saldo a favor)
    'warning': '#f39c12',       # Naranja (Botón Usar Saldo)
    'danger': '#c0392b',        # Rojo (Eliminar/Deuda)
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

# ==========================================
# PARTE 1: LA BASE DE DATOS (COMPLETA)
# ==========================================
class BaseDeDatos:
    def __init__(self, db_name="taller_repuestos_final.db"):
        self.conn = sqlite3.connect(db_name)
        self.cursor = self.conn.cursor()
        self.crear_tablas()

    def crear_tablas(self):
        # Tabla Clientes
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS clientes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                dni TEXT,
                nombre TEXT NOT NULL,
                telefono TEXT,
                localidad TEXT
            )
        """)
        # Tabla Deudas (Cabecera)
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
        # Tabla Detalle de Pagos (Historial)
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS pagos_detalle (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                deuda_id INTEGER,
                monto REAL,
                fecha TEXT,
                metodo TEXT,
                FOREIGN KEY(deuda_id) REFERENCES deudas(id)
            )
        """)
        self.conn.commit()

    # --- MÉTODOS DE CLIENTES ---
    def existe_cliente(self, dni):
        self.cursor.execute("SELECT id FROM clientes WHERE dni = ?", (dni,))
        row = self.cursor.fetchone()
        return row is not None

    def agregar_cliente(self, dni, nombre, localidad):
        self.cursor.execute("INSERT INTO clientes (dni, nombre, telefono, localidad) VALUES (?, ?, ?, ?)", 
                            (dni, nombre, "", localidad))
        self.conn.commit()

    def obtener_clientes_con_saldo(self, filtro=""):
        query = """
            SELECT c.id, c.dni, c.nombre, c.localidad, 
                   COALESCE(SUM(d.monto_total - d.monto_pagado), 0) as saldo_restante
            FROM clientes c
            LEFT JOIN deudas d ON c.id = d.cliente_id
            WHERE c.nombre LIKE ? OR c.dni LIKE ? OR c.localidad LIKE ?
            GROUP BY c.id
            ORDER BY c.nombre ASC
        """
        filtro_sql = '%' + filtro + '%'
        self.cursor.execute(query, (filtro_sql, filtro_sql, filtro_sql))
        return self.cursor.fetchall()

    # --- MÉTODOS DE DEUDAS ---
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

    def obtener_historial_cliente(self, cliente_id):
        # Indices: 0:id, 1:desc, 2:total, 3:pagado, 4:resta, 5:fecha_creacion, 6:fecha_pago, 7:estado, 8:metodo
        query = """
            SELECT id, descripcion, monto_total, monto_pagado, 
                   (monto_total - monto_pagado) as resta, 
                   fecha_creacion, fecha_pago, estado, metodo_pago
            FROM deudas 
            WHERE cliente_id = ?
        """
        self.cursor.execute(query, (cliente_id,))
        return self.cursor.fetchall()

    def obtener_total_individual(self, cliente_id):
        query = """
            SELECT COALESCE(SUM(monto_total - monto_pagado), 0) 
            FROM deudas WHERE cliente_id = ?
        """
        self.cursor.execute(query, (cliente_id,))
        resultado = self.cursor.fetchone()
        return resultado[0] if resultado else 0

    def borrar_deuda_permanentemente(self, deuda_id):
        # Primero borramos el historial de pagos de esa deuda
        self.cursor.execute("DELETE FROM pagos_detalle WHERE deuda_id = ?", (deuda_id,))
        # Luego borramos la deuda
        self.cursor.execute("DELETE FROM deudas WHERE id = ?", (deuda_id,))
        self.conn.commit()

    def agregar_interes_deuda(self, deuda_id, interes):
        """
        Suma el monto de interés al total de la deuda para que no quede como saldo a favor.
        """
        self.cursor.execute("UPDATE deudas SET monto_total = monto_total + ? WHERE id = ?", (interes, deuda_id))
        self.conn.commit()

    # --- MÉTODOS DE PAGOS (LÓGICA MANUAL Y DETALLADA) ---
    def registrar_pago(self, deuda_id, nuevo_pago, metodo):
        """
        Registra un pago en una deuda específica y guarda el movimiento en el historial.
        """
        # 1. Obtener datos actuales de la deuda
        self.cursor.execute("SELECT monto_total, monto_pagado FROM deudas WHERE id = ?", (deuda_id,))
        res = self.cursor.fetchone()
        if not res: return
        
        total, pagado_actual = res
        pagado_nuevo = pagado_actual + nuevo_pago
        
        # 2. Determinar estado
        estado = "PENDIENTE"
        # Usamos round para evitar problemas de decimales
        if round(pagado_nuevo, 2) >= round(total, 2):
            estado = "PAGADA"
        elif pagado_nuevo > 0:
            estado = "PARCIAL"
            
        ahora = datetime.now().strftime("%Y-%m-%d %H:%M")
        
        # 3. Actualizar la deuda general
        self.cursor.execute("""
            UPDATE deudas SET monto_pagado = ?, metodo_pago = ?, fecha_pago = ?, estado = ?
            WHERE id = ?
        """, (pagado_nuevo, metodo, ahora, estado, deuda_id))

        # 4. GUARDAR EN EL HISTORIAL DETALLADO
        self.cursor.execute("""
            INSERT INTO pagos_detalle (deuda_id, monto, fecha, metodo)
            VALUES (?, ?, ?, ?)
        """, (deuda_id, nuevo_pago, ahora, metodo))

        self.conn.commit()

    def obtener_detalles_pagos(self, deuda_id):
        """Recupera la lista de pagos individuales para el click derecho"""
        self.cursor.execute("""
            SELECT fecha, monto, metodo 
            FROM pagos_detalle 
            WHERE deuda_id = ? 
            ORDER BY id DESC
        """, (deuda_id,))
        return self.cursor.fetchall()

    # --- LÓGICA DE SALDOS A FAVOR (MANUAL) ---
    def obtener_saldo_a_favor_disponible(self, cliente_id):
        """
        Suma todo el dinero que sobra de las boletas pagadas en exceso.
        Retorna un número positivo (la cantidad disponible para usar).
        """
        self.cursor.execute("""
            SELECT SUM(monto_pagado - monto_total) 
            FROM deudas 
            WHERE cliente_id = ? AND monto_pagado > monto_total
        """, (cliente_id,))
        res = self.cursor.fetchone()
        return res[0] if res and res[0] else 0.0

    def usar_saldo_manual(self, cliente_id, deuda_destino_id):
        """
        Lógica compleja: Saca dinero de las boletas donde sobra y lo pone en la deuda_destino_id.
        Registra los movimientos en el historial como 'SALDO A FAVOR'.
        """
        # 1. Calcular cuánto saldo a favor hay disponible
        saldo_disponible = self.obtener_saldo_a_favor_disponible(cliente_id)
        if saldo_disponible <= 0:
            return False, "No hay saldo a favor disponible."

        # 2. Verificar cuánto falta pagar en la deuda destino
        self.cursor.execute("SELECT monto_total, monto_pagado FROM deudas WHERE id = ?", (deuda_destino_id,))
        res = self.cursor.fetchone()
        if not res: return False, "Deuda no encontrada."
        
        total_destino, pagado_destino = res
        falta_pagar = total_destino - pagado_destino
        
        if falta_pagar <= 0:
            return False, "La deuda destino ya está pagada."

        # 3. Determinar cuánto vamos a usar
        monto_a_usar = min(saldo_disponible, falta_pagar)
        
        # 4. Registrar el pago en la deuda destino
        self.registrar_pago(deuda_destino_id, monto_a_usar, "SALDO A FAVOR")

        # 5. Descontar ese dinero de las deudas que tenían saldo a favor
        #    Reducimos su 'monto_pagado' hasta cubrir 'monto_a_usar'.
        resto = monto_a_usar
        
        self.cursor.execute("SELECT id, monto_total, monto_pagado FROM deudas WHERE cliente_id = ? AND monto_pagado > monto_total", (cliente_id,))
        superavitarias = self.cursor.fetchall()
        
        for d_id, d_total, d_pagado in superavitarias:
            if resto <= 0: break
            
            excedente = d_pagado - d_total
            descuento = min(resto, excedente)
            
            # Restamos al pagado de esa deuda
            nuevo_pagado = d_pagado - descuento
            self.cursor.execute("UPDATE deudas SET monto_pagado = ? WHERE id = ?", (nuevo_pagado, d_id))
            
            resto -= descuento

        self.conn.commit()
        return True, f"Se utilizaron ${monto_a_usar:,.2f} de saldo a favor."

    # ==========================================
    # NUEVOS METODOS PARA ESTADISTICAS
    # ==========================================
    
    def obtener_top_deudores(self, limit=5):
        """
        Retorna la lista de los clientes con mayor deuda acumulada.
        Formato: [(Nombre, DeudaTotal), ...]
        """
        sql = """
            SELECT c.nombre, SUM(d.monto_total - d.monto_pagado) as deuda_acumulada
            FROM deudas d
            JOIN clientes c ON d.cliente_id = c.id
            GROUP BY d.cliente_id
            HAVING deuda_acumulada > 1
            ORDER BY deuda_acumulada DESC
            LIMIT ?
        """
        self.cursor.execute(sql, (limit,))
        return self.cursor.fetchall()

    def obtener_deuda_total(self):
        """
        Retorna la suma total de todas las deudas pendientes en el sistema.
        """
        sql = "SELECT SUM(monto_total - monto_pagado) FROM deudas WHERE (monto_total - monto_pagado) > 0"
        self.cursor.execute(sql)
        res = self.cursor.fetchone()
        return res[0] if res and res[0] else 0.0

    def obtener_cobro_mes(self):
        """
        Retorna la suma de pagos realizados en el mes actual.
        Basado en la fecha del pago (tabla pagos_detalle).
        """
        mes_actual = datetime.now().strftime("%Y-%m")
        patron = f"{mes_actual}%"
        
        sql = "SELECT SUM(monto) FROM pagos_detalle WHERE fecha LIKE ?"
        self.cursor.execute(sql, (patron,))
        res = self.cursor.fetchone()
        return res[0] if res and res[0] else 0.0

    def obtener_desglose_pagos_mes(self):
        """
        Retorna una lista de tuplas (metodo, monto) con lo recaudado este mes,
        agrupado por método de pago (ignorando comentarios entre paréntesis).
        """
        mes_actual = datetime.now().strftime("%Y-%m")
        patron = f"{mes_actual}%"
        
        # Obtenemos TODOS los pagos del mes con su método y monto
        sql = "SELECT metodo, monto FROM pagos_detalle WHERE fecha LIKE ?"
        self.cursor.execute(sql, (patron,))
        filas = self.cursor.fetchall()
        
        # Agrupamos manual en Python para limpiar "Metodo (Comentario)" -> "Metodo"
        agrupado = {}
        for metodo_raw, monto in filas:
            # Si dice "Debito (jee)" -> tomamos solo "Debito"
            metodo_limpio = metodo_raw.split(" (")[0].strip()
            
            if metodo_limpio not in agrupado:
                agrupado[metodo_limpio] = 0.0
            agrupado[metodo_limpio] += monto
            
        # Convertimos a lista y ordenamos por monto descendente
        resultado = list(agrupado.items())
        resultado.sort(key=lambda x: x[1], reverse=True)
        
        return resultado

    def obtener_recaudacion_historica(self):
        """
        Retorna la recaudación agrupada por mes (Año-Mes).
        Devuelve lista de tuplas: (mes_str, total)
        Ordenado del más reciente al más antiguo.
        """
        sql = """
            SELECT substr(fecha, 1, 7) as mes, SUM(monto)
            FROM pagos_detalle
            GROUP BY substr(fecha, 1, 7)
            ORDER BY mes DESC
        """
        self.cursor.execute(sql)
        return self.cursor.fetchall()

# ==========================================
# PARTE 2: INTERFAZ GRÁFICA MEJORADA
# ==========================================
class Aplicacion(tk.Tk):
    def __init__(self):
        super().__init__()
        self.db = BaseDeDatos()
        self.title("Gestión de Repuestos - Sistema Profesional")
        self.geometry("1350x780")
        self.configure(bg=COLORS['light'])
        
        # Lógica de rutas para logo en .exe
        if getattr(sys, 'frozen', False):
            self.carpeta_base = os.path.dirname(sys.executable)
        else:
            self.carpeta_base = os.path.dirname(os.path.abspath(__file__))

        ruta_icono = os.path.join(self.carpeta_base, "Logo_Sbrolla.ico")
        if os.path.exists(ruta_icono):
            try:
                self.iconbitmap(ruta_icono)
            except: pass
        
        self.cliente_seleccionado_id = None
        
        # Variables para Tooltip
        self.tooltip_window = None
        self.last_tooltip_row = None
        self.last_tooltip_col = None 

        # --- ESTILOS TTK ---
        self.style = ttk.Style()
        self.style.theme_use("clam")
        
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
        self.tree_clientes.heading("Saldo", text="Total ($)")
        
        self.tree_clientes.column("DNI", width=70)
        self.tree_clientes.column("Nombre", width=130)
        self.tree_clientes.column("Loc", width=70)
        self.tree_clientes.column("Saldo", width=80)
        
        self.tree_clientes.pack(side="left", fill="both", expand=True)
        self.tree_clientes.bind("<<TreeviewSelect>>", self.seleccionar_cliente)

    def construir_panel_detalle(self, parent):
        frame_acciones = tk.Frame(parent, bg=COLORS['light'])
        frame_acciones.pack(side="bottom", fill="x", padx=30, pady=10) 

        btn_eliminar = tk.Button(frame_acciones, text="🗑️ Eliminar Registro", 
                                 bg="#95a5a6", fg="white", 
                                 font=FONTS['body_bold'], relief="flat", cursor="hand2",
                                 padx=15, pady=8,
                                 command=self.eliminar_error)
        btn_eliminar.pack(side="left") 

        # --- BOTÓN NUEVO: USAR SALDO ---
        self.btn_usar_saldo = tk.Button(frame_acciones, text="🔄 USAR SALDO A FAVOR", 
                                        bg=COLORS['warning'], fg="white", 
                                        font=FONTS['body_bold'], relief="flat", cursor="hand2",
                                        padx=15, pady=8,
                                        command=self.click_usar_saldo)
        self.btn_usar_saldo.pack(side="left", padx=20)
        self.btn_usar_saldo.config(state="disabled") # Desactivado por defecto

        btn_pagar = tk.Button(frame_acciones, text="💵  INGRESAR PAGO", 
                              bg=COLORS['success'], fg="white", 
                              font=('Segoe UI', 12, 'bold'), 
                              relief="flat", cursor="hand2",
                              padx=30, pady=10, 
                              command=self.abrir_ventana_pago)
        btn_pagar.pack(side="right")

        frame_acciones.pack(side="bottom", fill="x", padx=30, pady=20) 
        
        # --- BARRA SUPERIOR (BOTÓN ESTADÍSTICAS) ---
        frame_top_bar = tk.Frame(parent, bg=COLORS['light'])
        frame_top_bar.pack(side="top", fill="x", padx=30, pady=(5, 0))

        btn_stats = tk.Button(frame_top_bar, text="📊 Ver Estadísticas", 
                              bg=COLORS['primary'], fg="white", 
                              font=('Segoe UI', 10, 'bold'), relief="flat", cursor="hand2",
                              padx=15, pady=5,
                              command=self.mostrar_estadisticas)
        btn_stats.pack(side="right")

        frame_encabezado = tk.Frame(parent, bg=COLORS['light'])
        frame_encabezado.pack(side="top", pady=(5, 0), fill="x", padx=30) 
        
        



        ruta_completa_imagen = os.path.join(self.carpeta_base, "Logo_Sbrolla.png")
        if os.path.exists(ruta_completa_imagen):
            try:
                self.img_logo = tk.PhotoImage(file=ruta_completa_imagen)
                self.img_logo = self.img_logo.subsample(4, 4) 
                lbl_img = tk.Label(frame_encabezado, image=self.img_logo, bg=COLORS['light'])
                lbl_img.pack(side="left", padx=(0, 15)) 
            except Exception as e:
                pass

        self.lbl_cliente_nombre = tk.Label(frame_encabezado, 
                                           text="Seleccione un cliente...", 
                                           font=('Segoe UI', 22, 'bold'), 
                                           bg=COLORS['primary'], 
                                           fg='white',            
                                           padx=20, pady=10)      
        self.lbl_cliente_nombre.pack(side="left", expand=True, fill="x")

        # --- ETIQUETAS DE TOTALES (Debajo del nombre, como antes) ---
        frame_totales = tk.Frame(parent, bg=COLORS['light'])
        frame_totales.pack(side="top", pady=5)
        
        self.lbl_cliente_total = tk.Label(frame_totales, text="", font=('Segoe UI', 24, 'bold'), fg=COLORS['danger'], bg=COLORS['light'])
        self.lbl_cliente_total.pack(anchor="center")
        
        self.lbl_saldo_disponible = tk.Label(frame_totales, text="", font=('Segoe UI', 14, 'bold'), fg=COLORS['success'], bg=COLORS['light'])
        self.lbl_saldo_disponible.pack(anchor="center")



        # --- FORMULARIO NUEVA DEUDA ---
        frame_title_add = tk.Frame(parent, bg=COLORS['light'])
        frame_title_add.pack(side="top", fill="x", padx=30, pady=(10, 0))
        tk.Label(frame_title_add, text="Agendar nueva deuda", font=FONTS['h2'], bg=COLORS['light'], fg=COLORS['text']).pack(side="left")

        frame_add = tk.Frame(parent, bg="white", padx=20, pady=15, relief="solid", bd=1)
        frame_add.pack(side="top", fill="x", padx=30, pady=5)

        frame_add.columnconfigure(1, weight=2) 
        frame_add.columnconfigure(3, weight=1)
        frame_add.columnconfigure(5, weight=1)
        frame_add.columnconfigure(6, weight=10) 

        tk.Label(frame_add, text="Concepto / Repuesto:", bg="white", font=FONTS['body']).grid(row=0, column=0, sticky="w")
        
        self.entry_desc = tk.Entry(frame_add, width=25, font=FONTS['body'], bg="white", relief="solid", bd=1)
        self.entry_desc.grid(row=0, column=1, sticky="ew", padx=(5, 15), ipady=5)
        self.entry_desc.insert(0, "Factura")

        tk.Label(frame_add, text="Monto ($):", bg="white", font=FONTS['body']).grid(row=0, column=2, sticky="w")
        self.entry_monto = tk.Entry(frame_add, width=10, font=FONTS['body'], bg="white", relief="solid", bd=1)
        self.entry_monto.grid(row=0, column=3, sticky="ew", padx=(5, 15), ipady=5)

        frame_fecha = tk.Frame(frame_add, bg="white")
        frame_fecha.grid(row=0, column=4, columnspan=2, sticky="w")
        
        tk.Label(frame_fecha, text="Fecha:", bg="white", font=FONTS['body']).pack(side="left", padx=(0,5))
        
        self.entry_dia = tk.Entry(frame_fecha, width=3, font=FONTS['body'], justify="center", bg="white", relief="solid", bd=1)
        self.entry_dia.pack(side="left", ipady=5)
        # Auto-focus al mes al escribir 2 digitos
        self.entry_dia.bind("<KeyRelease>", lambda e: self.entry_mes.focus() if len(self.entry_dia.get()) >= 2 else None)

        tk.Label(frame_fecha, text="/", bg="white", font=FONTS['body_bold']).pack(side="left", padx=2)
        
        self.entry_mes = tk.Entry(frame_fecha, width=3, font=FONTS['body'], justify="center", bg="white", relief="solid", bd=1)
        self.entry_mes.pack(side="left", ipady=5)
        # Auto-focus al anio al escribir 2 digitos
        self.entry_mes.bind("<KeyRelease>", lambda e: self.entry_anio.focus() if len(self.entry_mes.get()) >= 2 else None)

        tk.Label(frame_fecha, text="/", bg="white", font=FONTS['body_bold']).pack(side="left", padx=2)
        
        self.entry_anio = tk.Entry(frame_fecha, width=5, font=FONTS['body'], justify="center", bg="white", relief="solid", bd=1)
        self.entry_anio.pack(side="left", ipady=5)

        btn_add_deuda = tk.Button(frame_add, text="AGREGAR", 
                                  bg=COLORS['warning'], fg="white", 
                                  font=FONTS['body_bold'], 
                                  cursor="hand2", relief="flat",
                                  width=15, height=1,
                                  command=self.guardar_nueva_deuda)
        btn_add_deuda.grid(row=0, column=7, padx=10, sticky="e")
        
        # --- TABLA HISTORIAL ---
        frame_head = tk.Frame(parent, bg=COLORS['light'])
        frame_head.pack(side="top", fill="x", padx=30, pady=(10, 5))
        
        tk.Label(frame_head, text="Historial de Movimientos", bg=COLORS['light'], font=FONTS['h2'], fg=COLORS['text']).pack(side="left")
        
        self.combo_filtro = ttk.Combobox(frame_head, values=["Más Recientes", "Más Antiguas", "Por Estado"], state="readonly", width=20)
        self.combo_filtro.current(2)
        self.combo_filtro.pack(side="right")
        self.combo_filtro.bind("<<ComboboxSelected>>", self.aplicar_filtro)
        tk.Label(frame_head, text="Ordenar:", bg=COLORS['light'], font=FONTS['small']).pack(side="right", padx=5)

        frame_tabla_det = tk.Frame(parent, bg="white")
        frame_tabla_det.pack(side="top", fill="both", expand=True, padx=30, pady=5)

        scrollbar_d = ttk.Scrollbar(frame_tabla_det)
        scrollbar_d.pack(side="right", fill="y")

        cols_d = ("Desc", "Original", "Pagado", "Resta", "Fecha Ingreso", "Ultimo Pago", "Estado", "Metodo")
        self.tree_detalle = ttk.Treeview(frame_tabla_det, columns=cols_d, show="headings", height=45, yscrollcommand=scrollbar_d.set)
        scrollbar_d.config(command=self.tree_detalle.yview)

        headers = ["Concepto", "Original ($)", "Pagado ($)", "Debe ($)", "Fecha Creación", "Fecha Pago", "Estado", "Método"]
        widths = [200, 80, 80, 80, 100, 100, 80, 100] # Ancho ajustado
        
        for i, col in enumerate(cols_d):
            self.tree_detalle.heading(col, text=headers[i])
            self.tree_detalle.column(col, width=widths[i], anchor="center")
        
        self.tree_detalle.column("Desc", anchor="w") 

        self.tree_detalle.tag_configure('PENDIENTE', background='#ffebee', foreground=COLORS['danger']) 
        self.tree_detalle.tag_configure('PARCIAL', background='#fff3e0', foreground=COLORS['text'])    
        self.tree_detalle.tag_configure('PAGADA', background='#e8f5e9', foreground=COLORS['success'])
        
        self.tree_detalle.pack(side="left", fill="both", expand=True)

        self.tree_detalle.bind("<Motion>", self.verificar_tooltip)
        self.tree_detalle.bind("<Leave>", self.ocultar_tooltip)
        
        # --- CLICK DERECHO PARA MENU CONTEXTUAL ---
        self.tree_detalle.bind("<Button-3>", self.mostrar_menu_contextual)
        self.menu_contextual = Menu(self, tearoff=0)
        self.menu_contextual.add_command(label="Ver Historial de Pagos", command=self.ver_historial_pagos)

    def mostrar_menu_contextual(self, event):
        item = self.tree_detalle.identify_row(event.y)
        if item:
            self.tree_detalle.selection_set(item)
            self.menu_contextual.post(event.x_root, event.y_root)

    def ver_historial_pagos(self):
        seleccion = self.tree_detalle.selection()
        if not seleccion: return
        deuda_id = self.tree_detalle.item(seleccion, "tags")[1]
        descripcion = self.tree_detalle.item(seleccion)['values'][0]

        pagos = self.db.obtener_detalles_pagos(deuda_id)
        
        top = tk.Toplevel(self)
        top.title(f"Pagos: {descripcion}")
        top.geometry("450x300")
        top.configure(bg="white")
        
        if not pagos:
            tk.Label(top, text="No hay pagos registrados para esta deuda.", bg="white").pack(pady=20)
            return

        cols = ("Fecha", "Monto", "Metodo")
        tree = ttk.Treeview(top, columns=cols, show="headings")
        tree.heading("Fecha", text="Fecha"); tree.column("Fecha", width=120, anchor="center")
        tree.heading("Monto", text="Monto"); tree.column("Monto", width=100, anchor="center")
        tree.heading("Metodo", text="Método"); tree.column("Metodo", width=150, anchor="center")
        tree.pack(fill="both", expand=True, padx=10, pady=10)

        for p in pagos:
            tree.insert("", "end", values=(p[0], f"${p[1]:,.2f}", p[2]))

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
                            texto = item['values'][0] 
                        elif col_id == "#8":
                            texto = item['values'][7] 

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


    # --- ESTADÍSTICAS ---
    def mostrar_estadisticas(self):
        top = tk.Toplevel(self)
        top.title("Panel de Estadísticas")
        top.geometry("900x550")
        top.configure(bg=COLORS['light'])
        
        # Header Principal
        frame_head = tk.Frame(top, bg="white", pady=15)
        frame_head.pack(fill="x")
        tk.Label(frame_head, text="📊 Panel de Control y Estadísticas", font=FONTS['h1'], bg="white", fg=COLORS['primary']).pack()
        
        # Contenedor Principal (Grid 2 columnas)
        main_content = tk.Frame(top, bg=COLORS['light'])
        main_content.pack(fill="both", expand=True, padx=20, pady=20)
        
        main_content.columnconfigure(0, weight=1)
        main_content.columnconfigure(1, weight=1)

        # Footer Actions (Definirlo antes para asegurar que quede abajo)
        frame_foot = tk.Frame(top, bg=COLORS['light'])
        frame_foot.pack(side="bottom", pady=10)

        tk.Button(frame_foot, text="🗓️ Historial Mensual", 
                  command=self.mostrar_historial_mensual,
                  bg=COLORS['primary'], fg="white", font=FONTS['body_bold'], relief="flat", padx=15).pack(side="left", padx=10)

        tk.Button(frame_foot, text="Cerrar Panel", command=top.destroy, bg=COLORS['secondary'], fg="white", font=FONTS['body_bold'], relief="flat", padx=20).pack(side="left", padx=10)
        
        # --- COLUMNA IZQUIERDA: TARJETAS Y TOP DEUDORES ---
        left_panel = tk.Frame(main_content, bg=COLORS['light'])
        left_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        
        # Cálculo de datos generales
        deuda_total = self.db.obtener_deuda_total()
        cobro_mes = self.db.obtener_cobro_mes()
        
        # Tarjetas Resumen
        frame_cards = tk.Frame(left_panel, bg=COLORS['light'])
        frame_cards.pack(fill="x", pady=(0, 20))
        
        # Card 1
        c1 = tk.Frame(frame_cards, bg="white", padx=15, pady=15, relief="solid", bd=1)
        c1.pack(side="left", fill="both", expand=True, padx=(0, 5))
        tk.Label(c1, text="Deuda Activa", font=FONTS['small'], bg="white", fg="gray").pack(anchor="w")
        tk.Label(c1, text=f"${deuda_total:,.2f}", font=FONTS['h1'], fg=COLORS['danger'], bg="white").pack(anchor="w")

        # Card 2
        c2 = tk.Frame(frame_cards, bg="white", padx=15, pady=15, relief="solid", bd=1)
        c2.pack(side="left", fill="both", expand=True, padx=(5, 0))
        tk.Label(c2, text="Ingresos del Mes", font=FONTS['small'], bg="white", fg="gray").pack(anchor="w")
        tk.Label(c2, text=f"${cobro_mes:,.2f}", font=FONTS['h1'], fg=COLORS['success'], bg="white").pack(anchor="w")
        
        # Top Deudores
        tk.Label(left_panel, text="🏆 Top 5 Mayores Deudores", font=FONTS['h2'], bg=COLORS['light'], fg=COLORS['text']).pack(anchor="w", pady=(0, 10))
        
        frame_table = tk.Frame(left_panel, bg="white", relief="solid", bd=1)
        frame_table.pack(fill="both", expand=True)
        
        cols = ("Nombre", "Deuda")
        tree = ttk.Treeview(frame_table, columns=cols, show="headings", height=8)
        tree.heading("Nombre", text="Cliente")
        tree.column("Nombre", width=220)
        tree.heading("Deuda", text="Deuda")
        tree.column("Deuda", width=100, anchor="e")
        tree.pack(fill="both", expand=True)
        
        top_deudores = self.db.obtener_top_deudores()
        for nombre, deuda in top_deudores:
            tree.insert("", "end", values=(nombre, f"${deuda:,.2f}"))

        # --- COLUMNA DERECHA: DESGLOSE DE INGRESOS ---
        right_panel = tk.Frame(main_content, bg=COLORS['light'])
        right_panel.grid(row=0, column=1, sticky="nsew", padx=(10, 0))
        
        tk.Label(right_panel, text="💰 Desglose de Ingresos (Mes)", font=FONTS['h2'], bg=COLORS['light'], fg=COLORS['text']).pack(anchor="w", pady=(0, 10))
        
        frame_breakdown = tk.Frame(right_panel, bg="white", relief="solid", bd=1)
        frame_breakdown.pack(fill="both", expand=True, padx=0)
        
        cols_b = ("Metodo", "Monto", "Porc")
        tree_b = ttk.Treeview(frame_breakdown, columns=cols_b, show="headings")
        tree_b.heading("Metodo", text="Método Pago")
        tree_b.column("Metodo", width=120)
        tree_b.heading("Monto", text="Recaudado")
        tree_b.column("Monto", width=100, anchor="e")
        tree_b.heading("Porc", text="% Total")
        tree_b.column("Porc", width=60, anchor="center")
        tree_b.pack(fill="both", expand=True)
        
        desglose = self.db.obtener_desglose_pagos_mes()
        total_desglose = sum(x[1] for x in desglose) if desglose else 1
        
        for metodo, monto in desglose:
            porcentaje = (monto / total_desglose) * 100
            tree_b.insert("", "end", values=(metodo, f"${monto:,.2f}", f"{porcentaje:.1f}%"))


    def mostrar_historial_mensual(self):
        top = tk.Toplevel(self)
        top.title("Historial de Recaudación Mensual")
        top.geometry("400x500")
        top.configure(bg="white")
        
        tk.Label(top, text="📅 Recaudación por Mes", font=FONTS['h2'], bg="white", fg=COLORS['primary']).pack(pady=15)
        
        frame_table = tk.Frame(top, bg="white", relief="solid", bd=1)
        frame_table.pack(fill="both", expand=True, padx=20, pady=10)
        
        cols = ("Mes", "Monto")
        tree = ttk.Treeview(frame_table, columns=cols, show="headings")
        tree.heading("Mes", text="Mes (Año-Mes)")
        tree.column("Mes", width=150, anchor="center")
        tree.heading("Monto", text="Total Cobrado")
        tree.column("Monto", width=150, anchor="e")
        
        scrollbar = ttk.Scrollbar(frame_table, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        
        tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        datos = self.db.obtener_recaudacion_historica()
        for mes, monto in datos:
            tree.insert("", "end", values=(mes, f"${monto:,.2f}"))
            
        tk.Button(top, text="Cerrar", command=top.destroy, bg=COLORS['secondary'], fg="white").pack(pady=10)

    # --- LÓGICA GENERAL ---
    def modal_nuevo_cliente(self):
        top = tk.Toplevel(self)
        top.title("Nuevo Cliente")
        top.geometry("400x320")
        top.configure(bg="white")
        
        tk.Label(top, text="Registrar Nuevo Cliente", font=FONTS['h2'], bg="white", fg=COLORS['primary']).pack(pady=15)

        tk.Label(top, text="DNI / Código Único:", bg="white", font=FONTS['body_bold']).pack(anchor="w", padx=30)
        
        def validar_solo_numeros(text):
            return text.isdigit() or text == ""
        
        vcmd = (top.register(validar_solo_numeros), '%P')
        
        e_dni = tk.Entry(top, font=FONTS['body'], bg="white", relief="solid", bd=1, 
                         validate='key', validatecommand=vcmd)
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
            saldo = cli[4]
            # Mostrar el saldo tal cual
            if saldo < 0:
                txt_saldo = f"+ ${abs(saldo):,.2f} (Favor)"
            else:
                txt_saldo = f"${saldo:,.2f}"

            self.tree_clientes.insert("", "end", values=(cli[1], cli[2], cli[3], txt_saldo), tags=(cli[0],))

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
        
        # Filtros de ordenamiento
        filtro_actual = self.combo_filtro.get()
        if filtro_actual == "Más Recientes":
            historial.sort(key=lambda x: x[5] if x[5] else "", reverse=True)
        elif filtro_actual == "Más Antiguas":
            historial.sort(key=lambda x: x[5] if x[5] else "", reverse=False)
        elif filtro_actual == "Por Estado":
            peso_estado = {'PENDIENTE': 0, 'PARCIAL': 1, 'PAGADA': 2, 'PAGADO (SALDO)': 2}
            historial.sort(key=lambda x: peso_estado.get(x[7], 99))

        for h in historial:
            f_creacion = h[5] if h[5] else ""
            f_pago = h[6] if h[6] else "-"
            metodo = h[8] if h[8] else "-"
            
            resta_valor = h[4]
            if resta_valor < 0:
                txt_resta = f"+ ${abs(resta_valor):,.2f} (Favor)"
            else:
                txt_resta = f"${resta_valor:,.2f}"

            valores_fila = (h[1], f"${h[2]:,.2f}", f"${h[3]:,.2f}", txt_resta, f_creacion, f_pago, h[7], metodo)
            self.tree_detalle.insert("", "end", values=valores_fila, tags=(h[7], h[0])) 

        # TOTAL GENERAL Y SALDO A FAVOR
        total = self.db.obtener_total_individual(self.cliente_seleccionado_id)
        saldo_favor = self.db.obtener_saldo_a_favor_disponible(self.cliente_seleccionado_id)
        
        if total > 0:
            self.lbl_cliente_total.config(text=f"TOTAL ADEUDADO: ${total:,.2f}", fg=COLORS['danger'])
        elif total < 0:
            # Caso raro donde el total general es negativo, pero visualmente preferimos mostrarlo como "Favor"
            self.lbl_cliente_total.config(text=f"SALDO NETO: +${abs(total):,.2f}", fg=COLORS['success'])
        else:
            self.lbl_cliente_total.config(text="CUENTA AL DÍA ($0.00)", fg=COLORS['success'])

        # GESTIÓN DEL BOTÓN "USAR SALDO"
        if saldo_favor > 0:
            self.lbl_saldo_disponible.config(text=f"HAY SALDO A FAVOR DISPONIBLE: ${saldo_favor:,.2f}")
            self.btn_usar_saldo.config(state="normal", bg=COLORS['warning'])
        else:
            self.lbl_saldo_disponible.config(text="")
            self.btn_usar_saldo.config(state="disabled", bg="gray")

    def guardar_nueva_deuda(self):
        if not self.cliente_seleccionado_id:
            messagebox.showwarning("Error", "Selecciona un cliente primero")
            return
        
        monto_txt = self.entry_monto.get()
        desc = self.entry_desc.get()
        
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
            self.entry_desc.insert(0, "Factura")
            
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
        # Limpieza del string de deuda para obtener float
        texto_debe = str(item['values'][3]) 
        
        if "Favor" in texto_debe:
             val_falta = 0.0
        else:
             try:
                 val_falta = float(texto_debe.replace('$', '').replace(',', ''))
             except:
                 val_falta = 0
        
        # Sugerencias de fecha
        fecha_creacion_str = item['values'][4]
        txt_sugerencia = "Al día"
        if fecha_creacion_str:
            try:
                f_creacion_obj = datetime.strptime(fecha_creacion_str[:10], "%Y-%m-%d")
                f_hoy = datetime.now()
                dias_atraso = (f_hoy - f_creacion_obj).days
                if dias_atraso > 30:
                    txt_sugerencia = f"⚠ Atraso: {dias_atraso} días"
            except: pass 

        if val_falta <= 0 and "Favor" not in texto_debe:
            messagebox.showinfo("Bien", "Esta deuda ya está pagada o tiene saldo a favor. (Puedes agregar más pago si deseas aumentar el saldo)")

        popup = tk.Toplevel(self)
        popup.title("Ingresar Pago")
        popup.geometry("450x650") 
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

        tk.Label(popup, text="Observaciones (Nro Cheque / Nota):", bg="white", font=FONTS['body_bold']).pack(anchor="w", padx=30, pady=(10,0))
        e_obs = tk.Entry(popup, font=FONTS['body'], bg="white", relief="solid", bd=1)
        e_obs.pack(fill="x", padx=30, pady=5, ipady=3)

        def confirmar():
            try:
                monto = float(e_pago.get())
                if monto <= 0: return
                
                # --- LÓGICA DE INTERÉS AGREGADA ---
                try:
                    pct = float(entry_pct.get())
                except: pct = 0.0

                if pct > 0:
                    # El interés se calcula sobre lo que faltaba pagar (val_falta)
                    # Al confirmar, SUMAMOS ese interés a la deuda original 'monto_total'
                    # Así cuando paguen el total + interés, la cuenta da 0 y no sobra plata.
                    interes_monto = val_falta * (pct / 100.0)
                    if interes_monto > 0:
                        self.db.agregar_interes_deuda(deuda_id, interes_monto)
                # ----------------------------------

                metodo_final = c_metodo.get()
                obs = e_obs.get().strip()
                if obs:
                    metodo_final += f" ({obs})"

                self.db.registrar_pago(deuda_id, monto, metodo_final)
                self.actualizar_info_completa()
                self.cargar_lista_clientes(self.entry_buscar.get())
                popup.destroy()
            except: messagebox.showerror("Error", "Monto inválido")

        frame_btn_pago = tk.Frame(popup, bg="white")
        frame_btn_pago.pack(fill="x", pady=20, side="bottom") 
        
        tk.Button(frame_btn_pago, text="CONFIRMAR PAGO", bg=COLORS['success'], fg="white", 
                  font=FONTS['body_bold'], relief="raised", bd=2,
                  command=confirmar, cursor="hand2").pack(fill="x", padx=30, pady=10, ipady=10)
        
        popup.bind('<Return>', lambda e: confirmar())

    def click_usar_saldo(self):
        """Lógica para el botón USAR SALDO A FAVOR"""
        seleccion = self.tree_detalle.selection()
        if not seleccion:
            messagebox.showinfo("Atención", "Selecciona a qué deuda (ROJA/PENDIENTE) quieres aplicarle el saldo.")
            return
        
        deuda_id = self.tree_detalle.item(seleccion, "tags")[1]
        item = self.tree_detalle.item(seleccion)
        estado = item['values'][6] # Columna Estado
        
        if estado == "PAGADA" or "Favor" in str(item['values'][3]):
            messagebox.showinfo("Error", "Esa deuda ya está pagada o tiene saldo a favor. Elige una Pendiente.")
            return
        
        descripcion = item['values'][0]
        
        if messagebox.askyesno("Usar Saldo", f"¿Usar el saldo a favor disponible para pagar '{descripcion}'?"):
            exito = self.db.usar_saldo_manual(self.cliente_seleccionado_id, deuda_id)
            if exito:
                messagebox.showinfo("Éxito", "Saldo aplicado correctamente.")
                self.actualizar_info_completa()
                self.cargar_lista_clientes(self.entry_buscar.get())
            else:
                messagebox.showerror("Error", "No se pudo aplicar (quizás no alcanza el saldo disponible).")

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