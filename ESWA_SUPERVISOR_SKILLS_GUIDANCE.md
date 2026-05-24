# ESWA Supervisor-Skills distilled guidance

## 1. What kind of paper is this?

This project should be framed primarily as a **technical/expert-system paper with an evaluation-oriented dataset component**, not as a pure benchmark paper.

The paper's core is not "we build a new crash dataset." The core is:

> A missingness-aware, STPA-HF-grounded, evidence-constrained LLM expert system that converts sparse automated-driving event records into auditable safety-case bundles.

The dataset is important because it creates the hard condition under which the method is meaningful: public records often report ENV/ACTOR/CAR facts while omitting HMI, driver state, and internal ADS transition evidence.

## 2. Supervisor-Skills rules we should adopt

From `Supervisor-Skills`, the most useful guidance for this paper is:

- Use a six-part Introduction logic: background, limitations, problem essence, challenges, solution overview, contributions.
- Keep limitations to at most three.
- Make the paper type explicit: technical paper vs benchmark/evaluation paper.
- For evaluation-style work, the key is not raw scores but an evaluation gap, fine-grained taxonomy, empirical findings, and research opportunities.
- Every contribution must map to a section and to an experiment or artifact.
- Every experiment must validate a claim that appears in the Introduction.

## 3. Our final paper spine

### Running example

A public automated-driving collision report says: ADS was engaged; road, actor, lighting, speed/deceleration, and crash outcome are reported. However, it does not report whether the HMI displayed a mode transition, whether a takeover request was issued, whether the driver acknowledged it, or whether ADS confidence degraded internally.

Naive LLM behavior: "crash happened, so takeover failed."

Our system behavior: "crash happened, ADS context exists, but HMI/driver/internal ADS transition evidence is missing; therefore the stronger takeover-failure claim is not supported. The proper output is a bounded STPA-HF safety case plus explicit evidence gaps."

### Three limitations in prior/naive approaches

1. Public crash reports are sparse and heterogeneous; HMI, driver-state, and internal ADS transition facts are often absent.
2. Direct LLM prompting tends to over-escalate from crash outcome to takeover failure.
3. Existing safety-analysis pipelines often output classifications without an auditable boundary explaining which evidence supports or blocks a stronger claim.

### Problem essence

The problem is not accident reconstruction. The problem is evidence-constrained safety-case generation under missing feedback evidence.

### Three technical challenges

1. Missingness must be represented as an epistemic boundary, not treated as negative evidence.
2. LLM reasoning must be constrained by STPA-HF state and UCA catalogs so crash outcomes cannot directly imply takeover failure.
3. The system must transform sparse reports into useful analyst-facing outputs: safety case, evidence audit, feedback gap profile, and requirement candidates.

### Method modules

1. Provenance-aware functional case representation: reported, derived, not_reported, and counterfactual evidence are separated.
2. STPA-HF staged reasoning: prior formation, slot-level update, commitment boundary, mechanism trace, UCA activation.
3. Evidence audit and gap-to-requirement analysis: every claim cites evidence IDs; missing HMI/driver/internal ADS slots become audit/logging requirement candidates.
4. Counterfactual HMI sensitivity: controlled HMI cue injection tests whether boundary shifts follow STPA-HF expectations.

## 4. What feedback gaps mean

Feedback gaps are not "found design defects." They are missing evidence slots that block stronger safety claims.

For each case, the current profile checks 12 key evidence slots:

- HMI feedback: mode-state display, capability-boundary hint, time-budget indicator, acknowledgement requirement, trajectory display latency.
- Driver/cabin state: pressure, distraction.
- Internal ADS/transition: handover time budget, perception confidence, planner confidence, reported system issue, reported intervention.

For 20 NHTSA cases, all 12 slots are missing in each case, so the report has 240 evidence gaps.

The contribution is not the number 240 itself. The contribution is that the system turns "unknown HMI/driver/internal ADS evidence" into explicit audit boundaries and follow-up evidence requirements.

## 5. What requirement candidates mean

Rename these in the paper as:

> analysis-derived evidence/logging requirement candidates

They are not validated HMI design requirements. They are analyst-facing candidates describing what should be recorded, reported, or inspected to support stronger future safety claims.

Examples:

- Missing `HMI.mode_state_display` -> require event records to preserve whether the driver-visible automation mode/state was displayed.
- Missing `HMI.time_budget_indicator` -> require takeover or degradation events to record whether the time budget was displayed and how much time was available.
- Missing `CAR.reported_intervention` -> require incident logs to distinguish no intervention, manual takeover, remote assistance, and system fallback.
- Missing `CAR.perception_confidence` -> require internal ADS logs sufficient to distinguish perception uncertainty from planner or HMI feedback issues.

This output gives the paper application value: the system does not merely classify cases; it tells safety analysts what evidence is missing and what reporting/logging artifacts would make the safety case stronger.

## 6. How to use the 20-case pilot

The 20-case NHTSA pilot should be reported as a pilot or method validation, not as the final ESWA main experiment.

Supported claims:

- The full system can produce schema-valid STPA-HF bundles: 20/20 valid.
- Direct LLM over-escalates: direct baseline assigns 20/20 to not_supported_transfer.
- The staged system is more conservative and evidence-bounded: full system assigns 20/20 to contingent_readiness.
- Counterfactual HMI sensitivity behaves as expected: 80 pairs, directional consistency 0.9875.
- Evidence audit is clean: invalid evidence IDs = 0, UCA catalog consistency = 1.0.

Not yet supported:

- Generalization across sources.
- Human expert agreement.
- Real HMI causal effects.
- Real driver cognition.
- Final engineering requirements.

## 7. Next experimental plan

### Step 1: Rename and sharpen outputs

In code and paper tables, rename `requirement_candidates` to `evidence_requirement_candidates` or explicitly subtitle it as "analysis-derived evidence/logging requirement candidates."

Each candidate should include:

- gap field
- blocked stronger claim
- candidate evidence/logging requirement
- evidence type: HMI report, driver-state report, ADS internal log, intervention log
- priority
- whether it supports boundary, UCA, vulnerability, or audit only

### Step 2: Fix ablation robustness

The `no_update` ablation produced 18/20 schema-valid outputs. This means that skipping the PM update stage caused 2 cases to produce an invalid state/UCA combination. Treat this as a useful finding but improve the runner so invalid outputs are summarized cleanly.

Do not hide the invalidity. Report schema-valid rate as part of method robustness.

### Step 3: Main experiment sample

Build a 40-60 case main experiment:

- NHTSA SGO: 30-40 cases.
- CA DMV collision: 10-15 cases, preferably manually curated from PDFs or a clearly marked third-party CSV.
- CA DMV disengagement: 10-15 cases if the annual report package provides usable CSV/XLSX.

### Step 4: Human-gold evaluation

Use at least 2 annotators. Labels should represent STPA-HF safety-analysis judgments under evidence constraints, not true accident causality.

Annotate:

- boundary label
- dominant UCA
- active UCA set
- update vulnerability
- insufficient information flags
- supporting evidence IDs
- blocked stronger claims

### Step 5: Paper tables

1. Dataset statistics and missingness.
2. Full-system vs direct/generic CoT against human-gold labels.
3. Ablation and schema robustness.
4. Evidence audit and catalog consistency.
5. Counterfactual HMI feedback-boundary sensitivity.
6. Feedback gaps and evidence/logging requirement taxonomy.

## 8. CA DMV data decision

Current best position:

- Use NHTSA SGO CSV as the primary collision CSV source.
- Use CA DMV official collision PDFs for source diversity if curation time allows.
- Use CA DMV disengagement annual reports as a separate non-collision intervention/disengagement source if the package contains structured files.
- Use third-party CA DMV collision CSV only as a supplemental source and clearly mark it as non-official enhanced/curated data.

## 9. One-sentence paper claim

> We propose a missingness-aware STPA-HF LLM expert system that generates auditable safety-case bundles from sparse automated-driving event reports, reduces crash-to-takeover-failure over-escalation, and converts missing HMI/driver/internal ADS evidence into analysis-derived evidence requirements for future safety auditing.

