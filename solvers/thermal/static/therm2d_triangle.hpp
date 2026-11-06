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
#ifndef PLASK__MODULE_THERMAL_THERM2D_TRI_H
#define PLASK__MODULE_THERMAL_THERM2D_TRI_H

#include <plask/common/fem.hpp>
#include <plask/plask.hpp>

#include "common.hpp"
#include "plask/mesh/triangular2d.hpp"

namespace plask { namespace thermal { namespace tstatic {

class PLASK_SOLVER_API ThermalFem2DTriangleSolver : public FemSolverWithMesh<Geometry2DCartesian, TriangularMesh2D> {
  protected:
    int loopno;     ///< Number of completed loops
    double maxT;    ///< Maximum temperature recorded
    double toterr;  ///< Maximum estimated error during all iterations (useful for single calculations managed by external python
                    ///< script)
    DataVector<double> temperatures;    ///< Computed temperatures
    DataVector<Vec<2, double>> fluxes;  ///< Computed (only when needed) heat fluxes on our own mesh

    void makeMatrix();

    // HACK: method for creating FemMatrix based on the mesh
    FemMatrix* getMatrix();

    /// Setup matrix
    void setMatrix(FemMatrix& A,
                   DataVector<double>& B,
                   const BoundaryConditionsWithMesh<TriangularMesh2D::Boundary, double>& btemperature,
                   const BoundaryConditionsWithMesh<TriangularMesh2D::Boundary, double>& bheatflux,
                   const BoundaryConditionsWithMesh<TriangularMesh2D::Boundary, Convection>& bconvection,
                   const BoundaryConditionsWithMesh<TriangularMesh2D::Boundary, Radiation>& bradiation);

    /// Initialize the solver
    void onInitialize();

    /// Create 2D-vector with calculated heat fluxes
    void saveHeatFluxes();  // [W/m^2]

    /// Invalidate the data
    void onInvalidate();

  public:
    // Boundary conditions
    BoundaryConditions<TriangularMesh2D::Boundary, double>
        temperature_boundary;  ///< Boundary condition of constant temperature (K)
    BoundaryConditions<TriangularMesh2D::Boundary, double>
        heatflux_boundary;  ///< Boundary condition of constant heat flux [W/m^2]
    BoundaryConditions<TriangularMesh2D::Boundary, Convection> convection_boundary;  ///< Boundary condition of convection
    BoundaryConditions<TriangularMesh2D::Boundary, Radiation> radiation_boundary;    ///< Boundary condition of radiation

    double maxerr;    ///< Maximum residual error accepted as convergence
    double inittemp;  ///< Initial temperature

    ThermalFem2DTriangleSolver(const std::string& name = "");
    std::string getClassName() const;

    double compute(int loops = 1);

    /// Get max absolute correction for temperature
    double getErr() const { return toterr; }

    // providers
    ProviderFor<Temperature, Geometry2DCartesian>::Delegate outTemperature;
    ProviderFor<HeatFlux, Geometry2DCartesian>::Delegate outHeatFlux;
    ProviderFor<ThermalConductivity, Geometry2DCartesian>::Delegate outThermalConductivity;

    // receivers
    ReceiverFor<Heat, Geometry2DCartesian> inHeat;

    // getters
    struct ThermalConductivityData : public LazyDataImpl<Tensor2<double>> {
        const ThermalFem2DTriangleSolver* solver;
        shared_ptr<const MeshD<2>> dest_mesh;
        InterpolationFlags flags;
        LazyData<double> temps;
        ThermalConductivityData(const ThermalFem2DTriangleSolver* solver, const shared_ptr<const MeshD<2>>& dst_mesh);
        Tensor2<double> at(std::size_t i) const override;
        std::size_t size() const override;
    };
    const LazyData<double> getTemperatures(const shared_ptr<const MeshD<2>>& dest_mesh, InterpolationMethod method) const;
    const LazyData<Vec<2>> getHeatFluxes(const shared_ptr<const MeshD<2>>& dest_mesh, InterpolationMethod method);
    const LazyData<Tensor2<double>> getThermalConductivity(const shared_ptr<const MeshD<2>>& dest_mesh, InterpolationMethod method);

    ~ThermalFem2DTriangleSolver();
};

}}}  // namespace plask::thermal::tstatic

#endif
