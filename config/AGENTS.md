# Multi-Agent Coordination & Knowledge Architecture

Este documento define los protocolos operacionales para los agentes de OpenCode, la memoria persistente de contexto y el bus de colaboración del equipo.

---

## 1. Team Swarm Bus Protocol (`team-collab`)

Todos los agentes especializados (`@orchestrator`, `@backend`, `@frontend`, `@git-flow`, `@qa-auditor`, `@devops`) forman un equipo cohesionado y sincronizado a través de este MCP.

### Reglas de Sincronización y Coordinación Multi-Ventana:
1. **Conmutación Interactiva con `TAB`**:
   - Los 5 roles esenciales (`@orchestrator`, `@backend`, `@frontend`, `@git-flow`, `@qa-auditor`) operan como agentes primarios. El usuario puede alternar entre ellos en cualquier momento pulsando `TAB` en el prompt interactivo.

2. **Consciencia Multi-Ventana en Tiempo Real**:
   - En flujos de trabajo con múltiples terminales simultáneas (ej: Ventana 1 = Backend, Ventana 2 = Frontend, Ventana 3 = Git-Flow):
   - Al iniciar cualquier tarea, el agente consulta `team_get_live_activity()` para saber quién está activo en otras ventanas y en qué archivo/tarea trabaja.
   - Envía su estado o pulso de presencia:
     ```python
     team_set_status(agent_name="backend", status="working", current_task="Building user auth endpoints", window_id="win-backend")
     ```
     o emite pulsos de vida con `team_heartbeat(agent_name="backend", window_id="win-backend")`.

3. **Handoffs, Contratos y Disparadores Reactivos (Backend -> Frontend)**:
   - Cuando `@backend` termine un modelo de datos o endpoints, publica el contrato:
     ```python
     team_share_artifact(creator="backend", artifact_key="auth-api-v1", title="Auth Endpoints Contract", artifact_type="api_spec", content="...")
     ```
   - `team-collab` genera de inmediato un disparador reactivo en `team_triggers` y marca a `@frontend` como activo.
   - `@frontend` consume sus disparadores pendientes con:
     ```python
     team_check_triggers(agent_name="frontend")
     ```
   - O bien, un agente puede despachar explícitamente a otro:
     ```python
     team_trigger_agent(from_agent="backend", to_agent="frontend", trigger_type="api_spec", artifact_key="auth-api-v1", summary="Implementar vistas y formulario de login")
     ```

4. **Anuncios y Bloqueos**:
   - Si un agente se encuentra bloqueado o requiere intervención de otro dominio, publica un mensaje con categoría `warning` o `question`:
     ```python
     team_broadcast(sender="frontend", message="Blocked: Need updated JWT schema in auth-api-v1", category="warning", priority="high")
     ```

5. **Tablero de Tareas**:
   - El `@orchestrator` publica las metas con `team_post_task()`.
   - Los especialistas reclaman sus tareas con `team_claim_task()` y las marcan completadas con `team_update_task()`.
   - Al completar la tarea, el agente pasa automáticamente a `idle` y se registra un checkpoint de memoria silencioso en `context-memory`.

---

## 2. Persistent Context Memory Protocol (`context-memory` + `GetBrain`)

La memoria persistente permite conservar contexto, reglas de negocio, preferencias del usuario y decisiones arquitectónicas a través de diferentes sesiones y proyectos, eliminando la necesidad de compactación destructiva de contexto en OpenCode (`compaction.auto = false`).

### Puntos de Control y Cero Compactación:
1. **Checkpointing de Sesión (`checkpoint_session`)**:
   - Cada agente especializado debe registrar un checkpoint ante hitos mayores o antes de ceder el turno:
     ```python
     checkpoint_session(project=..., summary="...", decisions="...", active_task="...", next_steps="...", files_modified="...")
     ```
   - Este checkpoint se guarda en SQLite indexado y se refleja inmediatamente como un nodo `memory` destacado en el grafo visual GetBrain.
2. **Hidratación al Reanudar (`get_session_checkpoint`)**:
   - Para no saturar el historial de chat con cientos de mensajes previos, ejecuta:
     ```python
     get_session_checkpoint(project=...)
     ```
   - Recupera el estado exacto del proyecto, archivos modificados y próximos pasos con 100% de fidelidad.

### Seguimiento Autónomo de Contexto (Zero Manual Checkpoints):
1. **Rastreo Automático por Turno (`auto_track_turn`)**:
   - `context-memory` opera de forma continua en segundo plano.
   - Cada agente y orquestador invoca `auto_track_turn(project=..., turn_summary=..., decisions=..., files_touched=[...])` al finalizar pasos relevantes.
   - El usuario nunca necesita recordar hacer un "punto de guardado" manual: el sistema indexa y persiste el contexto automáticamente.
2. **Verificación de Integridad de Contexto (`verify_context_integrity`)**:
   - Valida que SQLite WAL, GetBrain y los tableros de tareas permanezcan sincronizados sin desincronizaciones entre ventanas.

### Prioridad de Consulta Habitual:
1. Al comenzar una sesión o recibir una instrucción compleja:
   ```python
   get_active_context(project="global")
   ```
2. Para resolver dudas técnicas sobre convenciones pasadas o cómo se implementó un módulo:
   ```python
   recall(query="jwt secret rotation", category="architecture")
   ```

### Cuándo Registrar en Memoria (`remember` y `record_project_learning`):
- **Decisiones Arquitectónicas**: Decisiones clave sobre bibliotecas, frameworks, patrones (ej: "usar Zustand para estado global", "PostgreSQL con UUIDv7").
- **Preferencias del Usuario**: Estilos de codificación, stack preferido, diseño oscuro, convenciones de nombres.
- **Aprendizajes y Retroalimentación Continua (`record_project_learning`)**:
  - Causa raíz de un fallo sutil, un gotcha de testing o una incompatibilidad, y cómo resolverlo.
  - Al alimentar este bucle, todos los subagentes consultan automáticamente las lecciones vía `get_session_bootstrap()` y `get_project_learnings()`, previniendo errores recurrentes y refinando su desempeño con el proyecto.

---

## 3. Codebase Knowledge Graph (`codebase-memory-mcp`)

*Nota: Requiere que `codebase-memory-mcp` esté instalado y habilitado. Si retorna "tool not found", recurre inmediatamente a grep/glob o a las herramientas nativas.*

Herramientas disponibles si el servidor está activo:
- `search_graph`: Búsqueda de símbolos por patrón (funciones, clases, rutas).
- `trace_path`: Análisis de llamadas entrantes y salientes.
- `get_code_snippet`: Extracción del cuerpo de una función o clase.
- `query_graph`: Consultas Cypher para relaciones complejas.

---

## 4. Swarm Sentinel Protocol (`swarm-sentinel`) — Guardián de Reglas de Desarrollo

El servidor MCP `swarm-sentinel` actúa como supervisor estricto y auditor de calidad continuo en todo el enjambre. Ningún agente puede dar por completada una tarea sin cumplir las reglas de ingeniería.

### Reglas Inmutables de Desarrollo:
- **`TDD-001`**: Cobertura obligatoria $\ge 80\%$ y pruebas unitarias/integración previas a la implementación.
- **`VERIF-001`**: Ciclo de verificación en 6 etapas (sintaxis, unit tests, integración, types, linter, seguridad).
- **`GIT-001`**: Commits bajo estándar estricto Conventional Commits 1.0 (`feat:`, `fix:`, `refactor:`, etc.).
- **`UI-001`**: Motion táctil, diseño curado, micro-animaciones, cero placeholders y estética anti-slop.
- **`SEC-001`**: Cero secretos, tokens o credenciales hardcodeadas; uso estricto de variables de entorno.
- **`ARCH-001`**: Principio de Responsabilidad Única (SRP), desacoplamiento y manejo explícito de excepciones.
- **`HANDOFF-001`**: Protocolo formal de contratos de interfaz entre `@backend` y `@frontend`.

### Flujo de Auditoría Obligatoria:
1. **Antes de cerrar tarea**:
   El orquestador o especialista somete el entregable a:
   ```python
   sentinel_audit_task(
     task_id=1,
     agent_name="backend",
     deliverables=["src/api/auth.py", "tests/test_auth.py"],
     test_command="pytest tests/test_auth.py",
     coverage_percent=92.5,
     commit_message="feat(auth): add JWT rotation with refresh tokens",
     security_checks_passed=True,
     architectural_notes="SRP applied, env vars used for JWT secret"
   )
   ```
2. **Rechazo y Alerta Automática**:
   Si una regla es violada (ej: cobertura < 80% o mensaje de commit inválido), Sentinel **rechaza** el entregable, registra la infracción y emite automáticamente un aviso en `team-collab` para que el agente rectifique.
3. **Mantenimiento del Bucle de Iteración y Continuidad**:
   El orquestador no se detiene si un subagente sigue trabajando: usa `team_wait_for_task(task_id, timeout_seconds=3)` para sondear el estado sin bloquear el hilo, asegurando ejecución continua sin pedir cambios manuales de TAB.

---

## 6. Blindaje Operacional Anti-Autosabotaje y Aprendizaje Continuo
- **Inspección Previa Obligatoria**: Jamás crear archivos duplicados ni componentes paralelos.
- **Validación Gateada**: Ningún agente cierra un entregable sin pruebas verdes (Build, Types, Lint, TDD >=80%, OWASP).
- **Retroalimentación Persistente**: Cada lección u optimización descubierta se ancla con `record_project_learning` para nutrir las siguientes sesiones.

---

## 5. Swarm Live Tester Protocol (`swarm-tester`) — Verificación en Tiempo Real y Blindaje Anti-Regresiones

El servidor MCP `swarm-tester` y su plugin interactivo operan en tiempo real para verificar continuamente cada componente, endpoint, página y cambio de código introducido por los agentes, evitando regresiones, código roto o alucinaciones. Trabaja de la mano con `swarm-sentinel`.

### Capacidades y Herramientas del Live Tester:
1. **Ejecución Automatizada de Suites (`tester_run_suite`)**:
   - Detección automática del test runner del proyecto (`pytest`, `vitest`, `jest`, `unittest`, `cargo test`, `go test`).
   - Parseo instantáneo de aserciones (`passed`, `failed`, `total`) y porcentaje de cobertura (`coverage_percent`).
   - Sincronización automática con `swarm-sentinel` (`auto_sync_sentinel=True`).
2. **Sondeo en Vivo de Endpoints (`tester_probe_endpoint`)**:
   - Envía peticiones HTTP reales a servidores de desarrollo locales (ej: APIs REST, microservicios, SPAs).
   - Valida códigos de respuesta esperados (200, 201), tiempo de latencia en milisegundos y patrones de texto en el body.
3. **Verificación Estática de Componentes UI y Código (`tester_verify_component`)**:
   - Comprueba sintaxis AST estricta (Python, TypeScript/JavaScript, CSS, HTML).
   - Valida balanceo de llaves, corchetes y etiquetas.
   - Detecta anti-patrones "slop" (como `TODO`, `FIXME`, placeholders o transiciones CSS genéricas).
   - Localiza y ejecuta suites de pruebas unitarias co-localizadas (ej: `server.py` -> `test_server.py`).
4. **Scorecard de Salud Global en Vivo (`tester_get_live_health`)**:
   - Muestra estado consolidado: `HEALTHY`, `DEGRADED`, o `FAILING`.
   - Consultable en la terminal mediante `ecc test --watch` o mediante la herramienta `tester_get_live_health()`.
5. **Comprobación Ultrarrápida de Modificaciones Git (`tester_quick_check`)**:
   - Inspecciona archivos modificados en el árbol git y los verifica en milisegundos.
6. **Puente Directo Tester ↔ Sentinel (`tester_sync_with_sentinel`)**:
   - Si las pruebas pasan y la cobertura es $\ge 80\%$, certifica la tarea en Sentinel.
   - Si una prueba falla o hay error de sintaxis, registra inmediatamente una infracción bajo `TDD-001` o `VERIF-001` y emite una alerta prioritaria en `team-collab`.


