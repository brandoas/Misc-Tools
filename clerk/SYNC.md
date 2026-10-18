# Sync rule: prompts are copied into the course repos

The master copies of the assessment chain prompts are `prompts/chain/*.md` and
`INPUT-SPEC.md`, here. Both course repos carry identical copies in
`Grading/prompts/`, because the machines that run the QA and Lab Manager
contexts often have only their own course repo checked out.

**After any change to `prompts/chain/` or `INPUT-SPEC.md`, run:**

```text
./sync-prompts.sh            copy to ITS-3100-Devel and ITS-4750-Infrastructure
./sync-prompts.sh --check    report drift without changing anything
```

Then tell Brandon both course repos have changes to commit.

Edit the master here, never a copy. If a copy in a course repo has been edited
by hand, `--check` shows it as drift: fold the change into the master first,
then sync, or it will be overwritten.

The prompts are written so they read correctly from either place: they name
files relative to the course repo (`Grading/...`) and say what to do when
`Misc-Tools` is not on the machine.
