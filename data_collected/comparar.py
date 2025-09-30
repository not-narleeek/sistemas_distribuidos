import pandas as pd
import argparse
import os

def analizar_csv(path_csv: str):
    df = pd.read_csv(path_csv)

    # Calcular métricas
    total = len(df)
    hits = (df['status'] == "hit").sum() + (df['status'] == "HIT").sum()
    misses = (df['status'] == "miss").sum() + (df['status'] == "MISS").sum()

    hit_rate = hits / total if total > 0 else 0
    miss_rate = misses / total if total > 0 else 0
    avg_latency = df['latency'].mean()
    avg_score = df['score'].mean()

    return {
        "archivo": os.path.basename(path_csv),
        "hit_rate": hit_rate,
        "miss_rate": miss_rate,
        "latencia_promedio": avg_latency,
        "score_promedio": avg_score
    }

def comparar_archivos(files):
    resultados = []
    for f in files:
        resultados.append(analizar_csv(f))

    df_resumen = pd.DataFrame(resultados)

    # Determinar "mejor" archivo
    # Reglas: mayor hit_rate, menor latencia, mayor score
    df_resumen['rank'] = (
        df_resumen['hit_rate'].rank(ascending=False) +
        df_resumen['latencia_promedio'].rank(ascending=True) +
        df_resumen['score_promedio'].rank(ascending=False)
    )

    mejor = df_resumen.loc[df_resumen['rank'].idxmin()]

    print("\n📊 Comparación de resultados entre archivos:\n")
    print(df_resumen.to_string(index=False))
    print("\n🏆 El archivo con mejor rendimiento es:", mejor['archivo'])

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Comparar resultados de 3 experimentos CSV")
    parser.add_argument("csvfiles", nargs=3, help="Rutas a los archivos CSV")
    args = parser.parse_args()

    comparar_archivos(args.csvfiles)

