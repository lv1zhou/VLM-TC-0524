# AAP Narrative Spine V1: Driver Process-Model Tabletop Replay for Automated-Driving Incidents

Date: 2026-05-15

## 1. Target Journal Positioning

The primary target journal is **Accident Analysis & Prevention (AAP)**.

This positioning is reasonable because AAP explicitly covers accident occurrence, injury and damage prevention, human/environmental/vehicular factors, countermeasure design and evaluation, accident data modeling, and safety-related decision-making. The proposed paper sits at the intersection of:

- automated-driving crash and disengagement report analysis,
- driver situation awareness and takeover behavior,
- human factors in automated driving,
- post-incident safety review,
- data/logging requirements for accident analysis.

The paper should be framed as a road-safety and accident-analysis contribution, not as a generic LLM paper. The LLM is an enabling component inside an evidence-constrained STPA-HF expert-system workflow.

## 2. One-Sentence Story

We propose an STPA-HF-constrained driver process-model tabletop replay framework that transforms sparse automated-driving crash and disengagement reports into auditable replay packages for post-incident safety review, driver-centered control-action analysis, and data/HMI/logging improvement planning.

## 3. Central Claim

Public automated-driving incident reports often describe the external scene, vehicle state, and terminal outcome, but they rarely contain the HMI, driver-state, takeover-timing, and internal ADS evidence needed to determine what the driver actually perceived or why the event occurred. Instead of reconstructing the true accident cause, this paper treats such reports as evidence-limited inputs for **driver process-model tabletop replay**.

The core claim is:

> A driver process-model replay layer can convert sparse incident narratives into structured, evidence-bounded safety-review artifacts: what the driver would need to know, what the report supports, which process-model updates remain unverifiable, which candidate control actions can be considered, which UCA pathways are admissible or blocked, and which data or feedback fields should be collected in future incidents.

## 4. What the Driver Model Does in Tabletop Replay

The driver model is not used to read the driver's mind. It is used as a structured intermediate layer between scene facts and safety-analysis claims.

### Function 1: Explanation Bridge

Incident text usually reports facts such as automation mode, road geometry, actor interaction, collision, disengagement, or intervention. Safety analysis, however, needs to reason about whether the human supervisor had enough information to monitor, prepare, take over, intervene, or modulate control. The driver process model bridges this gap:

```text
scene and vehicle evidence
-> driver process-model variables
-> process-model formation/update
-> candidate driver actions
-> UCA-in-context pathways
-> outcome compatibility
```

Without this layer, a model can jump directly from "collision occurred" to "driver failed to take over." With this layer, every stronger claim must pass through CPS/CPB/OPS/OPB, update sources, action selection, UCA gates, and evidence admissibility.

### Function 2: Overreach Suppression

The driver process model acts as a structural brake against unsupported inference. It forces the analysis to distinguish:

- reported evidence,
- derived evidence,
- missing evidence,
- abductive hypotheses,
- blocked claims.

This is especially important for automated-driving incidents, where collision or disengagement outcomes cannot by themselves prove takeover failure, driver inattention, HMI failure, or unsafe manual control.

### Function 3: Tabletop Review Script

The replay package can support a safety-review meeting by making the following questions explicit:

- What did the report support about ADS/vehicle current state (CPS)?
- What did the report support about ADS/vehicle future behavior or capability (CPB)?
- What did the report support about the external scene (OPS)?
- What did the report support about other actors' future behavior (OPB)?
- Which feedback or input sources could update these process models?
- Which candidate driver actions are supported, weakly supported, or blocked?
- Which UCA pathways are compatible with the reported outcome without using that outcome as positive UCA evidence?
- Which missing fields prevent stronger conclusions?

### Function 4: Improvement Planning

The replay output supports four practical activities:

1. **Post-incident safety review**: It gives analysts a structured driver-centered chain rather than a single outcome-driven label.
2. **Minimum reporting and logging requirements**: It identifies which HMI, driver-state, takeover-timing, and vehicle-behavior fields are necessary for future incident replay.
3. **HMI and takeover-support review**: It evaluates whether feedback cues, time-budget information, capability-boundary messages, or driver-action traces would change process-model updates and UCA pathway ranking.
4. **Case-based tabletop training and comparison**: It converts heterogeneous incident reports into a common replay schema for cross-case review.

## 5. Paper Type

According to the Supervisor-Skills introduction framework, this is best positioned as a **Technique Paper with a clear applied safety-analysis setting**.

It is not a pure benchmark paper, because the main contribution is not a new dataset. It is not merely a problem-position paper, because the code already implements a concrete method and output artifact. The narrative axis should be:

> STPA-HF-constrained driver process-model replay as the key mechanism for making LLM-supported incident analysis auditable, bounded, and useful for post-incident safety review.

## 6. Six-Paragraph Introduction Spine

### Paragraph 1: Background and Motivation

Automated-driving systems are increasingly evaluated through public-road collision and disengagement reports. These reports are valuable for road-safety analysis because they capture real-world interactions among automation, road geometry, traffic participants, and human supervisors. A typical report may state that an AV was operating in autonomous mode, encountered a rear-approaching vehicle or intersection conflict, and ended in a collision or disengagement. Yet the report may omit the HMI mode display, takeover warning, time budget, driver gaze, manual-control trace, and ADS internal confidence. This creates a post-incident review problem: the event outcome is visible, but the driver-side control and feedback pathway is underdetermined.

### Paragraph 2: Limitations of Existing Work

Existing automated-vehicle crash and disengagement studies have mainly used public reports for statistical modeling, scenario classification, thematic analysis, and risk-factor extraction. These studies reveal useful aggregate patterns, but they usually do not model how incident facts enter the human supervisor's process model. Takeover and situation-awareness studies, by contrast, provide strong evidence that driver awareness, HMI cues, time budget, workload, and trust affect takeover quality, but they often rely on simulator or experimental data that are unavailable in public incident reports. Recent LLM-based crash or disengagement analysis improves text-mining efficiency, but direct narrative reasoning can still overreach by treating collision or disengagement as evidence of takeover failure.

### Paragraph 3: Problem Essence and Goal

The key problem is not to reconstruct the true accident cause from sparse text. The key problem is to support evidence-bounded driver-centered incident replay when the public report contains enough scene evidence to motivate safety review, but not enough human-state or HMI evidence to support strong psychological or causal claims. Our goal is to transform automated-driving crash and disengagement reports into **driver process-model tabletop replay packages** that explicitly represent supported, weakly supported, and blocked driver-centered safety-analysis pathways.

### Paragraph 4: Key Challenges

Three challenges prevent a naive LLM or narrative-classification approach from solving this problem. First, the same report may contain source-visible scene facts and not-reported HMI/driver-state fields; a method must prevent missing evidence from becoming a positive fact. Second, driver-centered UCA claims cannot be inferred directly from terminal outcomes; they must be derived through process-model variables, update sources, candidate actions, and unsafe control contexts. Third, post-incident review needs an auditable artifact rather than a single label: analysts need replay questions, ranked pathways, blocked claims, and data/HMI/logging requirements.

### Paragraph 5: Solution Overview

We propose an STPA-HF-constrained driver process-model tabletop replay framework. To address evidence sparsity, the framework first builds provenance-aware evidence packets and maps incident facts into CPS, CPB, OPS, and OPB process-model variables. To prevent outcome-driven overreach, it separates process-model formation/update analysis, other-factor extraction, candidate driver-action selection, and forward-derived UCA hypothesis generation; the reported outcome is used only as a compatibility constraint. To support tabletop review, the framework uses deterministic evidence gates and an LLM judge to rank candidate pathways, then outputs a replay package containing process-model nodes, update sources, candidate actions, UCA pathways, replay questions, blocked claims, and missing requirement candidates.

### Paragraph 6: Contributions

1. We define the task of **driver process-model tabletop replay** for automated-driving incident reports, reframing sparse crash/disengagement narratives as evidence-bounded post-incident safety-review inputs rather than complete causal reconstructions.
2. We develop an **STPA-HF-constrained replay framework** that operationalizes CPS/CPB/OPS/OPB process-model variables and links evidence, process-model updates, candidate driver actions, UCA-in-context hypotheses, outcome compatibility, and pathway ranking.
3. We evaluate the framework on public automated-driving crash and disengagement text data, showing how it can generate auditable replay packages, suppress outcome-only overreach, and derive HMI/data/logging improvement candidates through base-report and feedback-injection analyses.

## 7. Research Questions

**RQ1: Replay Package Generation.**  
Can the framework transform sparse automated-driving crash/disengagement reports into schema-valid, evidence-grounded, STPA-HF-compliant driver process-model tabletop replay packages?

**RQ2: Overreach Suppression.**  
Compared with direct LLM and generic chain-of-thought baselines, does the STPA-HF-constrained replay framework reduce unsupported driver-state, HMI, and takeover-failure claims?

**RQ3: Improvement and Sensitivity Analysis.**  
Do HMI, takeover-timing, capability-boundary, driver-state, and manual-control-trace injections produce theoretically consistent changes in process-model updates, candidate actions, UCA pathway ranking, and missing requirement candidates?

## 8. Method Output

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
- missing data/HMI/logging requirement candidates.

## 9. Experimental Design

### RQ1: Generation Quality

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
- full STPA-HF tabletop replay.

Metrics:

- outcome-only UCA activation warnings,
- crash-to-takeover-failure overreach,
- not-reported-as-fact warnings,
- observed UCA without action evidence,
- abductive UCA without PM/update/action chain,
- psychological overclaim warnings.

### RQ3: Feedback/Data Sensitivity

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

## 10. Expected Conclusion

The expected conclusion should be:

> Public automated-driving incident reports are valuable but insufficient for direct driver-state or accident-cause inference. An STPA-HF-constrained driver process-model replay layer can turn such reports into auditable tabletop review artifacts, making explicit what is supported, what remains abductive, what must be blocked, and what data/HMI/logging fields are needed for stronger future analysis.

The paper should not claim:

- true accident-cause reconstruction,
- true driver mental-state inference,
- legal responsibility attribution,
- causal proof that HMI caused or prevented an accident,
- pathway scores as true causal probabilities.

## 11. Why AAP Is a Reasonable Target

AAP is a reasonable target because:

- the journal covers human, vehicle, and environmental factors in accident occurrence and prevention;
- it publishes automated-driving crash, disengagement, takeover, and road-safety data-analysis work;
- the proposed method produces road-safety-relevant outputs: post-incident review artifacts, overreach suppression, reporting/logging gaps, and countermeasure-oriented HMI/data requirements;
- the contribution is not merely computational, but explicitly tied to accident analysis and prevention.

Main risk:

- AAP reviewers may reject the paper if it reads as generic LLM prompt engineering or if it overclaims accident causality.

Defense:

- Frame the work as driver-centered incident replay for post-incident safety review.
- Use STPA-HF and evidence gates as the methodological core.
- Evaluate overreach suppression and replay usefulness, not just label accuracy.
- Include concrete case studies and missing-data requirement outputs.

## 12. Current Readiness Score

Current narrative fit for AAP: **8.7/10**.

Expected score after adding replay completeness audit, stronger case studies, and paired HMI-injection replay comparison: **9.1/10**.

The narrative is coherent and defensible if the paper consistently treats the driver process model as a replay and safety-review artifact, not as a claim about real driver psychology.

