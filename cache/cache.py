from collections import OrderedDict, defaultdict
from pymongo import MongoClient
from bson import ObjectId, json_util
import socket
import time
import argparse
import json


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



def query_dummy(payload, host="localhost", port=6000):
    try:
        with socket.create_connection((host, port), timeout=5) as sock:
            sock.sendall((json.dumps(payload) + "\n").encode())
            response = sock.recv(8192).decode().strip()
            return response
    except Exception as e:
        return json.dumps({"generated_answer": "", "score": 0.0, "error": str(e)})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--policy', choices=['lru', 'lfu'], required=True)
    parser.add_argument('--size', type=int, default=100)
    parser.add_argument('--mongo', default='mongodb://localhost:27017/')
    parser.add_argument('--db', default='yahoo_db')
    parser.add_argument('--coll', default='questions')
    parser.add_argument('--port', type=int, default=5000)
    parser.add_argument('--dummy_host', default="localhost")
    parser.add_argument('--dummy_port', type=int, default=6000)
    args = parser.parse_args()

    print(f"[Cache] Iniciando con política {args.policy.upper()} y tamaño {args.size}")
    cache = LRUCache(args.size) if args.policy == 'lru' else LFUCache(args.size)

    client = MongoClient(args.mongo)
    collection = client[args.db][args.coll]

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("0.0.0.0", args.port))
    server.listen(5)
    print(f"[Cache] Esperando conexiones en puerto {args.port}...")

    while True:
        conn, addr = server.accept()
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

                    
                    dummy_response = query_dummy(payload, host=args.dummy_host, port=args.dummy_port)

                    response = f"MISS {key} ({latency:.4f}s)\n{dummy_response}\n"
                    conn.sendall(response.encode())
                else:
                    conn.sendall(f"NOTFOUND {key}\n".encode())


if __name__ == "__main__":
    main()
