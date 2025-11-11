%default INPUT '/data/input/yahoo'
%default OUTPUT '/data/output/yahoo/wordcount'
%default TOP_OUTPUT '/data/output/yahoo/top50'
%default STOPWORDS '/opt/pig/scripts/stopwords_es.txt'

INCLUDE '/opt/pig/scripts/wordcount_common.pig';

raw = LOAD '$INPUT' USING PigStorage(',') AS (
    id_pregunta:chararray,
    respuesta_texto:chararray,
    origen:chararray,
    ts_creacion:chararray
);

clean = FILTER raw BY id_pregunta != 'id_pregunta';

TOKENIZE_AND_COUNT(clean, '$OUTPUT', '$TOP_OUTPUT');
