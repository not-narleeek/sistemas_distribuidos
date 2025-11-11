REGISTER '/opt/pig/piggybank.jar';
REGISTER '/opt/pig/scripts/udf/text_utils.py' USING jython AS textutils;

%default STOPWORDS '/opt/pig/scripts/stopwords_es.txt'

DEFINE NORMALIZER textutils.Normalizer('$STOPWORDS');

define TOKENIZE_AND_COUNT(data_relation, output_path, top_output_path) returns void {
    cleaned = FOREACH $data_relation GENERATE NORMALIZER.prepare(respuesta_texto) AS text;
    tokens = FOREACH cleaned GENERATE FLATTEN(TOKENIZE(text)) AS token;
    filtered = FILTER tokens BY NORMALIZER.is_valid_token(token);
    grouped = GROUP filtered BY token;
    counts = FOREACH grouped GENERATE group AS palabra, COUNT(filtered) AS freq;
    ordered = ORDER counts BY freq DESC;
    STORE ordered INTO $output_path USING PigStorage(',');
    top = LIMIT ordered 50;
    STORE top INTO $top_output_path USING PigStorage(',');
};
