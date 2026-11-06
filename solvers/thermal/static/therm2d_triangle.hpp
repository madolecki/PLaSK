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

namespace plask { namespace thermal { namespace tstatic {

class PLASK_SOLVER_API ThermalFem2DTriangleSolver : public FemSolverWithMesh<Geometry2DCartesian, TriangularMesh2D> {
  protected:
    int loopno;
    DataVector<double> temperatures;

    /// Setup matrix
    void makeMatrix();

    /// Initialize the solver
    void onInitialize();

    /// Invalidate the data
    void onInvalidate();

  public:
    ThermalFem2DTriangleSolver(const std::string& name = "");
    std::string getClassName() const;

    double compute(int loops = 1);

    // providers
    //ProviderFor<Temperature, Geometry2DCartesian>::Delegate outTemperature;
    //ProviderFor<HeatFlux, Geometry2DCartesian>::Delegate outHeatFlux;
    //ProviderFor<ThermalConductivity, Geometry2DCartesian>::Delegate outThermalConductivity;

    // receivers
    //ReceiverFor<Heat, Geometry2DCartesian> inHeat;

    ~ThermalFem2DTriangleSolver();
};

}}}  // namespace plask::thermal::tstatic

#endif
