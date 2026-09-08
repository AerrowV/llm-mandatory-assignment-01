# Project Structure

project-root/
├── README.md                      
├── config/                        # shared config
│
├── openhands/             
│   ├── setup.md                   # install + endpoint setup steps
│   ├── config.yaml                # 2 local endpoint configs + role bindings
│   ├── prompts/                   # phase prompts: architect, tech lead, docs, etc.
│   ├── docs/                      # architecture, tickets, README, runbook, checklist
│   ├── src/                       # implemented feature (git tracked)
│   └── tests/                     # test files + results
│
└── crewai/                
    ├── setup.md                   # install + endpoint setup steps
    ├── config.yaml                # 2 local endpoint configs + role bindings
    ├── agents.py                  # role/agent definitions
    ├── tools.py                   # file/git/test tool glue
    ├── docs/                      # architecture, tickets, README, runbook, checklist
    ├── src/                       # implemented feature (git tracked)
    └── tests/                     # test files + results

## Notes
- Each system is self-contained: run it, and its `docs/`, `src/`, `tests/`
  folders fill up with that system's output.
- Compare the two systems' folders side by side for the synopsis.
- `config.yaml` in each system points to the same 2 local endpoints —
  only the role→endpoint bindings may differ.