import pandas as pd
import matplotlib.pyplot as plt
import argparse
import os

def analizar_csv(path_csv: str):
    # Cargar dataset
    df = pd.read_csv(path_csv)

    # Convertir timestamp a datetime
    df['timestamp'] = pd.to_datetime(df['timestamp'])

    # Obtener nombre base del archivo (sin extensión)
    base_name = os.path.splitext(os.path.basename(path_csv))[0]

    # ---- Gráfico 1: Variación de Hit/Miss Rate ----
    resumen_cache = (
        df.groupby([pd.Grouper(key='timestamp', freq='1Min'), 'status'])
        .size()
        .unstack(fill_value=0)
    )

    # Evitar división por cero
    resumen_cache['hit_rate'] = resumen_cache.get('hit', 0) / (resumen_cache.sum(axis=1))
    resumen_cache['miss_rate'] = 1 - resumen_cache['hit_rate']

    plt.figure(figsize=(10, 5))
    plt.plot(resumen_cache.index, resumen_cache['hit_rate'], label="Hit Rate", marker="o")
    plt.plot(resumen_cache.index, resumen_cache['miss_rate'], label="Miss Rate", marker="x")
    plt.title("Variación de Hit/Miss Rate")
    plt.xlabel("Tiempo")
    plt.ylabel("Proporción")
    plt.legend()
    plt.grid(True)

    filename1 = f"variacion_hit_miss_{base_name}.png"
    plt.savefig(filename1, bbox_inches="tight")
    plt.close()

    # ---- Gráfico 2: Evaluación del rendimiento ----
    fig, ax1 = plt.subplots(figsize=(10, 5))

    ax1.set_title("Evaluación del rendimiento")
    ax1.set_xlabel("Tiempo")

    ax1.set_ylabel("Latencia (ms)", color="tab:red")
    ax1.plot(df['timestamp'], df['latency'], color="tab:red", alpha=0.7, label="Latencia")
    ax1.tick_params(axis="y", labelcolor="tab:red")

    ax2 = ax1.twinx()
    ax2.set_ylabel("Score", color="tab:blue")
    ax2.plot(df['timestamp'], df['score'], color="tab:blue", alpha=0.7, label="Score")
    ax2.tick_params(axis="y", labelcolor="tab:blue")

    fig.tight_layout()

    filename2 = f"evaluacion_rendimiento_{base_name}.png"
    plt.savefig(filename2, bbox_inches="tight")
    plt.close()

    print(f"Gráficas guardadas como: {filename1}, {filename2}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Analizar logs de cache y rendimiento desde un CSV")
    parser.add_argument("csvfile", type=str, help="Ruta al archivo CSV de entrada")
    args = parser.parse_args()

    analizar_csv(args.csvfile)

