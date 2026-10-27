# Model card: ModernBERT-large anchor (NewsAction NA-08)

| | |
|---|---|
| Model | ModernBERT-large (Dec-2024 weights) with Laya's decision-head architecture, freshly initialised and trained with the identical recipe; the clean anchor of the headline-claim rule (PREREG §1.3, §9.2). No distillation from any vendor model; Laya's undisclosed training data plays no part. |
| Init | `answerdotai/ModernBERT-large`, revision `45bb4654a4d5aaff24dd11d4781fa46d39bf8c13`, weights sha256 `44510fec5d3a81a1877f225637b869495f18e55f6f23a09abb9be0acc030295f` (checked before loading) |
| Architecture | ModernBERT-large encoder (fully fine-tuned) + decision head: 2 transformer layers and an option-marker scorer (Laya `DecisionModel`); the act head is frozen and unused |
| Reported model | the single seed run anchor-s13: 1 of the 3 seeds of PREREG §9.1; the others are deferred (PREREG §15 NA-08 row, operator decision) and enter the ensemble when they are imported |
| Inputs | the NA-04 masked E3 states (PREREG §6.10–6.11), identical to the API models' states |
| Outputs | probabilities per head; common prediction schema `work/kaggle/predictions/anchor_{val_a,val_b,test_callA}.parquet` |

## Heads

- **H-react** (score, 9 levels; Q1): "Once investors fully absorb the news in `news`, how will the company's stock perform relative to the overall market and its sector over the next five trading days?" Label: Q1's level of e5 = AR(C_{t−1}→C_{t+4})/(σ_cc·√5): 4 + sign(e5)·bin(|e5|), bins [0, 0.5) [0.5, 1) [1, 2) [2, 3) [3, ∞). Derived N̂ = Σ p_k m_k with m = (−3.5, −2.5, −1.5, −0.75, 0, 0.75, 1.5, 2.5, 3.5); E|N̂| = Σ p_k |m_k|.
- **H-mag** (score, 5 levels; an internal training question, never sent to an API model): "How large will the stock's move relative to the market and its sector be today?" Levels: negligible (< 0.5 typical daily moves); small (0.5–1); moderate (1–2); large (2–3); very large (> 3 typical daily moves). Label: bin(|z_cc,t|). Derived E[level midpoint] with midpoints (0.25, 0.75, 1.5, 2.5, 3.5) and P(|z| ≥ 1).
- **H-cont** (choice, 3; Q6, Call B only): "What will the stock's move in `reaction_so_far` do over the next five trading days, relative to the market and its sector?" Options reverse / stall / continue. Label (|G| ≥ 0.5, G = z_cc,t): x = sign(G)·y2, y2 = z(O_{t+1}→C_{t+5}); reverse x ≤ −0.5, continue x ≥ 0.5, else stall. Derived C = P(continue) − P(reverse); J analogue = C; W analogue = P(reverse).

Questions asked: Call A D0 and D2: H-react, H-mag; Call B D2: H-react, H-cont.

## Data

- Private Kaggle dataset `amirdehkordi98/newsaction-na08-states`; files by sha256 in `work/kaggle/dataset/sha256_manifest.json` (manifest sha256 `2bafd1de3d40a705ab14c150672b83d0c251b88d7ee0db57db286f5b0e796992`), equal to the files every run checked on Kaggle.
- Train: sessions 2024-07-01 … 2025-06-30, last label horizon 2025-06-30 (purge, PREREG §4.1); 174,320 examples (83,749 distinct states), including the block-dropout copies (PREREG §9.1: Call B without `reaction_so_far`, p = 0.3; any state without the context blocks, p = 0.1).
- Val-A: 2025-07-01 … 2025-09-30: early stopping, temperatures and every number below, without the first 5 sessions (PREREG §4.2).
- Val-B and test (Call A only): states without any label column; predictions are stored and not evaluated in NA-08. No test label left this machine.
- Sequence: Laya's `[CLS] question [SEP] options [SEP] state [SEP]`, max length 1036, head length 143 (the longest trained question, react, in Laya's rendering; operator decision on NA-04 owner decision 2). States longer than the room: 0 examples ({}), cut by ≤ 0 tokens.

## Training

AdamW, learning rates 2e-05 (encoder) / 0.0001 (head), weight decay 0.01, linear warm-up over 3% of the updates then cosine decay to 1e-06, gradient clip 1, effective batch 8 × 2 GPUs × 4, fp16 autocast, gradient checkpointing on. Loss: Laya's official RLCD objective (`laya.train.rlcd_loss`: a proper-scoring policy-gradient term over noisy logits plus soft cross-entropy). 1 epoch per run (PREREG §9.1 allows ≤ 3): the pilot measured an epoch at 5.9 h on 2×T4, so two do not fit a 12-hour session (artifacts/NA-08/throughput.json); the val-A cross-entropy is recorded, and early stopping has one epoch to choose.

| Run | Seed | Epochs run | Best epoch | Val-A loss by epoch | Stopped by time | GPU | Hours |
|---|---|---|---|---|---|---|---|
| anchor-s13 | 13 | 1 | 1 | 1.6136 | False | 2× Tesla T4 | 8.11 |

## Val-A results (embargo excluded)

| | Model | IC | NW t | 95% CI (block bootstrap) | Days | Events |
|---|---|---|---|---|---|---|
| D0 Call A: N̂ vs z_cc,t | anchor-s13 (reported) | 0.0237 | 1.86 | [-0.0011, 0.0489] | 59 | 8,376 |
| D0 Call A: N̂ vs e5 | anchor-s13 (reported) | 0.0092 | 0.65 | [-0.0173, 0.0400] | 55 | 7,970 |
| D2 Call A: N̂ vs e5 | anchor-s13 (reported) | -0.0010 | -0.11 | [-0.0182, 0.0171] | 55 | 9,898 |
| D2 Call B: N̂ vs e5 | anchor-s13 (reported) | 0.0028 | 0.30 | [-0.0145, 0.0218] | 55 | 9,898 |
| D0 Call A: H-mag E[level] vs \|z_cc,t\| | anchor-s13 (reported) | 0.1690 | 6.32 | [0.1172, 0.2243] | 59 | 8,376 |
| D2 Call B: C vs sign(G)·y2 (\|G\| ≥ 0.5) | anchor-s13 (reported) | -0.0266 | -2.19 | [-0.0525, -0.0025] | 54 | 6,136 |

## Calibration (val-A, embargo excluded; 15-bin ECE)

| Head | Model | Temperature | ECE before | ECE after | NLL before | NLL after | n |
|---|---|---|---|---|---|---|---|
| cont | anchor-s13 (reported) | 20.000 | 0.0173 | 0.0077 | 1.0995 | 1.0986 | 6,136 |
| mag | anchor-s13 (reported) | 0.903 | 0.0026 | 0.0220 | 1.3537 | 1.3519 | 18,832 |
| react | anchor-s13 (reported) | 0.966 | 0.0039 | 0.0119 | 1.9035 | 1.9032 | 27,766 |

The reported model is the single seed anchor-s13; its temperatures are fit on val-A.

## Controls

- Shuffled labels (shuffle-s13): D0 N̂ vs e5 IC -0.0072, NW t -0.48: PASS (|NW t| of the val-A mean daily IC of N̂ vs e5 (D0) < 2.0).
- Reproducibility: pending: ['repro-s13'] not imported; if this week's quota does not allow it, the operator-approved deferral under AC3 (it does not block NA-11).

## Governance and limits

- The Kaggle dataset is private and holds masked, third-party-OK states and train / val-A labels only; val-B and test labels never left this machine (CLAUDE.md D15–D16).
- Nothing was pushed to the Hugging Face Hub: every run record says `hub_push: false`, the notebook has no upload call (tests/test_train_notebook.py) and the checkpoint stays in the kernel's output.
- Labels are noisy realised returns; the result is reported as it is.
