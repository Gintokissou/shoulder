from functools import partial

import biorbd
import biorbd_casadi
import casadi
import numpy as np
from scipy import integrate


from .enums import ControlsTypes, IntegrationMethods, MuscleParameter
from .helpers import Vector, Scalar, parse_muscle_index, concatenate
from .model_abstract import ModelAbstract


class ModelBiorbd(ModelAbstract):
    def __init__(self, model_path: str, use_casadi: bool = False):
        self._use_casadi = use_casadi
        self.brbd = biorbd_casadi if self._use_casadi else biorbd
        self._model = self.brbd.Model(model_path)

    @property
    def biorbd_model(self) -> biorbd.Model | biorbd_casadi.Model:
        return self._model

    @property
    def name(self) -> str:
        return self._model.path().absolutePath().to_string().split("/")[-1].split(".bioMod")[0]

    @property
    def n_q(self) -> int:
        return self._model.nbQ()

    @property
    def n_muscles(self) -> int:
        return self._model.nbMuscleTotal()

    def muscles_kinematics(
        self, q: Vector, qdot: Vector = None, muscle_index: range | slice | int = None
    ) -> Vector | tuple[Vector, Vector]:
        data_type = type(q)
        if qdot is not None and not isinstance(qdot, data_type):
            raise ValueError("q and qdot must have the same type")

        muscle_index = parse_muscle_index(muscle_index, self.n_muscles)

        n_muscles = len(range(muscle_index.start, muscle_index.stop))
        data_type = type(q)

        lengths = data_type((n_muscles, q.shape[1]))
        velocities = data_type((n_muscles, q.shape[1]))
        for i in range(q.shape[1]):
            if qdot is None:
                self._model.updateMuscles(q[:, i], True)
            else:
                self._model.updateMuscles(q[:, i], qdot[:, i], True)

            for j in range(self._model.nbMuscleTotal()):
                lengths[j, i] = self._model.muscle(j).length(self._model, q[:, i], False)
                if qdot is not None:
                    velocities[j, i] = self._model.muscle(j).velocity(self._model, q[:, i], qdot[:, i], False)

        if qdot is None:
            return lengths
        else:
            return lengths, velocities

    def muscle_force_coefficients(
        self,
        emg: Vector,
        q: Vector,
        qdot: Vector = None,
        muscle_index: int | range | slice | None = None,
    ) -> Vector | tuple[Vector, Vector, Vector]:
        data_type = type(emg)
        if not isinstance(q, data_type) or (qdot is not None and not isinstance(qdot, data_type)):
            raise ValueError("emg, q and qdot must have the same type")

        muscle_index = parse_muscle_index(muscle_index, self.n_muscles)
        if len(q.shape) == 1:
            q = q[:, np.newaxis]
        if qdot is not None and len(qdot.shape) == 1:
            qdot = qdot[:, np.newaxis]

        n_muscles = len(range(muscle_index.start, muscle_index.stop))

        out_flpe = data_type((n_muscles, q.shape[1]))
        out_flce = data_type((n_muscles, q.shape[1]))
        out_fvce = data_type((n_muscles, q.shape[1]))
        for i in range(q.shape[1]):
            if qdot is None:
                self._model.updateMuscles(q[:, i], True)
            else:
                self._model.updateMuscles(q[:, i], qdot[:, i], True)

            for j in range(muscle_index.start, muscle_index.stop):
                mus = self._upcast_muscle(self._model.muscle(j))
                activation = self.brbd.State(emg[j, i], emg[j, i])
                out_flpe[j, i] = mus.FlPE()
                out_flce[j, i] = mus.FlCE(activation)
                if qdot is not None:
                    out_fvce[j, i] = mus.FvCE()

        if qdot is None:
            return out_flpe, out_flce
        else:
            return out_flpe, out_flce, out_fvce

    def muscle_force(
        self, emg: Vector, q: Vector, qdot: Vector, muscle_index: int | range | slice | None = None
    ) -> Vector:
        data_type = type(emg)
        if not isinstance(q, data_type) or not isinstance(qdot, data_type):
            raise ValueError("emg, q and qdot must have the same type")
        if len(emg.shape) == 1:
            emg = emg[:, np.newaxis]

        muscle_index = parse_muscle_index(muscle_index, self.n_muscles)
        if len(q.shape) == 1:
            q = q[:, np.newaxis]
        if len(qdot.shape) == 1:
            qdot = qdot[:, np.newaxis]

        n_muscles = len(range(muscle_index.start, muscle_index.stop))
        muscle_index = list(range(*muscle_index.indices(n_muscles)))

        if data_type == casadi.MX or data_type == casadi.SX:
            out_force = data_type(n_muscles, q.shape[1])
        else:
            out_force = data_type((n_muscles, q.shape[1]))

        for i in range(q.shape[1]):
            if qdot is None:
                self._model.updateMuscles(q[:, i], True)
            else:
                self._model.updateMuscles(q[:, i], qdot[:, i], True)

            for j in range(n_muscles):
                mus = self._upcast_muscle(self._model.muscle(muscle_index[j]))
                activation = self.brbd.State(emg[j, i], emg[j, i])
                force_tp = mus.force(activation)
                if self._use_casadi:
                    force_tp = force_tp.to_mx()
                    if data_type == np.ndarray:
                        force_tp = casadi.Function("force", [], [force_tp], [], ["force"])()["force"]
                out_force[j, i] = force_tp

        return out_force

    def set_muscle_parameters(self, index: int, optimal_length: Scalar) -> None:
        self._model.muscle(index).characteristics().setOptimalLength(optimal_length)

    def get_muscle_parameter(self, index: int, parameter_to_get: MuscleParameter) -> Scalar:
        if parameter_to_get == MuscleParameter.OPTIMAL_LENGTH:
            return self._model.muscle(index).characteristics().optimalLength().to_mx()
        else:
            raise NotImplementedError(f"Parameter {parameter_to_get} not implemented")

    def integrate(
        self,
        t: Vector,
        states: Vector,
        controls: Vector,
        controls_type: ControlsTypes = ControlsTypes.TORQUE,
        integration_method: IntegrationMethods = IntegrationMethods.RK45,
    ) -> tuple[Vector, Vector]:
        data_type = type(states)
        if not isinstance(controls, data_type):
            raise ValueError("states and controls must have the same type")

        func = partial(self.forward_dynamics, tau=controls)

        if controls_type == ControlsTypes.EMG:
            if controls.shape[0] != self.n_muscles:
                raise ValueError(f"EMG controls should have {self.n_muscles} muscles, but got {controls.shape[0]}")
            func = partial(self._forward_dynamics_muscles, emg=controls)
        elif controls_type == ControlsTypes.TORQUE:
            if controls.shape[0] != self.n_q:
                raise ValueError(
                    f"Torque controls should have {self.n_q} generalized coordinates, but got {controls.shape[0]}"
                )
            func = partial(self._forward_dynamics, tau=controls)
        else:
            raise NotImplementedError(f"Control {controls_type} not implemented")

        if integration_method == IntegrationMethods.RK45:
            method = "RK45"
        elif integration_method == IntegrationMethods.RK4:
            method = "RK4"
        else:
            raise NotImplementedError(f"Integration method {integration_method} not implemented")

        t_span = (t[0], t[-1])
        results = integrate.solve_ivp(fun=func, t_span=t_span, y0=states, method=method, t_eval=t)

        q = results.y[: self.n_q, :]
        qdot = results.y[self.n_q :, :]
        return q, qdot

    def forward_dynamics(
        self,
        q: Vector,
        qdot: Vector,
        controls: Vector,
        controls_type: ControlsTypes = ControlsTypes.TORQUE,
    ) -> tuple[Vector, Vector]:
        data_type = type(q)
        if not isinstance(qdot, data_type) or not isinstance(controls, data_type):
            raise ValueError("q, qdot and controls must have the same type")

        if controls_type == ControlsTypes.EMG:
            if controls.shape[0] != self.n_muscles:
                raise ValueError(f"EMG controls should have {self.n_muscles} muscles, but got {controls.shape[0]}")
            func = partial(self._forward_dynamics_muscles, t=[], emg=controls)
        elif controls_type == ControlsTypes.TORQUE:
            if controls.shape[0] != self.n_q:
                raise ValueError(
                    f"Torque controls should have {self.n_q} generalized coordinates, but got {controls.shape[0]}"
                )
            func = partial(self._forward_dynamics, t=[], tau=controls)
        else:
            raise NotImplementedError(f"Control {controls_type} not implemented")

        results = func(x=concatenate(q, qdot))
        q = results[: self.n_q]
        qdot = results[self.n_q :]
        return q, qdot

    def _forward_dynamics_muscles(self, t: float, x: Vector, emg: Vector) -> Vector:
        q = x[: self.n_q]
        qdot = x[self.n_q :]
        states = self._model.stateSet()
        # for k in range(self._model.nbMuscles()):
        #     states[k].setActivation(emg[k])
        tau = self._model.muscularJointTorque(states, q, qdot)
        tau = tau.to_mx() if self._use_casadi else tau.to_array()

        return self._forward_dynamics(t, x, tau)

    def _forward_dynamics(self, t: float, x: Vector, tau: Vector) -> Vector:
        q = x[: self.n_q]
        qdot = x[self.n_q :]
        qddot = self._model.ForwardDynamics(q, qdot, tau)
        qddot = qddot.to_mx() if self._use_casadi else qddot.to_array()

        return concatenate(qdot, qddot)

    def animate(self, states: list[Vector]) -> None:
        import bioviz

        viz = bioviz.Viz(
            loaded_model=self._model,
            show_local_ref_frame=False,
            show_segments_center_of_mass=False,
            show_global_center_of_mass=False,
            show_gravity_vector=False,
        )
        viz.load_movement(states[0])
        viz.set_camera_roll(np.pi / 2)
        viz.exec()

    def _upcast_muscle(
        self, muscle: biorbd.Muscle | biorbd_casadi.Muscle
    ) -> (
        biorbd.HillType
        | biorbd_casadi.HillType
        | biorbd.HillThelenType
        | biorbd_casadi.HillThelenType
        | biorbd.HillDeGrooteType
        | biorbd_casadi.HillDeGrooteType
    ):
        muscle_type_id = muscle.type()
        if muscle_type_id == self.brbd.IDEALIZED_ACTUATOR:
            return self.brbd.IdealizedActuator(muscle)
        elif muscle_type_id == self.brbd.HILL:
            return self.brbd.HillType(muscle)
        elif muscle_type_id == self.brbd.HILL_THELEN:
            return self.brbd.HillThelenType(muscle)
        elif muscle_type_id == self.brbd.HILL_DE_GROOTE:
            return self.brbd.HillDeGrooteType(muscle)
        else:
            raise ValueError(f"Muscle type {muscle_type_id} not supported")
