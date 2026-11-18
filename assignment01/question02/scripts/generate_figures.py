#!/usr/bin/env python3
"""Generate the figures and numeric artifacts used by the PCA slide deck."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
from matplotlib import font_manager
from matplotlib.lines import Line2D


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "wine.data"
ASSETS = ROOT / "assets"
ASSETS.mkdir(parents=True, exist_ok=True)


def set_style() -> None:
    available = {font.name for font in font_manager.fontManager.ttflist}
    chinese = next(
        name
        for name in ("Songti SC", "PingFang SC", "Heiti SC", "Arial Unicode MS")
        if name in available
    )
    plt.rcParams.update(
        {
            "font.family": chinese,
            "font.size": 13,
            "axes.titlesize": 17,
            "axes.labelsize": 14,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.edgecolor": "#3b3b3b",
            "axes.linewidth": 0.8,
            "xtick.color": "#444444",
            "ytick.color": "#444444",
            "text.color": "#202020",
            "figure.facecolor": "white",
            "savefig.facecolor": "white",
        }
    )


def projection_figure() -> None:
    rng = np.random.default_rng(7)
    cov = np.array([[1.0, 0.78], [0.78, 0.72]])
    x = rng.multivariate_normal([0.0, 0.0], cov, size=48)

    eigenvalues, eigenvectors = np.linalg.eigh(cov)
    order = np.argsort(eigenvalues)[::-1]
    eigenvalues = eigenvalues[order]
    eigenvectors = eigenvectors[:, order]
    v1 = eigenvectors[:, 0]
    v2 = eigenvectors[:, 1]

    projections = np.outer(x @ v1, v1)
    scale = 2.8
    axis1 = np.vstack([-scale * np.sqrt(eigenvalues[0]) * v1, scale * np.sqrt(eigenvalues[0]) * v1])
    axis2 = np.vstack([-scale * np.sqrt(eigenvalues[1]) * v2, scale * np.sqrt(eigenvalues[1]) * v2])

    fig, ax = plt.subplots(figsize=(8.2, 5.3), dpi=180)
    ax.scatter(x[:, 0], x[:, 1], s=34, color="#35688f", alpha=0.72, edgecolor="white", linewidth=0.5)

    for point, projected in zip(x[::5], projections[::5]):
        ax.plot(
            [point[0], projected[0]],
            [point[1], projected[1]],
            color="#ef8a35",
            alpha=0.55,
            linewidth=1.0,
            linestyle=(0, (3, 2)),
            zorder=1,
        )
        ax.scatter(projected[0], projected[1], s=28, color="#ef8a35", zorder=3)

    ax.plot(axis1[:, 0], axis1[:, 1], color="#1f1f1f", linewidth=2.6, zorder=2)
    ax.plot(axis2[:, 0], axis2[:, 1], color="#6c6c6c", linewidth=1.6, linestyle="--", zorder=2)
    ax.annotate(
        "",
        xy=axis1[-1],
        xytext=(0, 0),
        arrowprops={"arrowstyle": "-|>", "lw": 2.6, "color": "#1f1f1f"},
    )
    ax.text(-2.65, 2.30, r"$v_1$：最大方差方向", fontsize=12.5,
            bbox={"boxstyle": "round,pad=0.18", "facecolor": "white", "edgecolor": "none", "alpha": 0.9})
    ax.text(1.55, -2.35, r"$v_2$", fontsize=14, color="#666666",
            bbox={"boxstyle": "round,pad=0.15", "facecolor": "white", "edgecolor": "none", "alpha": 0.9})

    ax.set_xlabel(r"原始变量 $x_1$", fontsize=16)
    ax.set_ylabel(r"原始变量 $x_2$", fontsize=16)
    ax.tick_params(axis="both", labelsize=12)
    ax.set_aspect("equal", adjustable="box")
    ax.set_xlim(-3.2, 3.2)
    ax.set_ylim(-2.8, 2.8)
    ax.axhline(0, color="#d8d8d8", linewidth=0.8, zorder=0)
    ax.axvline(0, color="#d8d8d8", linewidth=0.8, zorder=0)
    ax.text(
        0.97,
        0.04,
        "橙色点：样本在主成分上的新坐标",
        transform=ax.transAxes,
        ha="right",
        fontsize=11.5,
        color="#8a4c19",
        bbox={"boxstyle": "round,pad=0.18", "facecolor": "white", "edgecolor": "none", "alpha": 0.9},
    )
    fig.tight_layout()
    fig.savefig(ASSETS / "pca_projection.png", bbox_inches="tight")
    plt.close(fig)



def load_wine() -> tuple[np.ndarray, np.ndarray]:
    data = np.loadtxt(DATA, delimiter=",")
    return data[:, 1:], data[:, 0].astype(int)


def compute_pca(x: np.ndarray) -> dict[str, np.ndarray | float | int]:
    mean = x.mean(axis=0)
    std = x.std(axis=0, ddof=0)
    z = (x - mean) / std
    u, singular_values, vt = np.linalg.svd(z, full_matrices=False)

    # Eigenvectors are defined up to sign. Flip PC1 so high values mean
    # "more phenols/flavanoids", which makes the chemistry easier to read.
    u[:, 0] *= -1
    vt[0] *= -1

    variance = singular_values**2 / (len(z) - 1)
    ratio = variance / variance.sum()
    scores = u * singular_values
    return {
        "mean": mean,
        "std": std,
        "scores": scores,
        "components": vt,
        "ratio": ratio,
        "cumulative": np.cumsum(ratio),
        "singular_values": singular_values,
    }


def scree_figure(ratio: np.ndarray, cumulative: np.ndarray) -> None:
    n_show = 10
    x_axis = np.arange(1, n_show + 1)
    colors = ["#b9c5cd"] * n_show
    colors[0] = "#35688f"
    colors[1] = "#5f8ea9"
    colors[2] = "#ef8a35"

    fig, ax = plt.subplots(figsize=(8.4, 5.0), dpi=180)
    ax.bar(x_axis, ratio[:n_show] * 100, color=colors, width=0.66, zorder=2)
    ax.set_xlabel("主成分编号", fontsize=15)
    ax.set_ylabel("单个主成分解释方差（%）", color="#35688f", fontsize=15)
    ax.tick_params(axis="both", labelsize=12)
    ax.tick_params(axis="y", labelcolor="#35688f")
    ax.set_xticks(x_axis)
    ax.set_ylim(0, 39)

    ax2 = ax.twinx()
    ax2.plot(x_axis, cumulative[:n_show] * 100, color="#c9493f", marker="o", linewidth=2.2, zorder=3)
    ax2.set_ylabel("累计解释方差（%）", color="#c9493f", fontsize=15)
    ax2.tick_params(axis="y", labelsize=12, labelcolor="#c9493f")
    ax2.set_ylim(0, 103)
    ax2.spines["top"].set_visible(False)

    k3 = cumulative[2] * 100
    ax2.axvline(3, color="#ef8a35", linewidth=1.3, linestyle="--", alpha=0.9)
    ax2.scatter([3], [k3], s=75, color="#ef8a35", edgecolor="white", linewidth=1.5, zorder=5)
    ax2.annotate(
        f"k = 3：累计 {k3:.2f}%",
        xy=(3, k3),
        xytext=(4.1, k3 - 8),
        arrowprops={"arrowstyle": "->", "color": "#8a4c19", "lw": 1.2},
        color="#8a4c19",
        fontsize=13,
    )
    ax.grid(axis="y", color="#e9e9e9", linewidth=0.7, zorder=0)
    fig.tight_layout()
    fig.savefig(ASSETS / "pca_scree.png", bbox_inches="tight")
    plt.close(fig)


def scores_figure(scores: np.ndarray, labels: np.ndarray, ratio: np.ndarray, selected: list[int]) -> None:
    palette = {1: "#c9493f", 2: "#35688f", 3: "#3d8a6a"}
    class_names = {1: "品种 1", 2: "品种 2", 3: "品种 3"}

    fig = plt.figure(figsize=(8.4, 5.8), dpi=180)
    ax = fig.add_subplot(111, projection="3d")
    for cls in (1, 2, 3):
        mask = labels == cls
        ax.scatter(
            scores[mask, 0],
            scores[mask, 1],
            scores[mask, 2],
            s=28,
            alpha=0.72,
            color=palette[cls],
            edgecolor="white",
            linewidth=0.25,
            depthshade=False,
            label=class_names[cls],
        )

    label_offsets = {
        "A": (-0.60, 0.35, 0.70),
        "B": (0.35, -0.65, 0.60),
        "C": (0.70, 0.45, 0.70),
    }
    for index, letter in zip(selected, ("A", "B", "C")):
        row = scores[index]
        dx, dy, dz = label_offsets[letter]
        ax.scatter(row[0], row[1], row[2], s=130, color="#ef8a35", edgecolor="#202020", linewidth=1.4, depthshade=False)
        ax.text(
            row[0] + dx,
            row[1] + dy,
            row[2] + dz,
            f"{letter}\n({row[0]:.2f}, {row[1]:.2f}, {row[2]:.2f})",
            fontsize=10.5,
            color="#202020",
            bbox={"boxstyle": "round,pad=0.18", "facecolor": "white", "edgecolor": "none", "alpha": 0.88},
            zorder=12,
        )

    ax.set_xlabel(f"PC1 ({ratio[0] * 100:.1f}%)", labelpad=10, fontsize=16)
    ax.set_ylabel(f"PC2 ({ratio[1] * 100:.1f}%)", labelpad=10, fontsize=16)
    ax.set_zlabel(f"PC3 ({ratio[2] * 100:.1f}%)", labelpad=10, fontsize=16)
    ax.tick_params(axis="both", labelsize=10)
    ax.view_init(elev=23, azim=-56)
    ax.legend(loc="upper left", frameon=False, fontsize=13)
    ax.grid(True, color="#e7e7e7", linewidth=0.6)
    ax.xaxis.pane.set_facecolor("white")
    ax.yaxis.pane.set_facecolor("white")
    ax.zaxis.pane.set_facecolor("white")
    ax.xaxis.pane.set_edgecolor("#e0e0e0")
    ax.yaxis.pane.set_edgecolor("#e0e0e0")
    ax.zaxis.pane.set_edgecolor("#e0e0e0")
    fig.tight_layout()
    fig.savefig(ASSETS / "pca_scores_3d.png", bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    set_style()
    projection_figure()

    x, labels = load_wine()
    result = compute_pca(x)
    scores = result["scores"]
    components = result["components"]
    ratio = result["ratio"]
    cumulative = result["cumulative"]

    scree_figure(ratio, cumulative)

    # Pick one representative point near the centroid of each cultivar.
    selected: list[int] = []
    for cls in (1, 2, 3):
        members = np.flatnonzero(labels == cls)
        class_scores = scores[members, :3]
        center = class_scores.mean(axis=0)
        nearest = members[np.argmin(np.sum((class_scores - center) ** 2, axis=1))]
        selected.append(int(nearest))

    scores_figure(scores, labels, ratio, selected)

    feature_names = [
        "Alcohol",
        "Malic acid",
        "Ash",
        "Alcalinity of ash",
        "Magnesium",
        "Total phenols",
        "Flavanoids",
        "Nonflavanoid phenols",
        "Proanthocyanins",
        "Color intensity",
        "Hue",
        "OD280/OD315",
        "Proline",
    ]
    selected_rows = []
    for index, letter in zip(selected, ("A", "B", "C")):
        selected_rows.append(
            {
                "letter": letter,
                "sample_index": index + 1,
                "class": int(labels[index]),
                "original_13d": [round(float(value), 3) for value in x[index]],
                "score_3d": [round(float(value), 4) for value in scores[index, :3]],
            }
        )

    metrics = {
        "dataset": "UCI Wine",
        "samples": int(x.shape[0]),
        "features": int(x.shape[1]),
        "explained_variance_ratio": [round(float(value), 6) for value in ratio],
        "cumulative_3pc": round(float(cumulative[2]), 6),
        "reconstruction_error_3pc": round(float(1.0 - cumulative[2]), 6),
        "selected_samples": selected_rows,
        "loadings_first_three": {
            f"PC{i + 1}": {
                name: round(float(components[i, j]), 6)
                for j, name in enumerate(feature_names)
            }
            for i in range(3)
        },
        "feature_names": feature_names,
    }
    (ROOT / "pca_metrics.json").write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(metrics, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
