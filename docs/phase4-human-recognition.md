# Phase 4 Human Recognition Gate

Fresh Phase 4 visual acceptance requires label-hidden human recognition. Automated compatibility checks are not enough to set `visualAcceptance: true`.

Before asking for recognition answers, show the generated label-hidden previews from the active candidate QA directory:

- `work/akari-hq-apng/phase4-gap-repair/phase4-visual-recognition/qa/preview-128-light.png`
- `work/akari-hq-apng/phase4-gap-repair/phase4-visual-recognition/qa/preview-128-dark.png`
- `work/akari-hq-apng/phase4-gap-repair/phase4-visual-recognition/qa/preview-160-light.png`
- `work/akari-hq-apng/phase4-gap-repair/phase4-visual-recognition/qa/preview-160-dark.png`

Use `request_user_input` choices for each tile. Send a short normal message immediately before the question UI appears.

Collect:

- `guessedState`: `idle`, `thinking`, `working`, `attention`, `error`, `notification`, or `sleeping`
- `confidence`: `high`, `medium`, or `low`
- cue notes for `sleeping`, `error`, `attention`, and `notification`

Preserve the human answers verbatim before comparing them to `answer-key.json`.

Keep `visualAcceptance: false` when any required answer is wrong or missing, confidence is low, cue notes are missing, or the human explicitly rejects the candidate.
