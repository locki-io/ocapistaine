# Electoral Lists — Audierne-Esquibien Municipal Elections 2026

First round: 15 March 2026 | Second round: 22 March 2026

Source: Préfecture du Finistère — arrêté du 27 février 2026
Data: [data.gouv.fr](https://www.data.gouv.fr/datasets/elections-municipales-2026-listes-candidates-au-premier-tour) (commune 29003)

---

## Second Round Lists (22 March 2026)

After the first round (15 March), two lists remain for the second round:

| # | Official Name | Slug (RAG) | Directory | Nuance | Tête de liste | Docs |
|---|---|---|---|---|---|---|
| 1 | Construire l'Avenir | `ca` | `program_ca/` | LDVG | Florent Lardic | 17 |
| 2 | Passons à l'Action ! | `paa` | `program_paa/` | LDVD | Didier Guillon | 24 |

## Recomposition After First Round

- **S'unir pour Audierne-Esquibien** (Michel Van Praët, LDVG) — Fusion with Construire l'Avenir. 5 colistiers in eligible positions on the new combined list: Danièle Priol-Thomas, Adélie Castel, Christian Neveu (proposed as adjoint), Georges Castel, Michel Van Praët. Source: Facebook post by Michel Van Praët (17 March 2026).
- **Cap sur Notre Futur** (Éric Bosser, LDVD) — Withdrawal.

## First Round Lists (historical — all documents preserved in RAG)

| # | Official Name | Slug (RAG) | Directory | Nuance | Tête de liste | Docs |
|---|---|---|---|---|---|---|
| 1 | S'unir pour Audierne-Esquibien | `spae` | `program_spae/` | LDVG | Michel Van Praët | 15 |
| 2 | Cap sur Notre Futur | `csnf` | `program_csnfa/` | LDVD | Eric Bosser | 5 |
| 3 | Construire l'Avenir | `ca` | `program_ca/` | LDVG | Florent Lardic | 17 |
| 4 | Passons à l'Action ! | `paa` | `program_paa/` | LDVD | Didier Guillon | 24 |

## Participatory Program (non-electoral)

| Source | Slug (RAG) | Origin | Docs |
|---|---|---|---|
| Audierne-Esquibien 2026 | `audierne2026` | [audierne2026.fr](https://audierne2026.fr) | 103 |

This is the co-constructed participatory program built from citizen contributions via GitHub issues, not affiliated with any electoral list.

---

## Directory Structure

```
ext_data/
├── program_ca/          # Construire l'Avenir — 17 JPG + 17 MD (Mistral OCR)
│   ├── ca_1.jpg … ca_16.jpg    # Campaign proposals (social media captures)
│   └── colistiers.md           # Candidate list
├── program_csnfa/       # Cap sur Notre Futur — 2 PDF + 5 MD (Mistral OCR)
│   ├── liste_name.pdf          # Candidate list
│   └── program_1.pdf           # Program manifesto
├── program_paa/         # Passons à l'Action ! — 24 JPG + 24 MD (Mistral OCR)
│   ├── paa_edito*.jpg          # Editorial series (4 editions, multi-page)
│   ├── paa_presentation_*.jpg  # Candidate profiles (11 presentations)
│   └── paa_liste_colistier.jpg # Full candidate list
├── program_spae/        # S'unir pour Audierne-Esquibien — 15 JPG + 15 MD (Mistral OCR)
│   ├── colistier_*.jpg         # Candidate presentations (grouped by page)
│   ├── spae_*.jpg              # Program platform
│   ├── spae_securite_1.jpg     # Security-specific proposal
│   └── presse_1.jpg            # Press coverage
```

## RAG Metadata

Every document ingested into ChromaDB carries:

- `list_name`: slug from the table above (e.g. `paa`, `spae`)
- `doc_id`: filename without extension (e.g. `paa_edito2`)
- `title`: human-readable title derived from filename and list
- `source_type`: `ocr` for program documents, `contribution` for audierne2026

The RAG comparison mode queries each `list_name` separately and asks the LLM to synthesize a neutral comparison.

## OCR Pipeline

All program documents were processed via Mistral Document AI (`scripts/ocr_programs.py`):
- JPG/PNG: sent as base64 `image_url` to Mistral OCR
- PDF: sent as base64 `document_url` to Mistral OCR
- Output: markdown files saved alongside source files
- Progress tracked in `.ocr_programs_index.json`

## Abbreviation Reference

| Abbreviation | Meaning |
|---|---|
| SPAE | S'unir Pour Audierne-Esquibien |
| CSNF | Cap Sur Notre Futur |
| PAA | Passons À l'Action ! |
| CA | Construire l'Avenir |
| LDVG | Liste Divers Gauche |
| LDVD | Liste Divers Droite |
