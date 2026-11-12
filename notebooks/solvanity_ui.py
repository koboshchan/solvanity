"""Shared Solvanity notebook interface. Never prints worker output or secret events."""
from __future__ import annotations
import threading
import uuid
import weakref
import html
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import ipywidgets as W
from IPython.display import display, Javascript

ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"

CSS = """<style>
.sv{--bg:#fff;--fg:#1d1d1f;--mut:#6e6e73;--card:#f5f5f7;--line:#d2d2d7;--acc:#0071e3;
 font-family:-apple-system,BlinkMacSystemFont,"SF Pro Text","Segoe UI",system-ui,sans-serif;
 background:var(--bg);color:var(--fg);padding:28px;border:1px solid var(--line);border-radius:20px;max-width:760px;box-sizing:border-box}
@media(prefers-color-scheme:dark){.sv{--bg:#1c1c1e;--fg:#f5f5f7;--mut:#98989d;--card:#2c2c2e;--line:#3a3a3c;--acc:#0a84ff}}
.sv .widget-label,.sv label{color:var(--mut)!important;font-family:inherit!important}
.sv input[type=text],.sv input[type=number],.sv select,.sv textarea{background:var(--card)!important;color:var(--fg)!important;
 border:1px solid var(--line)!important;border-radius:10px!important;min-height:36px!important;padding:0 12px!important;font-family:inherit!important;box-sizing:border-box!important;opacity:1!important}
.sv input:focus,.sv select:focus{outline:2px solid var(--acc)!important;border-color:var(--acc)!important}
.sv .widget-text,.sv .widget-dropdown,.sv .widget-bounded-int-text{min-height:40px;margin:4px 0}
.sv .widget-toggle-buttons button{background:var(--card)!important;color:var(--fg)!important;border:0!important;font-family:inherit!important}
.sv .widget-toggle-buttons button.mod-active{background:var(--acc)!important;color:#fff!important}
.sv button{border-radius:10px!important;font-family:inherit!important;font-weight:600}
.sv-title{font:700 32px/1.1 -apple-system,BlinkMacSystemFont,system-ui,sans-serif;letter-spacing:-.5px;margin:0 0 4px}
.sv-note{color:var(--mut);font:13px/1.5 inherit;margin:6px 0}
.sv-metrics{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px 24px;background:var(--card);border-radius:14px;padding:16px 18px;margin:10px 0}
.sv-number{font:600 17px/1.25 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-variant-numeric:tabular-nums;color:var(--fg);overflow-wrap:anywhere}.sv-caption{font:12px/1.4 inherit;color:var(--mut);margin-top:2px}
.sv-result{background:var(--card);border-radius:14px;padding:14px 16px;overflow-wrap:anywhere;margin-top:12px}
.sv-address{font:15px ui-monospace,SFMono-Regular,Menlo,monospace}
.sv-eta{background:var(--card);border-radius:14px;padding:14px 16px;margin:10px 0}.sv-eta-big{font:700 28px/1.2 inherit;letter-spacing:-.3px}.sv-eta-sub{font:13px/1.5 inherit;color:var(--mut);margin-top:2px}.sv-eta.warn{border:1px solid #ff9f0a}.sv-eta.warn .sv-eta-big{color:#ff9f0a}.sv-eta.bad .sv-eta-big{color:#ff453a}
.sv-status{font-size:14px;padding:10px 0;color:var(--mut)}
</style>"""

def coarse_probability(prefix, suffix, ignore_case):
    """Uniform-digit heuristic only. Prefix digit bias/overlap are not modeled."""
    probability = 1.0
    for char in prefix + suffix:
        variants = sum((c.lower() == char.lower()) if ignore_case else (c == char)
                       for c in ALPHABET)
        if not variants:
            return 0.0
        probability *= variants / 58
    return probability

def pattern_error(prefix, suffix, ignore_case):
    """Reuse the engine's own validation (base58 case-fold, overlap)."""
    try:
        from solvanity_wallet.core import validate_pattern
        validate_pattern(prefix, suffix, ignore_case)
    except ImportError:
        for c in prefix + suffix:
            if not any((o in ALPHABET) for o in ((c.lower(), c.upper()) if ignore_case else (c,))):
                return f"{c!r} cannot occur in base58 under this case mode"
    except ValueError as exc:
        return str(exc)
    return None

def eta_html(prefix, suffix, ignore_case, rate=None, running=False):
    """Expected time = 1 / (measured keys per second * match probability)."""
    if not (prefix or suffix):
        return ""
    error = pattern_error(prefix, suffix, ignore_case)
    if error:
        return '<div class="sv-eta bad" role="alert"><div class="sv-eta-big">Not possible</div><div class="sv-eta-sub">'+html.escape(error)+'</div></div>'
    probability = coarse_probability(prefix, suffix, ignore_case)
    odds = f"1 in {1/probability:,.0f}" if probability else "no match possible"
    if not rate or rate <= 0:
        big = "Warming up" if running else "Start to measure speed"
        return '<div class="sv-eta"><div class="sv-eta-big">'+big+'</div><div class="sv-eta-sub">Approx. odds '+odds+'. Estimate appears once speed is measured.</div></div>'
    seconds = 1/(rate*probability)
    cls = " warn" if seconds > 86400 else ""
    sub = f"Estimated average at {rate:,.0f} keys/s, approx. odds {odds}. Not a guarantee."
    if seconds > 86400:
        sub = "Over a day on average. Try a shorter pattern or Any caps. "+sub
    return '<div class="sv-eta'+cls+'"><div class="sv-eta-big">Expected ~'+human_time(seconds)+' (est.)</div><div class="sv-eta-sub">'+html.escape(sub)+'</div></div>'

def percentile_seconds(rate, probability, q):
    """Time by which a hit has probability q: -log1p(-q)/(rate*p). Stable for tiny p."""
    lam = rate*probability
    return -math.log1p(-q)/lam if lam > 0 else math.inf

GPU_FIELDS = "name,utilization.gpu,memory.used,memory.total,temperature.gpu,power.draw,power.limit"

def read_gpu():
    """One bounded nvidia-smi query. None when unavailable."""
    try:
        proc = subprocess.run(["nvidia-smi", "--query-gpu="+GPU_FIELDS, "--format=csv,noheader,nounits"],
                              capture_output=True, text=True, timeout=2)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0 or not proc.stdout.strip():
        return None
    parts = [x.strip() for x in proc.stdout.strip().splitlines()[0].split(",")]
    return parts if len(parts) == 7 else None

def gpu_cells(parts):
    na = lambda v: v if v and "N/A" not in v else None
    name, util, used, total, temp, power, limit = parts
    cells = [(na(name) or "GPU", "GPU")]
    cells.append((f"{util} %" if na(util) else "n/a", "GPU utilization"))
    cells.append((f"{float(used)/1024:.1f} / {float(total)/1024:.1f} GiB" if na(used) and na(total) else "n/a", "GPU memory"))
    cells.append((f"{temp} °C" if na(temp) else "n/a", "GPU temperature"))
    cells.append((f"{float(power):.0f} / {float(limit):.0f} W" if na(power) and na(limit) else "n/a", "GPU power"))
    return cells

def human_time(seconds):
    if not math.isfinite(seconds):
        return "unknown"
    if seconds < 60:
        return f"{seconds:.1f}s"
    if seconds < 3600:
        return f"{seconds/60:.1f} min"
    if seconds < 86400:
        return f"{seconds/3600:.1f} hours"
    return f"{seconds/86400:.1f} days"

def command_for(config, python=sys.executable):
    """CLI flags verified against the actual wallet and contract source."""
    mode = config["mode"]
    if mode not in ("wallet", "contract"):
        raise ValueError("Select wallet or contract")
    from solvanity_contract.core import Pattern, pubkey, validate_owner
    Pattern(config["prefix"], config["suffix"], config["ignore_case"])
    cmd = [python, "-u", "-m", "solvanity", mode, "grind", "--json",
           "--prefix", config["prefix"], "--suffix", config["suffix"],
           "--backend", config["backend"],
           "--count", str(config["count"])]
    if config.get("batch_size") is not None:
        cmd += ["--batch-size", str(config["batch_size"])]
    if config["ignore_case"]:
        cmd.append("--ignore-case")
    if config.get("max_attempts"):
        cmd += ["--max-attempts", str(config["max_attempts"])]
    if mode == "contract":
        base = str(pubkey(config["base"]))
        validate_owner(pubkey(config["owner"]))
        cmd += ["--base", base, "--owner", config["owner"]]
    return cmd

def gpu_info():
    try:
        proc = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total,driver_version",
                               "--format=csv,noheader"], capture_output=True, text=True, timeout=5)
        return proc.stdout.strip() if proc.returncode == 0 else "No NVIDIA GPU detected. CPU remains available."
    except (OSError, subprocess.TimeoutExpired):
        return "No NVIDIA GPU detected. CPU remains available."

class SolvanityUI:
    def __init__(self):
        self._pump_id = "solvanity_" + uuid.uuid4().hex
        self._closed = False
        self.proc = None
        self.task = None
        self.hits = []
        self.cards = []
        self.stopping = False
        self.config = None
        wide = lambda: W.Layout(width="100%")
        style = {"description_width": "100px"}
        self.mode = W.ToggleButtons(options=[("Wallet keypair", "wallet"), ("Seeded account", "contract")])
        self.prefix = W.Text(description="Prefix", placeholder="kobosh", style=style, layout=wide())
        self.suffix = W.Text(description="Suffix", placeholder="Optional", style=style, layout=wide())
        self.case = W.ToggleButtons(options=[("Exact caps", False), ("Any caps", True)], value=True)
        self.base = W.Text(description="Base public key", placeholder="Public signer address only, never a private key", style=style, layout=wide())
        self.owner = W.Dropdown(description="Owner program", options=[("SPL Token", "token"), ("Token 2022", "token2022"), ("Custom program", "custom")], style=style, layout=wide())
        self.custom_owner = W.Text(description="Program key", style=style, layout=wide())
        self.contract_box = W.VBox([self.base, self.owner, self.custom_owner,
            W.HTML('<p class="sv-note">A create_with_seed account is not an importable wallet or a PDA. The base signer is still needed to create it. No transaction is sent.</p>')])
        self.backend = W.Dropdown(description="Compute", options=[("NVIDIA CUDA", "cuda"), ("CPU reference", "cpu")], style=style, layout=wide())
        self.batch = W.Dropdown(description="Batch size", options=[("Automatic","auto"),("4,096",4096),("16,384",16384),("65,536",65536),("262,144",262144)], value="auto", style=style, layout=wide())
        self.count = W.BoundedIntText(description="Results", min=1, max=100, value=1, style=style, layout=wide())
        self.budget = W.BoundedIntText(description="Attempt limit", min=0, max=2**53-1, value=0, style=style, layout=wide())
        self.start = W.Button(description="Start search", icon="play", style={"button_color":"#0071e3","text_color":"#ffffff"}, layout=W.Layout(width="180px",height="42px"))
        self.stop = W.Button(description="Stop", icon="stop", disabled=True, layout=W.Layout(width="100px",height="42px"))
        self.clear = W.Button(description="Forget results", icon="trash", layout=W.Layout(width="160px",height="42px"))
        self.status = W.HTML('<div class="sv-status" role="status">Ready. Choose a pattern, then start.</div>')
        self.metrics = W.HTML()
        self.chance = W.FloatProgress(min=0,max=1,value=0,description="P(≥1 hit)", style={"description_width":"100px","bar_color":"#0071e3"}, layout=wide())
        self.eta = W.HTML()
        self.results = W.VBox()
        self.snap = {}
        self.gpu = None
        self.gpu_stop = threading.Event()
        self.transfer_output = W.Output()
        controls = W.Box([W.VBox([self.prefix,self.suffix,self.case],layout=W.Layout(flex="1 1 300px",min_width="260px")),
                          W.VBox([self.backend,self.batch,self.count,self.budget],layout=W.Layout(flex="1 1 300px",min_width="260px"))],
                         layout=W.Layout(display="flex",flex_flow="row wrap",grid_gap="24px"))
        self.root = W.VBox([
            W.HTML(CSS+'<p class="sv-title">Solvanity</p><p class="sv-note">Find a custom Solana address.</p>'),
            W.HTML('<p class="sv-note">'+html.escape(gpu_info())+'</p>'),
            self.mode, controls, self.contract_box,
            W.HBox([self.start,self.stop,self.clear]),self.status,self.metrics,
            self.eta,self.chance,self.results,self.transfer_output
        ],layout=W.Layout(width="100%"))
        self.root.add_class("sv")
        self.mode.observe(self._visibility,names="value")
        self.owner.observe(self._visibility,names="value")
        for w in (self.prefix,self.suffix,self.case):
            w.observe(self._preview,names="value")
        self.start.on_click(self._start)
        self.stop.on_click(self._stop)
        self.clear.on_click(self._clear)
        self._visibility()

    def display(self):
        display(self.root)
        self._start_pump()
        return self

    def _flush(self):
        """Push current widget state to the browser (Colab drops background-thread updates)."""
        for w in (self.status, self.metrics, self.chance, self.start, self.stop, self.results,
                  self.eta, self.contract_box, self.contract_box.layout, self.custom_owner, self.custom_owner.layout,
                  self.mode, self.owner, self.case, self.batch, self.backend):
            try:
                w.send_state()
            except Exception:
                pass

    def _start_pump(self):
        # Known Colab bug (googlecolab/colabtools#3373): widget changes made from a
        # background thread only reach the browser when a frontend->kernel round trip
        # happens. A browser-side timer calling a registered callback provides it.
        try:
            from google.colab import output
        except ImportError:
            return
        reference = weakref.ref(self)
        def refresh():
            app = reference()
            if app is None or app._closed:
                return False
            app._flush()
            return True
        output.register_callback(self._pump_id, refresh)
        name = json.dumps(self._pump_id)
        display(Javascript("""(() => {
          const name = """ + name + """;
          const registry = window[Symbol.for('solvanity.refreshTimers')] ||= new Map();
          if (registry.has(name)) registry.get(name)();
          let busy = false;
          const cleanup = () => {
            clearInterval(timer); registry.delete(name);
            window.removeEventListener('pagehide', cleanup);
          };
          const timer = setInterval(async () => {
            if (busy) return;
            busy = true;
            try {
              const result = await google.colab.kernel.invokeFunction(name, [], {});
              if (result?.data?.['application/json'] === false) cleanup();
            } catch (e) { cleanup(); }
            finally { busy = false; }
          }, 500);
          registry.set(name, cleanup);
          window.addEventListener('pagehide', cleanup, {once:true});
        })();"""))

    def close(self):
        self._closed = True
        self.gpu_stop.set()
        self._stop()
        name = json.dumps(self._pump_id)
        display(Javascript("window[Symbol.for('solvanity.refreshTimers')]?.get(" + name + ")?.();"))
        self.root.close()


    def _render(self):
        snap = self.snap
        if not snap:
            self.metrics.value = ""
            return
        batch = snap.get("batch_size") or (self.config or {}).get("batch_size")
        cells = [(f"{snap['current']:,.0f}", "keys / second now"), (f"{snap['rate']:,.0f}", "keys / second average"),
                 (f"{snap['attempts']:,}", "attempts"), (human_time(snap["elapsed"]), "elapsed"),
                 (human_time(snap["expected"]), "expected time (est.)"), (human_time(snap["p50"]), "50% chance by (est.)"), (human_time(snap["p90"]), "90% chance by (est.)"),
                 (f"{batch:,}" if isinstance(batch, int) else "Automatic", "batch size"), (str(len(self.hits)), "results found")]
        if (self.config or {}).get("backend") == "cuda":
            cells += gpu_cells(self.gpu) if self.gpu else [("Not available", "GPU telemetry")]
        else:
            cells.append(("Not available on CPU", "GPU telemetry"))
        self.metrics.value = '<div class="sv-metrics">'+"".join('<div><div class="sv-number">'+html.escape(a)+'</div><div class="sv-caption">'+html.escape(b)+'</div></div>' for a,b in cells)+'</div>'

    def _poll_gpu(self, stop):
        while not stop.wait(1.0):
            reading = read_gpu()
            if stop.is_set():
                return
            self.gpu = reading
            self._render()

    def _preview(self, *_):
        if self.task and self.task.is_alive():
            return
        self.eta.value = eta_html(self.prefix.value, self.suffix.value, self.case.value)

    def _visibility(self, *_):
        self.contract_box.layout.display = "" if self.mode.value == "contract" else "none"
        self.custom_owner.layout.display = "" if self.owner.value == "custom" else "none"

    def _status(self, text):
        self.status.value = '<div class="sv-status" role="status">'+html.escape(text)+'</div>'

    def _configuration(self):
        return dict(mode=self.mode.value,prefix=self.prefix.value,suffix=self.suffix.value,
                    ignore_case=self.case.value,backend=self.backend.value,batch_size=None if self.batch.value=="auto" else self.batch.value,
                    count=self.count.value,max_attempts=self.budget.value,
                    base=self.base.value.strip(),owner=self.custom_owner.value.strip() if self.owner.value=="custom" else self.owner.value)

    def _start(self, *_):
        if self.task and self.task.is_alive():
            return
        try:
            config = self._configuration()
            command = command_for(config)
        except (ValueError, ImportError) as exc:
            self._status(str(exc))
            return
        self._clear()
        self.config = config
        self.stopping = False
        self.start.disabled = True
        self.stop.disabled = False
        self.eta.value = eta_html(config["prefix"],config["suffix"],config["ignore_case"],None,True)
        self._status("Starting verified engine. CUDA compilation can take a moment.")
        self.snap = {}
        self.gpu = None
        self.batch_seen = None
        self.gpu_stop = threading.Event()
        if config["backend"] == "cuda":
            threading.Thread(target=self._poll_gpu, args=(self.gpu_stop,), daemon=True).start()
        self.task = threading.Thread(target=self._run, args=(command,), daemon=True)
        self.task.start()

    def _diag(self, text):
        path = os.environ.get("SOLVANITY_UI_DIAG")
        if path:
            try:
                with open(path, "a", opener=lambda p, flags: os.open(p, flags, 0o600)) as stream:
                    stream.write(f"{time.time():.3f} {text}\n")
            except OSError:
                pass  # Optional diagnostics must never interrupt a search.

    def _run(self, command):
        # Thread + Popen: asyncio tasks on an idle Colab kernel are not scheduled
        # until another cell runs, so the UI never updated by itself.
        try:
            with tempfile.TemporaryFile(mode="w+b") as stderr:
                # Never inherit stdout: wallet JSON events contain secret key material.
                self.proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=stderr)
                self._diag(f"popen pid={self.proc.pid}")
                if self.stopping:
                    self.proc.terminate()
                for raw in self.proc.stdout:
                    try:
                        event = json.loads(raw)
                    except (json.JSONDecodeError, UnicodeDecodeError):
                        continue  # never echo unparsed output
                    self._event(event)
                code = self.proc.wait()
                self._diag(f"exit code={code}")
                if self.stopping:
                    self._status(f"Stopped. Kept {len(self.hits)} verified result(s).")
                elif code == 0:
                    self._status(f"Finished. {len(self.hits)} verified result(s).")
                elif code == 1:
                    self._status(f"Attempt limit reached. Kept {len(self.hits)} result(s).")
                else:
                    self._status("Engine failed. Check installation, pattern and GPU support.")
        except Exception:
            self._status("Could not run engine. Check installed packages and runtime.")
        finally:
            self.gpu_stop.set()
            try:
                if self.proc and self.proc.poll() is None:
                    self.proc.terminate()
                    self.proc.wait(timeout=5)
            finally:
                self.proc = None
                self.start.disabled = False
                self.stop.disabled = True

    def _event(self, event):
        kind = event.get("type")
        if kind == "hit":
            self.hits.append(event)
            self._add_card(event)
        elif kind in ("start","tuning"):
            if isinstance(event.get("batch_size"), int):
                self.batch_seen = event["batch_size"]
        elif kind in ("progress","done","summary"):
            attempts = event.get("attempts",0)
            elapsed = event.get("elapsed_seconds",0)
            rate = event.get("keys_per_second", attempts/max(elapsed,1e-9))
            probability = coarse_probability(self.config["prefix"],self.config["suffix"],self.config["ignore_case"])
            chance = -math.expm1(-attempts*probability) if probability else 0
            now_t = elapsed
            prev = self.snap
            current = ((attempts-prev["attempts"])/(now_t-prev["elapsed"])) if prev and now_t > prev["elapsed"] else rate
            self.snap = dict(attempts=attempts, elapsed=elapsed, rate=rate, current=current, batch_size=event.get("batch_size") or getattr(self, "batch_seen", None),
                             expected=(1/(rate*probability) if rate*probability > 0 else math.inf), p50=percentile_seconds(rate, probability, .5), p90=percentile_seconds(rate, probability, .9))
            self.chance.value = min(chance,1)
            self.eta.value = eta_html(self.config["prefix"],self.config["suffix"],self.config["ignore_case"],rate,True)
            self._render()
            self._status(f"Searching. {len(self.hits)} verified result(s). Approximate chance so far {chance:.1%}.")
        elif kind == "error":
            self._status("Engine rejected the request. Check pattern, public key and selected backend.")

    def _stop(self, *_):
        self.stopping = True
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.terminate()
            except ProcessLookupError:
                pass
        self._status("Stopping worker. Existing results stay available.")

    def _clear(self, *_):
        # Clear sync'd secret widgets before dropping them; no zeroization guarantee.
        for card in self.cards:
            for secret_widget in card.get("secret_widgets",[]):
                secret_widget.value = ""
            card["box"].close()
        self.cards.clear()
        self.hits.clear()
        self.results.children = ()
        self.transfer_output.clear_output()
        if not (self.task and self.task.is_alive()):
            self.chance.value = 0
            self.metrics.value = ""
            self._status("Cleared.")

    def _add_card(self, hit):
        wallet = "keypair_json" in hit
        address = hit["address"]
        header = W.HTML('<div class="sv-result"><div class="sv-caption">CPU-verified '+("wallet keypair" if wallet else "seeded account")+'</div><div class="sv-address">'+html.escape(address)+'</div></div>')
        copy_address = W.Button(description="Copy address",icon="copy")
        copy_address.on_click(lambda _: self._copy(address))
        download = W.Button(description="Download JSON64" if wallet else "Download derivation JSON",icon="download",layout=W.Layout(width="240px"))
        download.on_click(lambda _: self._download(hit,wallet))
        controls = [copy_address,download]
        children = [header]
        secret_widgets = []
        if wallet:
            reveal = W.ToggleButton(description="Reveal secret",value=False,icon="eye",layout=W.Layout(width="160px"))
            secret = W.Textarea(value="",disabled=True,layout=W.Layout(width="100%",height="85px",display="none"))
            secret_widgets.append(secret)
            def toggle(change):
                secret.value = hit["phantom_secret"] if change["new"] else ""
                secret.layout.display = "" if change["new"] else "none"
                reveal.description = "Hide secret" if change["new"] else "Reveal secret"
            reveal.observe(toggle,names="value")
            copy_secret = W.Button(description="Copy secret",icon="copy")
            copy_secret.on_click(lambda _: self._copy(hit["phantom_secret"]))
            controls += [reveal,copy_secret]
            children += [secret,W.HTML('<p class="sv-note">Secret hidden by default. Reveal/copy/download is an explicit disclosure to this browser. JSON64 is a 64-byte array, not base64.</p>')]
        else:
            children += [W.HTML('<p class="sv-note">Seed '+html.escape(hit["seed"])+'<br>Base '+html.escape(hit["base"])+'<br>Owner '+html.escape(hit["owner"])+'</p>')]
            copy_seed = W.Button(description="Copy seed",icon="copy")
            copy_seed.on_click(lambda _: self._copy(hit["seed"]))
            controls.append(copy_seed)
        children += [W.Box(controls,layout=W.Layout(display="flex",flex_flow="row wrap",grid_gap="8px"))]
        box = W.VBox(children)
        self.cards.append(dict(box=box,secret_widgets=secret_widgets))
        self.results.children = (*self.results.children,box)

    def _copy(self, value):
        script = "navigator.clipboard.writeText("+json.dumps(value)+").then(()=>true)"
        try:
            from google.colab import output
            output.eval_js(script)
            self._status("Copied. Clipboard contents may be visible to other apps.")
        except ImportError:
            # Output is transient and cleared immediately after browser execution.
            with self.transfer_output:
                display(Javascript(script))
            self._status("Copy requested. Browser clipboard permission is required; download if unavailable. Clear all outputs before saving.")
        except Exception:
            self._status("Clipboard access was blocked. Use download instead.")

    def _download(self, hit, wallet):
        directory = Path(tempfile.mkdtemp(prefix="solvanity-export-"))
        directory.chmod(0o700)
        path = directory/(hit["address"]+".json")
        fd = os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,"w") as stream:
            json.dump(hit["keypair_json"] if wallet else hit,stream)
            stream.write("\n")
        try:
            from google.colab import files
            files.download(str(path))
            self._status("Download requested. Delete the runtime afterward; exported files exist on this VM until removed.")
        except ImportError:
            self._status("Export saved locally to "+str(path)+". Keep it private.")
        except Exception:
            self._status("Browser download failed. The private export remains on this VM. Delete runtime when finished.")
