# Triage Queue — Gestor de Cola de Prioridad

Gestor de pacientes en espera para un servicio de urgencias, escrito en Python con solo la biblioteca estándar. Los pacientes se atienden por **nivel de triaje** (1 = crítico, 2 = urgente, 3 = no urgente) y, dentro de cada nivel, **por orden de llegada**.

Práctica del itinerario *AI Engineering* de 4Geeks Academy.

> ⚠️ Proyecto educativo. No es un sistema clínico ni es apto para uso hospitalario real.

## 1. Problema que resuelve

En urgencias, quien llega antes no siempre pasa antes: un paciente crítico que acaba de entrar debe atenderse delante de uno leve que lleva una hora esperando. Una cola normal (FIFO) no sirve para esto.

Triage Queue mantiene una **cola de prioridad**:

- **Prioridad clínica**: el nivel 1 siempre va antes que el 2, y el 2 antes que el 3.
- **Justicia dentro del nivel**: entre pacientes del mismo nivel, pasa antes quien llegó antes (FIFO), incluso si se registraron en el mismo instante.
- **Llegada de un crítico**: se coloca automáticamente al principio de la cola.

## 2. Funcionalidades

| Operación      | Qué hace                                                       | Coste      |
|----------------|----------------------------------------------------------------|------------|
| `enqueue`      | Añade un paciente en la posición que le corresponde            | O(log n)   |
| `dequeue`      | Extrae y devuelve el siguiente paciente que se atenderá        | O(log n)   |
| `peek`         | Muestra el siguiente paciente sin retirarlo                    | O(1)       |
| `list_queue`   | Lista los pacientes en el orden real de atención, sin modificar la cola | O(n log n) |
| `stats`        | Pacientes pendientes por nivel, por ejemplo `{1: 2, 2: 3, 3: 1}` | O(n)     |

Además:

- **Validación** del nombre (no vacío), del nivel (entero 1–3, sin admitir `True`/`False`) y de la fecha de llegada (`datetime`, que se asigna automáticamente si no se indica).
- **Excepciones específicas**: `InvalidPatientError` y `EmptyQueueError`, ambas derivadas de `TriageQueueError`.
- **Segura entre hilos**: un `threading.Lock` protege todas las operaciones (véase [DESIGN.md](DESIGN.md)).
- **CLI robusta**: se recupera de cualquier entrada incorrecta y sale limpiamente con la opción 6, `Ctrl+C` o el fin de la entrada.

## 3. Requisitos

- Python 3 (usa `dataclasses`, disponible desde 3.7). **Verificado únicamente con Python 3.14.6** en Windows 11.
- Sin dependencias externas: no hay `requirements.txt` ni hace falta `pip install`.

## 4. Preparación del entorno

```bash
git clone https://github.com/rubenlosada11/triage-queue.git
cd triage-queue
python --version   # comprobar que es Python 3
```

No hace falta un entorno virtual, porque no se instala nada. Si se prefiere usar uno por costumbre:

```bash
python -m venv .venv
# Windows:      .venv\Scripts\activate
# Linux/macOS:  source .venv/bin/activate
```

## 5. Cómo ejecutar el programa

```bash
python triage_queue.py
```

```text
========================================
  TRIAGE QUEUE - Urgencias
========================================
  1. Añadir paciente
  2. Llamar al siguiente paciente
  3. Consultar el siguiente (sin retirarlo)
  4. Mostrar la cola completa
  5. Mostrar estadísticas por nivel
  6. Salir
----------------------------------------
Elige una opción (1-6):
```

## 6. Ejemplo de utilización

Llegan, en este orden, Lucía (nivel 2), Pedro (nivel 2) y Sofía (nivel 1). Al mostrar la cola (opción 4):

```text
Pacientes en espera (3), en orden de atención:
    1. Sofía | Nivel 1 (Crítico) | Llegada: 17/11/2026 20:18:20
    2. Lucía | Nivel 2 (Urgente) | Llegada: 17/11/2026 20:18:20
    3. Pedro | Nivel 2 (Urgente) | Llegada: 17/11/2026 20:18:20
```

Sofía llegó la última, pero es crítica y pasa la primera. Lucía y Pedro tienen el mismo nivel y la misma hora mostrada, y aun así conservan su orden de llegada.

Las entradas incorrectas no detienen el programa:

```text
Elige una opción (1-6): 9
Opción no válida: «9». Elige un número del 1 al 6.
...
Nivel de triaje (1=Crítico, 2=Urgente, 3=No urgente): dos
Dato no válido: «dos» no es un número. Introduce 1, 2 o 3. El paciente no se ha registrado.
...
Elige una opción (1-6): 2
La cola está vacía. No hay pacientes en espera.
```

### Uso como biblioteca

Gracias a `if __name__ == "__main__":`, el módulo se puede importar sin que se abra el menú:

```python
from triage_queue import Patient, TriageQueue

queue = TriageQueue()
queue.enqueue(Patient("Ana", 3))
queue.enqueue(Patient("Carlos", 2))
queue.enqueue(Patient("Marta", 1))

queue.peek().name                       # 'Marta'
[p.name for p in queue.list_queue()]    # ['Marta', 'Carlos', 'Ana']
queue.stats()                           # {1: 1, 2: 1, 3: 1}
queue.dequeue().name                    # 'Marta'
```

## 7. Cómo ejecutar las pruebas

Desde la raíz del proyecto:

```bash
python -m unittest discover -s tests -v
```

Hay 41 pruebas `unittest`:

- **Modelo**: validación de nombre, nivel (incluido `bool`) y fecha; inmutabilidad.
- **Cola**: prioridad, FIFO, crítico tardío, timestamps idénticos, cola vacía, estadísticas y lecturas que no modifican la cola.
- **Concurrencia**: inserciones, extracciones y lecturas simultáneas con 8 hilos, sin pérdidas ni duplicados.
- **CLI**: sesiones simuladas con entradas inválidas, cola vacía y salida limpia.

## 8. Estructura del proyecto

```text
triage-queue/
├── triage_queue.py            # Modelo (Patient), cola (TriageQueue), excepciones y CLI
├── tests/
│   └── test_triage_queue.py   # Pruebas unittest
├── DESIGN.md                  # Decisiones técnicas, complejidad y concurrencia
├── README.md                  # Este documento
└── .gitignore
```

`triage_queue.py` está organizado en capas independientes:

1. **Modelo**: `Patient`, una dataclass inmutable que se valida al crearse.
2. **Lógica de prioridad**: `TriageQueue`, un min-heap con `heapq` y un contador secuencial, protegido por un `Lock`.
3. **Presentación**: `format_patient` y las acciones del menú. No contiene lógica de ordenación.
4. **Control**: `main`, el bucle del menú y la gestión de errores.

Para entender **por qué** se diseñó así (heap frente a otras estructuras, contador frente a timestamp, estrategia de bloqueo y limitaciones), consulta [DESIGN.md](DESIGN.md).
