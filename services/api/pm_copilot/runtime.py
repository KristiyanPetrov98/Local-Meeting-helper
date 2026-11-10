"""Entry-point-aware private workers for source and bundled execution."""
import sys
from pathlib import Path

def hidden_flags(background=False,platform=None):
    """Windows console suppression is separate from background CPU priority."""
    if (platform or sys.platform)!='win32':return 0
    return 0x08000000 | (0x00004000 if background else 0)
MODULES={'document':'pm_copilot.document_worker','media':'pm_copilot.media_worker','assets':'pm_copilot.asset_worker','checks':'pm_copilot.check_worker'}

def command(worker):
    if worker not in MODULES:raise ValueError('Unknown worker')
    if getattr(sys,'frozen',False):return [sys.executable,'--worker',worker]
    return [sys.executable,'-u','-m',MODULES[worker]]

def cwd():return str(Path(sys.executable).parent if getattr(sys,'frozen',False) else Path(__file__).resolve().parents[1])
