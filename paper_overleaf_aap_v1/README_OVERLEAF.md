# Overleaf package for AAP manuscript draft

Upload the generated zip file to Overleaf and compile `main.tex`.

## Files

- `main.tex`: Elsevier `elsarticle` manuscript shell for Accident Analysis & Prevention.
- `introduction.tex`: AAP-oriented Introduction draft.
- `related_work.tex`: Thematic Related Work section with 28 curated references.
- `method_spine.tex`: Method section scaffold aligned with the current narrative.
- `experiment_plan.tex`: AAP-aligned experimental design scaffold.
- `references.bib`: Initial bibliography.
- `highlights.txt`: Elsevier-style highlights, kept as a separate submission file.
- `elsarticle-harv.bst`: Included for reproducible author-year bibliography style.

## AAP / Elsevier notes

- AAP is an Elsevier journal, so the `elsarticle` class is the appropriate LaTeX route.
- The current shell uses `\documentclass[preprint,12pt,authoryear]{elsarticle}` with line numbers and double spacing.
- Elsevier highlights are normally 3-5 bullet points, with each bullet under 85 characters.
- The abstract should be kept within the AAP/Elsevier limit used by the Guide for Authors.
- Replace placeholder authors, affiliations, funding, ethics, and data-availability text before submission.
- The richer-evidence case study is framed as an evidence-density stress test, not as a separate video-understanding experiment.

## Current Introduction score

The current Introduction + Related Work structure is assessed at 9.2/10 for AAP narrative fit. Remaining work should occur after the final experimental sample and results are frozen.
