"""Triage Queue — gestor de cola de prioridad para un servicio de urgencias.

El módulo se organiza en tres capas independientes:

1. Modelo de datos: ``Patient`` y sus funciones de validación.
2. Lógica de prioridad: ``TriageQueue``, un min-heap (``heapq``) protegido
   por un ``threading.Lock``.
3. Interfaz de terminal (CLI): funciones de presentación y el menú ``main``.

Solo utiliza la biblioteca estándar de Python.

Aviso: es un ejercicio educativo, no un sistema clínico apto para producción.
"""

import heapq
import threading
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime

# ---------------------------------------------------------------------------
# Constantes del dominio
# ---------------------------------------------------------------------------

MIN_TRIAGE_LEVEL = 1
MAX_TRIAGE_LEVEL = 3
TRIAGE_LEVELS = tuple(range(MIN_TRIAGE_LEVEL, MAX_TRIAGE_LEVEL + 1))

# Etiqueta legible de cada nivel. Un número menor significa mayor prioridad.
TRIAGE_LABELS = {
    1: "Crítico",
    2: "Urgente",
    3: "No urgente",
}


# ---------------------------------------------------------------------------
# Excepciones del dominio
# ---------------------------------------------------------------------------


class TriageQueueError(Exception):
    """Clase base de todos los errores propios de este módulo."""


class InvalidPatientError(TriageQueueError, ValueError):
    """Los datos de un paciente no son válidos (nombre, nivel o llegada)."""


class EmptyQueueError(TriageQueueError, LookupError):
    """Se ha intentado consultar o extraer un paciente de una cola vacía."""


# ---------------------------------------------------------------------------
# Validación (compartida por el modelo y por la CLI, sin duplicar reglas)
# ---------------------------------------------------------------------------


def normalize_name(name):
    """Devuelve el nombre sin espacios sobrantes o lanza InvalidPatientError."""
    if not isinstance(name, str):
        raise InvalidPatientError(
            f"El nombre debe ser un texto, no {type(name).__name__}."
        )
    cleaned = name.strip()
    if not cleaned:
        raise InvalidPatientError("El nombre del paciente no puede estar vacío.")
    return cleaned


def validate_triage_level(level):
    """Devuelve el nivel si es un entero entre 1 y 3; si no, lanza un error.

    ``bool`` es una subclase de ``int`` en Python (``True == 1``), así que se
    rechaza explícitamente para que ``True`` no se cuele como nivel 1.
    """
    if isinstance(level, bool) or not isinstance(level, int):
        raise InvalidPatientError(
            f"El nivel de triaje debe ser un número entero entre "
            f"{MIN_TRIAGE_LEVEL} y {MAX_TRIAGE_LEVEL}; "
            f"se recibió {level!r} ({type(level).__name__})."
        )
    if not MIN_TRIAGE_LEVEL <= level <= MAX_TRIAGE_LEVEL:
        raise InvalidPatientError(
            f"El nivel de triaje debe estar entre {MIN_TRIAGE_LEVEL} y "
            f"{MAX_TRIAGE_LEVEL}; se recibió {level}."
        )
    return level


def validate_arrival(arrived_at):
    """Devuelve la fecha de llegada si es un ``datetime``; si no, lanza un error.

    Se exige ``datetime`` (fecha y hora). Un ``date`` sin hora se rechaza.
    """
    if not isinstance(arrived_at, datetime):
        raise InvalidPatientError(
            "La fecha de llegada debe ser un objeto datetime; "
            f"se recibió {type(arrived_at).__name__}."
        )
    return arrived_at


# ---------------------------------------------------------------------------
# Modelo de datos
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Patient:
    """Paciente en espera.

    ``frozen=True`` hace el objeto inmutable: una vez dentro de la cola, nadie
    puede cambiarle el nivel y romper el orden interno del heap.

    No se define orden (``order=False`` por defecto), así que comparar dos
    pacientes con ``<`` lanza ``TypeError``. La cola nunca lo necesita.
    """

    name: str
    triage_level: int
    arrived_at: datetime = field(default_factory=datetime.now)

    def __post_init__(self):
        # En una dataclass congelada hay que usar object.__setattr__ para
        # guardar el valor normalizado durante la construcción.
        object.__setattr__(self, "name", normalize_name(self.name))
        validate_triage_level(self.triage_level)
        validate_arrival(self.arrived_at)

    @property
    def triage_label(self):
        """Etiqueta legible del nivel, por ejemplo «Crítico»."""
        return TRIAGE_LABELS[self.triage_level]


# ---------------------------------------------------------------------------
# Cola de prioridad
# ---------------------------------------------------------------------------


class TriageQueue:
    """Cola de prioridad de pacientes: primero el nivel más bajo y, dentro
    del mismo nivel, estricto orden de llegada (FIFO).

    Internamente es un min-heap de tuplas ``(triage_level, arrival_sequence,
    patient)``. ``arrival_sequence`` es un contador que crece en cada
    inserción y que:

    * garantiza FIFO incluso si dos pacientes tienen el mismo ``arrived_at``;
    * es único, por lo que Python nunca necesita comparar objetos ``Patient``.

    Todas las operaciones públicas comparten un único ``threading.Lock``, de
    modo que la cola puede usarse desde varios hilos sin corromper el heap,
    duplicar ni perder pacientes.
    """

    def __init__(self):
        self._heap = []
        self._next_sequence = 0
        self._lock = threading.Lock()

    def enqueue(self, patient):
        """Añade un paciente respetando su prioridad. Coste: O(log n)."""
        if not isinstance(patient, Patient):
            raise TypeError(
                "Solo se pueden encolar objetos Patient; "
                f"se recibió {type(patient).__name__}."
            )
        with self._lock:
            # Leer, usar e incrementar el contador debe ser atómico: si dos
            # hilos leyeran el mismo valor, el desempate FIFO dejaría de ser
            # único y Python intentaría comparar dos Patient.
            entry = (patient.triage_level, self._next_sequence, patient)
            self._next_sequence += 1
            heapq.heappush(self._heap, entry)

    def dequeue(self):
        """Extrae y devuelve el paciente más prioritario. Coste: O(log n).

        La comprobación de cola vacía y la extracción ocurren dentro del mismo
        bloqueo: dos hilos nunca pueden obtener el mismo paciente.
        """
        with self._lock:
            if not self._heap:
                raise EmptyQueueError("No hay pacientes en espera.")
            _, _, patient = heapq.heappop(self._heap)
        return patient

    def peek(self):
        """Devuelve el siguiente paciente sin retirarlo. Coste: O(1)."""
        with self._lock:
            if not self._heap:
                raise EmptyQueueError("No hay pacientes en espera.")
            _, _, patient = self._heap[0]
        return patient

    def list_queue(self):
        """Devuelve los pacientes pendientes en orden real de atención.

        Copia el heap dentro del bloqueo (O(n)) y ordena la copia fuera de él
        (O(n log n)). La cola original no se modifica.
        """
        with self._lock:
            snapshot = list(self._heap)
        snapshot.sort()  # las secuencias son únicas: nunca compara Patient
        return [patient for _, _, patient in snapshot]

    def stats(self):
        """Devuelve ``{nivel: pacientes pendientes}`` con los tres niveles
        siempre presentes. Coste: O(n)."""
        with self._lock:
            counts = Counter(level for level, _, _ in self._heap)
        return {level: counts.get(level, 0) for level in TRIAGE_LEVELS}

    def __len__(self):
        with self._lock:
            return len(self._heap)


# ---------------------------------------------------------------------------
# Interfaz de terminal (CLI)
#
# Solo traduce texto <-> objetos del dominio. No contiene lógica de prioridad:
# toda decisión de orden la toma TriageQueue.
# ---------------------------------------------------------------------------

DATETIME_FORMAT = "%d/%m/%Y %H:%M:%S"
EMPTY_QUEUE_MESSAGE = "La cola está vacía. No hay pacientes en espera."
GOODBYE_MESSAGE = "Saliendo de Triage Queue. Hasta pronto."

MENU = """
========================================
  TRIAGE QUEUE - Urgencias
========================================
  1. Añadir paciente
  2. Llamar al siguiente paciente
  3. Consultar el siguiente (sin retirarlo)
  4. Mostrar la cola completa
  5. Mostrar estadísticas por nivel
  6. Salir
----------------------------------------"""


def format_patient(patient):
    """Representación de una línea: nombre, nivel y hora de llegada."""
    return (
        f"{patient.name} | Nivel {patient.triage_level} "
        f"({patient.triage_label}) | "
        f"Llegada: {patient.arrived_at.strftime(DATETIME_FORMAT)}"
    )


def parse_triage_level(text):
    """Convierte la entrada del usuario en un nivel válido o lanza un error."""
    try:
        level = int(text.strip())
    except ValueError:
        raise InvalidPatientError(
            f"«{text.strip()}» no es un número. Introduce "
            f"{', '.join(map(str, TRIAGE_LEVELS[:-1]))} o {TRIAGE_LEVELS[-1]}."
        ) from None
    return validate_triage_level(level)


def _ask(input_fn, prompt):
    """Lee una línea y elimina espacios y el BOM invisible (U+FEFF) que
    algunas consolas, como Windows PowerShell 5.1, añaden al canalizar texto."""
    return input_fn(prompt).replace("\ufeff", "").strip()


def _add_patient(queue, input_fn, output_fn):
    name = normalize_name(_ask(input_fn, "Nombre del paciente: "))
    levels_help = ", ".join(f"{lvl}={TRIAGE_LABELS[lvl]}" for lvl in TRIAGE_LEVELS)
    level = parse_triage_level(_ask(input_fn, f"Nivel de triaje ({levels_help}): "))
    patient = Patient(name, level)
    queue.enqueue(patient)
    output_fn(f"Paciente registrado: {format_patient(patient)}")


def _call_next(queue, input_fn, output_fn):
    patient = queue.dequeue()
    output_fn(f"Pase a consulta: {format_patient(patient)}")


def _show_next(queue, input_fn, output_fn):
    output_fn(f"Siguiente en la cola: {format_patient(queue.peek())}")


def _show_queue(queue, input_fn, output_fn):
    patients = queue.list_queue()
    if not patients:
        output_fn(EMPTY_QUEUE_MESSAGE)
        return
    output_fn(f"Pacientes en espera ({len(patients)}), en orden de atención:")
    for position, patient in enumerate(patients, start=1):
        output_fn(f"  {position:>3}. {format_patient(patient)}")


def _show_stats(queue, input_fn, output_fn):
    stats = queue.stats()
    output_fn("Pacientes en espera por nivel:")
    for level, count in stats.items():
        output_fn(f"  Nivel {level} ({TRIAGE_LABELS[level]}): {count}")
    output_fn(f"  Total: {sum(stats.values())}")


MENU_ACTIONS = {
    "1": _add_patient,
    "2": _call_next,
    "3": _show_next,
    "4": _show_queue,
    "5": _show_stats,
}
EXIT_OPTION = "6"


def main(queue=None, input_fn=input, output_fn=print):
    """Bucle del menú. ``input_fn`` y ``output_fn`` se pueden sustituir en
    las pruebas para simular una sesión sin teclado."""
    queue = TriageQueue() if queue is None else queue
    while True:
        output_fn(MENU)
        try:
            option = _ask(input_fn, "Elige una opción (1-6): ")
            if option == EXIT_OPTION:
                output_fn(GOODBYE_MESSAGE)
                return
            action = MENU_ACTIONS.get(option)
            if action is None:
                output_fn(f"Opción no válida: «{option}». Elige un número del 1 al 6.")
                continue
            action(queue, input_fn, output_fn)
        except EmptyQueueError:
            output_fn(EMPTY_QUEUE_MESSAGE)
        except InvalidPatientError as error:
            output_fn(f"Dato no válido: {error} El paciente no se ha registrado.")
        except (EOFError, KeyboardInterrupt):
            # Ctrl+D / Ctrl+Z / Ctrl+C o fin de la entrada: salida limpia.
            output_fn("\n" + GOODBYE_MESSAGE)
            return


if __name__ == "__main__":
    main()
