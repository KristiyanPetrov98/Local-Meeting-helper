import os
import sys
from pathlib import Path

_dll_handles=[]
if sys.platform=='win32' and getattr(sys,'frozen',False):
    ffmpeg=Path(sys._MEIPASS)/'ffmpeg'
    if ffmpeg.is_dir():
        _dll_handles.append(os.add_dll_directory(str(ffmpeg)))
        os.environ['PATH']=str(ffmpeg)+os.pathsep+os.environ.get('PATH','')

from pm_copilot.launcher import main
if __name__=='__main__':main()
