import importlib.util
from pathlib import Path
from unittest.mock import patch
import io
import os

spec=importlib.util.spec_from_file_location("private_wallet",Path(__file__).parents[2]/"ops/private_wallet.py")
private=importlib.util.module_from_spec(spec)
spec.loader.exec_module(private)

class Sink(io.StringIO):
    def fileno(self):
        return 78
    def close(self):
        self.snapshot=self.getvalue()
        super().close()

def test_private_writer_exclusive_no_output(capsys):
    sink=Sink()
    with patch.object(private.os,"open",return_value=78) as opening, patch.object(private.os,"fdopen",return_value=sink), patch.object(private.os,"fsync") as sync:
        private.write_private({"keypair_json":[0]*64,"phantom_secret":"DO_NOT_EMIT"},Path("/private/file.json"))
    opening.assert_called_once_with(Path("/private/file.json"),os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    assert sink.snapshot=="["+",".join(["0"]*64)+"]\n"
    assert capsys.readouterr()==("","")
    sync.assert_called_once()

def test_no_raw_exception_or_cli_paths():
    text=Path(private.__file__).read_text()
    assert "traceback" not in text or "# Never stringify exceptions/tracebacks" in text
    assert 'solvanity_wallet.__main__' not in text
    assert 'print(e)' not in text
    assert 'str(e)' not in text
    assert 'read_text' not in text and 'read_bytes' not in text
