# README_AGENT — this branch was made by an AI agent

This branch (`agent/pymodaq-port/<date>`) was prepared automatically by the PyMoDAQ optimisation agents
(`/optimize-plugins port`, run `<run-id>`) on a fork owned by <owner>. It has not been tested on real hardware.
A person reviews it before anything is proposed to the plugin's author.

## Why
<one paragraph: what did not work with the current PyMoDAQ (from the assessment), e.g. legacy imports, entry points>

## What changed
- <change> — <reason> (commit `<sha>`)

## Checks
| check | before | after |
|---|---|---|
| `check_plugin <package> --strict-imports` | <errors/todos> | <errors/todos> |
| entry points import | <ok/fail> | <ok/fail> |
| plugin tests | <result or "none"> | <result> |

## Not done / not verified
- <hardware-only paths, vendor libraries, anything the agent could not run>

## How to review
`pip install -e .` in an environment with PyMoDAQ >= <version>, then `check_plugin <package>`, then open the plugin in
the DAQ_Move / DAQ_Viewer of the dashboard. Questions: <owner contact>.
