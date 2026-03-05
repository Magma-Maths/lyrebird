# Lyrebird Flow Reference

Every flow Lyrebird implements, shown as Mermaid diagrams. All events from the bot itself are silently ignored (loop prevention).

---

## Event Routing

```mermaid
flowchart LR
    PW["Public repo webhook"] --> PD["public-dispatch.yml<br/>(workflow_dispatch)"]
    PD --> HPE["handle-public-event.yml<br/>(private repo)"]
    HPE --> CLI["python -m lyrebird"]
    PI["Private repo<br/>issue event"] --> HPI["handle-private-issue.yml"]
    HPI --> CLI
    PC["Private repo<br/>comment event"] --> HPC["handle-private-comment.yml"]
    HPC --> CLI
    CLI --> LP{"Bot's own event?"}
    LP -- Yes --> IGN[Ignore]
    LP -- No --> DISP["dispatch.route()"]
    DISP --> HANDLER["Handler"]
```

---

## Public Events

### Public Issue Opened

```mermaid
flowchart TD
    A["Public issue opened"] --> B{"Mapping already<br/>exists?"}
    B -- "Yes (normal)" --> Z[Skip — idempotent]
    B -- "Yes (self-healed)" --> Z
    B -- No --> C["Create private issue<br/>[public #N] title"]
    C --> D["Mirror labels<br/>(auto-create missing)"]
    D --> E{"Issue type<br/>set? (Bug/Task/...)"}
    E -- Yes --> F["Mirror type<br/>to private"]
    E -- No --> G["Post mapping comment<br/>on public issue"]
    F --> G
```

### Public Issue Edited

```mermaid
flowchart TD
    A["Public issue edited"] --> B{"Mapping exists?"}
    B -- No --> Z["Skip"]
    B -- Yes --> C["Update private title<br/>→ [public #N] new title"]
    C --> D["Update private body<br/>(between BEGIN/END markers)"]
```

### Public Issue Closed

```mermaid
flowchart TD
    A["Public issue closed"] --> B{"Mapping exists?"}
    B -- No --> Z["Skip"]
    B -- Yes --> C["Post audit comment on private:<br/>'Public issue closed by @user'"]
    C --> D{"Closed by original<br/>reporter?"}
    D -- Yes --> E["Append '(original reporter)'<br/>to audit comment"]
    D -- No --> F["Close private issue"]
    E --> F
    F --> G{"state_reason<br/>provided?"}
    G -- Yes --> H["Close with state_reason<br/>(completed / not_planned)"]
    G -- No --> I["Close without state_reason"]
```

### Public Issue Reopened

```mermaid
flowchart TD
    A["Public issue reopened"] --> B{"Mapping exists?"}
    B -- No --> Z["Skip"]
    B -- Yes --> C["Remove all resolution:*<br/>and resolution:none labels<br/>from private"]
    C --> D["Post audit comment:<br/>'Public issue reopened by @user'"]
    D --> E["Reopen private issue"]
```

### Public Comment Created

```mermaid
flowchart TD
    A["Public comment created"] --> B{"Mapping exists?"}
    B -- No --> Z["Skip"]
    B -- Yes --> C["Build mirrored comment body<br/>(@author | permalink<br/>+ original text)"]
    C --> D["Post mirrored comment<br/>on private issue"]
```

### Public Comment Edited

```mermaid
flowchart TD
    A["Public comment edited"] --> B{"Mapping exists?"}
    B -- No --> Z["Skip"]
    B -- Yes --> C{"Mirrored comment<br/>found on private?"}
    C -- Yes --> D["Update mirrored comment<br/>in place"]
    C -- No --> E["Create new mirrored<br/>comment (self-heal)"]
```

### Public Comment Deleted

```mermaid
flowchart TD
    A["Public comment deleted"] --> B{"Mapping exists?"}
    B -- No --> Z["Skip"]
    B -- Yes --> C{"Mirrored comment<br/>found on private?"}
    C -- No --> Z2["Skip — nothing<br/>to tombstone"]
    C -- Yes --> D["Replace mirrored comment<br/>with tombstone:<br/>'🗑️ deleted by @user'"]
```

### Public Label Added/Removed

```mermaid
flowchart TD
    A["Public label<br/>added or removed"] --> B{"Mapping exists?"}
    B -- No --> Z["Skip"]
    B -- Yes --> C{"Action?"}
    C -- labeled --> D["Ensure label exists<br/>in private repo<br/>(auto-create if missing)"]
    D --> E["Add label to<br/>private issue"]
    C -- unlabeled --> F["Remove label from<br/>private issue"]
```

### Public Issue Typed/Untyped

```mermaid
flowchart TD
    A["Public issue type<br/>changed or removed"] --> B{"Mapping exists?"}
    B -- No --> Z["Skip"]
    B -- Yes --> C["Set same issue type<br/>on private issue<br/>(Bug/Task/Feature/none)"]
```

---

## Private Events

### Private Issue Closed

The public issue is **always closed immediately**. The resolution note is only posted if exactly one resolution label is present.

```mermaid
flowchart TD
    A["Private issue closed"] --> B{"Mirrored issue?"}
    B -- No --> Z["Do nothing"]
    B -- Yes --> C{"Public already<br/>closed?"}
    C -- Yes --> Z
    C -- No --> D{"How many resolution<br/>labels on private?"}
    D -- "Exactly 1" --> E["Post predefined note<br/>on public issue"]
    E --> F["Close public with<br/>state_reason"]
    D -- "0 or >1" --> G["Close public issue<br/>(no comment)"]
    G --> H["Delayed check runs<br/>after 5 min ⏱️"]
```

### Delayed Close Check (5 min after close)

A second workflow job runs after a 5-minute delay in the workflow. It re-checks the issue state and nudges if no resolution was provided.

```mermaid
flowchart TD
    A["Delayed check fires<br/>(5 min after close)"] --> B{"Mirrored issue?"}
    B -- No --> Z["Do nothing"]
    B -- Yes --> C{"Issue still<br/>closed?"}
    C -- No --> D["Bail — reopened<br/>during grace period"]
    C -- Yes --> E{"Exactly 1 resolution<br/>label?<br/>(excl. resolution:none)"}
    E -- Yes --> F["Do nothing —<br/>already handled"]
    E -- "0 or >1" --> G{"resolution:none<br/>already present?"}
    G -- No --> H["Add resolution:none<br/>label"]
    G -- Yes --> I
    H --> I["Post nudge comment<br/>(message varies:<br/>0 → 'add one' / >1 → 'remove extras')"]
```

### Private Issue Reopened

```mermaid
flowchart TD
    A["Private issue reopened"] --> B["Remove all resolution:*<br/>labels + resolution:none<br/>from private"]
    B --> C["Post audit comment:<br/>'reopened by @user'"]
    C --> D{"Mirrored issue?"}
    D -- No --> Z["Done"]
    D -- Yes --> E{"Public issue<br/>is closed?"}
    E -- No --> Z
    E -- Yes --> F["Reopen public issue"]
    F --> G["Post 'reopened for<br/>further investigation'<br/>on public"]
```

### Private Label Added/Removed

```mermaid
flowchart TD
    A["Private label<br/>added or removed"] --> B{"Mirrored issue?"}
    B -- No --> Z["Do nothing"]
    B -- Yes --> C{"Label exists on<br/>public repo?"}
    C -- No --> Z2["Skip — private-only<br/>label"]
    C -- Yes --> D{"Action?"}
    D -- labeled --> E["Add label to<br/>public issue"]
    D -- unlabeled --> F["Remove label from<br/>public issue"]
    E --> G{"Resolution label added<br/>AND issue is closed?"}
    G -- No --> Z
    G -- Yes --> H{"Exactly 1 resolution<br/>label on private?"}
    H -- No --> Z
    H -- Yes --> I["Post predefined note<br/>on public"]
    I --> J{"Public already<br/>closed?"}
    J -- No --> K["Close public with<br/>state_reason"]
    J -- Yes --> L{"resolution:none<br/>present?"}
    K --> L
    L -- Yes --> M["Remove resolution:none<br/>from private"]
    L -- No --> Z
```

### Private Issue Typed/Untyped

```mermaid
flowchart TD
    A["Private issue type<br/>changed or removed"] --> B{"Mirrored issue?"}
    B -- No --> Z["Skip"]
    B -- Yes --> C["Set same issue type<br/>on public issue<br/>(Bug/Task/Feature/none)"]
```

### `/anon` Slash Command

```mermaid
flowchart TD
    A["/anon message<br/>on private issue"] --> B{"Mirrored issue?"}
    B -- No --> C["Post error:<br/>'not linked to<br/>a public issue'"]
    B -- Yes --> D["Post message on<br/>public issue"]
    D --> E["Post acknowledgment<br/>on private:<br/>'Posted to public: URL'"]
    E --> F{"Issue is closed?"}
    F -- No --> Z["Done"]
    F -- Yes --> G{"resolution:none<br/>present?"}
    G -- Yes --> H["Remove resolution:none"]
    G -- No --> I{"Any real resolution<br/>label present?<br/>(excl. resolution:none)"}
    H --> I
    I -- Yes --> Z
    I -- No --> J["Add resolution:custom"]
```

---

## Resolution Labels

| Label | Purpose |
|-------|---------|
| `resolution:completed` | Resolved as completed — posts fix note |
| `resolution:not-planned` | Resolved as not planned — posts decline note |
| `resolution:cannot-reproduce` | Cannot reproduce — asks for more info |
| `resolution:custom` | Custom message posted via `/anon` — no auto note |
| `resolution:none` | Nudge label — no resolution posted yet (added by delayed check) |

---

## Typical Scenarios

### Happy path: close with label
1. Maintainer adds `resolution:completed` on private issue
2. Maintainer closes private issue
3. Lyrebird posts "This has been fixed..." on public and closes it
4. Delayed check fires after 5 min, sees 1 label, does nothing

### Close first, label later (within 5 min)
1. Maintainer closes private issue (no resolution label)
2. Lyrebird closes public issue with no comment
3. Within 5 min, maintainer adds `resolution:not-planned`
4. Label handler posts note on public, removes `resolution:none` if present
5. Delayed check fires, sees 1 label, does nothing

### Close with `/anon` custom message
1. Maintainer closes private issue
2. Lyrebird closes public issue
3. Maintainer uses `/anon Thanks for the report!`
4. Lyrebird posts message on public, adds `resolution:custom` on private
5. Delayed check fires, sees `resolution:custom`, does nothing

### No action taken (nudge)
1. Maintainer closes private issue
2. Lyrebird closes public issue
3. 5 minutes pass with no action
4. Delayed check adds `resolution:none` and posts nudge on private
5. Maintainer can then add a label or use `/anon`
