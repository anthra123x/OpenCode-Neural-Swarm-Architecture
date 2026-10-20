# Multi-Agent Coordination & Knowledge Architecture (Swarm v2)

Este documento define los protocolos operacionales para los agentes de OpenCode, la memoria en grafo de conocimiento (`brain-graph`) y el motor unificado de ejecución y calidad (`swarm-engine`).

---

## 1. Protocolo del Motor Operacional (`swarm-engine`)

Todos los agentes especializados (`@orchestrator`, `@backend`, `@frontend`, `@git-flow`, `@qa-auditor`, `@devops`) operan de forma sincronizada y coordinada a través del servidor MCP `swarm-engine`.

### Reglas de Sincronización y Coordinación de Tareas:
1. **Conmutación Interactiva con `TAB`**:
   - Los roles esenciales (`@orchestrator`, `@backend`, `@frontend`, `@git-flow`, `@qa-auditor`) operan como agentes configurados en OpenCode. El usuario o el flujo pueden alternar entre ellos mediante `TAB` en el prompt o invocando subagentes.

2. **Tablero de Tareas y Estado del Enjambre**:
   - El `@orchestrator` descompone las metas en hitos atómicos y los publica:
     ```python
     swarm_post_task(title="Implementar autenticación JWT", description="Crear endpoints de auth, rotación de refresh tokens y esquema de base de datos", assigned_to="@backend", priority="high")
     ```
   - Cada especialista consulta sus tareas asignadas:
     ```python
     swarm_list_tasks(status="todo", assigned_to="@backend")
     ```
   - Al comenzar y al completar el trabajo, actualiza el estado (`todo`, `in_progress`, `done`, `blocked`):
     ```python
     swarm_update_task(task_id=1, status="in_progress", notes="Escribiendo tests TDD para endpoints de auth")
     ```

3. **Handoffs Formales y Artefactos Compartidos (Backend -> Frontend / QA)**:
   - Al terminar un modelo, endpoint o componente, el agente publica el artefacto formal:
     ```python
     swarm_share_artifact(artifact_key="auth-api-v1", title="Auth Endpoints Contract", artifact_type="api_spec", content="POST /api/auth/login {email, password} -> {token, refreshToken}")
     ```
   - El siguiente agente (`@frontend`, `@qa-auditor`) recupera el contrato sin necesidad de consultar al usuario:
     ```python
     swarm_get_artifact(artifact_key="auth-api-v1")
     ```

4. **Compuerta de Calidad Unificada (`swarm_gate_check`)**:
   - Antes de dar por concluido un hito de tarea, se verifica la compuerta de calidad:
     ```python
     swarm_gate_check(task_id=1)
     ```
   - Valida que la tarea esté completada, que los tests hayan pasado y que no existan violaciones abiertas de Sentinel.

---

## 2. Protocolo del Cerebro Neural (`brain-graph`)

`brain-graph` proporciona una memoria en grafo de conocimiento relacional estilo Obsidian sobre SQLite WAL con búsqueda híbrida (FTS5 + expansión de sinapsis) y decaimiento exponencial de confianza (`confidence decay`).

### A. Hidratación al Iniciar Turno:
Al iniciar cualquier tarea o sesión, `@orchestrator` y los especialistas cargan el contexto consolidado del proyecto:
```python
get_brain_context(project="mi-proyecto")
```
Devuelve un snapshot con los nodos activos, observaciones recientes y el último checkpoint.

### B. Ciclo de Vida del Conocimiento:
1. **Creación de Entidades**:
   ```python
   create_entity(id="jwt-strategy", title="JWT Strategy with HttpOnly Cookies", node_type="decision", content="Rotación estricta de refresh token cada 7 días", tags="auth,security")
   ```
2. **Sinapsis Tipadas**:
   ```python
   relate(source="auth-controller", target="jwt-strategy", relation="USES", reason="Implementa flujo JWT")
   relate(source="auth-controller", target="sec-001", relation="GOVERNED_BY", reason="Cumple regla de cero secretos")
   ```
   *Vocabulario de relaciones*: `USES`, `DEPENDS_ON`, `TESTED_BY`, `GOVERNED_BY`, `EXPOSES`, `IMPLEMENTS`, `CONTRADICTS`, `SUPERSEDES`, `LEARNED_FROM`, `PART_OF`, `EXTENDS`, `REQUIRES`.
3. **Observaciones Incrementales** (sin reescribir el nodo):
   ```python
   observe(node_id="auth-controller", observation="Endpoints protegidos con middleware de rate limiting", observer="@backend")
   ```
4. **Traversal Multi-Hop**:
   ```python
   traverse(start_node="auth-controller", depth=2, relation_filter="USES")
   ```
5. **Búsqueda Híbrida**:
   ```python
   recall_graph(query="jwt secret rotation", expand_neighbors=True)
   ```
6. **Aprendizajes del Enjambre**:
   ```python
   record_learning(lesson="Bcrypt rounds >= 12 previene ataques de fuerza bruta", trigger_node="auth-controller")
   ```
7. **Puntos de Control de Sesión**:
   ```python
   checkpoint_brain(summary="Autenticación JWT implementada con 100% tests pasando", active_task="Comenzar vistas frontend", files_touched=["src/auth.ts", "tests/auth.test.ts"])
   ```

---

## 3. Guardián de Reglas de Desarrollo (`swarm-engine` · Sentinel)

Sentinel audita en tiempo real que los entregables cumplan las 7 Reglas Inmutables de Ingeniería:

### Las 7 Reglas Inmutables:
- **`TDD-001`**: Pruebas automatizadas obligatorias con cobertura $\ge 80\%$.
- **`VERIF-001`**: Bucle de verificación en 6 etapas (Build, Types, Lint, Tests, Security OWASP, Regresiones).
- **`GIT-001`**: Commits bajo estándar Conventional Commits 1.0 (`feat:`, `fix:`, `refactor:`, etc.) y árbol limpio.
- **`UI-001`**: Motion táctil, diseño curado, micro-animaciones, cero placeholders y estética anti-slop.
- **`SEC-001`**: Cero secretos hardcodeados; uso estricto de variables de entorno y saneamiento en frontera.
- **`ARCH-001`**: Principio de Responsabilidad Única (SRP), archivos modulares $<800$ líneas y errores tipados.
- **`HANDOFF-001`**: Contratos formales compartidos (`swarm_share_artifact`) antes del traspaso entre agentes.

### Auditoría y Cumplimiento:
1. **Auditar Entregable**:
   ```python
   sentinel_audit_task(
     agent_name="@backend",
     task_title="Implementar autenticación JWT",
     deliverables="src/auth.py, tests/test_auth.py",
     files_modified="src/auth.py, tests/test_auth.py",
     test_results="12 passed, 0 failed, 94% coverage"
   )
   ```
2. **Consultar Reglas y Checklists**:
   ```python
   sentinel_get_rules(category="security")
   ```
3. **Verificar Cumplimiento**:
   ```python
   sentinel_verify_compliance(agent_name="@backend")
   ```

---

## 4. Verificación en Tiempo Real (`swarm-engine` · Tester)

Tester ejecuta suites de prueba, sondea endpoints y verifica componentes para evitar regresiones o alucinaciones:

1. **Ejecución de Suites de Pruebas**:
   ```python
   tester_run_suite(runner="pytest", coverage=True)
   ```
2. **Sondeo en Vivo de Endpoints (HTTP Probe)**:
   ```python
   tester_probe_endpoint(url="http://localhost:3000/api/health", expected_status=200)
   ```
3. **Verificación Estática de Componentes / Sintaxis**:
   ```python
   tester_verify_component(file_path="src/index.ts")
   ```
4. **Scorecard de Salud Global en Vivo**:
   ```python
   tester_get_live_health()
   ```
5. **Comprobación Ultrarrápida de Archivos**:
   ```python
   tester_quick_check(file_path="src/auth.ts")
   ```
6. **Sincronización Tester ↔ Sentinel**:
   ```python
   tester_sync_with_sentinel()
   ```

---

## 5. Blindaje Operacional Anti-Autosabotaje

- **Inspección Previa Obligatoria**: Antes de escribir o sugerir código nuevo, inspecciona el árbol de archivos. Jamás crees duplicados ni componentes paralelos.
- **Validación Gateada**: Ningún agente cierra un entregable sin pruebas pasando (`tester_run_suite`) y verificación de Sentinel (`sentinel_audit_task` o `swarm_gate_check`).
- **Persistencia Silenciosa**: Al completar hitos clave, ancla el aprendizaje con `record_learning` y emite un checkpoint con `checkpoint_brain`.
