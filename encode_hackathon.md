# letter of intention

## Project name

```
Ò capistaine !
```

## Discord

```
https://discord.gg/hrm4cTkN
```

## join code

```
0e10f89d
```

## description of ocapistaine :

### this repository :

In the background of audierne2026.fr A Python-based crawling and AI agent system (built with FastAPI and related tools) for gathering, processing, and responding to civic contributions. This project focuses first on integrating **Opik** (from Comet ML) for LLM tracing, evaluation, and observability.

This repository is the RAG system, storing data and experience with the community.
fed by :

- issues/discussion in the audierne2026 repo
- the facebook interactions
- crawling the web on 6 years of commune documentation / regional / national and example of success abroad.
- the local press

```
Opik provides powerful tracing for LLM calls, agent workflows, and crawling operations, helping you monitor performance, detect hallucinations, and evaluate outputs. We'll start with the **cloud-hosted version** (free tier on Comet) for quick testing and iteration.
```

### agents work distribution

https://github.com/locki-io/vaettir

In Vaettir repository a N8N workflow taking decision or delegating to human, feed with the iterated prompts from the opik cloud plateform and error detections.
The N8N serves to link the FB, the email and the other source of interactions (chatbot)

### docusaurus

To document the workflows (SoC, ToC, TRIZ) and current status of the RAG system (subgit repo: public). Give link to examples of process being help in audierne2026
https://audierne2026.fr/contribution-process/

#### methodologies :

- [TRIZ](./docs/methods/TRIZ_METHODOLOGY.md)
- [CHARTE](https://github.com/audierne2026/participons/blob/main/docs/CHARTE_DE_CONTRIBUTION.md)
- Separation of concerns (for workflows and code in general)
- Theorie of Constrains (to solve budget constraints / localisation contraints etc)

Workflows :

- [RESPECT_CHARTE](https://audierne2026.fr/contribuer/#charte-de-contribution)
- [CONSOLIDATION](./docs/workflows/CONSOLIDATION.md)

# Goal :

## Project timing (started)

https://github.com/orgs/locki-io/projects/2

## best use of Opik

Showcase exceptional implementation of evaluation and observability in your AI system.
Demonstrate how you use Opik to systematically track experiments, measure agent performance, and improve system quality with data-driven insights.

### Examples:

Chat agent with online LLM-as-judge evaluations representing different aspects of your application's success.

- Automated prompt/agent tuning loop using Opik Agent Optimizer
- Guardrailed compliance summarizer (PII/red-flag detection) with Opik evals tracking safety/false-positive tradeoffs.
- Regression test suite for a feature-flagged LLM app, with Opik experiments comparing model versions on a fixed dataset.
- RAG QA bot for your internal docs, with Opik tracing + evals to tune retriever/k settings.
  Multi-tool coding agent where Opik scores tool-selection accuracy and trajectory efficiency across runs

### Judging Criteria:

- Functionality: Does the app actually work as intended? Are the core features implemented, stable, and responsive?
- Real-world relevance: How practical and applicable is this solution to real users’ lives and real-world New Year’s goals?
- Use of LLMs/Agents: How effectively does the project use LLMs or agentic systems (e.g. reasoning chains, autonomy, retrieval, tool use)?
- Evaluation and observability: Has the team implemented ways to evaluate or monitor their system’s behavior (e.g. metrics, human-in-the-loop validation, Opik integration)? How robustly?
- Goal Alignment: How well is Opik integrated into the development workflow (e.g. tracking experiments, model versions, evaluation runs)? Does the team use Opik to produce meaningful insights or improve model quality systematically? Are Opik dashboards, metrics, or visualizations clearly presented for judging?

## Social & Community Impact

Build apps that foster connection, inclusion, and create tangible social or environmental good.
Help people organize community initiatives, take meaningful environmental action, or connect with causes that matter to them.

### Examples:

- Community organizing tools that coordinate local initiatives
- Environmental action trackers that gamify sustainable habits
- Volunteer matching platforms that connect people with causes

### Judging Criteria:

- Functionality: Does the app actually work as intended? Are the core features implemented, stable, and responsive?
- Real-world relevance: How practical and applicable is this solution to real users’ lives and real-world New Year’s goals?
- Use of LLMs/Agents: How effectively does the project use LLMs or agentic systems (e.g. reasoning chains, autonomy, retrieval, tool use)?
- Evaluation and observability: Has the team implemented ways to evaluate or monitor their system’s behavior (e.g. metrics, human-in-the-loop validation, Opik integration)? How robustly?
- Goal Alignment: Does the app foster connection, inclusion, or tangible social benefit like environmental good?
