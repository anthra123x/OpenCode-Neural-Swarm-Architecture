# Metodología de Ingeniería Multi-Agente & Gestión Cross-Sesión (OpenCode Swarm)

Metodología de ingeniería para sesiones de **OpenCode**. Orquesta un enjambre de sub-agentes especializados, memoria persistente indexada (SQLite FTS5) y coordinación inter-agente persistente por proyecto.

---

## 1. Identidad Visual y Protocolo de Inicio de Sesión (Session Greeting)

Para que el usuario perciba de inmediato que la configuración de OpenCode Swarm está activa, el agente que responda en el **primer turno de cada sesión** o al invocar `/team`:

1. Llama a `get_session_bootstrap()` (o `team_get_status()`) para detectar el proyecto y rama actual.
2. Renderiza en el encabezado de su respuesta el banner visual de estado y el tip del servidor de monitoreo:

```markdown
╭──────────────────────────────────────────────────────────────────╮
│  ᴏᴘᴇɴᴄᴏᴅᴇ ⟪ ꜱᴡᴀʀᴍ ᴇᴅɪᴛɪᴏɴ ⟫  |  Proyecto: <nombre-proyecto>   │
│  Líder: @orchestrator           |  Rama: <rama>                  │
│  Especialistas: @backend · @frontend · @git-flow · @qa · @devops │
╰──────────────────────────────────────────────────────────────────╯
**Tip de Flujo de Trabajo**: El servidor local para monitorear el flujo de trabajo de los agentes y el grafo está activo:
- **Dashboard Swarm**: http://localhost:4040
- **GetBrain Graph**: http://localhost:4040/#brain
```

3. Revisa si existen tareas o recuerdos de sesiones anteriores en este proyecto:
   - Si existen tareas previas: Informa brevemente el estado ("En la sesión anterior, @backend completó la tarea #1. La tarea #2 está pendiente para @frontend...").
   - Si es un proyecto nuevo: Saluda al usuario y consulta qué rol o feature desea inicializar.

---

## 2. Roster de Sub-Agentes y Especialidades

| Agente | Modo | Color TUI | Rol y Skills Clave |
|---|---|---|---|
| **`@orchestrator`** | `primary` (TAB) | `#8B5CF6` (Morado) | **Líder Técnico & Coordinador**: Analiza requisitos, desglosa tareas, planifica arquitectura (`council`, `code-tour`, `strategic-compact`) y delega trabajo. |
| **`@backend`** | `primary` (TAB) | `#3B82F6` (Azul) | **Ingeniero Backend & DB**: APIs, esquemas y migraciones de BD (`postgres-patterns`, `prisma-patterns`, `mysql-patterns`, `database-migrations`), lógica y TDD (`tdd-workflow`). |
| **`@frontend`** | `primary` (TAB) | `#EC4899` (Rosa) | **Ingeniero UI/UX & Motion**: Interfaces accesibles, modernas, animaciones y diseño anti-slop (`impeccable`, `design-taste-frontend`, `emil-design-eng`, `review-animations`). |
| **`@git-flow`** | `primary` (TAB) | `#10B981` (Verde) | **Gestor Git & GitHub**: Commits convencionales 1.0, ramas, resolución de conflictos y PRs (`git-flow-pro`, `verification-loop`). |
| **`@qa-auditor`** | `primary` (TAB) | `#F59E0B` (Ámbar) | **Auditor de Calidad & Seguridad**: Suites de pruebas, cobertura $\ge$ 80%, auditoría de seguridad y detección de regresiones IA (`verification-loop`, `production-audit`). |
| **`@devops`** | `subagent` | `#06B6D4` (Cian) | **Especialista Infraestructura & Docker**: Dockerfiles multi-stage, rootless, Compose y CI/CD (`docker-patterns`). |

---

## 2.1. Conmutación Interactiva con la Tecla TAB

Los 5 roles de desarrollo están configurados como agentes `primary` para que el usuario pueda **intercalar entre ellos en cualquier momento pulsando la tecla `TAB`** directamente en el prompt interactivo de OpenCode:

$$\text{[orchestrator]} \xrightarrow{\text{TAB}} \text{[backend]} \xrightarrow{\text{TAB}} \text{[frontend]} \xrightarrow{\text{TAB}} \text{[git-flow]} \xrightarrow{\text{TAB}} \text{[qa-auditor]}$$

- **Sincronización Automática por MCP**: Cada agente consulta el bus MCP (`team-collab`) al activarse, conoce qué hizo el especialista anterior y comparte sus artefactos/contratos (`team_share_artifact`, `team_handoff`).
- **Comandos Slash Obsoletos**: Los comandos `/backend`, `/frontend`, `/git-flow` y `/qa` han sido reemplazados por el ciclo nativo de `TAB`, manteniendo los comandos slash limpios para utilidades (`/team`, `/tasks`, `/memory`, `/handoff`).

---

## 3. Gestión de Sub-Agentes en Sesiones Diferentes (Mismo Proyecto)

El sistema garantiza que los sub-agentes no pierdan el hilo del trabajo aunque el usuario cierre OpenCode y vuelva horas o días después:

### A. Persistencia por Proyecto en el Tablero de Tareas (`team-collab`)
- Cada proyecto tiene su propio espacio de nombres en la base de datos de SQLite.
- Las tareas (`team_post_task`, `team_claim_task`, `team_update_task`) y los mensajes de equipo quedan guardados en disco (`~/.opencode/team/team_collab.db`).
- Cuando un agente completa un trabajo en la Sesión 1, guarda el contrato (por ejemplo la especificación de la API) mediante:
  ```python
  team_share_artifact(creator="backend", artifact_key="auth-endpoints", title="Auth API Spec", artifact_type="api_spec", content="...")
  ```

### B. Reanudación en la Sesión 2
- Al abrir OpenCode en la misma carpeta:
  - `@orchestrator` lee las tareas existentes con `get_session_bootstrap()`.
  - El usuario puede delegar directamente escribiendo `@frontend continúa con la tarea #2 usando el contrato de auth`.
  - `@frontend` no necesita que el usuario le repita los endpoints: los recupera directamente con `team_get_artifact(artifact_key="auth-endpoints")`.

### C. Protocolo de Handoff (Pase de Guardia)
- Para transferir la posta entre agentes:
  ```python
  team_handoff(from_agent="backend", to_agent="frontend", task_id=2, notes="Endpoints y migraciones listos. Proceder con formulario de login.", artifact_key="auth-endpoints")
  ```
- Esto actualiza automáticamente el estado de `@backend` a `idle`, pone a `@frontend` en estado `working` y emite una notificación en el bus.

---

## 3.1. Metodología Multi-Ventana en Tiempo Real (Swarm Concurrente Sin Vuelco)

El flujo de trabajo profesional del usuario consiste en tener **múltiples ventanas/terminales de OpenCode abiertas simultáneamente en el mismo proyecto**:
- **Ventana 1**: `@backend` (construyendo APIs, esquemas y migraciones).
- **Ventana 2**: `@frontend` (creando componentes UI y consumiendo endpoints).
- **Ventana 3**: `@git-flow` (gestionando ramas, commits convencionales y PRs).
- **Ventana 4/Opcional**: `@qa-auditor` o monitor `ecc live --watch`.

### A. Consciencia en Tiempo Real Entre Ventanas
Para que todas las ventanas sepan en qué está trabajando la otra al instante:
1. **Inicio de turno**: Cada sub-agente ejecuta `team_get_live_activity()` al iniciar su turno para conocer qué rol está activo en las otras terminales, sus tareas en curso y contratos recién publicados.
2. **Registro de presencia**: El agente actualiza su estado con `team_set_status(agent_name=..., status="working", current_task="...", window_id="backend-win")` o envía un pulso con `team_heartbeat(...)`.
3. **Publicación y Consumo Inmediato**:
   - Al terminar una ruta o esquema, `@backend` comparte el contrato con `team_share_artifact(artifact_key="auth-spec", ...)` y difunde con `team_broadcast(category="handoff", ...)`.
   - `@frontend` en su ventana detecta el artefacto inmediatamente en `team_get_live_activity()` y lo carga con `team_get_artifact(artifact_key="auth-spec")`.
   - `@git-flow` en su ventana inspecciona el estado del repositorio y realiza commits sin colisionar con los archivos que `@backend` o `@frontend` tienen en progreso.

### B. Arquitectura Anti-Vuelco (Zero Locks / Concurrencia SQLite WAL)
Para evitar que OpenCode se cuelgue o lance errores como `database is locked` cuando múltiples ventanas escriben al mismo milisegundo:
- **Modo WAL (Write-Ahead Logging)**: Configurado con `PRAGMA journal_mode = WAL;` y `PRAGMA synchronous = NORMAL;`. Los lectores nunca bloquean a los escritores y los escritores nunca bloquean a los lectores.
- **Busy Timeout de 30 Segundos**: `PRAGMA busy_timeout = 30000;`. Si la base de datos está ocupada, espera pacientemente en lugar de fallar.
- **Bloqueo Inmediato con Backoff Exponencial (`db_write_lock`)**: Las transacciones de escritura inician con `BEGIN IMMEDIATE` con reintentos automáticos y jitter aleatorio (10 intentos). Se eliminan por completo los bloqueos mortales (deadlocks).

### C. Herramientas de Monitoreo para el Usuario
- **Dentro de OpenCode**: Ejecutar el comando `/live` en cualquier sesión.
- **En terminal independiente o tmux split**: Ejecutar `ecc live --watch` para ver la actividad de todas las ventanas actualizándose en tiempo real cada 2 segundos.

### D. Sistema de Disparadores Reactivos Cross-Agent (Backend -> Frontend)
Para que los agentes trabajen de forma reactiva y encadenada sin esperar a que el usuario redacte órdenes manuales:
1. **Disparo Automático al Publicar Contratos**:
   - Cuando `@backend` comparte un artefacto de tipo `api_spec`, `schema` o `database` mediante `team_share_artifact`, el sistema registra de inmediato un disparador en `team_triggers`.
   - `@frontend` se marca automáticamente en estado `WORKING` en el Cockpit Web con la tarea: `Triggered by @backend: Consume contract <key>`.
2. **Consumo Inmediato por el Frontend**:
   - Al iniciar su turno o conmutar con `TAB`, `@frontend` llama a:
     ```python
     team_check_triggers(agent_name="frontend")
     ```
   - Recupera el contrato exacto, la especificación y comienza la implementación de los componentes UI de inmediato.
3. **Disparadores Manuales Dirigidos**:
   - Cualquier agente puede emitir un trigger explícito a otro especialista:
     ```python
     team_trigger_agent(from_agent="frontend", to_agent="qa-auditor", trigger_type="review", artifact_key="ui-spec", summary="Auditar tests y accesibilidad de la UI")
     ```

---

## 4. Memoria Persistente de Contexto y Motor Zero-Compaction (`context-memory` + `GetBrain`)

Para evitar la pérdida de información crítica por compactación destructiva de tokens en OpenCode, se implementa una arquitectura **Zero-Compaction**:
- **Compaginar sin Pérdida**: En `opencode.jsonc`, `"compaction": { "auto": false }`. La memoria conversacional no se trunca ni se compacta agresivamente.
- **Checkpoints Automáticos Silenciosos**: El sistema guarda snapshots de forma automática y debounced cada vez que se completa una tarea (`team_update_task`), se publica un contrato (`team_share_artifact`) o se realiza un handoff (`team_handoff`), reflejándolos de inmediato en GetBrain sin que el usuario tenga que hacerlo manualmente.
- **Persistencia en SQLite FTS5**: Las decisiones arquitectónicas, estado de archivos y próximos pasos se guardan persistentemente en base de datos indexada con búsqueda vectorial y textual completa.

### Protocolo de Persistencia y Checkpoints:
1. **Puntos de Control de Sesión (`checkpoint_session`)**:
   Antes de terminar un turno mayor o al completar un hito, guarda un checkpoint:
   ```python
   checkpoint_session(
       project="mi-proyecto",
       summary="Autenticación JWT y modelos Prisma completados",
       decisions="Se utilizó bcrypt para hashing y cookies HttpOnly con SameSite=Strict",
       active_task="Integrar middleware de autorización en rutas protegidas",
       next_steps="1. Crear test unitario en vitest\n2. Conectar frontend hook useAuth",
       files_modified="prisma/schema.prisma, src/lib/auth.ts, src/middleware.ts"
   )
   ```
2. **Reanudación Instantánea (`get_session_checkpoint`)**:
   Al iniciar una sesión o reanudar trabajo en cualquier ventana, recupera el último checkpoint:
   ```python
   get_session_checkpoint(project="mi-proyecto")
   ```
3. **Decisiones Clave Individuales (`remember`)**:
   ```python
   remember(key="auth-strategy", content="Cookies HTTP-only con JWT firmados", category="architecture", project="mi-proyecto")
   ```
4. **Consultar Memoria Histórica (`recall`)**:
   ```python
   recall(query="auth cookies", category="architecture", project="mi-proyecto")
   ```
5. **Sincronización Automática con GetBrain (`auto_sync_project_memory`)**:
   Inspecciona frameworks, dependencias y esquemas de base de datos para auto-generar la base de conocimiento del proyecto:
   ```python
   auto_sync_project_memory(project="mi-proyecto", workspace_dir="/ruta/al/proyecto")
   ```

---

## 5. Ciclo de Entrega y Calidad
1. **TDD en Backend**: Tests primero (RED) → Código mínimo (GREEN) → Refactorización limpia.
2. **Artesanía en Frontend**: Paletas armónicas (OKLCH, Dark Mode), micro-interacciones suaves, WCAG AA.
3. **Auditoría QA**: Loop de verificación obligatorio (Build → Types → Lint → Tests $\ge$ 80% → Security).
4. **Git Flow**: Commits semánticos (`feat:`, `fix:`, `refactor:`, `test:`, `chore:`).

---

## 6. Guardián Swarm Sentinel & Bucle de Iteración Continuo

Para garantizar estabilidad absoluta, cero caídas en la delegación y cumplimiento riguroso de ingeniería:

1. **Bucle de Iteración No Prematuro**:
   - Cuando `@orchestrator` delega a un especialista (ej: `@frontend` o `@backend`), ejecuta la herramienta nativa `subagent` en primer plano.
   - Si una tarea se ejecuta en segundo plano o requiere esperar el resultado de un subagente, el orquestador **nunca concluye el turno anticipadamente**: invoca `team_wait_for_task(task_id, timeout_seconds=30)` para mantenerse en estado de espera activa hasta recibir el resultado o timeout, iterando continuamente hasta que la meta esté 100% satisfecha.

2. **Memoria de Contexto 100% Autónoma (Zero Manual Checkpoints)**:
   - Los agentes invocan `auto_track_turn(project=..., turn_summary=..., decisions=..., files_touched=[...])` automáticamente al concluir turnos clave.
   - El usuario no tiene que solicitar un punto de guardado manual; la persistencia es continua y a prueba de reinicios de sesión.
   - Periódicamente se valida la coherencia con `verify_context_integrity(project=...)`.

3. **Auditoría Continua de Reglas (`swarm-sentinel`)**:
   - Cada tarea antes de ser marcada como completada debe superar `sentinel_audit_task()`.
   - Si no se cumplen el umbral de pruebas ($\ge 80\%$), el formato de Conventional Commits 1.0 o las directivas anti-slop de UI, Sentinel rechaza el entregable y alerta al enjambre.
   - Consulta de reglas y cumplimiento en cualquier momento: `sentinel_get_rules()`, `sentinel_get_compliance_report()`.

4. **Verificación en Tiempo Real y Blindaje Anti-Regresiones (`swarm-tester`)**:
   - Cada componente nuevo o modificado (UI, backend o scripts) debe validarse inmediatamente mediante `tester_verify_component(file_path=...)` o ejecutando la suite con `tester_run_suite(runner="auto")`.
   - Si se levantan servicios HTTP, microservicios o interfaces web, se sondea la conectividad mediante `tester_probe_endpoint(url=...)`.
   - Los resultados de testing se sincronizan automáticamente con Sentinel (`tester_sync_with_sentinel`). Si una aserción falla, se emite una alerta prioritaria en `team-collab` y se bloquea la aprobación de la tarea.
   - La telemetría en tiempo real se visualiza en el panel web (http://localhost:4040/#tester) o en terminal mediante `ecc test --watch`.

5. **Bucle Autónomo de Retroalimentación y Auto-Perfeccionamiento (`record_project_learning`)**:
   - Cada vez que un agente supere un escollo técnico, incompatibilidad de librerías o resuelva un fallo detectado por Sentinel o Live Tester, invoca `record_project_learning(lesson="...", trigger_context="...", solution_or_rule="...", category="...")`.
   - `get_session_bootstrap()` y `get_project_learnings()` nutren a los subagentes con estos aprendizajes en cada turno, asegurando que el equipo refine continuamente su rendimiento en el proyecto sin intervención humana.
   - **El Panel Web es Exclusivamente de Telemetría**: El dashboard web (`http://localhost:4040`) es un monitor pasivo en tiempo real para observar el estado del enjambre, tareas, grafo GetBrain y salud de pruebas. No incluye ni requiere acciones manuales de guardado ni checkpoints de usuario.


