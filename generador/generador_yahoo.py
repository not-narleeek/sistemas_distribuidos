import argparse
import time
import random
import socket
import json
from pymongo import MongoClient
from datetime import datetime
import csv



def poisson_interarrival(lmbda):
    return random.expovariate(lmbda)

def uniform_interarrival(low, high):
    return random.uniform(low, high)



def query_system(payload, host='localhost', port=5000):
    try:
        with socket.create_connection((host, port), timeout=5) as sock:
            sock.sendall((json.dumps(payload) + "\n").encode())
            response = sock.recv(8192).decode().strip()
            return response
    except Exception as e:
        return f"ERROR {str(e)}"



def log_to_csv(filepath, row):
    with open(filepath, mode='a', newline='', encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(row)



def run_generator(dist, params, total_queries, mongo_uri, db_name, coll_name, cache_host, cache_port):
    client = MongoClient(mongo_uri)
    coll = client[db_name][coll_name]

    
    docs = list(coll.find({}, {"question_title": 1, "question_content": 1}))
    if not docs:
        print("No se encontraron preguntas en la colección.")
        return

    print(f"[Generator] {len(docs)} preguntas cargadas. Generando {total_queries} consultas usando '{dist}'...")

    
    csv_file = 'traffic_log.csv'
    with open(csv_file, 'w', newline='', encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(['timestamp', 'operation', 'id', 'title', 'status', 'latency', 'score'])

    
    for i in range(1, total_queries + 1):
        
        wait = poisson_interarrival(params['lmbda']) if dist == 'poisson' else uniform_interarrival(params['low'], params['high'])
        time.sleep(wait)

        
        doc = random.choice(docs)
        payload = {
            "id": str(doc["_id"]),
            "title": doc.get("question_title", ""),
            "content": doc.get("question_content", "")
        }

        
        start = time.time()
        response = query_system(payload, host=cache_host, port=cache_port)
        latency = time.time() - start
        timestamp = datetime.now().isoformat(timespec='seconds')

        
        score = ""
        if response.startswith("HIT"):
            operation = "GET"
            status = "HIT"
        elif response.startswith("MISS"):
            operation = "GET"
            status = "MISS"
            
            try:
                json_part = response.split("\n", 1)[1]
                parsed = json.loads(json_part)
                score = parsed.get("score", "")
            except Exception:
                pass
        elif response.startswith("ERROR"):
            operation = "GET"
            status = "ERROR"
        else:
            operation = "GET"
            status = "UNKNOWN"

        print(f"[{i:04d}] {operation} {payload['id']} → {status} · {latency:.3f}s · Score={score}")
        log_to_csv(csv_file, [timestamp, operation, payload["id"], payload["title"][:50], status, round(latency, 4), score])

    print("[Generator] Finalizado.")



if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generador de tráfico sintético para Yahoo Answers")
    parser.add_argument('--dist', choices=['poisson','uniform'], required=True)
    parser.add_argument('--lmbda', type=float, default=1.0)
    parser.add_argument('--low', type=float, default=0.5)
    parser.add_argument('--high', type=float, default=2.0)
    parser.add_argument('--n', type=int, default=1000)
    parser.add_argument('--mongo', type=str, default="mongodb://mongo:27017/")
    parser.add_argument('--db', type=str, default="yahoo_db")
    parser.add_argument('--coll', type=str, default="questions")
    parser.add_argument('--cache_host', type=str, default='localhost')
    parser.add_argument('--cache_port', type=int, default=5000)

    args = parser.parse_args()
    params = {'lmbda': args.lmbda, 'low': args.low, 'high': args.high}
    run_generator(args.dist, params, args.n, args.mongo, args.db, args.coll, args.cache_host, args.cache_port)
