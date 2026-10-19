# Proposal: fix 1 for fix-logout-session

## Why
The verifier found problems in `fix-logout-session` that this change fixes. The findings are listed below with their ids; each task of this change names the ones it answers.

## What Changes
- F-5964e3de (blocker): lint gate failed: `sh .l4/gates/lint-go.sh` failed: exit code 1

## Impact
The code and the tests of `fix-logout-session`.
