# Clerk

Code, spec and prompts only. Course data (cards, lab.md, rubrics, Evidence Maps,
fixtures) lives in each course repo's `Grading/`. Run directories live in
OneDrive. See `ASSESSMENT-CHAIN.md`.

## Sync rule

`prompts/chain/*.md` and `INPUT-SPEC.md` are masters with copies in
`ITS-3100-Devel/Grading/prompts/` and `ITS-4750-Infrastructure/Grading/prompts/`.
After changing any of them, run `./sync-prompts.sh` and tell Brandon both course
repos have changes to commit. Run `./sync-prompts.sh --check` at the start of any
prompt work; drift means someone edited a copy, so fold that into the master
first. Details in `SYNC.md`.
