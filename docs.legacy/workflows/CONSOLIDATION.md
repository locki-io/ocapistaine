# Consolidation Script Documentation

## Overview

`consolidate_contributions.py` generates weekly consolidation reports for the Audierne2026 participatory campaign by fetching and analyzing GitHub issues and discussions.

## Features

### Data Collection
- Fetches all issues from the repository
- Fetches discussions (requires GitHub token with GraphQL permissions)
- Filters contributions vs. automated reports

### Analysis
- **Categorization**: Groups contributions by theme (economie, logement, culture, etc.)
- **TRIZ Framework**: Identifies contradictions and patterns using Theory of Inventive Problem Solving
  - Resource vs. ambition conflicts
  - Participation vs. efficiency trade-offs
  - Preservation vs. development tensions
  - Individual vs. collective interests
  - Local vs. external perspectives
- **Common themes**: Extracts most frequent keywords across all contributions

### Reporting
- Markdown-formatted consolidation report
- Statistics by category
- Detailed contribution listings with links
- TRIZ contradiction analysis
- Recommendations for next steps
- Identification of issues ready for discussion migration

## Usage

### Basic Usage

```bash
python scripts/consolidate_contributions.py
```

This generates `consolidation_report.md` in the current directory.

### Custom Output File

```bash
python scripts/consolidate_contributions.py --output weekly_report_2026-01-07.md
```

### Skip Discussions (faster, no token required)

```bash
python scripts/consolidate_contributions.py --skip-discussions
```

## Configuration

### Environment Variables

Create a `.env` file or set environment variables:

```bash
# Required for private repositories or higher rate limits
GITHUB_TOKEN=ghp_xxxxxxxxxxxxx

# Repository (auto-detected from git or CI)
GITHUB_REPO=audierne2026/participons
```

### GitHub Token Permissions

For full functionality (including discussions), your GitHub token needs:
- `repo` scope (for private repos) or `public_repo` (for public repos)
- GraphQL API access (automatic with any token)

### Getting a GitHub Token

1. Go to https://github.com/settings/tokens
2. Click "Generate new token" → "Personal access token (classic)"
3. Give it a descriptive name: "Audierne2026 Consolidation Script"
4. Select scopes:
   - `repo` (or `public_repo` for public repos only)
5. Copy the token and add to `.env`

## Report Structure

Generated reports include:

1. **Overview**: Total contributions by type
2. **Category breakdown**: Table showing distribution
3. **Detailed contributions**:
   - Issues in contextualization phase
   - Active discussions
   - Labels, creation dates, comment counts
4. **TRIZ analysis**:
   - Contradictions identified per category
   - Cross-cutting themes and keywords
5. **Recommendations**:
   - Issues ready for discussion migration
   - Contradictions requiring creative resolution
   - Suggested next actions

## Weekly Workflow

### Recommended Schedule

Run every Monday morning to prepare the week:

```bash
# Generate report
python scripts/consolidate_contributions.py --output reports/weekly_$(date +%Y-%m-%d).md

# Review the report
cat reports/weekly_$(date +%Y-%m-%d).md

# Take actions:
# 1. Migrate ready issues to discussions
# 2. Comment on issues needing context
# 3. Plan TRIZ workshops for contradictions
```

### Automation with GitHub Actions

You can automate weekly reports with GitHub Actions (example workflow):

```yaml
name: Weekly Consolidation Report
on:
  schedule:
    - cron: '0 9 * * 1'  # Every Monday at 9 AM UTC
  workflow_dispatch:

jobs:
  consolidate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.13'
      - run: pip install requests python-dotenv
      - run: python scripts/consolidate_contributions.py --output weekly_report.md
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          GITHUB_REPO: ${{ github.repository }}
      - uses: actions/upload-artifact@v4
        with:
          name: weekly-report
          path: weekly_report.md
```

## TRIZ Methodology

### What is TRIZ?

TRIZ (Теория решения изобретательских задач) is a problem-solving methodology that identifies and resolves contradictions through systematic innovation patterns.

### How We Use It

The script detects five key contradiction types common in participatory democracy:

1. **Resource Constraint vs. Ambition**
   - Keywords: budget, coût, financement, moyens, ressources
   - Resolution strategies: Phased implementation, resource sharing, volunteer mobilization

2. **Participation vs. Efficiency**
   - Keywords: consultation, participation, rapidité, efficacité, délai
   - Resolution strategies: Parallel processes, digital tools, delegation

3. **Preservation vs. Development**
   - Keywords: patrimoine, préservation, développement, modernisation, changement
   - Resolution strategies: Adaptive reuse, respectful innovation, heritage integration

4. **Individual vs. Collective**
   - Keywords: individuel, collectif, communauté, personnel, commun
   - Resolution strategies: Nested scales, opt-in/opt-out, modular design

5. **Local vs. External**
   - Keywords: local, extérieur, tourisme, habitants, résidents
   - Resolution strategies: Controlled integration, resident priority, balanced policies

### Interpreting TRIZ Results

When the report shows a contradiction:
- **Strength 2-3**: Minor tension, monitor
- **Strength 4-6**: Moderate contradiction, needs attention
- **Strength 7+**: Major contradiction, requires workshop/debate

## Troubleshooting

### Rate Limiting

Without a GitHub token, you're limited to 60 API requests/hour. With a token: 5000 requests/hour.

**Solution**: Set `GITHUB_TOKEN` environment variable

### Discussions Not Fetching

**Error**: "GraphQL errors" or empty discussions

**Causes**:
- Token doesn't have required permissions
- Repository has no discussions enabled

**Solution**:
- Use `--skip-discussions` flag
- Or verify token permissions and repo settings

### Categories Not Recognized

If contributions aren't categorized correctly:

1. Check that issues have proper labels (economie, logement, culture, etc.)
2. Verify category names match the `CATEGORIES` list in the script
3. Update the script's `CATEGORIES` list if needed

## Extending the Script

### Adding New Categories

Edit the `CATEGORIES` list:

```python
CATEGORIES = [
    "economie",
    "logement",
    "culture",
    "ecologie",
    "associations",
    "jeunesse",
    "alimentation-bien-etre-soins",
    "your-new-category"  # Add here
]
```

### Adding TRIZ Patterns

Edit the `TRIZ_PATTERNS` dictionary:

```python
TRIZ_PATTERNS = {
    "your_new_contradiction": [
        "keyword1", "keyword2", "keyword3"
    ],
}
```

### Custom Filters

Modify the `is_contribution()` function to change what counts as a contribution.

## Dependencies

```bash
pip install requests python-dotenv
```

- `requests`: GitHub API calls
- `python-dotenv`: Load environment variables from `.env` (optional)

## Support

Questions or issues with the consolidation script:
- Open an issue: https://github.com/audierne2026/participons/issues
- Label: `aide`, `scripts`

---

**Version**: 1.0
**Last updated**: 2026-01-07
**Maintainer**: Audierne2026 team
