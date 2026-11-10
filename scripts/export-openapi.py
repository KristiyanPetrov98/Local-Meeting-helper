import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'services/api'))
from pm_copilot.app import create_app
app = create_app(':memory:', 'schema-generation-only', 'http://127.0.0.1:1')
Path('packages/contracts/openapi.json').write_text(json.dumps(app.openapi(), indent=2)+'\n')
app.state.store.close()
