from neo4j_query import run_cypher


print(run_cypher("MATCH (n) RETURN n"))
