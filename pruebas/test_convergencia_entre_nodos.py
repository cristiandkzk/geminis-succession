"""N nodos sin coordinarse — el hueco que dejaba abierto un motor de un nodo solo.

Todo el resto de este recorte prueba **un** `NodoPoD`. Eso alcanza para I3 —el
estado no se mueve porque nunca sale del proceso que lo tiene— y no alcanza para
lo único que un fork es: *dos nodos que dejan de estar en la misma cadena*. Un
mecanismo que conmuta bien en un proceso y distinto en dos no elimina ningún
fork; lo esconde hasta que hay más de una máquina.

Lo que estas pruebas fijan son cuatro cosas, y ninguna necesita red:

1. **nadie se pone de acuerdo con nadie.** Cada nodo se construye solo, produce
   sus propios bloques y no lee ni un byte de los demás. La comparación se hace
   *después*, afuera, y tiene que dar igualdad **bit a bit**: mismo hash de bloque
   a cada altura, mismo `H0_B`, misma altura de activación. Si convergen es por
   determinismo y no por coordinación, porque no hubo canal por donde coordinar;
2. **nadie reemplaza software en la transición.** `arranques` vale 1 en los cuatro
   de punta a punta y `id(estado)` no cambia. Es la versión falsable de *"no hay
   que distribuir un cliente nuevo"*: no es que no lo distribuimos, es que el
   objeto que corre es el mismo antes y después;
3. **un sucesor fuera del espacio de Genesis no consigue checkpoint.** El nodo que
   lo intenta no se desvía: se queda sin transicionar, con el rechazo on-chain (I1);
4. **un nodo que elige otro punto del espacio se desvía, y se detecta con un
   hash.** Acá hay una sutileza que conviene decir en voz alta, porque es lo que
   separa esta prueba de una que se auto-engaña: **el linaje del desviado verifica
   contra sí mismo.** Tiene que verificar — es la misma función de hash. Lo que lo
   delata no es `Verify` fallando en el vacío, es que su `H0_B` de la generación 1
   no es el `H0_B` de la generación 1 de todos los demás. Eso es §5: la cadena que
   conmutó distinto *se desvió*, y se prueba comparando un hash contra el que
   Genesis determinó, no opinando sobre cuál de las dos es la buena.

## Y lo que apareció al escribir esto: `H0_B` no commitea el cronograma

La primera versión de la prueba 4 usaba como adversario un nodo que **acorta su
ventana de finalidad**. Falla, y no por el test: ese nodo activa la transición seis
bloques antes que todos los demás y produce **exactamente el mismo `H0_B`**, el
mismo `state_trigger` y los mismos `params`. Su linaje verifica perfecto contra
`H0_GENESIS`, e injertado en el linaje honesto también verifica.

La causa es concreta: **`ventana_finalidad` es un parámetro del nodo y no del
ruleset.** Entra por el constructor de `NodoPoD`, no vive en `params.internos`, así
que I1 no lo acota y `H( H0_A ‖ state_trigger ‖ params )` no lo commitea. Lo único
que cambia son `altura_lockin` y `altura_activacion`, que son campos del evento
on-chain pero **no insumos de `h0`** — igual que `regla` y `clase`, como ya dice el
docstring de `Checkpoint`.

Lo que eso significa, dicho sin adornos: **el linaje prueba *qué* sucedió y *desde
qué estado*, no *cuándo* se activó.** Un verificador que sólo tiene los checkpoints
no puede distinguir un nodo que activó a tiempo de uno que activó antes. La
divergencia existe y es detectable —los hashes de bloque difieren, y eso se prueba
abajo— pero se detecta con la cadena, no con `Verify`.

No se arregla acá: es una decisión de diseño de §3, y las dos salidas razonables
—mover `ventana_finalidad` a `params.internos`, o meter las alturas en `h0`— cambian
el hash del paper. Queda como está, medido y escrito, con la prueba que lo fija
para que no se pierda.
"""

from __future__ import annotations

import unittest

from nodo.pod import NodoPoD
from protocolo import genesis as g
from protocolo.generacion import Params
from protocolo.linaje import motivo_linaje_invalido, verificar_linaje
from pruebas.comun import GASTAR_CANARIO
from sucesion.regla import ReglaCanarioCriptografico, ReglaEmisionAcumulada

#: Cuántos nodos corren en paralelo. Cuatro y no dos: con dos, un error simétrico
#: —los dos calculan mal lo mismo— se ve igual que una convergencia correcta.
CANTIDAD_NODOS = 4

#: Altura en la que se gasta el canario de §6.6. Con `Δ` criptográfica = 8 y
#: ventana de finalidad = 12, la activación cae en 5 + 12 + 8 = 25.
ALTURA_CANARIO = 5

#: Bloques que produce cada nodo. Holgado a propósito: la prueba no debe depender
#: de que la activación caiga justo en el último.
BLOQUES = 40

#: Para el caso de dos transiciones en vuelo: la de circulación dispara al emitir
#: `paso` unidades, con `emision_por_bloque = 1_000` desde Genesis.
PASO_EMISION = 10_000
BLOQUES_DOS_REGLAS = 110


def reglas_canario() -> list:
    """Una regla criptográfica nueva por nodo. Iguales, pero no compartidas.

    Que cada nodo tenga su propia instancia importa: si compartieran el objeto,
    un estado escondido en la regla haría pasar la prueba por el motivo
    equivocado —convergerían por memoria compartida, que es exactamente lo que
    dos máquinas distintas no tienen—.
    """
    return [ReglaCanarioCriptografico()]


def reglas_dos_clases() -> list:
    """Las dos clases a la vez: `Δ` largo y `Δ` corto, disparando superpuestas."""
    return [ReglaCanarioCriptografico(), ReglaEmisionAcumulada(paso=PASO_EMISION)]


def correr(
    fabrica_de_reglas=reglas_canario,
    bloques: int = BLOQUES,
    altura_canario: int = ALTURA_CANARIO,
    **opciones,
) -> NodoPoD:
    """Un nodo que corre solo `bloques` alturas, gastando el canario en una.

    No recibe bloques de nadie: los produce. Es la forma más fuerte de la prueba
    —si los nodos convergen produciendo cada uno por su cuenta, convergen también
    validando lo que produjo otro— y es la única disponible en esta fase, porque
    el nodo de §6.1 todavía no tiene `aplicar_bloque` (eso es Fase 3).
    """
    nodo = NodoPoD(reglas=fabrica_de_reglas(), **opciones)
    for altura in range(1, bloques + 1):
        transacciones = [GASTAR_CANARIO] if altura == altura_canario else []
        nodo.producir_bloque(transacciones)
    return nodo


def hashes_de(nodo: NodoPoD) -> list[bytes]:
    return [bloque.hash() for bloque in nodo.cadena]


def checkpoints_canonicos(nodo: NodoPoD) -> list[dict]:
    return [c.canonico() for c in nodo.cronograma.checkpoints]


class CuatroNodosConvergenSinCoordinarse(unittest.TestCase):
    """Cuatro nodos independientes producen la misma cadena, bit a bit.

    Es el criterio que faltaba: la conmutación no es una decisión de *este* nodo,
    es una consecuencia de Genesis que cualquier nodo recalcula solo.
    """

    def setUp(self) -> None:
        self.nodos = [correr() for _ in range(CANTIDAD_NODOS)]
        self.primero = self.nodos[0]

    def test_conmutaron_todos(self) -> None:
        for indice, nodo in enumerate(self.nodos):
            with self.subTest(nodo=indice):
                self.assertTrue(
                    nodo.conmutaciones, f"el nodo {indice} no conmutó: {nodo.resumen()}"
                )

    def test_misma_cadena_bloque_por_bloque(self) -> None:
        esperado = hashes_de(self.primero)
        for indice, nodo in enumerate(self.nodos[1:], start=1):
            with self.subTest(nodo=indice):
                self.assertEqual(hashes_de(nodo), esperado)

    def test_mismo_h0_b(self) -> None:
        esperado = [c.h0 for c in self.primero.cronograma.checkpoints]
        self.assertTrue(esperado, "sin checkpoints no hay nada que comparar")
        for indice, nodo in enumerate(self.nodos[1:], start=1):
            with self.subTest(nodo=indice):
                self.assertEqual([c.h0 for c in nodo.cronograma.checkpoints], esperado)

    def test_mismo_checkpoint_completo(self) -> None:
        """No sólo el hash: el evento on-chain entero, campo por campo."""
        esperado = checkpoints_canonicos(self.primero)
        for indice, nodo in enumerate(self.nodos[1:], start=1):
            with self.subTest(nodo=indice):
                self.assertEqual(checkpoints_canonicos(nodo), esperado)

    def test_misma_altura_de_activacion(self) -> None:
        esperado = [c.altura for c in self.primero.conmutaciones]
        for indice, nodo in enumerate(self.nodos[1:], start=1):
            with self.subTest(nodo=indice):
                self.assertEqual([c.altura for c in nodo.conmutaciones], esperado)

    def test_mismo_estado_y_misma_generacion(self) -> None:
        esperada = (self.primero.generacion, self.primero.estado.huella())
        for indice, nodo in enumerate(self.nodos[1:], start=1):
            with self.subTest(nodo=indice):
                self.assertEqual((nodo.generacion, nodo.estado.huella()), esperada)

    def test_el_linaje_verifica_en_todos(self) -> None:
        for indice, nodo in enumerate(self.nodos):
            with self.subTest(nodo=indice):
                self.assertTrue(
                    verificar_linaje(nodo.cronograma.checkpoints, g.H0_GENESIS)
                )


class ConvergenIgualConDosTransicionesEnVuelo(unittest.TestCase):
    """Con `Δ` distintas y disparos superpuestos, tampoco se separan.

    Es el caso donde convergir es menos obvio: entre el lock-in y la activación
    conviven un ruleset vigente y otro ya commiteado, y el orden de activación lo
    fija el lock-in y no la `Δ`. Si dos nodos fueran a desincronizarse en algún
    lado, es acá.

    Deliberadamente **no se afirma cuántas generaciones salen**: lo que se afirma
    es que salen las mismas en todos. Si el escenario cae en la cascada de
    `test_transiciones_en_vuelo`, cae en los cuatro igual.
    """

    def setUp(self) -> None:
        self.nodos = [
            correr(fabrica_de_reglas=reglas_dos_clases, bloques=BLOQUES_DOS_REGLAS)
            for _ in range(CANTIDAD_NODOS)
        ]
        self.primero = self.nodos[0]

    def test_hubo_mas_de_una_generacion(self) -> None:
        self.assertGreater(
            len(self.primero.conmutaciones), 1, self.primero.resumen()
        )

    def test_misma_cadena_bloque_por_bloque(self) -> None:
        esperado = hashes_de(self.primero)
        for indice, nodo in enumerate(self.nodos[1:], start=1):
            with self.subTest(nodo=indice):
                self.assertEqual(hashes_de(nodo), esperado)

    def test_mismo_linaje_completo(self) -> None:
        esperado = checkpoints_canonicos(self.primero)
        for indice, nodo in enumerate(self.nodos[1:], start=1):
            with self.subTest(nodo=indice):
                self.assertEqual(checkpoints_canonicos(nodo), esperado)

    def test_mismos_rechazos(self) -> None:
        """Si el escenario produce rechazos, también son los mismos en todos."""
        esperado = [r.canonico() for r in self.primero.cronograma.rechazos]
        for indice, nodo in enumerate(self.nodos[1:], start=1):
            with self.subTest(nodo=indice):
                self.assertEqual(
                    [r.canonico() for r in nodo.cronograma.rechazos], esperado
                )


class NingunNodoReemplazaSoftwareEnLaTransicion(unittest.TestCase):
    """*"No hay que distribuir un cliente nuevo"*, en forma falsable.

    La afirmación interesante de §3 no es que la activación sea determinista —una
    altura en un `if` también lo es— sino que el nodo que cruza la transición es
    **el mismo objeto** que la empezó. Eso se mide, no se promete: `arranques`
    vale 1 y la identidad del estado no cambia.
    """

    def test_arranques_uno_y_estado_el_mismo(self) -> None:
        for indice in range(CANTIDAD_NODOS):
            with self.subTest(nodo=indice):
                nodo = NodoPoD(reglas=reglas_canario())
                identidad = id(nodo.estado)
                for altura in range(1, BLOQUES + 1):
                    txs = [GASTAR_CANARIO] if altura == ALTURA_CANARIO else []
                    nodo.producir_bloque(txs)
                self.assertTrue(nodo.conmutaciones, nodo.resumen())
                self.assertEqual(nodo.arranques, 1)
                self.assertEqual(id(nodo.estado), identidad)

    def test_la_generacion_final_no_estaba_en_el_constructor(self) -> None:
        """El ruleset que gobierna al final no es el que se le pasó al nacer."""
        nodo = correr()
        self.assertEqual(g.RULESET_INICIAL.generacion, 0)
        self.assertGreater(nodo.ruleset.generacion, 0)
        self.assertNotEqual(nodo.ruleset.h0, g.RULESET_INICIAL.h0)


class UnSucesorFueraDelEspacioNoConsigueCheckpoint(unittest.TestCase):
    """I1: activar un formato que la máquina de Genesis no conoce no es transición.

    El nodo que lo intenta **no se desvía** —ése es el punto—: se queda sin
    transicionar, con el rechazo escrito on-chain, en la misma cadena que los
    demás hasta donde llegó. Un sucesor inventado no parte la red: no arranca.
    """

    def setUp(self) -> None:
        self.impostor = correr(
            fabrica_de_reglas=lambda: [
                ReglaCanarioCriptografico(formato_sucesor="firma/impostora")
            ]
        )

    def test_el_formato_no_estaba_en_genesis(self) -> None:
        self.assertNotIn("firma/impostora", g.FORMATOS_CONOCIDOS)

    def test_no_conmuto_y_quedo_el_rechazo(self) -> None:
        self.assertFalse(self.impostor.conmutaciones, self.impostor.resumen())
        self.assertFalse(self.impostor.cronograma.checkpoints)
        self.assertTrue(self.impostor.cronograma.rechazos)

    def test_sigue_en_la_generacion_cero(self) -> None:
        self.assertEqual(self.impostor.generacion, 0)


class ReglaEmisionACuarto(ReglaEmisionAcumulada):
    """Parte la emisión en cuatro en vez de en dos.

    Es un punto **legítimo** del espacio —250 está dentro de `RangoEntero(0,
    10_000)` igual que 500—, disparado por el mismo hecho del estado y a la misma
    altura. Lo único que cambia son los `params`, que sí son insumo de `h0`.

    Existe porque no hay otra forma de aislar esa mitad: los formatos conocidos que
    Genesis no trae desde el bloque 0 son exactamente uno (`firma/ml-dsa-44`), así
    que por el lado de la interfaz no hay un segundo sucesor válido con el que
    divergir.
    """

    def params_sucesor(self, estado, ruleset) -> Params:
        internos = dict(ruleset.params.internos)
        internos["emision_por_bloque"] = ruleset.interno("emision_por_bloque") // 4
        return Params(
            generacion=ruleset.generacion + 1,
            internos=internos,
            formatos=ruleset.formatos,
        )


class UnNodoQueActivaEnOtroMomentoPresentaElMismoLinaje(unittest.TestCase):
    """El hallazgo: `H0_B` no commitea el cronograma. Ver el docstring del módulo.

    Este nodo acorta su ventana de finalidad, activa seis bloques antes que todos
    los demás y **se desvía de verdad** —sus bloques no son los de nadie—, pero su
    linaje es indistinguible del honesto. No es una prueba de que el mecanismo
    ande: es la que fija el límite de lo que `Verify` prueba.
    """

    def setUp(self) -> None:
        self.honestos = [correr() for _ in range(CANTIDAD_NODOS)]
        self.temprano = correr(ventana_finalidad=6)

    def test_activo_antes_que_los_demas(self) -> None:
        honesta = [c.altura for c in self.honestos[0].conmutaciones]
        temprana = [c.altura for c in self.temprano.conmutaciones]
        self.assertTrue(temprana, self.temprano.resumen())
        self.assertLess(temprana[0], honesta[0])

    def test_su_cadena_no_es_la_de_los_demas(self) -> None:
        """La divergencia es real y se ve en los bloques."""
        self.assertNotEqual(hashes_de(self.temprano), hashes_de(self.honestos[0]))

    def test_y_aun_asi_el_h0_b_es_identico(self) -> None:
        honesto = self.honestos[0].cronograma.checkpoints[0]
        suyo = self.temprano.cronograma.checkpoints[0]
        self.assertEqual(suyo.h0, honesto.h0)
        self.assertEqual(suyo.state_trigger, honesto.state_trigger)
        self.assertEqual(suyo.params, honesto.params)
        # Lo único que se movió son las dos alturas del cronograma, que son campos
        # del evento on-chain y no insumos de `h0`.
        self.assertNotEqual(suyo.altura_activacion, honesto.altura_activacion)
        self.assertNotEqual(suyo.altura_lockin, honesto.altura_lockin)
        self.assertEqual(suyo.altura_disparo, honesto.altura_disparo)

    def test_su_linaje_verifica_y_tambien_injertado(self) -> None:
        """Las dos mitades del límite, juntas, para que no se lea de más."""
        self.assertTrue(
            verificar_linaje(self.temprano.cronograma.checkpoints, g.H0_GENESIS)
        )
        honestos = list(self.honestos[0].cronograma.checkpoints)
        injertado = honestos[:-1] + [self.temprano.cronograma.checkpoints[-1]]
        self.assertIsNone(motivo_linaje_invalido(injertado, g.H0_GENESIS))


class UnNodoQueElijeOtroPuntoDelEspacioSeDesvia(unittest.TestCase):
    """El que parte la emisión en cuatro conmuta, y conmuta a otra cadena.

    Es el adversario honesto: no elige un sucesor inválido ni rompe un hash. Elige
    un punto legítimo del espacio, distinto del que eligieron los demás, disparado
    por el mismo hecho y a la misma altura. Como `params` sí es insumo de `h0`, su
    `H0_B` es otro — y ahí el linaje sí lo delata.
    """

    def setUp(self) -> None:
        self.honestos = [
            correr(
                fabrica_de_reglas=lambda: [ReglaEmisionAcumulada(paso=PASO_EMISION)],
                bloques=BLOQUES_DOS_REGLAS,
            )
            for _ in range(CANTIDAD_NODOS)
        ]
        self.desviado = correr(
            fabrica_de_reglas=lambda: [ReglaEmisionACuarto(paso=PASO_EMISION)],
            bloques=BLOQUES_DOS_REGLAS,
        )

    def test_los_dos_conmutaron(self) -> None:
        """Si el desviado no conmutara, esto no diría nada sobre divergencia."""
        self.assertTrue(self.honestos[0].conmutaciones, self.honestos[0].resumen())
        self.assertTrue(self.desviado.conmutaciones, self.desviado.resumen())

    def test_disparo_en_la_misma_altura_por_el_mismo_hecho(self) -> None:
        """Aísla la causa: lo único distinto son los `params`, no el momento."""
        honesto = self.honestos[0].cronograma.checkpoints[0]
        suyo = self.desviado.cronograma.checkpoints[0]
        self.assertEqual(suyo.altura_disparo, honesto.altura_disparo)
        self.assertEqual(suyo.state_trigger, honesto.state_trigger)
        self.assertNotEqual(suyo.params, honesto.params)

    def test_su_h0_b_no_es_el_de_los_demas(self) -> None:
        honesto = self.honestos[0].cronograma.checkpoints[0]
        suyo = self.desviado.cronograma.checkpoints[0]
        self.assertEqual(honesto.generacion, suyo.generacion)
        self.assertNotEqual(suyo.h0, honesto.h0)

    def test_su_linaje_verifica_contra_si_mismo(self) -> None:
        """**Y tiene que verificar.** Es la misma función de hash.

        Esto es lo que una prueba ingenua se pierde: un desviado no se detecta
        porque `Verify` le falle, se detecta porque su `H0_B` no es el que Genesis
        determinó para esa generación. Afirmarlo acá explícitamente es lo que
        impide que alguien lea el test de al lado como *"el fraude no verifica"*.
        """
        self.assertTrue(
            verificar_linaje(self.desviado.cronograma.checkpoints, g.H0_GENESIS)
        )

    def test_su_checkpoint_no_entra_en_el_linaje_honesto(self) -> None:
        """Injertarlo en la cadena de los demás sí rompe, y dice dónde."""
        honestos = list(self.honestos[0].cronograma.checkpoints)
        injertado = [self.desviado.cronograma.checkpoints[0]] + honestos[1:]
        motivo = motivo_linaje_invalido(injertado, g.H0_GENESIS)
        self.assertIsNotNone(motivo)

    def test_los_honestos_siguen_de_acuerdo_entre_ellos(self) -> None:
        """Un nodo que se va no arrastra a los que se quedan."""
        esperado = hashes_de(self.honestos[0])
        for indice, nodo in enumerate(self.honestos[1:], start=1):
            with self.subTest(nodo=indice):
                self.assertEqual(hashes_de(nodo), esperado)
        self.assertNotEqual(hashes_de(self.desviado), esperado)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
