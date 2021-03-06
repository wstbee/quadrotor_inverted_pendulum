# -*- coding: utf8 -*-
#!/usr/bin/env python
__author__ = "Gilhyun Ryou and Seong Ho Yeon"
__email__ = "ghryou@mit.edu, syeon@mit.edu"

import math
import numpy as np

from pydrake.all import (
    DiagramBuilder,
    Simulator,
    SignalLogger,
    VectorSystem,
    LeafSystem, BasicVector,
    PortDataType
    )

# Define a system to calculate the continuous dynamics
# of the quadrotor pendulum.
# 
# This class takes as input the physical description
# of the system, in terms of the center of mass of 
# the drone (mb with body lenght lb) and the first
# link (m1 centered at l1).
class QuadrotorPendulum(VectorSystem):
    def __init__(self, mb = 1., lb = 0.2, 
                       m1 = 2., l1 = 0.2,
                       g = 10., input_max = 10.):
        VectorSystem.__init__(self,
            2,                           # Two input (thrust of each rotor).
            8)                           # Eight outputs (xb, yb, thetab, theta1) and its derivatives
        self._DeclareContinuousState(8)  # Eight states (xb, yb, thetab, theta1) and its derivatives.

        self.mb = float(mb)
        self.lb = float(lb)
        self.m1 = float(m1)
        self.l1 = float(l1)
        self.g = float(g)
        self.input_max = float(input_max)

        # Go ahead and calculate rotational inertias.
        # Treat the drone as a rectangle.
        self.Ib = 1. / 3. * self.mb * self.lb ** 2
        # Treat the first link as a line.
        self.I1 = 1. / 3. * self.m1 * self.l1 ** 2

    # This method returns (M, C, tauG, B)
    # according to the dynamics of this system.
    def GetManipulatorDynamics(self, q, qd):
        M = np.array(
            [[self.mb + self.m1, 0., 0., self.m1*self.l1*math.cos(q[3])],
             [0., self.mb + self.m1, 0., self.m1*self.l1*math.sin(q[3])],
             [0., 0., self.Ib, 0.],
             [self.m1*self.l1*math.cos(q[3]), self.m1*self.l1*math.sin(q[3]), 0., self.I1 + self.m1*self.l1**2]])
        
        C = np.array(
            [[0., 0., 0., -self.m1*self.l1*math.sin(q[3])*qd[3]],
             [0., 0., 0., self.m1*self.l1*math.cos(q[3])*qd[3]],
             [0., 0., 0., 0.],
             [0., 0., 0., 0.]])
        
        tauG = np.array(
            [[0.],
             [-(self.m1+self.mb)*self.g],
             [0.],
             [-self.m1*self.l1*self.g*math.sin(q[3])]])
        
        B = np.array(
            [[-math.sin(q[2]), -math.sin(q[2])],
             [math.cos(q[2]), math.cos(q[2])],
             [-self.lb, self.lb],
             [0., 0.]])
        
        return (M, C, tauG, B)

    # This helper uses the manipulator dynamics to evaluate
    # \dot{x} = f(x, u). It's just a thin wrapper around
    # the manipulator dynamics. If throw_when_limits_exceeded
    # is true, this function will throw a ValueError when
    # the input limits are violated. Otherwise, it'll clamp
    # u to the input range.
    def evaluate_f(self, u, x, throw_when_limits_exceeded=False):
        # Bound inputs
        if throw_when_limits_exceeded and abs(u[0]) > self.input_max:
            raise ValueError("You commanded an out-of-range input of u=%f" % (u[0]))
        else:
            u[0] = max(-self.input_max, min(self.input_max, u[0]))
        
        if throw_when_limits_exceeded and abs(u[1]) > self.input_max:
            raise ValueError("You commanded an out-of-range input of u=%f" % (u[1]))
        else:
            u[1] = max(-self.input_max, min(self.input_max, u[1]))

        # Use the manipulator equation to get qdd.
        q = x[0:4]
        qd = x[4:8]
        (M, C, tauG, B) = self.GetManipulatorDynamics(q, qd)

        # Awkward slice required on tauG to get shapes to agree --
        # numpy likes to collapse the other dot products in this expression
        # to vectors.
        qdd = np.dot(np.linalg.inv(M), (tauG[:, 0] + np.dot(B, u) - np.dot(C, qd)))

        return np.hstack([qd, qdd])


    # This method calculates the time derivative of the state,
    # which allows the system to be simulated forward in time.
    def _DoCalcVectorTimeDerivatives(self, context, u, x, xdot):
        q = x[0:4]
        qd = x[4:8]
        xdot[:] = self.evaluate_f(u, x, throw_when_limits_exceeded=False)

    # This method calculates the output of the system
    # (i.e. those things that are visible downstream of
    # this system) from the state. In this case, it
    # copies out the full state.
    def _DoCalcVectorOutput(self, context, u, x, y):
        y[:] = x

    # The Drake simulation backend is very careful to avoid
    # algebraic loops when systems are connected in feedback.
    # This system does not feed its inputs directly to its
    # outputs (the output is only a function of the state),
    # so we can safely tell the simulator that we don't have
    # any direct feedthrough.
    def _DoHasDirectFeedthrough(self, input_port, output_port):
        if input_port == 0 and output_port == 0:
            return False
        else:
            # For other combinations of i/o, we will return
            # "None", i.e. "I don't know."
            return None

    # The method return matrices (A) and (B) that encode the
    # linearized dynamics of this system around the fixed point
    # u_f, x_f.
    def GetLinearizedDynamics(self, u_f, x_f):
        q = x_f[0:4]
        qd = x_f[4:8]

        ###### TODO ######
        A = np.zeros((8, 8))
        B = np.zeros((8, 2))
        C = np.zeros((8, 1))
        
        alpha = self.m1*self.l1/(self.m1+self.mb)
        I = self.I1 + self.m1*self.mb*self.l1**2/(self.m1+self.mb)
        
        B[4,0] = -1/(self.m1+self.mb)*math.sin(q[2]) + alpha**2/I*math.cos(q[3])*math.sin(q[3]-q[2])
        B[4,1] = B[4,0]
        
        B[5,0] = (self.I1+self.m1*self.l1**2)/(self.m1+self.mb)/I*math.cos(q[2]) - alpha**2/I*math.cos(q[3])*math.cos(q[3]-q[2])
        B[5,1] = B[5,0]
        
        B[6,0] = -self.lb/self.Ib
        B[6,1] = self.lb/self.Ib
        
        B[7,0] = -alpha/I*math.sin(q[3]-q[2])
        B[7,1] = -alpha/I*math.sin(q[3]-q[2])
        
        A[:4,4:] = np.diag(np.ones(4))
        
        A[4,2] = (-1/(self.m1+self.mb)*math.cos(q[2])-alpha**2/I*math.cos(q[3])*math.cos(q[3]-q[2]))*(u_f[0]+u_f[1])
        A[5,2] = (-(self.I1+self.m1*self.l1**2)/(self.m1+self.mb)/I*math.sin(q[2])-alpha**2/I*math.cos(q[3])*math.sin(q[3]-q[2]))*(u_f[0]+u_f[1])
        
        A[4,3] = alpha*math.cos(q[3])*qd[3]**2+alpha**2/I*math.cos(2.*q[3]-q[2])*(u_f[0]+u_f[1])
        A[5,3] = alpha*math.sin(q[3])*qd[3]**2+alpha**2/I*math.sin(2.*q[3]-q[2])*(u_f[0]+u_f[1])
        A[4,7] = 2.*alpha*math.sin(q[3])*qd[3]
        A[5,7] = -2.*alpha*math.cos(q[3])*qd[3]

        A[7,2] = alpha/I*math.cos(q[3]-q[2])*(u_f[0]+u_f[1])
        A[7,3] = -alpha/I*math.cos(q[3]-q[2])*(u_f[0]+u_f[1])
        
        C[4] = alpha*math.sin(q[3])*qd[3]**2+(-1/(self.m1+self.mb)*math.sin(q[2]) + alpha**2/I*math.cos(q[3])*math.sin(q[3]-q[2]))*(u_f[0]+u_f[1])
        C[5] = -alpha*math.cos(q[3])*qd[3]**2-self.g+((self.I1+self.m1*self.l1**2)/(self.m1+self.mb)/I*math.cos(q[2])-alpha**2/I*math.cos(q[3])*math.cos(q[3]-q[2]))*(u_f[0]+u_f[1])
        C[6] = (-u_f[0]+u_f[1])/self.Ib
        C[7] = -alpha/I*math.sin(q[3]-q[2])*(u_f[0]+u_f[1])
        
        return (A, B)


class QuadrotorController(LeafSystem):
    
    def __init__(self, feedback_rule,
                 control_period = 0.0333,
                 print_period = 1.0):
        
        LeafSystem.__init__(self)
        
        self.feedback_rule = feedback_rule
        self.print_period = print_period
        self.control_period = control_period
        self.last_print_time = -print_period
        
        self.DeclareInputPort(PortDataType.kVectorValued,8)
        self.DeclareDiscreteState(2)
        self.DeclarePeriodicDiscreteUpdate(period_sec=control_period)
        self.DeclareVectorOutputPort(BasicVector(2), self.DoCalcVectorOutput)
    
    def DoCalcDiscreteVariableUpdates(self, context, events, discrete_state):
        # Call base method to ensure we do not get recursion.
        LeafSystem.DoCalcDiscreteVariableUpdates(self, context, events, discrete_state)

        new_control_input = discrete_state.get_mutable_vector().get_mutable_value()
        x = self.EvalVectorInput(context, 0).get_value()
        old_u = new_control_input
        new_u = self.feedback_rule(x, context.get_time())
        new_control_input[:] = new_u

    def DoCalcVectorOutput(self, context, y_data):
        if (self.print_period and
                context.get_time() - self.last_print_time
                >= self.print_period):
            self.last_print_time = context.get_time()
        control_output = context.get_discrete_state_vector().get_value()
        y = y_data.get_mutable_value()
        y[:] = control_output
        

def RunSimulation(quadrotor_plant, control_law, x0=np.random.random((8, 1)), 
                  duration=30, control_period = 0.0333, print_period = 1.0, simulation_period = 0.0333):
    
    quadrotor_controller = QuadrotorController(control_law,
                 control_period = control_period,
                 print_period = print_period)

    # Create a simple block diagram containing the plant in feedback
    # with the controller.
    builder = DiagramBuilder()
    # The last pendulum plant we made is now owned by a deleted
    # system, so easiest path is for us to make a new one.
    plant = builder.AddSystem(QuadrotorPendulum(
        mb = quadrotor_plant.mb,
        lb = quadrotor_plant.lb, 
        m1 = quadrotor_plant.m1, 
        l1 = quadrotor_plant.l1,
        g = quadrotor_plant.g, 
        input_max = quadrotor_plant.input_max))

    controller = builder.AddSystem(quadrotor_controller)
    builder.Connect(plant.get_output_port(0), controller.get_input_port(0))
    builder.Connect(controller.get_output_port(0), plant.get_input_port(0))

    # Create a logger to capture the simulation of our plant
    input_log = builder.AddSystem(SignalLogger(2))
    input_log._DeclarePeriodicPublish(control_period, 0.0)

    builder.Connect(controller.get_output_port(0), input_log.get_input_port(0))

    state_log = builder.AddSystem(SignalLogger(8))
    state_log._DeclarePeriodicPublish(control_period, 0.0)

    builder.Connect(plant.get_output_port(0), state_log.get_input_port(0))

    diagram = builder.Build()

    # Set the initial conditions for the simulation.
    context = diagram.CreateDefaultContext()
    state = context.get_mutable_continuous_state_vector()
    state.SetFromVector(x0)

    # Create the simulator.
    simulator = Simulator(diagram, context)
    simulator.Initialize()
    simulator.set_publish_every_time_step(True)

    simulator.get_integrator().set_fixed_step_mode(True)
    simulator.get_integrator().set_maximum_step_size(control_period)

    # Simulate for the requested duration.
    simulator.StepTo(duration)

    return input_log, state_log