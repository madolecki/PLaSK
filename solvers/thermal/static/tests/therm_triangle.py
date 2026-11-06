import unittest

import numpy
from plask import *
from plask import material, geometry, mesh
from thermal.static import Static2DTriangle

def temperature_at(solver, x, y):
    point_mesh = mesh.Rectangular2D(
        [x], [y]
    )

    data = solver.outTemperature(point_mesh)

    return float(numpy.asarray(data).ravel()[0])

def flux_at(solver, x, y):
    point_mesh = mesh.Rectangular2D([x], [y])

    data = solver.outHeatFlux(point_mesh, "nearest")

    return numpy.asarray(data).reshape(-1, 2)[0]

def thermal_cond_at(solver, x, y):
    point_mesh = mesh.Rectangular2D(
        [x], [y]
    )

    data = solver.outThermalConductivity(point_mesh)

    return float(numpy.asarray(data).ravel()[0])

def assert_temperature(solver, coords, expected, epsilon=1e-6):
    # WARN: Z JAKIEGOŚ POWODU x i y SĄ ZE MUSZĄ BYĆ ZE SOBĄ ZAMIENIONE PRZY CZYTANIU Z SIATKI. CZY TO CELOWE??
    actual = temperature_at(solver, coords[1], coords[0])

    error = abs(actual - expected)

    assert error < epsilon, (
        f"Temperature mismatch at {coords}: "
        f"expected {expected:.8f} K, "
        f"got {actual:.8f} K, "
        f"error = {error:.3e} K, "
        f"tolerance = {epsilon:.3e} K"
    )


def assert_flux(solver, coords, expected, epsilon=1e-6):
    actual = flux_at(solver, coords[1], coords[0])

    numpy.testing.assert_allclose(
    actual, expected,
    rtol=epsilon,
    atol=1e-9 * numpy.max(numpy.abs(expected)),
    err_msg=f"Heat flux mismatch at {coords}"
)

m = mesh.Triangular2D()
b = mesh.Triangular2D.Builder(m)

y_levels = [0, 0.5, 1, 1.5, 2]
x_levels = [0, 1, 2]

for j in range(len(y_levels) - 1):
    for i in range(len(x_levels) - 1):
        p00 = [x_levels[i],     y_levels[j]]
        p10 = [x_levels[i+1],   y_levels[j]]
        p01 = [x_levels[i],     y_levels[j+1]]
        p11 = [x_levels[i+1],   y_levels[j+1]]

        b.add(p00, p10, p11)
        b.add(p00, p11, p01)

#plask.plot_mesh(m)
#plask.show()

solver = Static2DTriangle("therm2d_tri")
@material.simple()
class ConstK(material.Material):
    def thermk(self, T=300., h=float('inf')):
        return 100.

solver.geometry = geometry.Cartesian2D(geometry.Rectangle(2, 2, ConstK()))
solver.mesh = m
solver.temperature_boundary.append(m.Bottom(), 300.0)
solver.temperature_boundary.append(m.Top(), 500.0)
solver.compute()


# check temperatures and heat fluxes
y_levels = [0, 0.5, 1, 1.5, 2]
for y in y_levels:
    temp = 100 * y + 300
    assert_temperature(solver, [0, y], temp)
    assert_temperature(solver, [1, y], temp)
    assert_temperature(solver, [2, y], temp)

    flux = [0, 1e6 * 100 * -(500-300)/2]
    assert_flux(solver, [y, 0], flux)
