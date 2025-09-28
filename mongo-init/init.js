db = db.getSiblingDB("yahoo_db");

db.createCollection("questions");

// Cargar datos desde bdd.json
var file = cat("/docker-entrypoint-initdb.d/bdd.json");
var docs = file.split("\n");
docs.forEach(function(line) {
    if (line.trim().length > 0) {
        db.questions.insertOne(JSON.parse(line));
    }
});

print("✅ Datos importados en yahoo_db.questions");
