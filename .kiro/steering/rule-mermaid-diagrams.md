# Rule: Use Mermaid diagrams for architectural exploration

**Always-loaded protocol rule.**

## The rule

When exploring, proposing, or documenting architecture — use **Mermaid diagrams** as the default visual notation. Every architectural exploration or deviation from the current design MUST include at least one Mermaid diagram that makes the proposal concrete.

## When to produce a Mermaid diagram

- Proposing a new component or service boundary
- Exploring data flow between systems
- Documenting sequence of operations across boundaries
- Comparing architectural options (one diagram per option)
- Showing deviation from the current architecture
- Explaining event-driven flows or state machines
- Mapping deployment topology

## Preferred diagram types by context

| Context | Mermaid type |
|---|---|
| Component relationships | `graph TD` or `C4Context` |
| Request/response flows | `sequenceDiagram` |
| State transitions | `stateDiagram-v2` |
| Data pipeline stages | `flowchart LR` |
| Deployment topology | `graph TD` with subgraphs |
| Decision trees | `flowchart TD` |
| Entity relationships | `erDiagram` |
| Timeline / milestones | `gantt` |

## Conventions

1. **Label edges.** Unlabeled arrows are ambiguous. Every arrow gets a verb or data-type label.
2. **Use subgraphs for boundaries.** Tenant boundary, network zone, deployment unit — wrap in `subgraph`.
3. **Keep diagrams ≤ 15 nodes.** If larger, split into overview + detail diagrams.
4. **Name nodes with domain language.** Not `Service A` → `ImageIngestionWorker`.
5. **Store in the artifact.** Diagrams live inline in the ADR, spec, or architecture doc they support — not in a separate `diagrams/` folder.

## Anti-patterns

- ASCII art when Mermaid would be clearer and renderable.
- Diagrams without context text — a diagram alone is not an explanation.
- Visio/Draw.io exports committed as images — prefer source-controlled Mermaid.
- Diagrams that show the happy path only — show error/retry paths too.

## Example: deviation proposal

When proposing a deviation, structure as:

```markdown
### Current state

​```mermaid
graph LR
  A[Client] --> B[API Gateway] --> C[Monolith]
​```

### Proposed deviation

​```mermaid
graph LR
  A[Client] --> B[API Gateway]
  B --> C[AuthService]
  B --> D[ImageService]
  B --> E[MetadataService]
​```

### What changes and why
...
```
