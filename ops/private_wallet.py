"""Private desktop launcher. Never invoke the key-emitting package CLI."""
import os
import sys
import json
import time
import signal
import resource
from pathlib import Path
from datetime import datetime, timezone

def write_private(hit, target):
    """Never read the file back; exclusive creation; no secret-derived messages."""
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(hit["keypair_json"], f, separators=(",", ":"))
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
    finally:
        # Do not include hit, exceptions or private data in any status.
        pass

def main():
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    os.umask(0o077)
    root = Path("/mnt/e/solvanity")
    os.chdir(root)
    sys.path.insert(0,str(root/"optimized"))
    from solvanity_wallet.core import grind
    from solvanity_wallet.entropy import source, Sodium
    from solvanity.probability import probability
    if not isinstance(source(), Sodium):
        raise RuntimeError("Native entropy dependency unavailable")
    if sys.argv[1:] == ["--benchmark"]:
        # Public deterministic fixtures are used by separate matcher audit.
        # This bounded benchmark discards all hits and never serializes a key.
        last = {}
        def event(e):
            if e["type"] == "progress":
                last.update({k:e[k] for k in ("attempts","elapsed_seconds","keys_per_second")})
        for batch in (65536,110592,221184):
            last.clear()
            hits=grind(prefix="z"*20,ignore_case=False,backend="cuda",batch_size=batch,
                       max_attempts=60000000,on_event=event)
            del hits
            print(json.dumps(dict(type="benchmark",batch_size=batch,**last)),flush=True)
        return 0
    batch=int(sys.argv[1])
    target=root/"keys"/("kobosh-"+datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")+".json")
    if not target.parent.is_dir():
        raise RuntimeError("Private destination missing")
    last_emit=0
    def event(e):
        nonlocal last_emit
        kind=e.get("type")
        if kind=="hit":
            write_private(e,target)
            print(json.dumps({"type":"hit","address":e["address"],"path":str(target)}),flush=True)
        elif kind=="progress":
            now=time.monotonic()
            if now-last_emit>=10:
                safe={k:e[k] for k in ("attempts","elapsed_seconds","keys_per_second","found")}
                print(json.dumps({"type":"progress",**safe}),flush=True)
                last_emit=now
        elif kind=="done":
            print(json.dumps({k:e[k] for k in ("type","attempts","found","elapsed_seconds","complete")}),flush=True)
    print(json.dumps({"type":"started","pid":os.getpid(),"prefix":"kobosh","ignore_case":True,
                      "batch_size":batch,"destination":str(target),
                      "probability":probability("kobosh","",True)}),flush=True)
    results=grind(prefix="kobosh",ignore_case=True,backend="cuda",batch_size=batch,count=1,on_event=event)
    success=len(results)==1
    for hit in results:
        hit.clear()
    results.clear()
    return 0 if success else 1

if __name__=="__main__":
    try:
        code=main()
    except KeyboardInterrupt:
        print('{"type":"stopped"}',flush=True)
        code=130
    except BaseException:
        # Never stringify exceptions/tracebacks from secret-bearing code.
        print('{"type":"failed","message":"Private search stopped; no diagnostic contents exported"}',flush=True)
        code=2
    sys.exit(code)
