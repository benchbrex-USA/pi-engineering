"""Package product sources without local state or archived teaching code."""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parent
FILES = [
    "pi.py", "pi_app.py", "pi_workspace.py", "pi_engine.py", "pi_tools.py",
    "pi_terminal.py", "pi_workflow.py", "pi_server.py", "pyproject.toml",
    "pi_models.py", "pi_knowledge.py", "pi_operations.py",
    "pi_qualification.py", "tests/test_qualification.py", "SECURITY.md",
    "reports/security-static.json", "reports/dependency-audit.json",
    "requirements.lock",
    "integrations/deepwiki.json",
    "README.md", "CLI_DESIGN.md", "BUILD_CONTRACT.md", "RESEARCH.md",
    "VERIFICATION.md", "install.sh", "uninstall.sh", "build_release.py",
    "tests/test_product.py", "tests/http_mcp_fixture.py", "tests/check_distribution.py",
    "tests/test_release_features.py", "tests/live_acceptance.py",
    "tests/test_recovery.py",
    "tests/live_integration.py", "tests/load_acceptance.py",
    "reports/live.json", "reports/integration.json", "reports/load.json",
    ".github/workflows/ci.yml",
    "dist/pi_engineering-0.3.2-py3-none-any.whl",
]

if __name__ == "__main__":
    target = ROOT.parent / "Pi_Engineering_CLI.zip"
    with ZipFile(target, "w", compression=ZIP_DEFLATED) as archive:
        for name in FILES:
            archive.write(ROOT / name, "Pi_Engineering_CLI/" + name)
    print(target)
