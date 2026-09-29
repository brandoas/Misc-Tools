"""Local inference client.

One model, one host, no fallback. Student work is only ever sent to an Ohio ECT
inference box, and that is enforced here in code rather than left to a README.

Two reasons there is no provider fallback, unlike the other apps on these boxes
(PolAI, DARS AI) which chain through GitHub Models, Google and OpenRouter:

1. These are student lab reports. They do not leave the university.
2. A grade has to be reproducible. Silently switching models mid run means two
   students are graded by two different instruments, which is indefensible the
   first time one of them asks why.

If the configured host is down, the run fails and says so. That is the correct
behaviour.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from dataclasses import dataclass
from urllib.parse import urlsplit

from openai import AsyncOpenAI
from pydantic import BaseModel, ValidationError

#: Inference hosts this tool will talk to. Nothing else, ever.
ALLOWED_HOSTS = {"ai-01.its.ohio.edu", "spark-01.its.ohio.edu"}


@dataclass(frozen=True)
class Host:
    """A model on a host, with the concurrency that host actually supports.

    slots is OLLAMA_NUM_PARALLEL on the box: how many requests the runner will
    work on at once against one loaded model. Each slot holds its own KV cache,
    so the number is bounded by memory, not by choice. Matching the client to it
    keeps the GPU busy without piling up queue latency. Going higher does not
    make a batch finish sooner.
    """
    name: str
    base_url: str
    key_env: str
    model: str
    slots: int
    context: int


HOSTS: dict[str, Host] = {
    # Vision on spark, so an end to end run need not straddle two boxes.
    # qwen3-vl is single slot on this build regardless of OLLAMA_NUM_PARALLEL,
    # which costs nothing here because grading runs single slot anyway.
    "spark-vision": Host(
        name="spark-vision",
        base_url="http://spark-01.its.ohio.edu/v1",
        key_env="SPARK_API_KEY",
        model="qwen3-vl:30b-a3b",
        slots=1,
        context=32768,
    ),
    # ai-01: A10, 24 GB VRAM, OLLAMA_NUM_PARALLEL=2.
    "ai01": Host(
        name="ai01",
        base_url="https://ai-01.its.ohio.edu/v1",
        key_env="OHIO_API_KEY",
        model="gpt-oss:20b",
        slots=2,
        context=32768,
    ),
    # spark-01: GB10, unified memory, OLLAMA_NUM_PARALLEL=4, context pinned at
    # 32k by OLLAMA_CONTEXT_LENGTH after the 2026-09-19 out of memory incident.
    # Do not raise the context here expecting the box to honour it.
    "spark": Host(
        name="spark",
        base_url="http://spark-01.its.ohio.edu/v1",
        key_env="SPARK_API_KEY",
        model="gpt-oss:120b",
        slots=4,
        context=32768,
    ),
    # Image digest pass. Separate host entry rather than a separate concept,
    # because it is the same client with a different model.
    "ai01-vision": Host(
        name="ai01-vision",
        base_url="https://ai-01.its.ohio.edu/v1",
        key_env="OHIO_API_KEY",
        model="gemma4:12b",
        slots=2,
        context=32768,
    ),
}


class EngineError(Exception):
    pass


#: Per call timings for the whole process, appended by Engine.ask.
#: Kept as a plain module list rather than threaded through every call site:
#: the cost of a run is a property of the run, not of any one stage.
METRICS: list[dict] = []


def metrics_summary() -> dict:
    """Aggregate what the model calls cost, for the run report."""
    if not METRICS:
        return {}
    import statistics
    by_model: dict[str, list[dict]] = {}
    for m in METRICS:
        by_model.setdefault(m["model"], []).append(m)
    out = {"calls": len(METRICS),
           "wall_seconds": round(sum(m["seconds"] for m in METRICS), 1)}
    for model, rows in by_model.items():
        secs = [r["seconds"] for r in rows]
        out[model] = {
            "calls": len(rows),
            "seconds_total": round(sum(secs), 1),
            "seconds_median": round(statistics.median(secs), 1),
            "seconds_max": round(max(secs), 1),
            "prompt_chars_median": int(statistics.median(r["prompt_chars"] for r in rows)),
            "retries": sum(r["attempts"] - 1 for r in rows),
            "failures": sum(1 for r in rows if not r["ok"]),
        }
    return out


def _check_host_allowed(base_url: str) -> None:
    host = urlsplit(base_url).hostname or ""
    if host not in ALLOWED_HOSTS:
        raise EngineError(
            f"refusing to send student work to {host!r}. This tool only talks to "
            f"{', '.join(sorted(ALLOWED_HOSTS))}."
        )


class Engine:
    """Async client for one model on one host.

    Usage is deliberately narrow: ask for a JSON object matching a Pydantic
    model, get it back validated, or get an exception. There is no free form
    completion path, because everything this tool asks a model for is
    structured.
    """

    def __init__(self, host: str | Host = "ai01", *, model: str | None = None,
                 temperature: float = 0.0, seed: int = 20260926,
                 keep_alive: str | int = "30m", slots: int | None = None):
        h = HOSTS[host] if isinstance(host, str) else host
        if host not in HOSTS and isinstance(host, str):
            raise EngineError(f"unknown host {host!r}, expected one of {list(HOSTS)}")
        _check_host_allowed(h.base_url)

        key = os.environ.get(h.key_env)
        if not key:
            raise EngineError(
                f"no API key: set {h.key_env} in .env. Mint one in Open WebUI "
                f"under Account settings on {urlsplit(h.base_url).hostname}."
            )

        self.host = h
        self.model = model or h.model
        # Zero temperature and a fixed seed, so two runs over the same report
        # produce the same rating. A grader that disagrees with itself between
        # runs has no standing.
        self.temperature = temperature
        self.seed = seed
        self.keep_alive = keep_alive
        self._client = AsyncOpenAI(base_url=h.base_url, api_key=key, timeout=300.0)
        # Grading runs at one request in flight, not at the host's slot count.
        #
        # Measured on ai-01 against the same report three times: at two slots
        # the score came back 85, 74, 84, an eleven point spread on byte
        # identical input at temperature zero with a fixed seed. At one slot it
        # was 81, 83, 83, and passes two and three agreed on every criterion.
        #
        # The cause is batching. Ollama fills a batch from whatever requests are
        # in flight, and a batched floating point reduction is not associative,
        # so the same prompt yields different logits depending on what it was
        # batched with. Nothing on the client can make that reproducible.
        #
        # A grader that scores the same report 85 one run and 74 the next has no
        # standing, so the parallelism is spent. Callers that genuinely want the
        # throughput and not the reproducibility pass slots explicitly.
        self.slots = slots if slots is not None else 1
        self._sem = asyncio.Semaphore(self.slots)
        self._warm = False

    async def warmup(self) -> None:
        """One throwaway call so the first graded criterion is not the cold one.

        In the sequential variance test, passes two and three matched exactly
        and pass one did not. The first request after a model load carries
        different cache state, and paying for it once up front keeps it out of
        a student's grade.
        """
        if self._warm:
            return
        self._warm = True
        try:
            await self._client.chat.completions.create(
                model=self.model, temperature=0, seed=self.seed, max_tokens=1,
                messages=[{"role": "user", "content": "ok"}],
                extra_body={"keep_alive": self.keep_alive},
            )
        except Exception:
            pass  # a failed warmup is not a reason to refuse to grade

    async def ask(self, system: str, user: str, schema: type[BaseModel], *,
                  images: list[str] | None = None, retries: int = 2) -> BaseModel:
        """Send one prompt, return a validated instance of schema.

        Prompt ordering matters and is the caller's job: put the invariant part
        (the student report) at the top of `user` and the varying part (the
        criterion) at the bottom. Ollama reuses the KV cache for a shared prompt
        prefix, so judging one student's criteria consecutively prefills the
        report once instead of once per criterion.

        images are base64 data URLs, used only by the vision pass.
        """
        content: object = user
        if images:
            content = [{"type": "text", "text": user}] + [
                {"type": "image_url", "image_url": {"url": img}} for img in images
            ]

        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": content},
        ]

        last_error: Exception | None = None
        started = time.monotonic()
        attempts = 0
        async with self._sem:
            for attempt in range(retries + 1):
                attempts = attempt + 1
                try:
                    raw = await self._complete(messages, schema, attempt)
                    result = schema.model_validate_json(raw)
                    METRICS.append({
                        "host": self.host.name, "model": self.model,
                        "seconds": time.monotonic() - started,
                        "prompt_chars": len(system) + len(user),
                        "images": len(images or []),
                        "attempts": attempts, "ok": True,
                    })
                    return result
                except ValidationError as e:
                    # The model returned JSON that does not fit the schema. Show
                    # it what it got wrong rather than just asking again, which
                    # on a small model usually reproduces the same mistake.
                    last_error = e
                    messages = messages + [
                        {"role": "assistant", "content": raw},
                        {"role": "user", "content":
                            f"That did not match the required schema:\n{e}\n"
                            f"Return only a JSON object matching the schema. No prose."},
                    ]
                except json.JSONDecodeError as e:
                    last_error = e
                    messages = messages + [
                        {"role": "assistant", "content": raw},
                        {"role": "user", "content":
                            "That was not valid JSON. Return only a JSON object, no prose."},
                    ]
        METRICS.append({
            "host": self.host.name, "model": self.model,
            "seconds": time.monotonic() - started,
            "prompt_chars": len(system) + len(user),
            "images": len(images or []),
            "attempts": attempts, "ok": False,
        })
        raise EngineError(
            f"{self.model} did not return valid output after {retries + 1} attempts: "
            f"{last_error}"
        )

    async def _complete(self, messages: list[dict], schema: type[BaseModel],
                        attempt: int) -> str:
        """One round trip. Asks for a JSON schema, degrades to JSON mode.

        Ollama supports a JSON schema natively in its `format` field, but whether
        Open WebUI's /v1 gateway forwards response_format intact is a property of
        the gateway version, not something to assume. The first failure that
        looks like the gateway rejecting the parameter drops to plain JSON mode
        for the rest of the process, and the validate and retry loop above is
        what actually guarantees the shape either way.
        """
        kwargs: dict = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "seed": self.seed,
            "extra_body": {"keep_alive": self.keep_alive},
        }
        if _SCHEMA_SUPPORTED:
            kwargs["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": schema.__name__,
                    "strict": True,
                    "schema": schema.model_json_schema(),
                },
            }
        else:
            kwargs["response_format"] = {"type": "json_object"}

        try:
            resp = await self._client.chat.completions.create(**kwargs)
        except Exception as e:
            if _SCHEMA_SUPPORTED and _looks_like_unsupported_param(e):
                _disable_schema_mode(e)
                return await self._complete(messages, schema, attempt)
            if _is_repeat_loop(e) and attempt < 2:
                # Open WebUI aborts a generation that starts repeating itself.
                # Seen on the thin fixture, whose filler prose gives the model
                # little to say and every reason to say it twice. Retrying the
                # identical request reproduces the loop, because temperature is
                # zero and the seed is fixed, so the retry has to perturb
                # sampling to break out. Determinism is worth giving up here:
                # the alternative is no rating at all.
                kwargs["temperature"] = 0.3
                kwargs["seed"] = self.seed + attempt + 1
                resp = await self._client.chat.completions.create(**kwargs)
                return resp.choices[0].message.content or ""
            raise
        return resp.choices[0].message.content or ""

    async def close(self) -> None:
        await self._client.close()


_SCHEMA_SUPPORTED = True


def _looks_like_unsupported_param(e: Exception) -> bool:
    s = str(e).lower()
    return "response_format" in s or "json_schema" in s or "unsupported" in s


def _is_repeat_loop(e: Exception) -> bool:
    """Open WebUI's guard against a generation that starts repeating itself."""
    s = str(e).lower()
    return "repeat limit" in s or "prediction aborted" in s


def _disable_schema_mode(e: Exception) -> None:
    global _SCHEMA_SUPPORTED
    _SCHEMA_SUPPORTED = False
    print(f"note: gateway rejected json_schema response_format, falling back to "
          f"JSON mode for the rest of this run ({e})")
