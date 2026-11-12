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
    assert app.batch.value is None

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
