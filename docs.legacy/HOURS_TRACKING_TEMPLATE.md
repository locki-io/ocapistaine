# Hours Tracking Spreadsheet Template

Create a Google Spreadsheet with the following structure:

## Sheet 1: Hours Log

| Column | Name | Format | Description |
|--------|------|--------|-------------|
| A | Date | Date (YYYY-MM-DD) | When the work was done |
| B | Contributor | Text | Name of contributor |
| C | Hours | Number (0.5 increments) | Time spent |
| D | Component | Dropdown | `src/`, `src/rag/`, `src/opik/`, `docs/`, `agents/`, `workflows/` |
| E | License | Auto-calculated | Apache 2.0 or ELv2 (based on Component) |
| F | Prize Eligible | Auto-calculated | Yes/No (based on License) |
| G | Task Description | Text | What was done |
| H | PR/Commit Link | URL | Link to related PR or commit |

### Dropdown values for Column D (Component):
- `src/` (Apache 2.0)
- `src/rag/` (Apache 2.0)
- `src/opik/` (Apache 2.0)
- `docs/` (Apache 2.0)
- `agents/` (ELv2)
- `workflows/` (ELv2)
- `prompts/` (ELv2)

### Formulas:

**Column E (License):**
```
=IF(OR(D2="src/", D2="src/rag/", D2="src/opik/", D2="docs/"), "Apache 2.0", "ELv2")
```

**Column F (Prize Eligible):**
```
=IF(E2="Apache 2.0", "Yes", "No")
```

---

## Sheet 2: Summary Dashboard

| Row | Metric | Formula |
|-----|--------|---------|
| 1 | **Contributor** | (Name) |
| 2 | Total Hours | `=SUMIF(Log!B:B, A1, Log!C:C)` |
| 3 | Prize-Eligible Hours | `=SUMIFS(Log!C:C, Log!B:B, A1, Log!F:F, "Yes")` |
| 4 | % of Total Eligible | `=B3 / SUM of all eligible hours` |

### Summary Table:

| Contributor | Total Hours | Eligible Hours | % Share |
|-------------|-------------|----------------|---------|
| Jean-Noël   | =SUMIF(...) | =SUMIFS(...)   | =...    |
| ML Engineer | =SUMIF(...) | =SUMIFS(...)   | =...    |
| ...         | ...         | ...            | ...     |

---

## Prize Calculation

```
Prize Share = (Contributor Eligible Hours / Total Team Eligible Hours) × Prize Amount
```

Example:
- Total Prize: €10,000
- Jean-Noël: 40 eligible hours
- ML Engineer: 30 eligible hours
- Total: 70 hours

Jean-Noël: (40/70) × €10,000 = €5,714
ML Engineer: (30/70) × €10,000 = €4,286

---

## Rules

1. Log hours **at least weekly**
2. Include PR/commit links for verification
3. Only Apache 2.0 components count for prize
4. Disputes resolved by reviewing git history
