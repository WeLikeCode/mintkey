# Views and Beyond — documentation method

We follow the SEI *Views and Beyond* approach. Each architectural view answers a different question, and the documentation as a whole is a *package* that, together, lets a reader build a faithful mental model of the system.

> *"Architecture is the set of structures needed to reason about the system, comprising software elements, relations among them, and properties of both."* — Bass, Clements, Kazman.

## The view‑types we use

| View‑type        | Question it answers                                       | Where in this repo                                           |
|------------------|------------------------------------------------------------|---------------------------------------------------------------|
| **Module**       | "What are the code units and how do they depend?"          | Iteration 2, derived from container view + tech stack.       |
| **Component‑and‑Connector (C&C)** | "What runs and how does data flow?"            | [`02-container-view.md`](02-container-view.md) (Mermaid).     |
| **Allocation**   | "How is software mapped to hardware/processes/teams?"      | [`../05-deployment/`](../05-deployment/) (iteration 2).        |

For each, we document at least:
- **Primary presentation** (the diagram).
- **Element catalog** (each element's responsibility, properties).
- **Context** (how this view connects to the others).
- **Variability** (what's intentionally pluggable).
- **Rationale** (why this structure, not another).

## "Beyond" (the rest of the documentation package)

| Item                              | Where                                                                                |
|-----------------------------------|---------------------------------------------------------------------------------------|
| Documentation roadmap             | [`docs/README.md`](../README.md)                                                      |
| System overview                   | [`00-vision/02-product-vision.md`](../00-vision/02-product-vision.md)                  |
| Stakeholders & concerns           | [`00-vision/03-personas-and-stakeholders.md`](../00-vision/03-personas-and-stakeholders.md) |
| Glossary                          | [`00-vision/04-glossary.md`](../00-vision/04-glossary.md)                              |
| ADRs                              | [`adr/`](adr/)                                                                         |
| Quality attribute scenarios       | [`03-quality-attributes.md`](03-quality-attributes.md)                                  |
| Threat model                      | [`05-threat-model.md`](05-threat-model.md)                                              |

## Why this method (and not "free‑form")
- **Stakeholder alignment**: every view is named for a stakeholder concern. The Operator reads container view; the SRE reads deployment view; the security reviewer reads threat model.
- **Reviewability**: ADRs let us re‑litigate one decision without re‑opening the whole architecture.
- **Evolvability**: views and beyond are loosely coupled — we can add a new view (e.g., a deployment view in iteration 2) without rewriting earlier ones.

## Anti‑patterns we are deliberately avoiding
- **The "uber‑diagram"** that mixes runtime, deployment, and module concerns into one big picture. Different views, on purpose.
- **Implementation‑first documentation** ("here are the packages, figure it out"). We document the structures *needed to reason*, not the structures *that exist after the fact*.
- **Decision amnesia** — every meaningful "why X not Y" is captured as an ADR.

## References
- Clements, Bachmann, Bass, Garlan, Ivers, Little, Merson, Nord, Stafford. *Documenting Software Architectures: Views and Beyond* (2nd ed.), SEI / Addison‑Wesley, 2010.
- Bass, Clements, Kazman. *Software Architecture in Practice* (4th ed.), Addison‑Wesley, 2021.
- Brown. *The C4 Model for Visualising Software Architecture*, Leanpub, ongoing.
- Nygard. "Documenting Architecture Decisions", 2011.
