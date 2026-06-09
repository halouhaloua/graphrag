# Auto-generated from base_config.yaml. Do not edit manually.
# Run scripts/generate_prompts.py to regenerate.

prompts = {
        # 图构建提示词，非演化模式
        "construction_general": """You are a Knowledge Graph Specialist responsible for extracting entities, attributes, and relationships from the input text. 
    Your task is to analyze the provided text and extract as many valuable entities, their attributes, 
    and relations as possible in a structured JSON format.  
    Guidelines:
    1. Prioritize the following predefined schema for extraction;  
    ```{schema}```
    2. Flexibility: If the context does not fit the predefined schema, extract the valuable knowledge as needed;
    3. Conciseness: The Attributes and Triples you extract should be complementary and no semantic redundancy.
    4. Do NOT miss any useful information in the context;
    5. Quality constraints for triples:
     - Do NOT extract meaningless single symbols, punctuation marks, standalone numbers, or pure stopwords (e.g., "a", "the", "it", "this") as entities or relations.
     - Every entity mention and relation phrase must carry concrete semantic meaning within the context.
     - Avoid extracting triples where either entity is an empty string, a single character, or a meaningless placeholder.
     - If a numeric value is an important attribute (e.g., "65%", "2013-2022"), treat it as an attribute value, not as a separate entity.
     - Triples are now 5-element lists: [head_entity, relation, tail_entity, relation_keywords, relation_description].
        * relation_keywords:  One or more high-level keywords summarizing the overarching nature, concepts, or themes of the relationship. Multiple keywords within this field must be separated by a comma `,`(e.g., "adaptation, inspiration source").
        * relation_description: A concise explanation of the nature of the relationship between the source and target entities, providing a clear rationale for their connection.(e.g., "The Shawshank Redemption is based on Stephen King's novella").
        * If the LLM cannot generate keywords or description, use empty string "" for those fields.
     - N-ary Relationship Decomposition: If a single statement describes a relationship involving more than two entities (e.g., "Alice, Bob, and Carol collaborated on Project X"), decompose it into multiple binary (two-entity) relationship pairs.
    6. Context & Objectivity:
     - Ensure all entity names and descriptions are written in the third person.
     - Explicitly name the subject or object; avoid using pronouns such as "this article", "this paper", "I", "you", "he/she".

    Output Format: Return only JSON as **Example Output** with:    
     - Attributes: Map each entity to its descriptive features.    
     - Triples: List relations between entities in `[head, relation, tail, keywords, description]` 5-element format.  
     - Entity_types: Map each entity to its schema type based on the provided schema.
     ```
     input chunk:
     {chunk}
     ```
    Example Output(Use the same language as chunk):{{
        "attributes": {{
            "Stephen King": ["profession: author"],
            "Shawshank Redemption": ["type: movie"],
            "Rita Hayworth and Shawshank Redemption": ["type: novella"],
            "Frank Darabont": ["profession: director"]
            }},
        "triples": [
            ["Shawshank Redemption", "based on", "Rita Hayworth and Shawshank Redemption", "adaptation, inspiration source", "The Shawshank Redemption is adapted from Stephen King's novella"],
            ["Shawshank Redemption", "directed by", "Frank Darabont", "direction, film direction", "Frank Darabont directed this film"]
        ],
        "entity_types": {{
            "Stephen King": "person",
            "Shawshank Redemption": "creative_work",
            "Rita Hayworth and Shawshank Redemption": "creative_work",
            "Frank Darabont": "person"
            }}
        }}""",
        # 图构建提示词，演化模式
        "construction_general_agent": """You are a Knowledge Graph Specialist responsible for extracting entities, attributes, and relationships from the input text. 
    Your task is to analyze the provided text and extract as many valuable entities,
    their attributes, and relations as possible in a structured JSON format.

    Guidelines:
    1. Prioritize the following predefined schema for extraction; 
    ```{schema}```
    2. Flexibility: If the context does not fit the predefined schema, extract the valuable knowledge as needed;
    3. Conciseness: The Attributes and Triples you extract should be complementary and no semantic redundancy.
    4. Do NOT miss any useful information in the context;
    5. Quality constraints for triples:
     - Do NOT extract meaningless single symbols, punctuation marks, standalone numbers, or pure stopwords (e.g., "a", "the", "it", "this") as entities or relations.
     - Every entity mention and relation phrase must carry concrete semantic meaning within the context.
     - Avoid extracting triples where either entity is an empty string, a single character, or a meaningless placeholder.
     - If a numeric value is an important attribute (e.g., "65%", "2013-2022"), treat it as an attribute value, not as a separate entity.
     - Triples are now 5-element lists: [head_entity, relation, tail_entity, relation_keywords, relation_description].
        * relation_keywords:  One or more high-level keywords summarizing the overarching nature, concepts, or themes of the relationship. Multiple keywords within this field must be separated by a comma `,`(e.g., "adaptation, inspiration source").
        * relation_description: A concise explanation of the nature of the relationship between the source and target entities, providing a clear rationale for their connection.(e.g., "The Shawshank Redemption is based on Stephen King's novella").
        * If the LLM cannot generate keywords or description, use empty string "" for those fields.
     - N-ary Relationship Decomposition: If a single statement describes a relationship involving more than two entities (e.g., "Alice, Bob, and Carol collaborated on Project X"), decompose it into multiple binary (two-entity) relationship pairs.
    6. Context & Objectivity:
     - Ensure all entity names and descriptions are written in the third person.
     - Explicitly name the subject or object; avoid using pronouns such as "this article", "this paper", "I", "you", "he/she".

    Output Format: Return only JSON as **Example Output** with:
    - Attributes: Map each entity to its descriptive features.
    - Triples: List relations between entities in `[head, relation, tail, keywords, description]` 5-element format.
    - Entity_types: Map each entity to its schema type based on the provided schema.

    Schema Evolution: If you find new and important entity types, relation types,
    or attribute types that are valuable for knowledge extraction,
    include them in a "new_schema_types" field. Notably,
    only when the new type is clearly distinct from all existing types and of high importance.
     ```
     input chunk:
     {chunk}
     ```
    Example Output(Return ONLY the JSON object. No other text.Use the same language as chunk):{{
        "attributes": {{
            "Stephen King": ["profession: author"],
            "Shawshank Redemption": ["type: movie"],
            "Rita Hayworth and Shawshank Redemption": ["type: novella"],
            "Frank Darabont": ["profession: director"]
            }},
        "triples":[
            ["Shawshank Redemption", "based on", "Rita Hayworth and Shawshank Redemption", "adaptation, inspiration source", "The Shawshank Redemption is adapted from Stephen King's novella"],
            ["Shawshank Redemption", "directed by", "Frank Darabont", "direction, film direction", "Frank Darabont directed this film"]
            ],
        "entity_types": {{
            "Stephen King": "person",
            "Shawshank Redemption": "creative_work",
            "Rita Hayworth and Shawshank Redemption": "creative_work",
            "Frank Darabont": "person"
            }},
        "new_schema_types": {{
            "nodes": ["Novella"],
            "relations": ["adapted_into"],
            "attributes": ["publication_year"]
            }}
        }}""",
        # 问题分解提示词
        "decomposition_general": """You are a professional question decomposition expert specializing in multi-hop reasoning.
    Given the following ontology and the question, decompose the complex question into 2-3 focused sub-questions and identify involved schema types.
    CRITICAL REQUIREMENTS:1. Each sub-question must be:  
    - Specific and focused on a single fact or relationship by identifing all entities, relationships, and reasoning steps needed  
    - Answerable independently with the given ontology  - Explicitly reference entities and relations from the original question  
    - Designed to retrieve relevant knowledge for the final answer2. For simple questions (1-2 hop), return the original question as a single sub-question3. Analyze the question and identify all schema types that might be involved4. Only return a concise JSON object with sub_questions array and involved_types object.
    5. For each sub-question, also output:
       - "search_query": Extract 3-5 key terms/phrases optimized for vector similarity search. Remove generic query words like "introduce", "describe", "explain", "what is". Keep entity names, relations, and distinguishing attributes.
       - "type": Classify the sub-question:
         * "micro": asks about a specific entity's attributes or identity
         * "macro": involves comparisons, influences, causality, or themes
    6. Each sub-question object format:
    {{
      "sub-question": "readable question text",
      "search_query": "keyword1 keyword2 keyword3",
      "type": "micro"
    }}
    Ontology:{ontology}
    Question: {question}
    Example for complex question:Original: "Which film has the director died earlier, Ethnic Notions or Gordon Of Ghost City?
    "Output:{{
    "sub_questions": [
            {{
              "sub-question": "Who is the director of Ethnic Notions?",
              "search_query": "Ethnic Notions director filmmaker",
              "type": "micro"
            }},
            {{
              "sub-question": "Who is the director of Gordon Of Ghost City?",
              "search_query": "Gordon Of Ghost City director filmmaker",
              "type": "micro"
            }},
            {{
              "sub-question": "When did the director of Ethnic Notions die?",
              "search_query": "Ethnic Notions director death year",
              "type": "micro"
            }},
            {{
              "sub-question": "When did the director of Gordon Of Ghost City die?",
              "search_query": "Gordon Of Ghost City director death year",
              "type": "micro"
            }}
            ], 
    "involved_types":{{
            "nodes": ["creative_work", "person"],
            "relations": ["directed_by"],
            "attributes": ["name", "date"]
            }}
        }}
    Example for simple question:Original: "What is the capital of France?
    "Output:{{
    "sub_questions":
            [
            {{
              "sub-question": "What is the capital of France?",
              "search_query": "France capital city",
              "type": "micro"
            }}
            ],
    "involved_types": {{
            "nodes": ["location"],
            "relations": ["located_in"],
            "attributes": ["name"]
            }}
        }}""",
        # 问题回答提示词
        "retrieval_general": '''You are an expert knowledge assistant.
    Your task is to answer the question based on the provided knowledge context.
      1. Use ONLY the information from the provided knowledge context and try your best to answer the question.
      2. If the knowledge is insufficient, reject to answer the question.
      3. Be precise and concise in your answer.
      4. For factual questions, provide the specific fact or entity name.
      5. For temporal questions, provide the specific date, year, or time.
    periodQuestion: {question}
    Knowledge Context:{context}
    Answer(be specific and direct):''',
        # 问题迭代回复提示词
        "retrieval_ircot": '''You are an expert knowledge assistant using iterative retrieval with chain-of-thought reasoning.
    Think step by step about if additional information you need to answer the question completely and accurately.
    Instructions:
      1. Analyze the current knowledge context and the question.
      2. Think about what information might be missing or unclear.
      3. If you have enough information to answer, in the end of your response, write "So the answer is:" followed by your final answer.
      4. If you need more information, in the end of your response, write a specific query begin with "The new query is:" to retrieve additional relevant information.
      5. Be specific and focused in your reasoning.
    Current Question: {current_query}
    Available Knowledge Context:{context}
    Previous Thoughts: {previous_thoughts}
    Step {step}: 
    Your reasoning:''',
}
