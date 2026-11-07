"""Exercise an installed console script, not imports from the source checkout."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


def check(executable):
    with tempfile.TemporaryDirectory() as directory:
        def run(*arguments):
            result = subprocess.run([executable, "--workspace", directory, "--json", *arguments],
                                    cwd=directory, check=True, capture_output=True, text=True, timeout=120,
                                    env={**os.environ, "PI_TEST_BACKUP": "distribution-test-only-passphrase"})
            return json.loads(result.stdout)
        run("setup")
        pending = run("call", "workspace_write", json.dumps({
            "path": "verified.txt", "content": "installed package writes verified", "expected_hash": "missing"}))
        target = Path(directory) / "verified.txt"
        assert pending["status"] == "awaiting_approval"
        assert not target.exists()
        action_hash = pending["calls"][0]["hash"]
        result = run("approve", pending["id"], action_hash)
        assert result["status"] == "completed"
        assert target.read_text() == "installed package writes verified"
        replay = run("approve", pending["id"], action_hash)
        assert replay["calls"] == result["calls"]
        assert run("receipt", pending["id"])[0]["verification"] == "file_readback"
        assert any(row["kind"] == "verify" for row in run("trace", pending["id"]))
        source = run("knowledge", "add", "verified.txt")
        assert run("knowledge", "search", "package")[0]["source_id"] == source["id"]
        memory = run("memory", "add", "--title", "Release", "--body", "public acceptance",
                     "--source", "distribution test", "--ttl-days", "1")
        assert run("memory", "search", "acceptance")[0]["id"] == memory["id"]
        run("check", "add", "passing", "--command", sys.executable, "--arg=-c", "--arg=print('verified')")
        check = run("call", "workspace_check", '{"name":"passing"}')
        assert check["status"] == "awaiting_approval"
        check = run("approve", check["id"], check["calls"][0]["hash"])
        assert check["calls"][0]["result"]["check_passed"]
        archive = str(Path(directory) / "backup.pi")
        run("backup", archive, "--key-env", "PI_TEST_BACKUP")
        restored = Path(directory) / "restored"
        restored.mkdir()
        run("restore", archive, "--key-env", "PI_TEST_BACKUP", "--workspace", str(restored))
        assert run("memory", "search", "acceptance", "--workspace", str(restored))[0]["id"] == memory["id"]
    print("Installed package: proposal, approval, write/readback, replay, retrieval, memory, checks and encrypted recovery passed.")


if __name__ == "__main__":
    check(sys.argv[1])
