"""Generated per-user files and real shell-independent desktop-entry execution."""
import ctypes
import ctypes.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import pytest
from PySide6.QtGui import QImage
from hero_cad.desktop_launcher import install_launcher, uninstall_launcher, data_directory, main


def environment(tmp_path):
    folder=tmp_path/'venv space % dollar$ back` quote" slash\\'
    bindir=folder/'bin';bindir.mkdir(parents=True)
    import venv
    venv.EnvBuilder(with_pip=False,symlinks=True).create(folder)
    python=bindir/'python'
    marker=tmp_path/'launched.json'
    (bindir/'hero-cad').write_text('import os,json\nfrom pathlib import Path\nPath('+repr(str(marker))+').write_text(json.dumps({k:os.environ.get(k) for k in ("QT_QPA_PLATFORM","HERO_CAD_ICON","PATH","LD_LIBRARY_PATH")}))\n')
    icon=tmp_path/'approved test fixture.png'
    image=QImage(64,64,QImage.Format_ARGB32);image.fill(0xff987650);assert image.save(str(icon))
    return python,icon,marker


def launch_with_gio(desktop):
    # Actual desktop Exec parsing, not shlex or a second implementation of quoting.
    gio=ctypes.CDLL(ctypes.util.find_library('gio-2.0'))
    gio.g_desktop_app_info_new_from_filename.argtypes=[ctypes.c_char_p]
    gio.g_desktop_app_info_new_from_filename.restype=ctypes.c_void_p
    gio.g_app_info_launch.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,ctypes.POINTER(ctypes.c_void_p)]
    gio.g_app_info_launch.restype=ctypes.c_int
    app=gio.g_desktop_app_info_new_from_filename(os.fsencode(desktop));assert app
    error=ctypes.c_void_p();assert gio.g_app_info_launch(app,None,None,ctypes.byref(error)), error
    gobject=ctypes.CDLL(ctypes.util.find_library('gobject-2.0'))
    gobject.g_object_unref.argtypes=[ctypes.c_void_p];gobject.g_object_unref(app)


def test_repeatable_install_real_gio_launch_special_paths_and_uninstall(tmp_path,monkeypatch):
    python,icon,marker=environment(tmp_path)
    data=tmp_path/'user data % dollar$ back` quote" slash\\'
    monkeypatch.setenv('XDG_DATA_HOME',str(data));monkeypatch.setenv('XDG_STATE_HOME',str(tmp_path/'state'))
    monkeypatch.setenv('PATH','/no/activated/environment');monkeypatch.delenv('VIRTUAL_ENV',raising=False)
    monkeypatch.delenv('QT_QPA_PLATFORM',raising=False);monkeypatch.setenv('LD_LIBRARY_PATH','/preserved/library/path')
    desktop=install_launcher(icon,python=python)
    text=desktop.read_text()
    assert desktop==data/'applications/hero-cad.desktop' and 'Terminal=false' in text and 'Name=HERO-CAD' in text
    assert 'Categories=Graphics;Engineering;' in text and 'StartupWMClass=hero-cad' in text
    installed_icon=data/'icons/hicolor/64x64/apps/hero-cad.png'
    assert installed_icon.read_bytes()==icon.read_bytes() and 'Icon='+str(installed_icon).replace('\\','\\\\') in text
    first=desktop.read_bytes();assert install_launcher(icon,python=python).read_bytes()==first
    assert list((data/'applications').glob('*.desktop'))==[desktop]
    launch_with_gio(desktop)
    deadline=time.monotonic()+5
    while not marker.exists() and time.monotonic()<deadline:time.sleep(.02)
    assert marker.exists()
    values=json.loads(marker.read_text())
    assert values=={'QT_QPA_PLATFORM':'xcb','HERO_CAD_ICON':str(installed_icon),'PATH':'/no/activated/environment','LD_LIBRARY_PATH':'/preserved/library/path'}
    unrelated=data/'applications/unrelated.desktop';unrelated.write_text('keep')
    preferences=data/'hero-cad/other-file';preferences.write_text('keep')
    uninstall_launcher();uninstall_launcher()
    assert not desktop.exists() and not installed_icon.exists() and not (data/'hero-cad/launch.py').exists()
    assert unrelated.read_text()==preferences.read_text()=='keep'


def test_explicit_qt_environment_preserved_and_png_size_changes_cleanup(tmp_path,monkeypatch):
    python,icon,marker=environment(tmp_path);data=tmp_path/'data'
    desktop=install_launcher(icon,python=python,data_home=data)
    monkeypatch.setenv('QT_QPA_PLATFORM','offscreen');monkeypatch.setenv('XDG_STATE_HOME',str(tmp_path/'state'))
    subprocess.run([str(python),str(data/'hero-cad/launch.py')],check=True)
    assert json.loads(marker.read_text())['QT_QPA_PLATFORM']=='offscreen'
    image=QImage(128,128,QImage.Format_ARGB32);image.fill(0xff987650);image.save(str(icon))
    install_launcher(icon,python=python,data_home=data)
    assert (data/'icons/hicolor/128x128/apps/hero-cad.png').exists()
    uninstall_launcher(data_home=data)
    assert not (data/'icons/hicolor/128x128/apps/hero-cad.png').exists()
    assert not (data/'icons/hicolor/64x64/apps/hero-cad.png').exists()


def test_missing_artwork_environment_and_unmanaged_entries_fail_before_install(tmp_path):
    python,icon,marker=environment(tmp_path);data=tmp_path/'data'
    with pytest.raises(ValueError,match='approved'):install_launcher(tmp_path/'missing.png',python=python,data_home=data)
    assert not data.exists()
    with pytest.raises(ValueError,match='environment'):install_launcher(icon,python=tmp_path/'missing-python',data_home=data)
    image=QImage(64,32,QImage.Format_ARGB32);image.fill(0);image.save(str(icon))
    with pytest.raises(ValueError,match='square'):install_launcher(icon,python=python,data_home=data)
    image=QImage(64,64,QImage.Format_ARGB32);image.fill(0);image.save(str(icon))
    desktop=data/'applications/hero-cad.desktop';desktop.parent.mkdir(parents=True);desktop.write_text('custom user entry')
    with pytest.raises(ValueError,match='unmanaged'):install_launcher(icon,python=python,data_home=data)
    with pytest.raises(ValueError,match='unmanaged'):uninstall_launcher(data_home=data)
    assert desktop.read_text()=='custom user entry'
    with pytest.raises(SystemExit):main([])


def test_svg_icon_xdg_fallback_and_standard_validator(tmp_path,monkeypatch):
    python,_,_=environment(tmp_path);icon=tmp_path/'approved.svg'
    icon.write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512"><circle cx="256" cy="256" r="200"/></svg>')
    data=tmp_path/'standard data';desktop=install_launcher(icon,python=python,data_home=data)
    assert (data/'icons/hicolor/scalable/apps/hero-cad.svg').read_text()==icon.read_text()
    monkeypatch.setenv('XDG_DATA_HOME','relative-is-ignored')
    assert data_directory()==Path.home()/'.local/share'
    validator=shutil.which('desktop-file-validate') or os.environ.get('HERO_DESKTOP_VALIDATOR')
    if validator:
        result=subprocess.run([validator,str(desktop)],text=True,capture_output=True)
        assert result.returncode==0,result.stdout+result.stderr
    else:
        pytest.skip('desktop-file-utils is required for the standard validator check')


def test_real_launcher_opens_installed_app_without_activation(qtbot,tmp_path,monkeypatch):
    # Use the installed development environment and real console entry point.
    _,icon,_=environment(tmp_path);data=tmp_path/'actual desktop data'
    install_launcher(icon,python=sys.executable,data_home=data)
    env=dict(os.environ,PATH='/no/activated/environment',XDG_CONFIG_HOME=str(tmp_path/'config'),
             XDG_STATE_HOME=str(tmp_path/'state'))
    env.pop('VIRTUAL_ENV',None)
    child=subprocess.Popen([sys.executable,str(data/'hero-cad/launch.py')],env=env)
    x=ctypes.CDLL(ctypes.util.find_library('X11'))
    x.XOpenDisplay.argtypes=[ctypes.c_char_p];x.XOpenDisplay.restype=ctypes.c_void_p
    x.XDefaultRootWindow.argtypes=[ctypes.c_void_p];x.XDefaultRootWindow.restype=ctypes.c_ulong
    x.XQueryTree.argtypes=[ctypes.c_void_p,ctypes.c_ulong,ctypes.POINTER(ctypes.c_ulong),ctypes.POINTER(ctypes.c_ulong),ctypes.POINTER(ctypes.POINTER(ctypes.c_ulong)),ctypes.POINTER(ctypes.c_uint)]
    x.XFetchName.argtypes=[ctypes.c_void_p,ctypes.c_ulong,ctypes.POINTER(ctypes.c_void_p)]
    x.XInternAtom.argtypes=[ctypes.c_void_p,ctypes.c_char_p,ctypes.c_int];x.XInternAtom.restype=ctypes.c_ulong
    x.XGetWindowProperty.argtypes=[ctypes.c_void_p,ctypes.c_ulong,ctypes.c_ulong,ctypes.c_long,ctypes.c_long,ctypes.c_int,ctypes.c_ulong,ctypes.POINTER(ctypes.c_ulong),ctypes.POINTER(ctypes.c_int),ctypes.POINTER(ctypes.c_ulong),ctypes.POINTER(ctypes.c_ulong),ctypes.POINTER(ctypes.c_void_p)]
    x.XFree.argtypes=[ctypes.c_void_p]
    x.XCloseDisplay.argtypes=[ctypes.c_void_p]
    class ClassHint(ctypes.Structure):
        _fields_=[('name',ctypes.c_void_p),('class_',ctypes.c_void_p)]
    x.XGetClassHint.argtypes=[ctypes.c_void_p,ctypes.c_ulong,ctypes.POINTER(ClassHint)]
    display=x.XOpenDisplay(os.fsencode(os.environ['DISPLAY']));assert display
    found=[];seen=set()
    def visible_window():
        if child.poll() is not None:
            log=tmp_path/'state/hero-cad/launcher.log'
            pytest.fail(log.read_text() if log.exists() else 'Application exited before opening')
        root=x.XDefaultRootWindow(display);r=ctypes.c_ulong();p=ctypes.c_ulong();children=ctypes.POINTER(ctypes.c_ulong)();count=ctypes.c_uint()
        x.XQueryTree(display,root,ctypes.byref(r),ctypes.byref(p),ctypes.byref(children),ctypes.byref(count))
        windows=[children[i] for i in range(count.value)]
        if children:x.XFree(children)
        for window in windows:
            title=ctypes.c_void_p();actual=ctypes.c_ulong();fmt=ctypes.c_int();items=ctypes.c_ulong();remaining=ctypes.c_ulong()
            atom=x.XInternAtom(display,b'_NET_WM_NAME',True)
            x.XGetWindowProperty(display,window,atom,0,4096,False,0,ctypes.byref(actual),ctypes.byref(fmt),ctypes.byref(items),ctypes.byref(remaining),ctypes.byref(title))
            if title and fmt.value==8:
                name=ctypes.string_at(title,items.value).decode(errors='replace');x.XFree(title);seen.add(name)
                if name.startswith('HERO-CAD 0.'):
                    hint=ClassHint()
                    if not x.XGetClassHint(display,window,ctypes.byref(hint)):continue
                    values=[ctypes.string_at(hint.name).decode(),ctypes.string_at(hint.class_).decode()]
                    x.XFree(hint.name);x.XFree(hint.class_)
                    # A mapped native window alone can precede the first CAD frame.
                    # Wait for actual blue shaded solid pixels, not a blank GL surface.
                    import numpy as np
                    from PySide6.QtWidgets import QApplication
                    rendered=QApplication.primaryScreen().grabWindow(window).toImage().convertToFormat(QImage.Format_RGB888)
                    if rendered.isNull():continue
                    rows=np.frombuffer(rendered.constBits(),dtype=np.uint8).reshape(rendered.height(),rendered.bytesPerLine())
                    rgb=rows[:,:rendered.width()*3].reshape(rendered.height(),rendered.width(),3).astype(int)
                    center=rgb[rgb.shape[0]//4:3*rgb.shape[0]//4,rgb.shape[1]//3:2*rgb.shape[1]//3]
                    if np.count_nonzero((center[...,2]-center[...,0]>20)&(center[...,1]>100))<100:continue
                    found.append((name,values));return True
        return False
    try:
        try:qtbot.waitUntil(visible_window,timeout=20000)
        except Exception:
            print('Observed X11 window titles:',seen)
            raise
        assert 'hero-cad' in found[0][1]  # Matches StartupWMClass for GNOME dock grouping.
    finally:
        x.XCloseDisplay(display)
        child.terminate()
        try:child.wait(timeout=10)
        except subprocess.TimeoutExpired:child.kill();child.wait()
