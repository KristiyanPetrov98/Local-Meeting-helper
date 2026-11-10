"""Synthetic evidence exercises policy; these fixtures are never release evidence."""
import hashlib
from pm_copilot.release_policy import qualify,TARGET_CHECKS,REVIEW_CHECKS
from pm_copilot.build_identity import ordered_sources


def test_source_order_is_identical_for_windows_and_posix_paths():
    from pathlib import PurePosixPath,PureWindowsPath
    names=['apps/web/src/client.ts','apps/web/src/QualificationPanel.tsx','apps/web/src/App.tsx']
    result=[]
    for path_type,root in ((PurePosixPath,'/source'),(PureWindowsPath,'C:/source')):
        directory=path_type(root)
        result.append([p.relative_to(directory).as_posix() for p in ordered_sources([directory/n for n in names],directory)])
    assert result[0]==result[1]==sorted(names)


def test_missing_files_short_runs_stale_and_truthy_evidence_cannot_qualify(tmp_path):
    identity='a'*64
    assert qualify(identity)['release_ready'] is False
    installer=tmp_path/'fixture.exe';installer.write_bytes(b'explicit fixture, not an installer')
    artifact=hashlib.sha256(installer.read_bytes()).hexdigest()
    evidence=dict(portable={'source_digest':identity,'status':'passed','checks':dict.fromkeys(
        ('api','unit','native','types','schema','build','electron','frozen_backend','portable_soak'),True)},
        dependencies={'source_digest':identity,'status':'passed'},
        target={'source_digest':identity,'kind':'target_laptop_telemetry','phase':'completed','telemetry_passed':True,
                'checks':dict.fromkeys(TARGET_CHECKS,True),'duration_seconds':5401,'model_digest':'b'*64},
        windows={'source_digest':identity,'status':'passed','platform':'win32','full_model_runtime':True,
                 'bundled_smoke_passed':True,'installer_sha256':artifact},
        review={'source_digest':identity,'reviewer':'Policy test fixture','reviewed_at':'2026-11-09','installer_sha256':artifact,'checks':dict.fromkeys(REVIEW_CHECKS,True)})
    assert qualify(identity,**evidence,installer=installer)['release_ready'] is True
    for name in evidence:
        stale={**evidence[name],'source_digest':'wrong'}
        assert qualify(identity,**{**evidence,name:stale},installer=installer)['release_ready'] is False
    for key,value in [('duration_seconds',60),('telemetry_passed','true'),('model_digest','unknown'),('checks',{})]:
        assert not qualify(identity,**{**evidence,'target':{**evidence['target'],key:value}},installer=installer)['release_ready']
    for key in REVIEW_CHECKS:
        checks={**evidence['review']['checks'],key:False}
        assert not qualify(identity,**{**evidence,'review':{**evidence['review'],'checks':checks}},installer=installer)['release_ready']
    installer.write_bytes(b'changed')
    assert not qualify(identity,**evidence,installer=installer)['release_ready']
