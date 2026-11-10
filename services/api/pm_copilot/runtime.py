"""Entry-point-aware private workers for source and bundled execution."""
import sys
from pathlib import Path
MODULES={'document':'pm_copilot.document_worker','media':'pm_copilot.media_worker','assets':'pm_copilot.asset_worker','checks':'pm_copilot.check_worker'}

def command(worker):
    if worker not in MODULES:raise ValueError('Unknown worker')
    if getattr(sys,'frozen',False):return [sys.executable,'--worker',worker]
    return [sys.executable,'-u','-m',MODULES[worker]]

def cwd():return str(Path(sys.executable).parent if getattr(sys,'frozen',False) else Path(__file__).resolve().parents[1])
