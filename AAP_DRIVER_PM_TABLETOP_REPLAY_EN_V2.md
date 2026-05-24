# AAP Narrative Spine V2: Evidence-Bounded Driver Process-Model Tabletop Replay for Automated-Driving Incidents

Date: 2026-05-15

## 1. Target Journal Positioning

The primary target journal is **Accident Analysis & Prevention (AAP)**.

This is a reasonable and strategically sound target because AAP explicitly covers accident occurrence, human and vehicular factors, road-safety countermeasures, safety-related decision-making, and methods that improve accident analysis and prevention. The proposed work is not framed as a general LLM pipeline; it is framed as a **driver-centered post-incident safety-review method** for automated-driving crash and disengagement reports.

The paper sits at the intersection of:

- automated-driving crash and disengagement report analysis,
- driver situation awareness and takeover behavior,
- human factors in automated driving,
- post-incident safety review,
- minimum incident reporting and logging requirement design.

## 2. One-Sentence Story

We propose an **Evidence-Bounded Driver Process-Model Replay** framework, grounded in STPA-HF, that transforms sparse automated-driving crash and disengagement reports into auditable tabletop replay packages for post-incident safety review and minimum incident reporting/logging requirement design.

## 3. Central Claim

Public automated-driving incident reports usually describe the external scene, vehicle state, and terminal event outcome, but they rarely provide the HMI, driver-state, takeover-timing, and internal ADS evidence needed to determine what the driver actually knew or why the event occurred. Therefore, such reports should not be treated as complete causal records. Instead, they should be treated as **evidence-limited inputs for driver-centered replay**.

The central claim of this paper is:

> An evidence-bounded driver process-model replay layer can transform sparse automated-driving incident text into structured, auditable post-incident review artifacts that make explicit (i) what the driver would need to know, (ii) what the report supports, (iii) which process-model updates remain unverifiable, (iv) which candidate control actions and UCA pathways are admissible or blocked, and (v) which missing data, HMI, or logging fields are needed for stronger future review.

## 4. Why the Driver Process Model Is Necessary

This is the most important conceptual point in the paper.

The driver process model is **not** an optional descriptive layer. It is the **minimum intermediate representation** required to connect incident facts to driver-action hypotheses without collapsing directly from outcome to takeover failure.

### 4.1 Why a direct scene-to-action or outcome-to-action mapping is insufficient

Incident text may report:

- ADS active or autonomous mode,
- road geometry or intersection structure,
- presence of another vehicle, pedestrian, or cyclist,
- collision, disengagement, or intervention.

However, these scene facts do not directly specify which driver control action should be inferred. A driver action hypothesis depends on what the driver could plausibly believe about:

- the current ADS/vehicle/control state,
- the future ADS/vehicle behavior and capability boundary,
- the current external scene,
- the future behavior of other traffic participants.

Without this intermediate layer, an analyzer can jump directly from:

```text
collision occurred
-> driver did not take over
-> takeover failure
```

This is precisely the type of unsupported reasoning that the paper aims to suppress.

### 4.2 The driver process model as the necessary bridge

The driver process model provides the smallest structured bridge between incident evidence and driver-centered safety claims:

```text
scene and vehicle evidence
-> driver process-model variables (CPS/CPB/OPS/OPB)
-> process-model formation/update possibilities
-> candidate driver control actions
-> UCA-in-context pathways
-> outcome compatibility
```

In this paper, the driver process model is therefore necessary for three reasons:

1. **Action selection requires internal state representation.**  
   Driver control actions are not determined by scene facts alone; they depend on what the driver could reasonably model about the vehicle, the automation, the road, and other actors.

2. **UCA generation requires a control-theoretic intermediate layer.**  
   In STPA-HF, a UCA is a driver control action in an unsafe context. That unsafe context cannot be defined directly from the terminal outcome alone. It must be mediated by process-model and feedback/update structure.

3. **Replay transparency requires explicit blocked claims.**  
   If the process-model layer is absent, the system cannot explicitly say whether a stronger claim failed because the scene facts were insufficient, the update source was missing, the action evidence was unavailable, or the outcome was being overused.

### 4.3 What “driver process model” means in this paper

The paper does not use “mental model” in a loose psychological sense. It uses a **bounded, operationalized process-model representation** grounded in STPA-HF:

| Variable | Meaning in this paper | Example in incident text |
|---|---|---|
| CPS | Driver belief about the current ADS/vehicle/control state | ADS active, autonomous mode, disengagement, control authority |
| CPB | Driver belief about future ADS/vehicle behavior or capability | whether ADS will brake, avoid, keep lane, remain within support |
| OPS | Driver belief about the current external environment state | road geometry, weather, visibility, lane structure, traffic signal |
| OPB | Driver belief about future behavior of other traffic participants | whether another vehicle will stop, cut in, rear-approach, cross |

This representation is not a claim about the driver's true cognition. It is an evidence-bounded replay structure for safety review.

## 5. What the Replay Package Improves in Practice

The replay package should not be presented as a vague “useful artifact.” It should be tied to specific accident-analysis workflows.

### 5.1 Two primary workflows

The paper should emphasize **two primary workflows**.

#### Workflow A: Post-Incident Safety Review

The replay package supports analyst-led post-incident review by making the following explicit:

- which process-model variables were supported or unsupported,
- which update sources were visible or missing,
- which driver actions were plausible, weak, or blocked,
- which UCA pathways were admissible only as abductive replay hypotheses,
- which claims could not be made under the available evidence boundary.

This improves the quality of post-incident analysis because it replaces an outcome-driven narrative with a driver-centered, evidence-audited control-and-feedback replay.

#### Workflow B: Minimum Incident Reporting and Logging Requirement Design

The replay package also supports the design of better incident reporting and logging practice. It identifies which missing fields—such as HMI mode display, takeover demand timing, driver acknowledgement, manual-control trace, or ADS confidence—prevent stronger post-incident conclusions.

This gives the paper a direct prevention-oriented value:

> it helps specify which data should be recorded if future automated-driving incidents are to be reviewed more safely and more reliably.

### 5.2 Two secondary workflows

The paper may also mention, but should not overemphasize, **two secondary workflows**:

1. **HMI and takeover-support design review**: to examine whether additional cues would alter process-model update, action selection, and UCA pathway ranking.
2. **Case-based tabletop training and comparison**: to convert heterogeneous incident reports into a common replay schema for analyst discussion and training.

These are useful extensions, but they should remain secondary to the two primary workflows above.

## 6. Paper Type

According to the Supervisor-Skills introduction framework, this is best positioned as a **Technique Paper with a road-safety application focus**.

It is not a pure benchmark paper, because the core contribution is not merely a new dataset. It is not primarily a New Problem/Setting paper, because the method and artifact are concrete and implemented. The narrative axis should be:

> Evidence-Bounded Driver Process-Model Replay as the key mechanism for making automated-driving incident review auditable, bounded, and safety-useful under missing evidence.

## 7. Six-Paragraph Introduction Spine

### Paragraph 1: Background and Motivation

Automated-driving systems are increasingly evaluated through public-road collision and disengagement reports. These reports matter because they record real-world interactions among automation, road geometry, traffic participants, and human supervisors. A typical report may state that an AV was operating in autonomous mode near an intersection or rear-approaching vehicle and ended in a collision or disengagement. Yet the same report may omit the HMI mode display, takeover request, time budget, driver gaze, manual-control trace, and ADS internal confidence. This creates a practical post-incident review problem: the event outcome is visible, but the driver-side control and feedback pathway is not.

### Paragraph 2: Limitations of Existing Work

Existing automated-vehicle crash and disengagement studies have mainly used public reports for crash-pattern statistics, scenario classification, and thematic risk-factor analysis. These studies are useful for describing what happened in the scene, but they usually do not represent how incident facts enter the human supervisor's control logic. Takeover and situation-awareness studies, by contrast, provide strong evidence that awareness, HMI cues, time budget, workload, and trust affect takeover quality, but they usually rely on simulator or experimental measures unavailable in public incident reports. Recent LLM-based crash and disengagement analysis improves text processing efficiency, but direct narrative reasoning can still overreach by treating collision or disengagement as evidence of takeover failure.

### Paragraph 3: Problem Essence and Goal

The key problem is not to reconstruct the true accident cause from sparse text. The key problem is to support a driver-centered safety review when the public report contains enough scene evidence to motivate replay, but not enough human-state or HMI evidence to justify strong psychological or causal claims. Our goal is to transform automated-driving crash and disengagement reports into **evidence-bounded driver process-model tabletop replay packages** that explicitly represent supported, weakly supported, and blocked driver-centered safety-analysis pathways.

### Paragraph 4: Key Challenges

Three challenges prevent a naive LLM or direct narrative-classification approach from solving this problem. First, a report may contain source-visible scene facts together with not-reported HMI, driver-state, and internal ADS fields; missing evidence must not become a positive fact. Second, driver-centered UCA claims cannot be inferred directly from terminal outcomes; they must be mediated by process-model variables, process-model updates, candidate control actions, and unsafe control contexts. Third, accident analysis requires a review artifact rather than a single label: analysts need replay questions, ranked pathways, blocked claims, and minimum reporting/logging requirements.

### Paragraph 5: Solution Overview

We propose an STPA-HF-constrained Evidence-Bounded Driver Process-Model Replay framework. To address evidence sparsity, the framework first builds provenance-aware evidence packets and maps incident facts into CPS, CPB, OPS, and OPB process-model variables. To prevent outcome-driven overreach, it separates process-model formation/update analysis, other-factor extraction, candidate driver-action selection, and forward-derived UCA hypothesis generation; the reported outcome is used only as a compatibility constraint. To support accident-analysis workflows, the framework uses deterministic evidence gates and an LLM judge to rank candidate pathways, then outputs a replay package containing process-model nodes, update sources, candidate actions, UCA pathways, replay questions, blocked claims, and missing reporting/logging requirement candidates.

### Paragraph 6: Contributions

1. We define the task of **Evidence-Bounded Driver Process-Model Replay** for automated-driving incident reports, reframing sparse crash/disengagement narratives as structured post-incident review inputs rather than complete causal reconstructions.
2. We develop an **STPA-HF-constrained replay framework** that operationalizes CPS/CPB/OPS/OPB process-model variables and links evidence, process-model updates, candidate driver actions, UCA-in-context hypotheses, outcome compatibility, and pathway ranking.
3. We evaluate the framework on public automated-driving crash and disengagement text data, showing how it can generate auditable replay packages, suppress outcome-only overreach, and derive minimum reporting/logging and HMI-support requirement candidates through base-report and feedback-injection analyses.

## 8. Research Questions

**RQ1: Replay Package Generation.**  
Can the framework transform sparse automated-driving crash/disengagement reports into schema-valid, evidence-grounded, STPA-HF-compliant driver process-model tabletop replay packages?

**RQ2: Overreach Suppression.**  
Compared with direct LLM and generic chain-of-thought baselines, does the replay framework reduce unsupported driver-state, HMI, and takeover-failure claims by requiring process-model and action-selection mediation?

**RQ3: Review Utility and Sensitivity.**  
Do feedback- and logging-related injections produce theoretically consistent changes in process-model updates, candidate actions, UCA pathway ranking, and minimum reporting/logging requirement outputs?

## 9. Paper-Facing Output

The paper-facing output is `tabletop_replay_package`, containing:

- evidence profile,
- CPS/CPB/OPS/OPB driver process-model nodes,
- process-model formation and update analysis,
- other action-selection factors,
- driver replay posture,
- candidate driver actions,
- forward-derived UCA pathway summary,
- ranked explanatory pathways,
- outcome compatibility blocks,
- replay questions,
- missing reporting/logging requirement candidates.

This output should be described as a **post-incident safety-review artifact**, not merely a JSON result file.

## 10. Experimental Design

### RQ1: Replay Package Generation

Metrics:

- schema valid rate,
- invalid evidence ID count,
- process-model quadrant coverage,
- replay package completeness,
- mean candidate pathways per case,
- UCA catalog consistency,
- evidence citation provenance distribution.

### RQ2: Overreach Suppression

Baselines:

- direct LLM,
- generic CoT,
- no-update ablation,
- full STPA-HF replay.

Metrics:

- outcome-only UCA activation warnings,
- crash-to-takeover-failure overreach,
- not-reported-as-fact warnings,
- observed UCA without action evidence,
- abductive UCA without PM/update/action chain,
- psychological overclaim warnings.

### RQ3: Review Utility and Sensitivity

Counterfactual injections:

- explicit HMI mode display,
- takeover demand with time budget,
- capability-boundary cue,
- driver acknowledgement or intervention trace,
- manual control trace.

Metrics:

- update evidence status changes,
- candidate action status changes,
- UCA pathway score/rank changes,
- blocked claim reductions,
- missing requirement candidate reductions,
- directional consistency across injection types.

## 11. Expected Conclusion

The conclusion should be:

> Public automated-driving incident reports are valuable but insufficient for direct driver-state or accident-cause inference. An STPA-HF-constrained evidence-bounded driver process-model replay layer can convert such reports into auditable post-incident review artifacts, making explicit what is supported, what remains abductive, what must be blocked, and what minimum reporting/logging or HMI-related fields are needed for stronger future review.

The paper should not claim:

- true accident-cause reconstruction,
- true driver mental-state inference,
- legal responsibility attribution,
- causal proof that HMI caused or prevented an accident,
- pathway scores as true causal probabilities.

## 12. Why AAP Is a Reasonable Target

AAP is a reasonable target because:

- the journal covers human, vehicle, and environmental factors in accident occurrence and prevention;
- it publishes automated-driving crash, disengagement, takeover, and safety-analysis studies;
- the proposed method produces road-safety-relevant outputs for accident review and prevention, not just computational outputs;
- the primary contribution is an accident-analysis workflow artifact: a structured replay package for post-incident review and minimum reporting/logging requirement design.

Main risk:

- reviewers may see the work as generic LLM prompt engineering if the paper overemphasizes implementation detail and underemphasizes accident-analysis workflows.

Main defense:

- frame the method as a driver-centered post-incident review framework;
- show that the driver process model is a necessary intermediate representation rather than an optional explanation layer;
- evaluate replay completeness, overreach suppression, and reporting/logging requirement generation;
- use concrete case studies and paired feedback-injection comparisons.

## 13. Current Readiness Score

Current narrative fit for AAP: **9.1/10**.

The remaining gap is not conceptual coherence. The remaining gap is execution: stronger case studies, replay-completeness audit, and experimental tables that foreground review utility rather than only UCA output.

