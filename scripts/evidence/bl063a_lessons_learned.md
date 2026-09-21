# BL-063a evidence — IDF lessons learned (retrospective), 2026-09-21

Implementation: Production of comprehensive project retrospective [`docs/LESSONS_LEARNED.md`](../../docs/LESSONS_LEARNED.md) synthesizing all technical, architectural, and operational findings from the ESP-IDF track:
- **Risk Outcomes**: Systematic analysis of risks R1 through R15 from PLAN §9, mapping IDF results to their concrete implications for the upcoming Zephyr track.
- **Hardware & Tooling Traps**: Detailed root cause and resolution for 8 critical traps (WSL2/usbipd R14 reset-on-open, per-variant sdkconfig contamination R15, optional subsystem fatal asserts, software vs hardware reset dynamics, vacuous evidence pitfalls, and polling contention).
- **Actionable Zephyr Checklist**: Defined strict pre-flight requirements for P2 Zephyr bring-up (MCUboot swap-with-revert verification gate, raw UART console assignment, non-fatal radio initialization).

## Acceptance Criteria (IDF Track) — PASS

- **AC1: "docs/LESSONS_LEARNED.md covers every risk R1–R15 outcome and every trap found during the IDF track"** — **PASS**:
  - Full matrix embedded covering R1 to R15.
  - Traps 1 through 8 comprehensively documented with symptom, root cause, and resolution.
- **AC2: "Every lesson has an action: a plan change, a tool change or a checklist item"** — **PASS**:
  - Every risk entry in Section 2 features an explicit Plan Action, Tool Action, or Checklist Item.
  - Section 4 defines 5 concrete mandatory gates for the Zephyr track.
- **AC3: "Owner review recorded"** — **PASS**:
  - Section 5 records formal owner sign-off and approval to proceed to BL-063b.
