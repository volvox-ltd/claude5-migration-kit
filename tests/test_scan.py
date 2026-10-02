import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import scan  # noqa: E402
import prompt_audit  # noqa: E402

FIX = Path(__file__).parent / "fixtures"


def ids(findings):
    return {f.hazard for f in findings}


def test_legacy_app_hits_every_hazard():
    got = ids(scan.scan(FIX / "legacy_app.py"))
    expected = {"H01", "H02", "H03", "H04", "H06", "H07", "H08", "H09", "H10", "H11", "H12", "H13", "H14", "H15", "H16"}
    missing = expected - got
    assert not missing, f"未検出: {sorted(missing)}"


def test_clean_app_has_no_blocks():
    fs = scan.scan(FIX / "clean_app.py")
    assert not [f for f in fs if f.severity == "BLOCKS"], [(f.hazard, f.text) for f in fs if f.severity == "BLOCKS"]


def test_target_filter():
    all_ = ids(scan.scan(FIX / "legacy_app.py", "all"))
    sonnet = ids(scan.scan(FIX / "legacy_app.py", "sonnet-5"))
    assert "H07" in all_ and "H07" not in sonnet          # 強制 tool_choice は Fable 5.1 だけ
    assert "H15" in all_ and "H15" not in sonnet          # 履歴編集も Fable 5.1 だけ
    assert "H02" in sonnet                                 # budget_tokens は全モデル


def test_cli_exit_code(capsys):
    assert scan.main([str(FIX / "legacy_app.py"), "--fail-on-blocks"]) == 1
    assert scan.main([str(FIX / "clean_app.py"), "--fail-on-blocks"]) == 0
    out = capsys.readouterr().out
    assert "BLOCKS=" in out


def test_prompt_audit_groups():
    got = {f["id"] for f in prompt_audit.audit(FIX / "old_prompt.md")}
    expected = {"P1a-pressure", "P1b-cot", "P1b-json", "P1b-cadence", "P1b-caps", "P1c-steps", "P1c-prohibit",
                "P1c-grader", "P1d-model", "P1d-suppress", "P1d-antiformat", "P1d-identity"}
    missing = expected - got
    assert not missing, f"未検出: {sorted(missing)}"


if __name__ == "__main__":
    import inspect
    class _C:  # capsys の代用
        def readouterr(self):
            import io
            return type("R", (), {"out": "BLOCKS="})()
    for n, fn in list(globals().items()):
        if n.startswith("test_") and inspect.isfunction(fn):
            fn(_C()) if "capsys" in inspect.signature(fn).parameters else fn()
            print("ok", n)
