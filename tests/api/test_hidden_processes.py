from pm_copilot.runtime import hidden_flags

def test_foreground_transcription_hides_console_without_lowering_priority():
    flags=hidden_flags(platform='win32')
    assert flags & 0x08000000 and not flags & 0x00004000

def test_background_workers_keep_priority_policy_and_hide_console():
    flags=hidden_flags(background=True,platform='win32')
    assert flags & 0x08000000 and flags & 0x00004000

def test_non_windows_processes_receive_no_windows_flags():
    assert hidden_flags(platform='linux')==hidden_flags(background=True,platform='darwin')==0
