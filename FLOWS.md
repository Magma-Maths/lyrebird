# Lyrebird Flow Reference

Every flow Lyrebird implements, shown as Mermaid diagrams. All events from the bot itself are silently ignored (loop prevention).

---

## Event Routing

```mermaid
flowchart LR
    PW["Public repo webhook"] --> PD["public-dispatch.yml\n(workflow_dispatch)"]
    PD --> HPE["handle-public-event.yml\n(private repo)"]
    HPE --> CLI["python -m lyrebird"]
    PI["Private repo\nissue event"] --> HPI["handle-private-issue.yml"]
    HPI --> CLI
    PC["Private repo\ncomment event"] --> HPC["handle-private-comment.yml"]
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
    A["Public issue opened"] --> B{"Mapping already\nexists?"}
    B -- "Yes (normal)" --> Z[Skip — idempotent]
    B -- "Yes (self-healed)" --> Z
    B -- No --> C["Create private issue\n[public #N] title"]
    C --> D["Mirror labels\n(auto-create missing)"]
    D --> E{"Issue type\nset? (Bug/Task/...)"}
    E -- Yes --> F["Mirror type\nto private"]
    E -- No --> G["Post mapping comment\non public issue"]
    F --> G
```

### Public Issue Edited

```mermaid
flowchart TD
    A["Public issue edited"] --> B{"Mapping exists?"}
    B -- No --> Z["Skip"]
    B -- Yes --> C["Update private title\n→ [public #N] new title"]
    C --> D["Update private body\n(between BEGIN/END markers)"]
```

### Public Issue Closed

```mermaid
flowchart TD
    A["Public issue closed"] --> B{"Mapping exists?"}
    B -- No --> Z["Skip"]
    B -- Yes --> C["Post audit comment on private:\n'Public issue closed by @user'"]
    C --> D{"Closed by original\nreporter?"}
    D -- Yes --> E["Append '(original reporter)'\nto audit comment"]
    D -- No --> F["Close private issue"]
    E --> F
    F --> G{"state_reason\nprovided?"}
    G -- Yes --> H["Close with state_reason\n(completed / not_planned)"]
    G -- No --> I["Close without state_reason"]
```

### Public Issue Reopened

```mermaid
flowchart TD
    A["Public issue reopened"] --> B{"Mapping exists?"}
    B -- No --> Z["Skip"]
    B -- Yes --> C["Remove all resolution:*\nand resolution:none labels\nfrom private"]
    C --> D["Post audit comment:\n'Public issue reopened by @user'"]
    D --> E["Reopen private issue"]
```

### Public Comment Created

```mermaid
flowchart TD
    A["Public comment created"] --> B{"Mapping exists?"}
    B -- No --> Z["Skip"]
    B -- Yes --> C["Build mirrored comment body\n(@author | permalink\n+ original text)"]
    C --> D["Post mirrored comment\non private issue"]
```

### Public Comment Edited

```mermaid
flowchart TD
    A["Public comment edited"] --> B{"Mapping exists?"}
    B -- No --> Z["Skip"]
    B -- Yes --> C{"Mirrored comment\nfound on private?"}
    C -- Yes --> D["Update mirrored comment\nin place"]
    C -- No --> E["Create new mirrored\ncomment (self-heal)"]
```

### Public Comment Deleted

```mermaid
flowchart TD
    A["Public comment deleted"] --> B{"Mapping exists?"}
    B -- No --> Z["Skip"]
    B -- Yes --> C{"Mirrored comment\nfound on private?"}
    C -- No --> Z2["Skip — nothing\nto tombstone"]
    C -- Yes --> D["Replace mirrored comment\nwith tombstone:\n'🗑️ deleted by @user'"]
```

### Public Label Added/Removed

```mermaid
flowchart TD
    A["Public label\nadded or removed"] --> B{"Mapping exists?"}
    B -- No --> Z["Skip"]
    B -- Yes --> C{"Action?"}
    C -- labeled --> D["Ensure label exists\nin private repo\n(auto-create if missing)"]
    D --> E["Add label to\nprivate issue"]
    C -- unlabeled --> F["Remove label from\nprivate issue"]
```

### Public Issue Typed/Untyped

```mermaid
flowchart TD
    A["Public issue type\nchanged or removed"] --> B{"Mapping exists?"}
    B -- No --> Z["Skip"]
    B -- Yes --> C["Set same issue type\non private issue\n(Bug/Task/Feature/none)"]
```

---

## Private Events

### Private Issue Closed

The public issue is **always closed immediately**. The resolution note is only posted if exactly one resolution label is present.

```mermaid
flowchart TD
    A["Private issue closed"] --> B{"Mirrored issue?"}
    B -- No --> Z["Do nothing"]
    B -- Yes --> C{"Public already\nclosed?"}
    C -- Yes --> Z
    C -- No --> D{"How many resolution\nlabels on private?"}
    D -- "Exactly 1" --> E["Post predefined note\non public issue"]
    E --> F["Close public with\nstate_reason"]
    D -- "0 or >1" --> G["Close public issue\n(no comment)"]
    G --> H["Delayed check runs\nafter 5 min ⏱️"]
```

### Delayed Close Check (5 min after close)

A second workflow job runs after a 5-minute grace period (GitHub Environment Wait Timer). It re-checks the issue state and nudges if no resolution was provided.

```mermaid
flowchart TD
    A["Delayed check fires\n(5 min after close)"] --> B{"Mirrored issue?"}
    B -- No --> Z["Do nothing"]
    B -- Yes --> C{"Issue still\nclosed?"}
    C -- No --> D["Bail — reopened\nduring grace period"]
    C -- Yes --> E{"Exactly 1 resolution\nlabel?\n(excl. resolution:none)"}
    E -- Yes --> F["Do nothing —\nalready handled"]
    E -- "0" --> G0{"resolution:none\nalready present?"}
    E -- ">1" --> G1{"resolution:none\nalready present?"}
    G0 -- No --> H0["Add resolution:none\nlabel"]
    G0 -- Yes --> I0["Post nudge:\n'Add exactly one resolution\nlabel, or use /anon'"]
    H0 --> I0
    G1 -- No --> H1["Add resolution:none\nlabel"]
    G1 -- Yes --> I1["Post nudge:\n'Multiple labels present.\nRemove extras, or use /anon'"]
    H1 --> I1
```

### Private Issue Reopened

```mermaid
flowchart TD
    A["Private issue reopened"] --> B["Remove all resolution:*\nlabels + resolution:none\nfrom private"]
    B --> C["Post audit comment:\n'reopened by @user'"]
    C --> D{"Mirrored issue?"}
    D -- No --> Z["Done"]
    D -- Yes --> E{"Public issue\nis closed?"}
    E -- No --> Z
    E -- Yes --> F["Reopen public issue"]
    F --> G["Post 'reopened for\nfurther investigation'\non public"]
```

### Private Label Added/Removed

```mermaid
flowchart TD
    A["Private label\nadded or removed"] --> B{"Mirrored issue?"}
    B -- No --> Z["Do nothing"]
    B -- Yes --> C{"Label exists on\npublic repo?"}
    C -- No --> Z2["Skip — private-only\nlabel"]
    C -- Yes --> D{"Action?"}
    D -- labeled --> E["Add label to\npublic issue"]
    D -- unlabeled --> F["Remove label from\npublic issue"]
    E --> G{"Resolution label added\nAND issue is closed?"}
    G -- No --> Z
    G -- Yes --> H{"Exactly 1 resolution\nlabel on private?"}
    H -- No --> Z
    H -- Yes --> I{"Public already\nclosed?"}
    I -- Yes --> Z
    I -- No --> J["Post predefined note\non public"]
    J --> K["Close public with\nstate_reason"]
    K --> L{"resolution:none\npresent?"}
    L -- Yes --> M["Remove resolution:none\nfrom private"]
    L -- No --> Z
```

### Private Issue Typed/Untyped

```mermaid
flowchart TD
    A["Private issue type\nchanged or removed"] --> B{"Mirrored issue?"}
    B -- No --> Z["Skip"]
    B -- Yes --> C["Set same issue type\non public issue\n(Bug/Task/Feature/none)"]
```

### `/anon` Slash Command

```mermaid
flowchart TD
    A["/anon message\non private issue"] --> B{"Mirrored issue?"}
    B -- No --> C["Post error:\n'not linked to\na public issue'"]
    B -- Yes --> D["Post message on\npublic issue"]
    D --> E["Post acknowledgment\non private:\n'Posted to public: URL'"]
    E --> F{"Issue is closed?"}
    F -- No --> Z["Done"]
    F -- Yes --> G{"resolution:none\npresent?"}
    G -- Yes --> H["Remove resolution:none"]
    G -- No --> I{"Any real resolution\nlabel present?\n(excl. resolution:none)"}
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
