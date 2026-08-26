# Expansion Governance

**Updated:** 2026-08-26T21:54:29.791975+00:00

## Prescreen Filter Status

- **Version Evaluated:** V3 (uncommitted)
- **Verdict:** REJECTED
- **Recall (genuine):** 0%
- **FP Rate:** 2.5%

### Reason

Keyword-only prescreen achieves 0% recall on genuine ADIAR/REJEITAR cases after cleaning template-leaked verdicts. FP rate 2.5% (meta-proposal self-match). Architectural limitation: real deferral causes are proxy validation gaps, duplicate detection, supersession tracking, and data quality issues — none detectable via keyword regex.

### Recommendation

Do not deploy keyword filter. Invest in structural checks: (1) supersession detector, (2) title-similarity dedup, (3) verdict template leak scanner, (4) semantic triage for proxy TIER0 proposals.

## Data Quality Issues

- Template-leaked verdicts: 60 (8%)
- Known templates:
  - Arbitragem DEX-CEX
  - Proxy TIER0 via GitHub Search sem validação de mercado BR
  - Schema híbrido (GitHub+ReceitaWS)
  - Timers improve causaram checkout compartilhado
  - Dados operacionais validos mas sem relevancia BR
  - Proxy global via GitHub Search API focado em agências/enterprises


## Supersession Detector V1
- **Status:** INTEGRATED (2026-08-26)
- **Proposal:** exp-20260827-supersession-detector-integration
- **Verdict:** APROVAR_IMPLEMENTACAO (confidence 0.92)
- **Script:** scripts/detect_supersession.py
- **Integration:** Non-blocking flag in scripts/prescreen_proposal.py
- **Output:** data/expansion/supersession_flags.jsonl
- **Valid pairs detected:** 6 (4 catchable before judgment)
- **Rollback:** SUPERSESSION_CHECK_ENABLED=0
