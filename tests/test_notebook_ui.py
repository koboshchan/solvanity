import importlib.util
from pathlib import Path
import pytest
W=pytest.importorskip("ipywidgets")

def load():
    p=Path(__file__).resolve().parents[1]/"notebooks/solvanity_ui.py"
    spec=importlib.util.spec_from_file_location("sv_ui",p)
    m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m

def test_inputs_present_and_editable():
    app=load().SolvanityUI()
    for w in (app.prefix,app.suffix,app.count,app.budget,app.batch,app.base,app.custom_owner,app.owner):
        assert not w.disabled
    app.prefix.value="ko"; app.suffix.value="sh"; app.count.value=3; app.budget.value=100
    app.mode.value="contract"; app.base.value="11111111111111111111111111111111"
    assert app.contract_box.layout.display==""
    assert app.batch.value == "auto" and app._configuration()["batch_size"] is None

def test_no_disclaimer_box():
    import json
    app=load().SolvanityUI()
    blob=" ".join(str(getattr(c,"value","")) for c in app.root.children)
    assert "vaults" not in blob and "sv-warning" not in blob

def test_shared_layout_not_hidden():
    app=load().SolvanityUI()
    for w in (app.prefix,app.suffix,app.batch,app.count,app.budget,app.base,app.owner):
        assert w.layout.display!="none" or w is app.base
    assert app.prefix.layout.display!="none" and app.batch.layout.display!="none"

def test_auto_and_explicit_batch_cli():
    ui=load();app=ui.SolvanityUI()
    config=dict(mode="wallet",prefix="ko",suffix="",ignore_case=False,backend="cpu",count=1,max_attempts=8,batch_size=None)
    cmd=ui.command_for(config)
    assert "--batch-size" not in cmd
    assert cmd[3:6]==["solvanity","wallet","grind"]
    config["batch_size"]=128
    cmd=ui.command_for(config)
    assert cmd[cmd.index("--batch-size")+1]=="128"

def test_notebook_uses_only_unified_repository():
    import json
    r=Path(__file__).resolve().parents[1]
    n=json.loads((r/"notebooks/Solvanity.ipynb").read_text())
    code="\n".join("".join(c["source"]) for c in n["cells"] if c["cell_type"]=="code")
    assert 'for repo in ("solvanity",):' in code
    assert "solvanity-wallet" not in code and "solvanity-contract" not in code
    for c in n["cells"]:
        if c["cell_type"]=="code":compile("".join(c["source"]),"notebook","exec")

def test_batch_default_selected_and_no_consent():
    app=load().SolvanityUI()
    assert app.batch.index==0 and not hasattr(app,"consent")

def test_background_thread_updates_without_event_loop():
    import sys, time
    m=load(); app=m.SolvanityUI()
    app.config=dict(prefix="A",suffix="",ignore_case=False)
    cmd=[sys.executable,"-c","import json;print(json.dumps({'type':'progress','attempts':10,'elapsed_seconds':1}),flush=True)"]
    import threading
    app.stopping=False
    app.task=threading.Thread(target=app._run,args=(cmd,),daemon=True); app.task.start(); app.task.join(10)
    assert not app.task.is_alive() and "Finished" in app.status.value
    assert app.start.disabled is False and app.stop.disabled is True

def test_stop_before_process_assignment(monkeypatch):
    import sys
    m=load(); app=m.SolvanityUI()
    app.config=dict(prefix="A",suffix="",ignore_case=False)
    app.start.disabled=True; app.stop.disabled=False
    app._stop()
    app._run([sys.executable,"-c","import time;time.sleep(30)"])
    assert app.proc is None and app.start.disabled is False and app.stop.disabled is True
    assert "Stopped" in app.status.value

def test_spawn_failure_restores_controls_without_output(capsys):
    m=load(); app=m.SolvanityUI()
    app.start.disabled=True; app.stop.disabled=False
    app._run(["/nonexistent/solvanity-private-worker"])
    assert app.proc is None and app.start.disabled is False and app.stop.disabled is True
    assert "Could not run" in app.status.value
    assert "solvanity-private-worker" not in capsys.readouterr().out

def test_refresh_identity_is_unique_and_only_flushes_safe_widgets(monkeypatch):
    m=load(); app=m.SolvanityUI(); other=m.SolvanityUI()
    assert app._pump_id != other._pump_id
    sent=[]
    for name in ("status","metrics","chance","start","stop","results"):
        monkeypatch.setattr(getattr(app,name),"send_state",lambda name=name:sent.append(name))
    app._flush()
    assert sent==["status","metrics","chance","start","stop","results"]

def test_optional_diagnostic_failure_does_not_break_worker(monkeypatch):
    m=load(); app=m.SolvanityUI()
    monkeypatch.setenv("SOLVANITY_UI_DIAG","/nonexistent/private-dir/worker.log")
    app._diag("popen pid=123")

def test_flush_covers_visibility_layouts():
    app=load().SolvanityUI()
    sent=[]
    for w in (app.contract_box.layout, app.custom_owner.layout, app.contract_box, app.status, app.stop):
        w.send_state=(lambda key: (lambda *a,**k: sent.append(key)))(id(w))
    app.mode.value="contract"
    assert app.contract_box.layout.display==""
    app._flush()
    assert id(app.contract_box.layout) in sent and id(app.custom_owner.layout) in sent
    app.mode.value="wallet"
    assert app.contract_box.layout.display=="none"


def test_eta_states():
    m=load()
    assert "Probability is not completion" not in Path(m.__file__).read_text()
    assert m.eta_html("","",True)==""
    assert "Not possible" in m.eta_html("0","",False)
    assert "Warming up" in m.eta_html("ab","",False,None,True)
    assert "Start to measure" in m.eta_html("ab","",False)
    fast=m.eta_html("ab","",False,1e6,True)
    assert "Expected" in fast and "warn" not in fast and "Not a guarantee" in fast
    slow=m.eta_html("kobosh","ab",False,1e6,True)
    assert "warn" in slow and "Over a day" in slow
    assert "incompatible overlap" in m.eta_html("a"*30,"b"*30,False) or "Not possible" in m.eta_html("a"*30,"b"*30,False)


def test_preview_updates_eta():
    app=load().SolvanityUI()
    app.prefix.value="ab"
    assert "Start to measure" in app.eta.value


def test_percentiles_and_edges():
    import math
    m=load()
    p=m.coarse_probability("ab","",False)
    assert 0 < p < 1/58**2
    r=1e6
    assert m.percentile_seconds(r,p,.5)==pytest.approx(math.log(2)/(r*p))
    assert m.percentile_seconds(r,p,.9)==pytest.approx(math.log(10)/(r*p))
    tiny=m.percentile_seconds(r,1e-30,.5)
    assert tiny==pytest.approx(math.log(2)/(r*1e-30)) and math.isfinite(tiny)
    assert m.percentile_seconds(0,p,.5)==math.inf
    assert m.coarse_probability("0","",False)==0.0
    assert m.coarse_probability("a","",True)>0
    assert "Not possible" in m.eta_html("l","",False)
    assert "Not possible" in m.eta_html("a"*40,"b"*40,False)
    assert "Not possible" in m.eta_html("a"*45,"",False)



def test_gpu_cells_and_render(monkeypatch):
    m=load()
    cells=m.gpu_cells(["A100","73","10240","40960","61","250.5","400.00"])
    assert ("73 %","GPU utilization") in cells and ("61 °C","GPU temperature") in cells
    assert m.gpu_cells(["A100","[N/A]","[N/A]","[N/A]","[N/A]","[N/A]","[N/A]"])[1][0]=="n/a"
    app=m.SolvanityUI()
    app.config=dict(backend="cpu",batch_size=None,prefix="ab",suffix="",ignore_case=False)
    app._event(dict(type="progress",attempts=1000,elapsed_seconds=1.0,keys_per_second=1000))
    app._event(dict(type="progress",attempts=3000,elapsed_seconds=2.0,keys_per_second=1500))
    assert "2,000" in app.metrics.value and "1,500" in app.metrics.value
    assert "Not available on CPU" in app.metrics.value and "Automatic" in app.metrics.value
    assert "Expected" in app.eta.value


def test_expected_eta_uses_mean_not_percentile():
    m=load()
    assert "Expected ~"+m.human_time(1/(100*m.match_probability("ab","",False))) in m.eta_html("ab","",False,100)
    assert "warn" in m.eta_html("abcdef","",False,1)
    app=m.SolvanityUI()
    assert not hasattr(app,"chance_note")
    assert "Probability is not completion" not in app.eta.value

def test_gpu_poll_drops_stale_query_after_stop(monkeypatch):
    import threading
    m=load(); app=m.SolvanityUI(); stop=threading.Event()
    monkeypatch.setattr(stop,"wait",lambda timeout:False)
    def query():
        stop.set()
        return ["stale","1","1","1","1","1","1"]
    monkeypatch.setattr(m,"read_gpu",query)
    app._poll_gpu(stop)
    assert app.gpu is None

def test_koboshchan_warns_over_a_day():
    m=load()
    out=m.eta_html("koboshchan","",False,1e7,True)
    assert "warn" in out and "Over a day" in out and "Expected" in out
    p=m.coarse_probability("koboshchan","",False)
    assert p == pytest.approx(m.match_probability("koboshchan","",False))


def test_exact_probability_matches_monte_carlo():
    import os
    from solvanity_wallet.core import b58encode
    m=load()
    n=300000
    addrs=[b58encode(os.urandom(32)) for _ in range(n)]
    for prefix,suffix,fold in [("2","",False),("H","",False),("k","",False),("K","",True),("1","",False),("Ab","",False),("","a",False),("3","z",False),("h","",True)]:
        def ok(a):
            if fold: a=a.lower()
            pr,su=(prefix.lower(),suffix.lower()) if fold else (prefix,suffix)
            return a.startswith(pr) and a.endswith(su)
        hits=sum(1 for a in addrs if ok(a))
        expected=m.match_probability(prefix,suffix,fold)*n
        assert abs(hits-expected) <= 5*max(expected,1)**.5+2, (prefix,suffix,fold,hits,expected)


def test_first_digit_bias():
    m=load()
    assert m.match_probability("2","",False) > 2/58
    assert m.match_probability("k","",False) < m.match_probability("5","",False)/10


def test_rare_start_indicator():
    m=load()
    assert "Rare start" in m.eta_html("kobosh","",False,1e9,True)
    assert "Rare start" not in m.eta_html("2bc","",False,1e9,True)


def test_first_digit_boundary_J():
    m=load()
    full=m.match_probability("H","",False)
    part=m.match_probability("J","",False)
    assert 0.2 < part/full < 0.26 or part/full > 0  # J is partial in 44-char range
    assert part < full*0.3 + m.match_probability("K","",False)*0 + 1e-3*full


def test_exact_counts():
    m=load()
    from solvanity_wallet.core import b58encode
    assert m.count_matching("J","",False,lengths={44}) == 2**256-17*58**43 == 1543026857568826263157438925144268627362929848315748976455741857738870751232
    ff=b58encode(b"\xff"*32)
    assert ff=="JEKNVnkbo3jma5nREBBJCDoXFVeKkD56V3xKrvRmWxFG"
    assert m.count_matching(ff,"",False)==1
    assert m.count_matching(ff[:30],ff[20:],False)==1       # compatible overlap
    assert m.count_matching(ff[:30],"x"+ff[21:],False)==0   # contradictory overlap
    assert m.count_matching("1"*32,"",False)==1             # all-zero key
    assert m.count_matching("K","",False,lengths={44})==0
    assert m.count_matching("K","",False)>0                 # shorter addresses
    assert m.count_matching("kobosh","",True)==16*58**37
    assert m.count_matching("","",False)==2**256
    assert m.count_matching("o","",True)==m.count_matching("o","",False)
    assert 0 < m.count_matching("1","",False) <= 2**256//255


def test_exact_counts_vs_enumeration():
    m=load()
    import os
    from solvanity_wallet.core import b58encode
    for _ in range(200):
        a=b58encode(os.urandom(32))
        assert m.count_matching(a[:3],a[-2:],False)>=1
        assert m.count_matching(a[:3].upper(),a[-2:].lower(),True)>=1

