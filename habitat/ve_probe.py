import json
import socket
from datetime import datetime
import os

payload = {
    "ts_utc": datetime.utcnow().isoformat() + "Z",
    "host": socket.gethostname(),
    "user": os.environ.get("USERNAME") or os.environ.get("USER"),
    "note": "Echo Nexus habitat probe online",
}

print(json.dumps(payload))
