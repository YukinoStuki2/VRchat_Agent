#!/usr/bin/env python3
"""Execute the real compiled C# core; append unmodified evidence."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

root = Path(__file__).resolve().parent
core = root.parent.parent / "Packages~/com.yukino.vrchat-managed-editing/Editor/Core/GatePolicy.cs"
label = sys.argv[1] if len(sys.argv) > 1 else "manual"
sdk = os.environ.get("DOTNET", "/home/ubuntu/.local/share/vrchat-agent-dev/dotnet/dotnet")
compat = len(sys.argv) > 2 and sys.argv[2] == "--compat"
project = root / ("compatibility/CoreCompatibility.csproj" if compat else "CoreTests.csproj")
if compat:
    command = [sdk, "build", str(project), "--configuration", "Release", "--nologo"]
else:
    command = [sdk, "run", "--project", str(project), "--configuration", "Release"]
    if len(sys.argv) > 2:
        command += ["--", sys.argv[2]]
def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None
before = {"core": sha(core), "tests": sha(root / "Program.cs"), "project": sha(project), "runner": sha(Path(__file__))}
try:
    completed = subprocess.run(command, cwd=root, text=True, capture_output=True,
                               env={**os.environ, "DOTNET_NOLOGO": "1", "DOTNET_CLI_TELEMETRY_OPTOUT": "1"})
    output = completed.stdout + completed.stderr
    code = completed.returncode
except OSError as error:
    output, code = str(error), 127
record = {"label": label, "utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
          "command": command, "source_sha256": before, "exit_code": code, "output": output}
folder = root / "evidence"
folder.mkdir(exist_ok=True)
with (folder / "runs.jsonl").open("a") as handle:
    handle.write(json.dumps(record, ensure_ascii=False) + "\n")
print(output, end="" if output.endswith("\n") else "\n")
print("EVIDENCE", label, "exit_code=" + str(code))
sys.exit(code)
