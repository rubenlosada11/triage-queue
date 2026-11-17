# DESIGN — Triage Queue

Decisiones técnicas del gestor de cola de prioridad: qué estructura de datos se usa, por qué, cuánto cuesta cada operación y cómo se protege la cola cuando varios hilos la usan a la vez.

> Proyecto educativo. No es un sistema clínico apto para producción.

---

## 1. El problema

En urgencias no se atiende por orden de llegada, sino por **gravedad**. Cada paciente recibe un nivel de triaje:

| Nivel | Etiqueta   | Significado                   |
|-------|------------|-------------------------------|
| 1     | Crítico    | Se atiende antes que nadie    |
| 2     | Urgente    | Después de todos los críticos |
| 3     | No urgente | Al final                      |

Dos reglas definen el orden de atención:

1. **Prioridad**: un nivel menor se atiende siempre antes.
2. **FIFO dentro del nivel** (*First In, First Out*: el primero en entrar es el primero en salir): entre dos pacientes del mismo nivel, pasa antes el que llegó antes.

Una estructura que cumple estas reglas se llama **cola de prioridad**. Una cola normal (FIFO) solo mira el orden de llegada. Una cola de prioridad mira primero la prioridad y usa el orden de llegada solo para desempatar.

---

## 2. ¿Qué es un heap binario?

Un **min-heap binario** es un árbol binario casi completo que cumple una sola regla:

> **Invariante del heap:** cada nodo es menor o igual que sus hijos.

De ahí sale una consecuencia muy útil: **el mínimo siempre está en la raíz**. En cambio, el heap **no** está ordenado del todo: hermanos y primos pueden estar en cualquier orden.

El árbol no se guarda con punteros, sino en una lista. El nodo de la posición `i` tiene sus hijos en `2i + 1` y `2i + 2`, y su padre en `(i - 1) // 2`.

```text
Lista:  [ (1,3,Marta), (2,0,Luis), (2,1,Eva), (3,2,Pablo) ]
índice:        0            1          2           3

Árbol:              (1,3,Marta)
                   /           \
           (2,0,Luis)        (2,1,Eva)
            /
     (3,2,Pablo)
```

Las dos operaciones básicas solo recorren **un camino** de la raíz a una hoja. Como la altura del árbol es `log₂ n`, ambas cuestan **O(log n)**:

- **Insertar (`heappush`)**: se añade el elemento al final y se hace *sift-up*, es decir, se intercambia con su padre mientras sea menor que él.
- **Extraer el mínimo (`heappop`)**: se saca la raíz, el último elemento pasa a ocupar su lugar y se hace *sift-down*: se intercambia con el menor de sus hijos mientras sea mayor que alguno.

### `heapq`

`heapq` es el módulo de la biblioteca estándar que implementa estas operaciones sobre una `list` normal de Python. No es una clase: son funciones (`heappush`, `heappop`) que mantienen el invariante en la lista que reciben. El heap es un **min-heap**, así que la convención «1 = más urgente» encaja directamente, sin invertir valores.

---

## 3. Prioridad con tuplas y el contador secuencial

Python compara las tuplas **elemento a elemento**, de izquierda a derecha, y solo pasa al siguiente si hay empate. Cada entrada del heap es:

```python
(triage_level, arrival_sequence, patient)
```

- `triage_level` decide primero: la prioridad clínica.
- `arrival_sequence` desempata dentro del mismo nivel. Es un entero que empieza en 0 y crece en 1 con **cada** inserción.
- `patient` es la carga útil. **Nunca llega a compararse.**

### ¿Por qué un contador y no `arrived_at`?

1. **Empates de marca temporal.** Dos pacientes registrados en el mismo instante, o con la misma resolución de reloj, tienen el mismo `datetime`. Si el desempate fuera `arrived_at`, el orden entre ellos no estaría definido y Python pasaría a comparar el tercer elemento.
2. **Comparar `Patient` está prohibido.** `Patient` no define orden (la dataclass no usa `order=True`), así que `patient_a < patient_b` lanza `TypeError`. Como cada número de secuencia es **único**, dos tuplas siempre se distinguen en el segundo elemento y el tercero no se compara nunca. Esto lo comprueba `test_equal_patients_do_not_break_heap`.
3. **El orden de inserción es la verdad del sistema.** Un reloj puede ajustarse (NTP, horario de verano) o venir de otra fuente. El contador refleja exactamente el orden en que la cola recibió a los pacientes (`test_insertion_order_beats_arrival_timestamp`).

`arrived_at` se conserva como **dato informativo** que se muestra en pantalla, pero no interviene en el orden.

---

## 4. Alternativas comparadas

Sea `n` el número de pacientes en espera y `k` el número de niveles (aquí `k = 3`).

| Estructura                      | Encolar                     | Desencolar                          | Peek             | Comentario |
|---------------------------------|-----------------------------|-------------------------------------|------------------|------------|
| **1. Una única `deque`**        | O(1) al final               | O(n): hay que buscar el más urgente | O(n)             | FIFO puro; la prioridad obliga a recorrerla entera. Si se inserta en su posición, encolar pasa a ser O(n). |
| **2. Lista ordenada**           | O(n) (`bisect.insort`: búsqueda O(log n) + desplazamiento O(n)) | O(1) si se ordena al revés y se usa `pop()` | O(1) | Listar es trivial (ya está ordenada), pero cada inserción mueve memoria. |
| **3. Tres `deque` (una por nivel)** | O(1)                    | O(k): mirar la primera cola no vacía | O(k)           | Con `k` fijo y pequeño es **asintóticamente la mejor** opción: O(1) efectivo. |
| **4. Heap (`heapq`)** ✅        | O(log n)                    | O(log n)                            | O(1)             | Una sola estructura y un solo invariante; la prioridad se expresa con una tupla. |

### ¿Por qué el heap, si tres `deque` son más rápidas?

Con exactamente tres niveles fijos, tres `deque` ganan en coste asintótico, y ocultarlo sería poco riguroso. El heap se elige por estas razones:

- **Es el requisito del ejercicio** y la estructura canónica de una cola de prioridad.
- **Generalidad**: la clave de prioridad es una tupla. Añadir niveles (el sistema Manchester usa 5) o criterios nuevos, como una puntuación de gravedad o el envejecimiento (*aging*) para que un nivel 3 no espere indefinidamente, solo cambia la tupla, no la estructura. Con colas por nivel, una prioridad continua no se puede representar.
- **Un único estado compartido**: una lista y un contador. Esto simplifica la sección crítica en concurrencia.
- La diferencia entre O(1) y O(log n) es irrelevante a escala de urgencias: con mil pacientes, log₂ 1000 ≈ 10 comparaciones.

---

## 5. Complejidad de las operaciones

| Operación      | Complejidad    | Cómo se consigue |
|----------------|----------------|------------------|
| `enqueue`      | **O(log n)**   | `heapq.heappush` (*sift-up*). Nunca se reordena la lista entera. |
| `dequeue`      | **O(log n)**   | `heapq.heappop` (*sift-down*). |
| `peek`         | **O(1)**       | El mínimo está siempre en `heap[0]`. |
| `list_queue`   | **O(n log n)** | Copia O(n) del heap y `sort()` de la copia O(n log n). El heap no está totalmente ordenado, así que no basta con devolverlo tal cual. |
| `stats`        | **O(n)**       | Un recorrido con `collections.Counter`. |
| `len(queue)`   | O(1)           | `len` de la lista. |

**Memoria:** O(n) para el heap. `list_queue` usa O(n) extra para la copia.

*Alternativa descartada para `stats`:* mantener un contador por nivel que se actualice en cada `enqueue` y `dequeue` daría O(1), pero añade un segundo estado que debe mantenerse sincronizado con el heap. Para el volumen de este problema, O(n) es suficiente y más difícil de romper.

---

## 6. Tratamiento de errores

Todas las excepciones propias heredan de `TriageQueueError`. Así, quien use la cola puede capturarlas todas juntas o una a una.

| Excepción              | Hereda también de | Cuándo se lanza |
|------------------------|-------------------|-----------------|
| `InvalidPatientError`  | `ValueError`      | Nombre vacío o que no es texto; nivel fuera de 1–3 o que no es `int` (incluidos `True`/`False`, `2.0` y `"2"`); `arrived_at` que no es `datetime`. |
| `EmptyQueueError`      | `LookupError`     | `dequeue()` o `peek()` sobre una cola vacía. |
| `TypeError` (estándar) | —                 | `enqueue()` recibe algo que no es un `Patient`. Es un error de programación, no un dato de usuario. |

Detalles:

- **`bool` se rechaza explícitamente.** En Python `True` es un `int` que vale 1 (`isinstance(True, int)` devuelve `True`), así que sin esta comprobación `Patient("Ana", True)` se colaría como nivel 1.
- **Validación en el constructor** (`__post_init__`): no puede existir un `Patient` inválido, y por eso la cola solo tiene que comprobar el tipo.
- **`Patient` es inmutable** (`frozen=True`). Si se pudiera cambiar `triage_level` de un paciente que ya está en el heap, el invariante se rompería sin que nadie se enterase.
- **Las reglas de validación están en un solo sitio** (`normalize_name`, `validate_triage_level`). La CLI las reutiliza en lugar de duplicarlas.
- **La CLI** traduce las excepciones a mensajes comprensibles y vuelve al menú. Además, cierra limpiamente ante `Ctrl+C` o el fin de la entrada (`EOFError`).

---

## 7. Concurrencia

### 7.1. El problema

`heapq` **no es thread-safe** (seguro para varios hilos). Sus funciones modifican una lista compartida en varios pasos, y nada impide que otro hilo intervenga entre medias. Además, varias operaciones de la cola son **compuestas**:

- `dequeue`: «¿está vacía?» → «extrae la raíz».
- `enqueue`: «lee el contador» → «incrementa» → «inserta».

El **GIL** (*Global Interpreter Lock*) de CPython solo garantiza que no se ejecutan dos instrucciones de bytecode a la vez. **No** convierte una secuencia de pasos en una operación atómica. Además, existen builds de Python sin GIL (*free-threaded*, desde 3.13).

### 7.2. Escenario obligatorio: un worker extrae mientras otro encola un crítico

Un *worker* es un hilo que realiza trabajo, en este caso atender o registrar pacientes. **Sin bloqueo**, un entrelazado posible es:

```text
Worker A (dequeue)                     Worker B (enqueue crítico)
-------------------------------------  -------------------------------------
lee heap[0] -> Luis (nivel 2)
                                       heappush((1, 7, Sofía)) -> sift-up,
                                       Sofía pasa a heap[0]
heappop() -> extrae a Sofía
devuelve Luis  (¡pero ha sacado a Sofía!)
```

Resultado: Luis se atiende y **sigue en la cola** (se atenderá dos veces), y Sofía, la paciente crítica, **desaparece**. Otros entrelazados posibles:

- **Doble procesamiento**: dos workers comprueban «no está vacía», los dos leen la misma raíz y los dos atienden al mismo paciente.
- **Pérdida y `IndexError`**: dos workers ven un único paciente; uno lo extrae y el otro falla con una lista vacía.
- **Contador repetido**: dos `enqueue` leen el mismo `arrival_sequence`. El desempate deja de ser único, el FIFO se rompe y, si los niveles coinciden, Python intenta comparar dos `Patient` → `TypeError` a mitad de un *sift-up*, con el heap a medio reorganizar (**estado corrupto**).
- **Lecturas inconsistentes**: `list_queue` o `stats` recorren la lista mientras otro hilo la reorganiza y ven pacientes duplicados o ausentes.

### 7.3. Solución: un único `threading.Lock`

Una **sección crítica** es un fragmento de código que solo puede ejecutar un hilo a la vez. `TriageQueue` tiene un `threading.Lock` y **todas** las operaciones que leen o modifican `_heap` o `_next_sequence` entran en él con `with self._lock:`.

| Riesgo                  | Cómo se evita |
|-------------------------|---------------|
| Doble procesamiento     | `dequeue` comprueba si hay pacientes **y** hace `heappop` dentro del mismo bloqueo: la extracción es atómica. |
| Corrupción del heap     | Ningún `heappush`/`heappop` puede solaparse con otro. |
| Contador repetido       | Leer, usar e incrementar `_next_sequence` ocurre dentro del bloqueo. |
| Lecturas inconsistentes | `peek`, `list_queue`, `stats` y `len` leen bajo el mismo bloqueo, así que ven siempre un estado completo. |
| Pérdida de pacientes    | Consecuencia de todo lo anterior: cada `enqueue` aparece exactamente una vez en las extracciones. |

En el escenario de 7.2, con el bloqueo solo hay dos órdenes posibles, y los dos son correctos:

- B entra primero → Sofía está en la raíz → A atiende a Sofía.
- A entra primero → A atiende a Luis → B inserta a Sofía, que será la siguiente.

**Criterios aplicados:**

- **Un solo bloqueo común**: hay un único estado compartido (lista y contador). Con varios bloqueos habría riesgo de *deadlock* (bloqueo mutuo) sin ganar nada.
- **Sección crítica mínima**:
  - la validación `isinstance` de `enqueue` se hace **antes** de entrar;
  - `list_queue` solo copia la lista dentro del bloqueo (O(n)) y la ordena **fuera** (O(n log n));
  - el formateo y los `print` de la CLI ocurren siempre fuera.
- **Sin E/S dentro del bloqueo**: `TriageQueue` no lee de teclado ni escribe en pantalla.
- **Devolver referencias es seguro** porque `Patient` es inmutable.
- `Lock` y no `RLock`: ningún método vuelve a pedir el bloqueo que ya tiene, así que no hace falta reentrada.

### 7.4. Qué se ha verificado

`ConcurrencyTests` lanza 8 hilos, sincronizados con `threading.Barrier`, y reduce `sys.setswitchinterval` para forzar cambios de hilo frecuentes. Comprueba:

- Inserciones simultáneas: 4 000 pacientes, ninguno perdido, secuencias `0…3999` sin repetir, orden global correcto y FIFO de cada hilo respetado.
- Extracciones simultáneas: 4 000 extracciones sin duplicados ni pérdidas, y la cola queda vacía con estadísticas a cero.
- Mezcla de productores, consumidores y lectores: las instantáneas de `stats` y `list_queue` son siempre coherentes.

**Control negativo:** se ejecutaron las mismas pruebas sustituyendo el lock por un contexto vacío y con una pausa artificial (`time.sleep(0)`) entre leer y escribir para hacer visible la ventana de carrera. Las **3 pruebas fallaron**: pacientes perdidos (`3318 != 4000`) y `TypeError` por comparar `Patient`. Las pruebas detectan, por tanto, los fallos que el bloqueo evita.

**Límite honesto:** ninguna batería de pruebas puede demostrar que **no** existan condiciones de carrera; solo puede no encontrarlas. La garantía viene del razonamiento anterior: todo acceso al estado compartido está dentro del mismo bloqueo. Las pruebas se ejecutaron en CPython 3.14.6 **con GIL**, no en un build *free-threaded*.

### 7.5. Fuera de alcance

El programa sigue siendo una CLI de un solo hilo. No se introducen workers, servidores ni procesamiento distribuido. Para varios **procesos** o máquinas, `threading.Lock` no sirve: haría falta una base de datos con transacciones o un broker de mensajes.

---

## 8. Limitaciones

- **Solo en memoria**: al cerrar el programa se pierde la cola. No hay persistencia ni auditoría.
- **Inanición (*starvation*)**: si siguen llegando pacientes de nivel 1 y 2, un nivel 3 puede esperar indefinidamente. Un sistema real usaría *aging* o tiempos máximos por nivel.
- **No se puede reclasificar ni retirar a un paciente** de la cola, por ejemplo si empeora o se marcha. Un heap no permite buscar un elemento de forma eficiente; haría falta un índice auxiliar o el patrón de «borrado perezoso».
- **Fechas *naive***: `datetime.now()` no guarda zona horaria.
- **Identidad**: dos pacientes con el mismo nombre son indistinguibles en pantalla; no hay identificador clínico.
- **Concurrencia limitada a hilos de un mismo proceso**, y verificada solo en CPython con GIL.
- **Uso educativo**: no sustituye a un protocolo de triaje ni a un sistema hospitalario certificado.
