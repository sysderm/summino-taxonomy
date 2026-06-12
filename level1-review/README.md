# Level-1 taxonomy review — three-model convergence

**Goal:** design the user-facing first level of the summino taxonomy. The
deep ~120k-node classifier taxonomy already exists; this is the
human-facing top — 12 to 25 categories the user picks from at onboarding,
sized to feel impressively broad on a single screen.

**Method:** ask three top models the same design question independently,
diff the answers, converge on the categories where 2 of 3 agree.

## Files

- `PROMPT.md` — the shared prompt. Paste verbatim into each model.
- `opus-4-8.json` — Opus 4.8 (Fable) answer. Already filled in.
- `gemini-2.5-pro.json` — TO FILL: paste PROMPT.md into Gemini 2.5 Pro
  (gemini.google.com or AI Studio), save the JSON response here.
- `gpt-5.json` — TO FILL: paste PROMPT.md into ChatGPT with the GPT-5
  model selected, save the JSON response here.

## Operator instructions

1. Open `PROMPT.md`. Copy the whole file.
2. **Gemini 2.5 Pro:**
   - Go to https://gemini.google.com or https://aistudio.google.com
   - Select Gemini 2.5 Pro
   - Paste the prompt. Wait for response.
   - Copy the JSON output (only the JSON, strip any markdown fence).
   - Save to `gemini-2.5-pro.json`.
3. **GPT-5:**
   - Go to https://chat.openai.com
   - Select GPT-5
   - Paste the prompt. Wait for response.
   - Copy the JSON output.
   - Save to `gpt-5.json`.
4. Tell me they're saved. I'll run the convergence diff and produce
   `level1-converged.json`.

## Convergence rules

- If 2 of 3 models name "Medicine" (or close synonym), it ships.
- If 2 of 3 models split "Physics" and "Astronomy", we split.
- If all 3 disagree on a category, operator decides.
- Aliases get unified: "CS", "Computer Science", "Computing & AI" → one
  canonical name.
- Final count target: ~18, range 15–22.
