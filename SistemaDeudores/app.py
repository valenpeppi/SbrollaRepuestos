import tkinter as tk
from tkinter import ttk, messagebox
import sqlite3
from datetime import datetime
import os 

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

    def agregar_cliente(self, dni, nombre, telefono, localidad):
        self.cursor.execute("INSERT INTO clientes (dni, nombre, telefono, localidad) VALUES (?, ?, ?, ?)", 
                            (dni, nombre, telefono, localidad))
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

# --- PARTE 2: INTERFAZ GRÁFICA ---
class Aplicacion(tk.Tk):
    def __init__(self):
        super().__init__()
        self.db = BaseDeDatos()
        self.title("Gestión de Repuestos - Sistema Completo")
        self.geometry("1300x750")
        
        self.cliente_seleccionado_id = None

        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Treeview", font=('Arial', 10), rowheight=28)
        style.configure("Treeview.Heading", font=('Arial', 10, 'bold'))

        panel_izquierdo = tk.Frame(self, width=400, bg="#e0e0e0")
        panel_izquierdo.pack(side="left", fill="both", expand=False)
        
        self.panel_derecho = tk.Frame(self, bg="white")
        self.panel_derecho.pack(side="right", fill="both", expand=True)

        self.construir_panel_clientes(panel_izquierdo)
        self.construir_panel_detalle(self.panel_derecho)
        
        self.cargar_lista_clientes()

    def construir_panel_clientes(self, parent):
        tk.Label(parent, text="📂 CLIENTES", font=("Arial", 14, "bold"), bg="#e0e0e0").pack(pady=20)
        
        frame_search = tk.Frame(parent, bg="#e0e0e0")
        frame_search.pack(fill="x", padx=10)
        tk.Label(frame_search, text="Buscar (Nom/DNI/Loc):", bg="#e0e0e0").pack(side="left")
        self.entry_buscar = tk.Entry(frame_search)
        self.entry_buscar.pack(side="left", fill="x", expand=True, padx=5)
        self.entry_buscar.bind("<KeyRelease>", self.filtrar_clientes)

        frame_tabla = tk.Frame(parent)
        frame_tabla.pack(fill="both", expand=True, padx=10, pady=5)

        scrollbar = tk.Scrollbar(frame_tabla)
        scrollbar.pack(side="right", fill="y")

        columns = ("DNI", "Nombre", "Loc", "Saldo")
        self.tree_clientes = ttk.Treeview(frame_tabla, columns=columns, show="headings", yscrollcommand=scrollbar.set)
        
        scrollbar.config(command=self.tree_clientes.yview)

        self.tree_clientes.heading("DNI", text="DNI / Cód")
        self.tree_clientes.heading("Nombre", text="Nombre")
        self.tree_clientes.heading("Loc", text="Loc")
        self.tree_clientes.heading("Saldo", text="Debe ($)")
        
        self.tree_clientes.column("DNI", width=80)
        self.tree_clientes.column("Nombre", width=140)
        self.tree_clientes.column("Loc", width=80)
        self.tree_clientes.column("Saldo", width=80)
        
        self.tree_clientes.pack(side="left", fill="both", expand=True)
        self.tree_clientes.bind("<<TreeviewSelect>>", self.seleccionar_cliente)

        btn_nuevo = tk.Button(parent, text="+ NUEVO CLIENTE", bg="#2196F3", fg="white", font=("Arial", 10, "bold"), command=self.modal_nuevo_cliente)
        btn_nuevo.pack(fill="x", padx=10, pady=10, ipady=5)

    def construir_panel_detalle(self, parent):
        frame_encabezado = tk.Frame(parent, bg="white")
        frame_encabezado.pack(pady=10, fill="x", padx=20) 

        carpeta_actual = os.path.dirname(os.path.abspath(__file__))
        ruta_completa_imagen = os.path.join(carpeta_actual, "Logo_Sbrolla.png")
        
        if os.path.exists(ruta_completa_imagen):
            try:
                self.img_logo = tk.PhotoImage(file=ruta_completa_imagen)
                self.img_logo = self.img_logo.subsample(4, 4) 
                lbl_img = tk.Label(frame_encabezado, image=self.img_logo, bg="white")
                lbl_img.pack(side="left") 
            except Exception as e:
                print(f"Error cargando imagen: {e}")

        self.lbl_cliente_nombre = tk.Label(frame_encabezado, text="Seleccione un cliente", font=("Arial", 22, "bold"), bg="white", fg="#333")
        self.lbl_cliente_nombre.pack(side="left", expand=True, fill="x")

        self.lbl_cliente_total = tk.Label(parent, text="", font=("Arial", 16, "bold"), fg="#d32f2f", bg="white")
        self.lbl_cliente_total.pack(pady=5)

        frame_add = tk.LabelFrame(parent, text="Cargar Nueva Deuda", bg="white", padx=10, pady=10, font=("Arial", 11, "bold"), fg="#d32f2f")
        frame_add.pack(fill="x", padx=20, pady=10)

        tk.Label(frame_add, text="Repuesto:", bg="white").grid(row=0, column=0, padx=5, sticky="e")
        self.entry_desc = tk.Entry(frame_add, width=35)
        self.entry_desc.grid(row=0, column=1, padx=5)

        tk.Label(frame_add, text="Monto ($):", bg="white").grid(row=0, column=2, padx=5, sticky="e")
        self.entry_monto = tk.Entry(frame_add, width=15)
        self.entry_monto.grid(row=0, column=3, padx=5)

        tk.Label(frame_add, text="Fecha (dd/mm/aaaa):", bg="white").grid(row=0, column=4, padx=5, sticky="e")
        self.entry_fecha = tk.Entry(frame_add, width=15) 
        self.entry_fecha.grid(row=0, column=5, padx=5)
        tk.Label(frame_add, text="(Opcional)", font=("Arial", 8), fg="gray", bg="white").grid(row=1, column=5)

        btn_add_deuda = tk.Button(frame_add, text="AGREGAR", bg="#FF9800", fg="black", font=("Arial", 9, "bold"), command=self.guardar_nueva_deuda)
        btn_add_deuda.grid(row=0, column=6, padx=15, rowspan=2)

        frame_head = tk.Frame(parent, bg="white")
        frame_head.pack(fill="x", padx=20, pady=(10, 0))
        
        tk.Label(frame_head, text="Historial de Cuenta Corriente:", bg="white", font=("Arial", 10)).pack(side="left")
        
        frame_filtro_container = tk.Frame(frame_head, bg="white")
        frame_filtro_container.pack(side="right")

        tk.Label(frame_filtro_container, text="Ordenar por:", bg="white", font=("Arial", 9)).pack(side="left", padx=5)
        self.combo_filtro = ttk.Combobox(frame_filtro_container, values=["Más Recientes", "Más Antiguas", "Por Estado (Pendientes primero)"], state="readonly", width=25)
        self.combo_filtro.current(0)
        self.combo_filtro.pack(side="left")
        self.combo_filtro.bind("<<ComboboxSelected>>", self.aplicar_filtro)

        frame_tabla = tk.Frame(parent, bg="white")
        frame_tabla.pack(fill="both", expand=True, padx=20, pady=5)

        scrollbar = tk.Scrollbar(frame_tabla)
        scrollbar.pack(side="right", fill="y")

        columns = ("Desc", "Original", "Pagado", "Resta", "Fecha Ingreso", "Ultimo Pago", "Estado", "Metodo")
        self.tree_detalle = ttk.Treeview(frame_tabla, columns=columns, show="headings", yscrollcommand=scrollbar.set)
        scrollbar.config(command=self.tree_detalle.yview)

        self.tree_detalle.heading("Desc", text="Repuesto / Nota")
        self.tree_detalle.heading("Original", text="Original ($)")
        self.tree_detalle.heading("Pagado", text="Pagado ($)")
        self.tree_detalle.heading("Resta", text="Falta ($)")
        self.tree_detalle.heading("Fecha Ingreso", text="Fecha Fiao'")
        self.tree_detalle.heading("Ultimo Pago", text="Fecha Pago")
        self.tree_detalle.heading("Estado", text="Estado")
        self.tree_detalle.heading("Metodo", text="Forma Pago")
        
        self.tree_detalle.column("Desc", width=180)
        self.tree_detalle.column("Original", width=70)
        self.tree_detalle.column("Pagado", width=70)
        self.tree_detalle.column("Resta", width=70)
        self.tree_detalle.column("Fecha Ingreso", width=110)
        self.tree_detalle.column("Ultimo Pago", width=110)
        self.tree_detalle.column("Estado", width=80)
        self.tree_detalle.column("Metodo", width=90)
        
        self.tree_detalle.tag_configure('PENDIENTE', background='#ffcccc') 
        self.tree_detalle.tag_configure('PARCIAL', background='#fff4e5')   
        self.tree_detalle.tag_configure('PAGADA', background='#d4edda')    
        
        self.tree_detalle.pack(side="left", fill="both", expand=True)

        frame_acciones = tk.Frame(parent, bg="white")
        frame_acciones.pack(fill="x", padx=20, pady=15) 

        btn_pagar = tk.Button(frame_acciones, text="💵 INGRESAR PAGO", bg="#4CAF50", fg="white", 
                              font=("Arial", 12, "bold"), padx=20, pady=10, 
                              command=self.abrir_ventana_pago)
        btn_pagar.pack(side="right", padx=10)

        btn_eliminar = tk.Button(frame_acciones, text="🗑️ Eliminar Registro", bg="#757575", fg="white", 
                                 font=("Arial", 10, "bold"), padx=15, pady=8,
                                 command=self.eliminar_error)
        btn_eliminar.pack(side="right", padx=10)

    # --- LÓGICA ---
    def modal_nuevo_cliente(self):
        top = tk.Toplevel(self)
        top.title("Nuevo Cliente")
        top.geometry("350x300")
        
        tk.Label(top, text="DNI / Código (Lo que se verá en la lista):").pack(pady=5)
        e_dni = tk.Entry(top)
        e_dni.pack(pady=5)

        tk.Label(top, text="Nombre y Apellido:").pack(pady=5)
        e_nombre = tk.Entry(top)
        e_nombre.pack(pady=5)
        
        tk.Label(top, text="Localidad:").pack(pady=5)
        valores_loc = ["Bombal", "Bigand", "Firmat", "Alcorta", "Rosario", "Venado Tuerto", "Otro"]
        e_localidad = ttk.Combobox(top, values=valores_loc, state="readonly")
        e_localidad.pack(pady=5)
        e_localidad.current(0)

        tk.Label(top, text="Teléfono:").pack(pady=5)
        e_tel = tk.Entry(top)
        e_tel.pack(pady=5)
        
        def guardar():
            if e_nombre.get() and e_dni.get():
                self.db.agregar_cliente(e_dni.get(), e_nombre.get(), e_tel.get(), e_localidad.get())
                self.cargar_lista_clientes()
                top.destroy()
            else:
                messagebox.showwarning("Faltan datos", "El DNI/Código y el Nombre son obligatorios")
        
        tk.Button(top, text="GUARDAR", bg="#2196F3", fg="white", command=guardar).pack(pady=20)

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
            self.lbl_cliente_nombre.config(text=f"Cliente: {nombre_cliente}")
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
            historial.sort(key=lambda x: x[0], reverse=True)
        elif filtro_actual == "Más Antiguas":
            historial.sort(key=lambda x: x[0], reverse=False)
        elif filtro_actual == "Por Estado (Pendientes primero)":
            peso_estado = {'PENDIENTE': 0, 'PARCIAL': 1, 'PAGADA': 2}
            historial.sort(key=lambda x: peso_estado.get(x[7], 99))

        for h in historial:
            f_creacion = h[5] if h[5] else ""
            f_pago = h[6] if h[6] else "-"
            metodo = h[8] if h[8] else "-"
            
            valores_fila = (h[1], f"${h[2]}", f"${h[3]}", f"${h[4]}", f_creacion, f_pago, h[7], metodo)
            self.tree_detalle.insert("", "end", values=valores_fila, tags=(h[7], h[0])) 

        total = self.db.obtener_total_individual(self.cliente_seleccionado_id)
        self.lbl_cliente_total.config(text=f"DEUDA TOTAL: ${total:,.2f}")

    def guardar_nueva_deuda(self):
        if not self.cliente_seleccionado_id:
            messagebox.showwarning("Error", "Selecciona un cliente primero")
            return
        
        monto_txt = self.entry_monto.get()
        desc = self.entry_desc.get()
        fecha_txt = self.entry_fecha.get().strip()

        if not monto_txt: return

        fecha_final = None
        if fecha_txt:
            try:
                fecha_obj = datetime.strptime(fecha_txt, "%d/%m/%Y")
                if fecha_obj.date() > datetime.now().date():
                    messagebox.showerror("Error de Fecha", "No puedes registrar deudas con fecha futura.")
                    return 
                fecha_final = fecha_obj.strftime("%Y-%m-%d 00:00")
            except ValueError:
                messagebox.showerror("Error de Fecha", "Formato incorrecto.\nUtilice: DD/MM/AAAA (ej: 25/01/2024)")
                return

        try:
            monto = float(monto_txt)
            self.db.agregar_deuda(self.cliente_seleccionado_id, monto, desc, fecha_final)
            
            self.entry_monto.delete(0, tk.END)
            self.entry_desc.delete(0, tk.END)
            self.entry_fecha.delete(0, tk.END)
            
            self.actualizar_info_completa()
            self.cargar_lista_clientes(self.entry_buscar.get())
        except ValueError:
            messagebox.showerror("Error", "El monto debe ser un número")

    def abrir_ventana_pago(self):
        seleccion = self.tree_detalle.selection()
        if not seleccion:
            messagebox.showinfo("Atención", "Selecciona qué deuda quiere pagar el cliente.")
            return
            
        tags = self.tree_detalle.item(seleccion, "tags")
        deuda_id = tags[1] 
        
        item = self.tree_detalle.item(seleccion)
        desc = item['values'][0]
        falta_pagar = str(item['values'][3]).replace('$', '')
        
        # --- CALCULO DE DIAS Y SUGERENCIA ---
        fecha_creacion_str = item['values'][4]
        dias_atraso = 0
        porcentaje_sugerido = 0
        txt_sugerencia = "Sin recargo sugerido"
        
        if fecha_creacion_str:
            try:
                f_creacion_obj = datetime.strptime(fecha_creacion_str[:10], "%Y-%m-%d")
                f_hoy = datetime.now()
                dias_atraso = (f_hoy - f_creacion_obj).days
                
                # REGLA: Cada 30 dias se suma 10%
                bloques_30_dias = dias_atraso // 30
                porcentaje_sugerido = bloques_30_dias * 10
                
                if porcentaje_sugerido > 0:
                    txt_sugerencia = f"⚠ SUGERIDO: {porcentaje_sugerido}% ({dias_atraso} días de atraso)"
                else:
                    txt_sugerencia = f"Sin recargo ({dias_atraso} días de atraso)"
                    
            except:
                pass 

        try:
            val_falta = float(falta_pagar)
        except:
            val_falta = 0
            
        if val_falta <= 0:
            messagebox.showinfo("Bien", "Esta deuda ya está pagada por completo.")
            return

        # CONFIGURACION VENTANA POPUP
        popup = tk.Toplevel(self)
        popup.title("Ingresar Pago")
        popup.geometry("500x650")
        popup.configure(bg="white") # Fondo blanco limpio
        
        # Titulo Principal
        tk.Label(popup, text=f"Pagando: {desc}", font=("Arial", 14, "bold"), bg="white").pack(pady=10)
        
        # Panel de Deuda Original
        frame_deuda = tk.LabelFrame(popup, text="Estado Actual", bg="white", padx=10, pady=5)
        frame_deuda.pack(pady=5, padx=20, fill="x")
        
        tk.Label(frame_deuda, text=f"Capital a Pagar:", font=("Arial", 10), bg="white").pack(side="left")
        tk.Label(frame_deuda, text=f"${val_falta}", font=("Arial", 12, "bold"), fg="red", bg="white").pack(side="right")

        # Panel Sugerencia
        color_sug = "#FF9800" if porcentaje_sugerido > 0 else "green"
        tk.Label(popup, text=txt_sugerencia, fg=color_sug, font=("Arial", 10, "bold"), bg="white").pack(pady=10)

        # --- SECCION INTERESES ---
        frame_interes = tk.LabelFrame(popup, text="Aplicar Interés / Recargo", padx=10, pady=10, bg="white")
        frame_interes.pack(pady=5, padx=20, fill="x")

        # Entrada manual de porcentaje
        tk.Label(frame_interes, text="% Interés:", bg="white").pack(side="left")
        entry_porcentaje = tk.Entry(frame_interes, width=5, font=("Arial", 11), justify="center")
        entry_porcentaje.pack(side="left", padx=5)
        entry_porcentaje.insert(0, "0") # SIEMPRE EMPIEZA EN 0 POR DEFECTO

        # Botones rapidos
        def set_porcentaje(valor):
            entry_porcentaje.delete(0, tk.END)
            entry_porcentaje.insert(0, str(valor))
            calcular_total_con_interes()

        # Botones estéticos
        tk.Button(frame_interes, text="10%", bg="#e0e0e0", command=lambda: set_porcentaje(10)).pack(side="left", padx=2)
        tk.Button(frame_interes, text="20%", bg="#e0e0e0", command=lambda: set_porcentaje(20)).pack(side="left", padx=2)
        
        # Boton especial para la sugerencia
        if porcentaje_sugerido > 0:
             tk.Button(frame_interes, text=f"Aplicar Sugerido ({porcentaje_sugerido}%)", bg="#FFCC80", 
                       command=lambda: set_porcentaje(porcentaje_sugerido)).pack(side="left", padx=5)

        # LABEL DINAMICO DE TOTAL
        lbl_total_con_interes = tk.Label(popup, text=f"Total a Cobrar: ${val_falta}", font=("Arial", 16, "bold"), fg="#2196F3", bg="white")
        lbl_total_con_interes.pack(pady=15)

        # Funcion de calculo en tiempo real
        def calcular_total_con_interes(event=None):
            try:
                pct = float(entry_porcentaje.get())
                total_calc = val_falta * (1 + pct / 100)
                lbl_total_con_interes.config(text=f"Total a Cobrar: ${total_calc:.2f}")
                return total_calc
            except ValueError:
                return val_falta

        # Vinculamos la entrada de texto al calculo
        entry_porcentaje.bind("<KeyRelease>", calcular_total_con_interes)

        # --- ENTRADA DE DINERO ---
        frame_pago = tk.LabelFrame(popup, text="Ingreso del Dinero", bg="white", padx=10, pady=10)
        frame_pago.pack(fill="x", padx=20, pady=5)
        
        tk.Label(frame_pago, text="Monto Final que Paga:", bg="white").pack(pady=2)
        entry_pago = tk.Entry(frame_pago, font=("Arial", 14), justify="center")
        entry_pago.pack(pady=5, fill="x")
        entry_pago.focus()

        # BOTON PAGO COMPLETO (Usa el total con interes)
        def set_pago_completo():
            total_final = calcular_total_con_interes()
            entry_pago.delete(0, tk.END)
            entry_pago.insert(0, f"{total_final:.2f}")
            entry_pago.focus()

        btn_completo = tk.Button(frame_pago, text="⚡ PAGO COMPLETO (Con Interés)", bg="#2196F3", fg="white", 
                                 font=("Arial", 10, "bold"), command=set_pago_completo)
        btn_completo.pack(pady=5, fill="x")

        # --- FORMA DE PAGO ---
        tk.Label(frame_pago, text="Forma de Pago:", bg="white").pack(pady=2)
        combo_metodo = ttk.Combobox(frame_pago, values=["Efectivo", "Transferencia", "Débito", "Crédito", "Cheque"], state="readonly")
        combo_metodo.current(0) 
        combo_metodo.pack(pady=5, fill="x")

        def confirmar():
            try:
                monto = float(entry_pago.get())
                if monto <= 0: return
                
                metodo = combo_metodo.get()
                
                self.db.registrar_pago_parcial(deuda_id, monto, metodo)
                self.actualizar_info_completa()
                self.cargar_lista_clientes(self.entry_buscar.get())
                popup.destroy()
            except ValueError:
                messagebox.showerror("Error", "Ingresa un número válido")

        tk.Button(popup, text="CONFIRMAR PAGO", bg="#4CAF50", fg="white", font=("Arial", 12, "bold"), 
                  pady=10, command=confirmar).pack(pady=20, fill="x", padx=20)
        
        popup.bind('<Return>', lambda event: confirmar())

    def eliminar_error(self):
        seleccion = self.tree_detalle.selection()
        if not seleccion: return
        tags = self.tree_detalle.item(seleccion, "tags")
        deuda_id = tags[1]
        if messagebox.askyesno("Borrar", "¿Borrar este registro permanentemente?"):
            self.db.borrar_deuda_permanentemente(deuda_id)
            self.actualizar_info_completa()
            self.cargar_lista_clientes(self.entry_buscar.get())

if __name__ == "__main__":
    app = Aplicacion()
    app.mainloop()