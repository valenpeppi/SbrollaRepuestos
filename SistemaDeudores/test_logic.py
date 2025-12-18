import unittest
import os
import sqlite3
from datetime import datetime
from app import BaseDeDatos

class TestSistemaDeudores(unittest.TestCase):
    def setUp(self):
        # Use a temporary file database for testing to ensure isolation
        self.db_name = "test_db.sqlite"
        if os.path.exists(self.db_name):
            os.remove(self.db_name)
        self.db = BaseDeDatos(self.db_name)

    def tearDown(self):
        self.db.conn.close()
        if os.path.exists(self.db_name):
            os.remove(self.db_name)

    def test_crear_y_buscar_cliente(self):
        """Test creating a client and finding them."""
        self.db.nuevo_cliente("12345678", "Juan Perez", "123456", "Centro")
        
        # Test exact match
        res = self.db.buscar_clientes("Juan")
        self.assertTrue(len(res) > 0)
        self.assertEqual(res[0][2], "Juan Perez")
        
        # Test searching by DNI
        res_dni = self.db.buscar_clientes("12345678")
        self.assertEqual(len(res_dni), 1)

    def test_deuda_y_pagos(self):
        """Test debt creation, partial payment, and full payment."""
        # Create client
        self.db.nuevo_cliente("111", "Test User", "", "")
        client_id = self.db.cursor.lastrowid
        
        # Create debt
        self.db.nueva_deuda(client_id, "Repuesto X", 1000.0, "01", "01", "2024")
        
        # Verify initial debt
        deudas = self.db.obtener_historial(client_id)
        self.assertEqual(len(deudas), 1)
        self.assertEqual(deudas[0][2], 1000.0) # Monto Total
        self.assertEqual(deudas[0][7], "PENDIENTE")
        
        # Make Partial Payment (500)
        deuda_id = deudas[0][0]
        self.db.registrar_pago(deuda_id, 500.0, "Efectivo")
        
        # Verify status update
        deudas = self.db.obtener_historial(client_id)
        self.assertEqual(deudas[0][3], 500.0) # Pagado
        self.assertEqual(deudas[0][7], "PARCIAL")
        
        # Make Remaining Payment (500)
        self.db.registrar_pago(deuda_id, 500.0, "Efectivo")
        
        # Verify status update
        deudas = self.db.obtener_historial(client_id)
        self.assertEqual(deudas[0][3], 1000.0) # Pagado
        self.assertAlmostEqual(deudas[0][4], 0.0) # Resta
        self.assertEqual(deudas[0][7], "PAGADA")

    def test_interes_deuda(self):
        """Verify adding interest increases the total debt amount."""
        self.db.nuevo_cliente("222", "Interes User", "", "")
        client_id = self.db.cursor.lastrowid
        self.db.nueva_deuda(client_id, "Deuda con Interes", 1000.0, "01", "01", "2024")
        
        deudas = self.db.obtener_historial(client_id)
        deuda_id = deudas[0][0]
        
        # Apply 10% interest (100.0)
        self.db.agregar_interes_deuda(deuda_id, 100.0)
        
        deudas = self.db.obtener_historial(client_id)
        self.assertEqual(deudas[0][2], 1100.0) # New Total

    def test_estadisticas_agrupacion(self):
        """
        CRITICAL: Verify that 'Debito (algo)' is aggregated as 'Debito'.
        """
        # We need to manually insert into pagos_detalle to simulate different months/methods
        # because registrar_pago uses current date.
        
        # Mocking data insertion directly into pagos_detalle for control
        mes_actual = datetime.now().strftime("%Y-%m-%d")
        
        # Insert raw payments
        self.db.cursor.execute("INSERT INTO pagos_detalle (deuda_id, fecha, monto, metodo) VALUES (?, ?, ?, ?)", 
                               (1, mes_actual, 100.0, "Debito"))
        self.db.cursor.execute("INSERT INTO pagos_detalle (deuda_id, fecha, monto, metodo) VALUES (?, ?, ?, ?)", 
                               (1, mes_actual, 200.0, "Debito (Banco X)"))
        self.db.cursor.execute("INSERT INTO pagos_detalle (deuda_id, fecha, monto, metodo) VALUES (?, ?, ?, ?)", 
                               (1, mes_actual, 50.0, "Efectivo"))
        self.db.conn.commit()
        
        # Test aggregation method
        desglose = self.db.obtener_desglose_pagos_mes() # Returns list of tuples (method, amount)
        
        # Convert to dict for easier checking
        res_dict = dict(desglose)
        
        # 'Debito' should be 100 + 200 = 300
        self.assertIn("Debito", res_dict)
        self.assertEqual(res_dict["Debito"], 300.0)
        
        # 'Debito (Banco X)' should NOT exist
        self.assertNotIn("Debito (Banco X)", res_dict)
        
        # 'Efectivo' should be 50
        self.assertEqual(res_dict["Efectivo"], 50.0)

    def test_recaudacion_historica(self):
        """Verify monthly grouping."""
        # Insert payments in different months
        self.db.cursor.execute("INSERT INTO pagos_detalle (deuda_id, fecha, monto, metodo) VALUES (?, ?, ?, ?)", 
                               (1, "2024-01-15", 1000.0, "Efectivo"))
        self.db.cursor.execute("INSERT INTO pagos_detalle (deuda_id, fecha, monto, metodo) VALUES (?, ?, ?, ?)", 
                               (1, "2024-02-20", 2000.0, "Efectivo"))
        self.db.cursor.execute("INSERT INTO pagos_detalle (deuda_id, fecha, monto, metodo) VALUES (?, ?, ?, ?)", 
                               (1, "2024-01-10", 500.0, "Efectivo"))
        self.db.conn.commit()
        
        historial = self.db.obtener_recaudacion_historica()
        # Should return [(Month, Total), ...]
        
        # Convert to dict
        hist_dict = dict(historial)
        
        self.assertEqual(hist_dict["2024-01"], 1500.0)
        self.assertEqual(hist_dict["2024-02"], 2000.0)

if __name__ == '__main__':
    import sys
    runner = unittest.TextTestRunner(stream=sys.stdout, verbosity=2)
    unittest.main(testRunner=runner)
