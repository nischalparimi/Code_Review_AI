#!/usr/bin/env bash
# setup_and_test.sh
# Run this ONCE tonight to make sure everything works before tomorrow's demo.
# Usage: bash setup_and_test.sh

set -e

echo "=================================================="
echo "STEP 1: Checking Python is installed"
echo "=================================================="
python3 --version || { echo "Python 3 not found. Install it from python.org first."; exit 1; }

echo ""
echo "=================================================="
echo "STEP 2: Installing dependencies (pytest, matplotlib)"
echo "=================================================="
pip3 install -r requirements.txt --quiet 2>/dev/null \
  || pip install -r requirements.txt --quiet 2>/dev/null \
  || pip3 install -r requirements.txt --quiet --break-system-packages 2>/dev/null \
  || pip3 install -r requirements.txt --quiet --user 2>/dev/null \
  || echo "Could not auto-install dependencies. If later steps fail, run: pip install pytest matplotlib --user"

echo ""
echo "=================================================="
echo "STEP 3: Running the analyzer on the BAD sample file"
echo "(This should show ~14 issues, including 2 CRITICAL, and save a chart)"
echo "=================================================="
python3 cli.py samples/bad_example.py --chart /tmp/setup_check_bad.png || true

echo ""
echo "=================================================="
echo "STEP 4: Running the analyzer on the GOOD sample file"
echo "(This should show 0 issues, gate PASSES, and save a chart)"
echo "=================================================="
python3 cli.py samples/good_example.py --chart /tmp/setup_check_good.png

echo ""
echo "=================================================="
echo "STEP 5: Running the automated test suite"
echo "(All 7 tests should say PASSED)"
echo "=================================================="
python3 -m pytest tests/ -v

echo ""
echo "=================================================="
echo "SUCCESS. Everything works. You are ready for tomorrow."
echo "=================================================="
