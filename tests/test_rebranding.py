"""Identity migration and immutable pre-rename STAR-CAD document fixtures."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from importlib import metadata
import pytest
from hero_cad import __version__
from hero_cad.document import Document
from hero_cad.features import BoxParameters
from hero_cad.geometry import volume
from hero_cad.ui.main_window import MainWindow

FIXTURES = Path(__file__).parent/'fixtures'/'legacy_documents'


def test_installed_package_and_console_identity():
    distribution = metadata.distribution('hero-cad')
    assert distribution.version == __version__
    scripts = {e.name:e.value for e in distribution.entry_points if e.group=='console_scripts'}
    assert scripts == {'hero-cad':'hero_cad.app:main'}
    import ast
    root=Path(__file__).parents[1]
    old_package='star'+'_cad'
    for directory in (root/'src',root/'tests'):
        for path in directory.rglob('*.py'):
            for node in ast.walk(ast.parse(path.read_text())):
                names=([node.module] if isinstance(node,ast.ImportFrom) else
                       [n.name for n in node.names] if isinstance(node,ast.Import) else [])
                assert all(name is None or name.split('.')[0]!=old_package for name in names),path
    old_source=Path(__file__).parents[1]/'src'/'star_cad'
    # Upgraded checkouts may retain ignored bytecode caches; no old source ships.
    assert not any(old_source.rglob('*.py'))


def test_main_window_hero_title_and_document_filters(qtbot,monkeypatch,tmp_path):
    from PySide6.QtWidgets import QFileDialog
    w=MainWindow()
    qtbot.addWidget(w)
    assert w.windowTitle().startswith(f'HERO-CAD {__version__}')
    calls=[]
    def save(*args):
        calls.append(args)
        return str(tmp_path/'unchanged_extension.starcad'),''
    monkeypatch.setattr(QFileDialog,'getSaveFileName',save)
    assert w.save_document(save_as=True)
    assert calls[0][1]=='Save HERO-CAD document'
    assert calls[0][3]=='HERO-CAD documents (*.starcad)'
    assert json.loads(w.document.path.read_text())['format']=='star-cad'
    def open_file(*args):
        calls.append(args)
        return str(FIXTURES/'v6.starcad'),''
    monkeypatch.setattr(QFileDialog,'getOpenFileName',open_file)
    w.open_document()
    assert calls[-1][1]=='Open HERO-CAD document'
    assert calls[-1][3]=='HERO-CAD documents (*.starcad)'
    assert any(f.type=='boolean' for f in w.document.features)
    assert all(s.valid for s in w.document.statuses.values())


@pytest.mark.parametrize('version',range(1,7))
def test_pre_rename_documents_regenerate_save_and_history(version,tmp_path):
    path=FIXTURES/f'v{version}.starcad'
    original=path.read_bytes()
    expected=json.loads((FIXTURES/'manifest.json').read_text())['files'][path.name]
    assert hashlib.sha256(original).hexdigest()==expected['sha256']
    d=Document.load(path)
    assert not d.dirty
    assert all(s.valid for s in d.statuses.values())
    assert [f.type for f in d.features]==expected['feature_types']
    assert len(d.active_body_ids)==expected['active_bodies']
    assert volume(d.shape)==pytest.approx(expected['volume'],rel=1e-10)
    before=d.features
    p=d.parameters
    d.set_box(BoxParameters(p.width,p.depth,p.height+5))
    assert all(s.valid for s in d.statuses.values())
    assert volume(d.shape)!=pytest.approx(expected['volume'])
    d.undo()
    assert d.features==before and volume(d.shape)==pytest.approx(expected['volume'])
    d.redo()
    assert all(s.valid for s in d.statuses.values())
    d.undo()
    destination=tmp_path/path.name
    d.save(destination)
    loaded=Document.load(destination)
    assert loaded.features==d.features
    assert json.loads(destination.read_text())['format']=='star-cad'
    assert path.read_bytes()==original
    if version>=3:
        assert json.loads(destination.read_text())==json.loads(original)


@pytest.mark.parametrize('entry',['console','module'])
def test_real_launcher_starts_hero_window_and_exits_cleanly(entry,tmp_path):
    # Test-only instrumentation exits the actual Qt event loop after inspecting
    # its visible window. Production receives no smoke-test flag or hook.
    (tmp_path/'sitecustomize.py').write_text("""
import json
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QMainWindow
original_exec=QApplication.exec
def inspected_exec(self):
    def inspect():
        windows=[w for w in self.topLevelWidgets() if isinstance(w,QMainWindow) and w.isVisible()]
        data={'name':self.applicationName(),'display':self.applicationDisplayName(),
              'version':self.applicationVersion(),'titles':[w.windowTitle() for w in windows]}
        print('HERO_LAUNCH_METADATA='+json.dumps(data),flush=True)
        self.quit()
    QTimer.singleShot(0,inspect)
    return original_exec()
QApplication.exec=inspected_exec
""")
    command = [str(Path(sys.executable).parent/'hero-cad')] if entry=='console' else [sys.executable,'-m','hero_cad']
    env={**os.environ,'PYTHONPATH':str(tmp_path)}
    result=subprocess.run(command,cwd=tmp_path,env=env,text=True,capture_output=True,timeout=60)
    assert result.returncode==0,result.stderr
    line=next(line for line in result.stdout.splitlines() if line.startswith('HERO_LAUNCH_METADATA='))
    data=json.loads(line.split('=',1)[1])
    assert data['name']==data['display']=='HERO-CAD'
    assert data['version']==__version__
    assert len(data['titles'])==1 and data['titles'][0].startswith(f'HERO-CAD {__version__}')
