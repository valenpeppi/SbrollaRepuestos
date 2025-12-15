import tkinter as tk
from tkinter import ttk, messagebox
import sqlite3

# --- PARTE 1: LA BASE DE DATOS RELACIONAL ---
class BaseDeDatos:
    def __init__(self, db_name="taller_repuestos.db"):
        self.conn = sqlite3.connect(db_name)
        self.cursor = self.conn.cursor()
        self.crear_tablas()

    def crear_tablas(self):
        # Tabla Clientes: Datos personales
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS clientes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT NOT NULL,
                telefono TEXT
            )
        """)
        # Tabla Deudas: Vinculada al cliente por cliente_id
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS deudas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cliente_id INTEGER,
                monto REAL NOT NULL,
                descripcion TEXT,
                fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(cliente_id) REFERENCES clientes(id)
            )
        """)
        self.conn.commit()

    def agregar_cliente(self, nombre, telefono):
        self.cursor.execute("INSERT INTO clientes (nombre, telefono) VALUES (?, ?)", (nombre, telefono))
        self.conn.commit()
        return self.cursor.lastrowid

    def agregar_deuda(self, cliente_id, monto, descripcion):
        self.cursor.execute("INSERT INTO deudas (cliente_id, monto, descripcion) VALUES (?, ?, ?)", 
                            (cliente_id, monto, descripcion))
        self.conn.commit()

    def obtener_clientes_con_saldo(self, filtro=""):
        # CORREGIDO: Quitamos c.telefono de la primera linea del SELECT
        # para que el orden coincida con las columnas de la tabla visual (ID, Nombre, Deuda)
        query = """
            SELECT c.id, c.nombre, COALESCE(SUM(d.monto), 0) as total
            FROM clientes c
            LEFT JOIN deudas d ON c.id = d.cliente_id
            WHERE c.nombre LIKE ?
            GROUP BY c.id
            ORDER BY c.nombre ASC
        """
        self.cursor.execute(query, ('%' + filtro + '%',))
        return self.cursor.fetchall()

    def obtener_historial_cliente(self, cliente_id):
        self.cursor.execute("SELECT id, descripcion, monto, fecha FROM deudas WHERE cliente_id = ? ORDER BY id DESC", (cliente_id,))
        return self.cursor.fetchall()

    def borrar_deuda(self, deuda_id):
        self.cursor.execute("DELETE FROM deudas WHERE id = ?", (deuda_id,))
        self.conn.commit()
        
    def borrar_cliente_entero(self, cliente_id):
        # Borra al cliente y todas sus deudas
        self.cursor.execute("DELETE FROM deudas WHERE cliente_id = ?", (cliente_id,))
        self.cursor.execute("DELETE FROM clientes WHERE id = ?", (cliente_id,))
        self.conn.commit()
    
    # Agrega esto dentro de class BaseDeDatos:
    def obtener_total_individual(self, cliente_id):
        # Suma todos los montos de un cliente especifico
        self.cursor.execute("SELECT COALESCE(SUM(monto), 0) FROM deudas WHERE cliente_id = ?", (cliente_id,))
        return self.cursor.fetchone()[0]

# --- PARTE 2: INTERFAZ GRÁFICA ---
class Aplicacion(tk.Tk):
    def __init__(self):
        super().__init__()
        self.db = BaseDeDatos()
        self.title("Gestión de Cobranzas - Repuestos")
        self.geometry("1000x600")
        
        self.cliente_seleccionado_id = None

        # Configuración de layout principal (2 paneles)
        # Panel Izquierdo: Lista de Clientes
        panel_izquierdo = tk.Frame(self, width=400, bg="#f0f0f0")
        panel_izquierdo.pack(side="left", fill="both", expand=False)
        
        # Panel Derecho: Detalle y Acciones
        self.panel_derecho = tk.Frame(self, bg="white")
        self.panel_derecho.pack(side="right", fill="both", expand=True)

        self.construir_panel_clientes(panel_izquierdo)
        self.construir_panel_detalle(self.panel_derecho)
        
        # Cargar lista inicial
        self.cargar_lista_clientes()

    def construir_panel_clientes(self, parent):
        tk.Label(parent, text="📂 LISTA DE CLIENTES", font=("Arial", 12, "bold"), bg="#f0f0f0").pack(pady=10)
        
        # Buscador
        frame_search = tk.Frame(parent, bg="#f0f0f0")
        frame_search.pack(fill="x", padx=10)
        tk.Label(frame_search, text="Buscar:", bg="#f0f0f0").pack(side="left")
        self.entry_buscar = tk.Entry(frame_search)
        self.entry_buscar.pack(side="left", fill="x", expand=True, padx=5)
        self.entry_buscar.bind("<KeyRelease>", self.filtrar_clientes)

        # Lista de Clientes (Treeview)
        columns = ("ID", "Nombre", "Deuda Total")
        self.tree_clientes = ttk.Treeview(parent, columns=columns, show="headings")
        self.tree_clientes.heading("ID", text="ID")
        self.tree_clientes.heading("Nombre", text="Cliente")
        self.tree_clientes.heading("Deuda Total", text="Deuda Total ($)")
        
        self.tree_clientes.column("ID", width=30)
        self.tree_clientes.column("Nombre", width=180)
        self.tree_clientes.column("Deuda Total", width=100)
        
        self.tree_clientes.pack(fill="both", expand=True, padx=10, pady=5)
        self.tree_clientes.bind("<<TreeviewSelect>>", self.seleccionar_cliente)

        # Botón Nuevo Cliente
        btn_nuevo = tk.Button(parent, text="+ CREAR NUEVO CLIENTE", bg="#2196F3", fg="white", command=self.modal_nuevo_cliente)
        btn_nuevo.pack(fill="x", padx=10, pady=10, ipady=5)

    def construir_panel_detalle(self, parent):
        # Encabezado del cliente
        self.lbl_cliente_nombre = tk.Label(parent, text="Seleccione un cliente", font=("Arial", 16, "bold"), bg="white", fg="#555")
        self.lbl_cliente_nombre.pack(pady=20)

        self.lbl_cliente_total = tk.Label(parent, text="", font=("Arial", 14, "bold"), fg="#d32f2f", bg="white")
        self.lbl_cliente_total.pack(pady=5)

        # Tabla de deudas individuales
        tk.Label(parent, text="Historial de Movimientos:", bg="white").pack(anchor="w", padx=20)
        
        self.tree_detalle = ttk.Treeview(parent, columns=("Desc", "Monto", "Fecha"), show="headings", height=8)
        self.tree_detalle.heading("Desc", text="Descripción")
        self.tree_detalle.heading("Monto", text="Monto ($)")
        self.tree_detalle.heading("Fecha", text="Fecha")
        
        self.tree_detalle.column("Desc", width=250)
        self.tree_detalle.column("Monto", width=80)
        self.tree_detalle.column("Fecha", width=120)
        
        self.tree_detalle.pack(fill="x", padx=20, pady=5)

        # Botón para borrar deuda seleccionada (pagar)
        btn_pagar = tk.Button(parent, text="✅ Marcar Seleccionada como PAGADA", bg="#8bc34a", command=self.pagar_deuda_individual)
        btn_pagar.pack(anchor="e", padx=20, pady=5)

        # --- SECCIÓN AGREGAR NUEVA DEUDA ---
        frame_add = tk.LabelFrame(parent, text="Agregar Deuda a este Cliente", bg="white", padx=10, pady=10)
        frame_add.pack(fill="x", padx=20, pady=20)

        tk.Label(frame_add, text="Concepto:", bg="white").grid(row=0, column=0)
        self.entry_desc = tk.Entry(frame_add, width=30)
        self.entry_desc.grid(row=0, column=1, padx=5)

        tk.Label(frame_add, text="Monto:", bg="white").grid(row=0, column=2)
        self.entry_monto = tk.Entry(frame_add, width=15)
        self.entry_monto.grid(row=0, column=3, padx=5)

        btn_add_deuda = tk.Button(frame_add, text="AGREGAR", bg="#FF9800", fg="black", command=self.guardar_nueva_deuda)
        btn_add_deuda.grid(row=0, column=4, padx=10)

        # Agrega esto dentro de class Aplicacion:
    def actualizar_cartel_total(self):
        if self.cliente_seleccionado_id:
            # Usamos la nueva función de la base de datos
            total_real = self.db.obtener_total_individual(self.cliente_seleccionado_id)
            self.lbl_cliente_total.config(text=f"DEUDA TOTAL: ${total_real}")

    # --- LÓGICA ---
    def cargar_lista_clientes(self, filtro=""):
        for row in self.tree_clientes.get_children():
            self.tree_clientes.delete(row)
        
        clientes = self.db.obtener_clientes_con_saldo(filtro)
        for cli in clientes:
            # cli = (id, nombre, telefono, saldo_total)
            self.tree_clientes.insert("", "end", values=cli)

    def filtrar_clientes(self, event):
        self.cargar_lista_clientes(self.entry_buscar.get())

    def modal_nuevo_cliente(self):
        # Ventana emergente simple para crear cliente
        top = tk.Toplevel(self)
        top.title("Nuevo Cliente")
        top.geometry("300x150")
        
        tk.Label(top, text="Nombre:").pack(pady=5)
        e_nombre = tk.Entry(top)
        e_nombre.pack(pady=5)
        
        tk.Label(top, text="Teléfono:").pack(pady=5)
        e_tel = tk.Entry(top)
        e_tel.pack(pady=5)
        
        def guardar():
            nombre = e_nombre.get()
            if nombre:
                self.db.agregar_cliente(nombre, e_tel.get())
                self.cargar_lista_clientes()
                top.destroy()
        
        tk.Button(top, text="Guardar", command=guardar).pack(pady=10)

    def seleccionar_cliente(self, event):
        seleccion = self.tree_clientes.selection()
        if not seleccion:
            return
        
        item = self.tree_clientes.item(seleccion)
        # item['values'] devuelve [id, nombre, saldo]
        self.cliente_seleccionado_id = item['values'][0]
        nombre = item['values'][1]
        saldo = item['values'][2]

        # Actualizar panel derecho
        self.lbl_cliente_nombre.config(text=f"Cliente: {nombre}")
        self.lbl_cliente_total.config(text=f"DEUDA TOTAL: ${saldo}")
        
        # Cargar historial
        self.cargar_historial()

        self.actualizar_cartel_total()

    def cargar_historial(self):
        for row in self.tree_detalle.get_children():
            self.tree_detalle.delete(row)
            
        historial = self.db.obtener_historial_cliente(self.cliente_seleccionado_id)
        for h in historial:
            # h = (id, descripcion, monto, fecha)
            # Ocultamos el ID en la tabla pero lo usamos para borrar
            self.tree_detalle.insert("", "end", values=(h[1], h[2], h[3]), tags=(h[0],))

    def guardar_nueva_deuda(self):
        if not self.cliente_seleccionado_id:
            messagebox.showwarning("Error", "Seleccione un cliente primero")
            return
        
        monto = self.entry_monto.get()
        desc = self.entry_desc.get()
        
        if not monto: return

        try:
            self.db.agregar_deuda(self.cliente_seleccionado_id, float(monto), desc)
            self.entry_monto.delete(0, tk.END)
            self.entry_desc.delete(0, tk.END)
            
            # Recargar datos
            self.cargar_historial()
            self.cargar_lista_clientes(self.entry_buscar.get()) # Actualizar saldos totales
            self.actualizar_cartel_total()

            # Actualizar label de total manualmente para feedback instantáneo
            items = self.db.obtener_clientes_con_saldo(self.entry_buscar.get())
            for i in items:
                if i[0] == self.cliente_seleccionado_id:
                    self.lbl_cliente_total.config(text=f"DEUDA TOTAL: ${i[3]}")
                    break
                    
        except ValueError:
            messagebox.showerror("Error", "El monto debe ser numérico")

    def pagar_deuda_individual(self):
        seleccion = self.tree_detalle.selection()
        if not seleccion:
            messagebox.showinfo("Info", "Seleccione una deuda del historial para marcarla como pagada")
            return
            
        item = self.tree_detalle.item(seleccion)
        deuda_id = self.tree_detalle.item(seleccion, "tags")[0] # Recuperamos el ID oculto
        
        if messagebox.askyesno("Confirmar", "¿Este repuesto ya fue pagado? Se borrará de la deuda."):
            self.db.borrar_deuda(deuda_id)
            self.cargar_historial()
            self.cargar_lista_clientes(self.entry_buscar.get())
            self.actualizar_cartel_total()
if __name__ == "__main__":
    app = Aplicacion()
    app.mainloop()