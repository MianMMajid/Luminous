# Backend Architecture Execution Plan

Date: 2026-04-13  
Source report: [backend_architecture_report_2026-04-13.md](/Users/qubitmac/Documents/BioxYC/docs/backend_architecture_report_2026-04-13.md)  
Audience: Senior backend engineer, tech lead, product owner  
Goal: Turn the architecture report recommendations into a phased implementation plan.

## Objective

Move the current Streamlit-centered monolith from a prototype-grade in-process backend toward a maintainable, observable, and scalable backend architecture, without breaking the existing user experience.

This plan assumes the product will continue shipping during the migration. The strategy is incremental extraction, not a rewrite.

## Planning Principles

- Preserve current product behavior while extracting backend responsibilities.
- Separate concerns in this order: orchestration, state, execution, persistence, integrations, observability.
- Avoid introducing durable infrastructure before the application boundaries are explicit.
- Keep Streamlit as a UI adapter, not the long-term owner of backend orchestration.
- Require measurable acceptance criteria per phase.

## Recommendation Coverage Map

| Report recommendation | Plan workstream |
|---|---|
| Extract service layer from UI-owned orchestration | Phases 1 and 2 |
| Replace ad hoc `st.session_state` ownership with typed session model | Phase 2 |
| Externalize non-durable background execution | Phase 3 |
| Replace local persistence model | Phase 4 |
| Normalize blocking vs background execution | Phases 1 and 3 |
| Remove Streamlit coupling from `src/` backend modules | Phases 1 and 2 |
| Centralize retry, timeout, and resilience policy | Phase 5 |
| Add structured logging and metrics | Phase 6 |
| Standardize environment/runtime entrypoints | Phase 0 |

## Proposed Timeline

Notional timeline: 8 to 12 weeks, depending on team size and how much feature work must continue in parallel.

- Phase 0: 3 to 5 days
- Phase 1: 1.5 to 2 weeks
- Phase 2: 1 to 1.5 weeks
- Phase 3: 2 to 3 weeks
- Phase 4: 1.5 to 2 weeks
- Phase 5: 1 week
- Phase 6: 1 week
- Phase 7: 3 to 5 days

## Phase 0: Stabilization And Guardrails

### Goal

Create a safe baseline before architectural extraction begins.

### Scope

- Standardize one canonical local/runtime entrypoint.
- Lock in the existing smoke suite as the migration safety net.
- Add architectural guardrails so new code does not deepen current coupling.

### Tasks

1. Standardize execution commands around one path:
   - `uv run ...` or
   - `.venv/bin/python ...`
2. Document the required runtime contract:
   - expected environment variables
   - background execution assumptions
   - supported deployment mode
3. Add CI job(s) to run:
   - `scripts/test_full_pipeline.py`
   - import smoke tests
4. Add lightweight lint rule or review rule:
   - no new `streamlit` imports in backend modules unless explicitly justified
5. Mark legacy blocking paths in code with deprecation comments where appropriate.

### Deliverables

- one canonical developer command path
- CI baseline for full pipeline smoke tests
- migration ADR or short design note

### Acceptance Criteria

- Every developer can run the same validated command path locally.
- CI passes on the current architecture before refactoring begins.
- New backend changes are prevented from increasing Streamlit coupling.

## Phase 1: Extract Application Services

### Goal

Move orchestration out of components into explicit backend services.

### Scope

Extract the main UI-owned flows currently embedded in:

- `components/structure_viewer.py`
- `components/context_panel.py`
- `components/project_manager.py`
- `components/chat_followup.py`

### New Service Interfaces

- `PredictionService`
- `ContextService`
- `InterpretationService`
- `ProjectService`
- `ChatResearchService`

### Tasks

1. Define service contracts and input/output types.
2. Move prediction backend selection and fallback logic into `PredictionService`.
3. Move context fetch fallback logic into `ContextService`.
4. Move interpretation dispatch into `InterpretationService`.
5. Move project save/load serialization logic into `ProjectService`.
6. Keep components as thin adapters:
   - gather user intent
   - call service
   - render response

### Refactoring Rules

- Components may read state and render UI.
- Services may orchestrate workflows and call integrations.
- Services must not import Streamlit.
- Integrations should not mutate session state directly.

### Deliverables

- new `src/services/` package
- component code reduced to UI and event handling
- unchanged user behavior

### Acceptance Criteria

- No orchestration-heavy component owns fallback logic directly.
- At least prediction, context, interpretation, and project persistence can be exercised through service interfaces without Streamlit runtime.
- Existing smoke tests still pass.

## Phase 2: Introduce A Typed Session State Model

### Goal

Replace implicit string-key mutation patterns with a typed application state model.

### Scope

Centralize ownership of analysis state currently spread across:

- `app.py`
- `components/query_input.py`
- `components/notification_poller.py`
- `components/project_manager.py`

### New Model

Create an `AnalysisSession` aggregate, for example with:

- query metadata
- prediction result
- trust audit
- biological context
- interpretation
- task metadata references
- cached analysis artifacts

### Tasks

1. Define typed state schema.
2. Implement explicit transition methods:
   - `start_query`
   - `clear_analysis`
   - `set_prediction`
   - `set_trust_audit`
   - `set_bio_context`
   - `set_interpretation`
   - `restore_project`
3. Replace duplicated reset logic with one owner.
4. Update serialization/deserialization to operate on the typed model rather than raw session keys.
5. Leave `st.session_state` in place only as a storage adapter for the typed object.

### Deliverables

- typed session aggregate
- one canonical reset path
- one canonical project serialization path

### Acceptance Criteria

- Reset logic exists in one backend-owned location.
- Project save/load no longer depends on manually mirrored lists of session keys.
- Components consume typed state rather than raw string-key bags where possible.

## Phase 3: Externalize Background Execution

### Goal

Replace in-process daemon-thread jobs with durable, observable background execution.

### Scope

Current in-process task execution lives in:

- `src/task_manager.py`
- `src/background_tasks.py`
- `components/notification_poller.py`

### Target

Adopt one durable job system:

- `RQ`
- `Celery`
- `Arq`
- or `Temporal` if workflow complexity is expected to grow materially

### Tasks

1. Define a job model:
   - job id
   - type
   - status
   - submitted time
   - started time
   - completed time
   - retry count
   - correlation id
   - owning user/session/project
2. Move long-running flows behind jobs:
   - prediction
   - context fetch
   - interpretation
   - video generation
   - research/chat tool-chains if latency justifies it
3. Replace `task_manager` with a job submission client and job status reader.
4. Replace the current sidebar poller with job-status polling or push updates from a durable store.
5. Preserve stale-result protection semantics from the current generation counter model.

### Migration Strategy

- First introduce the durable job abstraction behind the current task submission API.
- Then switch prediction/context/video to the new backend one by one.
- Remove thread-based execution only after parity is confirmed.

### Deliverables

- queue/worker infrastructure
- persisted job table or backend job store
- UI job status integration

### Acceptance Criteria

- A process restart does not silently lose submitted long-running jobs.
- Job status can be inspected outside the current Streamlit process.
- Prediction, context, and video jobs no longer rely on daemon threads.

## Phase 4: Replace Local Persistence With Shared Storage

### Goal

Make user and project persistence production-safe for multi-user and multi-instance operation.

### Scope

Current persistence:

- SQLite in `src/user_store.py`
- JSON project files in `data/projects/`

### Target

- Postgres for metadata and user/project records
- object storage for blobs and exported artifacts

### Tasks

1. Define persistence schema for:
   - users
   - projects
   - analysis sessions
   - job records
   - saved exports/artifacts metadata
2. Add repository interfaces:
   - `UserRepository`
   - `ProjectRepository`
   - `AnalysisRepository`
   - `JobRepository`
3. Migrate SQLite user profile logic to Postgres-backed repositories.
4. Replace direct JSON snapshot writes with repository + object storage upload flow.
5. Add ownership and authorization semantics for project access.
6. Add schema migrations.

### Deliverables

- Postgres schema and migration system
- repository abstraction
- object storage integration for large payloads

### Acceptance Criteria

- Project save/load works without local filesystem dependence.
- User records are no longer stored in SQLite.
- Multiple application instances can access the same project and job metadata.

## Phase 5: Normalize Integration Boundaries And Resilience

### Goal

Standardize how external providers are called, timed out, retried, and observed.

### Scope

Current provider logic is uneven across:

- `src/tamarind_client.py`
- `src/modal_client.py`
- `src/bio_context.py`
- `src/online_tools.py`
- direct `httpx` calls in components and utility modules

### Tasks

1. Introduce provider adapter modules with common conventions:
   - timeout classes
   - retryable exception taxonomy
   - non-retryable exception taxonomy
   - request metadata
2. Define a shared retry policy:
   - retry budgets
   - exponential backoff with jitter
   - idempotency assumptions
3. Move direct provider calls out of components.
4. Standardize response envelopes where practical.
5. Add circuit-breaker or provider health protections for the highest-risk dependencies.

### Deliverables

- `src/integrations/` or similar package structure
- shared resilience policy
- reduced direct `httpx` usage in components

### Acceptance Criteria

- Provider failures behave consistently across prediction, context, and research flows.
- No component owns direct network fallback logic.
- Retry behavior is centrally inspectable and configurable.

## Phase 6: Add Observability

### Goal

Make backend behavior inspectable without relying on UI toasts and ad hoc reproduction.

### Scope

Observability is currently minimal. This phase adds operational visibility without changing product behavior.

### Tasks

1. Add structured logging with:
   - request id
   - user id or session id
   - project id
   - job id
   - provider
   - latency
   - outcome
2. Add metrics for:
   - job queue depth
   - job duration
   - provider error rate
   - retry count
   - fallback activation count
   - precomputed cache hit rate
3. Add error reporting hooks for:
   - failed jobs
   - provider adapter exceptions
   - serialization failures
4. Add a basic operational dashboard or at least log/metric queries.

### Deliverables

- structured logs
- metrics dashboard
- error alerting hooks

### Acceptance Criteria

- Failed prediction/context jobs can be traced by job id.
- Provider latency and failure trends are visible.
- Engineers no longer need to inspect UI behavior alone to diagnose backend failures.

## Phase 7: Clean Up Remaining Coupling

### Goal

Finish the extraction by removing the remaining Streamlit leakage and legacy execution paths.

### Tasks

1. Eliminate Streamlit imports from backend/domain modules unless explicitly part of UI adapter code.
2. Remove deprecated synchronous execution flows once job-backed flows are proven.
3. Replace `run_async()` global event-loop bridging where it is still used for backend work.
4. Delete duplicate reset logic and dead compatibility code.
5. Tighten module boundaries through package-level ownership rules.

### Deliverables

- cleaner `src/` package with backend purity
- reduced technical debt after migration

### Acceptance Criteria

- `src/` backend modules are largely UI-agnostic.
- There is one supported execution model for long-running work.
- Legacy fallback code paths are intentionally retained only where product behavior requires them.

## Cross-Phase Work Items

These should run continuously across the plan.

### Testing

- Expand the current smoke suite with service-layer tests.
- Add repository tests for new persistence abstractions.
- Add integration tests for provider adapters.
- Add job lifecycle tests for submission, completion, failure, retry, and cancellation.

### Documentation

- Maintain an ADR log for major decisions:
  - job system choice
  - persistence schema
  - session aggregate design
  - provider adapter contract

### Rollout Strategy

- Use feature flags for job backend migration where possible.
- Migrate one workflow at a time.
- Preserve current UI behavior until backend parity is verified.

## Proposed Work Breakdown By Sprint

### Sprint 1

- Phase 0 complete
- service interface design approved
- start Phase 1 extraction for prediction and context

### Sprint 2

- Phase 1 complete for prediction, context, interpretation, projects
- Phase 2 session model introduced

### Sprint 3

- durable job system selected and scaffolded
- prediction flow migrated to durable jobs

### Sprint 4

- context, interpretation, and video migrated to durable jobs
- job observability baseline added

### Sprint 5

- Postgres/object storage repositories introduced
- user/project persistence migrated

### Sprint 6

- provider adapter normalization
- retry/timeout policy unified
- remaining coupling cleanup

## Key Risks

### Risk 1: Migration increases delivery friction

Mitigation:

- keep UI stable
- migrate one workflow at a time
- use smoke tests on every phase

### Risk 2: Durable jobs are introduced before service boundaries are clear

Mitigation:

- do not start Phase 3 until Phase 1 contracts are stable

### Risk 3: Project persistence migration breaks existing saved sessions

Mitigation:

- keep a compatibility import path for legacy JSON snapshots during at least one migration cycle

### Risk 4: Streamlit assumptions remain hidden in backend code

Mitigation:

- add explicit review rule and import checks

## Decision Gates

Before Phase 3:

- service layer merged
- typed session aggregate in place
- orchestration no longer primarily UI-owned

Before Phase 4:

- durable job model and ownership fields finalized

Before Phase 7 closure:

- logs and metrics available in the target environment
- no critical flow depends on process-local background threads

## Recommended Owners

- Backend lead: service extraction, job architecture, persistence design
- Platform/infrastructure: queue, Postgres, object storage, deployment changes
- Frontend/Streamlit owner: component adaptation and UI parity during migration
- QA or senior engineer: migration regression suite and rollout validation

## Success Definition

This plan is successful when:

- backend orchestration is service-owned, not component-owned
- analysis state is explicit and typed
- long-running jobs survive process restarts
- projects and users are stored in shared durable infrastructure
- provider integrations use a common reliability policy
- backend failures are diagnosable from logs and metrics
- Streamlit remains the UI shell rather than the backend control plane

## Immediate Next Actions

1. Approve the target migration shape and pick the durable job technology.
2. Create ADRs for:
   - service layer boundaries
   - session aggregate design
   - queue/worker stack
   - persistence stack
3. Open implementation tickets per phase and assign owners.
4. Start Phase 0 immediately, since it has low risk and improves every later phase.
