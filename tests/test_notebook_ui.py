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
