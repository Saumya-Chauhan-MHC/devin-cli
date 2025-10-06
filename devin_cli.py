#!/usr/bin/env python3
"""
Devin + GitHub Issues CLI (Simplified Workflow, scoping-aware, PR spinner)

Workflow:
1) List issues from a GitHub repo
2) Scope ONE issue with Devin → print ONLY Devin’s final scoping message + native Confidence
3) Prompt to create a PR → ask Devin → poll for PR URL (structured_output or messages) with spinner

Env:
  DEFAULT_REPO=owner/repo                # default repo (optional; can pass --repo instead)
  GITHUB_TOKEN=ghp_...                   # required only for private repos
  DEVIN_API_KEY=apk_user_...             # Devin → Settings → Devin’s API
  DEVIN_API_BASE=https://api.devin.ai/v1 # (default)
  DEVIN_USE_GH_APP=true|false            # let Devin's GH App open PRs (default true)
"""

import os, time, random, re, datetime as dt
from typing import Optional, Dict, Any, List, Tuple

import requests
import typer
from rich.console import Console
from rich.panel import Panel
from tabulate import tabulate

# ---------- CLI ----------
app = typer.Typer(no_args_is_help=True)
issues_app = typer.Typer(help="GitHub issue workflow")
app.add_typer(issues_app, name="issues")
console = Console()

# ---------- Env ----------
DEFAULT_REPO   = os.getenv("DEFAULT_REPO", "")
GITHUB_TOKEN   = os.getenv("GITHUB_TOKEN", "")
DEVIN_API_KEY  = os.getenv("DEVIN_API_KEY", "")
DEVIN_API_BASE = os.getenv("DEVIN_API_BASE", "https://api.devin.ai/v1")
USE_DEVIN_GH_APP = os.getenv("DEVIN_USE_GH_APP", "true").lower() == "true"  

GH_H = {"Accept": "application/vnd.github+json"}
if GITHUB_TOKEN:
    GH_H["Authorization"] = f"Bearer {GITHUB_TOKEN}"
DV_H = {"Authorization": f"Bearer {DEVIN_API_KEY}"} if DEVIN_API_KEY else {}

# ---------- Tunables ----------
POLL_MSG_TIMEOUT_S  = 120   # wait up to 2 min for scoping messages
POLL_MSG_INTERVAL_S = 3
EXTRA_SCOPE_WAIT_S  = 45    # extra wait to catch Devin's final scoping block
POLL_PR_TIMEOUT_S   = 4000   # wait up to 4 min for PR URL
POLL_PR_INTERVAL_S  = 6

# ---------- HTTP with retries ----------
def _request_with_retries(method, url, headers=None, json=None, timeout=30, max_retries=4):
    attempt = 0
    while True:
        try:
            r = requests.request(method, url, headers=headers, json=json, timeout=timeout)
        except requests.RequestException:
            if attempt >= max_retries: raise
            time.sleep(1.0 + attempt * 0.8); attempt += 1; continue
        if 500 <= r.status_code < 600 and attempt < max_retries:
            time.sleep(1.0 + attempt * 0.8); attempt += 1; continue
        return r

# ---------- GitHub ----------
def gh_list_issues(repo: str, state="open"):
    if not repo:
        raise SystemExit("No repo provided. Pass --repo owner/repo or set DEFAULT_REPO.")
    url = f"https://api.github.com/repos/{repo}/issues?state={state}"
    r = _request_with_retries("GET", url, headers=GH_H, timeout=30)
    if r.status_code == 401:
        raise SystemExit("GitHub 401 — invalid/missing GITHUB_TOKEN for private repos (public repos don’t need it).")
    r.raise_for_status()
    return [i for i in r.json() if "pull_request" not in i]

def gh_get_issue(repo: str, number: int):
    url = f"https://api.github.com/repos/{repo}/issues/{number}"
    r = _request_with_retries("GET", url, headers=GH_H, timeout=30)
    if r.status_code == 404:
        raise SystemExit(f"Issue #{number} not found in {repo}.")
    r.raise_for_status()
    return r.json()

# ---------- Devin API ----------
def devin_create_session(prompt: str, title: str) -> Dict[str, Any]:
    if not DEVIN_API_KEY:
        raise SystemExit("DEVIN_API_KEY is not set. Get it from Devin → Settings → Devin’s API.")
    nonce = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    body = {
        "prompt": f"{prompt}\n\n[session_nonce:{nonce}]",
        "idempotent": False,  # force new session
        "title": f"{title} • {nonce}",
    }
    r = _request_with_retries("POST", f"{DEVIN_API_BASE}/sessions", headers=DV_H, json=body, timeout=60)
    if r.status_code == 401:
        raise SystemExit("Devin API 401: Invalid/expired key. Regenerate in Devin → Settings → Devin’s API.")
    r.raise_for_status()
    ses = r.json()
    console.print(f"[dim]New Devin session:[/] {ses.get('session_id')} • {body['title']}")
    return ses

def devin_send_message(session_id: str, message: str):
    _request_with_retries("POST",
        f"{DEVIN_API_BASE}/sessions/{session_id}/message",
        headers={**DV_H, "Content-Type": "application/json"},
        json={"message": message}, timeout=30)

def devin_get_session(session_id: str) -> Dict[str, Any]:
    r = _request_with_retries("GET", f"{DEVIN_API_BASE}/sessions/{session_id}", headers=DV_H, timeout=30)
    r.raise_for_status()
    return r.json()

# ---------- Confidence extraction ----------
CONF_LINE_RE = re.compile(
    r"""(?imx)
    ^\s*Confidence[^:\n]*:\s*
    (?P<label>High|Medium|Low|Green|Yellow|Red)?\s*
    (?P<emoji>[🟢🟡🔴])?
    (?:\s*[-–—:]\s*(?P<why>.+))?
    $
    """
)

def extract_confidence_from_texts(texts: List[str]) -> Tuple[Optional[str], Optional[str]]:
    for t in reversed(texts[-20:]):
        for line in reversed(t.splitlines()[-12:]):
            mo = CONF_LINE_RE.search(line)
            if not mo: continue
            emoji = (mo.group("emoji") or "").strip()
            label = (mo.group("label") or "").strip().lower()
            why   = (mo.group("why") or "").strip()
            if emoji in {"🟢","🟡","🔴"}:
                return {"🟢":"green","🟡":"yellow","🔴":"red"}[emoji], why
            if label in {"green","yellow","red"}:
                return label, why
            if label in {"high","medium","low"}:
                return {"high":"green","medium":"yellow","low":"red"}[label], why
    return None, None

# ---------- Message helpers ----------
def is_user_message(m: Dict[str, Any]) -> bool:
    t = (m.get("type") or "").lower()
    o = (m.get("origin") or "").lower()
    return t in {"initial_user_message","user_message"} or o == "api"

def is_devin_message(m: Dict[str, Any]) -> bool:
    return not is_user_message(m)

def newest_devin_after(messages: List[Dict[str, Any]], baseline_len: int) -> List[str]:
    new_msgs = messages[baseline_len:]
    return [m.get("message","") for m in new_msgs if is_devin_message(m) and m.get("message")]

def looks_like_scoping(text: str) -> bool:
    tl = text.lower()
    if "confidence:" in tl:
        return True
    keys = ["current", "requested", "files", "tests", "risks"]
    return sum(1 for k in keys if k in tl) >= 2

# ---------- Pollers ----------
def poll_for_final_scoping(session_id: str, baseline_len: int,
                           timeout_s=POLL_MSG_TIMEOUT_S,
                           extra_wait_s=EXTRA_SCOPE_WAIT_S) -> Tuple[List[str], Dict[str, Any]]:
    """
    Poll until a Devin-authored message that *looks like scoping* appears after baseline.
    If first we see a “thinking” message, keep polling up to extra_wait_s.
    """
    deadline = time.time() + timeout_s
    best_text: Optional[str] = None
    snap: Dict[str, Any] = devin_get_session(session_id)

    while time.time() < deadline:
        time.sleep(POLL_MSG_INTERVAL_S)
        snap = devin_get_session(session_id)
        msgs = snap.get("messages") or []
        new_devins = newest_devin_after(msgs, baseline_len)
        for txt in reversed(new_devins):
            if looks_like_scoping(txt):
                return [txt], snap
            if best_text is None:
                best_text = txt

    end2 = time.time() + extra_wait_s
    while time.time() < end2:
        time.sleep(POLL_MSG_INTERVAL_S)
        snap = devin_get_session(session_id)
        msgs = snap.get("messages") or []
        new_devins = newest_devin_after(msgs, baseline_len)
        for txt in reversed(new_devins):
            if looks_like_scoping(txt):
                return [txt], snap
            if best_text is None:
                best_text = txt

    return ([best_text] if best_text else []), snap

PR_URL_RE = re.compile(r"https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/pull/\d+")

def poll_for_pr_url(session_id: str, timeout_s=POLL_PR_TIMEOUT_S) -> Optional[str]:
    """
    Poll Devin session until PR URL appears (structured_output.artifacts.pr_url OR inside Devin messages).
    Shows a small spinner while polling.
    """
    deadline = time.time() + timeout_s
    spinner = ["⠋","⠙","⠹","⠸","⠼","⠴","⠦","⠧","⠇","⠏"]
    i = 0
    seen_len = 0

    while time.time() < deadline:
        time.sleep(POLL_PR_INTERVAL_S)
        cur = devin_get_session(session_id)
        # 1) structured_output
        so = cur.get("structured_output") or {}
        art = so.get("artifacts") or {}
        pr_url = art.get("pr_url")
        if pr_url:
            console.print("\r", end="")
            return pr_url

        # 2) messages text
        msgs = cur.get("messages") or []
        new_msgs = msgs[seen_len:]
        for m in new_msgs:
            txt = m.get("message","") or ""
            mo = PR_URL_RE.search(txt)
            if mo:
                console.print("\r", end="")
                return mo.group(0)
        seen_len = len(msgs)

        # spinner
        console.print(f"\r{spinner[i]}  polling Devin for PR...", end="", style="dim")
        i = (i + 1) % len(spinner)

    console.print("\r", end="")
    return None

# ---------- CLI Commands ----------
@issues_app.command("list")
def list_issues(repo: str = typer.Option(DEFAULT_REPO or ..., help="owner/repo")):
    issues = gh_list_issues(repo)
    rows = [[i["number"], i["title"], i["state"],
             ",".join([l["name"] for l in i.get("labels", [])]),
             i["html_url"]] for i in issues]
    console.print(Panel.fit(f"[bold]{repo}[/] • {len(rows)} issues"))
    print(tabulate(rows, headers=["#", "title", "state", "labels", "url"], tablefmt="github"))

@issues_app.command("scope")
def scope_issue(number: int = typer.Option(..., "-n", help="issue number"),
                repo: str = typer.Option(DEFAULT_REPO or ..., help="owner/repo"),
                open_url: bool = typer.Option(True, help="open Devin session URL")):
    """
    Scope ONE issue (clean UX):
    - Start a fresh Devin session (non-idempotent)
    - Poll until a *final* scoping block appears (or timeout)
    - Print only Devin’s scoping + native Confidence
    - Prompt to create a PR (optionally let Devin’s GH app open the PR)
    """
    issue = gh_get_issue(repo, number)
    console.print(Panel.fit(f"[bold]Scoping issue #{number}[/]\n{issue['title']}"))

    # Create session
    prompt = (
        f"Scope this issue in repo https://github.com/{repo}.\n"
        f"Title: {issue['title']}\n\nBody:\n{issue.get('body','')}\n\n"
        "Please write your scoping in the conversation (Current / Requested / Files / Tests / Risks if any).\n"
        "Include a line exactly like:\n"
        "Confidence: High 🟢 - <why>   (or Medium 🟡 / Low 🔴)\n"
        "Then wait for next instruction."
    )
    ses = devin_create_session(prompt, f"Scope {repo}#{number}")
    sid = ses["session_id"]
    if open_url and ses.get("url"):
        console.print(f"[dim]Session:[/] {ses['url']}")

    # Baseline & poll for scoping
    initial = devin_get_session(sid)
    baseline_len = len(initial.get("messages") or [])
    scoping_texts, snap = poll_for_final_scoping(sid, baseline_len, POLL_MSG_TIMEOUT_S, EXTRA_SCOPE_WAIT_S)

    # Print scoping
    console.rule(f"Scoping result for #{number}")
    if scoping_texts:
        combined = "\n\n".join(scoping_texts)
        console.print(Panel.fit(combined, title="Devin’s scoping", border_style="cyan"))
    else:
        console.print("[yellow]No scoping message yet — showing latest Devin messages.[/]")
        msgs = snap.get("messages") or []
        new_devins = newest_devin_after(msgs, baseline_len)
        combined = "\n\n".join(new_devins[-2:]) if new_devins else (msgs[-1].get("message","") if msgs else "")
        console.print(Panel.fit(combined or "(no content)", title="Latest messages"))

    # Confidence (prefer scoping_texts; fallback to all)
    msgs_all = snap.get("messages") or []
    color, why = extract_confidence_from_texts(scoping_texts)
    if not color:
        color, why = extract_confidence_from_texts([m.get("message","") for m in msgs_all if m.get("message")])
    display_conf = color or "-"
    console.print(f"\n[bold]Confidence:[/] {display_conf}{f' — {why}' if why else ''}")

    # Prompt to PR
    choice = input(f"\nCreate a PR for issue #{number}? [y/N]: ").strip().lower()
    if choice != "y":
        console.print("[yellow]Skipped PR creation.[/]")
        return

    if not USE_DEVIN_GH_APP:
        console.print(
            "[yellow]DEVIN_USE_GH_APP=false — not sending PR to Devin.\n"
            "Enable DEVIN_USE_GH_APP=true to let Devin open PRs via its GitHub integration,\n"
            "or wire a local gh/pat-based PR flow here.\n"
        )
        return

    # Ask Devin to open PR (via GitHub App)
    pr_instr = (
        f"Create a branch `devin/issue-{number}` in https://github.com/{repo}.\n"
        "Implement the scoped changes with minimal safe tests and open a PR.\n"
        "When done, write the PR URL into structured_output.artifacts.pr_url."
    )
    devin_send_message(sid, pr_instr)

    pr_url = poll_for_pr_url(sid, timeout_s=POLL_PR_TIMEOUT_S)
    if pr_url:
        console.print(Panel.fit(f"[green]✅ PR Created[/]\n{pr_url}", border_style="green"))
    else:
        console.print(Panel.fit(
            "[yellow]⚠️ No PR URL detected yet.[/]\n"
            "You can monitor progress in the Devin session:\n"
            f"{ses.get('url','(session url unavailable)')}"
        ))

def main():
    app()  # this runs the Typer CLI

if __name__ == "__main__":
    app()
