"""In-memory standalone-plugin layout. Does not install, enable or publish it."""
from pathlib import Path
import hashlib
import json

FILES = ('__init__.py', 'plugin.yaml', 'hermes_binding.py', 'hermes_connection.py',
         'hermes_conversation.py', 'hermes_handoff.py', 'hermes_handoff_relay.py',
         'hermes_chat.py', 'hermes_gateway.py', 'README.md', 'INSTALL.md')

def collect(root):
    root = Path(root)
    files = {name:(root/'clients'/name).read_bytes() for name in FILES}
    files['LICENSE'] = (root/'package/LICENSE').read_bytes()
    files['SHA256SUMS.json'] = (json.dumps({name:hashlib.sha256(data).hexdigest()
        for name,data in sorted(files.items())},indent=2)+'\n').encode()
    return files
