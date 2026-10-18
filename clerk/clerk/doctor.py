"""Preflight: prove the inference host is usable before grading anything.

Six checks, in the order they fail in practice. Each one prints what to do about
it rather than just what went wrong, because every failure here has a specific
fix on the box and none of them are guessable from a stack trace.

    python -m clerk doctor
    python -m clerk doctor --host spark

Check 5 is the one worth having. Ollama supports a JSON schema natively, but
whether Open WebUI's /v1 gateway forwards response_format intact is a property
of the gateway build, not something to assume. The grader works either way, and
this says which path it will take before a batch run rather than during one.
"""

from __future__ import annotations

import asyncio
import os
import time
from urllib.parse import urlsplit

import httpx
from pydantic import BaseModel

from .engine import HOSTS, Engine, EngineError

OK, BAD, WARN = "  ok  ", " FAIL ", " warn "


class _Probe(BaseModel):
    answer: int
    units: str


def _say(status: str, text: str, detail: str = "") -> None:
    print(f"[{status}] {text}")
    if detail:
        for line in detail.strip().split("\n"):
            print(f"         {line}")


def cmd_doctor(args) -> int:
    host = HOSTS[args.host]
    site = urlsplit(host.base_url)
    origin = f"{site.scheme}://{site.netloc}"
    failures = 0

    print(f"checking {host.name}: {host.model} at {host.base_url}\n")

    # 1. Key present.
    key = os.environ.get(host.key_env)
    if key:
        _say(OK, f"{host.key_env} is set ({key[:6]}...{key[-4:]}, {len(key)} chars)")
    else:
        failures += 1
        _say(BAD, f"{host.key_env} is not set", f"""
Put it in Misc-Tools/clerk/.env as:
    {host.key_env}=sk-...
Get it from {origin} under Settings, Account, API keys.
""")
        return _finish(failures)

    # 2. Host reachable.
    t0 = time.time()
    try:
        r = httpx.get(f"{origin}/health", timeout=15.0)
        _say(OK, f"{site.hostname} is reachable "
                 f"({r.status_code}, {(time.time() - t0) * 1000:.0f} ms)")
    except Exception as e:
        failures += 1
        _say(BAD, f"cannot reach {site.hostname}", f"""
{e}
spark-01 is on a private 10.x address and is reachable from the campus and ECT
networks only. ai-01 is public. Check VPN if you are off campus.
""")
        return _finish(failures)

    # 3. The key authenticates.
    try:
        r = httpx.get(f"{host.base_url}/models",
                      headers={"Authorization": f"Bearer {key}"}, timeout=30.0)
    except Exception as e:
        failures += 1
        _say(BAD, "could not list models", str(e))
        return _finish(failures)

    if r.status_code == 401:
        failures += 1
        _say(BAD, "the key was rejected (401)", """
Either the key is wrong, or your account is still 'pending'. Open WebUI on this
box runs DEFAULT_USER_ROLE=pending, so a new signup can do nothing at all until
an admin approves it, and an API key minted by a pending account gets a 401.

On the box, see where your account stands:

    docker exec open-webui python3 -c 'import sqlite3;print(sqlite3.connect("/app/backend/data/webui.db").execute("select name,email,role from user").fetchall())'

If your row says pending, promote it (the email is an argument, so there is no
quoting to get wrong):

    docker exec open-webui python3 -c 'import sqlite3,sys;d=sqlite3.connect("/app/backend/data/webui.db");d.execute("update user set role=? where email=?",("admin",sys.argv[1]));d.commit()' YOU@ohio.edu
    docker restart open-webui

Then mint a fresh key at Settings, Account, API keys. The old one stays invalid.
""")
        return _finish(failures)

    if r.status_code != 200:
        failures += 1
        _say(BAD, f"models endpoint returned {r.status_code}", r.text[:400])
        return _finish(failures)

    models = [m.get("id", "") for m in (r.json().get("data") or [])]
    _say(OK, f"authenticated, {len(models)} model(s) visible")

    # 4. The model this host is configured for is actually there.
    if host.model in models:
        _say(OK, f"{host.model} is available")
    else:
        near = [m for m in models if m.split(":")[0] == host.model.split(":")[0]]
        failures += 1
        _say(BAD, f"{host.model} is not in the model list", f"""
{'Closest tags: ' + ', '.join(near) if near else 'Available: ' + ', '.join(models[:12])}

Pull it on the box:
    docker exec ollama ollama pull {host.model}
""")

    # 5. A structured response round trips.
    async def probe() -> tuple[bool, str, float]:
        engine = Engine(args.host)
        start = time.time()
        try:
            out = await engine.ask(
                "You answer with a JSON object and nothing else.",
                "How many bits are in an IPv6 address? "
                "Reply as {\"answer\": <number>, \"units\": \"bits\"}.",
                _Probe,
            )
            return True, f"answer={out.answer} units={out.units}", time.time() - start
        except Exception as e:
            return False, str(e), time.time() - start
        finally:
            await engine.close()

    if host.model in models:
        good, detail, secs = asyncio.run(probe())
        if good:
            from .engine import _SCHEMA_SUPPORTED
            mode = "json_schema" if _SCHEMA_SUPPORTED else "json_object plus retry"
            _say(OK, f"structured output works via {mode} ({secs:.1f}s)", detail)
        else:
            failures += 1
            _say(BAD, f"structured output failed after {secs:.1f}s", detail)

    # 6. Concurrency, so a surprise here does not show up mid batch.
    # Report what the engine will actually do, not the box's capacity. Grading
    # runs single slot for reproducibility regardless of OLLAMA_NUM_PARALLEL.
    engine_slots = Engine(args.host).slots
    if engine_slots == 1:
        _say(OK, f"grading will use 1 slot for reproducibility "
                 f"({host.name} supports {host.slots})")
    else:
        _say(WARN, f"client set to {engine_slots} slots; scores will vary "
                   f"between runs on identical input")

    return _finish(failures)


def _finish(failures: int) -> int:
    print()
    if failures:
        print(f"{failures} check(s) failed. Fix the first one and run again.")
        return 1
    print("ready. Next:")
    print("    python -m clerk judge     <run>")
    print("    python -m clerk calibrate <run>     # fixture runs only")
    return 0
