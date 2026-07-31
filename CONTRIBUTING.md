# Contributing to O(1)mem

Thanks for taking the time. This project is small, opinionated, and field-tested on real
work — contributions are welcome, and the guidelines below exist because each one comes
from a bug that actually shipped.

Read this in other languages: [Português (Brasil)](./docs/CONTRIBUTING.ptbr.md)

---

## Four ground rules

These are not style preferences. A PR that breaks one of them will be asked to change.

### 1. Never commit memory data — this repository is public

The whole point of O(1)mem is to index your project's memory, and that memory is usually
private. The tooling is built so the data never enters the repository:

- the vector index persists at `~/.claude/o1mem/chroma/<slug>/`, never inside the worktree;
- `graph/graph.json` is generated locally and is already in `.gitignore`;
- `handover-nudge.log` lives under `~/.claude/`.

The same applies to **screenshots**. Every image in `assets/` must be synthetic sample data
or redacted. If a screenshot shows real node names, file names, or client identifiers, it
does not go in. When in doubt, generate a throwaway project and screenshot that instead.

### 2. The installer vendors its own copies — sync them or you ship a broken package

This is the single easiest way to send a fix to git and still leave every npm user broken.
The published package (`@tbluhm82/o1mem`) does not read the top-level folders; it carries
its own copies. **If you change a source file on the left, update the copy on the right in
the same commit:**

| Source of truth | Vendored copy inside the npm package |
|---|---|
| `handover/handover.py` | `installer/skills/handover/handover.py` |
| `handover/SKILL.md` | `installer/skills/handover/SKILL.md` |
| `organizador-mem/SKILL.md` | `installer/skills/organizador-mem/SKILL.md` |
| `retomar/SKILL.md` | `installer/skills/retomar/SKILL.md` |
| `rag/o1mem_rag.py`, `o1mem_rag_daemon.py`, `o1mem_distill.py` | `installer/vendor/rag/` |
| `graph/o1mem_graph.py` | `installer/vendor/graph/o1mem_graph.py` |
| `handover-nudge-hook/handover_nudge.py` | `installer/vendor/hook/handover_nudge.py` |

Check before you push:

```bash
bash tools/check-vendor-sync.sh
```

It exits non-zero and prints every file that drifted. Use `--strip-trailing-cr` semantics —
the script already does — because CRLF differences are noise, not drift.

### 3. Mechanics belong in code, not in prose

A skill is a `SKILL.md` (instructions the model reads) plus, where applicable, a `.py` that
does the mechanical work. The dividing line matters: **anything that must happen every time
— path validation, the history cap, decay, exit codes, coherence checks — goes in the
Python, where it is executed.** Instructions in prose are followed approximately; code is
followed exactly.

Concretely: if you want to add a new rule to `handover`, add it as a validation or a test in
`handover/handover.py`, not as another paragraph in `SKILL.md`. The skill file got to 182
lines of accumulated corrections before this rule existed; it is ~100 now, and the rules it
lost are the ones that are now enforced.

### 4. Numbers in the docs are observations, not promises

Every percentage in the README comes from a measured session and is labeled as such
(`n=1`, "order of magnitude, not a promise"). If you change a number, say where the new
measurement came from. If you add one, label its sample size. Do not turn an observed
result into a marketing claim — the credibility of the whole project rests on this.

---

## Repository layout — where to change what

| You want to change… | Edit here |
|---|---|
| how a skill behaves | `handover/`, `organizador-mem/`, `retomar/` (+ the vendored copy) |
| when the nudge fires | `handover-nudge-hook/handover_nudge.py` |
| semantic search / indexing | `rag/o1mem_rag.py` |
| the wikilink graph or its UI | `graph/` |
| the economy dashboard | `dashboard/` |
| npm install flow | `installer/lib/`, `installer/cli.js` |
| English docs | `README.md` (canonical) |
| Portuguese docs | `docs/README.ptbr.md` |

**Do not rename the skill folders.** `handover`, `retomar`, and `organizador-mem` are the
names users type as slash commands and the names the installer writes into `.claude/skills/`.
They are Portuguese, and they stay Portuguese — renaming them breaks every existing install.

---

## Running the tests

```bash
# npm installer (Node ≥ 16)
cd installer && node --test "test/*.test.js"

# semantic search — offline, no network, no model download
cd rag && python test_rag_offline.py
cd rag && python test_daemon_offline.py

# graph UI smoke test — needs a built graph.json first
cd graph && python o1mem_graph.py --project <slug> build
cd graph && node test_ui_smoke.js
```

The Python tests are offline by design: they must pass on a machine with no `chromadb`,
no model cache, and no network. If your change makes a test require the network, the
change is wrong, not the test.

Optional runtime dependencies (`chromadb`, `sentence-transformers`) are installed only by
users who opt into the `rag` skill — never make them mandatory for the rest of the toolkit.

---

## Pull requests

- **One concern per PR.** A fix and a refactor in the same diff will be asked to split.
- **Conventional commits**: `fix(rag): …`, `feat(graph): …`, `docs: …`. The subject line
  should say what changed, and the body should say *why* — the discarded alternative is
  usually more useful than the chosen one.
- **Say what you verified.** "Tests pass" is fine if they do. "Should work" is not — if you
  could not run something, say which part and why, rather than implying it was checked.
- If your change touches the npm package, bump `installer/package.json`. Publishing is done
  by the maintainer; the version bump in the PR is what makes it publishable.

---

## Reporting things

- **Bug** — use the bug report template. Include your OS, Python version, and Node version;
  a surprising number of issues here are Windows console encoding or path separators.
- **Your calibration numbers** — the README explicitly asks for these, and there is a
  template for it. Numbers that *disagree* with mine are more valuable than numbers that
  agree; they are what turns `n=1` into a real range.
- **Security or privacy issue** (e.g. a path where memory data could leak into a repo):
  please open a regular issue without including the sensitive content itself.

---

## Code of conduct

Be decent. Assume good faith, critique the work and not the person, and take disagreements
to the technical substance. Maintainers may close or lock threads that stop being useful.
