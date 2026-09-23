# Diagrams

Both diagrams are Mermaid, so they render on GitHub and stay diffable.

## System

```mermaid
flowchart LR
    user([Student · Faculty · Coordinator · Admin])

    subgraph browser["Browser"]
        spa["React 19 + TypeScript SPA<br/>Vite · Tailwind · TanStack Query"]
    end

    subgraph api["FastAPI (modular monolith)"]
        routers["Routers<br/><i>HTTP only</i>"]
        services["Services<br/><i>business rules</i>"]
        policies["Policies<br/><i>ownership · scope</i>"]
        ml["app/ml<br/><i>TF-IDF · embeddings · scoring</i>"]
        jobs["APScheduler job<br/><i>deadline reminders</i>"]
        events["Event bus<br/><i>in-process, in-transaction</i>"]
    end

    subgraph data["PostgreSQL 17"]
        tables[("35 tables")]
        ext["pg_trgm · btree_gist · pgvector"]
    end

    user --> spa
    spa -- "JSON over HTTPS<br/>Bearer access token<br/>httpOnly refresh cookie" --> routers
    routers --> services
    services --> policies
    services --> events
    services --> ml
    events --> services
    jobs --> services
    services --> tables
    ml --> tables
    tables --- ext
```

Three things this picture is meant to make obvious: routers do no business
logic, every write goes through a policy before it touches a table, and the
event bus runs *inside* the caller's transaction (so a notification and the
thing it describes commit together).

## Entity relationships

Abbreviated: join tables and audit-style tables are described in the notes
rather than drawn, to keep the diagram readable.

```mermaid
erDiagram
    SCHOOLS ||--o{ DEPARTMENTS : contains
    DEPARTMENTS ||--o{ USERS : "belong to"
    USERS ||--o| STUDENT_PROFILES : has
    USERS ||--o| RESEARCHER_PROFILES : has
    USERS ||--o{ USER_SKILLS : claims
    USERS ||--o{ USER_RESEARCH_AREAS : claims
    SKILLS ||--o{ USER_SKILLS : "claimed in"
    RESEARCH_AREAS ||--o{ USER_RESEARCH_AREAS : "claimed in"
    RESEARCH_AREAS ||--o{ RESEARCH_AREAS : "parent of"

    USERS ||--o{ PROJECTS : owns
    PROJECTS ||--o{ PROJECT_MEMBERS : has
    USERS ||--o{ PROJECT_MEMBERS : "joins as"
    PROJECTS ||--o{ OPPORTUNITIES : "advertises"
    OPPORTUNITIES ||--o{ APPLICATIONS : receives
    USERS ||--o{ APPLICATIONS : submits
    APPLICATIONS ||--o{ APPLICATION_EVENTS : "timeline of"

    USERS ||--o{ PUBLICATIONS : creates
    PUBLICATIONS ||--o{ PUBLICATION_AUTHORS : "authored by"
    USERS ||--o{ PUBLICATION_AUTHORS : "appears as"
    PROJECTS ||--o{ PROJECT_PUBLICATIONS : cites
    PUBLICATIONS ||--o{ PROJECT_PUBLICATIONS : "cited by"

    USERS ||--o{ COLLABORATION_REQUESTS : sends
    DEPARTMENTS ||--o{ FACILITIES : runs
    FACILITIES ||--o{ EQUIPMENT : holds
    EQUIPMENT ||--o{ BOOKINGS : "booked in"
    USERS ||--o{ BOOKINGS : books

    FUNDING_OPPORTUNITIES ||--o{ FUNDING_RESEARCH_AREAS : "targets"
    RESEARCH_AREAS ||--o{ FUNDING_RESEARCH_AREAS : "targeted by"
    USERS ||--o{ SAVED_ITEMS : saves
    USERS ||--o{ NOTIFICATIONS : receives
    USERS ||--o{ CONTENT_REPORTS : reports
```

Notes on the parts not drawn:

- **`audit_logs`** is append-only and references any entity by
  `(entity_type, entity_id)` — no foreign keys, by design.
- **`entity_embeddings`** stores one vector per `(entity_type, entity_id,
  model_name)`, likewise without foreign keys: it points at five different
  tables, and searches join back to the real table.
- **`saved_items`** points at exactly one of a project, opportunity,
  researcher or funding call (`CHECK num_nonnulls(...) = 1`).
- **`bookings.period`** is a `tstzrange` with an exclusion constraint, which
  is what makes double-booking impossible rather than merely unlikely.
- **`refresh_tokens`** are hashed, rotated, and grouped into families so a
  replayed token revokes the whole family.
- Join tables (`project_skills`, `project_research_areas`,
  `opportunity_skills`, `tag_aliases`, `tag_suggestions`) follow the obvious
  shape.
