# AAP Paper Structure With Related Work V1

## Narrative Core

The paper is framed as **Evidence-Bounded Driver Process-Model Replay** for automated-driving crash and disengagement reports.

The paper does not claim to reconstruct the true accident cause, infer true driver psychology, prove HMI causality, or assign legal responsibility. It produces a post-incident tabletop replay package that makes driver-process-model pathways, blocked claims, missing evidence, replay questions, and minimum HMI/logging requirements auditable.

## Revised Structure

1. **Introduction**
   - Purpose: state the sparse-report evidence problem, define the task, explain why LLMs need STPA-HF constraints, and list three contributions.
   - Citation role: minimal, only source-regime citations for NHTSA and CA DMV.
   - Avoids: detailed literature review, long taxonomy, and repeated method details.

2. **Related Work**
   - Purpose: position the paper among AV report analysis, driver takeover/HMI research, LLM/VLM traffic-safety work, and STPA-HF/system-theoretic safety analysis.
   - Current subsections:
     - Public automated-driving incident reports
     - Driver takeover, HMI, and process-model evidence
     - LLM and VLM methods for traffic safety analysis
     - STPA-HF and evidence-bounded driver-process-model replay
   - Current bibliography: 28 cited references, with no unused BibTeX entries.

3. **Method**
   - Task definition and claim boundary
   - Evidence packet construction
   - Driver process-model representation: CPS / CPB / OPS / OPB
   - Process-model update analysis
   - Candidate driver action generation
   - UCA pathway generation and outcome compatibility
   - LLM judge ranking and blocked-claim gate
   - Tabletop replay package output

4. **Experiments**
   - RQ1: replay package generation and auditability
   - RQ2: process-model mediation and overreach suppression
   - RQ3: expert alignment, HMI/logging sensitivity, and evidence-density response
   - Final richer-evidence replay case study as evidence-density stress test

5. **Discussion**
   - Post-incident driver-centered safety review
   - Minimum reporting/logging requirement design
   - HMI and process-model update sensitivity
   - Why replay packages help analysts without claiming accident truth

6. **Limitations**
   - Sparse reports limit claim strength
   - LLM rankings are not causal probabilities
   - Richer-evidence case study is not a separate video-understanding contribution
   - Human expert validation remains required for final safety review use

## Contribution Packaging

1. **Problem formulation**
   - Evidence-bounded driver process-model replay as a post-incident safety-review task.

2. **Method**
   - STPA-HF-constrained LLM pipeline from incident text to process-model replay package.

3. **Evaluation and utility**
   - Replay-generation quality, overreach suppression, expert alignment, HMI/logging sensitivity, and richer-evidence replay convergence.

## Current Score

**9.2 / 10** for narrative structure.

Strengths:
- The paper now has a clear AAP-compatible accident-analysis object.
- Introduction and Related Work are separated cleanly.
- The three AAP LLM/VLM papers are used as positioning references, not as direct targets to imitate.
- The richer-evidence case study is framed as evidence-density stress testing, which protects the main contribution.

Remaining gaps:
- Method section still needs full prose rather than scaffold.
- Experiments need final sample sizes and headline metrics.
- One concrete running example should be threaded through Introduction, Method, and Case Study.
- Several BibTeX entries should receive a final publisher-level verification pass before submission.
