"""Parse the lab context file.

lab.md is the deliverable handout reduced to what a judge needs: one section per
task, carrying the Objective and the numbered steps that produce evidence. The
card joins to it by task number, so a criterion marked tasks: [3, 4] gets those
two sections in its prompt and nothing else.

Sending the whole handout with every criterion would be simpler and worse. It
crowds the context window, and it gives the judge instructions the criterion is
not about, which is how a criterion ends up penalised for work that belongs to a
different rubric row.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml

FRONT_MATTER_RE = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)
TASK_RE = re.compile(
    # The handouts are inconsistent: D01 uses a hyphen in its task headings,
    # D02 uses an en dash. Both, plus an em dash and a colon, are accepted.
    r"^##\s+Task\s+(?P<num>\d+)\s*[-–—:]?\s*(?P<title>.*?)\s*$", re.M)


class LabError(Exception):
    pass


OBJECTIVE_LINE_RE = re.compile(r"^\s*(?:>\s*)?(?:\*\*)?Objective:?(?:\*\*)?:?\s*(?P<body>.+?)\s*$",
                               re.M | re.I)


@dataclass
class Task:
    number: int
    title: str
    body: str

    @property
    def objective(self) -> str:
        """The handout's own Objective line for this task.

        This is the IMPORTANT prompt the student was given, so it is what they
        were told to achieve, and it outranks anything a grading guide says
        afterwards. Cards carry a copy and lint compares the two.
        """
        m = OBJECTIVE_LINE_RE.search(self.body)
        return m.group("body").strip() if m else ""

    def render(self) -> str:
        return f"## Task {self.number} - {self.title}\n\n{self.body.strip()}"


@dataclass
class Lab:
    path: Path
    meta: dict
    tasks: list[Task]

    def task_numbers(self) -> list[int]:
        return [t.number for t in self.tasks]

    def task(self, number: int) -> Task | None:
        for t in self.tasks:
            if t.number == number:
                return t
        return None

    def context_for(self, numbers: list[int]) -> str:
        """Render the named tasks, in lab order.

        An empty list means the criterion spans the whole report, for example a
        report standards row, so it gets every task.
        """
        wanted = set(numbers) if numbers else set(self.task_numbers())
        chosen = [t for t in self.tasks if t.number in wanted]
        if not chosen:
            return "(no task context recorded for this criterion)"
        return "\n\n".join(t.render() for t in chosen)


def load(path: str | Path) -> Lab:
    path = Path(path)
    if not path.is_file():
        raise LabError(f"no lab context at {path}")
    text = path.read_text(encoding="utf-8")

    meta: dict = {}
    m = FRONT_MATTER_RE.match(text)
    if m:
        meta = yaml.safe_load(m.group(1)) or {}
        text = text[m.end():]

    marks = list(TASK_RE.finditer(text))
    if not marks:
        raise LabError(
            f"{path.name} has no '## Task N - Title' headings. The card joins to "
            f"this file by task number, so the headings have to carry it."
        )
    tasks = []
    for i, mark in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        tasks.append(Task(
            number=int(mark.group("num")),
            title=mark.group("title").strip(),
            body=text[mark.end():end],
        ))
    return Lab(path=path, meta=meta, tasks=tasks)
