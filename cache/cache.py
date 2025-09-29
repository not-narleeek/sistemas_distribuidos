from collections import OrderedDict, defaultdict
from pymongo import MongoClient
from bson import ObjectId, json_util
import socket
import time
import argparse
import json
import sys


class CacheBase:
    def __init__(self, size):
        self.size = size
        self.cache = {}
        self.hits = 0
        self.misses = 0

    def get(self, key):
        raise NotImplementedError

    def put(self, key, value):
        raise NotImplementedError

    def stats(self):
        return {"hits": self.hits, "misses": self.misses}


class LRUCache(CacheBase):
    def __init__(self, size):
        super().__init__(size)
        self.order = OrderedDict()

    def get(self, key):
        if key in self.order:
            self.order.move_to_end(key)
            self.hits += 1
            return self.cache[key]
        self.misses += 1
        return None

    def put(self, key, value):
        if key in self.order:
            self.order.move_to_end(key)
        else:
            if len(self.order) >= self.size:
                old_key = next(iter(self.order))
                self.order.pop(old_key)
                self.cache.pop(old_key)
            self.order[key] = None
        self.cache[key] = value


class LFUCache(CacheBase):
    def __init__(self, size):
        super().__init__(size)
        self.freq = defaultdict(int)

    def get(self, key):
        if key in self.cache:
            self.freq[key] += 1
            self.hits += 1
            return self.cache[key]
        self.misses += 1
        return None

    def put(self, key, value):
        if key not in self.cache and len(self.cache) >= self.size:
            least_used = min(self.freq, key=lambda k: self.freq[k])
            del self.cache[least_used]
            del self.freq[least_used]
        self.cache[key] = value
        self.freq[key] += 1


class FIFOCache(CacheBase):
    def __init__(self, size):
        super().__init__(size)
        self.queue = []

    def get(self, key):
        if key in self.cache:
            self.hits += 1
            return self.cache[key]
        self.misses += 1
        return None

    def put(self, key, value):
        if key not in self.cache:
            if len(self.cache) >= self.size:
                # Elimina el primero que entró
                oldest_key = self.queue.pop(0)
                del self.cache[oldest_key]
            self.queue.append(key)
        self.cache[key] = value


def query_dummy(payload, host="mongo", port=6000):
    try:
        with socket.create_connection((host, port), timeout=10) as sock:
            sock.sendall((json.dumps(payload) + "\n").encode())
            response = sock.recv(8192).decode().strip()
            return response
    except Exception as e:
        print(f"[Cache] Error conectando con dummy LLM: {e}", file=sys.stderr)
        return json.dumps({"generated_answer": "", "score": 0.0, "error": str(e)})


def wait_for_service(host, port, timeout=60):
    """Espera a que un servicio esté disponible"""
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            with socket.create_connection((host, port), timeout=2):
                print(f"[Cache] Servicio {host}:{port} está disponible")
                return True
        except (socket.error, ConnectionRefusedError):
            print(f"[Cache] Esperando a {host}:{port}...")
            time.sleep(2)
    return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--policy', choices=['lru', 'lfu', 'fifo'], required=True)
    parser.add_argument('--size', type=int, default=100)
    parser.add_argument('--mongo', default='mongodb://mongo:27017/')
    parser.add_argument('--db', default='yahoo_db')
    parser.add_argument('--coll', default='questions')
    parser.add_argument('--port', type=int, default=5000)
    parser.add_argument('--dummy_host', default="mongo")
    parser.add_argument('--dummy_port', type=int, default=6000)
    args = parser.parse_args()

    print(f"[Cache] Iniciando con politica {args.policy.upper()} y tamaño {args.size}")
    if args.policy == 'lru':
        cache = LRUCache(args.size)
    elif args.policy == 'lfu':
        cache = LFUCache(args.size)
    elif args.policy == 'fifo':
        cache = FIFOCache(args.size)
    else:
        print(f"[Cache] Política desconocida: {args.policy}")
        sys.exit(1)


    # Esperar a que MongoDB esté disponible
    print("[Cache] Esperando a MongoDB...")
    mongo_host = args.mongo.split('://')[1].split(':')[0] if '://' in args.mongo else 'localhost'
    if not wait_for_service(mongo_host, 27017):
        print("[Cache] Error: MongoDB no está disponible")
        sys.exit(1)

    # Esperar a que dummy LLM esté disponible
    print("[Cache] Esperando a dummy LLM...")
    if not wait_for_service(args.dummy_host, args.dummy_port):
        print("[Cache] Error: Dummy LLM no está disponible")
        sys.exit(1)
    # Conectar a MongoDB
    try:
        client = MongoClient(args.mongo)
        # Verificar conexión
        client.admin.command('ping')
        collection = client[args.db][args.coll]
        print(f"[Cache] Conectado a MongoDB: {args.mongo}")
    except Exception as e:
        print(f"[Cache] Error conectando a MongoDB: {e}")
        sys.exit(1)

    # Iniciar servidor
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        server.bind(("0.0.0.0", args.port))
        server.listen(5)
        print(f"[Cache] Esperando conexiones en puerto {args.port}...")
    except Exception as e:
        print(f"[Cache] Error iniciando servidor: {e}")
        sys.exit(1)

    while True:
        try:
            conn, addr = server.accept()
            print(f"[Cache] Conexión recibida de {addr}")
            with conn:
                data = conn.recv(4096).decode().strip()
                if not data:
                    continue

                if data.upper() == "STATS":
                    stats = cache.stats()
                    conn.sendall(json.dumps(stats).encode())
                    continue

                try:
                    payload = json.loads(data)
                except json.JSONDecodeError:
                    conn.sendall("INVALID_JSON\n".encode())
                    continue

                key = payload.get("id")
                if not key:
                    conn.sendall("MISSING_ID\n".encode())
                    continue

                start = time.time()
                doc = cache.get(key)
                if doc:
                    latency = time.time() - start
                    response = f"HIT {key} ({latency:.4f}s)\n{json_util.dumps(doc)}\n"
                    conn.sendall(response.encode())
                    print(f"[Cache] HIT: {key}")
                else:
                    try:
                        object_id = ObjectId(key)
                    except Exception:
                        conn.sendall(f"INVALID_ID {key}\n".encode())
                        continue

                    doc = collection.find_one({"_id": object_id})
                    if doc:
                        cache.put(key, doc)
                        latency = time.time() - start

                        # Consultar dummy LLM
                        dummy_response = query_dummy(payload, host=args.dummy_host, port=args.dummy_port)

                        response = f"MISS {key} ({latency:.4f}s)\n{dummy_response}\n"
                        conn.sendall(response.encode())
                        print(f"[Cache] MISS: {key}")
                    else:
                        conn.sendall(f"NOTFOUND {key}\n".encode())
                        print(f"[Cache] NOT FOUND: {key}")

        except KeyboardInterrupt:
            print("\n[Cache] Cerrando servidor...")
            break
        except Exception as e:
            print(f"[Cache] Error en el servidor: {e}")
            continue

    server.close()


if __name__ == "__main__":
    main()
