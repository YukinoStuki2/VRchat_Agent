"""Actual file/helper/C# import pipeline; reviewer, context and UI are fixtures."""
from pathlib import Path
import json
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
dotnet, dll = sys.argv[1:]

def run(args, data=b''):
    result = subprocess.run(args, input=data, capture_output=True, timeout=15)
    assert not result.stderr, 'unexpected stderr in private fixture pipe'
    return result

with tempfile.TemporaryDirectory(prefix='review-pipe-fixture-') as directory:
    root = Path(directory)
    fixture = run([dotnet, dll, 'emit-fixture'])
    assert fixture.returncode == 0
    # Clearly synthetic, produced by the compiled test, never a real review record.
    assert json.loads(fixture.stdout)['reviewer'] == 'fixture reviewer, not real review'
    file = root/'review.json'
    file.write_bytes(fixture.stdout)
    selection = json.dumps({'root': str(root), 'name': 'review.json'}).encode()
    captured = run([sys.executable, '-I', '-B', str(ROOT/'diagnostics/asset_review.py')], selection)
    assert captured.returncode == 0 and captured.stdout == fixture.stdout
    staged = run([dotnet, dll, 'accept-pipe-fixture'], captured.stdout)
    assert staged.returncode == 0 and staged.stdout == b'STAGED_THEN_SEPARATELY_CONFIRMED'
    for payload in (b'{invalid', b'\xff', b'{}', b'x'*262145):
        refused = run([dotnet, dll, 'accept-pipe-fixture'], payload)
        assert refused.returncode == 2 and refused.stdout == b'REFUSED'
    assert file.read_bytes() == fixture.stdout
assert not root.exists()
print('PASS AR007 actual_file_private_helper_csharp_import_with_fixture_context')
