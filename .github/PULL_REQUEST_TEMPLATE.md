## What changes, and why

<!--
What the change does, and the reasoning behind it. The alternative you rejected is
usually more useful to a future reader than the option you picked.
-->

## How it was verified

<!--
Say what you actually ran and what it printed. If you could not verify part of it, say
which part and why — "should work" is fine to write as long as it is labeled as such,
and much better than implying it was tested.
-->

## Checklist

- [ ] **Vendored copies are in sync** — `bash tools/check-vendor-sync.sh` exits 0.
      (Skip only if this PR touches no file listed in that script.)
- [ ] **No memory data added to the repository** — no `graph.json`, no chroma index, no
      logs, and any screenshot uses synthetic or redacted data.
- [ ] **Nothing new was added to the boot path** — `MEMORY.md` remains the only thing
      loaded every session.
- [ ] **Mechanics live in code, not prose** — new rules for a skill are validations or
      tests in its `.py`, not additional paragraphs in `SKILL.md`.
- [ ] **Tests pass** for the parts touched:
      `cd installer && node --test "test/*.test.js"` ·
      `cd rag && python test_rag_offline.py`
- [ ] **`installer/package.json` version bumped**, if this changes anything shipped in the
      npm package.
- [ ] **Numbers are labeled** — any figure added or changed in the docs says where it was
      measured and over how many sessions.
