"""Pruebas de triage_queue con unittest (biblioteca estándar).

Ejecutar desde la raíz del proyecto:

    python -m unittest discover -s tests -v
"""

import sys
import threading
import unittest
from datetime import date, datetime
from pathlib import Path

# Permite importar triage_queue.py (en la raíz) desde cualquier directorio.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import triage_queue  # noqa: E402
from triage_queue import (  # noqa: E402
    EmptyQueueError,
    InvalidPatientError,
    Patient,
    TriageQueue,
    TriageQueueError,
)


def names(patients):
    return [patient.name for patient in patients]


def drain(queue):
    """Vacía la cola y devuelve los nombres en orden de extracción."""
    return [queue.dequeue().name for _ in range(len(queue))]


class PatientModelTests(unittest.TestCase):
    """Validación del modelo de datos."""

    def test_valid_patient_keeps_its_data(self):
        arrival = datetime(2026, 11, 17, 9, 30)
        patient = Patient("Ana", 2, arrival)
        self.assertEqual(patient.name, "Ana")
        self.assertEqual(patient.triage_level, 2)
        self.assertEqual(patient.arrived_at, arrival)
        self.assertEqual(patient.triage_label, "Urgente")

    def test_arrival_defaults_to_now(self):
        before = datetime.now()
        patient = Patient("Ana", 1)
        after = datetime.now()
        self.assertIsInstance(patient.arrived_at, datetime)
        self.assertTrue(before <= patient.arrived_at <= after)

    def test_name_is_stripped(self):
        self.assertEqual(Patient("  Ana  ", 1).name, "Ana")

    # 12. Rechazar nombres vacíos
    def test_rejects_empty_or_blank_names(self):
        for bad_name in ("", "   ", "\t\n"):
            with self.subTest(name=bad_name):
                with self.assertRaises(InvalidPatientError):
                    Patient(bad_name, 1)

    def test_rejects_non_string_names(self):
        for bad_name in (None, 123, ["Ana"]):
            with self.subTest(name=bad_name):
                with self.assertRaises(InvalidPatientError):
                    Patient(bad_name, 1)

    # 11. Rechazar niveles de triaje incorrectos
    def test_rejects_invalid_triage_levels(self):
        for bad_level in (0, 4, -1, 2.0, "2", None, True, False):
            with self.subTest(level=bad_level):
                with self.assertRaises(InvalidPatientError):
                    Patient("Ana", bad_level)

    def test_accepts_all_valid_levels(self):
        for level in (1, 2, 3):
            with self.subTest(level=level):
                self.assertEqual(Patient("Ana", level).triage_level, level)

    def test_rejects_invalid_arrival(self):
        for bad_arrival in ("2026-11-17 09:30", None, date(2026, 11, 17), 0):
            with self.subTest(arrived_at=bad_arrival):
                with self.assertRaises(InvalidPatientError):
                    Patient("Ana", 1, bad_arrival)

    def test_patient_is_immutable(self):
        patient = Patient("Ana", 3)
        with self.assertRaises(AttributeError):
            patient.triage_level = 1

    def test_patients_are_not_orderable(self):
        # Garantiza que, si el heap llegara a comparar dos Patient, fallaría
        # de forma ruidosa: el contador debe evitar que ocurra.
        with self.assertRaises(TypeError):
            Patient("Ana", 1) < Patient("Luis", 1)  # noqa: B015

    def test_domain_errors_share_a_base_class(self):
        self.assertTrue(issubclass(InvalidPatientError, TriageQueueError))
        self.assertTrue(issubclass(InvalidPatientError, ValueError))
        self.assertTrue(issubclass(EmptyQueueError, TriageQueueError))


class TriageQueueTests(unittest.TestCase):
    """Comportamiento funcional de la cola (un solo hilo)."""

    def setUp(self):
        self.queue = TriageQueue()

    def enqueue_all(self, *specs):
        for name, level in specs:
            self.queue.enqueue(Patient(name, level))

    # 1. Encolar un paciente
    def test_enqueue_single_patient(self):
        patient = Patient("Ana", 2)
        self.queue.enqueue(patient)
        self.assertEqual(len(self.queue), 1)
        self.assertIs(self.queue.peek(), patient)

    # 2. Encolar pacientes con prioridades diferentes (escenario A)
    def test_different_priorities_are_served_by_level(self):
        self.enqueue_all(("Ana", 3), ("Carlos", 2), ("Marta", 1))
        self.assertEqual(drain(self.queue), ["Marta", "Carlos", "Ana"])

    # 3. Respetar FIFO en niveles iguales (escenario C)
    def test_same_level_is_fifo(self):
        self.enqueue_all(("P1", 2), ("P2", 2), ("P3", 2))
        self.assertEqual(drain(self.queue), ["P1", "P2", "P3"])

    def test_fifo_is_kept_inside_each_level_when_interleaved(self):
        self.enqueue_all(
            ("A3", 3), ("B2", 2), ("C3", 3), ("D1", 1), ("E2", 2), ("F1", 1)
        )
        self.assertEqual(drain(self.queue), ["D1", "F1", "B2", "E2", "A3", "C3"])

    # 4. Paciente crítico después de otros (escenario B)
    def test_late_critical_patient_goes_first(self):
        self.enqueue_all(("Luis", 2), ("Eva", 2), ("Pablo", 3))
        self.queue.enqueue(Patient("Sofía", 1))
        self.assertEqual(self.queue.peek().name, "Sofía")
        self.assertEqual(
            names(self.queue.list_queue()), ["Sofía", "Luis", "Eva", "Pablo"]
        )

    # 5. Extraer correctamente el siguiente paciente
    def test_dequeue_returns_and_removes_next_patient(self):
        self.enqueue_all(("Ana", 2), ("Marta", 1))
        self.assertEqual(self.queue.dequeue().name, "Marta")
        self.assertEqual(len(self.queue), 1)
        self.assertEqual(self.queue.dequeue().name, "Ana")
        self.assertEqual(len(self.queue), 0)

    # 6. Consultar el siguiente sin eliminarlo
    def test_peek_does_not_remove(self):
        self.enqueue_all(("Ana", 2), ("Marta", 1))
        self.assertEqual(self.queue.peek().name, "Marta")
        self.assertEqual(self.queue.peek().name, "Marta")
        self.assertEqual(len(self.queue), 2)

    # 7. Listar la cola completa
    def test_list_queue_returns_attention_order(self):
        self.enqueue_all(("Ana", 3), ("Luis", 2), ("Marta", 1), ("Eva", 2))
        self.assertEqual(
            names(self.queue.list_queue()), ["Marta", "Luis", "Eva", "Ana"]
        )

    def test_list_queue_of_empty_queue_is_empty_list(self):
        self.assertEqual(self.queue.list_queue(), [])

    # 8. Estadísticas
    def test_stats_counts_every_level(self):
        self.enqueue_all(
            ("a", 1), ("b", 1), ("c", 2), ("d", 2), ("e", 2), ("f", 3)
        )
        self.assertEqual(self.queue.stats(), {1: 2, 2: 3, 3: 1})

    def test_stats_always_include_three_levels(self):
        self.assertEqual(self.queue.stats(), {1: 0, 2: 0, 3: 0})
        self.enqueue_all(("Ana", 2))
        self.assertEqual(self.queue.stats(), {1: 0, 2: 1, 3: 0})

    # 9. Estadísticas después de desencolar (escenario E)
    def test_stats_after_dequeue(self):
        self.enqueue_all(("a", 1), ("b", 2), ("c", 2))
        self.queue.dequeue()
        self.assertEqual(self.queue.stats(), {1: 0, 2: 2, 3: 0})
        self.queue.dequeue()
        self.queue.dequeue()
        self.assertEqual(self.queue.stats(), {1: 0, 2: 0, 3: 0})

    # 10. Gestionar una cola vacía (escenario D)
    def test_empty_queue_raises_descriptive_errors(self):
        with self.assertRaisesRegex(EmptyQueueError, "No hay pacientes"):
            self.queue.dequeue()
        with self.assertRaisesRegex(EmptyQueueError, "No hay pacientes"):
            self.queue.peek()

    def test_queue_becomes_empty_again_after_draining(self):
        self.enqueue_all(("Ana", 1))
        self.queue.dequeue()
        with self.assertRaises(EmptyQueueError):
            self.queue.dequeue()

    # 13. Rechazar objetos incompatibles con Patient
    def test_enqueue_rejects_non_patients(self):
        for bad in ("Ana", None, 1, ("Ana", 1), {"name": "Ana", "level": 1}):
            with self.subTest(value=bad):
                with self.assertRaises(TypeError):
                    self.queue.enqueue(bad)
        self.assertEqual(len(self.queue), 0)

    # 14. Mismo timestamp exacto mantiene FIFO
    def test_identical_timestamps_keep_fifo(self):
        same_moment = datetime(2026, 11, 17, 20, 0, 0)
        for name in ("Primero", "Segundo", "Tercero"):
            self.queue.enqueue(Patient(name, 2, same_moment))
        self.assertEqual(drain(self.queue), ["Primero", "Segundo", "Tercero"])

    def test_insertion_order_beats_arrival_timestamp(self):
        # El contador manda: si se encola antes, se atiende antes, aunque su
        # marca temporal sea posterior (p. ej. reloj desajustado).
        self.queue.enqueue(Patient("Tarde", 2, datetime(2026, 11, 17, 21, 0)))
        self.queue.enqueue(Patient("Pronto", 2, datetime(2026, 11, 17, 20, 0)))
        self.assertEqual(drain(self.queue), ["Tarde", "Pronto"])

    def test_equal_patients_do_not_break_heap(self):
        # Dos pacientes idénticos en todo: el contador evita compararlos.
        moment = datetime(2026, 11, 17, 20, 0)
        first, second = Patient("Ana", 1, moment), Patient("Ana", 1, moment)
        self.queue.enqueue(first)
        self.queue.enqueue(second)
        self.assertIs(self.queue.dequeue(), first)
        self.assertIs(self.queue.dequeue(), second)

    # 15. Las lecturas no alteran la cola
    def test_read_operations_do_not_modify_queue(self):
        self.enqueue_all(("Ana", 3), ("Luis", 2), ("Marta", 1), ("Eva", 2))
        internal_before = list(self.queue._heap)

        self.queue.peek()
        listed = self.queue.list_queue()
        self.queue.stats()
        len(self.queue)

        self.assertEqual(self.queue._heap, internal_before)
        listed.clear()  # modificar la lista devuelta no afecta a la cola
        self.assertEqual(len(self.queue), 4)
        self.assertEqual(drain(self.queue), ["Marta", "Luis", "Eva", "Ana"])

    def test_large_mixed_workload_matches_reference_order(self):
        # Comparación con un orden de referencia calculado de forma independiente.
        specs = [(f"P{i}", (i * 7) % 3 + 1) for i in range(300)]
        for name, level in specs:
            self.queue.enqueue(Patient(name, level))
        expected = [
            name for name, _ in sorted(specs, key=lambda spec: spec[1])
        ]  # sorted es estable: conserva el orden de llegada en empates
        self.assertEqual(names(self.queue.list_queue()), expected)
        self.assertEqual(drain(self.queue), expected)


class ConcurrencyTests(unittest.TestCase):
    """Uso simultáneo desde varios hilos.

    Se reduce el intervalo de cambio de hilo del intérprete para provocar el
    máximo de entrelazados posibles. Estas pruebas no pueden demostrar la
    ausencia de condiciones de carrera (eso requiere razonamiento sobre el
    código); verifican que, bajo fuerte contención, no aparecen síntomas.
    """

    THREADS = 8
    PER_THREAD = 500

    def setUp(self):
        self._old_interval = sys.getswitchinterval()
        sys.setswitchinterval(1e-6)
        self.queue = TriageQueue()

    def tearDown(self):
        sys.setswitchinterval(self._old_interval)

    def run_threads(self, target, count):
        barrier = threading.Barrier(count)
        errors = []

        def wrapper(index):
            try:
                barrier.wait()
                target(index)
            except Exception as exc:  # registrar fallos de cualquier hilo
                errors.append(exc)

        threads = [
            threading.Thread(target=wrapper, args=(i,)) for i in range(count)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)
            self.assertFalse(thread.is_alive(), "un hilo no terminó")
        self.assertEqual(errors, [])

    def producer(self, index):
        for i in range(self.PER_THREAD):
            level = (index + i) % 3 + 1
            self.queue.enqueue(Patient(f"T{index}-{i}", level))

    def test_concurrent_enqueues_lose_nothing_and_keep_order(self):
        self.run_threads(self.producer, self.THREADS)
        total = self.THREADS * self.PER_THREAD

        self.assertEqual(len(self.queue), total)
        self.assertEqual(sum(self.queue.stats().values()), total)
        # Secuencias únicas y consecutivas: el contador no se repitió.
        sequences = sorted(seq for _, seq, _ in self.queue._heap)
        self.assertEqual(sequences, list(range(total)))

        listed = self.queue.list_queue()
        self.assertEqual(len({p.name for p in listed}), total)
        # Orden global por nivel; dentro de cada nivel, cada hilo conserva
        # el orden en que encoló a sus pacientes.
        levels = [p.triage_level for p in listed]
        self.assertEqual(levels, sorted(levels))
        last_seen = {}
        for patient in listed:
            thread_id, i = patient.name[1:].split("-")
            key = (patient.triage_level, thread_id)
            self.assertLess(last_seen.get(key, -1), int(i))
            last_seen[key] = int(i)

    def test_concurrent_dequeues_never_duplicate_or_lose(self):
        total = self.THREADS * self.PER_THREAD
        for i in range(total):
            self.queue.enqueue(Patient(f"P{i}", i % 3 + 1))
        results = [[] for _ in range(self.THREADS)]

        def consumer(index):
            while True:
                try:
                    results[index].append(self.queue.dequeue())
                except EmptyQueueError:
                    return

        self.run_threads(consumer, self.THREADS)
        served = [p.name for chunk in results for p in chunk]

        self.assertEqual(len(served), total)                  # nada perdido
        self.assertEqual(len(set(served)), total)             # nada duplicado
        self.assertEqual(set(served), {f"P{i}" for i in range(total)})
        self.assertEqual(len(self.queue), 0)
        self.assertEqual(self.queue.stats(), {1: 0, 2: 0, 3: 0})
        # Cada hilo extrae en orden de prioridad no decreciente.
        for chunk in results:
            chunk_levels = [p.triage_level for p in chunk]
            self.assertEqual(chunk_levels, sorted(chunk_levels))

    def test_mixed_producers_consumers_and_readers(self):
        producers = 4
        expected_total = producers * self.PER_THREAD
        served = []
        served_lock = threading.Lock()
        producers_done = threading.Event()
        inconsistent_stats = []

        def worker(index):
            if index < producers:
                self.producer(index)
            elif index < producers + 3:
                while True:
                    try:
                        patient = self.queue.dequeue()
                    except EmptyQueueError:
                        if producers_done.is_set() and len(self.queue) == 0:
                            return
                        continue
                    with served_lock:
                        served.append(patient.name)
            else:
                # Lector: cada instantánea debe ser coherente consigo misma.
                while not producers_done.is_set() or len(self.queue):
                    stats = self.queue.stats()
                    if set(stats) != {1, 2, 3} or min(stats.values()) < 0:
                        inconsistent_stats.append(stats)
                    snapshot = self.queue.list_queue()
                    levels = [p.triage_level for p in snapshot]
                    if levels != sorted(levels):
                        inconsistent_stats.append(levels)

        def watcher():
            for thread in producer_threads:
                thread.join()
            producers_done.set()

        barrier = threading.Barrier(producers + 4)
        errors = []

        def wrapper(index):
            try:
                barrier.wait()
                worker(index)
            except Exception as exc:
                errors.append(exc)

        all_threads = [
            threading.Thread(target=wrapper, args=(i,))
            for i in range(producers + 4)
        ]
        producer_threads = all_threads[:producers]
        for thread in all_threads:
            thread.start()
        watch = threading.Thread(target=watcher)
        watch.start()
        for thread in all_threads + [watch]:
            thread.join(timeout=60)
            self.assertFalse(thread.is_alive(), "un hilo no terminó")

        self.assertEqual(errors, [])
        self.assertEqual(inconsistent_stats, [])
        self.assertEqual(len(served), expected_total)
        self.assertEqual(len(set(served)), expected_total)
        self.assertEqual(len(self.queue), 0)


class CliTests(unittest.TestCase):
    """Sesiones de menú simuladas: entradas predefinidas, salida capturada."""

    def run_session(self, *inputs, queue=None):
        pending = list(inputs)
        output = []

        def fake_input(prompt):
            output.append(prompt)
            if not pending:
                raise EOFError  # como si el usuario cerrara la entrada
            return pending.pop(0)

        queue = TriageQueue() if queue is None else queue
        triage_queue.main(queue, input_fn=fake_input, output_fn=output.append)
        return queue, "\n".join(output)

    def test_full_happy_path(self):
        queue, out = self.run_session(
            "1", "Ana", "3",
            "1", "Marta", "1",
            "3",
            "4",
            "5",
            "2",
            "6",
        )
        self.assertIn("Paciente registrado: Ana | Nivel 3 (No urgente)", out)
        self.assertIn("Siguiente en la cola: Marta | Nivel 1 (Crítico)", out)
        self.assertIn("1. Marta", out)
        self.assertIn("2. Ana", out)
        self.assertIn("Nivel 1 (Crítico): 1", out)
        self.assertIn("Pase a consulta: Marta", out)
        self.assertIn("Saliendo de Triage Queue", out)
        self.assertEqual(names(queue.list_queue()), ["Ana"])

    def test_shows_arrival_time(self):
        _, out = self.run_session("1", "Ana", "2", "6")
        self.assertRegex(out, r"Llegada: \d{2}/\d{2}/\d{4} \d{2}:\d{2}:\d{2}")

    def test_invalid_inputs_do_not_stop_the_program(self):
        queue, out = self.run_session(
            "1", "   ",            # nombre vacío
            "1", "Ana", "dos",     # nivel no numérico
            "1", "Ana", "7",       # nivel fuera de rango
            "1", "Ana", "0",
            "9",                   # opción inexistente
            "",                    # opción vacía
            "1", "Ana", "2",       # entrada correcta tras los errores
            "6",
        )
        self.assertIn("no puede estar vacío", out)
        self.assertIn("«dos» no es un número", out)
        self.assertIn("debe estar entre 1 y 3; se recibió 7", out)
        self.assertIn("se recibió 0", out)
        self.assertIn("Opción no válida: «9»", out)
        self.assertIn("Opción no válida: «»", out)
        self.assertEqual(len(queue), 1)  # solo el registro válido

    def test_ignores_invisible_bom_in_input(self):
        queue, out = self.run_session("\ufeff1", "\ufeffAna", "\ufeff2", "6")
        self.assertNotIn("Opción no válida", out)
        self.assertEqual(names(queue.list_queue()), ["Ana"])

    def test_empty_queue_messages(self):
        _, out = self.run_session("2", "3", "4", "5", "6")
        self.assertEqual(out.count("La cola está vacía"), 3)
        self.assertIn("Total: 0", out)

    def test_end_of_input_exits_cleanly(self):
        _, out = self.run_session("1", "Ana")  # EOF a mitad de un alta
        self.assertIn("Saliendo de Triage Queue", out)

    def test_keyboard_interrupt_exits_cleanly(self):
        def interrupted(prompt):
            raise KeyboardInterrupt

        output = []
        triage_queue.main(TriageQueue(), input_fn=interrupted,
                          output_fn=output.append)
        self.assertIn("Saliendo de Triage Queue", "\n".join(output))


if __name__ == "__main__":
    unittest.main()
