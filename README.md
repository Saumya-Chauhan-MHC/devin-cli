# Devin Issues CLI

### *Fast-track GitHub issue scoping and PR creation with Devin*

The **Devin Issues CLI** lets you move backlog fixes from idea → scoped → PR in minutes — directly from your terminal.
It connects your GitHub repository to **Devin**, automatically scoping issues, estimating risk, and optionally opening pull requests via Devin’s GitHub App.

---

## Features

* List and filter GitHub issues right from your terminal
* Send an issue to Devin for full scoping (Current / Requested / Files / Tests / Risks)
* Extract Devin’s **native confidence signal** (🟢 / 🟡 / 🔴)
* Let Devin’s GitHub App create branches and open PRs automatically
* Zero PAT risk — uses Devin’s secure integration permissions

---

## Setup Guide

### Clone this repository

```bash
git clone https://github.com/Saumya-Chauhan-MHC/devin-cli.git
cd devin-cli
```

### Create and activate a virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate     # (Mac / Linux)
# .venv\Scripts\activate      # (Windows)
```

You’ll know it’s active when you see **(.venv)** in your terminal prompt.

---

### Install dependencies

For editable (developer) install:

```bash
pip install -e .
```

Or manually (if testing before packaging):

```bash
pip install typer==0.12.5 click==8.1.7 requests==2.32.3 rich==13.9.2 tabulate==0.9.0
```

---

### Create your environment file

Copy the example and edit with your keys:

```bash
cp .env.example .env
```

Then open **.env** and fill in your real values:

```bash
DEFAULT_REPO=your-org/your-repo
GITHUB_TOKEN=ghp_your_github_token_here
DEVIN_API_KEY=apk_user_your_devin_api_key_here
DEVIN_USE_GH_APP=true
```

Load it into your shell:

```bash
export $(grep -v '^#' .env | xargs)
```

---

### Connect Devin ↔ GitHub

1. Open **Devin → Settings → Integrations → GitHub**
2. Click **Connect** and install the **Devin GitHub App** on the repo(s) you want it to manage
3. This allows Devin to:

   * Create branches (e.g. `devin/issue-123`)
   * Open PRs securely
   * Never expose your PAT

---

## Usage

| Step           | Command                                                                    | Description                                                         |
| -------------- | -------------------------------------------------------------------------- | ------------------------------------------------------------------- |
| List issues | `devin-cli issues list --repo Saumya-Chauhan-MHC/devin-demo-service`       | Lists open GitHub issues                                            |
| Scope issue | `devin-cli issues scope -n 1 --repo Saumya-Chauhan-MHC/devin-demo-service` | Starts a Devin session to analyze the issue                         |
| Confidence  | *(auto)*                                                                   | Devin prints the full scoping plan and native confidence (🟢 🟡 🔴) |
| Create PR    | Press `y` when prompted                                                    | Devin creates a branch and opens a PR through its GitHub App        |

Example CLI output:

```
Devin’s scoping
Current: /health returns 500 due to NoneType in probe
Requested: Handle probe=None safely
Tests: probe=None, probe={'status':'fail'}
Confidence: High 🟢 — straightforward fix

✅ PR Created
https://github.com/Saumya-Chauhan-MHC/devin-demo-service/pull/9
```

---

### List open issues

```bash
devin-cli issues list --repo your-org/your-repo
```

Shows open issues with titles, labels, and URLs.

---

### Scope an issue

```bash
devin-cli issues scope -n 123 --repo your-org/your-repo
```

The CLI:

1. Starts a fresh Devin session
2. Waits for Devin’s final scoping message (not the first “thinking” line)
3. Prints the entire scoping plan and the native confidence line
4. Prompts to create a PR if confidence 🟢 / 🟡

Example output:

```
Devin’s scoping
Current behavior: …  
Requested fix: …  
Files to modify: …  
Tests needed: …  
Confidence: Medium 🟡 – Moderate change, low risk.

Create a PR for issue #123? [y/N]:
```

---

### Automatic PR Creation

If you hit **Y**, Devin’s GitHub App will:

* Create a branch `devin/issue-123`
* Implement the change + tests
* Open a pull request
* Return the PR URL once ready

While polling, you’ll see:

```
⠙ polling Devin for PR...
✅ PR Created
https://github.com/your-org/your-repo/pull/9
```

---

## Example Demo Repository

For demos and testing, this CLI uses the **[Devin Demo Service](https://github.com/Saumya-Chauhan-MHC/devin-demo-service)** —
a lightweight Python microservice with 3 example issues:

```
#1  Bug: /health intermittently returns 500 (staging)
#2  Feature: Add Prometheus /metrics endpoint
#3  Enhancement: Structured JSON logs + request_id propagation
```

You can fork this repo to your own GitHub account (recommended for testing PRs) or clone it locally to explore the code.

---

## Expected Output

* Full scoping response from Devin in your terminal
* Confidence line (e.g. “High 🟢 — straightforward fix”)
* PR URL or Devin session link for follow-up

---

## Demo Video

See the 5-minute walkthrough:
[**Devin CLI Demo/Video Guide**](https://www.loom.com/share/83ca12c2be174387a53ad76f60e5d7b3?sid=b20a888e-99e7-4311-8ad1-2d2efad2f20a) 

---

## Repository Structure

```
devin-cli/
├── devin_cli.py          # main CLI logic (list, scope, PR)
├── requirements.txt      # dependency list
├── pyproject.toml        # CLI packaging config
├── .env.example          # environment template (do not commit real .env)
├── .gitignore            # ignore build + secrets
└── README.md             # this file
```

---

## Contributing

Contributions welcome!
Submit PRs to add new commands (e.g. ranked prioritization or bulk scoping).
Follow [PEP 8](https://peps.python.org/pep-0008/) and include type annotations.

---

## License

MIT License © 2025 Saumya Chauhan — Feel free to use and adapt for internal DevOps automation.
