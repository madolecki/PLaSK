/*
 * This file is part of PLaSK (https://plask.app) by Photonics Group at TUL
 * Copyright (c) 2022 Lodz University of Technology
 *
 * This program is free software: you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation, version 3.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
 * GNU General Public License for more details.
 */

#include "therm2d_triangle.hpp"

namespace plask { namespace thermal { namespace tstatic {
ThermalFem2DTriangleSolver::ThermalFem2DTriangleSolver(const std::string& name)
    : FemSolverWithMesh<Geometry2DCartesian, TriangularMesh2D>(name), loopno(0) {}

ThermalFem2DTriangleSolver::~ThermalFem2DTriangleSolver() {}

std::string ThermalFem2DTriangleSolver::getClassName() const { return "thermal.Static2DTriangle"; }

void ThermalFem2DTriangleSolver::onInitialize() {
    if (!geometry) throw NoGeometryException(getId());
    if (!mesh) throw NoMeshException(getId());
    FemSolverWithMesh<Geometry2DCartesian, TriangularMesh2D>::onInitialize();
    loopno = 0;
    temperatures.reset(mesh->size(), 300.);
}

void ThermalFem2DTriangleSolver::onInvalidate() { temperatures.reset(); }

void ThermalFem2DTriangleSolver::makeMatrix() {
    writelog(LOG_INFO, "[TEST]: Triangular mesh: {} nodes, {} elements", mesh->size(), mesh->getElementsCount());
    for (size_t i = 0; i < mesh->getElementsCount(); ++i) {
      auto element_nodes = mesh->getElement(i).getNodes();
        auto a = element_nodes[0];
        auto b = element_nodes[1];
        auto c = element_nodes[2];
        writelog(LOG_RESULT, "[TEST]: Element {}: ({}, {}) ({}, {}) ({}, {})",
                 i, a.c0, a.c1, b.c0, b.c1, c.c0, c.c1);
    }
}

double ThermalFem2DTriangleSolver::compute(int) {
    initCalculation();
    makeMatrix();
    return 0.;
}
}}}  // namespace plask::thermal::tstatic
