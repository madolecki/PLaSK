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
#include "plask/common/fem/iterative_matrix.hpp"
#include "plask/mesh/triangular2d.hpp"
#include "solvers/thermal/static/therm2d.hpp"

namespace plask { namespace thermal { namespace tstatic {
ThermalFem2DTriangleSolver::ThermalFem2DTriangleSolver(const std::string& name)
    : FemSolverWithMesh<Geometry2DCartesian, TriangularMesh2D>(name),
      loopno(0),
      outTemperature(this, &ThermalFem2DTriangleSolver::getTemperatures),
      outHeatFlux(this, &ThermalFem2DTriangleSolver::getHeatFluxes),
      outThermalConductivity(this, &ThermalFem2DTriangleSolver::getThermalConductivity),
      maxerr(0.05),
      inittemp(300.) {
    temperatures.reset();
    fluxes.reset();
    inHeat = 0.0;
}

ThermalFem2DTriangleSolver::~ThermalFem2DTriangleSolver() {}

std::string ThermalFem2DTriangleSolver::getClassName() const { return "thermal.Static2DTriangle"; }

void ThermalFem2DTriangleSolver::onInitialize() {
    if (!this->geometry) throw NoGeometryException(getId());
    if (!this->mesh) throw NoMeshException(getId());
    FemSolverWithMesh<Geometry2DCartesian, TriangularMesh2D>::onInitialize();
    loopno = 0;
    temperatures.reset(mesh->size(), 300.);
}

void ThermalFem2DTriangleSolver::onInvalidate() { temperatures.reset(); }

FemMatrix* ThermalFem2DTriangleSolver::getMatrix() {
    size_t size = this->mesh->size();
    size_t num_elements = this->mesh->elements().size();

    return new SparseFreeMatrix(this, size, num_elements * 10);
}

void ThermalFem2DTriangleSolver::setMatrix(FemMatrix& A,
                                           DataVector<double>& B,
                                           const BoundaryConditionsWithMesh<TriangularMesh2D::Boundary, double>& btemperature,
                                           const BoundaryConditionsWithMesh<TriangularMesh2D::Boundary, double>& bheatflux,
                                           const BoundaryConditionsWithMesh<TriangularMesh2D::Boundary, Convection>& bconvection,
                                           const BoundaryConditionsWithMesh<TriangularMesh2D::Boundary, Radiation>& bradiation) {
    this->writelog(LOG_DETAIL, "Setting up matrix system ({})", A.describe());

    auto iMesh = (this->mesh)->getElementMesh();
    auto heatdensities = inHeat(iMesh);

    A.clear();
    B.fill(0.0);

    // Set stiffness matrix and load vector
    const auto& elems = this->mesh->elements();

    for (size_t elem_idx = 0; elem_idx < elems.size(); ++elem_idx) {
        const auto& elem = elems[elem_idx];

        // nodes numbers for the current element
        auto n1_idx = elem.getNodeIndex(0);
        auto n2_idx = elem.getNodeIndex(1);
        auto n3_idx = elem.getNodeIndex(2);

        auto n1 = elem.getNode(0);
        auto n2 = elem.getNode(1);
        auto n3 = elem.getNode(2);

        double d = (n1.ee_x() - n2.ee_x()) * (n2.ee_y() - n3.ee_y()) - (n1.ee_y() - n2.ee_y()) * (n2.ee_x() - n3.ee_x());

        double a1 = (n2.ee_y() - n3.ee_y()) / d;
        double a2 = (n3.ee_y() - n1.ee_y()) / d;
        double a3 = (n1.ee_y() - n2.ee_y()) / d;

        double b1 = (n3.ee_x() - n2.ee_x()) / d;
        double b2 = (n1.ee_x() - n3.ee_x()) / d;
        double b3 = (n2.ee_x() - n1.ee_x()) / d;

        double area = elem.getArea();

        // get elements material at its midpoint
        Vec<2, double> midpoint = elem.getMidpoint();
        auto material = this->geometry->getMaterial(midpoint);

        // average temperature on the element
        double temp = (temperatures[n1_idx] + temperatures[n2_idx] + temperatures[n3_idx]) / 3.0;

        // thermal conductivity
        double kx, ky;
        std::tie(kx, ky) = std::tuple<double, double>(material->thermk(temp));

        // load vector
        double f = 1e-12 * heatdensities[elem_idx] * (1. / 3.) * area;
        double f1 = f, f2 = f, f3 = f;

        // stiffness matrix
        double k11, k12, k13, k22, k23, k33;
        k11 = (kx * a1 * a1 + ky * b1 * b1) * area;
        k22 = (kx * a2 * a2 + ky * b2 * b2) * area;
        k33 = (kx * a3 * a3 + ky * b3 * b3) * area;
        k12 = (kx * a1 * a2 + ky * b1 * b2) * area;
        k13 = (kx * a1 * a3 + ky * b1 * b3) * area;
        k23 = (kx * a2 * a3 + ky * b2 * b3) * area;

        // set stiffness matrix
        A(n1_idx, n1_idx) += k11;
        A(n2_idx, n2_idx) += k22;
        A(n3_idx, n3_idx) += k33;

        A(n1_idx, n2_idx) += k12;
        A(n1_idx, n3_idx) += k13;
        A(n2_idx, n3_idx) += k23;

        // set load vector
        B[n1_idx] += f1;
        B[n2_idx] += f2;
        B[n3_idx] += f3;
    }

    // boundary conditions of the first kind
    A.applyBC(btemperature, B);
}

double ThermalFem2DTriangleSolver::compute(int loops) {
    this->initCalculation();

    fluxes.reset();

    // store boundary conditions for current mesh
    auto btemperature = temperature_boundary(this->mesh, this->geometry);
    auto bheatflux = heatflux_boundary(this->mesh, this->geometry);
    auto bconvection = convection_boundary(this->mesh, this->geometry);
    auto bradiation = radiation_boundary(this->mesh, this->geometry);

    this->writelog(LOG_INFO, "Running thermal calculations");

    int loop = 0;
    size_t size = this->mesh->size();

    std::unique_ptr<FemMatrix> pA(this->getMatrix());
    FemMatrix& A = *pA.get();

    double err;
    toterr = 0.;

#ifndef NDEBUG
    if (!temperatures.unique()) this->writelog(LOG_DEBUG, "Temperature data held by something else...");
#endif
    temperatures = temperatures.claim();

    DataVector<double> B(size), temp0(size);

    do {
        std::copy(temperatures.begin(), temperatures.end(), temp0.begin());

        setMatrix(A, B, btemperature, bheatflux, bconvection, bradiation);
        A.solve(B, temperatures);

        // Update error
        err = 0.;
        maxT = 0.;
        for (auto temp = temperatures.begin(), t = temp0.begin(); t != temp0.end(); ++temp, ++t) {
            double corr = std::abs(*t - *temp);  // for boundary with constant temperature this will be zero anyway
            if (corr > err) err = corr;
            if (*temp > maxT) maxT = *temp;
        }
        if (err > toterr) toterr = err;

        ++loopno;
        ++loop;

        // show max correction
        this->writelog(LOG_RESULT, "Loop {:d}({:d}): max(T) = {:.3f} K, error = {:g} K", loop, loopno, maxT, err);

    } while ((!this->iter_params.converged || err > maxerr) && (loops == 0 || loop < loops));

    outTemperature.fireChanged();
    outHeatFlux.fireChanged();

    return toterr;
}


void ThermalFem2DTriangleSolver::saveHeatFluxes()
{
    this->writelog(LOG_DETAIL, "Computing heat fluxes");

    fluxes.reset(this->mesh->getElementsCount());

    const auto& elems = this->mesh->elements();

    for (size_t elem_idx = 0; elem_idx < elems.size(); ++elem_idx) {
        const auto& elem = elems[elem_idx];

        auto n1_idx = elem.getNodeIndex(0);
        auto n2_idx = elem.getNodeIndex(1);
        auto n3_idx = elem.getNodeIndex(2);

        auto n1 = elem.getNode(0);
        auto n2 = elem.getNode(1);
        auto n3 = elem.getNode(2);

        double d = (n1.ee_x() - n2.ee_x()) * (n2.ee_y() - n3.ee_y()) - (n1.ee_y() - n2.ee_y()) * (n2.ee_x() - n3.ee_x());

        double a1 = (n2.ee_y() - n3.ee_y()) / d;
        double a2 = (n3.ee_y() - n1.ee_y()) / d;
        double a3 = (n1.ee_y() - n2.ee_y()) / d;

        double b1 = (n3.ee_x() - n2.ee_x()) / d;
        double b2 = (n1.ee_x() - n3.ee_x()) / d;
        double b3 = (n2.ee_x() - n1.ee_x()) / d;


        Vec<2, double> midpoint = elem.getMidpoint();
        auto material = this->geometry->getMaterial(midpoint);

        // average temperature on the element
        double temp = (temperatures[n1_idx] + temperatures[n2_idx] + temperatures[n3_idx]) / 3.0;

        double kx, ky;
        std::tie(kx, ky) = std::tuple<double, double>(material->thermk(temp));

        fluxes[elem_idx] = vec(
            - 1e6 * ky * (temperatures[n1_idx] * b1 + temperatures[n2_idx] * b2 + temperatures[n3_idx] * b3),  // 1e6 - from um to m
            - 1e6 * kx * (temperatures[n1_idx] * a1 + temperatures[n2_idx] * a2 + temperatures[n3_idx] * a3)  // 1e6 - from um to m
        );
    }
}


ThermalFem2DTriangleSolver::ThermalConductivityData::ThermalConductivityData(const ThermalFem2DTriangleSolver* solver, const shared_ptr<const MeshD<2>>& dst_mesh):
    solver(solver), dest_mesh(dst_mesh), flags(solver->geometry)
{
    if (solver->temperatures) temps = interpolate(solver->mesh, solver->temperatures, solver->mesh->getElementMesh(), INTERPOLATION_LINEAR);
    else temps = LazyData<double>(solver->mesh->getElementsCount(), solver->inittemp);
}

Tensor2<double> ThermalFem2DTriangleSolver::ThermalConductivityData::at(std::size_t i) const {
    Vec<2, double> pt = dest_mesh->at(i);
    
    auto material = solver->geometry->getMaterial(pt);
    
    double temp = temps[i];
    double kx, ky;
    std::tie(kx, ky) = std::tuple<double, double>(material->thermk(temp));
    
    return Tensor2<double>(kx, ky);
}

std::size_t ThermalFem2DTriangleSolver::ThermalConductivityData::size() const { return dest_mesh->size(); }

const LazyData<Tensor2<double>> ThermalFem2DTriangleSolver::getThermalConductivity(const shared_ptr<const MeshD<2>>& dst_mesh,
                                                                                   InterpolationMethod) {
    this->initCalculation();
    this->writelog(LOG_DEBUG, "Getting thermal conductivities");
    return LazyData<Tensor2<double>>(new ThermalFem2DTriangleSolver::ThermalConductivityData(this, dst_mesh));
}

const LazyData<Vec<2>> ThermalFem2DTriangleSolver::getHeatFluxes(const shared_ptr<const MeshD<2>>& dest_mesh,
                                                                 InterpolationMethod method) {
    this->writelog(LOG_DEBUG, "Getting heat fluxes");
    if (!temperatures)
        return LazyData<Vec<2>>(dest_mesh->size(),
                                Vec<2>(0., 0.));  // in case the receiver is connected and no fluxes calculated yet
    if (!fluxes) saveHeatFluxes();                // we will compute fluxes only if they are needed
    if (method == INTERPOLATION_DEFAULT) method = INTERPOLATION_LINEAR;
    return SafeData<Vec<2>>(
        interpolate(this->mesh->getElementMesh(), fluxes, dest_mesh, method,
                    InterpolationFlags(this->geometry, InterpolationFlags::Symmetry::NP, InterpolationFlags::Symmetry::PN)),
        Zero<Vec<2>>());
}

const LazyData<double> ThermalFem2DTriangleSolver::getTemperatures(const shared_ptr<const MeshD<2>>& dest_mesh,
                                                                   InterpolationMethod method) const {
    this->writelog(LOG_DEBUG, "Getting temperatures");
    if (!temperatures)
        return LazyData<double>(dest_mesh->size(),
                                inittemp);  // in case the receiver is connected and no temperature calculated yet
    if (method == INTERPOLATION_DEFAULT) method = INTERPOLATION_LINEAR;
    return SafeData<double>(interpolate(this->mesh, temperatures, dest_mesh, method, this->geometry), 300.);
}
}}}  // namespace plask::thermal::tstatic
