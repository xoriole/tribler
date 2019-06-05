import igraph as ig
import numpy as np

import json
import urllib2

data = []
req = urllib2.Request("https://raw.githubusercontent.com/plotly/datasets/master/miserables.json")
opener = urllib2.build_opener()
f = opener.open(req)
data = json.loads(f.read())

print data.keys()



N=len(data['nodes'])


L=len(data['links'])
Edges=[(data['links'][k]['source'], data['links'][k]['target']) for k in range(L)]

G=ig.Graph(Edges, directed=False)


labels=[]
group=[]
for node in data['nodes']:
    labels.append(node['name'])
    group.append(node['group'])


layt=G.layout('kk', dim=3)


Xn=[layt[k][0] for k in range(N)]# x-coordinates of nodes
Yn=[layt[k][1] for k in range(N)]# y-coordinates
Zn=[layt[k][2] for k in range(N)]# z-coordinates
Xe=[]
Ye=[]
Ze=[]
for e in Edges:
    Xe+=[layt[e[0]][0],layt[e[1]][0], None]# x-coordinates of edge ends
    Ye+=[layt[e[0]][1],layt[e[1]][1], None]
    Ze+=[layt[e[0]][2],layt[e[1]][2], None]


print zip(Xn, Yn, Zn)

pos1 = np.empty((N, 3))
# size = np.empty((53))
# color = np.empty((53, 4))
for k in range(N):
    pos1[k] = (layt[k][0], layt[k][1], layt[k][2])

from pyqtgraph.Qt import QtCore, QtGui
import pyqtgraph.opengl as gl

app = QtGui.QApplication([])
w = gl.GLViewWidget()
w.opts['distance'] = 20
w.show()
w.setWindowTitle('pyqtgraph example: GLScatterPlotItem')

g = gl.GLGridItem()
w.addItem(g)

##
##  First example is a set of points with pxMode=False
##  These demonstrate the ability to have points with real size down to a very small scale
##
pos = np.empty((53, 3))
size = np.empty((53))
color = np.empty((53, 4))
pos[0] = (1, 0, 0)
size[0] = 0.5
color[0] = (1.0, 0.0, 0.0, 0.5)
pos[1] = (0, 1, 0)
size[1] = 0.2
color[1] = (0.0, 0.0, 1.0, 0.5)
pos[2] = (0, 0, 1)
size[2] = 2. / 3.
color[2] = (0.0, 1.0, 0.0, 0.5)

z = 0.5
d = 6.0
for i in range(3, 53):
    pos[i] = (0, 0, z)
    size[i] = 2. / d
    color[i] = (0.0, 1.0, 0.0, 0.5)
    z *= 0.5
    d *= 2.0

sp1 = gl.GLScatterPlotItem(pos=pos1, size=0.1, pxMode=False)
sp1.translate(5, 5, 0)
w.addItem(sp1)



# ## Start Qt event loop unless running in interactive mode.
if __name__ == '__main__':
    import sys
    if (sys.flags.interactive != 1) or not hasattr(QtCore, 'PYQT_VERSION'):
        QtGui.QApplication.instance().exec_()