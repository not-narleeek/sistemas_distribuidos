%default INPUT_YAHOO '/data/output/yahoo/full'
%default INPUT_LLM '/data/output/llm/full'
%default OUTPUT '/data/output/compare/wordcount_diff'

ny = LOAD '$INPUT_YAHOO' USING PigStorage('\t') AS (palabra:chararray, freq_yahoo:long);
ll = LOAD '$INPUT_LLM' USING PigStorage('\t') AS (palabra:chararray, freq_llm:long);

joined = JOIN ny BY palabra FULL, ll BY palabra;

comparativo = FOREACH joined GENERATE
    (ny::palabra IS NOT NULL ? ny::palabra : ll::palabra) AS palabra,
    (ny::freq_yahoo IS NOT NULL ? ny::freq_yahoo : 0L) AS freq_yahoo,
    (ll::freq_llm IS NOT NULL ? ll::freq_llm : 0L) AS freq_llm,
    ((ll::freq_llm IS NOT NULL ? ll::freq_llm : 0L) - (ny::freq_yahoo IS NOT NULL ? ny::freq_yahoo : 0L)) AS diff,
    ((double)(ll::freq_llm IS NOT NULL ? ll::freq_llm : 0L)) / ((double)((ny::freq_yahoo IS NOT NULL ? ny::freq_yahoo : 0L) + 1)) AS ratio;

ordered = ORDER comparativo BY diff DESC;
STORE ordered INTO '$OUTPUT' USING PigStorage('\t');
