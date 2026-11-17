import sys
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

# modo: "slide" (1920x1080 px) o "informe" (18,2 x 10 cm a 300 dpi)
MODE = sys.argv[1]
OUT = sys.argv[2]
plt.rcParams["font.family"] = "DejaVu Sans"

if MODE == "slide":
    W_IN, H_IN, DPI = 19.2, 10.8, 100
    X0, X1 = 0, 1920
else:
    W_IN, H_IN, DPI = 18.2 / 2.54, 10 / 2.54, 300
    X0, X1 = -22, 1942   # misma altura 1080, un poco mas ancho para la proporcion 18,2 x 10
S = W_IN / 19.2          # escala de tipografia y trazos respecto a la version slide

fig = plt.figure(figsize=(W_IN, H_IN), dpi=DPI)
ax = fig.add_axes([0, 0, 1, 1])
ax.set_xlim(X0, X1)
ax.set_ylim(1080, 0)
ax.axis("off")

BLUE, GREEN, ORANGE, INK = "#1f5faa", "#2a7d34", "#b8540f", "#1a1a1a"
F_TITLE, F_BODY, F_LAB, F_LEG = 22 * S, 17.5 * S, 16.5 * S, 19 * S


def box(x, y, w, h, title, body, fill, dotted=False, tscale=1.0):
    ax.add_patch(FancyBboxPatch(
        (x, y), w, h, boxstyle="round,pad=0,rounding_size=26",
        fc=fill, ec=INK, lw=2.4 * S * 1.0 if MODE == "slide" else 2.4 * S * 1.0,
        ls=(0, (1.5, 2)) if dotted else "-"))
    ax.text(x + w / 2, y + 40, title, ha="center", va="center",
            fontsize=F_TITLE * tscale, fontweight="bold", color=INK)
    ax.text(x + w / 2, y + 52 + (h - 52) / 2 + 6, body, ha="center", va="center",
            fontsize=F_BODY, color=INK, linespacing=1.28)


def arrow(p, q, color, ls="-", rad=0.0, lw=3.2):
    ax.annotate("", xy=q, xytext=p, arrowprops=dict(
        arrowstyle="-|>", lw=lw * S, color=color, ls=ls, shrinkA=0, shrinkB=0,
        mutation_scale=24 * S, connectionstyle=f"arc3,rad={rad}"))


def label(x, y, t, color, ha="center"):
    ax.text(x, y, t, ha=ha, va="center", fontsize=F_LAB, fontweight="bold", color=color)


# leyenda
for x, color, ls, txt in ((36, BLUE, "-", "tráfico de la aplicación"),
                          (652, GREEN, (0, (4, 2)), "monitoreo (Datadog Agent)"),
                          (1286, ORANGE, (0, (6, 2.5, 1.2, 2.5)), "carga de prueba (Artillery)")):
    ax.plot([x, x + 120], [62, 62], color=color, ls=ls, lw=4 * S)
    ax.text(x + 136, 62, txt, ha="left", va="center", fontsize=F_LEG, color=INK)

# red Docker (ahora incluye a Artillery)
ax.add_patch(FancyBboxPatch((338, 130), 1260, 915, boxstyle="round,pad=0,rounding_size=34",
                            fc="none", ec="#555555", lw=2.4 * S, ls=(0, (5, 3))))
ax.text(372, 166, "Red Docker cluster-net", ha="left", va="center",
        fontsize=F_TITLE * 0.95, fontweight="bold", color="#555555")

# nodos
box(24, 265, 300, 185, "Usuario", "navegador\nlocalhost:8080", "#e8f0fb")
box(478, 300, 342, 312, "haproxy",
    "HAProxy 2.6\nfe_web :8080\nroundrobin\nfe_stats :8404\nGET /health cada 1 s", "#e8f0fb")
for i, y in enumerate((178, 400, 622)):
    box(960, y, 280, 174, f"backend{i+1}", ":5000\nFlask + Gunicorn", "#e8f0fb")
box(1338, 380, 222, 204, "db", "PostgreSQL 17", "#eef1e0")
box(1655, 420, 250, 300, "Datadog", "nube\ndashboard\n3 monitores\naviso por correo", "#f1f1f1")
box(606, 668, 250, 150, "haproxy-socket", "volumen\nadmin.sock", "#fdf5da", dotted=True, tscale=0.82)
box(366, 700, 200, 215, "artillery", "Artillery 2.0.34\nperfil\ntools", "#fbeee1")
box(878, 858, 410, 160, "datadog-agent", "Agent 7.85.1\nlogs de los contenedores", "#e8f3e8")

# tráfico de la aplicación
arrow((324, 358), (474, 402), BLUE)
for y in (265, 487, 709):
    pass
arrow((822, 456), (956, 262), BLUE)
arrow((822, 458), (956, 486), BLUE)
arrow((822, 460), (956, 708), BLUE)
arrow((1242, 270), (1334, 474), BLUE, lw=2.4)
arrow((1242, 488), (1334, 482), BLUE, lw=2.4)
arrow((1242, 706), (1334, 500), BLUE, lw=2.4)

# carga de prueba
arrow((466, 700), (492, 614), ORANGE, ls=(0, (6, 2.5, 1.2, 2.5)))
label(400, 650, ":8080", ORANGE, ha="center")
arrow((568, 892), (874, 940), ORANGE, ls=(0, (6, 2.5, 1.2, 2.5)))
label(722, 985, "DogStatsD :8125", ORANGE)

# monitoreo
arrow((730, 614), (730, 664), GREEN, ls=(0, (4, 2)), lw=2.6)
arrow((880, 882), (860, 812), GREEN, ls=(0, (4, 2)), lw=2.6)
label(790, 872, "lee (ro)", GREEN, ha="right")
arrow((960, 856), (846, 616), GREEN, ls=(0, (1.5, 1.5)), lw=2.6)
ax.text(904, 740, "http_check", ha="center", va="center", rotation=-64.6, rotation_mode="anchor", fontsize=F_LAB * 0.92, fontweight="bold", color=GREEN, bbox=dict(fc="white", ec="none", pad=2.5 * S / 0.373 * 0.373), zorder=5)
arrow((1180, 856), (1180, 800), GREEN, ls=(0, (4, 2)), lw=2.6)
label(1166, 828, "/metrics ×3", GREEN, ha="right")
arrow((1284, 858), (1402, 590), GREEN, ls=(0, (4, 2)), rad=-0.3, lw=2.6)
label(1470, 760, "check\npostgres", GREEN)
arrow((1296, 970), (1604, 724), GREEN, ls=(0, (4, 2)), lw=3)
label(1540, 880, "HTTPS", GREEN)

fig.savefig(OUT, dpi=DPI, facecolor="white")
print("ok", OUT)
