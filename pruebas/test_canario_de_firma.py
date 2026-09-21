"""El canario de firma se gasta rompiéndolo, no incrementando un contador.

Hasta esta prueba, `("gastar_canario",)` era `canarios_gastados += 1`: quien pudiera
meter la transacción en un bloque disparaba la transición a voluntad. Acá se fija lo
contrario, en tres partes: la instancia sale de la semilla sin trampa, gastar exige una
firma válida, y cada gasto consume una instancia distinta.
"""

from __future__ import annotations

import unittest

from estado.sintetico import EstadoSintetico, OperacionInvalida
from protocolo import canario
from protocolo import genesis as g
from protocolo.serializacion import HASH_GENESIS, huella
from pruebas.comun import GASTAR_CANARIO, GASTAR_CANARIO_2, nodo_canario

SEMILLA = g.CANARIO_SEMILLA


def gastar(estado: EstadoSintetico, transaccion: tuple) -> None:
    estado.aplicar(transaccion, g.RULESET_INICIAL)


class LaInstanciaSeDerivaDeLaSemilla(unittest.TestCase):
    def test_es_determinista_y_es_la_que_genesis_publica(self):
        recalculada = canario.instancia.__wrapped__(SEMILLA, 0)  # sin el cache
        self.assertEqual(recalculada, canario.instancia(SEMILLA, 0))
        self.assertEqual(canario.compromiso(SEMILLA), g.CANARIO_INSTANCIA)

    def test_los_parametros_son_un_grupo_de_schnorr_valido(self):
        i = canario.instancia(SEMILLA, 0)
        self.assertTrue(canario._es_primo(i.p) and canario._es_primo(i.q))
        self.assertEqual(i.q.bit_length(), 32)
        self.assertEqual((i.p - 1) % i.q, 0)
        for elemento in (i.g, i.y):
            self.assertNotEqual(elemento, 1)
            self.assertEqual(pow(elemento, i.q, i.p), 1, "fuera del subgrupo")

    def test_cada_canario_es_una_instancia_distinta(self):
        self.assertNotEqual(
            canario.instancia(SEMILLA, 0).y, canario.instancia(SEMILLA, 1).y
        )

    def test_la_clave_no_se_deriva_con_un_exponente_conocido(self):
        """Si `y = g^H(semilla)`, la clave privada es ese hash y el canario se gasta solo."""
        i = canario.instancia(SEMILLA, 0)
        ingenuo = int.from_bytes(
            huella(SEMILLA, "canario", hash_id=HASH_GENESIS), "big"
        )
        self.assertNotEqual(i.y, pow(i.g, ingenuo % i.q, i.p))

    def test_es_rompible_que_es_lo_que_lo_hace_una_alarma(self):
        """Un canario que nadie puede gastar no alarma de nada."""
        i = canario.instancia(SEMILLA, 0)
        x = canario.romper(i)
        self.assertEqual(pow(i.g, x, i.p), i.y)


class GastarloExigeUnaFirmaValida(unittest.TestCase):
    def setUp(self):
        self.estado = EstadoSintetico()
        _, self.e, self.s = GASTAR_CANARIO
        self.q = canario.instancia(SEMILLA, 0).q

    def assertRechaza(self, transaccion: tuple):
        with self.assertRaises(OperacionInvalida):
            gastar(self.estado, transaccion)
        self.assertEqual(self.estado.canarios_gastados, 0)

    def test_una_firma_real_lo_gasta(self):
        gastar(self.estado, GASTAR_CANARIO)
        self.assertEqual(self.estado.canarios_gastados, 1)

    def test_el_contador_de_antes_ya_no_lo_gasta(self):
        self.assertRechaza(("gastar_canario",))

    def test_basura_no_lo_gasta(self):
        self.assertRechaza(("gastar_canario", 0, 0))
        self.assertRechaza(("gastar_canario", 1, 2))

    def test_una_firma_alterada_no_lo_gasta(self):
        self.assertRechaza(("gastar_canario", self.e, (self.s + 1) % self.q))
        self.assertRechaza(("gastar_canario", (self.e + 1) % self.q, self.s))

    def test_una_firma_fuera_de_rango_no_lo_gasta(self):
        """`s + q` verificaría igual módulo `q`: aceptarlo es dejar una firma maleable."""
        self.assertRechaza(("gastar_canario", self.e, self.s + self.q))
        self.assertRechaza(("gastar_canario", -1, self.s))

    def test_una_firma_de_otro_tipo_no_lo_gasta(self):
        self.assertRechaza(("gastar_canario", "a", "b"))
        self.assertRechaza(("gastar_canario", self.e))


class CadaGastoConsumeUnaInstanciaDistinta(unittest.TestCase):
    def test_la_firma_del_canario_uno_no_gasta_el_cero(self):
        estado = EstadoSintetico()
        with self.assertRaises(OperacionInvalida):
            gastar(estado, GASTAR_CANARIO_2)
        self.assertEqual(estado.canarios_gastados, 0)

    def test_una_firma_ya_usada_no_gasta_la_siguiente(self):
        """Quien vio el primer gasto no gana nada para disparar la segunda transición."""
        estado = EstadoSintetico()
        gastar(estado, GASTAR_CANARIO)
        with self.assertRaises(OperacionInvalida):
            gastar(estado, GASTAR_CANARIO)
        gastar(estado, GASTAR_CANARIO_2)
        self.assertEqual(estado.canarios_gastados, 2)


class UnNodoNoConmutaConUnCanarioFalso(unittest.TestCase):
    def test_el_bloque_con_la_transaccion_falsa_se_rechaza_y_no_hay_lockin(self):
        nodo = nodo_canario()
        nodo.producir(2)
        with self.assertRaises(OperacionInvalida):
            nodo.producir_bloque([("gastar_canario",)])
        self.assertEqual(nodo.estado.canarios_gastados, 0)
        self.assertEqual(nodo.cronograma.checkpoints, [])
        self.assertEqual(nodo.cronograma.pendientes, {})


if __name__ == "__main__":
    unittest.main()
