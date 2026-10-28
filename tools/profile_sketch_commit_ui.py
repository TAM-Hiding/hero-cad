from PySide6.QtWidgets import QApplication
from hero_cad.ui.main_window import MainWindow
from tools.profile_sketch_commit import fixture
from time import perf_counter
from statistics import median
import cProfile,pstats
from vtkmodules.qt.QVTKRenderWindowInteractor import QVTKRenderWindowInteractor
original = QVTKRenderWindowInteractor.__init__
def no_gpu(self,*a,**kw):
    original(self,*a,**kw)
    self.GetRenderWindow().Render = lambda: None
QVTKRenderWindowInteractor.__init__ = no_gpu
app=QApplication([])
w=MainWindow();w.show();app.processEvents()
for pairs,count in [(0,n) for n in (10,50,100,250)]+[(12,10),(37,10)]:
    samples=[]
    for _ in range(3):
        w.document,sid=fixture(pairs,count);w.refresh();w.viewport.sketch.enter(sid)
        from hero_cad.sketch import Line
        start=perf_counter();w.entity_created(Line(0,60,1,61));samples.append((perf_counter()-start)*1000)
    print(1+2*pairs,count,round(median(samples),3),flush=True)
p=cProfile.Profile();p.runcall(w.entity_created,Line(2,60,3,61));pstats.Stats(p).sort_stats('cumulative').print_stats(25)
w.viewport.Finalize()
