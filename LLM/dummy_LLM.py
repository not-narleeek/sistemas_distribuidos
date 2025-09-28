import socket
import json
import re
from pymongo import MongoClient
from bson import ObjectId
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity



def similarity_score(best_answer, llm_answer):
    vectorizer = TfidfVectorizer().fit([best_answer, llm_answer])
    vectors = vectorizer.transform([best_answer, llm_answer])
    score = cosine_similarity(vectors[0], vectors[1])[0][0]
    return round(float(score), 4)



def summarize_text(text):
    sentences = re.split(r'[.!?]', text)
    return sentences[0].strip() if sentences else text



def generate_answer(question_title, question_content):
    summary = summarize_text(question_content)
    return f"In short, '{question_title}' can be explained as: {summary}."



def run_dummy_server(host="0.0.0.0", port=6000,
                     mongo_uri="mongodb://mongo:27017/",
                     db_name="yahoo_db", coll_name="questions"):

    client = MongoClient(mongo_uri)
    collection = client[db_name][coll_name]

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind((host, port))
    server.listen(5)
    print(f"[DummyLLM] Servidor escuchando en {host}:{port}...")

    while True:
        conn, _ = server.accept()
        with conn:
            data = conn.recv(4096).decode().strip()
            if not data:
                continue

            try:
                payload = json.loads(data)
            except json.JSONDecodeError:
                conn.sendall("INVALID_JSON\n".encode())
                continue

            qid = payload.get("id")
            title = payload.get("title", "")
            content = payload.get("content", "")

            if not qid:
                conn.sendall("MISSING_ID\n".encode())
                continue

            
            try:
                doc = collection.find_one({"_id": ObjectId(qid)})
                best_answer = doc.get("best_answer", "") if doc else ""
            except Exception:
                best_answer = ""

            
            llm_answer = generate_answer(title, content)

            
            score = similarity_score(best_answer, llm_answer) if best_answer else 0.0

            response = {
                "generated_answer": llm_answer,
                "score": score
            }
            conn.sendall((json.dumps(response) + "\n").encode())


if __name__ == "__main__":
    run_dummy_server()
