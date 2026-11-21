"""Pruebas básicas de los artefactos y endpoints de las tres rutas (unittest)."""
import csv
import json
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from api.main import app
from api.services.model_service import ModelService
from utils.rutas_config import config, modelos_pronostico, ruta_id
from utils.resultados_store import obtener_ruta


class TestIntegracionRutas(unittest.TestCase):
    def test_registro_y_archivos(self):
        for rid in (16, 21, 2):
            cfg = config(rid)
            self.assertEqual(ruta_id(str(rid)), rid)
            for clave in ("grafo", "pronostico", "ciclo", "lgbm", "lgbm_meta", "meta_h7"):
                self.assertTrue(cfg[clave].is_file(), f"{rid}: {clave}")
        self.assertNotEqual(obtener_ruta("prediccion", 2), obtener_ruta("prediccion", 21))
        self.assertNotEqual(obtener_ruta("optimizacion", 2), obtener_ruta("optimizacion", 16))

    def test_grafo_y_panel_r1415(self):
        cfg = config(2)
        with cfg["grafo"].open(encoding="utf-8") as f:
            grafo = json.load(f)
        nodos = {int(n["idpunto"]) for n in grafo["nodos"]}
        self.assertEqual(len(nodos), 14)
        self.assertEqual(len(grafo["aristas"]), 13)
        ids = set()
        for archivo in cfg["panel"].glob("panel_*.csv"):
            with archivo.open(encoding="utf-8", newline="") as f:
                ids.update(int(r["idpunto"]) for r in csv.DictReader(f))
        self.assertEqual(ids, nodos)
        self.assertEqual(len(list(cfg["panel"].glob("panel_*.csv"))), 8)
        self.assertEqual(len(list(cfg["panel"].glob("servicio_*.csv"))), 8)

    def test_modelos(self):
        for rid in (16, 21, 2):
            m = ModelService(rid)
            self.assertEqual(len(m.features), {16:16, 21:20, 2:20}[rid])
        self.assertIn("H1", modelos_pronostico(2))
        self.assertNotIn("H1", modelos_pronostico(21))

    def test_api(self):
        with TestClient(app) as client:
            for rid in (16, 21, 2):
                resp = client.get("/model/info", params={"idruta": rid})
                self.assertEqual(resp.status_code, 200, resp.text)
                resp = client.post("/predictions/run", json={
                    "idruta": rid, "fecha_inicio": "2025-08-31", "horizonte_dias": 7
                })
                self.assertEqual(resp.status_code, 200, resp.text)
                self.assertEqual(len(resp.json()["predicciones"]), 133)
                resp = client.post("/optimization/run", json={
                    "idruta": rid, "fecha": "2025-09-01", "modelo": "H7",
                    "capacidad_bus": 50, "ocupacion_objetivo": 0.75,
                    "presupuesto_ciclos": 338, "flota_disponible": 94,
                    "time_limit": 20
                })
                self.assertEqual(resp.status_code, 200, resp.text)
                self.assertEqual(len(resp.json()["resultados"]), 19)
            self.assertEqual(client.get("/model/info", params={"idruta": 99}).status_code, 400)


if __name__ == "__main__":
    unittest.main()
