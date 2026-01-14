# Collaboration Addendum to OCapistaine Contribution Guidelines

**Date:** January 14, 2026
**Parties:** locki.io (represented by Jean-Noël Schilling) and __________________ (the "Contributor")

---

This Addendum supplements the OCapistaine contribution guidelines and applies to contributions related to civictech agents and workflows. By signing, the Contributor agrees to these terms in addition to the standard dual-license structure (Apache 2.0 for core infrastructure; Elastic License 2.0 for agents/workflows).

---

## 1. Scope of Contributions

### Protected Components ("Audierne2026 Project")
These components are governed by **Elastic License 2.0 (ELv2)**:
- Audierne-specific agent logic and prompts
- LLM evaluation prompts (LLM-as-judge)
- N8N workflow definitions specific to audierne2026
- Located in: `agents/`, `workflows/`, `prompts/`

### Collaborative Components ("Open Contributions")
These components are governed by **Apache 2.0**:
- Core infrastructure (`src/`)
- **RAG system core** (`src/rag/`) - embeddings, retrieval, vector store
- **Opik integration** (`src/opik/`) - tracing, observability
- Documentation (`docs/`)
- Utilities, helpers, and crawlers
- General-purpose civictech tools not specific to audierne2026

### RAG System Split (Important for ML Engineers)

The RAG system is split between both licenses:

| Component | Location | License | Prize Eligible? |
|-----------|----------|---------|-----------------|
| Embeddings generation | `src/rag/embeddings.py` | Apache 2.0 | **Yes** |
| Vector store integration | `src/rag/vectorstore.py` | Apache 2.0 | **Yes** |
| Retrieval/search logic | `src/rag/retrieval.py` | Apache 2.0 | **Yes** |
| Document chunking | `src/rag/chunking.py` | Apache 2.0 | **Yes** |
| Opik tracing setup | `src/opik/` | Apache 2.0 | **Yes** |
| Audierne agent prompts | `agents/audierne2026/prompts/` | ELv2 | No |
| LLM-as-judge evaluation | `agents/audierne2026/evaluation/` | ELv2 | No |
| Agent orchestration | `agents/audierne2026/agent.py` | ELv2 | No |

**Principle:** The reusable ML/RAG infrastructure is open source and counts toward prize. Only the Audierne-specific application (prompts, evaluation criteria, agent logic) is protected.

---

## 2. Intellectual Property Rights

### For Protected Components (ELv2)
- The Contributor grants locki.io a perpetual, worldwide, non-exclusive, royalty-free license to use, modify, distribute, and commercialize any contributions
- locki.io retains all commercial rights
- Code remains source-available (visible to all)
- The Contributor waives any rights to challenge locki.io's commercial use

### For Collaborative Components (Apache 2.0)
- Contributions are open source, free for anyone to use
- locki.io waives any claim to exclusive ownership
- The Contributor retains full rights to their original contributions
- Joint developments credited to all parties

### Separation of Components
If a contribution spans both scopes, parties will collaborate to separate them. In case of overlap, Protected Components take precedence under ELv2.

---

## 3. Collaboration Process

- Fork the repository and create feature branches (e.g., `feature/your-feature`)
- Submit PRs with clear documentation
- Follow the OCapistaine Code of Conduct
- Post-hackathon integration or spin-off to be discussed separately

---

## 4. Hackathon Prize Distribution

In the event of winning a hackathon prize (monetary or otherwise):

### Tracking Method
- Hours contributed are tracked via a **shared Google Spreadsheet**
- Spreadsheet URL: ________________________________________
- Each contributor logs their hours with task descriptions
- Logs must be updated at least weekly during the hackathon

### Eligible Contributions
Only contributions to **Apache 2.0 components** count toward prize share:
- Core infrastructure (`src/`)
- **RAG system core** (`src/rag/`) - embeddings, retrieval, vector store, chunking
- **Opik integration** (`src/opik/`) - tracing, observability setup
- Documentation (`docs/`)
- Utilities and helpers

**Note:** Contributions to ELv2 components (`agents/`, `workflows/`, `prompts/`) do NOT count toward prize share, as these become locki.io IP per Section 2.

**For ML Engineers:** Your work on embeddings, vector stores, retrieval logic, and Opik integration is Apache 2.0 and fully eligible for prize share. See Section 1 for the detailed RAG split.

### Calculation
```
Contributor Share = (Contributor Hours / Total Team Hours) × Prize Amount
```

### Distribution Timeline
- Prize distributed within **30 days** of receipt
- Payment via bank transfer or method agreed by parties

### Disputes
If parties disagree on hours logged:
1. Review Git commit history as supporting evidence
2. If unresolved, hackathon organizer or neutral third party arbitrates

---

## 5. Confidentiality

Both parties agree to keep sensitive discussions (e.g., proprietary ideas for Audierne2026) confidential. This does not apply to open-source code or public repo activity.

---

## 6. Termination and Disputes

- This Addendum terminates upon completion of the hackathon or by mutual agreement
- Rights grants survive termination
- **Governing Law:** French law
- **Disputes:** Good-faith negotiation first, then mediation (CCI or Tribunal de Quimper, France)

---

## 7. Acknowledgments

- The Contributor confirms understanding of the dual-license structure
- The Contributor agrees to track hours accurately and in good faith
- locki.io commits to transparent prize distribution based on logged hours

---

## Signatures

| Party | Name | Signature | Date |
|-------|------|-----------|------|
| **locki.io** | Jean-Noël Schilling | _______________ | ________ |
| **Contributor** | _______________ | _______________ | ________ |

---

*This document is part of the OCapistaine project. See [CONTRIBUTING.md](CONTRIBUTING.md) for general contribution guidelines.*
