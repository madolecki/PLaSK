import numpy
from plask import *
from plask import material, geometry, mesh
from thermal.static import Static2DTriangle

solver = Static2DTriangle()
solver.geometry = plask.geometry.Cartesian2D(plask.geometry.Rectangle(2, 1, "GaN"))

m = mesh.Triangular2D()
b = mesh.Triangular2D.Builder(m)   # takes the mesh to fill
b.add([0, 0], [2, 0], [2, 1])      # one triangle from three points
b.add([0, 0], [2, 1], [0, 1])      # the other half of the 2x1 rectangle

solver = Static2DTriangle("therm2d_tri")
solver.geometry = geometry.Cartesian2D(geometry.Rectangle(2, 1, "GaN"))
solver.mesh = m
solver.compute()
