%default INPUT '/data/input/yahoo/yahoo_respuestas.txt'
%default OUTPUT '/data/output/yahoo'
%default STOPWORDS '/opt/pig/scripts/stopwords_es.txt'
%default TOPN '50'

RAW = LOAD '$INPUT' USING TextLoader() AS (line:chararray);
LOW = FOREACH RAW GENERATE LOWER(line) AS line;
CLEAN = FOREACH LOW GENERATE REPLACE(line,'[^a-záéíóúñü0-9 ]',' ') AS line;
TOK = FOREACH CLEAN GENERATE FLATTEN(TOKENIZE(line)) AS token;
STOP = LOAD '$STOPWORDS' USING TextLoader() AS (sw:chararray);
TOK_CLEAN = FILTER TOK BY (SIZE(token) > 0) AND NOT (token MATCHES '^[0-9]+$');
TOK_JOIN = JOIN TOK_CLEAN BY token LEFT OUTER, STOP BY sw;
TOK_NO_SW = FOREACH (FILTER TOK_JOIN BY STOP::sw IS NULL) GENERATE TOK_CLEAN::token AS token;
GRP = GROUP TOK_NO_SW BY token;
CNT = FOREACH GRP GENERATE group AS token, COUNT(TOK_NO_SW) AS freq;
ORD = ORDER CNT BY freq DESC;
LIM = LIMIT ORD $TOPN;
STORE CNT INTO '$OUTPUT/full' USING PigStorage('\t');
STORE LIM INTO '$OUTPUT/top' USING PigStorage('\t');
