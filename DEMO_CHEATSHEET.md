# DEMO CHEAT SHEET — Read this before you go in

## Before you leave the house
1. Open a terminal in the `code-review-engine` folder.
2. Run: `bash setup_and_test.sh` (Mac/Linux) — Windows users, see below.
3. Confirm you see "SUCCESS. Everything works." at the bottom.
4. Take a screenshot of the successful output as a backup in case wifi/projector
   fails during the actual review.

## Windows users — run these one at a time
```
pip install -r requirements.txt
python cli.py samples\bad_example.py --chart chart1.png
python cli.py samples\good_example.py --chart chart2.png
python -m pytest tests/ -v
```

---

## THE ACTUAL DEMO (3 commands, ~2 minutes)

### Command 1 — show it catching real problems, with a chart
```
python cli.py samples/bad_example.py --chart demo_chart.png
```
**What to say while it runs:**
"This is a Python file we deliberately wrote with common mistakes. The tool
reads it — without running the code at all — and tells us exactly what's
wrong and where. It also saves a visual summary chart alongside the text."

**What to point at on screen:**
- `[CRITICAL] SEC002` — *"This caught a password typed directly into the
  code — a real security risk."*
- `[CRITICAL] SEC001` — *"This caught a call to `eval()`, which can run
  arbitrary code — a classic vulnerability."*
- Bottom line: *"14 issues found, 2 critical — so the quality gate
  automatically fails. In a real pipeline, this blocks the merge."*
- Open `demo_chart.png` — *"Same results, but visual — severity on the
  left, category breakdown on the right."*

### Command 2 — show it passes clean code
```
python cli.py samples/good_example.py --chart demo_chart2.png
```
**What to say:**
"Here's a properly written version of similar code. Zero issues, quality
gate passes. This proves the tool distinguishes clean code from bad code —
it isn't just flagging everything."

### Command 3 — show it's tested, not just working by luck
```
python -m pytest tests/ -v
```
**What to say:**
"We wrote 7 automated tests that check every rule individually — all
passing. That means we can keep adding rules later without breaking what
already works."

### Optional Command 4 — if asked about automation
```
cat .github/workflows/ci.yml
```
**What to say:**
"This is the GitHub Actions workflow — every time code is pushed, this
runs automatically: install dependencies, run the analyzer, run the
tests, and upload the report as a downloadable artifact. No one has to
run this by hand."

---

## IF SOMETHING BREAKS LIVE

- **If Python isn't found:** try `python3` instead of `python`
- **If wifi/projector fails:** show the screenshot you took last night
- **If pytest isn't found:** run `pip install pytest matplotlib` first
- **If a reviewer asks "why Python?"**: *"Python's built-in AST module lets
  us understand code structure natively, without needing an external
  parser."*
- **If asked "what's next?"**: *"Capstone-2 wires this into full deployment
  — Docker, Kubernetes, and monitoring — all already scoped in our
  architecture."*
- **If asked "did you write this yourself?"**: be honest about using AI
  assistance for scaffolding — most panels are fine with this as long as
  you can explain how it works, which you can (walk through rules.py →
  engine.py → cli.py if asked).

## ONE-LINE SUMMARY IF YOU GET FLUSTERED
"It's a robot that reads code and flags problems automatically — like a
spellchecker, but for security and bugs instead of grammar."
