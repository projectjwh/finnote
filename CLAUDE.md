# CLAUDE.md — finnote

## Project Overview

**finnote** is a hedge fund-grade investment research newsletter system. 43 AI agents organized into 9 teams collect global market signals, generate analytic views, conduct independent research with global coverage, debate through adversarial bull/bear analysis, validate signals against history, and produce Bloomberg-style visualizations. The system produces four products: Daily Screen, Daily Archive, Weekly Deep Dive, and Monthly Variant Perception Report (flagship).

**Business model**: Premium research newsletter (like BCA Research, Gavekal, Variant Perception). Accountability IS the brand — every research call is tracked publicly with a scorecard.

## Architecture

### 43 Agents across 9 Teams

| Team | Agents | Count |
|------|--------|-------|
| **DATA_ENGINEERING** | Data Architect, Pipeline Engineer, Data Quality Analyst | 3 |
| **ANALYTIC_ENGINEERING** | Macro, Markets, Alt Data Analytics Engineers | 3 |
| **RESEARCH** | 8 Regional Desks (Americas, LatAm, Europe, China, Japan/Korea, India/South Asia, MENA, EM/Frontier) + 6 Thematic (Disclosures, Central Bank, Commodities, Credit, Geopolitics, Technology) | 14 |
| **DATA_SCIENCE** | Bull Case, Bear Case, Sentiment & Flow, Quant Signals | 4 |
| **QUANT** | Researcher, Backtest Engineer, Risk Analyst, Execution Strategist | 4 |
| **REVIEW_BOARD** | Compliance Auditor, Devil's Advocate, Signal Validator, Track Record, Daily Screen Selector | 5 |
| **PROJECT_LEADS** | Macro Regime, Geopolitical/Climate, Structural Risk | 3 |
| **VISUALIZATION** | Chart Designer, Research Writer, Production Editor | 3 |
| **C_SUITE** | CRO (Research+DS), CIO (Quant), CPO (Viz), EIC (Terminal Node) | 4 |

### 12-Phase Pipeline
```
1. DATA_COLLECTION → 2. TRACK_RECORD_UPDATE → 3. ANALYTIC_VIEWS →
4. INDEPENDENT_RESEARCH (14 researchers, ISOLATED) →
5. DATA_SCIENCE_ANALYSIS (bull/bear adversarial) →
6. QUANT_SIGNALS (sequential: discover→backtest→risk→execute) →
7. COMPLIANCE_AUDIT → 8. ADVERSARIAL_CHALLENGE (devil's advocate) →
9. SIGNAL_VALIDATION → 10. REVIEW_AND_SELECT (all documented, some selected) →
11. FEATURED_COVERAGE (project leads update dossiers) →
12. EDITORIAL_PRODUCTION (viz + C-Suite approval → publish)
```

### Four Products
- **Daily Screen**: 5-8 selected findings with charts + 500 words, Mon-Fri pre-open
- **Daily Archive**: complete log of ALL findings, machine-readable
- **Weekly Deep Dive**: 8-12 charts + 2-4K words, Sunday evening
- **Monthly Variant Perception Report**: 20-30 charts + 5-10K words, 1st Monday

## Stack

- Python 3.11+
- `anthropic` SDK for agent orchestration (Claude API)
- `httpx` for async data collection
- `plotly` + `kaleido` for Bloomberg-style charts
- `polars` for data processing
- `pydantic` for agent message schemas and ResearchCall model
- SQLite for track record, daily findings archive, and featured coverage persistence

## Commands

```bash
pip install -e ".[dev]"           # Install with dev dependencies
python -m finnote                  # Run full daily pipeline
python -m finnote collect          # Collection phase only
python -m finnote debate           # Run debate phase only
python -m finnote visualize        # Generate visualizations only
pytest tests/ -v                   # Run tests
```

## Key Design Decisions

- **Adversarial debate embedded in Data Science**: ds_bull and ds_bear analyze the same research through opposing lenses, plus rb_devil challenges consensus. Researchers stay unbiased.
- **All documented, some selected**: rb_selector archives EVERY finding daily, promotes 5-8 to the screen. Nothing gets lost.
- **Featured coverages**: Project Leads own multi-week/month themes (war, regime change, structural risk) with accumulated dossiers that persist across runs.
- **Branch-specific C-Suite**: CRO owns research quality, CIO owns investment calls, CPO owns product quality, EIC is the terminal node that publishes or kills.
- **ResearchCall is the atomic unit**: direction, entry/target/stop, R:R, time horizon, conviction, falsification criteria, and backtest validation.
- **Signal validation gate**: >55% hit rate (N>15) for "validated". Lower can publish as contrarian.
- **Track record is immutable**: Once published, a call's terms cannot be modified.
- **Source credibility tiering**: Tier 1 (Fed/BIS/IMF) through Tier 6 (social media).
- **Information asymmetry**: Phase 4 researchers work in ISOLATION. Phase 6 quants see data science but NOT raw research.
- **20% rejection rule**: EIC must reject >= 20% of proposed content to maintain quality.

## Agent Naming Convention

`{team_prefix}_{function}`: `de_architect`, `ae_macro`, `res_americas`, `ds_bull`, `quant_researcher`, `rb_selector`, `pl_macro_regime`, `viz_designer`, `cs_eic`

## Commander Integration

This project uses agents and skills from the commander framework at `../commander/`.
- Agents: Read agent definitions from `../commander/agents/` before invoking
- Skills: Read skill workflows from `../commander/skills/` before executing
- Do NOT modify agent/skill definitions — changes go through commander only
- Reused commander agents: Aisha Okafor (de_architect), Nikolai Petrov (de_pipeline), Elena Vasquez (de_quality), Yuna Park (quant_researcher), Alexei Volkov (quant_backtest), Tomas Herrera (quant_risk)
