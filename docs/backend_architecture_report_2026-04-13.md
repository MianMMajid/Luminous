# Backend Architecture Report

Date: 2026-04-13  
Repository: `BioxYC` / `Luminous`  
Audience: Senior backend engineer  
Scope: Current backend/runtime architecture after the initial service-layer refactor.

## Executive Summary

The backend is still an in-process Streamlit monolith, but it is no longer purely UI-owned. The most important architectural improvement since the previous baseline is the introduction of an explicit application-service layer for session state, prediction dispatch, context retrieval, and project serialization:

- `src/analysis_session.py:22-390`
- `src/services/analysis_session_service.py:20-76`
- `src/services/prediction_service.py:19-216`
- `src/services/context_service.py:10-86`
- `src/services/project_service.py:9-38`

This is a meaningful step in the right direction. State initialization and reset are now centralized, project serialization is no longer embedded directly inside UI components, and the primary prediction/context orchestration path has been extracted behind service interfaces. That materially improves testability and makes the next backend refactor tractable.

The system is still not a separated backend architecture. `st.session_state` remains the runtime source of truth, long-running jobs are still daemon threads inside the Streamlit process, persistence is still local SQLite plus JSON files, and several legacy synchronous execution paths still exist beside the new service abstractions.

Current conclusion: the architecture is improved and better structured than before, but it is still in transition. The first extraction phase is partially complete; durability, storage abstraction, observability, and full backend/UI separation are still outstanding.

## What Changed Since The Previous Baseline

The following recommendations from the earlier review have been implemented at least partially:

### 1. Session state ownership is centralized

`AnalysisSessionService.ensure_defaults()` now initializes baseline state in `app.py:188-213`, and query reset flows route through `AnalysisSessionService.reset_analysis()` in:

- `app.py:211-213`
- `components/query_input.py:129-149`

The actual state rules now live in `src/analysis_session.py`:

- default keys: `src/analysis_session.py:22-46`
- reset contract: `src/analysis_session.py:48-101`, `182-206`
- typed aggregate: `src/analysis_session.py:152-164`

This removes duplicated reset logic from the main app flow and makes state transition rules explicit in one place.

### 2. Prediction orchestration has a service boundary

The active prediction path in `components/structure_viewer.py:315-341` now delegates to `PredictionService.run_prediction()` in `src/services/prediction_service.py:21-81`.

That service owns:

- precomputed example hydration: `src/services/prediction_service.py:150-216`
- Tamarind submission: `src/services/prediction_service.py:96-120`
- Modal submission: `src/services/prediction_service.py:122-148`
- RCSB fallback dispatch: `src/services/prediction_service.py:59-73`

The UI still renders status messages, but backend selection and dispatch policy are no longer embedded directly in the component's main path.

### 3. Context and project flows have service boundaries

The context tab now delegates background task submission to `ContextService`:

- `components/context_panel.py:52-57`
- `components/context_panel.py:59-64`
- `components/context_panel.py:372-374`

The service boundary is in `src/services/context_service.py:10-86`.

Project serialization and restore are now routed through `ProjectService`:

- `components/project_manager.py:135-151`
- `src/services/project_service.py:9-38`

### 4. Result promotion now reuses shared session-state logic

The notification poller still owns async completion handling, but prediction result storage now goes through the centralized session service rather than bespoke component logic:

- `components/notification_poller.py:196-218`
- `src/analysis_session.py:219-256`

This is a clean improvement because PDB parsing and `PredictionResult` construction now have one canonical path.

## Current Runtime Topology

```text
Browser
  -> Streamlit app (`app.py`)
    -> UI components (`components/*.py`)
      -> application services (`src/services/*.py`)
        -> session/state module (`src/analysis_session.py`)
        -> background-task wrappers (`src/background_tasks.py`)
        -> in-process task runtime (`src/task_manager.py`)
        -> external providers
           - Tamarind Bio
           - Modal
           - RCSB / UniProt / PubMed / Open Targets / ChEMBL / others
           - Anthropic / MCP connectors

Persistence
  - SQLite user profiles: `src/user_store.py`
  - JSON project snapshots on local disk: `data/projects/*.json`
  - precomputed example payloads: `data/precomputed/*`
```

There is still no standalone backend process or API boundary. The Streamlit process is still responsible for:

- the web runtime
- service invocation
- in-memory state ownership
- background task dispatch
- async completion polling
- persistence I/O
- provider integration

The improvement is structural, not topological: orchestration is better organized, but it still executes inside the same application process.

## Current Backend Flow

### 1. Session bootstrap and query reset

Session defaults are initialized once in `app.py:188-191`. New-query invalidation now routes through `AnalysisSessionService.reset_analysis()` in `components/query_input.py:129-149`, which delegates to `src/analysis_session.py:182-206`.

This is the main state-management improvement in the current architecture.

### 2. Query state promotion

Parsed query promotion is now centralized through `AnalysisSessionService.set_query()`:

- caller: `components/query_input.py:145-149`
- implementation: `src/services/analysis_session_service.py:36-42`
- underlying state write: `src/analysis_session.py:209-216`

### 3. Prediction dispatch

The active path in `components/structure_viewer.py:315-341` calls `PredictionService.run_prediction()`, which enforces this order:

1. Precomputed example payloads
2. Tamarind Boltz-2 background submission
3. Modal H100 background submission
4. RCSB experimental structure fallback

Relevant code:

- `src/services/prediction_service.py:21-81`
- `src/services/prediction_service.py:83-148`
- `src/services/prediction_service.py:150-216`

### 4. Background execution

The async model is unchanged in core design. `src/task_manager.py:32-140` still manages daemon-thread execution, while `_SessionProxy` in `src/task_manager.py:183-205` keeps one task manager per Streamlit session.

This remains the strongest current concurrency boundary in the system.

### 5. Result promotion and notifications

`components/notification_poller.py:33-95` remains the async completion boundary. It:

- polls active tasks
- writes finished results into session state
- surfaces success or failure toasts
- triggers reruns for critical task completions

Prediction result writeback now reuses `AnalysisSessionService.store_prediction()`:

- `components/notification_poller.py:196-218`

### 6. Biological context and interpretation

Context fetch and interpretation submission are now routed through `ContextService`:

- background submission: `src/services/context_service.py:10-27`
- interpretation submission: `src/services/context_service.py:29-51`
- synchronous fallback helpers still present: `src/services/context_service.py:53-86`

The UI entry points are in `components/context_panel.py:24-64` and `components/context_panel.py:332-374`.

### 7. Project serialization

Serialization logic is now centralized in `src/analysis_session.py:327-390`, exposed via `ProjectService`, and used by the project manager component:

- `components/project_manager.py:31-151`
- `src/services/project_service.py:9-38`

This is cleaner than the earlier component-owned serializer, but the underlying storage target is still local disk.

## What Is Working Well

- The service extraction is real, not cosmetic. Prediction, context, project, and session concerns now have explicit modules under `src/services/`.
- Session defaulting, reset, prediction storage, trust-audit creation, and serialization rules are centralized in `src/analysis_session.py:22-390`.
- The new `AnalysisSession` model in `src/analysis_session.py:152-164` gives the codebase a typed aggregate to build on, even though it is not yet the sole runtime source of truth.
- The per-session task manager remains a pragmatic and correct prototype design for single-process isolation. `src/task_manager.py:89-181` and `src/task_manager.py:183-205`
- Generation-based invalidation still protects against stale thread writeback after clears or resubmits. `src/task_manager.py:80-96`, `src/task_manager.py:107-124`, `src/task_manager.py:173-181`
- Tamarind integration is still the best-structured external client in the codebase. Shared HTTP client reuse and polling backoff are both reasonable. `src/tamarind_client.py:33-45`, `src/tamarind_client.py:145-181`
- The current smoke suite still passes in the project virtualenv: `./.venv/bin/python scripts/test_full_pipeline.py` -> `79/79`.

## Findings

### 1. High: The architecture is now layered, but Streamlit still owns the application runtime

The service boundary exists, but it is still invoked directly from Streamlit components and still mutates `st.session_state` through `MutableMapping` interfaces.

Evidence:

- session bootstrap: `app.py:188-213`
- query reset and set: `components/query_input.py:129-149`
- prediction entry point: `components/structure_viewer.py:315-341`
- service/session coupling: `src/services/analysis_session_service.py:20-76`
- state mutation core: `src/analysis_session.py:167-256`

Why this matters:

- It is easier to test than before, but still not reusable from a worker, API, or CLI boundary without carrying Streamlit session semantics along
- There is still no hard separation between transport/UI concerns and application orchestration
- The service layer is currently a thin facade over session-state mutation rather than a runtime-independent application core

Recommendation:

Make `AnalysisSession` the authoritative application aggregate rather than a derived convenience model. Services should operate on typed session/domain objects and repositories, with Streamlit acting only as a caller and renderer.

### 2. High: `st.session_state` remains the live source of truth

The refactor centralized the rules, but did not change the runtime ownership model. The application still stores its canonical working state in `st.session_state`, then occasionally derives a typed `AnalysisSession` view from it.

Evidence:

- default keys: `src/analysis_session.py:22-46`
- reset contract: `src/analysis_session.py:182-206`
- typed model definition: `src/analysis_session.py:152-164`
- typed model build: `src/analysis_session.py:327-347`
- project save path still serializes from session state: `src/analysis_session.py:350-390`

Why this matters:

- State is still string-keyed and mutation-based
- The typed aggregate is not yet the enforcing boundary
- Partial writes or out-of-band UI mutations can still produce inconsistent but valid-looking state
- Persistence remains coupled to internal session keys and cache prefixes

Recommendation:

Move toward an explicit state machine or aggregate-root model:

- `AnalysisSession.start_query()`
- `AnalysisSession.attach_prediction()`
- `AnalysisSession.attach_trust_audit()`
- `AnalysisSession.attach_bio_context()`
- `AnalysisSession.attach_interpretation()`
- `AnalysisSession.clear_analysis()`

Then keep `st.session_state` as a transport/cache layer, not the domain store.

### 3. High: Async execution is still process-local and non-durable

The refactor did not change the execution substrate. Long-running work is still handled by daemon threads inside the Streamlit process and tracked only in memory.

Evidence:

- task lifecycle and thread worker: `src/task_manager.py:32-140`
- session proxy: `src/task_manager.py:183-205`
- poller completion boundary: `components/notification_poller.py:33-95`

Why this matters:

- Jobs disappear on process restart
- There is no durable job table, retry ledger, or worker audit trail
- Horizontal scaling still requires sticky session assumptions or a different execution model
- Operational debugging remains weak because job history is transient

Recommendation:

Introduce a durable execution layer before expanding background-task coverage further:

- Redis-backed queue plus workers (`RQ`, `Arq`, `Celery`)
- or a workflow engine (`Temporal`)

Persist job state outside Streamlit and treat the notification poller as a frontend subscriber, not the job authority.

### 4. Medium-High: The execution model is still mixed; legacy synchronous paths remain

The primary path is now backgrounded through services, but older inline code paths still exist beside it.

Evidence:

- active service-driven path: `components/structure_viewer.py:315-341`
- legacy background submit helper still present: `components/structure_viewer.py:344-392`
- legacy blocking Tamarind path still present: `components/structure_viewer.py:411-450`
- legacy blocking Modal path still present: `components/structure_viewer.py:453-477`
- synchronous context/interpretation path still present: `components/context_panel.py:332-374`
- synchronous helper entry points still exposed in `ContextService`: `src/services/context_service.py:53-86`

Why this matters:

- The codebase currently supports multiple orchestration styles for the same domain action
- Future changes can accidentally patch the legacy path and miss the primary one, or vice versa
- UI-thread blocking behavior is still possible for certain flows

Recommendation:

Retire or quarantine the legacy synchronous paths once the service-based background paths are fully trusted. One execution abstraction per long-running domain action should be the goal.

### 5. Medium: Persistence has a better boundary, but the storage model is still local and single-instance oriented

Project save/load is cleaner, but it still writes JSON snapshots into `data/projects/`, and user state is still local SQLite.

Evidence:

- local project save/load UI: `components/project_manager.py:31-129`
- project serializer boundary: `components/project_manager.py:135-151`
- storage abstraction is still thin and local: `src/services/project_service.py:9-38`
- serialized session model: `src/analysis_session.py:350-390`
- user store: `src/user_store.py:13-106`

Why this matters:

- Project files fragment across instances in any scaled deployment
- SQLite is acceptable for local prototyping but weak as a multi-user control plane
- There is still no repository abstraction over durable storage and no ownership/authorization model around project assets

Recommendation:

Replace local persistence with:

- Postgres for users, projects, analysis metadata, and job state
- object storage for large artifacts and exports
- repository interfaces under `src/repositories/` or similar

### 6. Medium: Integration resilience is still provider-specific and inconsistent

Tamarind has reasonable polling behavior, but retry/timeout policy is still encoded ad hoc across providers and wrappers.

Evidence:

- shared Tamarind HTTP client: `src/tamarind_client.py:33-45`
- Tamarind submit path has no retry layer: `src/tamarind_client.py:118-142`
- Tamarind polling has backoff: `src/tamarind_client.py:145-181`
- Tamarind result download remains single-shot: `src/tamarind_client.py:209-242`
- RCSB background fetch is single-shot: `src/background_tasks.py:90-138`
- context providers fail over implicitly inside wrapper code: `src/background_tasks.py:167-183`, `src/services/context_service.py:57-86`

Why this matters:

- Error handling differs by provider and by call path
- There is no centralized retry budget, timeout policy, or idempotency model
- Operational review remains difficult because resilience behavior is distributed across provider-specific modules

Recommendation:

Introduce a shared integration policy layer:

- standard timeout classes
- retryable vs non-retryable exception types
- jittered backoff helpers
- explicit fallback policy and telemetry hooks

### 7. Medium: Observability is still minimal

The refactor improved structure, but it did not add real backend telemetry. Most runtime visibility is still UI toasts plus in-memory task state.

Evidence:

- task completion notifications are UI toasts: `components/notification_poller.py:63-94`
- task state is transient memory in `src/task_manager.py:51-57`
- no meaningful structured logging layer was introduced in the refactor

Why this matters:

- No durable audit trail exists for failed or slow jobs
- Provider latency, fallback frequency, and retry counts cannot be measured reliably
- Root-cause analysis still depends on local reproduction

Recommendation:

Add:

- structured logs with correlation IDs
- provider/task timing metrics
- success/failure counters
- fallback and cache-hit counters
- job lifecycle events

### 8. Medium: Backend purity improved, but is not complete

The good news is that the new service modules do not import Streamlit directly. The remaining issue is that the domain/application layer is still designed around Streamlit session mutation and component-triggered side effects.

Evidence:

- service modules are UI-free: `src/services/*.py`
- application state still arrives as `MutableMapping[str, Any]`: `src/services/analysis_session_service.py:22-75`, `src/services/prediction_service.py:21-29`

Why this matters:

- The refactor lowered coupling, but did not yet produce a transport-independent backend core
- A future API server or worker process would still need a second extraction step

Recommendation:

Push one step further:

- domain objects and repositories below
- Streamlit component adapters above
- no direct session dictionary mutation in the long-term service core

## Updated Recommendation Set

### Phase 1: Consolidation of the current refactor

Status: partially implemented

Complete the work already started:

- make `AnalysisSession` authoritative rather than derived
- remove remaining duplicated state writes in components
- retire legacy synchronous prediction/context paths
- move more component-owned orchestration into services

### Phase 2: Durable job execution

Status: not started

Deliverables:

- durable job queue
- worker processes
- persisted job records
- explicit retry/cancel semantics
- UI polling against persisted job status rather than in-memory task state

### Phase 3: Persistence abstraction and storage migration

Status: not started

Deliverables:

- repository interfaces
- Postgres-backed user/project/job metadata
- object storage for artifacts
- schema migrations
- ownership and authorization boundaries

### Phase 4: Provider adapters and resilience policy

Status: not started

Deliverables:

- provider adapter package per integration
- shared timeout/retry policy
- consistent exception taxonomy
- contract tests for provider behavior

### Phase 5: Observability

Status: not started

Deliverables:

- structured logs
- metrics
- correlation IDs
- provider/job dashboards

## Suggested Review Questions For Senior Backend Review

- Is the current goal to finish the application-layer extraction inside Streamlit, or to introduce a separate backend runtime now?
- Should durable jobs be prioritized before any further expansion of long-running workflows?
- Is `AnalysisSession` the right aggregate boundary, or should the domain be split into analysis/job/project aggregates?
- Which persistence boundary should be introduced first: projects, jobs, or user profiles?
- Which provider should become the reference adapter for timeout, retry, and telemetry policy?

## Validation Notes

Reviewed code paths:

- `app.py`
- `components/query_input.py`
- `components/structure_viewer.py`
- `components/context_panel.py`
- `components/notification_poller.py`
- `components/project_manager.py`
- `src/analysis_session.py`
- `src/services/analysis_session_service.py`
- `src/services/prediction_service.py`
- `src/services/context_service.py`
- `src/services/project_service.py`
- `src/task_manager.py`
- `src/background_tasks.py`
- `src/tamarind_client.py`
- `src/user_store.py`

Validation reference from the current branch state:

```bash
./.venv/bin/python scripts/test_full_pipeline.py
```

Result:

- `79 passed, 0 failed`

## Bottom Line

The backend architecture is better than the original report described. The codebase now has a real service layer and a centralized session-state module, which means the first architectural extraction phase has begun successfully.

It is still not a separated backend. The system remains a Streamlit-hosted application runtime with in-memory jobs, local-disk persistence, and `st.session_state` as the working state store. The next meaningful step is no longer "introduce a service layer" because that has started; the next step is to finish that extraction and then externalize execution and persistence before more operational complexity accumulates around the current runtime.
