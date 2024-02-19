from enum import Enum, auto

import bioviz
import numpy as np
from matplotlib import pyplot as plt

from .model import Model


class Animater:
    def __init__(self, model: Model, q: np.ndarray):
        self._viz = bioviz.Viz(
            loaded_model=model.model,
            show_local_ref_frame=False,
            show_segments_center_of_mass=False,
            show_global_center_of_mass=False,
            show_gravity_vector=False,
        )
        self._viz.load_movement(q)
        self._viz.set_camera_roll(np.pi / 2)

    def show(self):
        self._viz.exec()


class Plotter:
    class XAxis(Enum):
        TIME = auto()
        MUSCLE_PARAMETERS = auto()
        KINEMATICS = auto()

    def __init__(
        self,
        model: Model,
        t: np.ndarray = None,
        q: np.ndarray = None,
        qdot: np.ndarray = None,
        tau: np.ndarray = None,
        emg: np.ndarray = None,
        muscle_index: int | range | slice | None = None,
        dof_index: int | range | slice | None = None,
    ):

        # Store the data
        self._model = model
        self._t = t
        self._q = q
        self._qdot = qdot
        self._tau = tau
        self._emg = emg
        self._muscle_index = muscle_index
        self._dof_index = dof_index

    def plot_muscle_force_coefficients_surface(self, axis_id: int):
        if self._q is None or self._qdot is None or self._emg is None:
            raise ValueError("q, qdot and emg must be provided to plot the muscle force coefficients surface")

        # Draw the surface of the force-length-velocity relationship for each model
        fig = plt.figure("Force-Length-Velocity relationship")
        length, velocity = self._model.muscles_kinematics(self._q, self._qdot)

        x, y = np.meshgrid(self._q[self._dof_index, :], self._qdot[self._dof_index, :])
        z = np.ndarray((velocity.shape[1], length.shape[1]))

        for i in range(length.shape[1]):
            q_rep = np.repeat(self._q[:, i : i + 1], self._qdot.shape[1], axis=1)
            flce, fvce = self._model.muscle_force_coefficients(self._emg, q_rep, self._qdot, self._muscle_index)
            z[:, i] = flce * fvce

        ax = fig.add_subplot(axis_id, projection="3d")
        ax.plot_surface(x, y, z, cmap="viridis")
        ax.set_xlabel("Length")
        ax.set_ylabel("Velocity")
        ax.set_zlabel("Force")
        ax.set_title(self._model.name)

    def plot_muscle_force_surface(self, axis_id: int):
        if self._q is None or self._qdot is None or self._emg is None:
            raise ValueError("q, qdot and emg must be provided to plot the muscle force surface")

        # Draw the surface of the force-length-velocity relationship for each model
        fig = plt.figure("Force-Length-Velocity relationship")
        length, velocity = self._model.muscles_kinematics(self._q, self._qdot)

        x, y = np.meshgrid(self._q[self._dof_index, :], self._qdot[self._dof_index, :])
        z = np.ndarray((velocity.shape[1], length.shape[1]))

        for i in range(length.shape[1]):
            q_rep = np.repeat(self._q[:, i : i + 1], self._qdot.shape[1], axis=1)
            flce, fvce = self._model.muscle_force_coefficients(self._emg, q_rep, self._qdot, self._muscle_index)
            z[:, i] = flce * fvce

        ax = fig.add_subplot(axis_id, projection="3d")
        ax.plot_surface(x, y, z, cmap="viridis")
        ax.set_xlabel("Length")
        ax.set_ylabel("Velocity")
        ax.set_zlabel("Force")
        ax.set_title(self._model.name)

    def plot_movement(self):
        if self._t is None:
            raise ValueError("t must be provided to plot the movement")

        plt.figure()
        n_subplots = sum(x is not None for x in [self._q, self._qdot, self._tau, self._emg])
        subplot_index = 1

        if self._q is not None:
            plt.subplot(n_subplots, 1, subplot_index)
            plt.plot(self._t, self._q.T)
            plt.title("Position")
            plt.xlabel("Time")
            plt.ylabel("Q")
            subplot_index += 1

        if self._qdot is not None:
            plt.subplot(n_subplots, 1, subplot_index)
            plt.plot(self._t, self._qdot.T)
            plt.title("Velocity")
            plt.xlabel("Time")
            plt.ylabel("Qdot")
            subplot_index += 1

        if self._tau is not None:
            plt.subplot(n_subplots, 1, subplot_index)
            plt.step(self._t[[0, -1]], self._tau[np.newaxis, :][[0, 0], :])
            plt.title("Torque")
            plt.xlabel("Time")
            plt.ylabel("Tau")
            subplot_index += 1

        if self._emg is not None:
            plt.subplot(n_subplots, 1, subplot_index)
            plt.step(self._t[[0, -1]], self._emg[np.newaxis, :][[0, 0], :])
            plt.title("EMG")
            plt.xlabel("Time")
            plt.ylabel("EMG")

    @staticmethod
    def show():
        plt.show()

    def plot_muscle_force_coefficients(self, x_axes: list["Plotter.XAxes"], color: str, plot_right_axis: bool = True):
        title = []
        title.append("Force-Length relationship (Time)")
        title.append("Force-Velocity relationship (Time)")

        flce, fvce = self._model.muscle_force_coefficients(
            self._emg, self._q, self._qdot, muscle_index=self._muscle_index
        )
        y_left = []
        y_left.append(flce)
        y_left.append(fvce)

        length, velocity = self._model.muscles_kinematics(self._q, self._qdot, self._muscle_index)
        y_right = []
        y_right.append(length)
        y_right.append(velocity)

        y_right_label = []
        y_right_label.append("Muscle length")
        y_right_label.append("Muscle velocity")
        y_right_color = "g"
        for x_axis in x_axes:
            x = []
            x_label = []
            if x_axis == Plotter.XAxis.TIME:
                x.append(self._t)
                x_label.append("Time (s)")

                x.append(self._t)
                x_label.append("Time (s)")

            elif x_axis == Plotter.XAxis.MUSCLE_PARAMETERS:
                x.append(length[0, :])
                x_label.append("Muscle length")

                x.append(velocity[0, :])
                x_label.append("Muscle velocity")

            elif x_axis == Plotter.XAxis.KINEMATICS:
                x.append(self._q[self._dof_index, :])
                x_label.append("q")

                x.append(self._qdot[self._dof_index, :])
                x_label.append("qdot")

            else:
                raise NotImplementedError(f"X axis {x_axis} not implemented")

            for j in range(len(y_left)):
                plt.figure(title[j])
                for i in range(len(x[j])):
                    n_points = x[j].shape[0]
                    plt.plot(x[j], y_left[j].T, f"{color}o", alpha=i / n_points, label=self._model.name)

                plt.legend(loc="upper left")
                plt.xlabel(x_label[j])
                plt.ylabel("Force (normalized)")

                if plot_right_axis:
                    # On the right axis, plot the muscle length
                    plt.twinx()
                    plt.plot(x[j], y_right[j].T, f"{y_right_color}o", alpha=i / n_points, label=y_right_label[j])
                    plt.legend(loc="upper right")
                    plt.ylabel(y_right_label[j])