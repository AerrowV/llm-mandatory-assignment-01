# Setup and Run Guide

This project runs a small AI software team on your own computer. Six roles
(architect, tech lead, two coders, tester, docs writer, deploy checker) are
OpenHands agents. They use two local model servers, so nothing goes to the
cloud. They work as a team: they share a team chat, and when tests fail the
coders get the failures and try again.

Plan on about 20 minutes for setup and 15–25 minutes for one run.

---

## Step 1 — Install the tools

| Tool | How to get it | Check it works |
| --- | --- | --- |
| Docker Desktop | <https://www.docker.com/products/docker-desktop> | `docker compose version` |
| Ollama | <https://ollama.com/download> (or `brew install ollama`) | `ollama --version` |
| Python 3.11+ | <https://www.python.org/downloads> (or `brew install python`) | `python3 --version` |
| Git | usually already installed | `git --version` |

Start Docker Desktop and leave it running. A Mac with 16 GB of memory works;
32 GB is more comfortable.

## Step 2 — Get the project

```bash
git clone <this repository> llm-mandatory-assignment-01
cd llm-mandatory-assignment-01
cp .env.example .env
```

`.env` holds every setting. The defaults work, so you do not need to edit it.

## Step 3 — Start the two model servers

The workflow uses two separate model servers. Open a terminal for each.

**Terminal 1 — endpoint A** (planning roles, port 11434):

```bash
ollama serve
```

If the Ollama app is already running, endpoint A is already up and you can
skip this command.

**Terminal 2 — endpoint B** (coding roles, port 11435):

```bash
OLLAMA_HOST=127.0.0.1:11435 OLLAMA_MODELS=~/.ollama-b/models \
  OLLAMA_NUM_PARALLEL=2 OLLAMA_FLASH_ATTENTION=1 ollama serve
```

**Terminal 3 — download the models** (only once, a few GB):

```bash
ollama pull qwen2.5:3b
OLLAMA_HOST=127.0.0.1:11435 ollama pull llama3.1:8b
```

## Step 4 — Check that everything is ready

```bash
python3 scripts/pipeline.py --check
```

This starts the LiteLLM proxy and OpenHands in Docker. The first time, it
downloads them, so give it a few minutes. You should see four `[ok]` lines:

```
  [ok] endpoint A qwen2.5:3b -> architect,techlead,docs
  [ok] endpoint B llama3.1:8b -> coder-1,coder-2,tester,deploy-validator
  [ok] litellm up
  [ok] openhands up
```

## Step 5 — Run the team

```bash
python3 scripts/pipeline.py
```

Watch the agents work live at <http://localhost:8000>.

The roles run in this order. Each one must deliver its files before the next
one starts:

| # | Role | Server | What it produces |
| --- | --- | --- | --- |
| 1 | architect | A | `docs/components.md`, `api.md`, `deployment.md`, `decisions.md`, `handoff.md` |
| 2 | techlead | A | `tickets/list.md` and one file per ticket |
| 3 | coder-1 and coder-2, at the same time | B | `storage.py` and `server.py` in `workspace/demo-project/src/todoapp/`, each on its own git branch |
| 4 | tester | B | runs the tests, writes `workspace/demo-project/QUALITY.md` |
| ↺ | fix rounds | B | if tests fail, the coders get the failures and their last attempt and try again (up to 2 rounds; a fix is kept only if more tests pass) |
| 5 | docs | A | `workspace/demo-project/README.md` |
| 6 | deploy-validator | B | runs `docker/validate.sh`, writes `docs/deployment-validation.md` |

Every role ends with a short message to the team, and every later role sees
those messages. At the end you get a summary like this:

```
== summary
  FR1  architect            96s  verified
  FR2  techlead             39s  verified
  ...
  record: artifacts/runs/<time>/run.json, team-chat.md
```

## Step 6 — Look at the results

| What | Where |
| --- | --- |
| What the roles said to each other | `artifacts/runs/<time>/team-chat.md` |
| Pass/fail and time per stage | `artifacts/runs/<time>/run.json` |
| Each coder's changes | `git diff main agent/coder-1` and `git diff main agent/coder-2` |
| Run the demo app's tests yourself | `cd workspace/demo-project && python3 -m unittest discover -s tests` |
| Deployment checks on their own | `./docker/validate.sh` |

## Step 7 — Stop

```bash
docker compose stop
```

Then press `Ctrl+C` in the `ollama serve` terminals.

---

## More options

```bash
python3 scripts/pipeline.py --from tester          # resume at a role
python3 scripts/pipeline.py --compare RUN_A RUN_B  # compare two runs (folder names in artifacts/runs/)
```

- **Use other models, or move a role to the other server:** edit `.env`
  (`ENDPOINT_A_MODEL`, `ENDPOINT_B_ROLES`, …). The next run picks it up.
- **Make the agents ask before running commands:** set `CONFIRMATION=risky`
  in `.env`.
- **Change what an agent is told:** every instruction is in `prompts/`, one
  file per role, plus the shared messages in `prompts/shared/`.

## If something goes wrong

| Problem | What to do |
| --- | --- |
| `[FAIL] endpoint A` or `endpoint B` | that `ollama serve` is not running — see Step 3 |
| `litellm did not start` or `openhands did not start` | open Docker Desktop, then run Step 4 again |
| A stage says `did not deliver` | small models sometimes miss; resume with `python3 scripts/pipeline.py --from <role>` |
| An agent writes text instead of doing the work | the model cannot make tool calls; pick another model in `.env` |
| Everything is slow | close other heavy apps; the coders and tester need the most memory |
