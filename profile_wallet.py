"""Measurement-only wallet profile. Never logs seeds, public keys or hit records."""
import json, os, platform, statistics, subprocess, sys, time
from pathlib import Path
import numpy as np
import cupy as cp
from solvanity_wallet.cuda_backend import CUDABackend
from solvanity_wallet.core import grind, verify_hit

OUT=Path("/content/solvanity-profile")
OUT.mkdir(exist_ok=True)
REPORT={"source_sha": subprocess.check_output(["git","rev-parse","HEAD"],cwd="/content/solvanity-profile/source",text=True).strip(),
        "python":platform.python_version(),"cupy":cp.__version__,
        "method":"Wall-time staged clone of scan, CUDA events for kernel. Synchronization wall time overlaps kernel execution and must not be added to event time. Actual grind runs are uninstrumented except aggregate callbacks; no secrets logged.",
        "gpu":subprocess.check_output(["nvidia-smi","--query-gpu=name,uuid,driver_version,memory.total","--format=csv,noheader"],text=True).strip(),
        "device_attributes":cp.cuda.Device().attributes}
def save():
    (OUT/"profile.json").write_text(json.dumps(REPORT,indent=2))
def util_run(name, fn):
    raw=OUT/(name+"-smi.csv")
    with raw.open("w") as f:
        proc=subprocess.Popen(["nvidia-smi","--query-gpu=timestamp,utilization.gpu,utilization.memory,memory.used,power.draw","--format=csv,noheader,nounits","--loop-ms=200"],stdout=f,stderr=subprocess.PIPE)
        try:
            t=time.perf_counter(); result=fn(); wall=time.perf_counter()-t
        finally:
            proc.terminate(); proc.wait(timeout=10)
    samples=[]
    for line in raw.read_text().splitlines():
        fields=line.split(",")
        try: samples.append(float(fields[1]))
        except (IndexError,ValueError): pass
    return dict(result=result,wall_seconds=wall,util_samples=len(samples),
                util_median=statistics.median(samples) if samples else None,
                util_peak=max(samples) if samples else None,util_raw=raw.name)

engine=CUDABackend()
# Compile and warm memory/event/fill paths outside measured runs.
engine.scan(os.urandom(32*4096),"abcdef","",False)
engine.scan(os.urandom(32*4096),"","abcdef",False)
REPORT["kernel_attributes"]=engine.kernel.attributes
# Actual public API validates every returned hit on CPU; no hit values are retained.
match_events=[]
def match_event(e):
    if e["type"] in ("done","progress"):
        match_events.append({k:e[k] for k in ("type","attempts","found") if k in e})
hits=grind(backend="cuda",batch_size=4096,count=4096,max_attempts=4096,on_event=match_event)
assert len(hits)==4096
del hits
REPORT["all_hit_cpu_verification"]={"count":4096,"events":match_events}
save()

def actual(batch,pre,suf,limit=80000000):
    events=[]; stages=[]
    def event(e):
        if e["type"] in ("start","tuning"): stages.append(e)
        if e["type"]=="done": events.append(e)
    t=time.perf_counter()
    hits=grind(backend="cuda",prefix=pre,suffix=suf,batch_size=batch,max_attempts=limit,on_event=event)
    wall=time.perf_counter()-t
    # Any rare match has already been CPU verified. Do not serialize private results.
    count=len(hits); del hits
    assert events and events[-1]["attempts"]==limit
    return {"attempts":limit,"wall_seconds":wall,"keys_per_second":limit/wall,"hits_verified":count,"events":stages}
REPORT["actual_auto"]=util_run("auto-prefix",lambda:actual(None,"abcdef",""))
save()
tuning=[e for e in REPORT["actual_auto"]["result"]["events"] if e["type"]=="tuning"]
assert tuning and tuning[-1]["calibration_complete"]
batch=tuning[-1]["batch_size"]; block=tuning[-1]["block_size"]
REPORT["selected"]={"batch_size":batch,"block_size":block}
# Explicit batch uses public API's default block128, so label accordingly.
REPORT["actual_fixed65536"]=util_run("fixed65536-prefix",lambda:actual(65536,"abcdef",""))
save()
REPORT["actual_auto_suffix"]=util_run("auto-suffix",lambda:actual(None,"","abcdef"))
save()

def staged(n,block,pre,suf,repeats=128):
    rows=[]; engine.block_size=block
    for _ in range(repeats):
        row={}; whole=time.perf_counter()
        t=time.perf_counter(); seeds=os.urandom(32*n); row["host_csprng_s"]=time.perf_counter()-t
        t=time.perf_counter()
        src=cp.asarray(np.frombuffer(seeds,dtype=np.uint8))
        pre_d=cp.asarray(np.frombuffer(pre.encode("ascii"),dtype=np.uint8))
        suf_d=cp.asarray(np.frombuffer(suf.encode("ascii"),dtype=np.uint8))
        found=cp.zeros(1,dtype=cp.uint32)
        indices=cp.empty(n,dtype=cp.uint32); pubs=cp.empty((n,32),dtype=cp.uint8)
        row["allocation_h2d_enqueue_s"]=time.perf_counter()-t
        start,end=cp.cuda.Event(),cp.cuda.Event()
        try:
            start.record()
            t=time.perf_counter()
            engine.kernel(((n+block-1)//block,),(block,),
                (src,np.uint64(n),pre_d,np.int32(len(pre)),suf_d,np.int32(len(suf)),
                 np.int32(False),found,np.uint32(n),indices,pubs))
            end.record()
            row["kernel_enqueue_s"]=time.perf_counter()-t
            t=time.perf_counter(); end.synchronize(); row["kernel_sync_wait_s"]=time.perf_counter()-t
            row["kernel_gpu_s"]=cp.cuda.get_elapsed_time(start,end)/1000
            t=time.perf_counter(); k=int(found.get()[0]); row["match_count_d2h_s"]=time.perf_counter()-t
            assert k<=n
            t=time.perf_counter(); ids,keys=indices[:k].get(),pubs[:k].get()
            row["match_payload_d2h_s"]=time.perf_counter()-t
            t=time.perf_counter()
            for i,p in zip(ids,keys):
                hit=verify_hit(seeds[int(i)*32:(int(i)+1)*32],bytes(p),pre,suf,False)
                del hit
            row["cpu_verify_s"]=time.perf_counter()-t
            row["matches"]=k
        finally:
            t=time.perf_counter(); src.fill(0); pubs.fill(0); row["wipe_enqueue_s"]=time.perf_counter()-t
            t=time.perf_counter(); cp.cuda.get_current_stream().synchronize()
            row["wipe_sync_s"]=time.perf_counter()-t
        row["whole_batch_s"]=time.perf_counter()-whole
        rows.append(row)
        del seeds,src,pubs,indices,found,pre_d,suf_d,ids,keys
    totals={key:sum(r[key] for r in rows) for key in rows[0]}
    return {"batch_size":n,"block_size":block,"repeats":repeats,"totals":totals,
            "keys_per_second":n*repeats/totals["whole_batch_s"],
            "kernel_only_keys_per_second":n*repeats/totals["kernel_gpu_s"],
            "rows":rows}

REPORT["staged_selected"]=util_run("staged-selected",lambda:staged(batch,block,"abcdef","",512))
save()
REPORT["staged_fixed65536"]=util_run("staged-fixed65536",lambda:staged(65536,128,"abcdef","",512))
save()
REPORT["staged_large"]=util_run("staged-large",lambda:staged(1048576,64,"abcdef","",64))
save()
engine.close()
REPORT["complete"]=True
save()
print("PROFILE_COMPLETE",json.dumps({k:REPORT[k] for k in ("source_sha","selected","complete")}))
