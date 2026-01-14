# Contributing to OCapistaine

Thank you for your interest in contributing to OCapistaine! This document explains how contributions work, especially regarding our dual-license structure.

## Dual-License Structure

This project uses **two different licenses** depending on which part you contribute to:

| Component                     | License             | What it means                                              |
| ----------------------------- | ------------------- | ---------------------------------------------------------- |
| **Core infrastructure**       | Apache 2.0          | Your contributions are open source, free for anyone to use |
| **Agent workflows & prompts** | Elastic License 2.0 | Your contributions become part of locki.io IP              |

### What does this mean for you?

#### Contributing to Open Source components (`src/`, `docs/`)

- Your code is licensed under Apache 2.0
- Anyone can use, modify, and distribute it freely
- Standard open source contribution

#### Contributing to Protected components (`agents/`, `workflows/`)

- Your code is licensed under Elastic License 2.0
- locki.io retains commercial rights
- You grant locki.io the right to use your contribution commercially
- The code remains source-available (visible to all)

## Before Contributing

By submitting a pull request, you agree that:

1. **For Apache 2.0 components**: Your contribution is licensed under Apache 2.0
2. **For ELv2 components**: You grant locki.io a perpetual, worldwide, royalty-free license to use, modify, and commercialize your contribution

## How to Contribute

### Hackathon Participants

> **Prize Distribution:** If you're contributing to a hackathon, please sign the [COLLABORATION_ADDENDUM.md](COLLABORATION_ADDENDUM.md) which covers:
> - IP rights for your contributions
> - Prize distribution based on **hours tracked via Google Spreadsheet**
> - Only Apache 2.0 contributions count toward prize share

1. Sign the [Collaboration Addendum](COLLABORATION_ADDENDUM.md)
2. Fork the repository
3. Create a feature branch: `git checkout -b feature/your-feature`
4. **Log your hours** in the shared Google Spreadsheet
5. Make your changes and commit with clear messages
6. Push and create a Pull Request

### Which license applies to my contribution?

| If you're working on...       | License    |
| ----------------------------- | ---------- |
| Crawlers, scrapers (`src/`)   | Apache 2.0 |
| Documentation (`docs/`)       | Apache 2.0 |
| Utilities, helpers            | Apache 2.0 |
| Agent definitions (`agents/`) | ELv2       |
| Workflow logic (`workflows/`) | ELv2       |
| LLM prompts, evaluation       | ELv2       |
| N8N integrations              | ELv2       |

### Not sure?

Ask in the PR or open an issue. We're happy to clarify!

## Code of Conduct

- Be respectful and constructive
- Focus on the civic transparency mission
- Document your changes
- Write tests when applicable

## Questions?

- Open a GitHub Issue
- Join our [Discord](https://discord.gg/hrm4cTkN)
- Email: jn@locki3d.com

---

**Thank you for helping build civic transparency tools!**
